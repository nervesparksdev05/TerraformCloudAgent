# 🚀 TerraformCloudAgent

An AI-powered, conversational infrastructure generator that reads your GitHub repository's README and generates production-ready Terraform code for GCP — with a full lifecycle management UI.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [How It Works](#-how-it-works)
- [API Reference](#-api-reference)
- [Project Structure](#-project-structure)
- [Docker Deployment](#-docker-deployment)
- [Troubleshooting](#-troubleshooting)

---

## 🎯 Overview

TerraformCloudAgent is a **README-driven, conversational infrastructure generator** that:

1. **Reads your GitHub repository's README** to understand your project (supports private repos via token)
2. **Asks intelligent, context-aware questions** (10–12 for production, 4–6 for dev)
3. **Generates production-grade Terraform code** for GCP with security best practices
4. **Lets you edit files inline** or request AI-driven re-generation with natural language feedback
5. **Deploys infrastructure** with full lifecycle management (plan, approve, apply, destroy)
6. **Sends approval emails** for remote team review before deployment
7. **Persists all data** (conversations, sessions, users) to MongoDB

### Target Cloud Provider

| Provider | Compute        | Networking                   | IAM              |
| -------- | -------------- | ---------------------------- | ---------------- |
| **GCP**  | Compute Engine | VPC, Subnets, Firewall Rules | Service Accounts |

---

## ✨ Key Features

### 🤖 Intelligent Conversation System

- **README-First Analysis**: Detects languages, frameworks, databases, ports, and dependencies automatically
- **Environment-Aware Questioning**: Dev (4–6 questions, cost-focused) vs Production (10–12 questions, reliability-focused)
- **Streaming Responses**: Real-time token streaming via Server-Sent Events
- **Turn Guidance System**: AI knows exactly which question to ask next based on conversation state

### 🔐 Authentication & User Management

- **Firebase Authentication**: Email/password sign-up and sign-in
- **Google OAuth**: One-click "Continue with Google" via Firebase SDK popup
- **MongoDB User Sync**: Every login (email or Google) upserts a user record in the `users` collection
- **Protected API**: All endpoints require a valid Firebase Bearer token (configurable via `REQUIRE_AUTH`)

### 🏗️ Production-Grade Code Generation

- **Three Terraform Files**: `main.tf`, `variables.tf`, `outputs.tf`
- **User Data Scripts**: Clones your GitHub repo, installs dependencies, starts the app
- **Docker Support**: Detects Docker in README and generates Docker-based deployment
- **Terraform Validation**: Runs `terraform fmt` and `terraform validate` on generated code

### ✏️ Edit & Update Terraform Files

- **Inline Editor**: Click Edit on any file in the File Review tab to edit it directly in the browser
- **Save Changes**: Writes edited files back to disk via `POST /runs/{id}/files`
- **AI Re-generation**: Describe changes in natural language → AI regenerates all files via `POST /runs/{id}/edit`
- **Chat About Plan**: Ask questions about the generated Terraform plan via `POST /runs/{id}/chat`

### 📧 Email Approval Workflow

- Send Terraform files to your email for review before deployment
- Secure, action-specific approval/rejection tokens (no token reuse, 24h expiry)
- HTML email with syntax-highlighted Terraform code
- One-click approve/reject links in the email

### 📊 Observability

- **Langfuse Integration**: LLM call tracing, token usage tracking, and user feedback scoring
- **Structured Logging**: Per-session and per-run log files
- **MongoDB Persistence**: Conversations, sessions, and user records survive restarts

### ⚡ Rate Limiting

- **Redis-backed**: Per-user rate limiting via Redis (graceful bypass when Redis is unavailable)
- **Per-endpoint**: Applied on conversations, messages, feedback, runs, and edits

### 🔍 Frontend Insights

- **Mermaid Diagrams**: Architecture visualization rendered with Mermaid.js
- **Topology Vision**: Infrastructure topology preview
- **Self-Healer Alerts**: Proactive suggestions panel

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  REACT + VITE FRONTEND (Port 5173)              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Login (Email/Google) → WelcomePage → WorkspacePage      │  │
│  │  Tabs: Conversation | File Review (Edit) | Lifecycle     │  │
│  │  Panels: Insights | Topology Vision | Session History    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ HTTP/REST + SSE
┌─────────────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND (Port 8000)                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /auth  /conversations  /runs  /approve  /reject /health │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ConversationManager │ LLMService │ LLMGenerator         │  │
│  │  GithubService       │ WorkflowEngine │ RunManager       │  │
│  │  UserService │ EmailService │ WorkspaceManager           │  │
│  │  LangfuseService │ RateLimiter │ StreamingHelper         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       PERSISTENCE LAYER                         │
│  MongoDB (conversations, sessions, users)                       │
│  Redis (rate limiting)                                          │
│  File System (Terraform workspaces per run)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

```
- Python 3.11+
- Node.js 18+
- Terraform 1.0+
- MongoDB (local or Atlas)
- Redis (optional, for rate limiting)
- Google Gemini API key
- Firebase project (for auth)
- GCP service account (for deployment)
```

### Backend Setup

```bash
# 1. Clone the repository
git clone https://github.com/nervesparksdev05/TerraformCloudAgent.git
cd TerraformCloudAgent

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys (see Environment Variables below)

# 5. Start the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Frontend runs at http://localhost:5173
```

---

## 🔧 Environment Variables

```bash
# ── LLM ──────────────────────────────────────────────
GEMINI_API_KEY=...                       # Required
GEMINI_MODEL=gemini-2.5-pro             # Default: gemini-2.5-pro

# ── Database ─────────────────────────────────────────
MONGODB_URI=mongodb://localhost:27017/terraform_agent
MONGODB_DATABASE=terraform_agent

# ── Redis (Rate Limiting) ────────────────────────────
REDIS_URL=redis://redis:6379            # Optional; rate limiting bypassed if unavailable

# ── Firebase Auth ─────────────────────────────────────
REQUIRE_AUTH=true
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
FIREBASE_API_KEY=your-api-key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com

# ── GCP Credentials ──────────────────────────────────
GCP_PROJECT_ID=your-gcp-project
GCP_REGION=us-central1
GCP_ZONE=us-central1-a
GCP_CREDENTIALS_PATH=./gcp-sa-key.json

# ── AWS (if needed for multi-cloud) ──────────────────
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# ── Email Approvals ───────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app-password
SMTP_FROM_EMAIL=you@gmail.com
SMTP_FROM_NAME=Terraform Cloud Agent
SEND_EMAIL_ALERTS=true
APPROVAL_TOKEN_SECRET=change-this-secret-key
APPROVAL_TOKEN_EXPIRY_HOURS=24
BASE_URL=http://localhost:8000

# ── Observability (optional) ──────────────────────────
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com

# ── GitHub (optional, for private repos) ─────────────
GITHUB_TOKEN=ghp_...

# ── Server ────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
DEBUG=false

# ── Terraform ─────────────────────────────────────────
TERRAFORM_TIMEOUT=300
ENABLE_TERRAFORM_MCP=true
DEFAULT_PROVIDER=gcp                    # Must be one of: aws, gcp, azure, digitalocean
```

---

## 🔄 How It Works

### Phase 1: README Analysis

1. User provides GitHub owner, repo, optional token (private repos), and optional branch
2. `GithubService` fetches the README via GitHub API
3. `LLMService` analyzes it: extracts language, framework, database, ports, dependencies
4. Bot greets the user with a summary of what it found

### Phase 2: Intelligent Questioning

Questions follow a **strict mandatory order**:

| Step  | All Deployments | Dev Only       | Prod Only                                      |
| ----- | --------------- | -------------- | ---------------------------------------------- |
| 1     | Cloud Provider  |                |                                                |
| 2     | Environment     |                |                                                |
| 3     | Region          | ✓ (cheapest)   | ✓ (latency/compliance)                        |
| 4     |                 | Basic instance | Traffic estimation                              |
| 5–12  |                 |                | HA, storage, IAM, monitoring, backup, security  |

### Phase 3: Code Generation

`LLMGenerator` creates:

- **`main.tf`** — VPC, instances, security groups, IAM, firewalls
- **`variables.tf`** — All configurable parameters with descriptions and defaults
- **`outputs.tf`** — IPs, URLs, connection strings

Then runs `terraform fmt` + `terraform validate` automatically.

### Phase 4: Review & Edit

In the **File Review** tab:

- **Inline editing**: Click Edit on any file, modify in textarea, click Save
- **AI re-generation**: Type natural language feedback → AI rewrites all files
- **Chat about plan**: Ask questions about generated infrastructure
- **Download**: Download any file individually

### Phase 5: Deployment

In the **Lifecycle** tab:

- **Approve & Deploy**: Runs `terraform apply -auto-approve` in background
- **Request Email Approval**: Sends HTML email with Terraform files and approve/reject links
- **Reject Plan**: Marks run as rejected
- **Destroy**: Runs `terraform destroy -auto-approve`

---

## 📡 API Reference

### Auth

| Method | Endpoint         | Description                                          |
| ------ | ---------------- | ---------------------------------------------------- |
| `POST` | `/auth/sync-user` | Upsert Firebase user into MongoDB `users` collection |
| `POST` | `/auth/verify`   | Verify authentication and return user info           |

### Conversations

| Method   | Endpoint                                | Description                            |
| -------- | --------------------------------------- | -------------------------------------- |
| `POST`   | `/conversations`                        | Start a new README-driven conversation |
| `POST`   | `/conversations/{id}/message`           | Send a message (non-streaming)         |
| `POST`   | `/conversations/{id}/message/stream`    | Send a message (SSE streaming)         |
| `GET`    | `/conversations/{id}`                   | Get conversation details               |
| `GET`    | `/conversations`                        | List all conversations                 |
| `POST`   | `/conversations/{id}/feedback`          | Submit user feedback (rating/comment)  |
| `POST`   | `/conversations/{id}/generate`          | Manually trigger Terraform generation  |
| `DELETE` | `/sessions/{id}`                        | Delete a session                       |

### Runs

| Method | Endpoint                         | Description                                    |
| ------ | -------------------------------- | ---------------------------------------------- |
| `POST` | `/runs`                          | Create a new run directly                      |
| `GET`  | `/runs/{id}`                     | Get run status and details                     |
| `POST` | `/runs/{id}/chat`                | Chat / ask questions about the Terraform plan  |
| `POST` | `/runs/{id}/edit`                | AI re-generation with natural language feedback |
| `GET`  | `/runs/{id}/files`               | Get generated Terraform files                  |
| `POST` | `/runs/{id}/files`               | Save manually edited files + re-validate       |
| `POST` | `/runs/{id}/approve`             | Approve and deploy (async)                     |
| `POST` | `/runs/{id}/reject`              | Reject the plan                                |
| `POST` | `/runs/{id}/destroy`             | Destroy deployed infrastructure (async)        |
| `POST` | `/runs/{id}/send-for-approval`   | Send approval email                            |
| `GET`  | `/runs/{id}/approval-status`     | Get approval workflow status                   |

### Email Approval (token-based)

| Method | Endpoint            | Description                       |
| ------ | ------------------- | --------------------------------- |
| `GET`  | `/approve/{token}`  | Approve run via email link        |
| `GET`  | `/reject/{token}`   | Reject run via email link         |

### Other

| Method | Endpoint  | Description  |
| ------ | --------- | ------------ |
| `GET`  | `/`       | API info     |
| `GET`  | `/health` | Health check |

Interactive API docs available at `/docs` (Swagger UI).

---

## 📁 Project Structure

```
TerraformCloudAgent/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI application & all routes
│   ├── rate_limiter.py                  # Redis-backed per-user rate limiting
│   ├── streaming_helper.py              # SSE streaming utilities
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── auth.py                      # Firebase token verification (Admin SDK)
│   │   ├── config.py                    # Environment configuration
│   │   ├── database.py                  # MongoDB singleton connection
│   │   └── logger.py                    # Structured logging setup
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py                   # Pydantic models (RunResponse, AgentRequest, etc.)
│   │   └── conversation_schemas.py      # Chat/conversation Pydantic models
│   │
│   └── services/
│       ├── __init__.py
│       ├── conversation_manager.py      # Chat orchestration & state machine
│       ├── llm_service.py               # Gemini API integration
│       ├── llm_generator.py             # Terraform code generation
│       ├── github_service.py            # GitHub API client (public + private repos)
│       ├── workflow_engine.py           # Terraform lifecycle (plan/apply/destroy)
│       ├── run_manager.py               # Run state & workspace management
│       ├── workspace_manager.py         # Workspace directory management
│       ├── user_service.py              # MongoDB user upsert (auth sync)
│       ├── email_service.py             # SMTP approval emails
│       └── langfuse_service.py          # Langfuse observability integration
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js                   # Vite bundler config
│   ├── tailwind.config.js               # Tailwind CSS config
│   ├── postcss.config.js
│   └── src/
│       ├── main.jsx                     # React entry point
│       ├── App.jsx                      # Root component & routing
│       ├── App.css
│       ├── index.css                    # Global styles
│       ├── Login.jsx                    # Email/password + Google sign-in
│       │
│       ├── pages/
│       │   ├── WelcomePage.jsx          # New chat form (owner, repo, token, branch)
│       │   └── WorkspacePage.jsx        # Chat + File Review (edit) + Lifecycle tabs
│       │
│       ├── components/
│       │   ├── common/                  # Button, Card, Input, Badge
│       │   ├── layout/                  # Sidebar
│       │   └── features/
│       │       ├── chat/                # ChatPanel, ChatMessage, ChatInput, CodeEditor, CodeViewer
│       │       ├── insights/            # InsightsPanel, MermaidDiagram, SelfHealerAlert
│       │       ├── preview/             # TopologyVision
│       │       └── sessions/            # SessionItem
│       │
│       ├── services/
│       │   ├── api.js                   # Re-exports from client.js
│       │   ├── client.js                # Axios instance + all API methods
│       │   ├── auth.js                  # Firebase REST + Google OAuth
│       │   └── firebase.js              # Firebase app initialization
│       │
│       └── hooks/
│           ├── useAuth.js               # Authentication hook
│           └── useSession.js            # Session management hook
│
├── scripts/
│   ├── load_test.py                     # Locust load testing
│   ├── test_generation.py               # Code generation tests
│   ├── test_langfuse.py                 # Langfuse integration tests
│   ├── test_mcp.py                      # MCP integration tests
│   └── test_mini.py                     # Minimal smoke tests
│
├── runs/                                # Isolated Terraform workspaces per run
│   └── run_YYYYMMDD_HHMMSS/
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       └── state.json
│
├── logs/                                # Application logs
├── Dockerfile                           # Backend container image
├── Dockerfile.mcp                       # MCP server container image
├── docker-compose.yml                   # Redis + API orchestration
├── gunicorn.conf.py                     # Gunicorn production config
├── requirements.txt                     # Python dependencies
├── .env                                 # Environment variables (not committed)
└── .gitignore
```

---

## 🐳 Docker Deployment

### Using Docker Compose

```bash
# 1. Build and start services (API + Redis)
docker-compose up --build -d

# 2. View logs
docker-compose logs -f api

# 3. Stop services
docker-compose down
```

The `docker-compose.yml` starts two services:

- **redis**: Redis 7 Alpine for rate limiting
- **api**: FastAPI backend (port 8000), with GCP credentials mounted as a volume

> **Note:** Place your GCP service account key at `./gcp-sa-key.json` before running. The file is mounted read-only into the container.

### Using Gunicorn (Production)

```bash
gunicorn app.main:app -c gunicorn.conf.py
```

---

## 🐛 Troubleshooting

**MongoDB connection failed**

```bash
# Local MongoDB
mongod --dbpath ./data/db

# Or Docker
docker run -d -p 27017:27017 mongo:latest
```

**Firebase auth errors**

- Ensure `FIREBASE_PROJECT_ID` and `FIREBASE_SERVICE_ACCOUNT_PATH` are set correctly
- The service account JSON file must be accessible at the configured path
- For Google OAuth, ensure the Firebase project has Google as a sign-in provider

**GitHub rate limit / private repo 404**

- Set `GITHUB_TOKEN` in `.env` or pass it in the UI's "GitHub Token" field
- For private repos, use a token with `repo` scope

**Terraform not found**

```bash
# Verify installation
terraform --version

# Windows: ensure terraform.exe is in PATH
```

**Terraform validate fails after edit**

- The backend automatically re-runs `terraform fmt` + `terraform validate` after file saves
- Check `logs/` for detailed error output

**Redis connection issues**

- Redis is optional; rate limiting is bypassed if Redis is unavailable
- For Docker: ensure the `redis` service is healthy before `api` starts
- For local dev: `redis-server` or skip (the app handles it gracefully)

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

**Built with [FastAPI](https://fastapi.tiangolo.com/) · [React 19](https://react.dev/) · [Vite](https://vite.dev/) · [Tailwind CSS](https://tailwindcss.com/) · [Google Gemini](https://ai.google.dev/) · [Terraform](https://www.terraform.io/) · [Firebase](https://firebase.google.com/) · [MongoDB](https://www.mongodb.com/) · [Redis](https://redis.io/)**
