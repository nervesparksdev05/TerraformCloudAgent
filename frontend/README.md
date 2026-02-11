# Terraform Agent - Streamlit Frontend

A conversational interface for deploying AWS infrastructure with Terraform.

## Features

- **💬 Conversational Deployment**: Chat with an AI assistant to define your infrastructure
- **📄 Terraform Review**: Review and edit generated Terraform configurations
- **⚙️ Deployment Management**: Approve, deploy, and destroy infrastructure
- **🔒 Production-Ready**: Built-in security validation and best practices

## Running the Frontend

### Prerequisites

1. Backend server running on `http://localhost:8000`
2. Python 3.11+ with dependencies installed

### Start the Frontend

```bash
# From the frontend directory
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`.

## Usage

### 1. Start a Conversation

Click "Start Conversation" in the sidebar to begin.

### 2. Chat with the Bot

Answer the bot's questions about your infrastructure needs:
- Workload type (web server, API, database, etc.)
- Instance configuration (count, type, region)
- Network and security settings (ports, security groups)
- IAM permissions (custom roles based on your needs)
- Additional features (monitoring, auto-scaling, etc.)

### 3. Generate Terraform

Once all parameters are collected, click "Generate Terraform Configuration".

### 4. Review & Deploy

- Review the generated Terraform files
- Approve to deploy or reject to start over
- Manage and destroy infrastructure as needed

## Architecture

```
frontend/
├── app.py              # Main Streamlit application
├── api_client.py       # Backend API client
├── components/         # Reusable UI components
└── README.md          # This file
```

## API Endpoints Used

- `POST /conversations` - Start new conversation
- `POST /conversations/{id}/message` - Send message
- `GET /conversations/{id}` - Get conversation state
- `POST /conversations/{id}/generate` - Generate Terraform
- `GET /runs/{id}` - Get run status
- `GET /runs/{id}/files` - Get Terraform files
- `POST /runs/{id}/approve` - Deploy infrastructure
- `POST /runs/{id}/destroy` - Destroy infrastructure

## Configuration

The frontend connects to the backend at `http://localhost:8000` by default. To change this, modify the `get_api_client()` function in `app.py`.
