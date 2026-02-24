"""aws_service.py — TerraBot: Live AWS account context for conversation LLM prompts."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

# Services whose quotas we care about — checked opportunistically
_QUOTA_SERVICE_MAP = {
    "ec2":         ("Amazon EC2",            "L-1216C47A"),  # Running On-Demand Standard Instances
    "rds":         ("Amazon Relational Database Service", "L-7B6409FD"),  # DB instances
    "elasticache": ("Amazon ElastiCache",    "L-058D2F1A"),  # nodes
    "s3":          ("Amazon S3",             None),           # no quota needed — unlimited buckets
    "vpc":         ("Amazon VPC",            "L-F678F1CE"),  # VPCs per region
}

# Permissions that many IAM users legitimately lack.
# These errors should NEVER surface as WARNING spam in logs.
_SILENTLY_IGNORED_ACTIONS = {
    "servicequotas:GetServiceQuota",
    "servicequotas:ListServiceQuotas",
    "ec2:DescribeAccountAttributes",
    "iam:GetAccountSummary",
    "sts:GetCallerIdentity",
}


class AWSService:
    """Lightweight AWS account inspector used to enrich LLM conversation context."""

    def __init__(self) -> None:
        self._clients: Dict[str, Any] = {}

    # ── Client management ─────────────────────────────────────────────────────

    def _client(self, service: str, region: Optional[str] = None) -> Any:
        region = region or config.AWS_REGION or "us-east-1"
        key    = f"{service}:{region}"
        if key not in self._clients:
            try:
                kwargs: Dict[str, Any] = {"region_name": region}
                if config.AWS_ACCESS_KEY_ID:
                    kwargs["aws_access_key_id"]     = config.AWS_ACCESS_KEY_ID
                    kwargs["aws_secret_access_key"]  = config.AWS_SECRET_ACCESS_KEY
                if getattr(config, "AWS_SESSION_TOKEN", None):
                    kwargs["aws_session_token"] = config.AWS_SESSION_TOKEN
                self._clients[key] = boto3.client(service, **kwargs)
            except Exception as e:
                logger.debug("Could not create boto3 client for %s/%s: %s", service, region, e)
                return None
        return self._clients[key]

    # ── Permission-safe callers ───────────────────────────────────────────────

    def _safe_call(self, service: str, method: str, region: Optional[str] = None, **kwargs) -> Optional[Any]:
        """
        Call an AWS API method. Returns None (with debug log only) for:
          - AccessDenied / UnauthorizedOperation
          - NoCredentialsError
          - EndpointConnectionError (no network)
          - Any other ClientError

        This prevents WARNING spam in logs for legitimately restricted IAM users.
        """
        client = self._client(service, region)
        if not client:
            return None
        try:
            return getattr(client, method)(**kwargs)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            action = f"{service}:{method}"
            if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation",
                        "AuthorizationError", "AuthFailure"):
                # Silently skip — the IAM user simply doesn't have this permission
                logger.debug(
                    "AWS permission denied for %s (%s) — skipping. "
                    "Grant %s to enable live account context.",
                    action, code, action,
                )
            elif code == "OptInRequired":
                logger.debug("AWS service %s not enabled in region — skipping.", service)
            else:
                logger.debug("AWS API error %s.%s: %s %s", service, method, code,
                             e.response.get("Error", {}).get("Message", ""))
        except NoCredentialsError:
            logger.debug("AWS credentials not configured — skipping live context.")
        except EndpointConnectionError:
            logger.debug("Cannot reach AWS endpoint for %s — skipping live context.", service)
        except Exception as e:
            logger.debug("Unexpected error calling %s.%s: %s", service, method, e)
        return None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_caller_identity(self) -> Optional[Dict[str, str]]:
        result = self._safe_call("sts", "get_caller_identity")
        if result:
            return {
                "account_id": result.get("Account", "unknown"),
                "arn":        result.get("Arn", ""),
                "user_id":    result.get("UserId", ""),
            }
        return None

    def get_available_regions(self, service: str = "ec2") -> List[str]:
        result = self._safe_call("ec2", "describe_regions", Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}])
        if result:
            return sorted(r["RegionName"] for r in result.get("Regions", []))
        return []

    def get_service_quota(self, service_code: str, quota_code: str, region: Optional[str] = None) -> Optional[float]:
        """
        Fetch a service quota. Returns None silently if:
          - The IAM user lacks servicequotas:GetServiceQuota
          - The quota doesn't exist in this region
        Never logs a WARNING — this is always optional/best-effort.
        """
        result = self._safe_call(
            "service-quotas", "get_service_quota",
            region=region,
            ServiceCode=service_code,
            QuotaCode=quota_code,
        )
        if result:
            return result.get("Quota", {}).get("Value")
        return None

    def get_ec2_limits(self, region: Optional[str] = None) -> Dict[str, Any]:
        limits: Dict[str, Any] = {}

        # Running instance count (DescribeInstances) — usually allowed
        result = self._safe_call(
            "ec2", "describe_instances",
            region=region,
            Filters=[{"Name": "instance-state-name", "Values": ["running", "pending"]}],
        )
        if result:
            count = sum(
                len(r.get("Instances", []))
                for res in result.get("Reservations", [])
                for r in [res]
            )
            limits["running_instances"] = count

        # Free tier quota — opportunistic, no warning on denial
        quota = self.get_service_quota("ec2", "L-1216C47A", region=region)
        if quota is not None:
            limits["instance_quota"] = int(quota)

        return limits

    def get_rds_limits(self, region: Optional[str] = None) -> Dict[str, Any]:
        limits: Dict[str, Any] = {}
        result = self._safe_call("rds", "describe_db_instances", region=region)
        if result:
            limits["db_instance_count"] = len(result.get("DBInstances", []))
        return limits

    def get_s3_info(self) -> Dict[str, Any]:
        result = self._safe_call("s3", "list_buckets")
        if result:
            return {"bucket_count": len(result.get("Buckets", []))}
        return {}

    def get_vpc_info(self, region: Optional[str] = None) -> Dict[str, Any]:
        result = self._safe_call("ec2", "describe_vpcs", region=region)
        if result:
            vpcs = result.get("Vpcs", [])
            default = next((v for v in vpcs if v.get("IsDefault")), None)
            return {
                "vpc_count":        len(vpcs),
                "default_vpc_id":   default.get("VpcId") if default else None,
                "default_vpc_cidr": default.get("CidrBlock") if default else None,
            }
        return {}

    def get_key_pairs(self, region: Optional[str] = None) -> List[str]:
        result = self._safe_call("ec2", "describe_key_pairs", region=region)
        if result:
            return [kp["KeyName"] for kp in result.get("KeyPairs", [])]
        return []

    def get_free_tier_status(self, region: Optional[str] = None) -> Dict[str, Any]:
        """
        Best-effort check of free tier usage.
        All sub-calls use _safe_call so no permission errors surface as warnings.
        """
        status: Dict[str, Any] = {}

        ec2 = self.get_ec2_limits(region)
        if ec2:
            status["ec2"] = ec2

        rds = self.get_rds_limits(region)
        if rds:
            status["rds"] = rds

        s3 = self.get_s3_info()
        if s3:
            status["s3"] = s3

        vpc = self.get_vpc_info(region)
        if vpc:
            status["vpc"] = vpc

        return status

    def format_for_prompt(self, region: Optional[str] = None) -> str:
        """
        Returns a compact string summarising live AWS account state.
        Designed to be injected into the LLM conversation system prompt.

        SAFE: never raises, never logs warnings for permission errors.
        Returns "" if credentials aren't configured or all calls are denied.
        """
        region = region or config.AWS_REGION or "us-east-1"

        # Quick bail if no credentials at all
        if not config.AWS_ACCESS_KEY_ID:
            return ""

        lines: List[str] = []

        # Identity
        identity = self.get_caller_identity()
        if identity:
            lines.append(f"AWS Account: {identity['account_id']} | ARN: {identity['arn']}")

        lines.append(f"Target Region: {region}")

        # EC2
        ec2 = self.get_ec2_limits(region)
        if ec2:
            running   = ec2.get("running_instances", "unknown")
            quota     = ec2.get("instance_quota")
            quota_str = f" / {int(quota)} quota" if quota else ""
            lines.append(f"EC2 Running instances: {running}{quota_str}")

        # VPC
        vpc = self.get_vpc_info(region)
        if vpc.get("default_vpc_id"):
            lines.append(
                f"Default VPC: {vpc['default_vpc_id']} ({vpc.get('default_vpc_cidr', '')})"
            )
        elif vpc.get("vpc_count") is not None:
            lines.append(f"VPCs in region: {vpc['vpc_count']} (no default VPC detected)")

        # Key pairs
        keys = self.get_key_pairs(region)
        if keys:
            lines.append(f"EC2 Key Pairs: {', '.join(keys[:10])}")
        else:
            lines.append("EC2 Key Pairs: none found — user will need to create or skip (SSM)")

        # RDS
        rds = self.get_rds_limits(region)
        if rds.get("db_instance_count") is not None:
            lines.append(f"RDS instances: {rds['db_instance_count']}")

        # S3
        s3 = self.get_s3_info()
        if s3.get("bucket_count") is not None:
            lines.append(f"S3 buckets: {s3['bucket_count']}")

        if not lines:
            return ""

        return "\n\nLIVE AWS ACCOUNT CONTEXT:\n" + "\n".join(f"  {l}" for l in lines) + "\n"


# Module-level singleton
aws_service = AWSService()