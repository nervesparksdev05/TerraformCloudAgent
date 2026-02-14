"""
Test analyze_readme endpoint directly
"""
import requests

BASE_URL = "http://localhost:8000"

print("Testing analyze_readme...")
print("=" * 60)

# Step 1: Create session
print("\n1. Creating session...")
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

# Step 2: Analyze README
print("\n2. Analyzing README...")
response = requests.get(f"{BASE_URL}/conversations/{session_id}/analyze")
print(f"Status: {response.status_code}")

if response.status_code != 200:
    print(f"ERROR: {response.text}")
    exit(1)

data = response.json()
print(f"✅ README analyzed")
print(f"\nResponse keys: {list(data.keys())}")
print(f"Bot response: {data.get('bot_response', '')[:100]}...")
print(f"Has readme_analysis_summary: {'readme_analysis_summary' in data}")
print(f"Has form_fields: {'form_fields' in data}")
print(f"Has collected_parameters: {'collected_parameters' in data}")

if data.get('readme_analysis_summary'):
    summary = data['readme_analysis_summary']
    print(f"\nREADME Analysis Summary:")
    print(f"  - Tech stack: {summary.get('tech_stack', {})}")
    print(f"  - Workload: {summary.get('workload_type', 'unknown')}")

print("\n" + "=" * 60)
print("✅ TEST PASSED!")
