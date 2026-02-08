"""
Security validation for Terraform configurations.

Aligned with the production-grade template catalog (30 templates: 15 AWS + 15 GCP)
and the AWS/GCP system prompts.
"""
from __future__ import annotations

import re
from typing import List, Set, Tuple

from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class SecurityChecker:
    """Static security validation for generated Terraform code."""

    # ─────────────────────────────────────────────────────────
    # AWS Allowed Resources
    # Covers all 15 AWS templates + supporting resources
    # ─────────────────────────────────────────────────────────
    AWS_ALLOWED_RESOURCES: Set[str] = {
        # ── Compute: EC2 ──
        "aws_instance",
        "aws_key_pair",
        "aws_eip",
        "aws_eip_association",
        "aws_ami",                          # data source referenced as resource in some patterns
        "aws_ami_copy",
        "aws_placement_group",
        # ── Compute: Lambda ──
        "aws_lambda_function",
        "aws_lambda_permission",
        "aws_lambda_layer_version",
        "aws_lambda_event_source_mapping",
        "aws_lambda_alias",
        "aws_lambda_function_url",
        # ── Compute: ECS ──
        "aws_ecs_cluster",
        "aws_ecs_cluster_capacity_providers",
        "aws_ecs_service",
        "aws_ecs_task_definition",
        "aws_ecs_capacity_provider",
        "aws_ecs_account_setting_default",
        # ── Compute: EKS ──
        "aws_eks_cluster",
        "aws_eks_node_group",
        "aws_eks_addon",
        "aws_eks_fargate_profile",
        "aws_eks_identity_provider_config",
        # ── TLS & Cryptography ──
        "tls_private_key",
        "tls_self_signed_cert",
        "tls_locally_signed_cert",
        "tls_cert_request",
        # ── Utilities ──
        "random_id",
        "random_password",
        "random_string",
        "random_shuffle",
        "random_pet",
        "random_integer",
        "time_sleep",
        "time_static",
        # ── Archive (Lambda packaging) ──
        "archive_file",
        # ── Auto Scaling (EC2) ──
        "aws_launch_configuration",
        "aws_launch_template",
        "aws_autoscaling_group",
        "aws_autoscaling_policy",
        "aws_autoscaling_schedule",
        "aws_autoscaling_attachment",
        # ── Application Auto Scaling (ECS / DynamoDB) ──
        "aws_appautoscaling_target",
        "aws_appautoscaling_policy",
        "aws_appautoscaling_scheduled_action",
        # ── Storage: S3 ──
        "aws_s3_bucket",
        "aws_s3_bucket_versioning",
        "aws_s3_bucket_server_side_encryption_configuration",
        "aws_s3_bucket_public_access_block",
        "aws_s3_bucket_policy",
        "aws_s3_object",
        "aws_s3_bucket_lifecycle_configuration",
        "aws_s3_bucket_cors_configuration",
        "aws_s3_bucket_logging",
        "aws_s3_bucket_notification",
        "aws_s3_bucket_ownership_controls",
        "aws_s3_bucket_acl",
        "aws_s3_bucket_website_configuration",
        "aws_s3_bucket_intelligent_tiering_configuration",
        # ── Storage: EBS ──
        "aws_ebs_volume",
        "aws_ebs_encryption_by_default",
        "aws_volume_attachment",
        "aws_ebs_snapshot",
        # ── Database: RDS ──
        "aws_db_instance",
        "aws_db_subnet_group",
        "aws_db_parameter_group",
        "aws_db_option_group",
        "aws_db_snapshot",
        "aws_db_event_subscription",
        "aws_rds_cluster",
        "aws_rds_cluster_instance",
        "aws_rds_cluster_parameter_group",
        # ── Database: DynamoDB ──
        "aws_dynamodb_table",
        "aws_dynamodb_table_item",
        "aws_dynamodb_global_table",
        "aws_dynamodb_contributor_insights",
        "aws_dynamodb_kinesis_streaming_destination",
        # ── Networking: VPC ──
        "aws_vpc",
        "aws_subnet",
        "aws_route_table",
        "aws_route_table_association",
        "aws_route",
        "aws_nat_gateway",
        "aws_internet_gateway",
        "aws_egress_only_internet_gateway",
        "aws_vpc_endpoint",
        "aws_vpc_peering_connection",
        "aws_vpc_dhcp_options",
        "aws_vpc_dhcp_options_association",
        "aws_flow_log",
        # ── Networking: Security ──
        "aws_security_group",
        "aws_security_group_rule",
        "aws_vpc_security_group_ingress_rule",
        "aws_vpc_security_group_egress_rule",
        "aws_network_acl",
        "aws_network_acl_rule",
        "aws_network_acl_association",
        # ── Networking: Load Balancing ──
        "aws_lb",
        "aws_lb_listener",
        "aws_lb_listener_rule",
        "aws_lb_listener_certificate",
        "aws_lb_target_group",
        "aws_lb_target_group_attachment",
        "aws_alb",                          # legacy alias
        "aws_alb_listener",                 # legacy alias
        "aws_alb_target_group",             # legacy alias
        "aws_elb",
        # ── CloudFront & CDN ──
        "aws_cloudfront_distribution",
        "aws_cloudfront_origin_access_identity",
        "aws_cloudfront_origin_access_control",
        "aws_cloudfront_cache_policy",
        "aws_cloudfront_origin_request_policy",
        "aws_cloudfront_response_headers_policy",
        "aws_cloudfront_function",
        "aws_cloudfront_monitoring_subscription",
        # ── Route53 & DNS ──
        "aws_route53_zone",
        "aws_route53_record",
        "aws_route53_health_check",
        "aws_route53_query_log",
        # ── Security & IAM ──
        "aws_iam_role",
        "aws_iam_policy",
        "aws_iam_role_policy",
        "aws_iam_role_policy_attachment",
        "aws_iam_instance_profile",
        "aws_iam_user",
        "aws_iam_group",
        "aws_iam_policy_document",
        "aws_iam_openid_connect_provider",
        "aws_iam_service_linked_role",
        # ── KMS ──
        "aws_kms_key",
        "aws_kms_alias",
        "aws_kms_grant",
        # ── ACM (Certificates) ──
        "aws_acm_certificate",
        "aws_acm_certificate_validation",
        # ── CloudWatch & Monitoring ──
        "aws_cloudwatch_log_group",
        "aws_cloudwatch_log_stream",
        "aws_cloudwatch_log_metric_filter",
        "aws_cloudwatch_log_subscription_filter",
        "aws_cloudwatch_metric_alarm",
        "aws_cloudwatch_composite_alarm",
        "aws_cloudwatch_dashboard",
        "aws_cloudwatch_event_rule",
        "aws_cloudwatch_event_target",
        "aws_cloudwatch_query_definition",
        # ── SNS & SQS ──
        "aws_sns_topic",
        "aws_sns_topic_subscription",
        "aws_sns_topic_policy",
        "aws_sqs_queue",
        "aws_sqs_queue_policy",
        "aws_sqs_queue_redrive_policy",
        "aws_sqs_queue_redrive_allow_policy",
        # ── API Gateway v1 (REST) ──
        "aws_api_gateway_rest_api",
        "aws_api_gateway_resource",
        "aws_api_gateway_method",
        "aws_api_gateway_integration",
        "aws_api_gateway_deployment",
        "aws_api_gateway_stage",
        "aws_api_gateway_method_response",
        "aws_api_gateway_integration_response",
        "aws_api_gateway_authorizer",
        "aws_api_gateway_api_key",
        "aws_api_gateway_usage_plan",
        "aws_api_gateway_usage_plan_key",
        "aws_api_gateway_method_settings",
        "aws_api_gateway_account",
        "aws_api_gateway_domain_name",
        "aws_api_gateway_base_path_mapping",
        # ── API Gateway v2 (HTTP / WebSocket) ──
        "aws_apigatewayv2_api",
        "aws_apigatewayv2_stage",
        "aws_apigatewayv2_route",
        "aws_apigatewayv2_integration",
        "aws_apigatewayv2_authorizer",
        "aws_apigatewayv2_domain_name",
        "aws_apigatewayv2_api_mapping",
        "aws_apigatewayv2_deployment",
        "aws_apigatewayv2_vpc_link",
        # ── WAF ──
        "aws_wafv2_web_acl",
        "aws_wafv2_web_acl_association",
        # ── Secrets Manager ──
        "aws_secretsmanager_secret",
        "aws_secretsmanager_secret_version",
        # ── SSM Parameter Store ──
        "aws_ssm_parameter",
    }

    # ─────────────────────────────────────────────────────────
    # GCP Allowed Resources
    # Covers all 15 GCP templates + supporting resources
    # ─────────────────────────────────────────────────────────
    GCP_ALLOWED_RESOURCES: Set[str] = {
        # ── Compute: Compute Engine ──
        "google_compute_instance",
        "google_compute_instance_template",
        "google_compute_instance_group",
        "google_compute_instance_group_manager",
        "google_compute_region_instance_group_manager",
        "google_compute_autoscaler",
        "google_compute_region_autoscaler",
        "google_compute_image",             # data source
        "google_compute_instance_iam_member",
        # ── Compute: Cloud Functions ──
        "google_cloudfunctions_function",
        "google_cloudfunctions_function_iam_member",
        "google_cloudfunctions2_function",
        "google_cloudfunctions2_function_iam_member",
        # ── Compute: Cloud Run ──
        "google_cloud_run_service",
        "google_cloud_run_service_iam_member",
        "google_cloud_run_service_iam_binding",
        "google_cloud_run_service_iam_policy",
        "google_cloud_run_v2_service",
        "google_cloud_run_v2_service_iam_member",
        "google_cloud_run_v2_service_iam_binding",
        "google_cloud_run_v2_job",
        "google_cloud_run_domain_mapping",
        # ── Kubernetes: GKE ──
        "google_container_cluster",
        "google_container_node_pool",
        "google_container_registry",
        # ── Storage: Cloud Storage ──
        "google_storage_bucket",
        "google_storage_bucket_iam_member",
        "google_storage_bucket_iam_binding",
        "google_storage_bucket_iam_policy",
        "google_storage_bucket_object",
        "google_storage_bucket_access_control",
        "google_storage_default_object_access_control",
        "google_storage_notification",
        # ── Storage: Persistent Disk ──
        "google_compute_disk",
        "google_compute_attached_disk",
        "google_compute_snapshot",
        "google_compute_resource_policy",
        # ── Database: Cloud SQL ──
        "google_sql_database_instance",
        "google_sql_database",
        "google_sql_user",
        "google_sql_ssl_cert",
        "google_sql_source_representation_instance",
        # ── Database: Firestore ──
        "google_firestore_database",
        "google_firestore_document",
        "google_firestore_index",
        "google_firestore_backup_schedule",
        "google_firestore_field",
        # ── Database: Bigtable ──
        "google_bigtable_instance",
        "google_bigtable_table",
        # ── Networking: VPC ──
        "google_compute_network",
        "google_compute_subnetwork",
        "google_compute_router",
        "google_compute_router_nat",
        "google_compute_route",
        "google_compute_network_peering",
        # ── Networking: Firewall ──
        "google_compute_firewall",
        # ── Networking: Addresses ──
        "google_compute_address",
        "google_compute_global_address",
        # ── Networking: Load Balancing ──
        "google_compute_forwarding_rule",
        "google_compute_global_forwarding_rule",
        "google_compute_target_http_proxy",
        "google_compute_target_https_proxy",
        "google_compute_target_tcp_proxy",
        "google_compute_url_map",
        "google_compute_backend_service",
        "google_compute_region_backend_service",
        "google_compute_backend_bucket",
        "google_compute_health_check",
        "google_compute_http_health_check",
        "google_compute_https_health_check",
        "google_compute_region_health_check",
        "google_compute_target_pool",
        # ── Networking: SSL ──
        "google_compute_ssl_certificate",
        "google_compute_managed_ssl_certificate",
        "google_compute_ssl_policy",
        # ── Networking: Cloud Armor ──
        "google_compute_security_policy",
        # ── DNS ──
        "google_dns_managed_zone",
        "google_dns_record_set",
        "google_dns_policy",
        # ── Security & IAM ──
        "google_service_account",
        "google_service_account_key",
        "google_service_account_iam_member",
        "google_service_account_iam_binding",
        "google_service_account_iam_policy",
        "google_project_iam_member",
        "google_project_iam_binding",
        "google_project_iam_custom_role",
        "google_organization_iam_custom_role",
        # ── KMS ──
        "google_kms_key_ring",
        "google_kms_crypto_key",
        "google_kms_crypto_key_iam_member",
        "google_kms_crypto_key_iam_binding",
        # ── Monitoring & Logging ──
        "google_monitoring_alert_policy",
        "google_monitoring_notification_channel",
        "google_monitoring_dashboard",
        "google_monitoring_uptime_check_config",
        "google_monitoring_group",
        "google_monitoring_custom_service",
        "google_monitoring_slo",
        "google_logging_project_sink",
        "google_logging_metric",
        "google_logging_project_bucket_config",
        # ── Pub/Sub ──
        "google_pubsub_topic",
        "google_pubsub_topic_iam_member",
        "google_pubsub_topic_iam_binding",
        "google_pubsub_subscription",
        "google_pubsub_subscription_iam_member",
        "google_pubsub_subscription_iam_binding",
        "google_pubsub_schema",
        "google_pubsub_lite_topic",
        "google_pubsub_lite_subscription",
        # ── Cloud Scheduler ──
        "google_cloud_scheduler_job",
        # ── API Gateway ──
        "google_api_gateway_api",
        "google_api_gateway_api_config",
        "google_api_gateway_api_config_iam_member",
        "google_api_gateway_gateway",
        "google_api_gateway_gateway_iam_member",
        # ── Service Networking (Cloud SQL private IP) ──
        "google_service_networking_connection",
        # ── Project Services (API enablement) ──
        "google_project_service",
        # ── VPC Access Connector (Cloud Run / Functions) ──
        "google_vpc_access_connector",
        # ── Artifact Registry ──
        "google_artifact_registry_repository",
        "google_artifact_registry_repository_iam_member",
        # ── Secret Manager ──
        "google_secret_manager_secret",
        "google_secret_manager_secret_version",
        "google_secret_manager_secret_iam_member",
        "google_secret_manager_secret_iam_binding",
        # ── Utilities ──
        "random_id",
        "random_password",
        "random_string",
        "random_shuffle",
        "random_pet",
        "random_integer",
        "time_sleep",
        "time_static",
        # ── Archive ──
        "archive_file",
    }

    # ─────────────────────────────────────────────────────────
    # Prohibited patterns
    # ─────────────────────────────────────────────────────────

    # Keywords that MUST NOT appear anywhere in generated code
    PROHIBITED_KEYWORDS: Set[str] = {
        "provisioner",
        "null_resource",
        "local-exec",
        "remote-exec",
    }

    # Regex patterns for hard-coded credentials
    _CREDENTIAL_PATTERNS: List[re.Pattern] = [
        # Hard-coded password/secret (not a variable reference)
        re.compile(r'password\s*=\s*"(?!\$\{)[^"]{4,}"', re.IGNORECASE),
        re.compile(r'secret\s*=\s*"(?!\$\{)[^"]{4,}"', re.IGNORECASE),
        re.compile(r'secret_key\s*=\s*"(?!\$\{)[^"]{4,}"', re.IGNORECASE),
        # AWS access key patterns (AKIA...)
        re.compile(r'AKIA[0-9A-Z]{16}'),
        re.compile(r'AWS_SECRET_ACCESS_KEY', re.IGNORECASE),
        re.compile(r'AWS_ACCESS_KEY_ID', re.IGNORECASE),
        # GCP service account key JSON
        re.compile(r'"private_key"\s*:\s*"-----BEGIN'),
        re.compile(r'"client_email"\s*:\s*"[^"]+@[^"]+\.iam\.gserviceaccount\.com"'),
        # Private key inline (not a variable)
        re.compile(r'private_key\s*=\s*"(?!\$\{)-----BEGIN'),
        # Generic API key / token patterns (32+ hex/alphanum string literals)
        re.compile(r'(?:api_key|token|auth_token)\s*=\s*"(?!\$\{)[A-Za-z0-9/+=]{32,}"', re.IGNORECASE),
    ]

    # Patterns for insecure SSH/RDP access
    _INSECURE_ACCESS_PATTERNS: List[re.Pattern] = [
        # 0.0.0.0/0 with SSH port 22
        re.compile(
            r'(?:from_port|port)\s*=\s*22.*?cidr[_a-z]*\s*=\s*\[?\s*"0\.0\.0\.0/0"',
            re.DOTALL | re.IGNORECASE,
        ),
        re.compile(
            r'cidr[_a-z]*\s*=\s*\[?\s*"0\.0\.0\.0/0".*?(?:from_port|port)\s*=\s*22',
            re.DOTALL | re.IGNORECASE,
        ),
        # 0.0.0.0/0 with RDP port 3389
        re.compile(
            r'(?:from_port|port)\s*=\s*3389.*?cidr[_a-z]*\s*=\s*\[?\s*"0\.0\.0\.0/0"',
            re.DOTALL | re.IGNORECASE,
        ),
        re.compile(
            r'cidr[_a-z]*\s*=\s*\[?\s*"0\.0\.0\.0/0".*?(?:from_port|port)\s*=\s*3389',
            re.DOTALL | re.IGNORECASE,
        ),
        # GCP firewall: 0.0.0.0/0 + port 22 within same block
        re.compile(
            r'source_ranges\s*=\s*\[?\s*"0\.0\.0\.0/0".*?ports\s*=\s*\[?\s*"22"',
            re.DOTALL | re.IGNORECASE,
        ),
        re.compile(
            r'ports\s*=\s*\[?\s*"22".*?source_ranges\s*=\s*\[?\s*"0\.0\.0\.0/0"',
            re.DOTALL | re.IGNORECASE,
        ),
    ]

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    @classmethod
    def validate(cls, bundle: TerraformBundle, provider: str) -> Tuple[bool, str]:
        """Validate a Terraform bundle for security compliance.

        Args:
            bundle: TerraformBundle containing main_tf, variables_tf, outputs_tf.
            provider: Cloud provider key ("aws" or "gcp").

        Returns:
            (is_valid, error_message) – error_message is empty when valid.
        """
        logger.info("Validating %s Terraform code", provider.upper())

        all_code = "\n".join([bundle.main_tf, bundle.variables_tf, bundle.outputs_tf])

        allowed_resources = (
            cls.AWS_ALLOWED_RESOURCES if provider == "aws"
            else cls.GCP_ALLOWED_RESOURCES
        )

        # ── Check 1: Prohibited keywords ──
        keyword = cls._check_prohibited_keywords(all_code)
        if keyword:
            msg = f"Prohibited keyword found: '{keyword}'"
            logger.warning("Security check failed: %s", msg)
            return False, msg

        # ── Check 2: Resource allow-list ──
        bad_resource = cls._validate_resources(all_code, allowed_resources)
        if bad_resource:
            msg = f"Resource type not allowed: '{bad_resource}'"
            logger.warning("Security check failed: %s", msg)
            return False, msg

        # ── Check 3: Hard-coded credentials ──
        cred_detail = cls._check_hardcoded_credentials(all_code)
        if cred_detail:
            msg = f"Hardcoded credentials detected: {cred_detail}"
            logger.warning("Security check failed: %s", msg)
            return False, msg

        # ── Check 4: Insecure SSH/RDP access ──
        if cls._check_insecure_remote_access(all_code):
            msg = "Insecure remote access: SSH (22) or RDP (3389) open to 0.0.0.0/0"
            logger.warning("Security check failed: %s", msg)
            return False, msg

        # ── Check 5: Missing encryption (soft warning logged, not blocking) ──
        cls._warn_missing_encryption(all_code, provider)

        logger.info("Security validation passed")
        return True, ""

    # ─────────────────────────────────────────────────────────
    # Internal checks
    # ─────────────────────────────────────────────────────────

    @classmethod
    def _check_prohibited_keywords(cls, code: str) -> str:
        """Return the first prohibited keyword found, or empty string."""
        code_lower = code.lower()
        for keyword in cls.PROHIBITED_KEYWORDS:
            # Match as a distinct token to reduce false positives
            # e.g., "provisioner" should match but "provisioner_name" in a comment is still caught intentionally
            if keyword.lower() in code_lower:
                return keyword
        return ""

    @classmethod
    def _validate_resources(cls, code: str, allowed: Set[str]) -> str:
        """Return the first disallowed resource type, or empty string."""
        resource_pattern = re.compile(r'resource\s+"([^"]+)"\s+"[^"]+"')
        for match in resource_pattern.finditer(code):
            rtype = match.group(1)
            if rtype not in allowed:
                logger.warning("Disallowed resource type: %s", rtype)
                return rtype
        return ""

    @classmethod
    def _check_hardcoded_credentials(cls, code: str) -> str:
        """Return a description of the first credential pattern match, or empty string."""
        for pattern in cls._CREDENTIAL_PATTERNS:
            match = pattern.search(code)
            if match:
                # Return a sanitised snippet (first 60 chars of the match)
                snippet = match.group(0)[:60].strip()
                return f"pattern matched near: '{snippet}...'"
        return ""

    @classmethod
    def _check_insecure_remote_access(cls, code: str) -> bool:
        """Return True if SSH or RDP is open to 0.0.0.0/0."""
        for pattern in cls._INSECURE_ACCESS_PATTERNS:
            if pattern.search(code):
                return True
        return False

    @classmethod
    def _warn_missing_encryption(cls, code: str, provider: str) -> None:
        """Log warnings for common encryption omissions (non-blocking)."""
        if provider == "aws":
            # RDS without storage_encrypted
            if "aws_db_instance" in code and "storage_encrypted" not in code:
                logger.warning("Advisory: aws_db_instance may be missing storage_encrypted = true")
            # S3 without encryption configuration
            if "aws_s3_bucket" in code and "aws_s3_bucket_server_side_encryption_configuration" not in code:
                logger.warning("Advisory: S3 bucket may be missing server-side encryption configuration")
            # EBS volume without encryption
            if "aws_ebs_volume" in code and "encrypted" not in code:
                logger.warning("Advisory: aws_ebs_volume may be missing encrypted = true")
            # DynamoDB without server_side_encryption
            if "aws_dynamodb_table" in code and "server_side_encryption" not in code:
                logger.warning("Advisory: aws_dynamodb_table may be missing server_side_encryption block")
            # CloudWatch Log Group without KMS
            if "aws_cloudwatch_log_group" in code and "kms_key_id" not in code:
                logger.warning("Advisory: aws_cloudwatch_log_group may be missing kms_key_id for encryption")
            # EC2 without IMDSv2
            if "aws_instance" in code and "metadata_options" not in code:
                logger.warning("Advisory: aws_instance may be missing metadata_options (IMDSv2)")

        elif provider == "gcp":
            # Cloud SQL without private IP
            if "google_sql_database_instance" in code and "private_network" not in code:
                logger.warning("Advisory: Cloud SQL instance may be missing private_network configuration")
            # Compute Engine without shielded instance
            if "google_compute_instance" in code and "shielded_instance_config" not in code:
                logger.warning("Advisory: Compute Engine instance may be missing shielded_instance_config")
            # Compute Engine without OS Login
            if "google_compute_instance" in code and "enable-oslogin" not in code:
                logger.warning("Advisory: Compute Engine instance may be missing enable-oslogin metadata")
            # GCS without uniform_bucket_level_access
            if "google_storage_bucket" in code and "uniform_bucket_level_access" not in code:
                logger.warning("Advisory: GCS bucket may be missing uniform_bucket_level_access = true")
            # GCS without public_access_prevention
            if "google_storage_bucket" in code and "public_access_prevention" not in code:
                logger.warning("Advisory: GCS bucket may be missing public_access_prevention = enforced")