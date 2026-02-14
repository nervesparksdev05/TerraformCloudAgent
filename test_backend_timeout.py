"""
Quick test to see if backend is responding
"""
import requests
import time

BASE_URL = "http://localhost:8000"

print("Testing if backend responds...")

# Create session
start = time.time()
response = requests.post(
    f"{BASE_URL}/conversations",
    json={"github_url": "https://github.com/tiangolo/fastapi"},
    timeout=10
)
print(f"✅ Session created in {time.time() - start:.2f}s")
session_id = response.json()["session_id"]

# Analyze README
print(f"\nAnalyzing README for {session_id}...")
start = time.time()
try:
    response = requests.get(
        f"{BASE_URL}/conversations/{session_id}/analyze",
        timeout=30  # 30 second timeout
    )
    elapsed = time.time() - start
    print(f"✅ README analyzed in {elapsed:.2f}s")
    print(f"Status: {response.status_code}")
except requests.Timeout:
    print(f"❌ TIMEOUT after 30 seconds!")
except Exception as e:
    print(f"❌ ERROR: {e}")
