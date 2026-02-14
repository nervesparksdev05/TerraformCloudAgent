import asyncio
import json
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.services.conversation_manager import ConversationManager

def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}")
    with open("test_output.log", "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

async def run_v2_test():
    if os.path.exists("test_output.log"):
        os.remove("test_output.log")
    
    log("Starting Deep Conversational V2 Verification...")
    manager = ConversationManager()
    
    # 1. Create Session
    sid_data = manager.create_session("https://github.com/shekharshekharraj/Tunify-Full-Stack-Music-App")
    sid = sid_data["session_id"]
    log(f"Created Session: {sid}")
    
    # 2. Mock README analysis to bypass GitHub/LLM limits for repetitive tests
    session = manager.get_session(sid)
    session.readme_content = "This is a mocked Node.js app with Express."
    session.readme_analysis = {
        "tech_stack": {"language": "JavaScript", "framework": "Express"},
        "ports": [{"port": 3000}],
        "workload_type": "web",
        "confidence": 0.95,
        "reasoning": "Standard Node.js setup detected."
    }
    # Initial discovery prompt summary
    msg = "I see your Node.js app is using Express on port 3000. Let's talk about your deployment needs. How do you plan to handle data persistence?"
    session.messages.append({"role": "assistant", "content": msg, "timestamp": datetime.now().isoformat()})
    session.turn_count = 1
    manager._save_session(session)
    log(f"Mocked Analysis Response: {msg}")
    
    # 3. Simulate 12-turn conversation with rejections and pivots
    messages = [
        "I want to deploy this for 1000 users in us-east-1 for production.", # Global/Region + Env
        "My IP is 1.2.3.4/32", # Security
        "We'll use RDS PostgreSQL.", # Database
        "No, I don't want Redis or any caching.", # REJECTION (Pivot expected)
        "50GB storage is enough.", # Storage
        "We're using Node.js/Express.", # Compute
        "No autoscaling for now, just a single instance.", # REJECTION (Pivot expected)
        "Yes, we'll use GitHub Actions for CI/CD.", # CI/CD
        "Standard security rules are fine.", # Security (Already addressed, should pivot to Networking or Observability)
        "No monitoring tools for now.", # REJECTION (Pivot expected)
        "Use t3.medium instances.", # Compute (Refining)
        "Ready to generate the Terraform!" # Final
    ]

    for i, msg in enumerate(messages):
        log(f"\nTurn {i+1}: User: {msg}")
        chat_resp = await manager.send_message(sid, msg)
        log(f"Bot Response: {chat_resp['bot_response']}")
        session = manager.get_session(sid)
        log(f"Topics Addressed: {session.topics_addressed}")
        log(f"Collected Params: {json.dumps(session.collected_parameters, indent=2)}")
        log(f"Turn Count: {session.turn_count}")
        log(f"Is Complete: {chat_resp['is_complete']}")

    final_session = manager.get_session(sid)
    log(f"\nFinal Turn Count: {final_session.turn_count}")
    log(f"Final Is Complete: {final_session.is_complete}")
    
    if final_session.turn_count >= 12 and final_session.is_complete:
        log("SUCCESS: Deep conversation V2 finished successfully with 12+ turns.")
    else:
        log("FAILURE: Conversation ended too early or failed to track turns.")

if __name__ == "__main__":
    asyncio.run(run_v2_test())
