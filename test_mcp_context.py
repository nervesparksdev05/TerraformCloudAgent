import asyncio
from app.services.llm_generator import LLMGenerator
from app.core import config
from app.core.logger import setup_logging

setup_logging()

async def main():
    config.ENABLE_TERRAFORM_MCP = True
    print("Initializing LLMGenerator...")
    gen = LLMGenerator()
    print("Gathering MCP Context for VPC...")
    ctx = await gen._gather_mcp_context_async("I want to create an AWS VPC with CIDR 10.0.0.0/16.")
    print("\n--- MCP CONTEXT RESULT ---")
    print(ctx)

if __name__ == "__main__":
    asyncio.run(main())
