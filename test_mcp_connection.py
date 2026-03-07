import asyncio
from dotenv import load_dotenv
load_dotenv()
from app.services.mcp_service import mcp_manager
from app.core import config

async def test_mcp():
    print(f"ENABLE_TERRAFORM_MCP: {config.ENABLE_TERRAFORM_MCP}")
    print(f"TERRAFORM_MCP_SERVER: {config.TERRAFORM_MCP_SERVER}")
    print("Testing MCP connection...")
    try:
        tools = await mcp_manager.list_tools("terraform", config.TERRAFORM_MCP_SERVER)
        print(f"SUCCESS: Found {len(tools)} tools connected via MCP")
        for t in tools:
            print(f" - {t['name']}")
    except Exception as e:
        print(f"ERROR: MCP connection failed - {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp())
