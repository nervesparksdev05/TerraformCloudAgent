# AWS EC2 & GCP Compute Terraform Agent

An LLM-powered Terraform agent that generates secure, production-ready infrastructure code for **AWS EC2** and **GCP Compute Engine** instances with predefined IAM roles.

## 🎯 Overview

This agent converts natural language requests into validated Terraform configurations, focusing exclusively on:

- **AWS EC2** - Complete EC2 instance management with networking and load balancing
- **GCP Compute Engine** - Complete Compute instance management with networking and load balancing
- **10 AWS IAM Role Types** - Predefined secure role patterns for common use cases

## ✨ Features

- 🤖 **LLM-Powered Generation** - Natural language to Terraform using OpenAI/Gemini
- 🔒 **Security-First** - Strict validation, no provisioners, least-privilege IAM
- ☁️ **Multi-Cloud** - AWS EC2 and GCP Compute Engine support
- 📦 **Complete Workflows** - `terraform init`, `plan`, `apply` automation
- 🎭 **10 IAM Role Types** - Predefined secure patterns (S3, SSM, CloudWatch, Secrets Manager, etc.)
- 📊 **Workspace Isolation** - Each run in isolated directory
- 📝 **Comprehensive Logging** - Full execution logs and outputs

## 🚀 Quick Start

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

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-openai-api-key"
export AWS_REGION="us-east-1"
export GCP_PROJECT_ID="your-gcp-project"
export GCP_REGION="us-central1"

# Start the server
python -m app.main
```

The API will be available at `http://localhost:8000`

## 📖 Usage

### AWS EC2 Example

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Create a web server on port 80 and 443 with CloudWatch logging",
    "provider": "aws"
  }'
```

**Response**:
```json
{
  "run_id": "run_20260209_125000_abc123",
  "status": "ok",
  "provider": "aws",
  "log_path": "runs/run_20260209_125000_abc123",
  "outputs": {
    "instance_id": "i-0123456789abcdef",
    "public_ip": "54.123.45.67",
    "iam_role_arn": "arn:aws:iam::123456789012:role/ec2-cloudwatch-logs"
  }
}
```

### GCP Compute Example

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "request": "Create a VM instance with HTTP access",
    "provider": "gcp"
  }'
```

**Response**:
```json
{
  "run_id": "run_20260209_125100_xyz789",
  "status": "ok",
  "provider": "gcp",
  "log_path": "runs/run_20260209_125100_xyz789",
  "outputs": {
    "instance_id": "1234567890123456789",
    "instance_ip": "35.123.45.67",
    "service_account_email": "app-sa@project.iam.gserviceaccount.com"
  }
}
```

## 🔐 10 AWS IAM Role Types

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

📚 **[View detailed IAM role documentation →](docs/IAM_ROLES.md)**

## 🛠️ Supported Resources

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

## 🔒 Security Constraints

### Prohibited (Will Reject)
- ❌ Provisioners (`local-exec`, `remote-exec`, `file`)
- ❌ `null_resource` or `external` data sources
- ❌ Hardcoded credentials (AWS keys, passwords, secrets)
- ❌ Unsupported services (Lambda, S3, RDS, DynamoDB, Cloud Functions, Cloud Storage, etc.)

### Required Security Practices
- ✅ Variables for all sensitive data
- ✅ Least-privilege IAM policies
- ✅ Restrictive security groups (never 0.0.0.0/0 for SSH)
- ✅ One of the 10 predefined IAM role types (AWS)
- ✅ Encryption in transit (SSL/TLS)

## 📁 Project Structure

```
TerraformCloudAgent/
├── app/
│   ├── core/              # Configuration, logging, database
│   ├── models/            # Pydantic schemas
│   ├── prompts/           # LLM system prompts
│   │   ├── aws_focused_system_prompt.txt
│   │   └── gcp_focused_system_prompt.txt
│   ├── services/          # Business logic
│   │   ├── llm_generator.py        # OpenAI/Gemini integration
│   │   ├── security_checker.py     # Security validation
│   │   ├── terraform_runner.py     # Terraform execution
│   │   └── workspace_manager.py    # Workspace isolation
│   └── main.py            # FastAPI application
├── docs/
│   └── IAM_ROLES.md       # IAM role documentation
├── runs/                  # Isolated run workspaces
├── logs/                  # Application logs
└── requirements.txt       # Python dependencies
```

## 🌐 API Reference

### POST /runs

Create and execute a Terraform run.

**Request Body**:
```json
{
  "request": "Natural language infrastructure request",
  "provider": "aws" | "gcp",
  "auto_approve": false
}
```

**Response**:
```json
{
  "run_id": "run_20260209_125000_abc123",
  "status": "ok" | "error",
  "provider": "aws" | "gcp",
  "log_path": "runs/run_20260209_125000_abc123",
  "outputs": {
    "instance_id": "...",
    "public_ip": "..."
  },
  "error": "Error message (if status is error)"
}
```

## 📊 Example Requests

### AWS Examples

```bash
# Simple web server
"Create a web server on port 80 and 443"

# Web server with IAM role
"Create an EC2 instance that can write logs to CloudWatch"

# Auto-scaling web application
"Create auto-scaling web servers with load balancer"

# Bastion host
"Create a bastion host with SSM access"

# Container host
"Create EC2 instance for Docker containers with ECR access"
```

### GCP Examples

```bash
# Simple VM
"Create a VM instance with HTTP access"

# Multi-instance deployment
"Deploy 3 web servers with load balancer"

# Auto-scaling application
"Create auto-scaling Compute instances"

# Private instance
"Create instance in private subnet with Cloud NAT"
```

## 🧪 Testing

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

## ⚙️ Configuration

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...                    # OpenAI API key
AWS_REGION=us-east-1                     # AWS region
GCP_PROJECT_ID=my-project                # GCP project ID
GCP_REGION=us-central1                   # GCP region

# Optional
HOST=0.0.0.0                             # Server host (default: 0.0.0.0)
PORT=8000                                # Server port (default: 8000)
DEBUG=false                              # Debug mode (default: false)
WORKSPACE_BASE_DIR=./runs                # Workspace directory (default: ./runs)
LOGS_DIR=./logs                          # Logs directory (default: ./logs)
```

## 🐛 Troubleshooting

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

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📞 Support

For issues, questions, or feature requests, please open an issue on GitHub.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- LLM integration via [OpenAI](https://openai.com/) and [Google Gemini](https://ai.google.dev/)
- Infrastructure as Code with [Terraform](https://www.terraform.io/)
