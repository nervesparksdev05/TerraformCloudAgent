"""
COMPREHENSIVE SYSTEM DEMO
Visualizes the entire lifecycle from User Input to Infrastructure Destruction.
"""
import requests
import time
import json
import sys
import os

BASE_URL = "http://localhost:8000"

def print_section(title):
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)

def print_step(step, msg):
    print(f"\n🔹 STEP {step}: {msg}")

def get_run_details(run_id):
    resp = requests.get(f"{BASE_URL}/runs/{run_id}")
    return resp.json()

def wait_for_status(run_id, target_status, timeout=60):
    print(f"   Waiting for status '{target_status}'...", end="", flush=True)
    for _ in range(timeout):
        time.sleep(1)
        data = get_run_details(run_id)
        status = data["status"]
        if status == target_status:
            print(f" Done! (Current Status: {status})")
            return data
        if status == "failed":
            print(f"\n❌ Run failed: {data.get('error')}")
            sys.exit(1)
        print(".", end="", flush=True)
    print("\n❌ Timeout waiting for status")
    sys.exit(1)

def get_terraform_code(run_id):
    # In a real app we'd query API, here we peek at files for demo purposes
    data = get_run_details(run_id)
    log_path = data.get("log_path")
    
    files = {}
    for filename in ["main.tf", "variables.tf", "outputs.tf"]:
        filepath = os.path.join(log_path, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                files[filename] = f.read()
        else:
            files[filename] = f"(( No {filename} found ))"
            
    return files

def run_full_demo():
    print_section("🚀 TERRAFORM CLOUD AGENT - FULL PROCESS DEMO")

    # 1. User Input
    print_step(1, "USER INPUT (New Run)")
    user_request = "Create a Google Cloud Storage bucket named 'demo-bucket-123' in us-central1"
    print(f"   👤 User: \"{user_request}\"")
    
    payload = {
        "request": user_request,
        "provider": "gcp"
    }
    resp = requests.post(f"{BASE_URL}/runs", json=payload)
    if resp.status_code not in [200, 202]:
        print(f"❌ Failed to create run: {resp.text}")
        return
    
    run_data = resp.json()
    run_id = run_data["run_id"]
    print(f"   ✅ Backend: Run Created (ID: {run_id})")

    # 2. Planning (LLM Generation)
    print_step(2, "LLM GENERATION (Planning)")
    print("   🤖 AI Agent: Generating Terraform code...")
    wait_for_status(run_id, "planned")
    
    print("\n   📄 GENERATED TERRAFORM CODE:")
    files = get_terraform_code(run_id)
    for filename, content in files.items():
        print(f"   --- {filename} ---")
        for line in content.splitlines():
            print(f"   | {line}")
        print("   " + "-"*40)

    # 3. User Refinement
    print_step(3, "USER REFINEMENT (Chat)")
    refine_msg = "Actually, make it a regional bucket and add a label 'env=dev'"
    print(f"   👤 User: \"{refine_msg}\"")
    
    requests.post(f"{BASE_URL}/runs/{run_id}/edit", json={"message": refine_msg})
    print("   🤖 AI Agent: Updating configuration...")
    
    wait_for_status(run_id, "planned")
    
    print("\n   📄 UPDATED TERRAFORM CODE:")
    files = get_terraform_code(run_id)
    for filename, content in files.items():
        print(f"   --- {filename} ---")
        for line in content.splitlines():
            print(f"   | {line}")
        print("   " + "-"*40)

    # 4. Plan Output
    print_step(4, "TERRAFORM PLAN")
    data = get_run_details(run_id)
    print("   📋 Plan Output:")
    print(f"   {data.get('plan_output')}")
    print(f"   💰 Cost Estimate: {data.get('cost_estimate')}")

    # 5. Approval & Apply
    print_step(5, "APPROVAL & APPLY")
    print("   👤 User: IMPLICIT APPROVAL (Clicking 'Approve')")
    requests.post(f"{BASE_URL}/runs/{run_id}/approve")
    
    print("   ⚙️  Backend: Applying infrastructure...")
    data = wait_for_status(run_id, "completed")
    
    print("\n   ✅ INFRASTRUCTURE DEPLOYED!")
    print("   📤 Outputs:")
    print(json.dumps(data.get("outputs"), indent=4))

    # 6. Destroy
    print_step(6, "CLEANUP (Destroy)")
    print("   👤 User: Requesting Destroy")
    requests.post(f"{BASE_URL}/runs/{run_id}/destroy")
    
    print("   ⚙️  Backend: Destroying resources...")
    wait_for_status(run_id, "destroyed")
    
    print("\n   🗑️  Resource Destruction Confirmed.")
    print_section("✨ DEMO COMPLETED SUCCESSFULLY ✨")

if __name__ == "__main__":
    run_full_demo()
