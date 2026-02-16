"""
Simple demo of the enhanced detailed greeting.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.conversation_manager import ConversationManager


async def demo_greeting():
    """Demo the enhanced greeting."""
    print("\n" + "="*100)
    print("DEMO: Enhanced Detailed Technology Greeting")
    print("="*100 + "\n")
    
    manager = ConversationManager()
    
    print("Creating session for: expressjs/express\n")
    
    session_data = await manager.create_session(
        owner="expressjs",
        repo="express",
        github_token="",
        github_branch=""
    )
    
    greeting = session_data['bot_response']
    
    print("🤖 BOT GREETING:")
    print("─" * 100)
    print(greeting)
    print("─" * 100)
    
    # Count details
    lines = [l for l in greeting.split('\n') if l.strip()]
    bold_count = greeting.count('**') // 2
    
    print(f"\n📊 GREETING STATISTICS:")
    print(f"   • Total lines: {len(lines)}")
    print(f"   • Total words: {len(greeting.split())}")
    print(f"   • Technologies mentioned (bold): {bold_count}")
    print(f"   • Character count: {len(greeting)}")
    
    print(f"\n✅ Enhanced detailed greeting generated successfully!")


if __name__ == "__main__":
    asyncio.run(demo_greeting())
