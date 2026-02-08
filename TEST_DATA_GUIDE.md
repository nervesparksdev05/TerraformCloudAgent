# Test Data Summary

## 📊 Available Test Runs

You now have **11 test runs** available in your system for testing the UI!

### Test Runs Created
All runs are stored in: `runs/` directory

Each run includes:
- Run ID (e.g., `run_20260208_051515`)
- Provider (AWS or GCP)
- Request description
- Status (planning, planned, failed, etc.)
- Generated Terraform code
- State files

### How to View Test Data

#### Option 1: API (Recommended)
Visit the API documentation to explore all runs:
```
http://localhost:8000/docs
```

Try these endpoints:
- `GET /runs` - List all runs
- `GET /runs/{run_id}` - Get specific run details

#### Option 2: Frontend UI
Open the frontend application:
```
http://localhost:5174
```

The UI should display all available runs with their statuses.

#### Option 3: Direct File Access
Browse the `runs/` directory to see all run workspaces:
```
C:\Users\nerve\Desktop\NerveSparks\TerraformCloudAgent\runs\
```

Each directory contains:
- `state.json` - Run metadata and status
- `main.tf` - Generated Terraform main configuration
- `variables.tf` - Terraform variables
- `outputs.tf` - Terraform outputs
- `request.json` - Original user request

### Creating More Test Data

To create additional test runs, you can:

1. **Use the Frontend**: Open http://localhost:5174 and create new deployments
2. **Use the API**: Send POST requests to `/runs` endpoint
3. **Run the script**: Execute `python create_test_data.py` (may take time due to LLM generation)

### Example API Call
```powershell
Invoke-WebRequest -Uri http://localhost:8000/runs `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"request": "Create an S3 bucket", "provider": "aws"}' `
  -UseBasicParsing
```

## 🎯 Next Steps

1. **Explore the Frontend**: http://localhost:5174
2. **Browse API Docs**: http://localhost:8000/docs
3. **Check Run Details**: Click on any run to see generated Terraform code
4. **Test Workflows**: Try approving, chatting, editing runs

Enjoy testing! 🚀
