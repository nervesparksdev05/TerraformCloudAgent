"""
Detailed test to see exact response from analyze_readme
"""
import requests
import json

BASE_URL = "http://localhost:8000"

print("=" * 60)
print("DETAILED ANALYZE README TEST")
print("=" * 60)

# Create session
response = requests.post(
    f"{BASE_URL}/conversations",
    json={"github_url": "https://github.com/tiangolo/fastapi"}
)
session_id = response.json()["session_id"]
print(f"\n✅ Session: {session_id}")

# Analyze README
print("\n📊 Analyzing README...")
response = requests.get(f"{BASE_URL}/conversations/{session_id}/analyze")

print(f"\nStatus Code: {response.status_code}")
print(f"\nFull Response:")
print(json.dumps(response.json(), indent=2))

data = response.json()
print(f"\n" + "=" * 60)
print("KEY CHECKS:")
print("=" * 60)
print(f"✓ Has 'readme_analysis_summary': {'readme_analysis_summary' in data}")
print(f"✓ Has 'form_fields': {'form_fields' in data}")
print(f"✓ Has 'collected_parameters': {'collected_parameters' in data}")

if 'readme_analysis_summary' in data:
    summary = data['readme_analysis_summary']
    print(f"\n📋 README Analysis Summary:")
    print(json.dumps(summary, indent=2))
