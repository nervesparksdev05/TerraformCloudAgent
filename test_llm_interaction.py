"""
LLM Interaction Demo
Demonstrates the LLM generating code from natural language and refining it based on chat.
"""
import requests
import time
import json
import sys
import os

BASE_URL = "http://localhost:8000"

def wait_for_status(run_id, target_status, timeout=60):
    print(f"Waiting for status '{target_status}'...", end="", flush=True)
    for _ in range(timeout):
        time.sleep(1)
        resp = requests.get(f"{BASE_URL}/runs/{run_id}")
        data = resp.json()
        status = data["status"]
        if status == target_status:
            print(f" Done! (Status: {status})")
            return data
        if status == "failed":
            print(f"\n❌ Run failed: {data.get('error')}")
            sys.exit(1)
        print(".", end="", flush=True)
    print("\n❌ Timeout waiting for status")
    sys.exit(1)

def get_file_content(run_id, filename="main.tf"):
    # In a real scenario we'd fetch from API, but for this test we can peak at the file system
    # knowing the run_id maps to a folder
    # However, let's use the API to remain faithful if possible. 
    # The current API doesn't expose file content directly in the run object, 
    # so we will use the local file system since we are on the same machine.
    
    # We need to find where the run is stored.
    # The API returns 'log_path'.
    resp = requests.get(f"{BASE_URL}/runs/{run_id}")
    data = resp.json()
    log_path = data.get("log_path")
    
    filepath = os.path.join(log_path, filename)
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return f.read()
    return f"❌ File {filename} not found at {filepath}"

def run_demo():
    print("=" * 60)
    print("🤖 LLM GENERATION & REFINEMENT DEMO")
    print("=" * 60)

    # 1. Initial Request
    request_text = "Create an AWS EC2 instance named 'web-server' with t3.micro type"
    print(f"\n📝 USER INPUT 1: \"{request_text}\"")
    
    payload = {
        "request": request_text,
        "provider": "aws"
    }
    resp = requests.post(f"{BASE_URL}/runs", json=payload)
    if resp.status_code not in [200, 202]:
        print(f"❌ Failed to create run: {resp.text}")
        return
    
    run_id = resp.json()["run_id"]
    print(f"✅ Run Created: {run_id}")
    
    # Wait for LLM to generate code
    wait_for_status(run_id, "planned")
    
    print("\n📄 LLM GENERATED CODE (main.tf):")
    print("-" * 40)
    print(get_file_content(run_id))
    print("-" * 40)
    
    # 2. Refinement (Chat)
    refine_text = "Change the instance type to t3.large and add a 'Production' tag"
    print(f"\n💬 USER INPUT 2 (Refinement): \"{refine_text}\"")
    
    payload = {"message": refine_text}
    resp = requests.post(f"{BASE_URL}/runs/{run_id}/edit", json=payload)
    if resp.status_code != 200:
        print(f"❌ Failed to send edit: {resp.text}")
        return

    # Wait for LLM to refine code
    wait_for_status(run_id, "planned")
    
    print("\n📄 UPDATED LLM CODE (main.tf):")
    print("-" * 40)
    print(get_file_content(run_id))
    print("-" * 40)
    
    print("\n✅ Demo Complete! The LLM successfully updated the code based on your feedback.")

if __name__ == "__main__":
    run_demo()
