
import asyncio
import os
import sys
import logging
import json

# Add project root to path
sys.path.append(os.getcwd())

from app.services.mcp_client import MCPClientService

# Convert async test to sync execution
async def main():
    print("🚀 Starting MCP Integration Test...")
    
    # 1. Initialize Service
    try:
        client = MCPClientService()
        print("✅ MCPClientService initialized.")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return

    # 2. Connect
    try:
        async with client.connected():
            print("✅ Connected to MCP Servers.")
            
            # 3. List Tools
            try:
                # Tools are already loaded on connect, but we can verify
                tools = client.tools
                print(f"✅ Found {len(tools)} tools.")
                for t in tools:
                    print(f"   - {t['name']} (from {t.get('_server', 'unknown')})")
                    
                # Verify specific tools exist
                tool_names = [t['name'] for t in tools]
                assert 'execute_query' in tool_names
                assert 'get_available_contexts' in tool_names
                print("✅ Required tools found.")
                
            except Exception as e:
                print(f"❌ Failed to list tools: {e}")
                return

            # 4. Test Tool Execution (Execute Query)
            print("\n🧪 Testing Tool Execution: execute_query...")
            try:
                # Simple test query using default sqlite db
                sql = "SELECT 1 as test_col"
                result = await client.call_tool("execute_query", {"sql": sql, "explanation": "Test query"})
                print(f"✅ Result: {result}")
                
            except Exception as e:
                print(f"❌ Execution failed: {e}")
            
            # 5. Test Metadata Tool
            print("\n🧪 Testing Tool Execution: get_available_contexts...")
            try:
                result = await client.call_tool("get_available_contexts", {})
                print(f"✅ Contexts: {str(result)[:100]}...")
            except Exception as e:
                print(f"❌ Execution failed: {e}")
    
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        import traceback
        traceback.print_exc()

    print("\n🏁 Test Completed.")

if __name__ == "__main__":
    import anyio
    anyio.run(main)
