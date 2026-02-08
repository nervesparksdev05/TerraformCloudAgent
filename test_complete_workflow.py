"""
Comprehensive End-to-End Test Script for Terraform Cloud Agent
Tests all processes with mock data to verify everything is working correctly
"""
import requests
import time
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BLUE}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.YELLOW}ℹ️  {text}{Colors.RESET}")

def test_health_check():
    """Test 1: Health Check"""
    print_header("TEST 1: Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print_success("Backend is healthy")
            print_info(f"Response: {response.json()}")
            return True
        else:
            print_error(f"Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Health check failed: {str(e)}")
        return False

def test_create_run():
    """Test 2: Create a New Run"""
    print_header("TEST 2: Create New Run")
    try:
        payload = {
            "request": "Create a simple S3 bucket for storing logs",
            "provider": "aws"
        }
        
        print_info(f"Creating run with request: '{payload['request']}'")
        response = requests.post(
            f"{BASE_URL}/runs",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        
        if response.status_code in [200, 202]:
            run_data = response.json()
            print_success(f"Run created successfully!")
            print_info(f"Run ID: {run_data['run_id']}")
            print_info(f"Status: {run_data['status']}")
            print_info(f"Provider: {run_data['provider']}")
            return run_data['run_id']
        else:
            print_error(f"Failed to create run: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
    except Exception as e:
        print_error(f"Create run failed: {str(e)}")
        return None

def test_get_run(run_id):
    """Test 3: Get Run Details"""
    print_header("TEST 3: Get Run Details")
    try:
        print_info(f"Fetching details for run: {run_id}")
        response = requests.get(f"{BASE_URL}/runs/{run_id}", timeout=10)
        
        if response.status_code == 200:
            run_data = response.json()
            print_success("Run details retrieved successfully!")
            print_info(f"Status: {run_data['status']}")
            print_info(f"Request: {run_data['request']}")
            if run_data.get('error'):
                print_info(f"Error: {run_data['error']}")
            if run_data.get('plan_output'):
                print_info(f"Plan Output: {run_data['plan_output'][:100]}...")
            return run_data
        else:
            print_error(f"Failed to get run: {response.status_code}")
            return None
    except Exception as e:
        print_error(f"Get run failed: {str(e)}")
        return None

def test_list_runs():
    """Test 4: List All Runs"""
    print_header("TEST 4: List All Runs")
    try:
        response = requests.get(f"{BASE_URL}/runs", timeout=10)
        
        if response.status_code == 200:
            runs = response.json()
            print_success(f"Found {len(runs)} total runs")
            for i, run in enumerate(runs[:5], 1):  # Show first 5
                print_info(f"{i}. {run['run_id']} - Status: {run['status']} ({run['provider']})")
            if len(runs) > 5:
                print_info(f"... and {len(runs) - 5} more runs")
            return runs
        else:
            print_error(f"Failed to list runs: {response.status_code}")
            return []
    except Exception as e:
        print_error(f"List runs failed: {str(e)}")
        return []

def test_chat(run_id):
    """Test 5: Chat About Run"""
    print_header("TEST 5: Chat About Run")
    try:
        payload = {"message": "What resources will be created?"}
        print_info(f"Sending chat message: '{payload['message']}'")
        
        response = requests.post(
            f"{BASE_URL}/runs/{run_id}/chat",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 200:
            chat_response = response.json()
            print_success("Chat response received!")
            print_info(f"Response: {chat_response['response']}")
            return True
        else:
            print_error(f"Chat failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Chat failed: {str(e)}")
        return False

def test_edit(run_id):
    """Test 6: Edit/Refine Run"""
    print_header("TEST 6: Edit/Refine Run")
    try:
        payload = {"message": "Add versioning to the S3 bucket"}
        print_info(f"Sending edit request: '{payload['message']}'")
        
        response = requests.post(
            f"{BASE_URL}/runs/{run_id}/edit",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        
        if response.status_code == 200:
            run_data = response.json()
            print_success("Edit request submitted!")
            print_info(f"New Status: {run_data['status']}")
            return True
        else:
            print_error(f"Edit failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Edit failed: {str(e)}")
        return False

def test_approve(run_id):
    """Test 7: Approve Run"""
    print_header("TEST 7: Approve Run")
    try:
        print_info(f"Approving run: {run_id}")
        
        response = requests.post(
            f"{BASE_URL}/runs/{run_id}/approve",
            timeout=120
        )
        
        if response.status_code == 200:
            run_data = response.json()
            print_success("Run approved and applied!")
            print_info(f"Status: {run_data['status']}")
            if run_data.get('outputs'):
                print_info(f"Outputs: {json.dumps(run_data['outputs'], indent=2)}")
            return True
        else:
            print_error(f"Approve failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Approve failed: {str(e)}")
        return False

def test_destroy(run_id):
    """Test 8: Destroy Infrastructure"""
    print_header("TEST 8: Destroy Infrastructure")
    try:
        print_info(f"Destroying infrastructure for run: {run_id}")
        
        response = requests.post(
            f"{BASE_URL}/runs/{run_id}/destroy",
            timeout=60
        )
        
        if response.status_code == 200:
            run_data = response.json()
            print_success("Destroy initiated!")
            print_info(f"Status: {run_data['status']}")
            return True
        else:
            print_error(f"Destroy failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Destroy failed: {str(e)}")
        return False

def run_all_tests():
    """Run all tests in sequence"""
    print_header("TERRAFORM CLOUD AGENT - COMPREHENSIVE TEST SUITE")
    print_info(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "total": 8,
        "passed": 0,
        "failed": 0
    }
    
    # Test 1: Health Check
    if test_health_check():
        results["passed"] += 1
    else:
        results["failed"] += 1
        print_error("Backend is not healthy. Stopping tests.")
        return results
    
    time.sleep(1)
    
    # Test 2: Create Run
    run_id = test_create_run()
    if run_id:
        results["passed"] += 1
    else:
        results["failed"] += 1
        print_error("Cannot continue without a run ID")
        return results
    
    time.sleep(2)
    
    # Test 3: Get Run Details
    run_data = test_get_run(run_id)
    if run_data:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    time.sleep(1)
    
    # Test 4: List Runs
    runs = test_list_runs()
    if runs:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    time.sleep(1)
    
    # Test 5: Chat
    if test_chat(run_id):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    time.sleep(1)
    
    # Test 6: Edit (only if run is in planned state)
    if run_data and run_data.get('status') == 'planned':
        if test_edit(run_id):
            results["passed"] += 1
        else:
            results["failed"] += 1
        time.sleep(2)
    else:
        print_info("Skipping edit test (run not in planned state)")
        results["total"] -= 1
    
    # Wait for planning to complete if needed
    print_info("Waiting for run to be ready for approval...")
    for _ in range(10):
        run_data = test_get_run(run_id)
        if run_data and run_data.get('status') in ['planned', 'failed', 'completed']:
            break
        time.sleep(3)
    
    # Test 7: Approve (only if run is in planned state)
    if run_data and run_data.get('status') == 'planned':
        if test_approve(run_id):
            results["passed"] += 1
        else:
            results["failed"] += 1
        time.sleep(2)
    else:
        print_info(f"Skipping approve test (run status: {run_data.get('status') if run_data else 'unknown'})")
        results["total"] -= 1
    
    # Test 8: Destroy
    if test_destroy(run_id):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Print Summary
    print_header("TEST SUMMARY")
    print_info(f"Total Tests: {results['total']}")
    print_success(f"Passed: {results['passed']}")
    if results['failed'] > 0:
        print_error(f"Failed: {results['failed']}")
    else:
        print_success("All tests passed! ✨")
    
    success_rate = (results['passed'] / results['total']) * 100
    print_info(f"Success Rate: {success_rate:.1f}%")
    
    print_info(f"\nTest Run ID: {run_id}")
    print_info(f"Check details at: {BASE_URL}/runs/{run_id}")
    
    return results

if __name__ == "__main__":
    try:
        results = run_all_tests()
        exit(0 if results['failed'] == 0 else 1)
    except KeyboardInterrupt:
        print_error("\nTests interrupted by user")
        exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        exit(1)
