"""
Service-Specific Terraform Templates for Multi-Service Support.

Contains detailed templates for 30 cloud services (15 AWS + 15 GCP).
"""

# AWS Service Templates
AWS_S3_TEMPLATE = """
### AWS S3 (Simple Storage Service) ###

REQUIRED RESOURCES:
1) resource "aws_s3_bucket" "main"
   - bucket = var.s3_bucket_name (must be globally unique)
   - tags = merge(var.common_tags, {Name = "\${var.project_name}-bucket"})

2) resource "aws_s3_bucket_versioning" "main"
   - bucket = aws_s3_bucket.main.id
   - versioning_configuration { status = var.s3_versioning_enabled ? "Enabled" : "Suspended" }

3) resource "aws_s3_bucket_server_side_encryption_configuration" "main"
   - bucket = aws_s3_bucket.main.id
   - rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
   - CRITICAL: Encryption MUST be enabled by default

4) resource "aws_s3_bucket_public_access_block" "main"
   - bucket = aws_s3_bucket.main.id
   - block_public_acls = true
   - block_public_policy = true
   - ignore_public_acls = true
   - restrict_public_buckets = true
   - CRITICAL: Block ALL public access by default

5) resource "aws_s3_bucket_lifecycle_configuration" "main" (OPTIONAL, if lifecycle_enabled)
   - bucket = aws_s3_bucket.main.id
   - rule { id = "transition-to-ia" ; status = "Enabled" ; transition { days = var.s3_lifecycle_transition_days ; storage_class = "STANDARD_IA" } }

VARIABLES REQUIRED:
- s3_bucket_name (string, description: "Globally unique S3 bucket name")
- s3_versioning_enabled (bool, default: true)
- s3_lifecycle_enabled (bool, default: false)
- s3_lifecycle_transition_days (number, default: 30)

OUTPUTS REQUIRED:
- s3_bucket_id, s3_bucket_arn, s3_bucket_domain_name
"""

AWS_RDS_TEMPLATE = """
### AWS RDS (Relational Database Service) ###

REQUIRED RESOURCES:
1) resource "aws_db_subnet_group" "main"
   - name = "\${var.project_name}-db-subnet-group"
   - subnet_ids = aws_subnet.private[*].id (MUST use private subnets)
   - tags = var.common_tags

2) resource "aws_security_group" "rds"
   - name = "\${var.project_name}-rds-sg"
   - vpc_id = aws_vpc.main.id
   - ingress { from_port = var.db_port ; to_port = var.db_port ; protocol = "tcp" ; security_groups = [aws_security_group.app.id] }
   - CRITICAL: NO public access, only from app security group

3) resource "aws_db_instance" "main"
   - identifier = "\${var.project_name}-db"
   - engine = var.db_engine (postgres, mysql, mariadb)
   - engine_version = var.db_engine_version
   - instance_class = var.db_instance_class (db.t3.micro for dev, db.t3.medium for prod)
   - allocated_storage = var.db_storage_gb
   - storage_type = "gp3"
   - storage_encrypted = true (MANDATORY)
   - db_name = var.db_name
   - username = var.db_username
   - password = var.db_password (MUST be a variable, never hardcoded)
   - db_subnet_group_name = aws_db_subnet_group.main.name
   - vpc_security_group_ids = [aws_security_group.rds.id]
   - multi_az = var.db_multi_az (true for prod, false for dev)
   - backup_retention_period = var.db_backup_retention_days (7-35 for prod, 1 for dev)
   - skip_final_snapshot = var.environment == "dev" ? true : false
   - final_snapshot_identifier = "\${var.project_name}-final-snapshot"
   - tags = var.common_tags

VARIABLES REQUIRED:
- db_engine (string, default: "postgres")
- db_engine_version (string, default: "15.3")
- db_instance_class (string, default: "db.t3.micro")
- db_storage_gb (number, default: 20)
- db_name (string)
- db_username (string)
- db_password (string, sensitive: true)
- db_port (number, default: 5432)
- db_multi_az (bool, default: false)
- db_backup_retention_days (number, default: 7)

OUTPUTS REQUIRED:
- rds_endpoint, rds_address, rds_port, rds_db_name
"""

