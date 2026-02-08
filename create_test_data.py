"""
Script to create dummy test data for the Terraform Cloud Agent
This creates sample runs with different statuses for testing the UI
"""
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "http://localhost:8000"

def create_test_runs():
    """Create several test runs with different statuses"""
    
    test_scenarios = [
        {
            "request": "Create an EC2 instance with nginx web server",
            "provider": "aws",
            "description": "Simple web server deployment"
        },
        {
            "request": "Deploy a PostgreSQL RDS database with backup enabled",
            "provider": "aws",
            "description": "Database deployment"
        },
        {
            "request": "Create a GCP Cloud Storage bucket for static assets",
            "provider": "gcp",
            "description": "Storage bucket on GCP"
        },
        {
            "request": "Set up a Lambda function for image processing with S3 trigger",
            "provider": "aws",
            "description": "Serverless function"
        },
        {
            "request": "Create a VPC with public and private subnets",
            "provider": "aws",
            "description": "Network infrastructure"
        }
    ]
    
    print("🚀 Creating test data for Terraform Cloud Agent...\n")
    
    created_runs = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"[{i}/{len(test_scenarios)}] Creating: {scenario['description']}")
        
        try:
            response = requests.post(
                f"{BASE_URL}/runs",
                json={
                    "request": scenario["request"],
                    "provider": scenario["provider"]
                },
                headers={"Content-Type": "application/json"},
                timeout=120  # Increased timeout for LLM generation
            )
            
            if response.status_code in [200, 202]:
                run_data = response.json()
                created_runs.append(run_data)
                print(f"   ✅ Created run: {run_data['run_id']}")
                print(f"   Status: {run_data['status']}")
            else:
                print(f"   ❌ Failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
        
        print()
    
    print(f"\n✅ Successfully created {len(created_runs)} test runs!")
    print(f"\n📊 Summary:")
    for run in created_runs:
        print(f"   - {run['run_id']}: {run['status']} ({run['provider'].upper()})")
    
    print(f"\n🌐 View all runs at: {BASE_URL}/docs")
    print(f"🎨 Open frontend at: http://localhost:5174")
    
    return created_runs

if __name__ == "__main__":
    try:
        # Test if backend is running
        health_response = requests.get(f"{BASE_URL}/health", timeout=5)
        if health_response.status_code != 200:
            print("❌ Backend is not responding. Make sure it's running on port 8000")
            exit(1)
        
        print("✅ Backend is running\n")
        create_test_runs()
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend at http://localhost:8000")
        print("   Make sure the backend server is running:")
        print("   python -m app.main")
        exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        exit(1)
