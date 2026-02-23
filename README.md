# 🚀 TerraformCloudAgent

An AI-powered, conversational infrastructure generator that reads your GitHub repository's README and generates production-ready Terraform code for AWS, GCP, Azure, and DigitalOcean — with a full lifecycle management UI.

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
- [Troubleshooting](#-troubleshooting)

---

## 🎯 Overview

TerraformCloudAgent is a **README-driven, conversational infrastructure generator** that:

1. **Reads your GitHub repository's README** to understand your project (supports private repos via token)
2. **Asks intelligent, context-aware questions** (10–12 for production, 4–6 for dev)
3. **Generates production-grade Terraform code** with security best practices baked in
4. **Lets you edit files inline** or request AI-driven re-generation with natural language feedback
5. **Deploys infrastructure** with full lifecycle management (plan, approve, apply, destroy)
6. **Sends approval emails** for remote team review before deployment
7. **Persists all users** (email/password and Google OAuth) to MongoDB

### Supported Cloud Providers

| Provider               | Compute          | Networking                   | IAM                                     |
| ---------------------- | ---------------- | ---------------------------- | --------------------------------------- |
| **AWS**          | EC2              | VPC, Subnets, IGW, SGs       | IAM Roles (10 types), Instance Profiles |
| **GCP**          | Compute Engine   | VPC, Subnets, Firewall Rules | Service Accounts                        |
| **Azure**        | Virtual Machines | VNet, Subnets, NSGs          | Managed Identity                        |
| **DigitalOcean** | Droplets         | Firewall                     | SSH Keys                                |

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
- **Protected API**: All endpoints require a valid Firebase Bearer token

### 🏗️ Production-Grade Code Generation

- **Three Terraform Files**: `main.tf`, `variables.tf`, `outputs.tf`
- **GitHub Actions CI/CD**: Auto-generated `deploy.yml` for each cloud provider
- **User Data Scripts**: Clones your GitHub repo, installs dependencies, starts the app
- **Docker Support**: Detects Docker in README and generates Docker-based deployment
- **Terraform Validation**: Runs `terraform fmt` and `terraform validate` on generated code

### ✏️ Edit & Update Terraform Files

- **Inline Editor**: Click Edit on any file in the File Review tab to edit it directly in the browser
- **Save Changes**: Writes edited files back to disk via `POST /runs/{id}/files`
- **AI Re-generation**: Describe changes in natural language → AI regenerates all files via `POST /runs/{id}/edit`

### 📧 Email Approval Workflow

- Send Terraform files to any email for remote review before deployment
- Secure, action-specific approval/rejection tokens (no token reuse)
- HTML email with syntax-highlighted Terraform code

### 📊 Observability

- **Langfuse Integration**: LLM call tracing and token usage tracking
- **Structured Logging**: Per-session and per-run log files
- **MongoDB Persistence**: Conversations, sessions, and user records survive restarts

---

## 🏛️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     REACT FRONTEND (Port 5174)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Login (Email/Google) → WelcomePage → WorkspacePage      │  │
│  │  Tabs: Conversation | File Review (Edit) | Lifecycle     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ HTTP/REST + SSE
┌─────────────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND (Port 8000)                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /auth/sync-user  /conversations  /runs  /health         │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ConversationManager │ LLMService │ LLMGenerator         │  │
│  │  GithubService       │ WorkflowEngine │ RunManager       │  │
│  │  UserService         │ EmailService                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       PERSISTENCE LAYER                         │
│  MongoDB (conversations, sessions, users) │ File System (runs)  │
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
- Google Gemini API key
- Firebase project (for auth)
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
# Edit .env with your API keys

# 5. Start the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Frontend runs at http://localhost:5174
```

---

## 🔧 Environment Variables

```bash
# ── LLM ──────────────────────────────────────────────
GEMINI_API_KEY=...                    # Required
LLM_PROVIDER=gemini

# ── Database ─────────────────────────────────────────
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=terraform_agent

# ── Firebase Auth ─────────────────────────────────────
REQUIRE_AUTH=true
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CREDENTIALS_PATH=./your-firebase-adminsdk.json

# ── Email Approvals ───────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app-password
APPROVAL_BASE_URL=http://localhost:8000

# ── Observability (optional) ──────────────────────────
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com

# ── GitHub (optional, for private repos) ─────────────
GITHUB_TOKEN=ghp_...
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
| 3     | Region          | ✓ (cheapest)  | ✓ (latency/compliance)                        |
| 4     |                 | Basic instance | Traffic estimation                             |
| 5–12 |                 |                | HA, storage, IAM, monitoring, backup, security |

### Phase 3: Code Generation

`LLMGenerator` creates:

- **`main.tf`** — VPC, instances, security groups, IAM, load balancers
- **`variables.tf`** — All configurable parameters with descriptions and defaults
- **`outputs.tf`** — IPs, URLs, connection strings
- **`deploy.yml`** — GitHub Actions CI/CD workflow

Then runs `terraform fmt` + `terraform validate` automatically.

### Phase 4: Review & Edit

In the **File Review** tab:

- **Inline editing**: Click Edit on any file, modify in textarea, click Save
- **AI re-generation**: Type natural language feedback → AI rewrites all files
- **Download**: Download any file individually

### Phase 5: Deployment

In the **Lifecycle** tab:

- **Approve & Deploy**: Runs `terraform apply -auto-approve` in background
- **Request Remote Approval**: Sends HTML email with Terraform files and approve/reject links
- **Reject Plan**: Marks run as rejected
- **Destroy**: Runs `terraform destroy -auto-approve`

---

## 📡 API Reference

### Auth / User

| Method   | Endpoint            | Description                                            |
| -------- | ------------------- | ------------------------------------------------------ |
| `POST` | `/auth/sync-user` | Upsert Firebase user into MongoDB `users` collection |
| `GET`  | `/auth/me`        | Get current user's MongoDB profile                     |

### Conversations

| Method     | Endpoint                               | Description                            |
| ---------- | -------------------------------------- | -------------------------------------- |
| `POST`   | `/conversations`                     | Start a new README-driven conversation |
| `POST`   | `/conversations/{id}/message`        | Send a message (non-streaming)         |
| `POST`   | `/conversations/{id}/message/stream` | Send a message (SSE streaming)         |
| `GET`    | `/conversations/{id}`                | Get conversation details               |
| `POST`   | `/conversations/{id}/generate`       | Manually trigger Terraform generation  |
| `GET`    | `/sessions`                          | List all sessions                      |
| `DELETE` | `/sessions/{id}`                     | Delete a session                       |

### Runs

| Method   | Endpoint                         | Description                                     |
| -------- | -------------------------------- | ----------------------------------------------- |
| `GET`  | `/runs/{id}`                   | Get run status and details                      |
| `GET`  | `/runs/{id}/files`             | Get generated Terraform files                   |
| `POST` | `/runs/{id}/files`             | Save manually edited files + re-validate        |
| `POST` | `/runs/{id}/edit`              | AI re-generation with natural language feedback |
| `POST` | `/runs/{id}/approve`           | Approve and deploy (async)                      |
| `POST` | `/runs/{id}/reject`            | Reject the plan                                 |
| `POST` | `/runs/{id}/destroy`           | Destroy deployed infrastructure (async)         |
| `POST` | `/runs/{id}/send-for-approval` | Send approval email                             |

### Other

| Method   | Endpoint                     | Description                  |
| -------- | ---------------------------- | ---------------------------- |
| `GET`  | `/health`                  | Health check                 |
| `POST` | `/feedback`                | Submit LLM feedback          |
| `GET`  | `/runs/{id}/approve-email` | Email approval link handler  |
| `GET`  | `/runs/{id}/reject-email`  | Email rejection link handler |

---

## 📁 Project Structure

TerraformCloudAgent/
├── app/
│   ├── core/
│   │   ├── auth.py                # Firebase token verification (Admin SDK)
│   │   ├── config.py              # Environment configuration
│   │   ├── database.py            # MongoDB singleton connection
│   │   └── logger.py              # Structured logging setup
│   │
│   ├── models/
│   │   ├── schemas.py             # Pydantic models (RunResponse, AgentRequest, etc.)
│   │   └── conversation_schemas.py
│   │
│   ├── services/
│   │   ├── conversation_manager.py  # Chat orchestration & state machine
│   │   ├── llm_service.py           # Gemini API integration
│   │   ├── llm_generator.py         # Terraform code generation (4 providers)
│   │   ├── github_service.py        # GitHub API client (public + private repos)
│   │   ├── workflow_engine.py       # Terraform lifecycle (plan/apply/destroy)
│   │   ├── run_manager.py           # Run state & workspace management
│   │   ├── user_service.py          # MongoDB user upsert (auth sync)
│   │   ├── email_service.py         # SMTP approval emails
│   │   ├── langfuse_service.py      # langfuse integration
│   │   ├── workspace_manager.py   
│   │   └── service_templates.py     # Provider-specific Terraform snippets
│   │
│   └── main.py                      # FastAPI application & all routes
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── WelcomePage.jsx      # New chat form (owner, repo, token, branch)
│   │   │   └── WorkspacePage.jsx    # Chat + File Review (edit) + Lifecycle tabs
│   │   ├── components/
│   │   │   ├── common/              # Button, Card, Input, Badge
│   │   │   ├── features/chat/       # ChatPanel, ChatMessage, CodeEditor, CodeViewer
│   │   │   └── layout/              # Sidebar
│   │   ├── services/
│   │   │   ├── api.js               # Re-exports from client.js
│   │   │   ├── client.js            # Axios instance + all API methods
│   │   │   ├── auth.js              # Firebase REST + Google OAuth
│   │   │   └── firebase.js          # Firebase app initialization
│   │   ├── hooks/                   # useAuth, useSession
│   │   ├── App.jsx                  # Root component & routing
│   │   └── Login.jsx                # Email/password + Google sign-in
│   └── package.json
│
├── runs/                            # Isolated Terraform workspaces per run
│   └── run_YYYYMMDD_HHMMSS/
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       ├── deploy.yml
│       └── state.json
│
├── logs/                            # Application logs
├── requirements.txt
└── .env                             # Environment variables (not committed)

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

- Ensure `FIREBASE_PROJECT_ID` and `FIREBASE_CREDENTIALS_PATH` are set correctly
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

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

**Built with [FastAPI](https://fastapi.tiangolo.com/) · [React](https://react.dev/) · [Google Gemini](https://ai.google.dev/) · [Terraform](https://www.terraform.io/) · [Firebase](https://firebase.google.com/) · [MongoDB](https://www.mongodb.com/)**
