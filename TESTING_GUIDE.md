# 🚀 Complete Testing Guide - Production-Ready Features

## Quick Start (3 Steps)

### Step 1: Start Backend Server
```powershell
# In Terminal 1
cd c:\Users\nerve\Desktop\NerveSparks\TerraformCloudAgent
uvicorn app.main:app --port 8001
```

Wait for: `✅ INFO: Application startup complete`

### Step 2: Start Frontend Server
```powershell
# In Terminal 2 (new terminal)
cd c:\Users\nerve\Desktop\NerveSparks\TerraformCloudAgent\frontend
npm run dev
```

Wait for: `➜ Local: http://localhost:5173/`

### Step 3: Generate Mock Data
```powershell
# In Terminal 3 (new terminal)
cd c:\Users\nerve\Desktop\NerveSparks\TerraformCloudAgent
python create_comprehensive_test_data.py
```

This will create **25 test runs** showcasing:
- ✅ 20 template-based runs (10 AWS + 10 GCP)
- ✅ 5 natural language runs
- ✅ Multiple statuses: planned, completed, destroyed
- ✅ Various regions across AWS and GCP
- ✅ All major service categories

---

## What to Test

### 1. Dashboard (`http://localhost:5173/`)
**Features to verify:**
- ✅ **KPI Cards**: Total runs, active runs, resources, monthly cost
- ✅ **Status Overview Chart**: Shows planned, completed, destroyed counts
- ✅ **Run Activity Chart**: Line chart showing runs over last 30 days
- ✅ **Provider Distribution**: Pie chart showing AWS vs GCP split
- ✅ **Recent Runs Table**: Latest 7 runs with status badges

**Expected Results:**
- Total runs: ~25
- Status distribution: ~12 planned, ~5 completed, ~3 destroyed
- Provider split: ~60% AWS, ~40% GCP

---

### 2. Create Run Page (`http://localhost:5173/create`)

#### Test Template Selection
1. Click "Use Template"
2. Click "Next"
3. **Verify**: See 30 templates displayed in 3-column grid
4. Select AWS provider → **Verify**: 15 AWS templates shown
5. Select GCP provider → **Verify**: 15 GCP templates shown
6. Click any template → **Verify**: "Selected" badge appears
7. **Check**: Service chips displayed (e.g., "EC2", "VPC", "SG")

#### Test Region Selection
1. Continue to "Configure" step
2. Select AWS → **Verify**: Dropdown shows "28 regions available for AWS"
3. Open region dropdown → **Verify**: All regions listed with format "us-east-1 - US East (N. Virginia)"
4. Switch to GCP → **Verify**: "40 regions available for GCP"
5. Open region dropdown → **Verify**: All GCP regions listed

#### Test Natural Language Input
1. Go back to Method step
2. Select "Natural Language"
3. Click "Next"
4. **Verify**: Example prompts box appears with 4 examples
5. Type a request → **Verify**: Character counter updates
6. **Verify**: "X more needed" counter shows remaining characters

---

### 3. Runs List Page (`http://localhost:5173/runs`)
**Features to verify:**
- ✅ All 25 runs displayed
- ✅ Status badges with correct colors
- ✅ Provider badges (AWS/GCP)
- ✅ Region information
- ✅ Created timestamps
- ✅ Click on run → navigates to run details

---

### 4. Run Details Page
1. Click any run from the list
2. **Verify**:
   - Run ID and status displayed
   - Provider and region shown
   - Terraform code tabs (main.tf, variables.tf, outputs.tf)
   - Action buttons (Approve, Chat, Edit, Destroy)

---

### 5. Analytics Page (`http://localhost:5173/analytics`)
**Features to verify:**
- ✅ KPI cards: Total runs, success rate, avg duration, failed count
- ✅ Runs over time chart
- ✅ Cost trend chart (6 months)
- ✅ Status distribution chart
- ✅ Provider comparison chart
- ✅ Time range selector (7d, 30d, 90d)

---

### 6. Resources Page (`http://localhost:5173/resources`)
**Features to verify:**
- ✅ Resource inventory table
- ✅ Filter by provider (All, AWS, GCP)
- ✅ Filter by resource type
- ✅ Search functionality
- ✅ Sort options (updated, cost, name)
- ✅ Monthly cost calculation

---

### 7. API Endpoints (Optional)

Test the new endpoints directly:

```powershell
# Get all templates
Invoke-RestMethod http://localhost:8001/templates

# Get AWS templates only
Invoke-RestMethod http://localhost:8001/templates?provider=aws

# Get GCP templates only
Invoke-RestMethod http://localhost:8001/templates?provider=gcp

# Get AWS regions
Invoke-RestMethod http://localhost:8001/regions?provider=aws

# Get GCP regions
Invoke-RestMethod http://localhost:8001/regions?provider=gcp

# Get dashboard data
Invoke-RestMethod http://localhost:8001/dashboard/overview?days=30
```

---

## Production Features Checklist

### ✅ Backend (30 Templates)
- [x] 15 AWS templates (EC2, Lambda, S3, RDS, DynamoDB, VPC, ALB, EKS, CloudFront, API Gateway, IAM, CloudWatch, SNS/SQS, Route53, ECS)
- [x] 15 GCP templates (Compute Engine, Cloud Functions, Cloud Storage, Cloud SQL, Firestore, VPC, Load Balancer, GKE, Cloud CDN, API Gateway, IAM, Cloud Monitoring, Pub/Sub, Cloud DNS, Cloud Run)
- [x] 28 AWS regions
- [x] 40 GCP regions
- [x] GET /regions endpoint
- [x] Enhanced GET /templates endpoint

### ✅ Frontend
- [x] Dynamic region selection (all regions)
- [x] Enhanced template browser (3-column grid)
- [x] Service-aware AI input (example prompts)
- [x] Template count display
- [x] Region count display
- [x] Visual selection indicators
- [x] Chip overflow handling

### ✅ Dashboard
- [x] Status overview includes all statuses
- [x] Completed runs shown as "deployed"
- [x] Provider distribution chart
- [x] Run activity trends
- [x] Recent runs table

---

## Troubleshooting

### Backend won't start
```powershell
# Check if port 8001 is in use
netstat -ano | findstr :8001

# Kill process if needed
taskkill /PID <PID> /F
```

### Frontend won't start
```powershell
# Reinstall dependencies
npm install

# Clear cache
npm run dev -- --force
```

### No test data appearing
1. Check backend is running: `http://localhost:8001/health`
2. Check runs directory exists: `c:\Users\nerve\Desktop\NerveSparks\TerraformCloudAgent\runs`
3. Re-run test data script: `python create_comprehensive_test_data.py`

---

## Expected Test Data Summary

After running `create_comprehensive_test_data.py`:

| Metric | Value |
|--------|-------|
| Total Runs | ~25 |
| Template Runs | 20 |
| Natural Language Runs | 5 |
| AWS Runs | ~15 |
| GCP Runs | ~10 |
| Planned Status | ~12 |
| Completed Status | ~5 |
| Destroyed Status | ~3 |
| Unique AWS Regions | 8 |
| Unique GCP Regions | 10 |

---

## 🎯 Testing Workflow

1. **Start servers** (Steps 1-2 above)
2. **Generate mock data** (Step 3 above)
3. **Open frontend**: `http://localhost:5173`
4. **Test each page** systematically:
   - Dashboard → Runs → Create → Analytics → Resources
5. **Try creating a new run**:
   - Use template method
   - Select from 30 templates
   - Choose from all regions
   - Submit and verify

---

Enjoy testing the production-ready features! 🚀
