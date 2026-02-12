# Multi-Cloud Terraform Agent

An intelligent conversational agent that generates secure, production-ready Terraform infrastructure through natural language interactions. Built with FastAPI backend and Streamlit frontend for AWS EC2, GCP Compute Engine, Azure Virtual Machines, and DigitalOcean Droplets.

## ðŸŽ¯ Overview

This agent provides a conversational interface to design and deploy cloud infrastructure, focusing on:

- **AWS EC2** - Complete EC2 instance management with networking, load balancing, and IAM
- **GCP Compute Engine** - Complete Compute instance management with networking and load balancing
- **Azure Virtual Machines** - VM deployment with cloud-native defaults
- **DigitalOcean Droplets** - Droplet deployment with equivalent VM workflow
- **10 AWS IAM Role Types** - Predefined secure role patterns for common use cases
- **Conversational UX** - Chat-based infrastructure design with guided workflows

## âœ¨ Features

- ðŸ’¬ **Conversational Interface** - Chat with an AI assistant to define infrastructure requirements
- ðŸ¤– **LLM-Powered Generation** - Structured requests to Terraform using OpenAI/Gemini
- ðŸ”’ **Security-First** - Strict validation, no provisioners, least-privilege IAM
- â˜ï¸ **Multi-Cloud** - AWS, GCP, Azure, and DigitalOcean support
- âš¡ **Async Workflows** - Background execution with real-time status updates
- ðŸ“¦ **Complete Terraform Lifecycle** - `init`, `plan`, `apply`, `destroy` automation
- ðŸŽ­ **10 IAM Role Types** - Predefined secure patterns (S3, SSM, CloudWatch, Secrets Manager, etc.)
- ðŸ“Š **Workspace Isolation** - Each run in isolated directory with full state management
- ðŸ“ **Comprehensive Logging** - Full execution logs and outputs
- ðŸŽ¨ **Streamlit Frontend** - Beautiful, interactive UI for infrastructure management

## ðŸš€ Quick Start

### Prerequisites

- Python 3.11+
- Terraform 1.0+
- AWS CLI configured (for AWS deployments)
- GCP SDK configured (for GCP deployments)
- OpenAI API key or Google Gemini API key

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd TerraformCloudAgent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-openai-api-key"
export AWS_REGION="us-east-1"
export GCP_PROJECT_ID="your-gcp-project"
export GCP_REGION="us-central1"

# Optional: Configure MongoDB (default: local)
export MONGODB_URI="mongodb://localhost:27017/terraform_agent"

# Start the backend server
python -m app.main
```

The backend API will be available at `http://localhost:8000`

### Running the Frontend

```bash
# In a new terminal, from the project root
cd frontend
streamlit run app.py
```

The Streamlit UI will open at `http://localhost:8501`

## ðŸ“– Usage

### Option 1: Streamlit Frontend (Recommended)

1. **Start a Conversation**: Click "Start Conversation" in the sidebar
2. **Chat with the Bot**: Answer questions about your infrastructure:
   - Workload type (web server, API, database, etc.)
   - Instance configuration (count, type, region)
   - Network settings (VPC, subnets, ports)
   - IAM permissions (CloudWatch, S3, SSM, etc.)
   - Additional features (monitoring, auto-scaling)
3. **Generate Terraform**: Click "Generate Terraform Configuration"
4. **Review & Deploy**: Review files, approve to deploy, or edit and regenerate
5. **Manage Infrastructure**: Monitor status, view outputs, destroy when done

### Option 2: Direct API Usage

The backend accepts structured requests with detailed parameters:

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "request": {
      "terraform_resource_type": "aws_instance",
      "cloud_provider": "aws",
      "instance_count": 2,
      "instance_type": "t3.micro",
      "region": "us-east-1",
      "ports": [
        {"port": 80, "protocol": "tcp", "source_cidr": "0.0.0.0/0"},
        {"port": 443, "protocol": "tcp", "source_cidr": "0.0.0.0/0"}
      ],
      "iam_services": {
        "cloudwatch": ["logs:CreateLogGroup", "logs:PutLogEvents"]
      },
      "monitoring_enabled": true
    },
    "provider": "aws",
    "auto_approve": false
  }'