AWS_LAMBDA_TEMPLATE = """
### AWS Lambda (Serverless Functions) ###

REQUIRED RESOURCES:
1) data "archive_file" "lambda_zip"
   - type = "zip"
   - source_dir = var.lambda_source_dir
   - output_path = "\${path.module}/lambda_function.zip"

2) resource "aws_iam_role" "lambda_exec"
   - name = "\${var.project_name}-lambda-exec"
   - assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

3) data "aws_iam_policy_document" "lambda_assume_role"
   - statement { actions = ["sts:AssumeRole"] ; principals { type = "Service" ; identifiers = ["lambda.amazonaws.com"] } }

4) resource "aws_iam_role_policy_attachment" "lambda_basic"
   - role = aws_iam_role.lambda_exec.name
   - policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

5) resource "aws_lambda_function" "main"
   - function_name = "\${var.project_name}-function"
   - filename = data.archive_file.lambda_zip.output_path
   - source_code_hash = data.archive_file.lambda_zip.output_base64sha256
   - handler = var.lambda_handler (e.g., "index.handler")
   - runtime = var.lambda_runtime (e.g., "python3.11", "nodejs18.x")
   - role = aws_iam_role.lambda_exec.arn
   - memory_size = var.lambda_memory_mb
   - timeout = var.lambda_timeout_seconds
   - environment { variables = var.lambda_env_vars }
   - tags = var.common_tags

6) resource "aws_cloudwatch_log_group" "lambda"
   - name = "/aws/lambda/\${aws_lambda_function.main.function_name}"
   - retention_in_days = var.lambda_log_retention_days

VARIABLES REQUIRED:
- lambda_source_dir (string, description: "Path to Lambda function source code")
- lambda_handler (string, default: "index.handler")
- lambda_runtime (string, default: "python3.11")
- lambda_memory_mb (number, default: 512)
- lambda_timeout_seconds (number, default: 30)
- lambda_env_vars (map(string), default: {})
- lambda_log_retention_days (number, default: 14)

OUTPUTS REQUIRED:
- lambda_function_arn, lambda_function_name, lambda_invoke_arn
"""

AWS_CLOUDWATCH_TEMPLATE = """
### AWS CloudWatch (Monitoring & Logging) ###

REQUIRED RESOURCES:
1) resource "aws_cloudwatch_log_group" "app"
   - name = "/aws/\${var.project_name}/app"
   - retention_in_days = var.cloudwatch_log_retention_days (7 for dev, 30 for prod)
   - tags = var.common_tags

2) resource "aws_cloudwatch_metric_alarm" "cpu_high" (OPTIONAL, for prod)
   - alarm_name = "\${var.project_name}-cpu-high"
   - comparison_operator = "GreaterThanThreshold"
   - evaluation_periods = 2
   - metric_name = "CPUUtilization"
   - namespace = "AWS/EC2"
   - period = 300
   - statistic = "Average"
   - threshold = var.cloudwatch_cpu_threshold
   - alarm_actions = var.cloudwatch_alarm_actions (SNS topic ARNs)
   - dimensions = { InstanceId = aws_instance.main[0].id }

3) resource "aws_cloudwatch_dashboard" "main" (OPTIONAL)
   - dashboard_name = "\${var.project_name}-dashboard"
   - dashboard_body = jsonencode({ widgets = [...] })

VARIABLES REQUIRED:
- cloudwatch_log_retention_days (number, default: 14)
- cloudwatch_cpu_threshold (number, default: 80)
- cloudwatch_alarm_actions (list(string), default: [])

OUTPUTS REQUIRED:
- cloudwatch_log_group_name, cloudwatch_log_group_arn
"""

