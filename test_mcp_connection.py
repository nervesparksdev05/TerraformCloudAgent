import logging
logging.basicConfig(level=logging.DEBUG)
import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession

async def main():
    try:
        async with sse_client("http://localhost:8080/sse") as (read, write):
            async with ClientSession(read, write) as session:
                print("Connected! Initializing...")
                await asyncio.wait_for(session.initialize(), timeout=5)
                tools = await session.list_tools()
                print("Tools:", len(tools.tools))
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