```

**Response**:
```json
{
  "run_id": "run_20260211_095418",
  "status": "PLANNED",
  "provider": "aws",
  "workspace_path": "runs/run_20260211_095418",
  "plan_output": "Terraform files generated successfully..."
}
```

**Check Status**:
```bash
curl http://localhost:8000/runs/run_20260211_095418
```

**Approve & Deploy**:
```bash
curl -X POST http://localhost:8000/runs/run_20260211_095418/approve
```

## ðŸ” 10 AWS IAM Role Types

The agent supports 10 predefined IAM role patterns following AWS least-privilege principles:

| # | Role Type | Use Case | Example Request |
|---|-----------|----------|-----------------|
| 1 | **EC2 Basic** | Minimal EC2 permissions | "Create EC2 with basic permissions" |
| 2 | **EC2 S3 Access** | Read/write to S3 buckets | "Create EC2 that can access S3" |
| 3 | **EC2 SSM Managed** | Systems Manager access | "Create EC2 with SSM access" |
| 4 | **EC2 CloudWatch Logs** | Write logs to CloudWatch | "Create EC2 that writes logs" |
| 5 | **EC2 Secrets Manager** | Read secrets | "Create EC2 that reads secrets" |
| 6 | **Lambda Execution** | Lambda for EC2 automation | "Create Lambda execution role" |
| 7 | **Cross-Account Access** | Assume role from another account | "Create cross-account role" |
| 8 | **EC2 ECR** | Pull Docker images from ECR | "Create EC2 with ECR access" |
| 9 | **EC2 DynamoDB** | DynamoDB read/write | "Create EC2 with DynamoDB access" |
| 10 | **EC2 RDS** | RDS IAM authentication | "Create EC2 with RDS access" |

ðŸ“š **[View detailed IAM role documentation â†’](docs/IAM_ROLES.md)**

## ðŸ› ï¸ Supported Resources

### AWS Resources

**EC2 Compute**:
- `aws_instance`, `aws_key_pair`, `aws_eip`, `aws_eip_association`
- `aws_launch_template`, `aws_autoscaling_group`, `aws_autoscaling_policy`

**Networking**:
- `aws_vpc`, `aws_subnet`, `aws_route_table`, `aws_internet_gateway`, `aws_nat_gateway`
- `aws_security_group`, `aws_security_group_rule`

**Load Balancing**:
- `aws_lb`, `aws_lb_listener`, `aws_lb_target_group`, `aws_lb_target_group_attachment`

**IAM**:
- `aws_iam_role`, `aws_iam_policy`, `aws_iam_role_policy_attachment`, `aws_iam_instance_profile`

### GCP Resources

**Compute Engine**:
- `google_compute_instance`, `google_compute_instance_template`
- `google_compute_instance_group`, `google_compute_instance_group_manager`
- `google_compute_disk`, `google_compute_autoscaler`

**Networking**:
- `google_compute_network`, `google_compute_subnetwork`, `google_compute_firewall`
- `google_compute_router`, `google_compute_router_nat`, `google_compute_address`

**Load Balancing**:
- `google_compute_backend_service`, `google_compute_url_map`
- `google_compute_target_http_proxy`, `google_compute_forwarding_rule`, `google_compute_health_check`

**IAM**:
- `google_service_account`, `google_project_iam_member`, `google_compute_instance_iam_member`

## ðŸ”’ Security Constraints

### Prohibited (Will Reject)
- âŒ Provisioners (`local-exec`, `remote-exec`, `file`)
- âŒ `null_resource` or `external` data sources
- âŒ Hardcoded credentials (AWS keys, passwords, secrets)
- âŒ Unsupported services (Lambda, S3, RDS, DynamoDB, Cloud Functions, Cloud Storage, etc.)

### Required Security Practices
- âœ… Variables for all sensitive data
- âœ… Least-privilege IAM policies
- âœ… Restrictive security groups (never 0.0.0.0/0 for SSH)
- âœ… One of the 10 predefined IAM role types (AWS)
- âœ… Encryption in transit (SSL/TLS)

## ðŸ“ Project Structure

```
TerraformCloudAgent/
â”œâ”€â”€ app/
â”‚   â”œâ”€â”€ core/              # Configuration, logging, database
â”‚   â”‚   â”œâ”€â”€ config.py              # Environment configuration
â”‚   â”‚   â”œâ”€â”€ logger.py              # Logging setup
â”‚   â”‚   â””â”€â”€ database.py            # MongoDB connection
â”‚   â”œâ”€â”€ models/            # Pydantic schemas
â”‚   â”‚   â””â”€â”€ schemas.py             # Request/response models
â”‚   â”œâ”€â”€ prompts/           # LLM system prompts
â”‚   â”‚   â”œâ”€â”€ aws_focused_system_prompt.txt
â”‚   â”‚   â””â”€â”€ gcp_focused_system_prompt.txt
â”‚   â”œâ”€â”€ services/          # Business logic
â”‚   â”‚   â”œâ”€â”€ llm_generator.py       # OpenAI/Gemini integration
â”‚   â”‚   â”œâ”€â”€ security.py            # Security validation
â”‚   â”‚   â”œâ”€â”€ workflow_engine.py     # Async workflow orchestration
â”‚   â”‚   â”œâ”€â”€ run_manager.py         # Run state management
â”‚   â”‚   â”œâ”€â”€ workspace_manager.py   # Workspace isolation
â”‚   â”‚   â””â”€â”€ conversation_manager.py # Chat flow management
â”‚   â”œâ”€â”€ routers/           # API endpoints
â”‚   â”‚   â”œâ”€â”€ runs.py                # Terraform run endpoints
â”‚   â”‚   â””â”€â”€ conversations.py       # Chat endpoints
â”‚   â””â”€â”€ main.py            # FastAPI application
â”œâ”€â”€ frontend/              # Streamlit UI
â”‚   â”œâ”€â”€ app.py                     # Main Streamlit app
â”‚   â”œâ”€â”€ api_client.py              # Backend API client
â”‚   â””â”€â”€ components/                # Reusable UI components
â”œâ”€â”€ runs/                  # Isolated run workspaces
â”œâ”€â”€ logs/                  # Application logs
â””â”€â”€ requirements.txt       # Python dependencies
```

## ðŸŒ API Reference

### Conversation Endpoints

#### POST /conversations
Start a new conversation

**Response**: `{"conversation_id": "...", "message": "..."}`

#### POST /conversations/{id}/message
Send a message in the conversation

**Request**: `{"message": "I need a web server"}`

**Response**: `{"response": "...", "state": "collecting_params", "collected_params": {...}}`

#### POST /conversations/{id}/generate
Generate Terraform from collected parameters

**Response**: `{"run_id": "...", "status": "PLANNING"}`

---

### Run Endpoints

#### POST /runs
Create a Terraform run (direct API, bypasses conversation)

**Request Body**:
```json
{
  "request": {
    "terraform_resource_type": "aws_instance",
    "cloud_provider": "aws",
    "instance_count": 2,
    "instance_type": "t3.micro",
    "region": "us-east-1",
    "ports": [{"port": 80, "protocol": "tcp", "source_cidr": "0.0.0.0/0"}],
    "iam_services": {"cloudwatch": ["logs:PutLogEvents"]}
  },
  "provider": "aws",
  "auto_approve": false
}
```

**Response**:
```json
{
  "run_id": "run_20260211_095418",
  "status": "PLANNED",
  "provider": "aws",
  "workspace_path": "runs/run_20260211_095418",
  "plan_output": "..."
}
```

#### GET /runs/{run_id}
Get run status and details

**Response**: `{"run_id": "...", "status": "PLANNED", "outputs": {...}}`

#### POST /runs/{run_id}/approve
Approve and deploy the Terraform plan (async)

**Response**: `{"message": "Apply started", "status": "APPLYING"}`

#### POST /runs/{run_id}/destroy
Destroy deployed infrastructure (async)

**Response**: `{"message": "Destroy started", "status": "DESTROYING"}`

#### GET /runs/{run_id}/files
Retrieve generated Terraform files

**Response**: `{"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}`

#### POST /runs/{run_id}/refine
Refine Terraform based on feedback

**Request**: `{"feedback": "Add HTTPS support"}`

**Response**: `{"message": "Refinement started", "status": "PLANNING"}`

---

### Run Status Values

- `CREATED` - Run initialized
- `PLANNING` - Generating Terraform files
- `PLANNED` - Files ready for review
- `APPROVED` - User approved, ready to apply
- `APPLYING` - Deploying infrastructure
- `COMPLETED` - Successfully deployed
- `DESTROYING` - Destroying infrastructure
- `DESTROYED` - Infrastructure destroyed
- `FAILED` - Error occurred

## ðŸ’¬ Conversation Examples

The Streamlit frontend guides you through a natural conversation:

**User**: "I need to deploy a web application"

**Bot**: "Great! Let me help you set that up. What type of workload is this? (web_server, api_server, database, etc.)"

**User**: "web_server"

**Bot**: "Perfect. How many instances do you need?"

**User**: "2"

**Bot**: "What instance type would you like? (e.g., t3.micro, t3.small, t3.medium)"

...and so on until all parameters are collected.

---

## ðŸ“Š Direct API Request Examples

### AWS Web Server with CloudWatch

```json
{
  "request": {
    "terraform_resource_type": "aws_instance",
    "cloud_provider": "aws",
    "service_type": "web_server",
    "instance_count": 2,
    "instance_type": "t3.micro",
    "region": "us-east-1",
    "ports": [
      {"port": 80, "protocol": "tcp", "source_cidr": "0.0.0.0/0"},
      {"port": 443, "protocol": "tcp", "source_cidr": "0.0.0.0/0"}
    ],
    "iam_services": {
      "cloudwatch": ["logs:CreateLogGroup", "logs:PutLogEvents"]
    },
    "monitoring_enabled": true
  },
  "provider": "aws"
}
```

### GCP Compute with Load Balancer

```json
{
  "request": {
    "terraform_resource_type": "google_compute_instance",
    "cloud_provider": "gcp",
    "instance_count": 3,
    "machine_type": "e2-medium",
    "region": "us-central1",
    "load_balancer_type": "http",
    "enable_https": true
  },
  "provider": "gcp"
}
```

## ðŸ§ª Testing

### Manual Testing

```bash
# Test AWS EC2 creation
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"request": "Create a web server", "provider": "aws"}'

# Test GCP Compute creation
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"request": "Create a VM instance", "provider": "gcp"}'

# Verify generated files
cd runs/<run_id>
cat main.tf
cat variables.tf
cat outputs.tf
```

### Automated Tests

```bash
# Run security checker tests
python -m pytest tests/test_security_checker.py -v

# Run LLM generator tests
python -m pytest tests/test_llm_generator.py -v
```

## âš™ï¸ Configuration

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...                    # OpenAI API key
AWS_REGION=us-east-1                     # AWS region
GCP_PROJECT_ID=my-project                # GCP project ID
GCP_REGION=us-central1                   # GCP region

# Optional - LLM
OPENAI_MODEL=gpt-4                       # OpenAI model (default: gpt-4)
OPENAI_TEMPERATURE=0.7                   # Temperature (default: 0.7)
GOOGLE_API_KEY=...                       # Gemini fallback key
GEMINI_MODEL=gemini-1.5-pro              # Gemini model

# Optional - Database
MONGODB_URI=mongodb://localhost:27017/terraform_agent
MONGODB_DATABASE=terraform_agent

# Optional - Observability
LANGFUSE_PUBLIC_KEY=...                  # Langfuse tracing
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com

# Optional - Server
HOST=0.0.0.0                             # Server host (default: 0.0.0.0)
PORT=8000                                # Server port (default: 8000)
DEBUG=false                              # Debug mode (default: false)
WORKSPACE_BASE_DIR=./runs                # Workspace directory (default: ./runs)
LOGS_DIR=./logs                          # Logs directory (default: ./logs)
TERRAFORM_TIMEOUT=300                    # Terraform timeout in seconds
```

## ðŸ› Troubleshooting

### Common Issues

**"Resource type not allowed" error**:
- The agent only supports EC2/Compute resources
- Check that you're not requesting Lambda, S3, RDS, Cloud Functions, Cloud Storage, etc.

**"Security validation failed" error**:
- Review the security constraints
- Ensure no hardcoded credentials
- Check that IAM policies follow least-privilege

**"Terraform execution failed" error**:
- Check AWS/GCP credentials are configured
- Verify Terraform is installed and in PATH
- Review the run logs in `runs/<run_id>/terraform.log`

## ðŸ“ License

MIT License - see LICENSE file for details

## ðŸ¤ Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## ðŸ“ž Support

For issues, questions, or feature requests, please open an issue on GitHub.

## ðŸ™ Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- LLM integration via [OpenAI](https://openai.com/) and [Google Gemini](https://ai.google.dev/)
- Infrastructure as Code with [Terraform](https://www.terraform.io/)
