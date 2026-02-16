"""
Test script for README-based dev vs prod conversation flows.

This script tests:
1. Dev environment conversation (4-6 questions, simple)
2. Prod environment conversation (10-12 questions, detailed)
3. README context usage in questions
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.conversation_manager import ConversationManager
from app.core.logger import get_logger

logger = get_logger(__name__)


async def test_dev_conversation():
    """Test development environment conversation flow."""
    print("\n" + "="*80)
    print("TEST 1: DEV ENVIRONMENT CONVERSATION")
    print("="*80 + "\n")
    
    manager = ConversationManager()
    
    # Create session with a sample repo
    print("📝 Creating session with sample repo (facebook/react)...")
    session_data = await manager.create_session(
        owner="facebook",
        repo="react",
        github_token="",
        github_branch=""
    )
    
    session_id = session_data["session_id"]
    print(f"✅ Session created: {session_id}\n")
    print(f"🤖 Bot: {session_data['bot_response']}\n")
    
    # Simulate dev conversation
    conversation_steps = [
        "AWS",
        "dev",
        "us-east-1",
        "t3.micro",
        "No, I'll use MongoDB Atlas free tier",
        "Yes, basic CloudWatch logging"
    ]
    
    question_count = 0
    for i, user_input in enumerate(conversation_steps, 1):
        print(f"👤 User: {user_input}\n")
        
        response = await manager.process_message(session_id, user_input)
        question_count = i
        
        print(f"🤖 Bot: {response.bot_response}\n")
        
        if response.suggestions:
            print(f"💡 Suggestions: {', '.join(response.suggestions)}\n")
        
        if response.is_complete:
            print("✅ Conversation complete!")
            break
        
        print("-" * 80 + "\n")
    
    # Verify dev conversation characteristics
    print("\n📊 DEV CONVERSATION ANALYSIS:")
    print(f"   - Total questions: {question_count}")
    print(f"   - Expected range: 4-6 questions")
    print(f"   - Status: {'✅ PASS' if 4 <= question_count <= 6 else '❌ FAIL'}")
    
    session = manager.get_session(session_id)
    params = session.collected_parameters
    
    print(f"\n📋 Collected Parameters:")
    print(f"   - Environment: {params.get('environment')}")
    print(f"   - Cloud Provider: {params.get('cloud_provider')}")
    print(f"   - Region: {params.get('aws_region') or params.get('region')}")
    print(f"   - Instance Type: {params.get('instance_type')}")
    
    return session_id, question_count


async def test_prod_conversation():
    """Test production environment conversation flow."""
    print("\n" + "="*80)
    print("TEST 2: PROD ENVIRONMENT CONVERSATION")
    print("="*80 + "\n")
    
    manager = ConversationManager()
    
    # Create session with a sample repo
    print("📝 Creating session with sample repo (expressjs/express)...")
    session_data = await manager.create_session(
        owner="expressjs",
        repo="express",
        github_token="",
        github_branch=""
    )
    
    session_id = session_data["session_id"]
    print(f"✅ Session created: {session_id}\n")
    print(f"🤖 Bot: {session_data['bot_response']}\n")
    
    # Simulate prod conversation
    conversation_steps = [
        "AWS",
        "production",
        "5000 DAU, about 100 requests per second peak",
        "Yes, Multi-AZ with load balancer",
        "2x t3.medium with auto-scaling",
        "RDS PostgreSQL with 50GB storage",
        "Yes, ElastiCache Redis",
        "CloudWatch Logs, Secrets Manager, and SSM",
        "Yes, all CloudWatch alarms",
        "7 days backup retention",
        "203.0.113.50/32",
        "Yes, that looks good"
    ]
    
    question_count = 0
    for i, user_input in enumerate(conversation_steps, 1):
        print(f"👤 User: {user_input}\n")
        
        response = await manager.process_message(session_id, user_input)
        question_count = i
        
        print(f"🤖 Bot: {response.bot_response}\n")
        
        if response.suggestions:
            print(f"💡 Suggestions: {', '.join(response.suggestions)}\n")
        
        if response.is_complete:
            print("✅ Conversation complete!")
            break
        
        print("-" * 80 + "\n")
    
    # Verify prod conversation characteristics
    print("\n📊 PROD CONVERSATION ANALYSIS:")
    print(f"   - Total questions: {question_count}")
    print(f"   - Expected range: 10-12 questions")
    print(f"   - Status: {'✅ PASS' if 10 <= question_count <= 12 else '❌ FAIL'}")
    
    session = manager.get_session(session_id)
    params = session.collected_parameters
    
    print(f"\n📋 Collected Parameters:")
    print(f"   - Environment: {params.get('environment')}")
    print(f"   - Cloud Provider: {params.get('cloud_provider')}")
    print(f"   - Region: {params.get('aws_region') or params.get('region')}")
    print(f"   - Instance Type: {params.get('instance_type')}")
    print(f"   - Instance Count: {params.get('instance_count')}")
    print(f"   - Load Balancer: {params.get('load_balancer_type')}")
    
    return session_id, question_count


async def test_readme_context_usage():
    """Test that README context is properly used in questions."""
    print("\n" + "="*80)
    print("TEST 3: README CONTEXT USAGE")
    print("="*80 + "\n")
    
    manager = ConversationManager()
    
    # Create session with a repo that has specific tech stack
    print("📝 Creating session with sample repo (nodejs/node)...")
    session_data = await manager.create_session(
        owner="nodejs",
        repo="node",
        github_token="",
        github_branch=""
    )
    
    session_id = session_data["session_id"]
    print(f"✅ Session created: {session_id}\n")
    
    # Check if bot response references README
    bot_response = session_data['bot_response']
    print(f"🤖 Initial Bot Response:\n{bot_response}\n")
    
    # Check for README context indicators
    readme_indicators = [
        "I see",
        "I noticed",
        "Your README",
        "Based on",
        "README shows",
        "README mentions"
    ]
    
    has_readme_reference = any(indicator.lower() in bot_response.lower() for indicator in readme_indicators)
    
    print(f"\n📊 README CONTEXT ANALYSIS:")
    print(f"   - Bot references README: {'✅ YES' if has_readme_reference else '❌ NO'}")
    print(f"   - Status: {'✅ PASS' if has_readme_reference else '❌ FAIL'}")
    
    # Get session and check README context
    session = manager.get_session(session_id)
    readme_context = session.collected_parameters.get('readme_context', '')
    
    print(f"\n📋 README Context Extracted:")
    print(f"   - Length: {len(readme_context)} characters")
    print(f"   - Has context: {'✅ YES' if readme_context else '❌ NO'}")
    
    if readme_context:
        # Show first 500 chars
        print(f"\n📄 README Context Preview:")
        print(readme_context[:500] + "..." if len(readme_context) > 500 else readme_context)
    
    return session_id, has_readme_reference


async def main():
    """Run all tests."""
    print("\n" + "🚀 " * 20)
    print("README-BASED DEV VS PROD CONVERSATION TESTS")
    print("🚀 " * 20)
    
    try:
        # Test 1: Dev conversation
        dev_session, dev_questions = await test_dev_conversation()
        
        # Test 2: Prod conversation
        prod_session, prod_questions = await test_prod_conversation()
        
        # Test 3: README context usage
        readme_session, has_readme_ref = await test_readme_context_usage()
        
        # Final summary
        print("\n" + "="*80)
        print("FINAL TEST SUMMARY")
        print("="*80 + "\n")
        
        dev_pass = 4 <= dev_questions <= 6
        prod_pass = 10 <= prod_questions <= 12
        readme_pass = has_readme_ref
        
        print(f"✅ Dev Environment Test: {'PASS' if dev_pass else 'FAIL'} ({dev_questions} questions)")
        print(f"✅ Prod Environment Test: {'PASS' if prod_pass else 'FAIL'} ({prod_questions} questions)")
        print(f"✅ README Context Test: {'PASS' if readme_pass else 'FAIL'}")
        
        all_pass = dev_pass and prod_pass and readme_pass
        print(f"\n{'🎉 ALL TESTS PASSED!' if all_pass else '⚠️ SOME TESTS FAILED'}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
