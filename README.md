# 🚀 Terraform Cloud Agent - Multi-Cloud Infrastructure Automation

An intelligent **LLM-powered Terraform agent** that converts natural language requests into production-ready infrastructure for **AWS** and **GCP**. Features async workflows, model fallback, MongoDB persistence, and full observability.

## ✨ Key Features

- 🤖 **Natural Language to Infrastructure**: Describe what you want, get Terraform code
- 🎨 **Modern Web UI**: Full-featured React frontend with real-time updates
- 📋 **Template Catalog**: 50+ pre-built templates for common infrastructure patterns
- ☁️ **Multi-Cloud Support**: AWS (15 services) + GCP (15 services)
- 🔄 **Interactive Workflow**: Plan → Review → Chat/Edit → Approve → Apply → Destroy
- 🛡️ **Model Fallback**: OpenAI (primary) → Gemini (fallback) for 99.9% uptime
- 💾 **MongoDB Persistence**: State management with automatic file fallback
- 🔭 **Langfuse Observability**: Full LLM tracing and monitoring
- 🔒 **Security First**: Built-in validation and policy enforcement
- 📦 **Isolated Workspaces**: Each deployment runs in its own directory
- 🎯 **RESTful API**: FastAPI with async background tasks
- 📊 **Analytics Dashboard**: Monitor deployments, costs, and resource usage

## 🏗️ Architecture

See [Project Walkthrough](./PROJECT_WALKTHROUGH.md) for detailed flow explanation.

```
User (Web UI) → FastAPI (main.py) → LLMGenerator (OpenAI/Gemini)
                    ↓                         ↓
                MongoDB                SecurityChecker
                    ↓                         ↓
            WorkspaceManager           TerraformRunner → AWS/GCP
```

**State Machine**: `CREATED` → `PLANNING` → `PLANNED` → `APPROVED` → `APPLYING` → `COMPLETED` → `DESTROYING` → `DESTROYED`

## 🚦 Quick Start

### Prerequisites

- Python 3.9+
- Terraform CLI installed
- MongoDB (optional, falls back to files)
- OpenAI API key
- AWS or GCP credentials

### Installation

```bash
# Clone repository
cd TerraformCloudAgent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Configuration

Edit `.env`:

```env
# === OpenAI Configuration ===
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.2

# === Google Gemini (Fallback) ===
GOOGLE_API_KEY=AIza...
GEMINI_MODEL=gemini-1.5-pro

# === Langfuse (Observability) ===
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# === MongoDB (Optional) ===
MONGODB_URI=mongodb://localhost:27017/terraform_agent
MONGODB_DATABASE=terraform_agent

# === AWS Configuration ===
DEFAULT_PROVIDER=aws
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# === GCP Configuration ===
GCP_PROJECT_ID=my-project
GCP_REGION=us-central1
GCP_CREDENTIALS_PATH=path/to/service-account.json
```

### Run Backend

```bash
# Start backend server
uvicorn app.main:app --reload --port 8000
```

Backend: `http://localhost:8000`  
API Docs: `http://localhost:8000/docs`

### Run Frontend

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies (first time only)
npm install

# Start development server
npm run dev
```

Frontend: `http://localhost:5173`  
The frontend will automatically proxy API requests to the backend.

## 📖 API Usage

### 1. Create a Run

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Create a web server with HTTP access",
    "provider": "aws"
  }'
```

**Response (202 Accepted):**
```json
{
  "run_id": "run_20260207_210000",
  "status": "created",
  "provider": "aws",
  "log_path": "runs/run_20260207_210000"
}
```

### 2. Check Status

```bash
curl http://localhost:8000/runs/run_20260207_210000
```

**Response:**
```json
{
  "run_id": "run_20260207_210000",
  "status": "planned",
  "provider": "aws",
  "plan_output": "Terraform will perform the following actions...",
  "cost_estimate": null
}
```

### 3. Chat & Refine

**Ask Questions:**
```bash
curl -X POST http://localhost:8000/runs/run_20260207_210000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What will this cost?"}'
```

**Request Changes (Refine Plan):**
```bash
curl -X POST http://localhost:8000/runs/run_20260207_210000/edit \
  -H "Content-Type: application/json" \
  -d '{"message": "Change the instance type to t3.small"}'
