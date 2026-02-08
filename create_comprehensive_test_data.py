"""
Enhanced test data creation script for Terraform Cloud Agent
Creates comprehensive mock data showcasing all 30 templates and new features
"""
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

BASE_URL = "http://localhost:8001"

# Diverse test scenarios using the new 30 templates
TEST_SCENARIOS = [
    # AWS Templates
    {"template_id": "aws_ec2_instance", "provider": "aws", "region": "us-east-1"},
    {"template_id": "aws_lambda_function", "provider": "aws", "region": "us-west-2"},
    {"template_id": "aws_s3_bucket", "provider": "aws", "region": "eu-west-1"},
    {"template_id": "aws_rds_database", "provider": "aws", "region": "ap-southeast-1"},
    {"template_id": "aws_dynamodb_table", "provider": "aws", "region": "us-east-2"},
    {"template_id": "aws_vpc_network", "provider": "aws", "region": "eu-central-1"},
    {"template_id": "aws_alb_loadbalancer", "provider": "aws", "region": "us-west-1"},
    {"template_id": "aws_eks_cluster", "provider": "aws", "region": "ap-northeast-1"},
    {"template_id": "aws_cloudfront_distribution", "provider": "aws", "region": "us-east-1"},
    {"template_id": "aws_api_gateway", "provider": "aws", "region": "eu-west-2"},
    
    # GCP Templates
    {"template_id": "gcp_compute_instance", "provider": "gcp", "region": "us-central1"},
    {"template_id": "gcp_cloud_function", "provider": "gcp", "region": "us-east1"},
    {"template_id": "gcp_storage_bucket", "provider": "gcp", "region": "europe-west1"},
    {"template_id": "gcp_cloud_sql", "provider": "gcp", "region": "asia-southeast1"},
    {"template_id": "gcp_firestore", "provider": "gcp", "region": "us-west1"},
    {"template_id": "gcp_vpc_network", "provider": "gcp", "region": "europe-west3"},
    {"template_id": "gcp_load_balancer", "provider": "gcp", "region": "us-central1"},
    {"template_id": "gcp_gke_cluster", "provider": "gcp", "region": "asia-northeast1"},
    {"template_id": "gcp_cloud_cdn", "provider": "gcp", "region": "us-east4"},
    {"template_id": "gcp_pub_sub", "provider": "gcp", "region": "europe-west2"},
]

# Natural language requests for variety
NATURAL_LANGUAGE_REQUESTS = [
    {"request": "Deploy a scalable web application with load balancer and auto-scaling", "provider": "aws", "region": "us-east-1"},
    {"request": "Create a managed PostgreSQL database with automated backups", "provider": "aws", "region": "eu-west-1"},
    {"request": "Set up a serverless API with Lambda functions and API Gateway", "provider": "aws", "region": "us-west-2"},
    {"request": "Build a Kubernetes cluster with 3 worker nodes", "provider": "gcp", "region": "us-central1"},
    {"request": "Create a CDN for global content delivery with caching", "provider": "aws", "region": "us-east-1"},
]

