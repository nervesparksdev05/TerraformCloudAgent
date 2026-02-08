"""
Script to add comprehensive parameters to all remaining 26 templates.
This will be manually integrated into templates_catalog.py
"""

# Template parameters for remaining AWS services
AWS_TEMPLATE_PARAMETERS = {
    "aws_dynamodb_table": [
        {"name": "billing_mode", "label": "Billing Mode", "type": "select", "required": True, "default": "PAY_PER_REQUEST",
         "options": [
             {"value": "PAY_PER_REQUEST", "label": "On-Demand (Pay per request)"},
             {"value": "PROVISIONED", "label": "Provisioned (Fixed capacity)"},
         ]},
        {"name": "read_capacity", "label": "Read Capacity Units", "type": "number", "required": False, "default": 5, "min": 1, "max": 40000,
         "description": "Only for Provisioned mode"},
        {"name": "write_capacity", "label": "Write Capacity Units", "type": "number", "required": False, "default": 5, "min": 1, "max": 40000,
         "description": "Only for Provisioned mode"},
        {"name": "enable_encryption", "label": "Encryption at Rest", "type": "select", "required": True, "default": "true",
         "options": [
             {"value": "true", "label": "Enabled (AWS managed key)"},
             {"value": "false", "label": "Disabled"},
         ]},
    ],
    
    "aws_ecs_cluster": [
        {"name": "launch_type", "label": "Launch Type", "type": "select", "required": True, "default": "FARGATE",
         "options": [
             {"value": "FARGATE", "label": "Fargate (Serverless)"},
             {"value": "EC2", "label": "EC2 (Manage instances)"},
         ]},
        {"name": "cpu", "label": "CPU Units", "type": "select", "required": True, "default": "256",
         "options": [
             {"value": "256", "label": "0.25 vCPU"},
             {"value": "512", "label": "0.5 vCPU"},
             {"value": "1024", "label": "1 vCPU"},
             {"value": "2048", "label": "2 vCPU"},
             {"value": "4096", "label": "4 vCPU"},
         ]},
        {"name": "memory", "label": "Memory (MB)", "type": "select", "required": True, "default": "512",
         "options": [
             {"value": "512", "label": "512 MB"},
             {"value": "1024", "label": "1 GB"},
             {"value": "2048", "label": "2 GB"},
             {"value": "4096", "label": "4 GB"},
             {"value": "8192", "label": "8 GB"},
         ]},
    ],
    
    "aws_eks_cluster": [
        {"name": "kubernetes_version", "label": "Kubernetes Version", "type": "select", "required": True, "default": "1.28",
         "options": [
             {"value": "1.28", "label": "1.28 (Latest)"},
             {"value": "1.27", "label": "1.27"},
             {"value": "1.26", "label": "1.26"},
         ]},
        {"name": "node_instance_type", "label": "Node Instance Type", "type": "select", "required": True, "default": "t3.medium",
         "options": [
             {"value": "t3.medium", "label": "t3.medium (2 vCPU, 4 GB RAM)"},
             {"value": "t3.large", "label": "t3.large (2 vCPU, 8 GB RAM)"},
             {"value": "m5.large", "label": "m5.large (2 vCPU, 8 GB RAM)"},
             {"value": "m5.xlarge", "label": "m5.xlarge (4 vCPU, 16 GB RAM)"},
         ]},
        {"name": "desired_nodes", "label": "Desired Node Count", "type": "number", "required": True, "default": 2, "min": 1, "max": 100},
        {"name": "max_nodes", "label": "Maximum Node Count", "type": "number", "required": True, "default": 4, "min": 1, "max": 100},
    ],
    
    "aws_vpc_network": [
        {"name": "cidr_block", "label": "VPC CIDR Block", "type": "select", "required": True, "default": "10.0.0.0/16",
         "options": [
             {"value": "10.0.0.0/16", "label": "10.0.0.0/16 (65,536 IPs)"},
             {"value": "172.16.0.0/16", "label": "172.16.0.0/16 (65,536 IPs)"},
             {"value": "192.168.0.0/16", "label": "192.168.0.0/16 (65,536 IPs)"},
         ]},
        {"name": "enable_dns", "label": "Enable DNS Support", "type": "select", "required": True, "default": "true",
         "options": [
             {"value": "true", "label": "Enabled"},
             {"value": "false", "label": "Disabled"},
         ]},
        {"name": "subnet_count", "label": "Number of Subnets", "type": "number", "required": True, "default": 2, "min": 1, "max": 10},
    ],
    
    "aws_alb_loadbalancer": [
        {"name": "load_balancer_type", "label": "Load Balancer Type", "type": "select", "required": True, "default": "application",
         "options": [
             {"value": "application", "label": "Application Load Balancer (HTTP/HTTPS)"},
             {"value": "network", "label": "Network Load Balancer (TCP/UDP)"},
         ]},
        {"name": "enable_deletion_protection", "label": "Deletion Protection", "type": "select", "required": True, "default": "false",
         "options": [
             {"value": "true", "label": "Enabled"},
             {"value": "false", "label": "Disabled"},
         ]},
        {"name": "enable_http2", "label": "HTTP/2 Support", "type": "select", "required": True, "default": "true",
         "options": [
             {"value": "true", "label": "Enabled"},
             {"value": "false", "label": "Disabled"},
         ]},
    ],
}