```

**Response:**
```json
{
  "run_id": "run_20260207_210000",
  "status": "planning"
}
```

Wait for status to return to `planned` to see updated resources.

### 4. Approve & Deploy

```bash
curl -X POST http://localhost:8000/runs/run_20260207_210000/approve
```

**Response:**
```json
{
  "run_id": "run_20260207_210000",
  "status": "approved"
}
```

Poll until `status` becomes `completed`:

```json
{
  "run_id": "run_20260207_210000",
  "status": "completed",
  "outputs": {
    "instance_id": "i-0123456789abcdef0",
    "public_ip": "13.127.45.67"
  }
}
```

### 5. Destroy Infrastructure

```bash
curl -X POST http://localhost:8000/runs/run_20260207_210000/destroy
```

**Response:**
```json
{
  "run_id": "run_20260207_210000",
  "status": "destroying"
}
```

Poll until `status` becomes `destroyed`.

## 🌐 Multi-Cloud Support

### AWS Services (Top 15)
EC2, Lambda, ECS, S3, EBS, RDS, DynamoDB, VPC, Security Groups, Subnets, IGW, ALB, IAM, API Gateway, SQS

### GCP Services (Top 15)
Compute Engine, Cloud Functions, Cloud Run, Cloud Storage, Persistent Disk, Cloud SQL, Firestore, VPC, Firewall Rules, Subnets, Load Balancer, IAM, Pub/Sub, Cloud Scheduler

### Example Requests

**AWS Web Server:**
```json
{"request": "Create an EC2 web server with nginx", "provider": "aws"}
```

**GCP Database:**
```json
{"request": "Deploy a Cloud SQL MySQL instance", "provider": "gcp"}
```

**AWS Lambda:**
```json
{"request": "Create a Lambda function for image processing", "provider": "aws"}
```

## 🔒 Security Features

### Validation Layers
1. **Pydantic Schemas**: Request validation
2. **LLM Prompt Engineering**: Constrained generation
3. **SecurityChecker**: Policy enforcement
4. **Terraform Plan**: Pre-deployment review

### Prohibited Patterns
- ❌ Provisioners (local-exec, remote-exec)
- ❌ Hardcoded credentials
- ❌ Non-approved resources
- ❌ External data sources

## 🔭 Observability

### Langfuse Integration
- Traces all LLM calls (OpenAI + Gemini)
- Captures prompts, completions, errors
- Links traces to `run_id`
- Tracks model fallback events

**Setup**: Add Langfuse keys to `.env` (see Configuration section)

### Logs
- Application logs: `logs/app_YYYYMMDD.log`
- Terraform logs: `runs/<run_id>/terraform.log`

## 💾 State Management

### MongoDB (Primary)
- Stores run state and chat history
- Indexed for performance
- Supports queries and analytics

### File Fallback
- Automatic fallback if MongoDB unavailable
- Stored in `runs/<run_id>/state.json`
- Dual persistence for reliability

## 📁 Project Structure

```
TerraformCloudAgent/
├── app/
│   ├── core/
│   │   ├── config.py              # Environment configuration
│   │   ├── database.py            # MongoDB service
│   │   └── logger.py              # Logging setup
│   ├── models/
│   │   └── schemas.py             # Pydantic models
│   ├── services/
│   │   ├── llm_generator.py       # OpenAI/Gemini integration
│   │   ├── security_checker.py    # Policy validation
│   │   ├── terraform_runner.py    # Terraform execution
│   │   ├── workspace_manager.py   # Workspace management
│   │   ├── templates_catalog.py   # Template definitions
│   │   ├── insights_service.py    # Analytics & monitoring
│   │   └── settings_store.py      # User settings
│   ├── prompts/
│   │   ├── aws_focused_system_prompt.txt
│   │   └── gcp_focused_system_prompt.txt
│   └── main.py                    # FastAPI application
├── frontend/
│   ├── client/
│   │   ├── src/                   # React source code
│   │   ├── public/                # Static assets
│   │   └── index.html             # HTML entry point
│   ├── shared/
│   │   └── schema.ts              # TypeScript types
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.ts
├── runs/                          # Workspace directories
├── logs/                          # Application logs
├── .env                           # Environment variables
├── requirements.txt               # Python dependencies
└── PROJECT_WALKTHROUGH.md         # Code flow documentation
```

## 🚀 Production Readiness

### ✅ Ready
- Multi-cloud support (AWS + GCP)
- Model fallback (OpenAI → Gemini)
- MongoDB persistence with file fallback
- Langfuse observability
- Security validation
- Infrastructure lifecycle (create + destroy)

### ⚠️ Needs Attention
- **Authentication**: No API key/OAuth (critical)
- **Rate Limiting**: No DDoS protection
- **HTTPS**: Traffic unencrypted
- **Worker Isolation**: Move to Celery + Redis

See [Production Readiness Assessment](./brain/production_readiness.md) for details.

## 🛠️ Development

### API Documentation
Visit `http://localhost:8000/docs` for interactive Swagger UI.

### Running Tests
```bash
# Unit tests
pytest tests/

# Integration tests
pytest tests/integration/
```

### Docker Deployment
```bash
# Build image
docker build -t terraform-agent .

# Run with docker-compose
docker-compose up -d
```

## 📚 Documentation

- [Project Walkthrough](./PROJECT_WALKTHROUGH.md) - End-to-end code flow explanation
- [Langfuse Integration](./LANGFUSE_INTEGRATION.md) - LLM observability setup
- [Security Checker Fix](./SECURITY_CHECKER_FIX.md) - Security validation details
- [Testing Guide](./TESTING_GUIDE.md) - How to test the application
- [Template Parameters](./TEMPLATE_PARAMETERS_STATUS.md) - Template system documentation

## 🎯 Roadmap

- [x] Multi-cloud support (AWS + GCP)
- [x] Interactive workflow (plan → review → approve)
- [x] Model fallback (OpenAI → Gemini)
- [x] MongoDB persistence
- [x] Langfuse observability
- [x] Terraform destroy
- [x] Frontend UI (React + Vite + Tailwind)
- [x] Template catalog (50+ templates)
- [x] Analytics dashboard
- [ ] Cost estimation (Infracost)
- [ ] Authentication & rate limiting
- [ ] WebSocket real-time logs
- [ ] Multi-user support

## 🤝 Contributing

Contributions welcome! Please ensure:
- Code follows existing patterns
- Security validations are maintained
- Tests pass
- Documentation updated

## 📄 License

## 🆘 Support

For issues:
1. Check logs in `logs/` directory
2. Review Terraform logs in workspace
3. Verify credentials in `.env`
4. Ensure Terraform CLI is installed
5. Check MongoDB connection (if used)

---

**Built with ❤️ By NerveSparks**
