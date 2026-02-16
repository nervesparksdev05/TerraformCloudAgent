
import asyncio
import json
import logging
import sys
import os

# Adjust path so we can import app modules
sys.path.append(os.path.join(os.getcwd(), "TerraformCloudAgent"))

from app.services.conversation_manager import ConversationManager, ConversationStatus

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def test_debug_conversation():
    print("--- STARTING DEBUG VERIFICATION ---")
    
    # 1. Initialize ConversationManager
    cm = ConversationManager()
    
    # 2. Mock GitHub Service to avoid API calls and ensure consistent README
    # 2. Mock GitHub Service to avoid API calls and ensure consistent README
    async def mock_fetch_readme(owner=None, repo=None, repo_url=None, token=None, branch=None):
        return """
        # Tunify
        A full-stack music platform using Node.js, Express, and MongoDB.
        """
    cm.github_service.fetch_readme = mock_fetch_readme

    async def mock_analyze_readme(content):
        return {
            "message": "Hello! Tunify needs Node.js and MongoDB on AWS/GCP/Azure/DO.",
            "extracted_params": {"workload_description": "Music app", "ports": [3000]}
        }
    cm._analyze_readme = mock_analyze_readme
    
    # 3. Create Session
    session_data = await cm.create_session(owner="test", repo="tunify")
    session_id = session_data["session_id"]
    print(f"Session Created: {session_id}")
    print(f"Bot (Turn 1): {session_data['bot_response']}")

    # 4. Define User Inputs to trigger the bugs
    user_inputs = [
        "aws",                      # 1. Cloud Platform
        "production",               # 2. Environment
        "Asia Pacific (Mumbai)",    # 3. Region -> EXPECT: User Count
        "5000",                     # 4. User Count -> EXPECT: OS
        "Amazon Linux",             # 5. OS
        "standard one",             # 6. Instance Type (TESTING EXTRACTION) -> EXPECT: Count
        "Single instance",          # 7. Instance Count -> EXPECT: Storage Size
        "20GB",                     # 8. Storage Size -> EXPECT: Storage Type (NOT INSTANCE TYPE LOOP)
        "gp3",                      # 9. Storage Type
        "Custom Isolated VPC",      # 10. VPC
        "Private with NAT",         # 11. Subnets
        "Just Load Balancer",       # 12. Public IP
        "My IP",                    # 13. SSH
        "Detailed",                 # 14. Monitoring
        "Yes"                       # 15. Termination
    ]

    # 5. Loop through inputs
    for i, user_input in enumerate(user_inputs):
        print(f"\nUSER (Turn {i+2}): {user_input}")
        
        response = await cm.process_message(session_id, user_input)
        
        bot_msg = response.bot_response
        print(f"BOT (Turn {i+2}): {bot_msg}")
        
        # CHECK 1: Length
        lines = len(bot_msg.split('\n'))
        # Using a loose check because "4-5 lines" might include blank lines or be formatted differently
        if lines < 3:
            print(f"WARNING: Response too short ({lines} lines). Expected 4-5.")

        # CHECK 2: User Count (After Turn 3 "Region")
        if i == 2: # Input "Asia Pacific (Mumbai)"
            if "users" not in bot_msg.lower() and "traffic" not in bot_msg.lower():
                print("CRITICAL FAILURE: Expected 'User Count' question after Region.")
            else:
                print("SUCCESS: Asked about User Count.")

        # CHECK 3: Instance Type Loop (After Turn 7 "20GB")
        if i == 7: # Input "20GB"
            if "t3.medium" in bot_msg or "c5.large" in bot_msg:
                print("CRITICAL FAILURE: Bot looped back to Instance Type!")
            elif "gp3" in bot_msg or "io2" in bot_msg or "storage type" in bot_msg.lower():
                print("SUCCESS: Proceeded to Storage Type.")
            else:
                 print(f"WARNING: Unexpected next step: {bot_msg[:50]}...")

        # CHECK 4: Extraction of "standard one"
        if i == 5: # Input "standard one"
             if "single instance" in bot_msg.lower() or "auto-scaling" in bot_msg.lower() or "instance count" in bot_msg.lower():
                 print("SUCCESS: 'standard one' accepted, moved to Instance Count.")
             else:
                 print(f"FAILURE: Bot did not move to Instance Count. Message: {bot_msg[:50]}...")

        if response.is_complete:
            print(f"\n*** CONVERSATION COMPLETED AT TURN {i+2} ***")
            if "Total Estimate" in bot_msg:
                print("SUCCESS: Compact costing found in final message.")
            else:
                print("FAILURE: Costing missing or format incorrect.")
            break

if __name__ == "__main__":
    asyncio.run(test_debug_conversation())