# GCP Template parameters
GCP_TEMPLATE_PARAMETERS = {
    "gcp_compute_instance": [
        {"name": "machine_type", "label": "Machine Type", "type": "select", "required": True, "default": "e2-micro",
         "options": [
             {"value": "e2-micro", "label": "e2-micro (0.25 vCPU, 1 GB RAM)"},
             {"value": "e2-small", "label": "e2-small (0.5 vCPU, 2 GB RAM)"},
             {"value": "e2-medium", "label": "e2-medium (1 vCPU, 4 GB RAM)"},
             {"value": "n1-standard-1", "label": "n1-standard-1 (1 vCPU, 3.75 GB RAM)"},
             {"value": "n1-standard-2", "label": "n1-standard-2 (2 vCPU, 7.5 GB RAM)"},
         ]},
        {"name": "boot_disk_size", "label": "Boot Disk Size (GB)", "type": "number", "required": True, "default": 20, "min": 10, "max": 10000},
        {"name": "boot_disk_type", "label": "Boot Disk Type", "type": "select", "required": True, "default": "pd-standard",
         "options": [
             {"value": "pd-standard", "label": "Standard Persistent Disk"},
             {"value": "pd-balanced", "label": "Balanced Persistent Disk"},
             {"value": "pd-ssd", "label": "SSD Persistent Disk"},
         ]},
    ],
    
    "gcp_cloud_function": [
        {"name": "runtime", "label": "Runtime", "type": "select", "required": True, "default": "python312",
         "options": [
             {"value": "python312", "label": "Python 3.12"},
             {"value": "python311", "label": "Python 3.11"},
             {"value": "nodejs20", "label": "Node.js 20"},
             {"value": "nodejs18", "label": "Node.js 18"},
             {"value": "go121", "label": "Go 1.21"},
             {"value": "java17", "label": "Java 17"},
         ]},
        {"name": "memory", "label": "Memory (MB)", "type": "select", "required": True, "default": "256",
         "options": [
             {"value": "128", "label": "128 MB"},
             {"value": "256", "label": "256 MB"},
             {"value": "512", "label": "512 MB"},
             {"value": "1024", "label": "1 GB"},
             {"value": "2048", "label": "2 GB"},
         ]},
        {"name": "timeout", "label": "Timeout (seconds)", "type": "number", "required": True, "default": 60, "min": 1, "max": 540},
    ],
    
    "gcp_cloud_sql": [
        {"name": "database_version", "label": "Database Version", "type": "select", "required": True, "default": "POSTGRES_15",
         "options": [
             {"value": "POSTGRES_15", "label": "PostgreSQL 15"},
             {"value": "POSTGRES_14", "label": "PostgreSQL 14"},
             {"value": "MYSQL_8_0", "label": "MySQL 8.0"},
             {"value": "MYSQL_5_7", "label": "MySQL 5.7"},
             {"value": "SQLSERVER_2019_STANDARD", "label": "SQL Server 2019 Standard"},
         ]},
        {"name": "tier", "label": "Machine Type", "type": "select", "required": True, "default": "db-f1-micro",
         "options": [
             {"value": "db-f1-micro", "label": "db-f1-micro (0.6 GB RAM)"},
             {"value": "db-g1-small", "label": "db-g1-small (1.7 GB RAM)"},
             {"value": "db-n1-standard-1", "label": "db-n1-standard-1 (3.75 GB RAM)"},
             {"value": "db-n1-standard-2", "label": "db-n1-standard-2 (7.5 GB RAM)"},
         ]},
        {"name": "disk_size", "label": "Storage (GB)", "type": "number", "required": True, "default": 10, "min": 10, "max": 65536},
        {"name": "backup_enabled", "label": "Automated Backups", "type": "select", "required": True, "default": "true",
         "options": [
             {"value": "true", "label": "Enabled"},
             {"value": "false", "label": "Disabled"},
         ]},
    ],
    
    "gcp_storage_bucket": [
        {"name": "storage_class", "label": "Storage Class", "type": "select", "required": True, "default": "STANDARD",
         "options": [
             {"value": "STANDARD", "label": "Standard (Frequent access)"},
             {"value": "NEARLINE", "label": "Nearline (Once per month)"},
             {"value": "COLDLINE", "label": "Coldline (Once per quarter)"},
             {"value": "ARCHIVE", "label": "Archive (Once per year)"},
         ]},
        {"name": "versioning", "label": "Object Versioning", "type": "select", "required": True, "default": "true",
         "options": [
             {"value": "true", "label": "Enabled"},
             {"value": "false", "label": "Disabled"},
         ]},
        {"name": "public_access", "label": "Public Access Prevention", "type": "select", "required": True, "default": "enforced",
         "options": [
             {"value": "enforced", "label": "Enforced (Recommended)"},
             {"value": "inherited", "label": "Inherited from organization"},
         ]},
    ],
    
    "gcp_gke_cluster": [
        {"name": "kubernetes_version", "label": "Kubernetes Version", "type": "select", "required": True, "default": "latest",
         "options": [
             {"value": "latest", "label": "Latest stable"},
             {"value": "1.28", "label": "1.28"},
             {"value": "1.27", "label": "1.27"},
         ]},
        {"name": "node_machine_type", "label": "Node Machine Type", "type": "select", "required": True, "default": "e2-medium",
         "options": [
             {"value": "e2-medium", "label": "e2-medium (1 vCPU, 4 GB RAM)"},
             {"value": "e2-standard-2", "label": "e2-standard-2 (2 vCPU, 8 GB RAM)"},
             {"value": "n1-standard-2", "label": "n1-standard-2 (2 vCPU, 7.5 GB RAM)"},
         ]},
        {"name": "node_count", "label": "Initial Node Count", "type": "number", "required": True, "default": 3, "min": 1, "max": 100},
        {"name": "enable_autoscaling", "label": "Autoscaling", "type": "select", "required": True, "default": "true",
         "options": [
             {"value": "true", "label": "Enabled"},
             {"value": "false", "label": "Disabled"},
         ]},
    ],
}

print("Template parameters ready for integration!")
print(f"AWS templates with parameters: {len(AWS_TEMPLATE_PARAMETERS)}")
print(f"GCP templates with parameters: {len(GCP_TEMPLATE_PARAMETERS)}")
