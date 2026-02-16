"""
Simple test to verify conversation flow works correctly.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.conversation_manager import ConversationManager


async def quick_test():
    """Quick test of conversation flow."""
    print("\n" + "="*80)
    print("QUICK CONVERSATION FLOW TEST")
    print("="*80 + "\n")
    
    manager = ConversationManager()
    
    # Test 1: Create session
    print("1️⃣ Creating session with facebook/react...")
    session_data = await manager.create_session(
        owner="facebook",
        repo="react",
        github_token="",
        github_branch=""
    )
    
    session_id = session_data["session_id"]
    print(f"   ✅ Session: {session_id}")
    print(f"   📝 Bot greeting length: {len(session_data['bot_response'])} chars")
    
    # Check README reference
    greeting = session_data['bot_response']
    has_readme_ref = any(word in greeting.lower() for word in ['readme', 'i see', 'i noticed', 'your'])
    print(f"   {'✅' if has_readme_ref else '❌'} README referenced in greeting: {has_readme_ref}")
    
    # Test 2: Send first message (choose AWS)
    print("\n2️⃣ User chooses AWS...")
    response = await manager.process_message(session_id, "AWS")
    print(f"   ✅ Response received: {len(response.bot_response)} chars")
    print(f"   💡 Suggestions: {response.suggestions}")
    
    # Test 3: Choose dev environment
    print("\n3️⃣ User chooses dev environment...")
    response = await manager.process_message(session_id, "dev")
    print(f"   ✅ Response received: {len(response.bot_response)} chars")
    print(f"   ⚙️ Environment set: {response.collected_parameters.get('environment')}")
    
    # Test 4: Continue conversation
    print("\n4️⃣ User chooses region...")
    response = await manager.process_message(session_id, "us-east-1")
    print(f"   ✅ Response received: {len(response.bot_response)} chars")
    
    # Get session details
    session = manager.get_session(session_id)
    user_turns = sum(1 for m in session.messages if m.get("role") == "user")
    
    print(f"\n📊 RESULTS:")
    print(f"   - User turns: {user_turns}")
    print(f"   - Environment: {session.collected_parameters.get('environment')}")
    print(f"   - Cloud: {session.collected_parameters.get('cloud_provider')}")
    print(f"   - Region: {session.collected_parameters.get('aws_region')}")
    print(f"   - Complete: {session.is_complete}")
    
    print(f"\n✅ Test completed successfully!")
    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(quick_test())
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
