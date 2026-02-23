import asyncio
import sys
import os

# Add app to path securely
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.llm_service import AsyncLLMService

async def main():
    print("Testing Gemini LLM Connection...")
    try:
        service = AsyncLLMService()
        response = await service.chat_completion(
            messages=[{"role": "user", "content": "Hello!"}],
            temperature=0.7,
            max_tokens=50
        )
        print("Success! Response:")
        print(response)
    except Exception as e:
        print(f"FAILED: {type(e).__name__} - {e}")

if __name__ == "__main__":
    asyncio.run(main())
