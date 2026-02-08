"""
Full End-to-End Test for Mock Mode
Verifies that the entire workflow succeeds without valid credentials
"""
import requests
import time
import json
import sys

BASE_URL = "http://localhost:8000"

def run_mock_test():
    print("=" * 60)
    print("MOCK MODE FULL WORKFLOW TEST")
    print("=" * 60)
    
    # 1. Health Check
    try:
        resp = requests.get(f"{BASE_URL}/health")
        if resp.status_code == 200:
            print("✅ Backend is healthy")
        else:
            print(f"❌ Backend unhealthy: {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ Could not connect to backend: {e}")
        return False

    # 2. Create Run
    print("\n[1/4] Creating Run...")
    payload = {
        "request": "Create a test S3 bucket",
        "provider": "aws"
    }
    resp = requests.post(f"{BASE_URL}/runs", json=payload)
    if resp.status_code not in [200, 202]:
        print(f"❌ Failed to create run: {resp.text}")
        return False
    
    run_data = resp.json()
    run_id = run_data["run_id"]
    print(f"✅ Run Created: {run_id}")
    
    # 3. Wait for Plan
    print("\n[2/4] Waiting for Plan...")
    for _ in range(30):
        time.sleep(1)
        resp = requests.get(f"{BASE_URL}/runs/{run_id}")
        data = resp.json()
        status = data["status"]
        print(f"Status: {status}", end="\r")
        
        if status == "planned":
            print(f"\n✅ Plan Complete! Output: {data.get('plan_output')}")
            break
        elif status == "failed":
            print(f"\n❌ Plan Failed: {data.get('error')}")
            return False
    else:
        print("\n❌ Timeout waiting for plan")
        return False
        
    # 4. Approve Run
    print("\n[3/4] Approving Run...")
    resp = requests.post(f"{BASE_URL}/runs/{run_id}/approve")
    if resp.status_code != 200:
        print(f"❌ Failed to approve: {resp.text}")
        return False
        
    # Wait for completion
    for _ in range(30):
        time.sleep(1)
        resp = requests.get(f"{BASE_URL}/runs/{run_id}")
        data = resp.json()
        status = data["status"]
        print(f"Status: {status}", end="\r")
        
        if status == "completed":
            print(f"\n✅ Apply Complete! Outputs: {json.dumps(data.get('outputs'), indent=2)}")
            break
        elif status == "failed":
            print(f"\n❌ Apply Failed: {data.get('error')}")
            return False
            
    # 5. Destroy Run
    print("\n[4/4] Destroying Run...")
    resp = requests.post(f"{BASE_URL}/runs/{run_id}/destroy")
    if resp.status_code != 200:
        print(f"❌ Failed to destroy: {resp.text}")
        return False
        
    # Wait for destroyed
    for _ in range(30):
        time.sleep(1)
        resp = requests.get(f"{BASE_URL}/runs/{run_id}")
        data = resp.json()
        status = data["status"]
        print(f"Status: {status}", end="\r")
        
        if status == "destroyed":
            print("\n✅ Destroy Complete!")
            break
        elif status == "failed":
            print(f"\n❌ Destroy Failed: {data.get('error')}")
            return False
            
    print("\n" + "="*60)
    print("🎉 MOCK TEST PASSED SUCCESSFULLY!")
    print("="*60)
    return True

if __name__ == "__main__":
    if run_mock_test():
        sys.exit(0)
    else:
        sys.exit(1)