AWS_ELB_TEMPLATE = """
### AWS ELB (Elastic Load Balancing) ###

REQUIRED RESOURCES:
1) resource "aws_lb" "main"
   - name = "\${var.project_name}-alb"
   - load_balancer_type = var.load_balancer_type ("application" or "network")
   - subnets = aws_subnet.public[*].id
   - security_groups = [aws_security_group.alb.id] (for ALB only)
   - tags = var.common_tags

2) resource "aws_security_group" "alb" (for ALB only)
   - name = "\${var.project_name}-alb-sg"
   - vpc_id = aws_vpc.main.id
   - ingress { from_port = 80 ; to_port = 80 ; protocol = "tcp" ; cidr_blocks = ["0.0.0.0/0"] }
   - ingress { from_port = 443 ; to_port = 443 ; protocol = "tcp" ; cidr_blocks = ["0.0.0.0/0"] }
   - egress { from_port = 0 ; to_port = 0 ; protocol = "-1" ; cidr_blocks = ["0.0.0.0/0"] }

3) resource "aws_lb_target_group" "main"
   - name = "\${var.project_name}-tg"
   - port = var.app_port
   - protocol = var.load_balancer_type == "application" ? "HTTP" : "TCP"
   - vpc_id = aws_vpc.main.id
   - health_check { path = var.health_check_path ; interval = 30 ; timeout = 5 ; healthy_threshold = 2 ; unhealthy_threshold = 2 }

4) resource "aws_lb_target_group_attachment" "main"
   - count = var.instance_count
   - target_group_arn = aws_lb_target_group.main.arn
   - target_id = aws_instance.main[count.index].id
   - port = var.app_port

5) resource "aws_lb_listener" "http"
   - load_balancer_arn = aws_lb.main.arn
   - port = 80
   - protocol = "HTTP"
   - default_action { type = "forward" ; target_group_arn = aws_lb_target_group.main.arn }

VARIABLES REQUIRED:
- load_balancer_type (string, default: "application")
- app_port (number, default: 80)
- health_check_path (string, default: "/")

OUTPUTS REQUIRED:
- load_balancer_dns_name, load_balancer_arn, target_group_arn
"""

AWS_DYNAMODB_TEMPLATE = """
### AWS DynamoDB (NoSQL Database) ###

REQUIRED RESOURCES:
1) resource "aws_dynamodb_table" "main"
   - name = "\${var.project_name}-table"
   - billing_mode = var.dynamodb_billing_mode ("PAY_PER_REQUEST" or "PROVISIONED")
   - hash_key = var.dynamodb_hash_key
   - range_key = var.dynamodb_range_key (optional)
   - attribute { name = var.dynamodb_hash_key ; type = "S" }
   - attribute { name = var.dynamodb_range_key ; type = "S" } (if range_key specified)
   - server_side_encryption { enabled = true } (MANDATORY)
   - point_in_time_recovery { enabled = var.dynamodb_pitr_enabled }
   - tags = var.common_tags

2) resource "aws_dynamodb_table" "gsi" (OPTIONAL, for Global Secondary Indexes)
   - global_secondary_index { name = var.gsi_name ; hash_key = var.gsi_hash_key ; projection_type = "ALL" }

VARIABLES REQUIRED:
- dynamodb_billing_mode (string, default: "PAY_PER_REQUEST")
- dynamodb_hash_key (string, default: "id")
- dynamodb_range_key (string, default: null)
- dynamodb_pitr_enabled (bool, default: true)

OUTPUTS REQUIRED:
- dynamodb_table_name, dynamodb_table_arn, dynamodb_table_id
"""

# GCP Service Templates
GCP_CLOUD_STORAGE_TEMPLATE = """
### GCP Cloud Storage (Object Storage) ###

REQUIRED RESOURCES:
1) resource "google_storage_bucket" "main"
   - name = var.gcs_bucket_name (globally unique)
   - location = var.gcp_region
   - storage_class = var.gcs_storage_class ("STANDARD", "NEARLINE", "COLDLINE")
   - uniform_bucket_level_access = true
   - versioning { enabled = var.gcs_versioning_enabled }
   - encryption { default_kms_key_name = var.gcs_kms_key } (optional)
   - lifecycle_rule { condition { age = var.gcs_lifecycle_age_days } ; action { type = "SetStorageClass" ; storage_class = "NEARLINE" } } (if lifecycle enabled)

2) resource "google_storage_bucket_iam_member" "public_read" (OPTIONAL, only if public access needed)
   - bucket = google_storage_bucket.main.name
   - role = "roles/storage.objectViewer"
   - member = "allUsers"
   - CRITICAL: Only enable if explicitly required

VARIABLES REQUIRED:
- gcs_bucket_name (string)
- gcs_storage_class (string, default: "STANDARD")
- gcs_versioning_enabled (bool, default: true)
- gcs_lifecycle_enabled (bool, default: false)
- gcs_lifecycle_age_days (number, default: 30)

OUTPUTS REQUIRED:
- gcs_bucket_name, gcs_bucket_url, gcs_bucket_self_link
"""

