
import asyncio
import json
import secrets
from app.services.conversation_manager import ConversationManager

# Mock findings to simulate analyzed README
MOCK_README_ANALYSIS = {
    "extracted_params": {
        "workload_type": "web_server",
        "workload_description": "Full-stack music streaming app with Node.js/Express and MongoDB",
        "language": "Node.js",
        "database": "MongoDB",
        "dependencies": ["Express", "Mongoose"],
        "environment_hints": "production",
        "ports": [{"port": 3000, "protocol": "tcp", "description": "Node backend"}]
    },
    "message": (
        "Hello! 👋 How about your **Tunify** based on your README file?\n"
        "I see it is a **full-stack music platform** and has **Node.js/Express and MongoDB**.\n"
        "So it will be requiring **a scalable backend and a managed database** to be deployed.\n\n"
        "To start, which cloud platform would you prefer: **AWS**, **GCP**, **Azure**, or **DigitalOcean**?"
    ),
    "suggestions": ["AWS", "GCP", "Azure", "DigitalOcean"]
}

async def run_verification():
    cm = ConversationManager()
    
    # 1. Create Session with MOCK README analysis
    print(f"\n{'='*50}\nSTARTING LONG CONVERSATION TEST\n{'='*50}")
    
    # Manually inject mock analysis into a new session to bypass actual GitHub fetch
    sid = "verify_long_sess_" + secrets.token_hex(4)
    from app.models.conversation_schemas import ConversationSession, ConversationStatus
    
    session = ConversationSession(
        session_id=sid,
        provider="aws",
        messages=[],
        collected_parameters=MOCK_README_ANALYSIS["extracted_params"],
        is_complete=False,
        status=ConversationStatus.ACTIVE,
    )
    cm.sessions[sid] = session
    
    print(f"[{sid}] Session created.")
    print(f"BOT (Turn 1): {MOCK_README_ANALYSIS['message']}\n")

    # 2. Simulate User Responses following the 15-step flow
    user_inputs = [
        "AWS",                              # 1. Cloud Platform
        "Production",                       # 2. Environment
        "India",                            # 3. Region
        "5000",                             # 4. User Count
        "Ubuntu 22.04 LTS",                 # 5. Instance OS
        "t3.medium",                        # 6. Instance Type
        "Auto-scaling group",               # 7. Instance Count/Scaling
        "50 GB",                            # 8. Storage Size
        "gp3",                              # 9. Storage Type
        "Custom Isolated VPC",              # 10. VPC
        "Private with NAT Gateway",         # 11. Subnets
        "Just Load Balancer",               # 12. Public IP
        "103.2.1.0/24",                     # 13. SSH Access
        "Detailed Monitoring",              # 14. Monitoring
        "Yes, enable termination protection" # 15. Termination Protection
    ]

    with open("bot_long_debug.txt", "w", encoding="utf-8") as f:
        f.write("--- LONG CONVERSATION DEBUG LOG ---\n\n")
        f.write(f"BOT (Turn 1):\n{MOCK_README_ANALYSIS['message']}\n\n")

        for i, user_input in enumerate(user_inputs):
            print(f"USER (Turn {i+2}): {user_input}")
            f.write(f"USER (Turn {i+2}): {user_input}\n")
            
            response = await cm.process_message(sid, user_input)
            
            print(f"BOT (Turn {i+2}):\n{response.bot_response}\n")
            f.write(f"BOT (Turn {i+2}):\n{response.bot_response}\n\n")
            
            if response.is_complete:
                print(f"\n*** CONVERSATION COMPLETED AT TURN {i+2} ***")
                f.write(f"*** COMPLETED AT TURN {i+2} ***\n")
                break

    print(f"\n{'='*50}\nTEST COMPLETE. Check bot_long_debug.txt\n{'='*50}")

if __name__ == "__main__":
    asyncio.run(run_verification())
