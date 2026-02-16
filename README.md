# 🚀 TerraformCloudAgent - AI-Powered Multi-Cloud Infrastructure Generator

An intelligent, conversational AI agent that transforms natural language conversations into production-ready, secure Terraform infrastructure code. Built with FastAPI backend and Streamlit frontend, supporting AWS, GCP, Azure, and DigitalOcean.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [How It Works](#-how-it-works)
- [Core Services](#-core-services)
- [API Reference](#-api-reference)
- [Configuration](#-configuration)
- [Security](#-security)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)

---

## 🎯 Overview

TerraformCloudAgent is a **README-driven, conversational infrastructure generator** that:

1. **Reads your GitHub repository's README** to understand your project
2. **Asks intelligent, context-aware questions** (10-12 for production, 4-6 for dev)
3. **Generates production-grade Terraform code** with security best practices
4. **Deploys infrastructure** with full lifecycle management (plan, apply, destroy)
5. **Provides CI/CD workflows** for automated deployments

### Supported Cloud Providers

- **AWS** - EC2 instances with VPC, Load Balancers, IAM, and 10 predefined role types
- **GCP** - Compute Engine with networking, load balancing, and service accounts
- **Azure** - Virtual Machines with cloud-native defaults
- **DigitalOcean** - Droplets with equivalent VM workflows

---

## ✨ Key Features

### 🤖 Intelligent Conversation System
- **README-First Analysis**: Automatically detects languages, frameworks, databases, ports, and dependencies
- **Environment-Aware Questioning**: Different question flows for Development (simple, cost-focused) vs Production (comprehensive, reliability-focused)
- **Cloud-Specific Terminology**: Uses correct terminology for each provider (EC2 vs Droplets, RDS vs Cloud SQL)
- **Mandatory Question Order**: Enforces Cloud Provider → Environment → Region → Traffic (for prod) → Storage → IAM → Monitoring
- **Turn Guidance System**: AI knows exactly which question to ask next based on conversation state

### 🛡️ Security-First Design
- **No Hardcoded Credentials**: All sensitive data via variables
- **Least-Privilege IAM**: 10 predefined AWS IAM role types
- **Encrypted Everything**: EBS, S3, RDS encryption enabled by default
- **Private Subnets for Databases**: Never expose databases to the internet
- **SSH Restrictions**: Never allows 0.0.0.0/0 for SSH access
- **IMDSv2 Required**: Metadata service protection for AWS

### 🏗️ Production-Grade Code Generation
- **Complete Infrastructure**: Not just scaffolding - full working deployments
- **User Data Scripts**: Automatically clones GitHub repo, installs dependencies, starts the app
- **Docker Support**: Detects Docker in README and generates Docker-based deployment
- **Terraform Validation**: Runs `terraform fmt` and `terraform validate` on generated code
- **GitHub Actions Workflows**: Auto-generates CI/CD pipelines for each cloud provider

### 📊 Multi-Provider Support
- **Unified Interface**: Same conversation flow for all cloud providers
- **Provider-Specific Defaults**: Smart defaults for each cloud (gp3 for AWS, pd-balanced for GCP)
- **Cost Estimation**: Shows monthly cost breakdown before deployment
- **Fallback Logic**: Switches between OpenAI and Gemini if one fails

---

## 🏛️ Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Streamlit Frontend (Port 8501)                   │  │
│  │  - Chat Interface  - File Viewer  - Status Dashboard    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ HTTP/REST
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND (Port 8000)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   API Endpoints                          │  │
│  │  /conversations  /runs  /health  /feedback              │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  CORE SERVICES                           │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────┐ │  │
│  │  │ Conversation   │  │  LLM Service   │  │  GitHub    │ │  │
│  │  │   Manager      │  │  (OpenAI/      │  │  Service   │ │  │
│  │  │                │  │   Gemini)      │  │            │ │  │
│  │  └────────────────┘  └────────────────┘  └────────────┘ │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────┐ │  │
│  │  │  LLM Generator │  │   Workflow     │  │    Run     │ │  │
│  │  │                │  │    Engine      │  │  Manager   │ │  │
│  │  └────────────────┘  └────────────────┘  └────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      PERSISTENCE LAYER                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │    MongoDB       │  │  File System     │  │   Terraform  │ │
│  │  (Conversations) │  │  (Workspaces)    │  │     CLI      │ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. User provides GitHub repo → GithubService fetches README
2. ConversationManager → LLMService analyzes README (extracts tech stack)
3. ConversationManager → Asks 10-12 questions (prod) or 4-6 (dev)
4. User answers → Parameters stored in MongoDB
5. Generate button → LLMGenerator creates Terraform files
6. WorkflowEngine → Runs terraform fmt, validate
7. User approves → WorkflowEngine → terraform apply (async)
8. Outputs saved → User sees IPs, URLs, connection strings
```

---

## 🚀 Quick Start

### Prerequisites

```bash
# Required
- Python 3.11+
- Terraform 1.0+
- MongoDB (local or cloud)
- OpenAI API key OR Google Gemini API key

# Cloud Provider CLIs (for deployments)
- AWS CLI (configured with credentials)
- GCP SDK (authenticated)
- Azure CLI (logged in)
- DigitalOcean CLI (with token)
```

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/nervesparksdev05/TerraformCloudAgent.git
cd TerraformCloudAgent

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
cp .env.example .env
# Edit .env with your API keys and configuration

# 5. Start MongoDB (if local)
mongod --dbpath ./data/db

# 6. Start the backend
python -m app.main
# Backend runs at http://localhost:8000

# 7. Start the frontend (new terminal)
cd frontend
streamlit run app.py
# Frontend runs at http://localhost:8501
```

### Environment Variables

```bash
# Required - LLM Provider
OPENAI_API_KEY=sk-...                    # OpenAI API key
GOOGLE_API_KEY=...                       # OR Gemini API key
LLM_PROVIDER=gemini                      # "openai" or "gemini"

# Required - Database
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=terraform_agent

# Optional - Cloud Defaults
AWS_REGION=us-east-1
GCP_PROJECT_ID=my-project
GCP_REGION=us-central1
AZURE_LOCATION=eastus
DO_REGION=nyc1

# Optional - GitHub
GITHUB_TOKEN=ghp_...                     # For private repos

# Optional - Observability
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 🔄 How It Works

### Phase 1: README Analysis

When you provide a GitHub repository, the system:

1. **Fetches README** using GitHub API (supports private repos with token)
2. **Analyzes with AI** to extract:
   - Primary language/framework (e.g., "Node.js v18 with Express 4.x")
   - Database type (MongoDB, PostgreSQL, Redis, etc.)
   - Exposed ports (3000, 5432, etc.)
   - Dependencies (Docker, Nginx, Celery, etc.)
   - Storage needs (file uploads, logs, etc.)
3. **Generates Greeting** (12-15 lines) showing what it found
4. **Suggests Cloud Provider** based on detected tech stack

### Phase 2: Intelligent Questioning

The bot asks questions in a **strict, mandatory order**:

#### For ALL Deployments:
1. **Cloud Provider** (AWS, GCP, Azure, DigitalOcean)
2. **Environment** (Development or Production) - **CRITICAL**: This determines the entire question flow

#### For Development (4-6 questions):
3. Region (closest/cheapest)
4. Instance type (free tier vs paid)
5. Basic storage (only if README shows database)
6. Basic IAM (CloudWatch logging only)

#### For Production (10-12 questions):
3. Region (latency, compliance, cost)
4. **Traffic Estimation** (DAU, requests/sec) - **MANDATORY**
5. High Availability (Multi-AZ, load balancing)
6. Instance Configuration (type, count, auto-scaling)
7. Storage & Database (based on README findings)
8. IAM Permissions (based on detected services)
9. Monitoring & Alerting (CloudWatch, Cloud Monitoring)
10. Backup Strategy (if database detected)
11. Security (SSH CIDR restrictions)
12. Wrap-up & Confirmation

### Phase 3: Code Generation

The `LLMGenerator` creates three files:

1. **main.tf** - Core infrastructure (VPC, instances, load balancers, security groups)
2. **variables.tf** - All configurable parameters with descriptions and defaults
3. **outputs.tf** - Useful outputs (IPs, URLs, connection strings)
4. **deploy.yml** - GitHub Actions workflow for CI/CD

**Key Features**:
- **User Data Script**: Clones your GitHub repo, installs dependencies, starts the app
- **Docker Support**: If Docker detected, uses Docker-based deployment
- **Database Provisioning**: Creates managed database or configures storage
- **Security Hardening**: Encryption, private subnets, restrictive security groups

### Phase 4: Validation & Deployment

1. **Terraform Format**: Runs `terraform fmt` to clean up code
2. **Terraform Validate**: Checks syntax and configuration
3. **User Review**: Shows generated files in UI
4. **Terraform Plan**: (Skipped in multi-cloud mode to avoid credential requirements)
5. **User Approval**: Click "Deploy" button
6. **Terraform Apply**: Runs in background (async)
7. **Output Capture**: Saves IPs, URLs, and other outputs

---

## 🔧 Core Services

### 1. ConversationManager (`app/services/conversation_manager.py`)

**The "Brain" of the chatbot.**

**Responsibilities**:
- Manages conversation state in MongoDB
- Enforces question order (Cloud → Environment → Region → Traffic → ...)
- Builds dynamic prompts with turn guidance
- Merges AI-extracted parameters into session memory
- Calculates estimated monthly costs
- Applies provider-specific defaults

**Key Methods**:
- `create_session()` - Fetches README, analyzes with AI, creates session
- `process_message()` - Handles user replies, updates parameters, asks next question
- `_call_llm()` - Builds mega-prompt with system rules + turn guidance + README context
- `build_terraform_request()` - Converts chat parameters to Terraform-ready dict

**System Prompt Strategy**:
- **Base Prompt**: Defines TerraBot personality and rules
- **Turn Guidance**: Injected dynamically based on conversation state
- **README Context**: First 3500 chars of README + extracted parameters

### 2. LLMService (`app/services/llm_service.py`)

**The "Universal Translator" for AI models.**

**Responsibilities**:
- Abstracts OpenAI and Gemini APIs
- Handles JSON extraction from LLM responses
- Implements fallback logic (OpenAI → Gemini or vice versa)
- Manages rate limits and authentication

**Key Features**:
- **JSON Mode Enforcement**: Forces LLMs to return valid JSON
- **Markdown Stripping**: Removes ```json fences from responses
- **Async Support**: Non-blocking API calls for web server
- **Model-Specific Handling**: Different logic for Gemini vs OpenAI

### 3. LLMGenerator (`app/services/llm_generator.py`)

**The "Code Factory".**

**Responsibilities**:
- Generates production-grade Terraform code
- Enforces security best practices
- Creates provider-specific configurations
- Generates GitHub Actions workflows

**System Prompts**:
- **BASE_SYSTEM_PROMPT**: Standards of excellence, security rules
- **README_BRIDGE_PROMPT**: README-first behavior
- **AWS_TEMPLATE**: AWS-specific requirements (AMI data sources, IAM, etc.)
- **GCP_TEMPLATE**: GCP-specific requirements (service accounts, etc.)
- **AZURE_TEMPLATE**: Azure-specific requirements
- **DO_TEMPLATE**: DigitalOcean-specific requirements

**Post-Processing**:
- Runs `terraform fmt` to format code
- Runs `terraform validate` to check syntax
- Returns formatted, validated code

### 4. GithubService (`app/services/github_service.py`)

**The "Project Librarian".**

**Responsibilities**:
- Fetches README from GitHub (public or private repos)
- Handles authentication with GitHub tokens
- Implements fallback search for README files
- Decodes Base64-encoded file contents

**Fallback Strategy**:
1. Try `/repos/{owner}/{repo}/readme` endpoint
2. If fails, try common paths: `README.md`, `docs/README.md`, `.github/README.md`, etc.

### 5. WorkflowEngine (`app/services/workflow_engine.py`)

**The "Execution Orchestrator".**

**Responsibilities**:
- Manages Terraform lifecycle (plan, apply, destroy)
- Runs commands asynchronously to avoid blocking
- Captures outputs and errors
- Updates run status in real-time

**Phases**:
- **Planning**: Generate code, validate, save to workspace
- **Apply**: Run `terraform apply -auto-approve`, capture outputs
- **Destroy**: Run `terraform destroy -auto-approve`
- **Revalidate**: Re-check security after manual edits

### 6. RunManager (`app/services/run_manager.py`)

**The "Filing Cabinet".**

**Responsibilities**:
- Creates isolated workspace for each run
- Saves run state to disk (JSON files)
- Tracks status transitions (CREATED → PLANNING → PLANNED → APPLYING → COMPLETED)
- Provides audit trail (saves original request)

**Workspace Structure**:
```
runs/
└── run_20260216_105100/
    ├── state.json          # Run status and metadata
    ├── request.json        # Original user request
    ├── main.tf             # Generated Terraform
    ├── variables.tf
    ├── outputs.tf
    ├── deploy.yml          # GitHub Actions workflow
    └── terraform.tfstate   # Terraform state (after apply)
```

---

## 📡 API Reference

### Conversation Endpoints

#### `POST /conversations`
Start a new conversation.

**Request Body**:
```json
{
  "owner": "facebook",
  "repo": "react",
  "github_token": "ghp_...",  // Optional, for private repos
  "github_branch": "main"     // Optional
}
```

**Response**:
```json
{
  "session_id": "sess_20260216_105100_a1b2c3d4",
  "bot_response": "Welcome! I'm excited to help you deploy React!...",
  "suggestions": ["AWS", "GCP", "Azure", "DigitalOcean"]
}
```

#### `POST /conversations/{session_id}/message`
Send a message in the conversation.

**Request Body**:
```json
{
  "message": "AWS"
}
```

**Response**:
```json
{
  "session_id": "sess_20260216_105100_a1b2c3d4",
  "bot_response": "Great choice! Are you deploying to development or production?",
  "collected_parameters": {
    "cloud_provider": "aws",
    "github_owner": "facebook",
    "github_repo": "react"
  },
  "is_complete": false,
  "suggestions": ["Development", "Production"]
}
```

#### `POST /conversations/{session_id}/generate`
Generate Terraform from collected parameters.

**Response**:
```json
{
  "run_id": "run_20260216_105200",
  "status": "PLANNING"
}
```

---

### Run Endpoints

#### `GET /runs/{run_id}`
Get run status and details.

**Response**:
```json
{
  "run_id": "run_20260216_105200",
  "status": "PLANNED",
  "provider": "aws",
  "log_path": "c:/Users/.../runs/run_20260216_105200",
  "plan_output": "Terraform files generated successfully...",
  "outputs": null
}
```

#### `POST /runs/{run_id}/approve`
Approve and deploy the Terraform plan (async).

**Response**:
```json
{
  "message": "Apply started in background",
  "status": "APPLYING"
}
```

#### `GET /runs/{run_id}/files`
Retrieve generated Terraform files.

**Response**:
```json
{
  "main_tf": "terraform {\n  required_providers {...}",
  "variables_tf": "variable \"aws_region\" {...}",
  "outputs_tf": "output \"instance_ids\" {...}",
  "github_workflow_yaml": "name: Deploy Infrastructure..."
}
```

#### `POST /runs/{run_id}/destroy`
Destroy deployed infrastructure (async).

**Response**:
```json
{
  "message": "Destroy started in background",
  "status": "DESTROYING"
}
```

---

## 🔐 Security

### Security Checker

The `SecurityChecker` validates generated code against:

**Prohibited**:
- ❌ Provisioners (`local-exec`, `remote-exec`, `file`)
- ❌ `null_resource` or `external` data sources
- ❌ Hardcoded credentials (AWS keys, passwords)
- ❌ Unsupported services (Lambda, S3, RDS, Cloud Functions, etc.)
- ❌ SSH from 0.0.0.0/0

**Required**:
- ✅ Variables for all sensitive data
- ✅ Least-privilege IAM policies
- ✅ Encryption enabled (EBS, S3, RDS)
- ✅ Private subnets for databases
- ✅ IMDSv2 for AWS instances

### 10 AWS IAM Role Types

| # | Role Type | Permissions | Use Case |
|---|-----------|-------------|----------|
| 1 | EC2 Basic | Minimal EC2 permissions | Basic compute |
| 2 | EC2 S3 Access | S3 read/write | File storage |
| 3 | EC2 SSM Managed | Systems Manager | Remote management |
| 4 | EC2 CloudWatch Logs | CloudWatch logging | Application logs |
| 5 | EC2 Secrets Manager | Read secrets | API keys, passwords |
| 6 | Lambda Execution | Lambda for EC2 automation | Serverless functions |
| 7 | Cross-Account | Assume role from another account | Multi-account setups |
| 8 | EC2 ECR | Pull Docker images | Container deployments |
| 9 | EC2 DynamoDB | DynamoDB read/write | NoSQL database |
| 10 | EC2 RDS | RDS IAM authentication | Relational database |

---

## 🐛 Troubleshooting

### Common Issues

**"MongoDB not available. Chat will NOT work."**
```bash
# Start MongoDB
mongod --dbpath ./data/db

# Or use Docker
docker run -d -p 27017:27017 mongo:latest
```

**"GitHub rate limit exceeded"**
```bash
# Set GitHub token to increase rate limits
export GITHUB_TOKEN=ghp_...
```

**"Terraform execution failed"**
```bash
# Check Terraform is installed
terraform --version

# Check cloud credentials
aws configure list  # AWS
gcloud auth list    # GCP
az account show     # Azure
doctl auth list     # DigitalOcean
```

**"Security validation failed"**
- Review generated code in `runs/{run_id}/`
- Check for hardcoded credentials
- Ensure SSH is not open to 0.0.0.0/0
- Verify IAM policies follow least-privilege

---

## 📊 Project Structure

```
TerraformCloudAgent/
├── app/
│   ├── core/
│   │   ├── config.py              # Environment configuration
│   │   ├── logger.py              # Logging setup
│   │   └── database.py            # MongoDB connection
│   │
│   ├── models/
│   │   ├── schemas.py             # Pydantic models (RunResponse, AgentRequest, etc.)
│   │   └── conversation_schemas.py # Conversation models
│   │
│   ├── services/
│   │   ├── conversation_manager.py # Chat orchestration
│   │   ├── llm_service.py          # OpenAI/Gemini integration
│   │   ├── llm_generator.py        # Terraform code generation
│   │   ├── github_service.py       # GitHub API client
│   │   ├── workflow_engine.py      # Terraform lifecycle management
│   │   ├── run_manager.py          # Run state management
│   │   ├── workspace_manager.py    # File system operations
│   │   └── security.py             # Security validation
│   │
│   ├── routes/
│   │   ├── conversations.py        # Conversation endpoints
│   │   ├── runs.py                 # Run endpoints
│   │   └── health.py               # Health check
│   │
│   └── main.py                     # FastAPI application
│
├── frontend/
│   ├── app.py                      # Streamlit UI
│   └── api_client.py               # Backend API client
│
├── runs/                           # Isolated run workspaces
├── logs/                           # Application logs
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License.

---

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- LLM integration via [OpenAI](https://openai.com/) and [Google Gemini](https://ai.google.dev/)
- Infrastructure as Code with [Terraform](https://www.terraform.io/)
- UI powered by [Streamlit](https://streamlit.io/)

---

## 📧 Support

For issues, questions, or feature requests:
- Open an issue on [GitHub](https://github.com/nervesparksdev05/TerraformCloudAgent/issues)
- Email: support@example.com

---

**Made with ❤️ by the TerraformCloudAgent Team**
