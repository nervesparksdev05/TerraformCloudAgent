# Terraform Agent - Streamlit Frontend

A conversational interface for deploying multi-cloud infrastructure with Terraform (AWS, GCP, Azure, DigitalOcean).

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
- Stage 1: workload type, workload description, cloud provider, region, environment
- Stage 2: instance count, instance type, operating system
- Stage 3: storage size and storage type
- Stage 4: ports, SSH CIDRs, load balancer type
- Stage 5: IAM services/actions and IAM role name
- Stage 6: monitoring, detailed monitoring, autoscaling, backups, log retention

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
