import asyncio
from app.services.conversation_manager import ConversationManager

async def test_logic():
    print("Initializing manager...")
    cm = ConversationManager()
    
    print("\nCreating session with provider=None...")
    # Mocking mongo lookup to fail so we rely on in-memory
    cm.sessions_collection = None 
    
    res = cm.create_session(github_url="https://github.com/foo/bar", provider=None)
    sid = res["session_id"]
    print(f"Session created: {sid}")
    print(f"Initial Bot Response: {res['bot_response'][:100]}...")
    
    session = cm.get_session(sid)
    print(f"Session Provider: '{session.provider}'")
    
    missing = cm._missing_minimum_inputs(session)
    print(f"Missing inputs: {missing}")
    
    if "provider (aws/gcp/azure/digitalocean)" in missing:
        print("✅ PASS: Provider is correctly identified as missing")
    else:
        print("❌ FAIL: Provider is NOT missing! Logic error.")

if __name__ == "__main__":
    asyncio.run(test_logic())