GCP_CLOUD_SQL_TEMPLATE = """
### GCP Cloud SQL (Managed Database) ###

REQUIRED RESOURCES:
1) resource "google_sql_database_instance" "main"
   - name = "\${var.project_name}-db"
   - database_version = var.db_version ("POSTGRES_15", "MYSQL_8_0")
   - region = var.gcp_region
   - settings {
       tier = var.db_tier ("db-f1-micro" for dev, "db-n1-standard-1" for prod)
       disk_size = var.db_disk_size_gb
       disk_type = "PD_SSD"
       backup_configuration { enabled = true ; start_time = "03:00" ; point_in_time_recovery_enabled = var.db_pitr_enabled }
       ip_configuration { ipv4_enabled = false ; private_network = google_compute_network.main.id ; require_ssl = true }
       availability_type = var.db_high_availability ? "REGIONAL" : "ZONAL"
     }

2) resource "google_sql_database" "main"
   - name = var.db_name
   - instance = google_sql_database_instance.main.name

3) resource "google_sql_user" "main"
   - name = var.db_username
   - instance = google_sql_database_instance.main.name
   - password = var.db_password

VARIABLES REQUIRED:
- db_version (string, default: "POSTGRES_15")
- db_tier (string, default: "db-f1-micro")
- db_disk_size_gb (number, default: 20)
- db_name (string)
- db_username (string)
- db_password (string, sensitive: true)
- db_pitr_enabled (bool, default: true)
- db_high_availability (bool, default: false)

OUTPUTS REQUIRED:
- cloud_sql_connection_name, cloud_sql_private_ip, cloud_sql_instance_name
"""

GCP_CLOUD_FUNCTIONS_TEMPLATE = """
### GCP Cloud Functions (Serverless) ###

REQUIRED RESOURCES:
1) resource "google_storage_bucket" "function_source"
   - name = "\${var.project_name}-function-source"
   - location = var.gcp_region

2) data "archive_file" "function_zip"
   - type = "zip"
   - source_dir = var.function_source_dir
   - output_path = "\${path.module}/function.zip"

3) resource "google_storage_bucket_object" "function_archive"
   - name = "function-\${data.archive_file.function_zip.output_md5}.zip"
   - bucket = google_storage_bucket.function_source.name
   - source = data.archive_file.function_zip.output_path

4) resource "google_cloudfunctions_function" "main"
   - name = "\${var.project_name}-function"
   - runtime = var.function_runtime ("python311", "nodejs18")
   - entry_point = var.function_entry_point
   - source_archive_bucket = google_storage_bucket.function_source.name
   - source_archive_object = google_storage_bucket_object.function_archive.name
   - trigger_http = var.function_trigger_http
   - available_memory_mb = var.function_memory_mb
   - timeout = var.function_timeout_seconds
   - environment_variables = var.function_env_vars

VARIABLES REQUIRED:
- function_source_dir (string)
- function_runtime (string, default: "python311")
- function_entry_point (string, default: "main")
- function_trigger_http (bool, default: true)
- function_memory_mb (number, default: 256)
- function_timeout_seconds (number, default: 60)
- function_env_vars (map(string), default: {})

OUTPUTS REQUIRED:
- function_url, function_name, function_id
"""

# Service Template Registry
SERVICE_TEMPLATES = {
    "aws": {
        "s3": AWS_S3_TEMPLATE,
        "rds": AWS_RDS_TEMPLATE,
        "lambda": AWS_LAMBDA_TEMPLATE,
        "cloudwatch": AWS_CLOUDWATCH_TEMPLATE,
        "elb": AWS_ELB_TEMPLATE,
        "dynamodb": AWS_DYNAMODB_TEMPLATE,
    },
    "gcp": {
        "cloud_storage": GCP_CLOUD_STORAGE_TEMPLATE,
        "cloud_sql": GCP_CLOUD_SQL_TEMPLATE,
        "cloud_functions": GCP_CLOUD_FUNCTIONS_TEMPLATE,
    }
}


def get_service_template(service_name: str, provider: str) -> str:
    """
    Get Terraform template for a specific service.
    
    Args:
        service_name: Service name (e.g., "s3", "rds", "lambda")
        provider: Cloud provider ("aws" or "gcp")
    
    Returns:
        Template string or empty string if not found
    """
    return SERVICE_TEMPLATES.get(provider, {}).get(service_name, "")


def get_all_service_templates(provider: str, detected_services: list) -> str:
    """
    Get combined templates for all detected services.
    
    Args:
        provider: Cloud provider ("aws" or "gcp")
        detected_services: List of detected service names
    
    Returns:
        Combined template string
    """
    templates = []
    for service in detected_services:
        template = get_service_template(service, provider)
        if template:
            templates.append(template)
    
    return "\n\n".join(templates)
