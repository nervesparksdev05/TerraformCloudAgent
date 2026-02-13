"""LLM Terraform Generator — Uses rich conversation params for production EC2 code."""
from __future__ import annotations

import json
from typing import Any, Dict

from app.services.llm_service import LLMService

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class LLMGenerator:
    """Generate production-grade Terraform code from structured conversation parameters.
    
    Supports: AWS EC2, GCP Compute Engine, Azure VMs, DigitalOcean Droplets.
    """

    SYSTEM_PROMPT = """\
You are an expert Terraform code generator for multi-cloud infrastructure (AWS, GCP, Azure, DigitalOcean).

OUTPUT FORMAT — Return ONLY valid JSON with exactly these 3 keys:
{
  "main_tf": "complete main.tf HCL content with \\n newlines",
  "variables_tf": "complete variables.tf HCL content with \\n newlines",
  "outputs_tf": "complete outputs.tf HCL content with \\n newlines"
}

FORMATTING (CRITICAL):
- Each HCL block on separate lines using \\n
- 2-space indentation per nesting level
- Blank line (\\n\\n) between resource blocks
- Properly escaped quotes: \\"

═══════════════════════════════════════════════════════════════
REQUIRED BLOCKS IN main.tf (IN THIS ORDER)
═══════════════════════════════════════════════════════════════

1. TERRAFORM & PROVIDER BLOCKS (always include):
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
    tls = { source = "hashicorp/tls", version = "~> 4.0" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Environment = var.environment
      Project     = var.project_name
      ManagedBy   = "terraform"
    }
  }
}

2. DATA SOURCES (always include these):
# Find latest AMI
data "aws_ami" "selected" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical for Ubuntu, "amazon" for Amazon Linux

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]  # Adjust based on ami_os param
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Get available AZs
data "aws_availability_zones" "available" {
  state = "available"
}

# IAM policy document for instance role
data "aws_iam_policy_document" "instance_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# IAM policy for instance permissions
data "aws_iam_policy_document" "instance_policy" {
  # CloudWatch logs (always include)
  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "cloudwatch:PutMetricData"
    ]
    resources = ["*"]
  }

  # SSM (always include)
  statement {
    actions = [
      "ssm:UpdateInstanceInformation",
      "ssm:GetParameter",
      "ssm:GetParameters"
    ]
    resources = ["*"]
  }

  # Add additional service permissions based on user's iam_services parameter
}

3. TLS PRIVATE KEY (for SSH access):
resource "tls_private_key" "instance_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "instance_key" {
  key_name   = "${var.project_name}-${var.environment}-key"
  public_key = tls_private_key.instance_key.public_key_openssh
}

4. VPC & NETWORKING:
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "${var.project_name}-${var.environment}-vpc" }
}

resource "aws_subnet" "public" {
  count                   = var.subnet_count
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = element(data.aws_availability_zones.available.names, count.index)
  map_public_ip_on_launch = true
  tags = { Name = "${var.project_name}-${var.environment}-public-${count.index + 1}" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project_name}-${var.environment}-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${var.project_name}-${var.environment}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = var.subnet_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

5. SECURITY GROUP:
resource "aws_security_group" "instance" {
  vpc_id = aws_vpc.main.id
  name   = "${var.project_name}-${var.environment}-instance-sg"

  # Add ingress rules from ports parameter
  # Example: port 80, 443 from 0.0.0.0/0; port 22 from ssh_allowed_cidrs

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

6. IAM ROLE & INSTANCE PROFILE:
resource "aws_iam_role" "instance" {
  name               = "${var.project_name}-${var.environment}-instance-role"
  assume_role_policy = data.aws_iam_policy_document.instance_assume_role.json
}

resource "aws_iam_role_policy" "instance" {
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance_policy.json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.project_name}-${var.environment}-instance-profile"
  role = aws_iam_role.instance.name
}

7. EC2 INSTANCES:
resource "aws_instance" "main" {
  count                = var.instance_count
  ami                  = data.aws_ami.selected.id
  instance_type        = var.instance_type
  key_name             = aws_key_pair.instance_key.key_name
  subnet_id            = element(aws_subnet.public[*].id, count.index)
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile = aws_iam_instance_profile.instance.name

  root_block_device {
    volume_size           = var.storage_size_gb
    volume_type           = var.storage_type
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  tags = { Name = "${var.project_name}-${var.environment}-${count.index + 1}" }
}

8. LOAD BALANCER (if load_balancer_type != "none"):
# Add ALB/NLB resources if requested

═══════════════════════════════════════════════════════════════
VARIABLES.TF MUST INCLUDE
═══════════════════════════════════════════════════════════════

variable "aws_region" {
  type    = string
  default = "<from params>"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod"
  }
}

variable "project_name" {
  type    = string
  default = "<infer from workload_description or use 'app'>"
}

variable "instance_type" { type = string }
variable "instance_count" { type = number }
variable "storage_size_gb" { type = number }
variable "storage_type" { type = string }
variable "vpc_cidr" { type = string }
variable "subnet_count" { type = number }

variable "ssh_allowed_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to SSH"
}

═══════════════════════════════════════════════════════════════
OUTPUTS.TF MUST INCLUDE
═══════════════════════════════════════════════════════════════

output "instance_ids" {
  value = aws_instance.main[*].id
}

output "public_ips" {
  value = aws_instance.main[*].public_ip
}

output "private_ips" {
  value = aws_instance.main[*].private_ip
}

output "ssh_private_key" {
  value     = tls_private_key.instance_key.private_key_pem
  sensitive = true
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "security_group_id" {
  value = aws_security_group.instance.id
}

output "iam_role_arn" {
  value = aws_iam_role.instance.arn
}

═══════════════════════════════════════════════════════════════
CRITICAL RULES
═══════════════════════════════════════════════════════════════

✅ MUST INCLUDE:
- All data sources (aws_ami, aws_availability_zones, aws_iam_policy_document)
- TLS private key resource
- IAM role, policy, instance profile
- VPC with internet gateway and route table
- Security group with user-specified ports
- EC2 instances with encryption, IMDSv2, IAM profile

❌ NEVER:
- Hardcode AMI IDs (use data.aws_ami)
- Hardcode credentials
- Allow 0.0.0.0/0 for SSH
- Reference non-existent data sources
- Forget to define resources you reference in outputs

🎯 VALIDATION:
- Every resource referenced in outputs MUST be defined in main.tf
- Every variable in main.tf MUST be defined in variables.tf
- Code MUST pass `terraform validate`
"""

    def __init__(self) -> None:
        # LLMService handles provider selection, no need to enforce OPENAI_API_KEY here
        self.llm_service = LLMService()
        logger.info("LLMGenerator initialized with LLMService")

    def generate_terraform(
        self, params: Dict[str, Any], provider: str = "aws"
    ) -> TerraformBundle:
        """Generate Terraform from structured conversation parameters."""
        prompt = self._build_prompt(params, provider)
        return self._call(prompt, self.SYSTEM_PROMPT)

    def refine_terraform(
        self,
        base_request: str,
        current_code: Dict[str, Any],
        feedback: str,
        provider: str = "aws",
    ) -> TerraformBundle:
        """Refine existing Terraform based on user feedback."""
        prompt = (
            f"Original request: {base_request}\n"
            f"User feedback: {feedback}\n"
            f"Current code:\n{json.dumps(current_code, indent=2)}\n\n"
            f"Apply the feedback and return updated JSON with main_tf, variables_tf, outputs_tf."
        )
        return self._call(prompt, self.SYSTEM_PROMPT)

    def _build_prompt(self, params: Dict[str, Any], provider: str) -> str:
        """Build a rich, structured prompt from ALL conversation parameters."""
        p = params  # shorthand
        provider_norm = (p.get("cloud_provider") or provider or "aws").lower()
        provider_display = {
            "aws": "AWS EC2",
            "gcp": "GCP Compute Engine",
            "azure": "Azure Virtual Machines",
            "digitalocean": "DigitalOcean Droplets",
        }.get(provider_norm, "AWS EC2")
        default_region = {
            "aws": "us-east-1",
            "gcp": "us-central1",
            "azure": "eastus",
            "digitalocean": "nyc1",
        }.get(provider_norm, "us-east-1")
        default_instance = {
            "aws": "t3.micro",
            "gcp": "e2-micro",
            "azure": "B1s",
            "digitalocean": "basic-1vCPU-1GB",
        }.get(provider_norm, "t3.micro")

        # Format ports for readability
        ports_desc = ""
        for port_entry in p.get("ports", []):
            if isinstance(port_entry, dict):
                ports_desc += (
                    f"  - Port {port_entry.get('port')}/{port_entry.get('protocol', 'tcp')} "
                    f"from {port_entry.get('source_cidr', '0.0.0.0/0')} "
                    f"({port_entry.get('description', '')})\n"
                )

        # Format IAM services
        iam_desc = ""
        for svc, actions in p.get("iam_services", {}).items():
            iam_desc += f"  - {svc}: {', '.join(actions)}\n"

        # Auto-scaling config
        asg_desc = "Not enabled"
        if p.get("auto_scaling_enabled") and p.get("auto_scaling_config"):
            asc = p["auto_scaling_config"]
            asg_desc = f"min={asc.get('min', 1)}, max={asc.get('max', 4)}, target_cpu={asc.get('target_cpu', 70)}%"

        ssh_cidrs = ", ".join(p.get("ssh_allowed_cidrs", ["10.0.0.0/8"]))

        # Pre-compute fallbacks (Python 3.11 doesn't allow \ in f-string braces)
        default_ports = (
            "  - Port 80/tcp from 0.0.0.0/0 (HTTP)\n"
            "  - Port 443/tcp from 0.0.0.0/0 (HTTPS)\n"
        )
        default_iam = (
            "  - cloudwatch: basic logging\n"
            "  - ssm: instance management\n"
        )
        ports_section = ports_desc if ports_desc else default_ports
        iam_section = iam_desc if iam_desc else default_iam

        prompt = f"""Generate production-grade Terraform configuration for {provider_display}.

WORKLOAD: {p.get('workload_description', p.get('service_type', 'web server'))}
ENVIRONMENT: {p.get('environment', 'dev')}

COMPUTE:
  Instance type: {p.get('instance_type', default_instance)}
  Instance count: {p.get('instance_count', 1)}
  Region: {p.get('region', default_region)}
  OS: {p.get('os_image', 'ubuntu-22.04')} (use data "aws_ami" to find latest)

STORAGE:
  Root volume: {p.get('storage_size_gb', p.get('storage_size', 20))} GB {p.get('storage_type', 'gp3')}
  Encrypted: true (always)

NETWORKING:
  VPC CIDR: {p.get('vpc_cidr', '10.0.0.0/16')}
  Subnet type: {p.get('subnet_type', 'both')} (public + private)
  Subnet count: {p.get('subnet_count', 2)} AZs (use data "aws_availability_zones")
  Public IP: {p.get('enable_public_ip', True)}
  Load balancer: {p.get('load_balancer_type', 'none')}
  HTTPS: {p.get('enable_https', False)}

SECURITY GROUP PORTS:
{ports_section}  SSH allowed CIDRs: {ssh_cidrs}

IAM ROLE ({p.get('iam_role_name', 'app-role')}):
{iam_section}  Create custom IAM role with data "aws_iam_policy_document".
  Attach as instance profile.

MONITORING:
  Detailed monitoring: {p.get('detailed_monitoring', False)}
  CloudWatch logs: {p.get('cloudwatch_logs_enabled', True)}
  Log retention: {p.get('log_retention_days', 30)} days
  CloudWatch log group for application logs

AUTO-SCALING: {asg_desc}

SECURITY HARDENING:
  IMDSv2: required (http_tokens = "required")
  SSH key: generate via tls_private_key + aws_key_pair
  EBS encryption: enabled

CRITICAL REQUIREMENTS:
1. Use data "aws_ami" with owner and name filters — NO hardcoded AMI IDs
2. Use data "aws_availability_zones" for multi-AZ subnets
3. Use data "aws_iam_policy_document" for all IAM policies
4. All passwords/keys marked sensitive
5. Proper tags on every resource
6. Code must pass terraform validate
7. Return ONLY the JSON object with main_tf, variables_tf, outputs_tf"""

        return prompt

    def _call(
        self, user_prompt: str, system_prompt: str
    ) -> TerraformBundle:
        """Call LLM service (OpenAI with Gemini fallback) and parse Terraform JSON."""
        raw = self.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
            timeout=30,
        )
        data = json.loads(raw)

        # Ensure all keys are strings
        for key in ("main_tf", "variables_tf", "outputs_tf"):
            val = data.get(key, "")
            if isinstance(val, dict):
                data[key] = json.dumps(val, indent=2)
            else:
                data[key] = str(val) if val else ""

        return TerraformBundle(**data)
