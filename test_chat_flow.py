"""
Test script to verify the chat functionality end-to-end
"""
import asyncio
import httpx

BASE_URL = "http://localhost:8000"

async def test_chat_flow():
    """Test the complete chat flow"""
    async with httpx.AsyncClient() as client:
        print("=" * 60)
        print("Testing Chat Flow")
        print("=" * 60)
        
        # Step 1: Create conversation
        print("\n1. Creating conversation...")
        response = await client.post(
            f"{BASE_URL}/conversations",
            json={
                "github_url": "https://github.com/tiangolo/fastapi",
                "provider": "aws"
            }
        )
        print(f"Status: {response.status_code}")
        if response.status_code != 201:
            print(f"Error: {response.text}")
            return
        
        data = response.json()
        session_id = data["session_id"]
        print(f"✅ Session created: {session_id}")
        print(f"Bot response: {data['bot_response'][:100]}...")
        
        # Step 2: Analyze README
        print("\n2. Analyzing README...")
        response = await client.get(f"{BASE_URL}/conversations/{session_id}/analyze")
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
        
        data = response.json()
        print(f"✅ README analyzed")
        print(f"Bot response: {data['bot_response'][:100]}...")
        
        # Step 3: Send chat message
        print("\n3. Sending chat message: 'us-east-1'")
        response = await client.post(
            f"{BASE_URL}/conversations/{session_id}/message",
            json={"message": "us-east-1"}
        )
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
        
        data = response.json()
        print(f"✅ Message sent")
        print(f"Bot response: {data['bot_response']}")
        print(f"Suggestions: {data.get('suggestions', [])}")
        print(f"Collected parameters: {data.get('collected_parameters', {})}")
        print(f"Is complete: {data.get('is_complete', False)}")
        
        # Step 4: Send another message
        print("\n4. Sending chat message: 'production'")
        response = await client.post(
            f"{BASE_URL}/conversations/{session_id}/message",
            json={"message": "production"}
        )
        print(f"Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
        
        data = response.json()
        print(f"✅ Message sent")
        print(f"Bot response: {data['bot_response']}")
        print(f"Suggestions: {data.get('suggestions', [])}")
        print(f"Collected parameters: {data.get('collected_parameters', {})}")
        print(f"Is complete: {data.get('is_complete', False)}")
        
        print("\n" + "=" * 60)
        print("✅ Chat flow test completed successfully!")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_chat_flow())
