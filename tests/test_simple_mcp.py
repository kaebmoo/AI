
import sys
import os
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import anyio

logging.basicConfig(level=logging.INFO)

async def main():
    print("Testing direct MCP connection...")
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_servers.nt_metadata_mcp"],
        env=os.environ.copy()
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("Connected!")
                
                tools = await session.list_tools()
                print(f"Tools: {[t.name for t in tools.tools]}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    anyio.run(main)
