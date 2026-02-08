"""
Template catalog and request composition helpers.

Production-optimized for generating secure, scalable Terraform configurations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────
# Region Registries
# ─────────────────────────────────────────────────────────────

AWS_REGIONS: Dict[str, str] = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "af-south-1": "Africa (Cape Town)",
    "ap-east-1": "Asia Pacific (Hong Kong)",
    "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-south-2": "Asia Pacific (Hyderabad)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-southeast-2": "Asia Pacific (Sydney)",
    "ap-southeast-3": "Asia Pacific (Jakarta)",
    "ap-southeast-4": "Asia Pacific (Melbourne)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-northeast-3": "Asia Pacific (Osaka)",
    "ca-central-1": "Canada (Central)",
    "eu-central-1": "Europe (Frankfurt)",
    "eu-central-2": "Europe (Zurich)",
    "eu-west-1": "Europe (Ireland)",
    "eu-west-2": "Europe (London)",
    "eu-west-3": "Europe (Paris)",
    "eu-south-1": "Europe (Milan)",
    "eu-south-2": "Europe (Spain)",
    "eu-north-1": "Europe (Stockholm)",
    "il-central-1": "Israel (Tel Aviv)",
    "me-south-1": "Middle East (Bahrain)",
    "me-central-1": "Middle East (UAE)",
    "sa-east-1": "South America (São Paulo)",
}

GCP_REGIONS: Dict[str, str] = {
    "us-central1": "Iowa, USA",
    "us-east1": "South Carolina, USA",
    "us-east4": "Northern Virginia, USA",
    "us-east5": "Columbus, USA",
    "us-south1": "Dallas, USA",
    "us-west1": "Oregon, USA",
    "us-west2": "Los Angeles, USA",
    "us-west3": "Salt Lake City, USA",
    "us-west4": "Las Vegas, USA",
    "northamerica-northeast1": "Montréal, Canada",
    "northamerica-northeast2": "Toronto, Canada",
    "southamerica-east1": "São Paulo, Brazil",
    "southamerica-west1": "Santiago, Chile",
    "europe-central2": "Warsaw, Poland",
    "europe-north1": "Finland",
    "europe-southwest1": "Madrid, Spain",
    "europe-west1": "Belgium",
    "europe-west2": "London, UK",
    "europe-west3": "Frankfurt, Germany",
    "europe-west4": "Netherlands",
    "europe-west6": "Zürich, Switzerland",
    "europe-west8": "Milan, Italy",
    "europe-west9": "Paris, France",
    "europe-west10": "Berlin, Germany",
    "europe-west12": "Turin, Italy",
    "asia-east1": "Taiwan",
    "asia-east2": "Hong Kong",
    "asia-northeast1": "Tokyo, Japan",
    "asia-northeast2": "Osaka, Japan",
    "asia-northeast3": "Seoul, South Korea",
    "asia-south1": "Mumbai, India",
    "asia-south2": "Delhi, India",
    "asia-southeast1": "Singapore",
    "asia-southeast2": "Jakarta, Indonesia",
    "australia-southeast1": "Sydney, Australia",
    "australia-southeast2": "Melbourne, Australia",
    "me-central1": "Doha, Qatar",
    "me-central2": "Dammam, Saudi Arabia",
    "me-west1": "Tel Aviv, Israel",
    "africa-south1": "Johannesburg, South Africa",
}


# ─────────────────────────────────────────────────────────────
# Shared production constraints injected into every prompt
# ─────────────────────────────────────────────────────────────

_PRODUCTION_PREAMBLE = (
    "Generate production-grade Terraform code. "
    "Use terraform >= 1.0, proper resource naming with var.environment and var.project_name prefixes, "
    "comprehensive tagging/labeling (Environment, Project, ManagedBy=terraform), "
    "data sources over hard-coded AMI/image IDs where possible, "
    "and separate locals block for computed values. "
    "All sensitive inputs must use `sensitive = true`. "
    "Never use provisioners, null_resource, or hard-coded credentials. "
)


# ─────────────────────────────────────────────────────────────
# Template catalog – 30 templates (15 AWS + 15 GCP)
# ─────────────────────────────────────────────────────────────

TEMPLATE_CATALOG: List[Dict[str, Any]] = [
    # ==================== AWS COMPUTE ====================
    {
        "id": "aws_ec2_instance",
        "name": "EC2 Instance",
        "description": "Virtual server with customizable instance types, EBS-optimized by default",
        "category": "compute",
        "providers": ["aws"],
        "chips": ["EC2", "VPC", "Security Group", "EBS"],
        "prompt": (
            "Deploy an EC2 instance inside its own VPC (or use a data source for an existing default VPC). "
            "Create a security group that allows inbound on user-specified ports only from a configurable CIDR (default: operator IP, NOT 0.0.0.0/0 for SSH). "
            "Generate an SSH key pair using tls_private_key and aws_key_pair resources. "
            "Use a data source (aws_ami) to look up the latest AMI for the chosen OS instead of hard-coding an AMI ID. "
            "Attach a gp3 root EBS volume with encryption enabled (aws_ebs_default_encryption or volume-level). "
            "Enable detailed monitoring and IMDSv2 (metadata_options http_tokens = required). "
            "Output the instance ID, public IP, private IP, and the private key (marked sensitive)."
        ),
        "parameters": [
            {
                "name": "instance_type",
                "label": "Instance Type",
                "type": "select",
                "required": True,
                "default": "t3.micro",
                "options": [
                    {"value": "t3.micro", "label": "t3.micro (2 vCPU, 1 GB) – ~$0.01/hr"},
                    {"value": "t3.small", "label": "t3.small (2 vCPU, 2 GB) – ~$0.02/hr"},
                    {"value": "t3.medium", "label": "t3.medium (2 vCPU, 4 GB) – ~$0.04/hr"},
                    {"value": "t3.large", "label": "t3.large (2 vCPU, 8 GB) – ~$0.08/hr"},
                    {"value": "m5.large", "label": "m5.large (2 vCPU, 8 GB) – ~$0.10/hr"},
                    {"value": "m5.xlarge", "label": "m5.xlarge (4 vCPU, 16 GB) – ~$0.19/hr"},
                    {"value": "c5.large", "label": "c5.large (2 vCPU, 4 GB) – Compute Opt"},
                    {"value": "r5.large", "label": "r5.large (2 vCPU, 16 GB) – Memory Opt"},
                ],
                "description": "Choose based on workload: t3 general, c5 compute, r5 memory",
            },
            {
                "name": "ami",
                "label": "Operating System",
                "type": "select",
                "required": True,
                "default": "amazon-linux-2",
                "options": [
                    {"value": "amazon-linux-2", "label": "Amazon Linux 2"},
                    {"value": "ubuntu-22.04", "label": "Ubuntu 22.04 LTS"},
                    {"value": "ubuntu-20.04", "label": "Ubuntu 20.04 LTS"},
                    {"value": "windows-server-2022", "label": "Windows Server 2022"},
                    {"value": "rhel-9", "label": "Red Hat Enterprise Linux 9"},
                ],
            },
            {
                "name": "storage_size",
                "label": "Root Volume Size (GB)",
                "type": "number",
                "required": True,
                "default": 20,
                "min": 8,
                "max": 16384,
                "description": "EBS root volume size",
            },
            {
                "name": "storage_type",
                "label": "Storage Type",
                "type": "select",
                "required": True,
                "default": "gp3",
                "options": [
                    {"value": "gp3", "label": "gp3 – Best price/perf (default)"},
                    {"value": "gp2", "label": "gp2 – General Purpose SSD"},
                    {"value": "io2", "label": "io2 – Provisioned IOPS"},
                    {"value": "st1", "label": "st1 – Throughput HDD"},
                ],
            },
            {
                "name": "enable_monitoring",
                "label": "Detailed Monitoring",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled (1-min metrics)"},
                    {"value": "false", "label": "Disabled (5-min metrics)"},
                ],
            },
            {
                "name": "enable_public_ip",
                "label": "Public IP Address",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Assign public IP"},
                    {"value": "false", "label": "Private only"},
                ],
            },
        ],
    },
    {
        "id": "aws_lambda_function",
        "name": "Lambda Function",
        "description": "Serverless compute with IAM, CloudWatch, and X-Ray tracing",
        "category": "serverless",
        "providers": ["aws"],
        "chips": ["Lambda", "IAM", "CloudWatch", "X-Ray"],
        "prompt": (
            "Create a Lambda function with: "
            "1) A dedicated IAM execution role following least-privilege (logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents). "
            "2) A CloudWatch Log Group with configurable retention (var.log_retention_days). "
            "3) Environment variables block (empty map variable so users can inject). "
            "4) X-Ray active tracing enabled. "
            "5) A placeholder zip deployment package using a data 'archive_file' of a hello-world handler. "
            "6) Reserved concurrent executions variable (default null = unreserved). "
            "7) Dead-letter config variable (optional SQS ARN). "
            "Output the function ARN, invoke ARN, and log group name."
        ),
        "parameters": [
            {
                "name": "runtime",
                "label": "Runtime",
                "type": "select",
                "required": True,
                "default": "python3.12",
                "options": [
                    {"value": "python3.12", "label": "Python 3.12"},
                    {"value": "python3.11", "label": "Python 3.11"},
                    {"value": "python3.10", "label": "Python 3.10"},
                    {"value": "nodejs20.x", "label": "Node.js 20"},
                    {"value": "nodejs18.x", "label": "Node.js 18"},
                    {"value": "java17", "label": "Java 17"},
                    {"value": "java11", "label": "Java 11"},
                    {"value": "dotnet8", "label": ".NET 8"},
                    {"value": "go1.x", "label": "Go 1.x"},
                    {"value": "ruby3.2", "label": "Ruby 3.2"},
                ],
            },
            {
                "name": "memory_size",
                "label": "Memory (MB)",
                "type": "select",
                "required": True,
                "default": "512",
                "options": [
                    {"value": "128", "label": "128 MB"},
                    {"value": "256", "label": "256 MB"},
                    {"value": "512", "label": "512 MB"},
                    {"value": "1024", "label": "1024 MB (1 GB)"},
                    {"value": "2048", "label": "2048 MB (2 GB)"},
                    {"value": "4096", "label": "4096 MB (4 GB)"},
                    {"value": "10240", "label": "10240 MB (10 GB)"},
                ],
                "description": "More memory = proportionally more CPU",
            },
            {
                "name": "timeout",
                "label": "Timeout (seconds)",
                "type": "number",
                "required": True,
                "default": 30,
                "min": 1,
                "max": 900,
                "description": "Max execution time (1-900s)",
            },
        ],
    },
    {
        "id": "aws_ecs_cluster",
        "name": "ECS Cluster",
        "description": "Container orchestration with Fargate, auto-scaling, and service discovery",
        "category": "containers",
        "providers": ["aws"],
        "chips": ["ECS", "ECR", "Fargate", "Service Discovery"],
        "prompt": (
            "Set up an ECS cluster with: "
            "1) Fargate capacity providers (FARGATE and FARGATE_SPOT with configurable weights). "
            "2) Container Insights enabled for monitoring. "
            "3) A sample task definition with configurable CPU/memory, awslogs log driver, and a placeholder container image. "
            "4) An ECS service with desired_count, deployment_circuit_breaker with rollback enabled, "
            "and network configuration in private subnets. "
            "5) Application Auto Scaling target and policy (target tracking on CPU utilization). "
            "6) A dedicated CloudWatch Log Group for container logs. "
            "Output the cluster ARN, service name, and task definition ARN."
        ),
    },
    {
        "id": "aws_eks_cluster",
        "name": "EKS Cluster",
        "description": "Managed Kubernetes with managed node groups and IRSA",
        "category": "containers",
        "providers": ["aws"],
        "chips": ["EKS", "VPC", "IAM", "IRSA"],
        "prompt": (
            "Provision an EKS cluster with: "
            "1) A dedicated VPC with public and private subnets across 2 AZs. "
            "2) Cluster IAM role with AmazonEKSClusterPolicy. "
            "3) Managed node group with configurable instance types, desired/min/max sizes, and node IAM role "
            "(AmazonEKSWorkerNodePolicy, AmazonEKS_CNI_Policy, AmazonEC2ContainerRegistryReadOnly). "
            "4) Cluster security group allowing node-to-control-plane communication. "
            "5) OIDC provider for IAM Roles for Service Accounts (IRSA). "
            "6) Secrets encryption with a KMS key. "
            "7) Enabled cluster logging (api, audit, authenticator). "
            "Output cluster endpoint, cluster CA certificate, OIDC issuer URL, and kubeconfig command."
        ),
    },
    # ==================== AWS STORAGE ====================
    {
        "id": "aws_s3_bucket",
        "name": "S3 Bucket",
        "description": "Object storage with encryption, versioning, and lifecycle management",
        "category": "storage",
        "providers": ["aws"],
        "chips": ["S3", "Bucket Policy", "Versioning", "KMS"],
        "prompt": (
            "Create an S3 bucket with: "
            "1) Block all public access (aws_s3_bucket_public_access_block). "
            "2) Server-side encryption (SSE-S3 default, with option for SSE-KMS). "
            "3) Versioning enabled by default. "
            "4) Lifecycle rule to transition to STANDARD_IA after configurable days, and to GLACIER after another period. "
            "5) Bucket policy that enforces ssl-only access (aws:SecureTransport condition). "
            "6) Access logging to a separate logging bucket (optional, controlled by variable). "
            "7) CORS configuration variable (default empty). "
            "Use the newer separate resource style (aws_s3_bucket_versioning, aws_s3_bucket_server_side_encryption_configuration, etc.). "
            "Output the bucket ARN, bucket domain name, and bucket regional domain name."
        ),
        "parameters": [
            {
                "name": "versioning",
                "label": "Versioning",
                "type": "select",
                "required": True,
                "default": "Enabled",
                "options": [
                    {"value": "Enabled", "label": "Enabled – Keep all versions"},
                    {"value": "Disabled", "label": "Disabled"},
                ],
            },
            {
                "name": "encryption",
                "label": "Server-Side Encryption",
                "type": "select",
                "required": True,
                "default": "AES256",
                "options": [
                    {"value": "AES256", "label": "SSE-S3 (AES-256)"},
                    {"value": "aws:kms", "label": "SSE-KMS (AWS KMS)"},
                ],
            },
            {
                "name": "public_access",
                "label": "Public Access",
                "type": "select",
                "required": True,
                "default": "block",
                "options": [
                    {"value": "block", "label": "Block all public access (Recommended)"},
                    {"value": "allow", "label": "Allow public access"},
                ],
            },
            {
                "name": "lifecycle_days",
                "label": "Lifecycle – Transition to IA (days)",
                "type": "number",
                "required": False,
                "default": 30,
                "min": 30,
                "max": 365,
                "description": "Move objects to Infrequent Access after N days",
            },
        ],
    },
    # ==================== AWS DATABASE ====================
    {
        "id": "aws_rds_database",
        "name": "RDS Database",
        "description": "Managed relational database with encryption, backups, and multi-AZ",
        "category": "database",
        "providers": ["aws"],
        "chips": ["RDS", "Subnet Group", "Security Group", "KMS"],
        "prompt": (
            "Deploy an RDS database with: "
            "1) A DB subnet group spanning private subnets in at least 2 AZs (create VPC or use data source). "
            "2) Security group allowing ingress only on the DB port from a configurable app CIDR/security group. "
            "3) Storage encryption enabled (KMS key configurable). "
            "4) Automated backups with configurable retention (default 7 days) and preferred backup window. "
            "5) Multi-AZ option controlled by variable (default false for dev, true for prod). "
            "6) deletion_protection enabled by default (variable to override). "
            "7) skip_final_snapshot = false with a dynamic final_snapshot_identifier. "
            "8) Performance Insights enabled (free tier). "
            "9) Enhanced monitoring at 60s interval with a dedicated IAM role. "
            "10) Username via variable, password via var with sensitive=true (recommend aws_secretsmanager_secret in output hint). "
            "Output the endpoint, port, database name, and connection string template."
        ),
        "parameters": [
            {
                "name": "engine",
                "label": "Database Engine",
                "type": "select",
                "required": True,
                "default": "postgres",
                "options": [
                    {"value": "postgres", "label": "PostgreSQL"},
                    {"value": "mysql", "label": "MySQL"},
                    {"value": "mariadb", "label": "MariaDB"},
                    {"value": "oracle-ee", "label": "Oracle Enterprise Edition"},
                    {"value": "sqlserver-ex", "label": "SQL Server Express"},
                    {"value": "sqlserver-se", "label": "SQL Server Standard"},
                ],
            },
            {
                "name": "instance_class",
                "label": "Instance Class",
                "type": "select",
                "required": True,
                "default": "db.t3.micro",
                "options": [
                    {"value": "db.t3.micro", "label": "db.t3.micro (1 vCPU, 1 GB)"},
                    {"value": "db.t3.small", "label": "db.t3.small (2 vCPU, 2 GB)"},
                    {"value": "db.t3.medium", "label": "db.t3.medium (2 vCPU, 4 GB)"},
                    {"value": "db.m5.large", "label": "db.m5.large (2 vCPU, 8 GB)"},
                    {"value": "db.r5.large", "label": "db.r5.large (2 vCPU, 16 GB) – Memory Opt"},
                ],
            },
            {
                "name": "allocated_storage",
                "label": "Storage (GB)",
                "type": "number",
                "required": True,
                "default": 20,
                "min": 20,
                "max": 65536,
            },
            {
                "name": "multi_az",
                "label": "Multi-AZ Deployment",
                "type": "select",
                "required": True,
                "default": "false",
                "options": [
                    {"value": "true", "label": "Enabled (High Availability)"},
                    {"value": "false", "label": "Disabled (Single AZ)"},
                ],
            },
            {
                "name": "backup_retention",
                "label": "Backup Retention (days)",
                "type": "number",
                "required": True,
                "default": 7,
                "min": 0,
                "max": 35,
            },
        ],
    },
    {
        "id": "aws_dynamodb_table",
        "name": "DynamoDB Table",
        "description": "Fully managed NoSQL with encryption, PITR, and auto-scaling",
        "category": "database",
        "providers": ["aws"],
        "chips": ["DynamoDB", "GSI", "Auto Scaling", "KMS"],
        "prompt": (
            "Create a DynamoDB table with: "
            "1) Configurable billing mode (PAY_PER_REQUEST default, or PROVISIONED with auto-scaling). "
            "2) Hash key and optional range key via variables. "
            "3) Point-in-time recovery enabled. "
            "4) Server-side encryption with AWS managed key (option for CMK). "
            "5) TTL attribute configurable (default disabled). "
            "6) Global secondary index variable (list of objects with hash_key, range_key, projection_type). "
            "7) If PROVISIONED mode: auto-scaling policies for read and write capacity. "
            "8) Stream enabled variable (NEW_AND_OLD_IMAGES). "
            "Output the table ARN, table name, hash key, and stream ARN (if enabled)."
        ),
        "parameters": [
            {
                "name": "billing_mode",
                "label": "Billing Mode",
                "type": "select",
                "required": True,
                "default": "PAY_PER_REQUEST",
                "options": [
                    {"value": "PAY_PER_REQUEST", "label": "On-Demand (Pay per request)"},
                    {"value": "PROVISIONED", "label": "Provisioned (Fixed capacity)"},
                ],
            },
            {
                "name": "read_capacity",
                "label": "Read Capacity Units",
                "type": "number",
                "required": False,
                "default": 5,
                "min": 1,
                "max": 40000,
                "description": "Only for Provisioned mode",
            },
            {
                "name": "write_capacity",
                "label": "Write Capacity Units",
                "type": "number",
                "required": False,
                "default": 5,
                "min": 1,
                "max": 40000,
                "description": "Only for Provisioned mode",
            },
            {
                "name": "enable_encryption",
                "label": "Encryption at Rest",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled (AWS managed key)"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
        ],
    },
    # ==================== AWS NETWORKING ====================
    {
        "id": "aws_vpc_network",
        "name": "VPC Network",
        "description": "Production VPC with public/private subnets, NAT, and flow logs",
        "category": "networking",
        "providers": ["aws"],
        "chips": ["VPC", "Subnets", "NAT", "IGW", "Flow Logs"],
        "prompt": (
            "Create a production VPC with: "
            "1) Configurable CIDR block via variable. "
            "2) Public and private subnets across configurable number of AZs (use data 'aws_availability_zones'). "
            "3) Internet Gateway attached to VPC. "
            "4) NAT Gateway in the first public subnet with Elastic IP (optional: one per AZ for HA). "
            "5) Route tables: public subnets route 0.0.0.0/0 → IGW; private subnets route 0.0.0.0/0 → NAT GW. "
            "6) VPC Flow Logs to CloudWatch with a dedicated IAM role and log group (configurable retention). "
            "7) DNS support and DNS hostnames enabled. "
            "8) Proper tagging including kubernetes.io/role tags if var.enable_eks_tags is true. "
            "Output VPC ID, public subnet IDs, private subnet IDs, NAT Gateway IDs, and IGW ID."
        ),
        "parameters": [
            {
                "name": "cidr_block",
                "label": "VPC CIDR Block",
                "type": "select",
                "required": True,
                "default": "10.0.0.0/16",
                "options": [
                    {"value": "10.0.0.0/16", "label": "10.0.0.0/16 (65,536 IPs)"},
                    {"value": "172.16.0.0/16", "label": "172.16.0.0/16 (65,536 IPs)"},
                    {"value": "192.168.0.0/16", "label": "192.168.0.0/16 (65,536 IPs)"},
                ],
            },
            {
                "name": "enable_dns",
                "label": "Enable DNS Support",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
            {
                "name": "subnet_count",
                "label": "Number of AZs",
                "type": "number",
                "required": True,
                "default": 2,
                "min": 1,
                "max": 6,
                "description": "Creates one public + one private subnet per AZ",
            },
        ],
    },
    {
        "id": "aws_alb_loadbalancer",
        "name": "Application Load Balancer",
        "description": "Layer 7 load balancer with SSL, access logs, and WAF-ready",
        "category": "networking",
        "providers": ["aws"],
        "chips": ["ALB", "Target Group", "Listener", "ACM"],
        "prompt": (
            "Set up an Application Load Balancer with: "
            "1) ALB in public subnets with a dedicated security group (HTTP 80, HTTPS 443 ingress). "
            "2) Default target group with configurable health check (path, interval, thresholds). "
            "3) HTTP listener that redirects to HTTPS (301). "
            "4) HTTPS listener with ACM certificate ARN variable (forward to target group). "
            "5) Access logging to an S3 bucket (optional, controlled by variable). "
            "6) Idle timeout, drop_invalid_header_fields = true, desync_mitigation_mode = defensive. "
            "7) enable_deletion_protection variable (default true for prod). "
            "Output the ALB DNS name, ALB ARN, ALB zone ID, target group ARN, and HTTPS listener ARN."
        ),
        "parameters": [
            {
                "name": "load_balancer_type",
                "label": "Load Balancer Type",
                "type": "select",
                "required": True,
                "default": "application",
                "options": [
                    {"value": "application", "label": "Application Load Balancer (HTTP/HTTPS)"},
                    {"value": "network", "label": "Network Load Balancer (TCP/UDP)"},
                ],
            },
            {
                "name": "enable_deletion_protection",
                "label": "Deletion Protection",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
            {
                "name": "enable_http2",
                "label": "HTTP/2 Support",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
        ],
    },
    {
        "id": "aws_route53_zone",
        "name": "Route53 DNS Zone",
        "description": "DNS management with health checks and failover routing",
        "category": "networking",
        "providers": ["aws"],
        "chips": ["Route53", "DNS Records", "Health Checks"],
        "prompt": (
            "Create a Route53 hosted zone with: "
            "1) Public or private zone (if private, associate with VPC). "
            "2) A-record and/or CNAME record variables (list of maps). "
            "3) Health check for the primary endpoint with configurable failure threshold and request interval. "
            "4) Optional: failover routing policy with primary and secondary records. "
            "5) Query logging to CloudWatch (optional). "
            "Output the zone ID, name servers, and health check ID."
        ),
        "parameters": [
            {
                "name": "zone_type",
                "label": "Zone Type",
                "type": "select",
                "required": True,
                "default": "public",
                "options": [
                    {"value": "public", "label": "Public Hosted Zone"},
                    {"value": "private", "label": "Private Hosted Zone (VPC only)"},
                ],
            },
            {
                "name": "domain_name",
                "label": "Domain Name",
                "type": "text",
                "required": True,
                "default": "example.com",
                "description": "The domain name for the hosted zone",
            },
        ],
    },
    # ==================== AWS CDN & API ====================
    {
        "id": "aws_cloudfront_distribution",
        "name": "CloudFront CDN",
        "description": "Global CDN with OAC, custom SSL, and security headers",
        "category": "cdn",
        "providers": ["aws"],
        "chips": ["CloudFront", "S3", "SSL", "OAC"],
        "prompt": (
            "Deploy a CloudFront distribution with: "
            "1) S3 origin using Origin Access Control (OAC, not legacy OAI). "
            "2) S3 bucket policy granting CloudFront access via OAC condition. "
            "3) Custom SSL certificate via ACM (us-east-1) variable, with fallback to CloudFront default cert. "
            "4) Default cache behavior with CachingOptimized managed policy. "
            "5) Viewer protocol policy: redirect-to-https. "
            "6) Response headers policy for security headers (Strict-Transport-Security, X-Content-Type-Options, etc.). "
            "7) Configurable price class and geo restriction. "
            "8) WAF web ACL ARN variable (optional). "
            "9) Logging to S3 bucket (optional). "
            "Output the distribution ID, domain name, ARN, and hosted zone ID."
        ),
        "parameters": [
            {
                "name": "price_class",
                "label": "Price Class",
                "type": "select",
                "required": True,
                "default": "PriceClass_100",
                "options": [
                    {"value": "PriceClass_100", "label": "North America & Europe only"},
                    {"value": "PriceClass_200", "label": "NA, EU, Asia, ME & Africa"},
                    {"value": "PriceClass_All", "label": "All edge locations (Global)"},
                ],
            },
            {
                "name": "enable_ipv6",
                "label": "Enable IPv6",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
            {
                "name": "default_root_object",
                "label": "Default Root Object",
                "type": "text",
                "required": False,
                "default": "index.html",
            },
        ],
    },
    {
        "id": "aws_api_gateway",
        "name": "API Gateway",
        "description": "Managed REST/HTTP API with authorization and throttling",
        "category": "api",
        "providers": ["aws"],
        "chips": ["API Gateway", "Lambda", "Authorizer", "WAF"],
        "prompt": (
            "Create an API Gateway with: "
            "1) HTTP API (v2) or REST API (v1) based on var.api_protocol. "
            "2) Stage with auto_deploy = true and access logging to CloudWatch. "
            "3) Default route integrated with a Lambda function (permission grant). "
            "4) CORS configuration variable (allow_origins, allow_methods, allow_headers). "
            "5) Throttling defaults (burst_limit, rate_limit) via stage default_route_settings. "
            "6) Optional: custom domain name with ACM certificate and Route53 alias record. "
            "Output the API endpoint, API ID, stage invoke URL, and execution ARN."
        ),
        "parameters": [
            {
                "name": "endpoint_type",
                "label": "Endpoint Type",
                "type": "select",
                "required": True,
                "default": "REGIONAL",
                "options": [
                    {"value": "REGIONAL", "label": "Regional"},
                    {"value": "EDGE", "label": "Edge Optimized (CloudFront)"},
                    {"value": "PRIVATE", "label": "Private (VPC only)"},
                ],
            },
            {
                "name": "api_protocol",
                "label": "Protocol",
                "type": "select",
                "required": True,
                "default": "HTTP",
                "options": [
                    {"value": "HTTP", "label": "HTTP API (Lower cost, faster)"},
                    {"value": "REST", "label": "REST API (More features)"},
                    {"value": "WEBSOCKET", "label": "WebSocket API"},
                ],
            },
        ],
    },
    # ==================== AWS SECURITY & MONITORING ====================
    {
        "id": "aws_iam_role",
        "name": "IAM Role & Policy",
        "description": "Least-privilege IAM with trust relationships and policy boundaries",
        "category": "security",
        "providers": ["aws"],
        "chips": ["IAM", "Policy", "Trust Relationship", "Permissions Boundary"],
        "prompt": (
            "Create IAM resources with: "
            "1) An IAM role with assume_role_policy for the specified trusted service. "
            "2) A custom IAM policy document using data 'aws_iam_policy_document' (not inline JSON strings). "
            "3) Policy attachment to the role. "
            "4) Optional permissions boundary variable. "
            "5) Optional: instance profile if the trusted service is EC2. "
            "6) Configurable max_session_duration (default 3600). "
            "7) Condition keys in trust policy where appropriate (e.g., sts:ExternalId for cross-account). "
            "Output the role ARN, role name, policy ARN, and instance profile ARN (if applicable)."
        ),
        "parameters": [
            {
                "name": "role_name",
                "label": "Role Name",
                "type": "text",
                "required": True,
                "default": "my-app-role",
            },
            {
                "name": "trusted_service",
                "label": "Trusted Service",
                "type": "select",
                "required": True,
                "default": "ec2.amazonaws.com",
                "options": [
                    {"value": "ec2.amazonaws.com", "label": "EC2"},
                    {"value": "lambda.amazonaws.com", "label": "Lambda"},
                    {"value": "ecs-tasks.amazonaws.com", "label": "ECS Tasks"},
                    {"value": "rds.amazonaws.com", "label": "RDS"},
                ],
            },
        ],
    },
    {
        "id": "aws_cloudwatch_dashboard",
        "name": "CloudWatch Monitoring",
        "description": "Dashboards, alarms, composite alarms, and log insights",
        "category": "monitoring",
        "providers": ["aws"],
        "chips": ["CloudWatch", "Alarms", "Logs", "SNS"],
        "prompt": (
            "Set up CloudWatch monitoring with: "
            "1) A dashboard with JSON body containing widgets for CPU, memory, disk, network metrics. "
            "2) Log group with configurable retention and KMS encryption. "
            "3) Metric alarm for high CPU (> 80% for 5 min) with SNS notification. "
            "4) SNS topic for alarm notifications with email subscription variable. "
            "5) Optional: composite alarm combining multiple metric alarms. "
            "6) Log metric filter to create a custom metric from log patterns. "
            "Output the dashboard ARN, log group ARN, alarm ARNs, and SNS topic ARN."
        ),
        "parameters": [
            {
                "name": "dashboard_name",
                "label": "Dashboard Name",
                "type": "text",
                "required": True,
                "default": "AppDashboard",
            },
            {
                "name": "retention_days",
                "label": "Log Retention (Days)",
                "type": "select",
                "required": True,
                "default": "30",
                "options": [
                    {"value": "7", "label": "7 days"},
                    {"value": "14", "label": "14 days"},
                    {"value": "30", "label": "30 days"},
                    {"value": "90", "label": "90 days"},
                    {"value": "365", "label": "1 year"},
                    {"value": "0", "label": "Never expire"},
                ],
            },
        ],
    },
    {
        "id": "aws_sns_sqs",
        "name": "SNS/SQS Messaging",
        "description": "Pub/sub and queuing with DLQ, encryption, and access policies",
        "category": "messaging",
        "providers": ["aws"],
        "chips": ["SNS", "SQS", "Dead Letter Queue", "KMS"],
        "prompt": (
            "Create SNS/SQS messaging with: "
            "1) SQS queue with configurable FIFO/Standard mode. "
            "2) Dead letter queue with maxReceiveCount redrive policy. "
            "3) Server-side encryption using SQS-managed keys (or KMS). "
            "4) Queue policy allowing SNS topic to send messages. "
            "5) SNS topic with configurable display name and encryption. "
            "6) SNS subscription to the SQS queue (with raw_message_delivery). "
            "7) Optional: email/HTTPS endpoint subscriptions via variable list. "
            "Output the queue URL, queue ARN, DLQ URL, DLQ ARN, SNS topic ARN."
        ),
        "parameters": [
            {
                "name": "fifo_queue",
                "label": "FIFO Queue",
                "type": "select",
                "required": True,
                "default": "false",
                "options": [
                    {"value": "true", "label": "FIFO (First-In-First-Out)"},
                    {"value": "false", "label": "Standard"},
                ],
            },
            {
                "name": "message_retention_seconds",
                "label": "Message Retention (Seconds)",
                "type": "number",
                "required": True,
                "default": 345600,
                "min": 60,
                "max": 1209600,
                "description": "Default: 4 days (345600s)",
            },
            {
                "name": "visibility_timeout_seconds",
                "label": "Visibility Timeout (Seconds)",
                "type": "number",
                "required": True,
                "default": 30,
                "min": 0,
                "max": 43200,
            },
        ],
    },
    # ==================== GCP COMPUTE ====================
    {
        "id": "gcp_compute_instance",
        "name": "Compute Engine Instance",
        "description": "VM with shielded instance, OS Login, and service account",
        "category": "compute",
        "providers": ["gcp"],
        "chips": ["Compute Engine", "VPC", "Firewall", "Shielded VM"],
        "prompt": (
            "Deploy a Compute Engine instance with: "
            "1) Configurable machine type and zone. "
            "2) Boot disk using a data source for the latest image (google_compute_image) for the chosen OS family. "
            "3) Shielded instance config (enable_secure_boot, enable_vtpm, enable_integrity_monitoring). "
            "4) A dedicated service account with configurable scopes (default: cloud-platform). "
            "5) Firewall rule allowing SSH only from a configurable source CIDR (NOT 0.0.0.0/0). "
            "6) Firewall rule for application ports (configurable list). "
            "7) metadata: enable-oslogin = true. "
            "8) Network tags for firewall targeting. "
            "9) Optional: external IP (default none for private-only access). "
            "Output the instance self_link, internal IP, external IP (if any), and instance ID."
        ),
        "parameters": [
            {
                "name": "machine_type",
                "label": "Machine Type",
                "type": "select",
                "required": True,
                "default": "e2-micro",
                "options": [
                    {"value": "e2-micro", "label": "e2-micro (0.25 vCPU, 1 GB)"},
                    {"value": "e2-small", "label": "e2-small (0.5 vCPU, 2 GB)"},
                    {"value": "e2-medium", "label": "e2-medium (1 vCPU, 4 GB)"},
                    {"value": "n1-standard-1", "label": "n1-standard-1 (1 vCPU, 3.75 GB)"},
                    {"value": "n1-standard-2", "label": "n1-standard-2 (2 vCPU, 7.5 GB)"},
                ],
            },
            {
                "name": "boot_disk_size",
                "label": "Boot Disk Size (GB)",
                "type": "number",
                "required": True,
                "default": 20,
                "min": 10,
                "max": 10000,
            },
            {
                "name": "boot_disk_type",
                "label": "Boot Disk Type",
                "type": "select",
                "required": True,
                "default": "pd-balanced",
                "options": [
                    {"value": "pd-standard", "label": "Standard Persistent Disk"},
                    {"value": "pd-balanced", "label": "Balanced Persistent Disk"},
                    {"value": "pd-ssd", "label": "SSD Persistent Disk"},
                ],
            },
        ],
    },
    {
        "id": "gcp_cloud_function",
        "name": "Cloud Function",
        "description": "Event-driven serverless with 2nd gen, concurrency, and secret access",
        "category": "serverless",
        "providers": ["gcp"],
        "chips": ["Cloud Functions", "IAM", "Pub/Sub", "Secret Manager"],
        "prompt": (
            "Create a Cloud Function (2nd gen) with: "
            "1) HTTP trigger with configurable authentication (ALLOW_UNAUTHENTICATED or require auth). "
            "2) Source code from a GCS bucket (create bucket + archive_file data source for placeholder code). "
            "3) Dedicated service account with least-privilege IAM. "
            "4) Environment variables and secret references (via Secret Manager) as variables. "
            "5) Configurable concurrency (max_instance_request_concurrency). "
            "6) Min/max instance count for scaling control. "
            "7) VPC connector for private network access (optional). "
            "8) Ingress settings variable (ALLOW_ALL, ALLOW_INTERNAL_ONLY, ALLOW_INTERNAL_AND_GCLB). "
            "Output the function URI, function name, service account email."
        ),
        "parameters": [
            {
                "name": "runtime",
                "label": "Runtime",
                "type": "select",
                "required": True,
                "default": "python312",
                "options": [
                    {"value": "python312", "label": "Python 3.12"},
                    {"value": "python311", "label": "Python 3.11"},
                    {"value": "nodejs20", "label": "Node.js 20"},
                    {"value": "nodejs18", "label": "Node.js 18"},
                    {"value": "go121", "label": "Go 1.21"},
                    {"value": "java17", "label": "Java 17"},
                ],
            },
            {
                "name": "memory",
                "label": "Memory (MB)",
                "type": "select",
                "required": True,
                "default": "256",
                "options": [
                    {"value": "128", "label": "128 MB"},
                    {"value": "256", "label": "256 MB"},
                    {"value": "512", "label": "512 MB"},
                    {"value": "1024", "label": "1 GB"},
                    {"value": "2048", "label": "2 GB"},
                ],
            },
            {
                "name": "timeout",
                "label": "Timeout (seconds)",
                "type": "number",
                "required": True,
                "default": 60,
                "min": 1,
                "max": 540,
            },
        ],
    },
    {
        "id": "gcp_cloud_run",
        "name": "Cloud Run Service",
        "description": "Fully managed containers with traffic splitting and VPC access",
        "category": "containers",
        "providers": ["gcp"],
        "chips": ["Cloud Run", "Artifact Registry", "IAM", "VPC Connector"],
        "prompt": (
            "Deploy a Cloud Run service with: "
            "1) Container image from Artifact Registry (configurable var). "
            "2) Dedicated service account with least-privilege IAM. "
            "3) Configurable CPU/memory limits and CPU throttling (cpu_idle). "
            "4) Auto-scaling with min/max instances and concurrency. "
            "5) Environment variables and secret mounts (from Secret Manager). "
            "6) Ingress setting (all, internal, internal-and-cloud-load-balancing). "
            "7) VPC access connector for private network connectivity (optional). "
            "8) Optional: custom domain mapping with verified domain. "
            "9) IAM binding for invoker (allUsers for public, or specific accounts). "
            "Output the service URL, service name, latest revision, and service account email."
        ),
        "parameters": [
            {
                "name": "cpu",
                "label": "CPU Allocation",
                "type": "select",
                "required": True,
                "default": "1",
                "options": [
                    {"value": "1", "label": "1 CPU"},
                    {"value": "2", "label": "2 CPU"},
                    {"value": "4", "label": "4 CPU"},
                ],
            },
            {
                "name": "memory",
                "label": "Memory Allocation",
                "type": "select",
                "required": True,
                "default": "512Mi",
                "options": [
                    {"value": "256Mi", "label": "256 MiB"},
                    {"value": "512Mi", "label": "512 MiB"},
                    {"value": "1Gi", "label": "1 GiB"},
                    {"value": "2Gi", "label": "2 GiB"},
                    {"value": "4Gi", "label": "4 GiB"},
                ],
            },
            {
                "name": "min_instances",
                "label": "Min Instances",
                "type": "number",
                "required": True,
                "default": 0,
                "min": 0,
                "max": 100,
                "description": "Keep instances warm (costs money if > 0)",
            },
            {
                "name": "max_instances",
                "label": "Max Instances",
                "type": "number",
                "required": True,
                "default": 10,
                "min": 1,
                "max": 1000,
            },
        ],
    },
    {
        "id": "gcp_gke_cluster",
        "name": "GKE Cluster",
        "description": "Managed Kubernetes with Workload Identity and private cluster",
        "category": "containers",
        "providers": ["gcp"],
        "chips": ["GKE", "VPC", "Node Pool", "Workload Identity"],
        "prompt": (
            "Provision a GKE cluster with: "
            "1) Private cluster (enable_private_nodes, enable_private_endpoint optional). "
            "2) Workload Identity enabled (workload_metadata_config GKE_METADATA). "
            "3) Release channel (REGULAR default). "
            "4) Binary authorization variable. "
            "5) Network policy enabled (Calico). "
            "6) Shielded GKE nodes enabled. "
            "7) Separate default node pool (remove_default_node_pool = true) and managed node pool with: "
            "   auto-scaling, machine type, disk size/type, OAuth scopes, service account. "
            "8) Master authorized networks (configurable CIDR list). "
            "9) Maintenance window variable. "
            "10) VPC-native (ip_allocation_policy) with configurable pod and service CIDR ranges. "
            "Output the cluster endpoint, cluster CA cert, cluster name, and master version."
        ),
        "parameters": [
            {
                "name": "kubernetes_version",
                "label": "Kubernetes Version",
                "type": "select",
                "required": True,
                "default": "latest",
                "options": [
                    {"value": "latest", "label": "Latest stable"},
                    {"value": "1.28", "label": "1.28"},
                    {"value": "1.27", "label": "1.27"},
                ],
            },
            {
                "name": "node_machine_type",
                "label": "Node Machine Type",
                "type": "select",
                "required": True,
                "default": "e2-medium",
                "options": [
                    {"value": "e2-medium", "label": "e2-medium (1 vCPU, 4 GB)"},
                    {"value": "e2-standard-2", "label": "e2-standard-2 (2 vCPU, 8 GB)"},
                    {"value": "n1-standard-2", "label": "n1-standard-2 (2 vCPU, 7.5 GB)"},
                ],
            },
            {
                "name": "node_count",
                "label": "Initial Node Count",
                "type": "number",
                "required": True,
                "default": 3,
                "min": 1,
                "max": 100,
            },
            {
                "name": "enable_autoscaling",
                "label": "Autoscaling",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
        ],
    },
    # ==================== GCP STORAGE ====================
    {
        "id": "gcp_storage_bucket",
        "name": "Cloud Storage Bucket",
        "description": "Object storage with CMEK, retention policies, and lifecycle",
        "category": "storage",
        "providers": ["gcp"],
        "chips": ["Cloud Storage", "Lifecycle", "IAM", "CMEK"],
        "prompt": (
            "Create a Cloud Storage bucket with: "
            "1) Uniform bucket-level access enforced. "
            "2) Versioning enabled by default. "
            "3) Public access prevention enforced. "
            "4) Configurable storage class (STANDARD default). "
            "5) Lifecycle rules: transition to NEARLINE after N days, delete old versions after M days. "
            "6) Encryption with Google-managed or CMEK (optional KMS key variable). "
            "7) Retention policy variable (optional lock). "
            "8) CORS configuration variable. "
            "9) Logging to a separate bucket (optional). "
            "Output the bucket URL, bucket self_link, and bucket name."
        ),
        "parameters": [
            {
                "name": "storage_class",
                "label": "Storage Class",
                "type": "select",
                "required": True,
                "default": "STANDARD",
                "options": [
                    {"value": "STANDARD", "label": "Standard (Frequent access)"},
                    {"value": "NEARLINE", "label": "Nearline (Once per month)"},
                    {"value": "COLDLINE", "label": "Coldline (Once per quarter)"},
                    {"value": "ARCHIVE", "label": "Archive (Once per year)"},
                ],
            },
            {
                "name": "versioning",
                "label": "Object Versioning",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
            {
                "name": "public_access",
                "label": "Public Access Prevention",
                "type": "select",
                "required": True,
                "default": "enforced",
                "options": [
                    {"value": "enforced", "label": "Enforced (Recommended)"},
                    {"value": "inherited", "label": "Inherited from organization"},
                ],
            },
        ],
    },
    # ==================== GCP DATABASE ====================
    {
        "id": "gcp_cloud_sql",
        "name": "Cloud SQL Database",
        "description": "Managed SQL with private IP, HA, and automated backups",
        "category": "database",
        "providers": ["gcp"],
        "chips": ["Cloud SQL", "Private IP", "Backup", "IAM Auth"],
        "prompt": (
            "Deploy a Cloud SQL instance with: "
            "1) Private IP networking via google_compute_global_address and google_service_networking_connection. "
            "2) Automated backups with configurable start time and transaction log retention. "
            "3) High availability configuration controlled by variable (REGIONAL for HA). "
            "4) Point-in-time recovery enabled. "
            "5) Maintenance window (day, hour, update_track). "
            "6) Database flags variable (list of name/value pairs). "
            "7) Deletion protection enabled by default. "
            "8) IAM database authentication variable. "
            "9) Insights config enabled. "
            "10) Initial database and user (password via sensitive variable). "
            "Output the connection name, private IP, database name, and instance self_link."
        ),
        "parameters": [
            {
                "name": "database_version",
                "label": "Database Version",
                "type": "select",
                "required": True,
                "default": "POSTGRES_15",
                "options": [
                    {"value": "POSTGRES_15", "label": "PostgreSQL 15"},
                    {"value": "POSTGRES_14", "label": "PostgreSQL 14"},
                    {"value": "MYSQL_8_0", "label": "MySQL 8.0"},
                    {"value": "MYSQL_5_7", "label": "MySQL 5.7"},
                    {"value": "SQLSERVER_2019_STANDARD", "label": "SQL Server 2019 Standard"},
                ],
            },
            {
                "name": "tier",
                "label": "Machine Type",
                "type": "select",
                "required": True,
                "default": "db-f1-micro",
                "options": [
                    {"value": "db-f1-micro", "label": "db-f1-micro (0.6 GB RAM)"},
                    {"value": "db-g1-small", "label": "db-g1-small (1.7 GB RAM)"},
                    {"value": "db-n1-standard-1", "label": "db-n1-standard-1 (3.75 GB RAM)"},
                    {"value": "db-n1-standard-2", "label": "db-n1-standard-2 (7.5 GB RAM)"},
                ],
            },
            {
                "name": "disk_size",
                "label": "Storage (GB)",
                "type": "number",
                "required": True,
                "default": 10,
                "min": 10,
                "max": 65536,
            },
            {
                "name": "backup_enabled",
                "label": "Automated Backups",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
        ],
    },
    {
        "id": "gcp_firestore",
        "name": "Firestore Database",
        "description": "Scalable NoSQL with composite indexes and backup schedules",
        "category": "database",
        "providers": ["gcp"],
        "chips": ["Firestore", "Indexes", "Backup"],
        "prompt": (
            "Create a Firestore database with: "
            "1) google_firestore_database resource with location type (regional or multi-region). "
            "2) Concurrency mode configuration. "
            "3) App Engine integration awareness (Firestore requires App Engine app in some configs). "
            "4) Composite index examples as variables (collection, fields, query_scope). "
            "5) Backup schedule using google_firestore_backup_schedule (daily/weekly). "
            "6) IAM binding for database access. "
            "7) Deletion policy variable (ABANDON or DELETE). "
            "Output the database name, database ID, location, and key_prefix."
        ),
        "parameters": [
            {
                "name": "region_type",
                "label": "Location Type",
                "type": "select",
                "required": True,
                "default": "regional",
                "options": [
                    {"value": "regional", "label": "Regional (Lower latency)"},
                    {"value": "multi-region", "label": "Multi-Region (High availability)"},
                ],
            },
            {
                "name": "concurrency_mode",
                "label": "Concurrency Mode",
                "type": "select",
                "required": True,
                "default": "OPTIMISTIC",
                "options": [
                    {"value": "OPTIMISTIC", "label": "Optimistic"},
                    {"value": "PESSIMISTIC", "label": "Pessimistic"},
                    {"value": "OPTIMISTIC_WITH_ENTITY_GROUPS", "label": "Optimistic with Entity Groups"},
                ],
            },
        ],
    },
    # ==================== GCP NETWORKING ====================
    {
        "id": "gcp_vpc_network",
        "name": "VPC Network",
        "description": "Custom VPC with Cloud NAT, Private Google Access, and flow logs",
        "category": "networking",
        "providers": ["gcp"],
        "chips": ["VPC", "Subnets", "Firewall", "Cloud NAT"],
        "prompt": (
            "Create a VPC network with: "
            "1) Custom subnet mode (auto_create_subnetworks = false). "
            "2) Configurable subnets with secondary ranges for GKE (pods/services). "
            "3) Private Google Access enabled on all subnets. "
            "4) Flow logs with configurable aggregation interval and sampling. "
            "5) Cloud Router and Cloud NAT for private subnet internet access. "
            "6) Firewall rules: deny-all-ingress base rule, allow-internal for VPC ranges, "
            "   allow-ssh from IAP range (35.235.240.0/20), and allow health-checks (130.211.0.0/22, 35.191.0.0/16). "
            "7) Routing mode (REGIONAL or GLOBAL). "
            "8) MTU configuration. "
            "Output the VPC self_link, VPC name, subnet self_links, Cloud NAT name, and router name."
        ),
        "parameters": [
            {
                "name": "subnet_mode",
                "label": "Subnet Creation Mode",
                "type": "select",
                "required": True,
                "default": "CUSTOM",
                "options": [
                    {"value": "AUTO", "label": "Auto (Subnet per region)"},
                    {"value": "CUSTOM", "label": "Custom (Manual subnets)"},
                ],
            },
            {
                "name": "routing_mode",
                "label": "Routing Mode",
                "type": "select",
                "required": True,
                "default": "REGIONAL",
                "options": [
                    {"value": "REGIONAL", "label": "Regional"},
                    {"value": "GLOBAL", "label": "Global"},
                ],
            },
            {
                "name": "mtu",
                "label": "MTU",
                "type": "number",
                "required": True,
                "default": 1460,
                "min": 1300,
                "max": 8896,
            },
        ],
    },
    {
        "id": "gcp_load_balancer",
        "name": "Cloud Load Balancer",
        "description": "Global HTTPS LB with managed SSL, Cloud Armor, and CDN",
        "category": "networking",
        "providers": ["gcp"],
        "chips": ["Load Balancer", "Backend Service", "Health Check", "Cloud Armor"],
        "prompt": (
            "Set up a global HTTP(S) load balancer with: "
            "1) google_compute_global_forwarding_rule for port 443. "
            "2) HTTP-to-HTTPS redirect forwarding rule on port 80. "
            "3) Target HTTPS proxy with managed SSL certificate (google_compute_managed_ssl_certificate). "
            "4) URL map with default service and optional path-based routing. "
            "5) Backend service with health check, connection draining timeout, and session affinity. "
            "6) Cloud CDN integration (optional, controlled by variable). "
            "7) Cloud Armor security policy attachment (optional, variable for policy self_link). "
            "8) Logging enabled with configurable sample rate. "
            "9) Custom headers (X-Client-Geo, etc.) optional. "
            "Output the load balancer IP, forwarding rule self_link, SSL cert status, and backend service self_link."
        ),
        "parameters": [
            {
                "name": "load_balancer_type",
                "label": "Load Balancer Type",
                "type": "select",
                "required": True,
                "default": "EXTERNAL_MANAGED",
                "options": [
                    {"value": "EXTERNAL_MANAGED", "label": "Global External HTTP(S)"},
                    {"value": "EXTERNAL", "label": "Classic Application LB"},
                    {"value": "INTERNAL_MANAGED", "label": "Internal HTTP(S)"},
                ],
            },
            {
                "name": "enable_cdn",
                "label": "Enable Cloud CDN",
                "type": "select",
                "required": True,
                "default": "true",
                "options": [
                    {"value": "true", "label": "Enabled"},
                    {"value": "false", "label": "Disabled"},
                ],
            },
            {
                "name": "ssl_policy",
                "label": "SSL Policy",
                "type": "select",
                "required": True,
                "default": "MODERN",
                "options": [
                    {"value": "COMPATIBLE", "label": "Compatible (Broadest support)"},
                    {"value": "MODERN", "label": "Modern (TLS 1.2+)"},
                    {"value": "RESTRICTED", "label": "Restricted (TLS 1.2+ strong ciphers)"},
                ],
            },
        ],
    },
    {
        "id": "gcp_cloud_dns",
        "name": "Cloud DNS Zone",
        "description": "DNS management with DNSSEC and routing policies",
        "category": "networking",
        "providers": ["gcp"],
        "chips": ["Cloud DNS", "DNS Records", "DNSSEC"],
        "prompt": (
            "Create a Cloud DNS managed zone with: "
            "1) Public or private zone (private requires VPC network binding). "
            "2) DNSSEC configuration with algorithm and key type. "
            "3) A/AAAA/CNAME record sets via variable (list of maps: name, type, ttl, rrdatas). "
            "4) SOA serial number management awareness. "
            "5) Optional: routing policies (weighted, geolocation, failover). "
            "6) IAM binding for dns.admin role (configurable members). "
            "Output the zone name servers, zone DNS name, zone ID, and DNSSEC DS record (if enabled)."
        ),
        "parameters": [
            {
                "name": "zone_type",
                "label": "Visibility",
                "type": "select",
                "required": True,
                "default": "public",
                "options": [
                    {"value": "public", "label": "Public Zone"},
                    {"value": "private", "label": "Private Zone (VPC)"},
                ],
            },
            {
                "name": "dns_name",
                "label": "DNS Name",
                "type": "text",
                "required": True,
                "default": "example.com.",
                "description": "Must end with a dot (.)",
            },
            {
                "name": "dnssec_state",
                "label": "DNSSEC",
                "type": "select",
                "required": True,
                "default": "on",
                "options": [
                    {"value": "on", "label": "On"},
                    {"value": "off", "label": "Off"},
                ],
            },
        ],
    },
    # ==================== GCP CDN & API ====================
    {
        "id": "gcp_cloud_cdn",
        "name": "Cloud CDN",
        "description": "CDN with signed URLs, cache invalidation, and backend buckets",
        "category": "cdn",
        "providers": ["gcp"],
        "chips": ["Cloud CDN", "Backend Bucket", "Cache", "Signed URLs"],
        "prompt": (
            "Enable Cloud CDN with: "
            "1) Backend bucket connected to a GCS bucket. "
            "2) CDN policy with configurable cache mode, max TTL, default TTL, client TTL. "
            "3) Signed URL key for secure content (optional). "
            "4) Cache key policy (include_host, include_protocol, include_query_string). "
            "5) Negative caching for 404/410 responses. "
            "6) IAM for the backend bucket. "
            "7) URL map routing to the backend bucket. "
            "Output the CDN backend bucket self_link, cache stats URL, and serving URL."
        ),
        "parameters": [
            {
                "name": "cache_mode",
                "label": "Cache Mode",
                "type": "select",
                "required": True,
                "default": "CACHE_ALL_STATIC",
                "options": [
                    {"value": "CACHE_ALL_STATIC", "label": "Cache all static content"},
                    {"value": "USE_ORIGIN_HEADERS", "label": "Use origin headers"},
                    {"value": "FORCE_CACHE_ALL", "label": "Force cache all"},
                ],
            },
            {
                "name": "client_ttl",
                "label": "Max Client TTL (seconds)",
                "type": "number",
                "required": True,
                "default": 86400,
                "min": 0,
                "max": 31536000,
            },
        ],
    },
    {
        "id": "gcp_api_gateway",
        "name": "API Gateway",
        "description": "Managed API gateway with OpenAPI, auth, and rate limiting",
        "category": "api",
        "providers": ["gcp"],
        "chips": ["API Gateway", "Cloud Functions", "OpenAPI"],
        "prompt": (
            "Deploy an API Gateway with: "
            "1) google_api_gateway_api, google_api_gateway_api_config, and google_api_gateway_gateway resources. "
            "2) OpenAPI spec (rendered via templatefile or variable). "
            "3) Service account for backend invocation. "
            "4) IAM binding for gateway access. "
            "5) Managed service enablement (apigateway.googleapis.com, servicemanagement.googleapis.com). "
            "6) Labels for cost tracking. "
            "Output the gateway URL, gateway ID, API config ID, and managed service name."
        ),
        "parameters": [
            {
                "name": "gateway_id",
                "label": "Gateway ID",
                "type": "text",
                "required": True,
                "default": "my-gateway",
            },
            {
                "name": "display_name",
                "label": "Display Name",
                "type": "text",
                "required": False,
                "default": "My API Gateway",
            },
        ],
    },
    # ==================== GCP SECURITY & MONITORING ====================
    {
        "id": "gcp_iam_policy",
        "name": "IAM Policy & Service Account",
        "description": "Service accounts with custom roles and Workload Identity",
        "category": "security",
        "providers": ["gcp"],
        "chips": ["IAM", "Service Account", "Roles", "Workload Identity"],
        "prompt": (
            "Create IAM resources with: "
            "1) Service account with display name and description. "
            "2) Custom IAM role with configurable permissions list (use google_project_iam_custom_role). "
            "3) IAM member binding (service account to custom role at project level). "
            "4) Service account key (optional, controlled by variable – prefer Workload Identity). "
            "5) Workload Identity binding for GKE (optional: google_service_account_iam_binding). "
            "6) IAM conditions for time-based or resource-based access (optional). "
            "Output the service account email, unique_id, custom role ID, and key (if created, marked sensitive)."
        ),
        "parameters": [
            {
                "name": "account_id",
                "label": "Service Account ID",
                "type": "text",
                "required": True,
                "default": "my-service-account",
            },
            {
                "name": "display_name",
                "label": "Display Name",
                "type": "text",
                "required": False,
                "default": "My Service Account",
            },
        ],
    },
    {
        "id": "gcp_cloud_monitoring",
        "name": "Cloud Monitoring",
        "description": "Dashboards, alerting policies, uptime checks, and notification channels",
        "category": "monitoring",
        "providers": ["gcp"],
        "chips": ["Cloud Monitoring", "Alerts", "Dashboards", "Uptime Checks"],
        "prompt": (
            "Set up Cloud Monitoring with: "
            "1) Dashboard with JSON layout (google_monitoring_dashboard). "
            "2) Notification channel (email, PagerDuty, or Slack webhook via variable). "
            "3) Alert policy for high CPU (> 80%) with configurable duration and notification channels. "
            "4) Alert policy for high memory usage. "
            "5) Uptime check (HTTP/HTTPS) for a configurable URL with check interval. "
            "6) Alert on uptime check failure. "
            "7) Log-based metric for error rate. "
            "8) SLO monitoring (optional). "
            "Output the dashboard ID, alert policy names, uptime check ID, and notification channel name."
        ),
        "parameters": [
            {
                "name": "display_name",
                "label": "Dashboard Name",
                "type": "text",
                "required": True,
                "default": "Application Dashboard",
            },
            {
                "name": "period",
                "label": "Alignment Period",
                "type": "select",
                "required": True,
                "default": "60s",
                "options": [
                    {"value": "60s", "label": "1 Minute"},
                    {"value": "300s", "label": "5 Minutes"},
                    {"value": "3600s", "label": "1 Hour"},
                ],
            },
        ],
    },
    {
        "id": "gcp_pub_sub",
        "name": "Pub/Sub Messaging",
        "description": "Messaging with DLQ, ordering, schema validation, and BigQuery sink",
        "category": "messaging",
        "providers": ["gcp"],
        "chips": ["Pub/Sub", "Topics", "Subscriptions", "Schema"],
        "prompt": (
            "Create Pub/Sub messaging with: "
            "1) Topic with configurable message retention duration and KMS encryption. "
            "2) Schema resource for message validation (optional, Avro or Protocol Buffers). "
            "3) Pull subscription with configurable ack deadline, message retention, and expiration policy. "
            "4) Dead letter topic and subscription with max_delivery_attempts. "
            "5) Message ordering enabled (optional). "
            "6) Push subscription option (endpoint URL variable). "
            "7) BigQuery subscription option for analytics (optional). "
            "8) IAM bindings for publisher and subscriber roles. "
            "Output the topic ID, subscription ID, DLT topic ID, and DLT subscription ID."
        ),
        "parameters": [
            {
                "name": "message_retention_duration",
                "label": "Message Retention",
                "type": "text",
                "required": True,
                "default": "604800s",
                "description": "Duration (e.g., 604800s for 7 days)",
            },
            {
                "name": "ack_deadline_seconds",
                "label": "Ack Deadline (seconds)",
                "type": "number",
                "required": True,
                "default": 20,
                "min": 10,
                "max": 600,
            },
            {
                "name": "retain_acked_messages",
                "label": "Retain Acked Messages",
                "type": "select",
                "required": True,
                "default": "false",
                "options": [
                    {"value": "true", "label": "Yes"},
                    {"value": "false", "label": "No"},
                ],
            },
        ],
    },
]


# ─────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────

def get_template_catalog(provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all templates, optionally filtered by provider."""
    if not provider:
        return TEMPLATE_CATALOG
    provider = provider.lower()
    return [t for t in TEMPLATE_CATALOG if provider in t.get("providers", [])]


