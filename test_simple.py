"""
Create a simple, working test run that will actually succeed
This uses simplified infrastructure to avoid validation errors
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def create_simple_working_run():
    """Create a simple S3 bucket that should work"""
    
    print("Creating a simple, working test run...")
    print("=" * 60)
    
    # Simple request that should generate clean code
    payload = {
        "request": "Create a single S3 bucket named 'my-test-logs-bucket' with private access",
        "provider": "aws"
    }
    
    print(f"\nRequest: {payload['request']}")
    print(f"Provider: {payload['provider']}")
    print("\nSending request to backend...")
    
    try:
        response = requests.post(
            f"{BASE_URL}/runs",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        
        if response.status_code in [200, 202]:
            run_data = response.json()
            print(f"\n✅ Run created successfully!")
            print(f"Run ID: {run_data['run_id']}")
            print(f"Status: {run_data['status']}")
            
            # Wait for planning to complete
            print("\nWaiting for Terraform code generation...")
            for i in range(30):
                time.sleep(2)
                status_response = requests.get(f"{BASE_URL}/runs/{run_data['run_id']}")
                if status_response.status_code == 200:
                    current_run = status_response.json()
                    print(f"Status: {current_run['status']}", end="\r")
                    
                    if current_run['status'] in ['planned', 'failed', 'completed']:
                        print(f"\n\nFinal Status: {current_run['status']}")
                        
                        if current_run.get('error'):
                            print(f"❌ Error: {current_run['error']}")
                        
                        if current_run.get('plan_output'):
                            print(f"\nPlan Output:")
                            print(current_run['plan_output'][:500])
                        
                        print(f"\n📁 Run directory: runs/{run_data['run_id']}")
                        print(f"🌐 View in browser: http://localhost:5174")
                        print(f"📊 API details: {BASE_URL}/runs/{run_data['run_id']}")
                        
                        return run_data['run_id'], current_run['status']
            
            print("\n⏱️ Timeout waiting for planning to complete")
            return run_data['run_id'], 'timeout'
            
        else:
            print(f"\n❌ Failed to create run: {response.status_code}")
            print(f"Response: {response.text}")
            return None, 'failed'
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        return None, 'error'

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SIMPLE WORKING TEST - Terraform Cloud Agent")
    print("=" * 60)
    
    # Check backend health
    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5)
        if health.status_code == 200:
            print("✅ Backend is running\n")
        else:
            print("❌ Backend is not healthy")
            exit(1)
    except:
        print("❌ Cannot connect to backend")
        print("Make sure it's running: python -m app.main")
        exit(1)
    
    run_id, status = create_simple_working_run()
    
    if run_id:
        print(f"\n{'=' * 60}")
        print(f"Test completed!")
        print(f"Run ID: {run_id}")
        print(f"Status: {status}")
        print(f"{'=' * 60}\n")
    else:
        print("\n❌ Test failed")
        exit(1)
