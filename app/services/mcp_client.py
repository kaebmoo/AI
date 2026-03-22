
import os
import sys
import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from contextlib import asynccontextmanager, AsyncExitStack

# mcp imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str]
    env: Dict[str, str]

class MCPClientService:
    """
    Service to manage connections to multiple MCP servers and aggregate their tools.
    Designed for extensibility: configured via a list of server configs.
    """
    
    def __init__(self):
        self.servers: Dict[str, ClientSession] = {}
        self.tools: List[Dict[str, Any]] = []
        self.server_configs = self._load_server_configs()

    def _load_server_configs(self) -> List[MCPServerConfig]:
        """Load server configurations."""
        base_path = os.getcwd()
        env = os.environ.copy()

        # IMPORTANT: Pass BUSINESS DB path to MCP servers (not app DB!)
        # MCP servers need the business data DB (revenue, expense views)
        # not the app DB (users, sessions, chats)
        try:
            from app.config import settings
            if 'METADATA_DB_URL' not in env:
                bp = settings.BUSINESS_DB_PATH
                if bp:
                    if not bp.startswith("sqlite"):
                        bp = f"sqlite:///{os.path.abspath(bp)}"
                    env['METADATA_DB_URL'] = bp
                elif settings.DATABASE_URL:
                    env['METADATA_DB_URL'] = settings.DATABASE_URL
        except ImportError:
            pass

        # Ensure we use the correct python interpreter
        python_cmd = sys.executable
        
        configs = [
            MCPServerConfig(
                name="nt-metadata",
                command=python_cmd,
                args=["-m", "mcp_servers.nt_metadata_mcp"],
                env=env
            ),
            MCPServerConfig(
                name="nt-query",
                command=python_cmd,
                args=["-m", "mcp_servers.nt_query_mcp"],
                env=env
            )
        ]
        
        # Future extensibility: Check for Validation Server
        if os.path.exists(os.path.join(base_path, "mcp_servers", "nt_validation_mcp.py")):
            configs.append(MCPServerConfig(
                name="nt-validation",
                command=python_cmd,
                args=["-m", "mcp_servers.nt_validation_mcp"],
                env=env
            ))
            
        # Future extensibility: Check for Reporting Server
        if os.path.exists(os.path.join(base_path, "mcp_servers", "nt_reporting_mcp.py")):
            configs.append(MCPServerConfig(
                name="nt-reporting",
                command=python_cmd,
                args=["-m", "mcp_servers.nt_reporting_mcp"],
                env=env
            ))
            
        return configs

    @asynccontextmanager
    async def connected(self):
        """
        Async Context Manager to maintain connections to all MCP servers.
        Usage:
            async with client.connected():
                # use client
        """
        async with AsyncExitStack() as stack:
            # Connect to all servers
            for config in self.server_configs:
                try:
                    server_params = StdioServerParameters(
                        command=config.command,
                        args=config.args,
                        env=config.env
                    )
                    
                    # Create client connection context
                    stdio_transport = await stack.enter_async_context(stdio_client(server_params))
                    read, write = stdio_transport
                    
                    # Create session context
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    
                    self.servers[config.name] = session
                    logger.info(f"Connected to MCP server: {config.name}")
                    
                except Exception as e:
                    logger.error(f"Failed to connect to MCP server {config.name}: {e}")
            
            try:
                # Initialize tools once connected
                await self.get_tools()
                
                yield self
                
            finally:
                # Cleanup happens automatically when stack exits
                self.servers.clear()
                self.tools.clear()
                logger.info("Closed all MCP connections")

    async def get_tools(self) -> List[Dict[str, Any]]:
        """Fetch and aggregate tools from all connected servers"""
        self.tools = []
        
        for name, session in self.servers.items():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    # Convert MCP tool definition to OpenAI/Gemini compatible format
                    tool_def = {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema
                    }
                    # Tag the tool with its source server for routing execution
                    tool_def["_server"] = name 
                    self.tools.append(tool_def)
                    
            except Exception as e:
                logger.error(f"Failed to list tools from {name}: {e}")
                
        return self.tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool on the appropriate server"""
        
        # Find which server owns this tool
        target_server = None
        for tool in self.tools:
            if tool["name"] == tool_name:
                target_server = tool.get("_server")
                break
        
        if not target_server or target_server not in self.servers:
             # Fallback: try finding simple match if _server meta is missing
             for name, session in self.servers.items():
                 try:
                     tools = await session.list_tools()
                     if any(t.name == tool_name for t in tools.tools):
                         target_server = name
                         break
                 except:
                     continue
        
        if not target_server:
            raise ValueError(f"Tool not found or server unavailable: {tool_name}")
            
        try:
            session = self.servers[target_server]
            result = await session.call_tool(tool_name, arguments)
            
            # Return text content from result
            if result.content and len(result.content) > 0:
                return result.content[0].text
            return ""
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_name} on {target_server}: {e}")
            raise e