def get_templates_by_category(
    category: Optional[str] = None,
    provider: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return templates grouped by category."""
    templates = get_template_catalog(provider)
    if category:
        return {category: [t for t in templates if t.get("category") == category]}
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for t in templates:
        cat = t.get("category", "other")
        grouped.setdefault(cat, []).append(t)
    return grouped


def get_template_by_id(template_id: str) -> Optional[Dict[str, Any]]:
    """Look up a template by its unique ID."""
    for t in TEMPLATE_CATALOG:
        if t["id"] == template_id:
            return t
    return None


def compose_template_request(
    template_id: str,
    provider: str,
    region: Optional[str] = None,
    template_inputs: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Build the full natural-language prompt sent to the LLM code generator.

    Returns:
        (prompt_text, template_display_name)
    """
    template = get_template_by_id(template_id)
    if not template:
        raise ValueError(f"Invalid template_id: {template_id}")

    providers = [p.lower() for p in template.get("providers", [])]
    if provider.lower() not in providers:
        raise ValueError(
            f"Template '{template_id}' does not support provider '{provider}'"
        )

    # Assemble prompt parts
    parts: List[str] = [
        _PRODUCTION_PREAMBLE,
        template.get("prompt", "").strip(),
        f"Provider: {provider.upper()}.",
    ]
    if region:
        parts.append(f"Region: {region}.")

    if template_inputs:
        kvs = [
            f"{k}={v}" for k, v in template_inputs.items() if v not in (None, "")
        ]
        if kvs:
            parts.append("Inputs: " + ", ".join(kvs) + ".")

    return " ".join(parts), template["name"]