def check_backend():
    """Check if backend is running"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running\n")
            return True
        else:
            print(f"❌ Backend returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to backend at {BASE_URL}")
        print("   Make sure the backend server is running:")
        print("   uvicorn app.main:app --port 8001")
        return False
    except Exception as e:
        print(f"❌ Error checking backend: {str(e)}")
        return False

def create_template_run(template_id, provider, region):
    """Create a run using a template"""
    try:
        response = requests.post(
            f"{BASE_URL}/runs",
            json={
                "method": "template",
                "template_id": template_id,
                "provider": provider,
                "region": region,
                "auto_approve": False,
                "template_inputs": {"provider": provider, "region": region}
            },
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        if response.status_code in [200, 201, 202]:
            return response.json()
        else:
            print(f"   ⚠️  Failed to create {template_id}: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"   ⚠️  Error creating {template_id}: {str(e)}")
        return None

def create_natural_language_run(request, provider, region):
    """Create a run using natural language"""
    try:
        response = requests.post(
            f"{BASE_URL}/runs",
            json={
                "method": "natural_language",
                "request": request,
                "provider": provider,
                "region": region,
                "auto_approve": False
            },
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        if response.status_code in [200, 201, 202]:
            return response.json()
        else:
            print(f"   ⚠️  Failed: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"   ⚠️  Error: {str(e)}")
        return None

def approve_run(run_id):
    """Approve and apply a run"""
    try:
        response = requests.post(
            f"{BASE_URL}/runs/{run_id}/approve",
            timeout=60
        )
        return response.status_code in [200, 201, 202]
    except:
        return False

def destroy_run(run_id):
    """Destroy a run"""
    try:
        response = requests.post(
            f"{BASE_URL}/runs/{run_id}/destroy",
            timeout=60
        )
        return response.status_code in [200, 201, 202]
    except:
        return False

def create_comprehensive_test_data():
    """Create comprehensive test data showcasing all features"""
    
    print("🚀 Creating Comprehensive Test Data for Terraform Cloud Agent\n")
    print("=" * 70)
    
    created_runs = []
    
    # Phase 1: Create template-based runs
    print("\n📦 Phase 1: Creating Template-Based Runs")
    print("-" * 70)
    
    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        template_id = scenario["template_id"]
        provider = scenario["provider"]
        region = scenario["region"]
        
        print(f"[{i}/{len(TEST_SCENARIOS)}] Creating {template_id} in {region}...")
        
        run = create_template_run(template_id, provider, region)
        if run:
            created_runs.append(run)
            print(f"   ✅ Created: {run['run_id']} (status: {run['status']})")
        
        time.sleep(0.5)  # Small delay to avoid overwhelming the server
    
    # Phase 2: Create natural language runs
    print("\n💬 Phase 2: Creating Natural Language Runs")
    print("-" * 70)
    
    for i, scenario in enumerate(NATURAL_LANGUAGE_REQUESTS, 1):
        request = scenario["request"]
        provider = scenario["provider"]
        region = scenario["region"]
        
        print(f"[{i}/{len(NATURAL_LANGUAGE_REQUESTS)}] {request[:50]}...")
        
        run = create_natural_language_run(request, provider, region)
        if run:
            created_runs.append(run)
            print(f"   ✅ Created: {run['run_id']} (status: {run['status']})")
        
        time.sleep(0.5)
    
    # Phase 3: Approve some runs to create "completed" status
    print("\n✅ Phase 3: Approving Selected Runs (to create 'completed' status)")
    print("-" * 70)
    
    runs_to_approve = created_runs[:5]  # Approve first 5 runs
    for i, run in enumerate(runs_to_approve, 1):
        print(f"[{i}/{len(runs_to_approve)}] Approving {run['run_id']}...")
        if approve_run(run['run_id']):
            print(f"   ✅ Approved and applied")
        time.sleep(0.5)
    
    # Phase 4: Destroy some runs
    print("\n🗑️  Phase 4: Destroying Selected Runs (to create 'destroyed' status)")
    print("-" * 70)
    
    runs_to_destroy = created_runs[5:8]  # Destroy runs 6-8
    for i, run in enumerate(runs_to_destroy, 1):
        print(f"[{i}/{len(runs_to_destroy)}] Destroying {run['run_id']}...")
        if destroy_run(run['run_id']):
            print(f"   ✅ Destroyed")
        time.sleep(0.5)
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST DATA CREATION SUMMARY")
    print("=" * 70)
    print(f"\n✅ Successfully created {len(created_runs)} test runs!")
    print(f"   - Template-based runs: {len(TEST_SCENARIOS)}")
    print(f"   - Natural language runs: {len(NATURAL_LANGUAGE_REQUESTS)}")
    print(f"   - Approved runs: {len(runs_to_approve)}")
    print(f"   - Destroyed runs: {len(runs_to_destroy)}")
    
    print("\n🎯 Expected Status Distribution:")
    print("   - planned: ~12 runs (not yet approved)")
    print("   - completed: ~5 runs (approved and applied)")
    print("   - destroyed: ~3 runs (infrastructure removed)")
    
    print("\n🌍 Region Coverage:")
    aws_regions = set(s["region"] for s in TEST_SCENARIOS if s["provider"] == "aws")
    gcp_regions = set(s["region"] for s in TEST_SCENARIOS if s["provider"] == "gcp")
    print(f"   - AWS regions used: {len(aws_regions)} ({', '.join(sorted(aws_regions)[:5])}...)")
    print(f"   - GCP regions used: {len(gcp_regions)} ({', '.join(sorted(gcp_regions)[:5])}...)")
    
    print("\n📦 Template Coverage:")
    print(f"   - AWS templates tested: 10/15")
    print(f"   - GCP templates tested: 10/15")
    
    print("\n🌐 Next Steps:")
    print(f"   1. Open Frontend: http://localhost:5173")
    print(f"   2. View Dashboard: See all metrics and charts")
    print(f"   3. Browse Runs: Check different statuses and providers")
    print(f"   4. Test Create Run: Try the new 30 templates and region selection")
    print(f"   5. View Analytics: See cost trends and provider distribution")
    
    print("\n✨ All frontend features are now ready to test!")
    print("=" * 70 + "\n")
    
    return created_runs

if __name__ == "__main__":
    if not check_backend():
        exit(1)
    
    try:
        create_comprehensive_test_data()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test data creation interrupted by user")
        exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
