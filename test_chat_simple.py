"""
Simple test to check if send_message endpoint works
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("Testing send_message endpoint...")
print("=" * 60)

# Step 1: Create session
print("\n1. Creating session...")
try:
    response = requests.post(
        f"{BASE_URL}/conversations",
        json={"github_url": "https://github.com/tiangolo/fastapi"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code != 201:
        print(f"ERROR: {response.text}")
        exit(1)
    
    session_id = response.json()["session_id"]
    print(f"✅ Session: {session_id}")
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)

# Step 2: Analyze README
print("\n2. Analyzing README...")
try:
    response = requests.get(f"{BASE_URL}/conversations/{session_id}/analyze")
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"ERROR: {response.text}")
        exit(1)
    print("✅ README analyzed")
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)

# Step 3: Send message
print("\n3. Sending message: 'us-east-1'...")
try:
    response = requests.post(
        f"{BASE_URL}/conversations/{session_id}/message",
        json={"message": "us-east-1"}
    )
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
        print(f"ERROR Response:")
        print(response.text)
        exit(1)
    
    data = response.json()
    print(f"✅ Bot response: {data['bot_response'][:100]}...")
    print(f"Collected: {data.get('collected_parameters', {})}")
    print(f"Complete: {data.get('is_complete', False)}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("✅ TEST PASSED!")
