import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from app.services.conversation_manager import ConversationManager
from app.models.conversation_schemas import ConversationStatus

async def test_conversational_flow():
    log_file = open("test_output.log", "w", encoding="utf-8")
    def log(msg):
        print(msg)
        log_file.write(msg + "\n")
        log_file.flush()

    log("Testing Conversational Flow Refactor...")
    
    # 1. Initialize Manager
    manager = ConversationManager()
    
    # Mock dependencies
    manager.github_service.fetch_readme = AsyncMock(return_value={
        "content": "# My Node App\nThis is a production node.js application that runs on port 3000."
    })
    manager.readme_analyzer.analyze = AsyncMock(return_value={
        "tech_stack": {"language": "Node.js", "framework": "Express"},
        "ports": [{"port": 3000}],
        "workload_type": "web_app",
        "confidence": 0.9,
        "reasoning": "Standard Node.js app detected from port 3000."
    })

    # 2. Create Session
    session_data = manager.create_session("https://github.com/user/node-app", provider="aws")
    sid = session_data["session_id"]
    log(f"Created Session: {sid}")
    
    # 3. Analyze README
    log("\nAnalyzing README...")
    analysis_resp = await manager.analyze_readme(sid)
    log(f"Bot Response (Analysis): {analysis_resp.bot_response}")
    
    # 4. Long Conversation Simulation with Rejections
    messages = [
        "I want to deploy this to production for about 1000 users in us-east-1.",
        "My IP is 1.2.3.4/32",
        "We use PostgreSQL for data.",
        "Yes, we need high availability for the database.",
        "No, I don't want Redis or any caching.", # Rejection
        "We're using Express/Node.js.",
        "About 50GB of storage for now.",
        "Standard security group rules are fine.",
        "Let's use t3.medium instances.",
        "No, I'll manage secrets manually for now.", # Rejection
        "Ready to generate the Terraform now!"
    ]

    for i, msg in enumerate(messages):
        log(f"\nTurn {i+1}: User: {msg}")
        chat_resp = await manager.send_message(sid, msg)
        log(f"Bot Response: {chat_resp['bot_response']}")
        session = manager.get_session(sid)
        log(f"Topics Addressed: {session.topics_addressed}")
        log(f"Turn Count: {session.turn_count}")
        log(f"Is Complete: {chat_resp['is_complete']}")

    final_session = manager.get_session(sid)
    log(f"\nFinal Turn Count: {final_session.turn_count}")
    log(f"Final Is Complete: {final_session.is_complete}")
    
    if final_session.is_complete:
        log("✅ SUCCESS: Deep conversation finished successfully with 10+ turns.")
    else:
        log("❌ FAILURE: Conversation ended too early or didn't complete.")
    
    log_file.close()

if __name__ == "__main__":
    asyncio.run(test_conversational_flow())
