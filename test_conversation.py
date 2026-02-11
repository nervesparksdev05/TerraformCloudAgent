"""
Test script to simulate a complete friendly conversation with the chatbot
"""
import requests
import json
import time
import sys
import io

# Fix Windows console encoding for emojis
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"

def print_response(stage, response):
    print(f"\n{'='*60}")
    print(f"STAGE {stage}")
    print(f"{'='*60}")
    if 'bot_response' in response:
        print(f"Bot: {response['bot_response']}")
        if response.get('suggestions'):
            print(f"\nSuggestions: {', '.join(response['suggestions'][:3])}")
        if response.get('collected_parameters'):
            print(f"\nCollected Parameters: {json.dumps(response['collected_parameters'], indent=2)}")
        print(f"Complete: {response.get('is_complete', False)}")
    else:
        print(f"Error: {response}")

# Create conversation
print("Creating conversation...")
resp = requests.post(f"{BASE_URL}/conversations")
data = resp.json()
session_id = data['session_id']
print_response(1, data)

# Conversation stages
stages = [
    ("I want to build a website", "Stage 1: Service type"),
    ("Production", "Stage 2: Environment"),
    ("AWS", "Stage 3: Cloud platform"),
    ("About 1000 users", "Stage 4: Scale"),
    ("US East Coast", "Stage 5: Location"),
    ("Ubuntu, 50GB storage, MySQL database", "Stage 6: Technical config"),
    ("Sounds good", "Stage 7: Instance confirmation"),
    ("Yes, that works", "Stage 8: Cost approval"),
    ("Yes, generate the files", "Stage 9: Final confirmation"),
]

for i, (user_msg, stage_name) in enumerate(stages, start=2):
    print(f"\n\nUser: {user_msg}")
    try:
        resp = requests.post(
            f"{BASE_URL}/conversations/{session_id}/message",
            json={"message": user_msg}
        )
        response_data = resp.json()
        print_response(i, response_data)
        
        if response_data.get('is_complete'):
            print("\n\n" + "="*60)
            print("CONVERSATION COMPLETE!")
            print("="*60)
            
            if response_data.get('run_id'):
                run_id = response_data['run_id']
                print(f"\nTerraform generation started: {run_id}")
                
                # Wait for Terraform generation
                print("\nWaiting for Terraform files...")
                for j in range(20):
                    time.sleep(3)
                    run_resp = requests.get(f"{BASE_URL}/runs/{run_id}")
                    run_data = run_resp.json()
                    print(f"  Status: {run_data['status']}")
                    
                    if run_data['status'] in ['planned', 'pending_approval']:
                        print("\n✅ Terraform files generated!")
                        
                        # Get the files
                        files_resp = requests.get(f"{BASE_URL}/runs/{run_id}/files")
                        files_data = files_resp.json()
                        
                        print("\n" + "="*60)
                        print("MAIN.TF (first 500 chars)")
                        print("="*60)
                        print(files_data['files']['main_tf'][:500])
                        break
                    elif run_data['status'] == 'failed':
                        print(f"\n❌ Failed: {run_data.get('error_message')}")
                        break
            break
        
        time.sleep(1)
    except Exception as e:
        print(f"Error: {e}")
        break

print("\n\nTest completed!")
