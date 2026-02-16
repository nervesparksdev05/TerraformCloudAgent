"""
Test the enhanced detailed greeting with technology breakdown.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.conversation_manager import ConversationManager


async def test_detailed_greeting():
    """Test that the greeting includes detailed technology information."""
    print("\n" + "="*80)
    print("TESTING ENHANCED DETAILED GREETING")
    print("="*80 + "\n")
    
    manager = ConversationManager()
    
    # Test with a well-known repo that has clear tech stack
    repos_to_test = [
        ("facebook", "react"),
        ("expressjs", "express"),
        ("django", "django"),
    ]
    
    for owner, repo in repos_to_test:
        print(f"\n{'='*80}")
        print(f"Testing: {owner}/{repo}")
        print(f"{'='*80}\n")
        
        session_data = await manager.create_session(
            owner=owner,
            repo=repo,
            github_token="",
            github_branch=""
        )
        
        greeting = session_data['bot_response']
        
        print(f"🤖 BOT GREETING:\n")
        print(greeting)
        print(f"\n{'─'*80}\n")
        
        # Analyze the greeting
        lines = greeting.split('\n')
        word_count = len(greeting.split())
        
        # Check for technology mentions (bold markdown)
        tech_mentions = greeting.count('**')
        
        # Check for specific keywords
        has_version = any(v in greeting.lower() for v in ['v1', 'v2', 'v3', 'version', '.x'])
        has_port = 'port' in greeting.lower()
        has_infrastructure = any(word in greeting.lower() for word in ['compute', 'instance', 'storage', 'database'])
        has_recommendation = any(word in greeting.lower() for word in ['recommend', 'suggest', 'ideal'])
        
        print(f"📊 ANALYSIS:")
        print(f"   - Lines: {len(lines)}")
        print(f"   - Words: {word_count}")
        print(f"   - Bold tech mentions: {tech_mentions // 2}")  # Divide by 2 since ** appears twice per bold
        print(f"   - Has version info: {'✅' if has_version else '❌'}")
        print(f"   - Mentions ports: {'✅' if has_port else '❌'}")
        print(f"   - Discusses infrastructure: {'✅' if has_infrastructure else '❌'}")
        print(f"   - Includes recommendation: {'✅' if has_recommendation else '❌'}")
        
        # Overall assessment
        is_detailed = (
            len(lines) >= 10 and
            tech_mentions >= 10 and
            has_infrastructure and
            has_recommendation
        )
        
        print(f"\n   Overall: {'✅ DETAILED GREETING' if is_detailed else '⚠️ NEEDS MORE DETAIL'}")
        print()
    
    print(f"\n{'='*80}")
    print("✅ Test completed!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    try:
        asyncio.run(test_detailed_greeting())
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
