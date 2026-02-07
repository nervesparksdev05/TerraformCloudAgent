"""
Security validation for Terraform configurations
"""
import re
from typing import Tuple
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class SecurityChecker:
    """Static security validation for Terraform code"""
    
    # AWS Allowed Resources (15 core services)
    AWS_ALLOWED_RESOURCES = {
        # Compute
        "aws_instance", "aws_key_pair", "aws_eip", "aws_eip_association",
        "aws_lambda_function", "aws_lambda_permission", "aws_lambda_layer_version",
        "aws_ecs_cluster", "aws_ecs_service", "aws_ecs_task_definition",
        # Storage
        "aws_s3_bucket", "aws_s3_bucket_versioning", 
        "aws_s3_bucket_server_side_encryption_configuration",
        "aws_s3_bucket_public_access_block", "aws_s3_bucket_policy", "aws_s3_object",
        "aws_ebs_volume", "aws_volume_attachment",
        # Database
        "aws_db_instance", "aws_db_subnet_group", "aws_db_parameter_group",
        "aws_dynamodb_table",
        # Networking
        "aws_vpc", "aws_subnet", "aws_route_table", "aws_route_table_association",
        "aws_route", "aws_nat_gateway", "aws_internet_gateway",
        "aws_security_group", "aws_security_group_rule",
        "aws_lb", "aws_lb_listener", "aws_lb_target_group", "aws_lb_target_group_attachment",
        # Security
        "aws_iam_role", "aws_iam_policy", "aws_iam_role_policy_attachment",
        "aws_iam_instance_profile", "aws_iam_user", "aws_iam_group",
        "aws_iam_policy_document",  # data source
        # Integration
        "aws_api_gateway_rest_api", "aws_api_gateway_resource",
        "aws_api_gateway_method", "aws_api_gateway_integration",
        "aws_api_gateway_deployment", "aws_api_gateway_stage",
        "aws_lambda_permission", "aws_sqs_queue", "aws_sns_topic",
        "aws_sns_topic_subscription",
    }
    
    # GCP Allowed Resources (15 core services)
    GCP_ALLOWED_RESOURCES = {
        # Compute
        "google_compute_instance", "google_compute_instance_template",
        "google_compute_instance_group", "google_compute_instance_group_manager",
        "google_cloudfunctions_function", "google_cloudfunctions_function_iam_member",
        "google_cloud_run_service", "google_cloud_run_service_iam_member",
        # Storage
        "google_storage_bucket", "google_storage_bucket_iam_member",
        "google_storage_bucket_object", "google_storage_bucket_versioning",
        "google_compute_disk", "google_compute_attached_disk",
        # Database
        "google_sql_database_instance", "google_sql_database", "google_sql_user",
        "google_firestore_database", "google_firestore_document", "google_firestore_index",
        # Networking
        "google_compute_network", "google_compute_subnetwork",
        "google_compute_router", "google_compute_router_nat",
        "google_compute_firewall", "google_compute_address",
        "google_compute_global_address", "google_compute_backend_service",
        "google_compute_url_map", "google_compute_target_http_proxy",
        "google_compute_target_https_proxy", "google_compute_forwarding_rule",
        "google_compute_health_check",
        # Security
        "google_service_account", "google_service_account_key",
        "google_project_iam_member", "google_project_iam_binding",
        "google_storage_bucket_iam_member",
        # Integration
        "google_pubsub_topic", "google_pubsub_subscription",
        "google_pubsub_topic_iam_member", "google_cloud_scheduler_job",
    }
    
    # Prohibited keywords that indicate unsafe operations
    PROHIBITED_KEYWORDS = {
        "provisioner",
        "null_resource",
        "local-exec",
        "remote-exec",
        "file(",
        "templatefile(",
        "external"
    }
    
    @classmethod
    def validate(cls, bundle: TerraformBundle, provider: str) -> Tuple[bool, str]:
        """
        Validate Terraform bundle for security compliance
        
        Args:
            bundle: TerraformBundle to validate
            provider: Cloud provider ("aws" or "gcp")
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        logger.info(f"Validating {provider.upper()} Terraform code")
        
        # Combine all Terraform code
        all_code = f"{bundle.main_tf}\n{bundle.variables_tf}\n{bundle.outputs_tf}"
        
        # Select allowed resources based on provider
        allowed_resources = (
            cls.AWS_ALLOWED_RESOURCES if provider == "aws"
            else cls.GCP_ALLOWED_RESOURCES
        )
        
        # Check 1: Prohibited keywords
        found_keyword = cls._check_prohibited_keywords(all_code)
        if found_keyword:
            error = f"Prohibited keyword found: '{found_keyword}'"
            logger.warning(f"Security check failed: {error}")
            return False, error
        
        # Check 2: Resource validation
        invalid_resource = cls._validate_resources(all_code, allowed_resources)
        if invalid_resource:
            error = f"Resource type not allowed: '{invalid_resource}'"
            logger.warning(f"Security check failed: {error}")
            return False, error
        
        # Check 3: Hardcoded credentials
        if cls._check_hardcoded_credentials(all_code):
            error = "Hardcoded credentials detected"
            logger.warning(f"Security check failed: {error}")
            return False, error
        
        logger.info("Security validation passed")
        return True, ""
    
    @classmethod
    def _validate_resources(cls, code: str, allowed_resources: set) -> str:
        """Check if only allowed resources are used. Returns invalid resource type or empty string."""
        # Extract resource types using regex
        resource_pattern = r'resource\s+"([^"]+)"'
        found_resources = re.findall(resource_pattern, code)
        
        for resource_type in found_resources:
            if resource_type not in allowed_resources:
                logger.warning(f"Disallowed resource type: {resource_type}")
                return resource_type
        return ""
    
    @classmethod
    def _check_prohibited_keywords(cls, code: str) -> str:
        """Check for prohibited keywords. Returns found keyword or empty string."""
        code_lower = code.lower()
        for keyword in cls.PROHIBITED_KEYWORDS:
            if keyword.lower() in code_lower:
                return keyword
        return ""
    
    @classmethod
    def _check_hardcoded_credentials(cls, code: str) -> bool:
        """Check for hardcoded credentials"""
        credential_patterns = [
            r'password\s*=\s*"[^$]',  # Hardcoded password (not variable)
            r'secret\s*=\s*"[^$]',    # Hardcoded secret
            r'AWS_SECRET_ACCESS_KEY',  # AWS credentials
            r'private_key\s*=\s*"[^$]',  # Private keys
        ]
        
        for pattern in credential_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return True
        return False
