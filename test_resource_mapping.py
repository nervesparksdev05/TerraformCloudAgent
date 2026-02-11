"""
Quick test script to verify Terraform generation with cloud resource mapping
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

print("Testing Terraform Generation with Cloud Resource Mapping\n")
print("="*60)

# Test 1: Create conversation
print("\n1. Creating conversation...")
resp = requests.post(f"{BASE_URL}/conversations")
data = resp.json()
session_id = data['session_id']
print(f"✓ Session created: {session_id}")

# Test 2: Request a website (should map to EC2/Compute)
messages = [
    "I want to build a website",
    "Production",
    "AWS",
    "About 1000 users",
    "US East Coast",
    "Ubuntu with 50GB storage and MySQL",
    "Sounds good",
    "Yes",
    "Yes, generate the files"
]

for i, msg in enumerate(messages, 1):
    print(f"\n{i+1}. User: {msg}")
    resp = requests.post(
        f"{BASE_URL}/conversations/{session_id}/message",
        json={"message": msg}
    )
    data = resp.json()
    
    if data.get('is_complete'):
        print(f"✓ Conversation complete!")
        print(f"✓ Run ID: {data.get('run_id')}")
        
        # Wait for generation
        run_id = data['run_id']
        print(f"\n3. Waiting for Terraform generation (fast mode with gpt-4o-mini)...")
        
        for j in range(20):
            time.sleep(2)
            run_resp = requests.get(f"{BASE_URL}/runs/{run_id}")
            run_data = run_resp.json()
            print(f"   Status: {run_data['status']}")
            
            if run_data['status'] in ['planned', 'pending_approval']:
                print(f"\n✓ Terraform generated successfully!")
                
                # Get files
                files_resp = requests.get(f"{BASE_URL}/runs/{run_id}/files")
                files_data = files_resp.json()
                
                print("\n" + "="*60)
                print("MAIN.TF")
                print("="*60)
                print(files_data['files']['main_tf'][:800])
                
                # Check for resource mapping
                main_tf = files_data['files']['main_tf']
                if 'aws_instance' in main_tf:
                    print("\n✓ CORRECT: Detected EC2 resource (aws_instance) for website!")
                else:
                    print("\n✗ ERROR: EC2 resource not found!")
                
                break
            elif run_data['status'] == 'failed':
                print(f"\n✗ FAILED: {run_data.get('error_message')}")
                break
        break
    else:
        print(f"   Bot: {data.get('bot_response', '')[:100]}...")
    
    time.sleep(0.5)

print("\n\nTest completed!")
