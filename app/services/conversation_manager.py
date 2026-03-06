"""conversation_manager.py — TerraBot: Multi-cloud (AWS + GCP) Terraform conversation engine."""
from __future__ import annotations

import asyncio
import json
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.llm_service import AsyncLLMService
from app.services.github_service import GithubService
from app.models.conversation_schemas import ConversationSession, ChatMessageResponse, ConversationStatus
from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

AWS_CORE = ["ec2", "vpc", "security_groups", "iam_roles"]
AWS_TOP15 = AWS_CORE + [
    "s3", "rds", "elasticache", "alb",
    "route53", "cloudwatch", "ebs", "auto_scaling",
    "eks", "sqs", "cloudfront",
]

# ── Prompts ───────────────────────────────────────────────────────────────────

_README_PROMPT = """\
You are a cloud infrastructure analyst. Analyze the following README and extract all
infrastructure-relevant information. Return ONLY valid JSON (no markdown, no explanation).

Extract:
{
  "message": "Brief greeting + what you found in 1-2 sentences",
  "project_name": "",
  "workload_description": "",
  "language": "",
  "current_deployment_platform": "",
  "app_start_command": "",
  "install_command": "",
  "build_command": "",
  "process_manager": "",
  "ports": [{"port": 0, "protocol": "tcp", "description": ""}],
  "runtime_services": [{"name": "", "port": 0}],
  "has_database": false,
  "database_type": "",
  "database_hosting_model": "",
  "database_orm": "",
  "database_connection_env_var": "",
  "has_cache": false,
  "cache_type": "",
  "cache_purpose": "",
  "has_websockets": false,
  "websocket_library": "",
  "has_frontend": false,
  "frontend_type": "",
  "frontend_served_by": "",
  "has_docker": false,
  "docker_services": [],
  "storage_needs": false,
  "storage_description": "",
  "storage_provider": "",
  "background_jobs": false,
  "background_job_description": "",
  "detected_services": [],
  "required_env_vars": [{"name": "", "is_secret": false, "description": ""}],
  "optional_env_vars": [{"name": "", "description": ""}],
  "env_var_groups": {},
  "external_services": [{"name": "", "description": ""}],
  "infrastructure_warnings": [{"severity": "critical|warning|info", "message": "", "recommendation": ""}],
  "extracted_params": {}
}

README:
"""

_SYSTEM = """\
You are TerraBot 🤖 — a senior cloud architect and patient mentor for professional companies deploying websites and web applications on AWS, GCP, or DigitalOcean. Your mission is to guide the user from a GitHub repository to a fully production-grade cloud deployment.

TONE & STYLE:
- BE PROFESSIONAL, warm, and concise.
- BE A MENTOR: Briefly explain WHY each question matters in 1 sentence.
- ONE QUESTION PER TURN — never combine multiple unrelated questions.
- LENGTH: HARD LIMIT — every "message" field MUST be 4-5 lines maximum. No exceptions. Do NOT write paragraphs or long explanations. Count your lines before responding.
- CONCISION: Ask the question and provide 2-3 options max. Nothing more.
- Return ONLY valid JSON — no markdown, no explanation outside JSON.

GLOBAL RULES:
- Never suggest Free Tier-only resources. This agent is for production-grade company deployments.
- Always recommend HA (high availability) for production.
- Capture all answers in extracted_params.
- CRITICAL DEFAULTS: ssh_allowed_cidrs=[], ssh_key_name="", alert_email="".

Return ONLY this JSON every turn:
{"message":"...","extracted_params":{},"is_complete":false,"suggestions":["option1","option2"]}

══════════════════════════════════════════════════════════
CONVERSATION FLOW — STEP 0 (ALWAYS FIRST):
══════════════════════════════════════════════════════════
BEFORE asking anything else, you MUST ask:
  "Which cloud provider would you like to deploy on?"
  Options: AWS, GCP, DigitalOcean
  → Set cloud_provider = "aws", "gcp", or "digitalocean"
  → Then ask: Development or Production?
  → Set environment = "dev" or "production"
  → ALL subsequent questions adapt to the chosen provider.

══════════════════════════════════════════════════════════
AWS DEV FLOW (ask in order, one per turn):
══════════════════════════════════════════════════════════
1.  Region         — which AWS region? (any valid region, e.g. us-east-1, eu-west-1, ap-south-1)
2.  Database       — SQL or NoSQL?
                     SQL   → RDS (PostgreSQL / MySQL / MariaDB) — ask engine choice
                     NoSQL → DynamoDB (serverless) OR DocumentDB (MongoDB-compatible)
                     None  → skip
3.  Cache          — Redis cache needed? (ElastiCache) — ask node type
4.  File Storage   — S3 bucket for uploads/media? — ask bucket name
5.  Domain & SSL   — Custom domain? → Route 53 + ACM SSL cert
6.  CDN            — CloudFront for static frontend assets?
7.  Background Jobs— SQS queue for async tasks (emails, processing)?
8.  Email Sending  — SES for transactional email?
9.  User Auth      — AWS Cognito OR external (Firebase, Auth0, Clerk)?
10. Alerts         — CloudWatch alert email (CPU, errors, latency)?
11. Secrets        — Secrets Manager for env secrets?
12. Server Access  — EC2 key pair name OR SSM Session Manager (no key needed)?
13. SSH CIDR       — IP ranges allowed for SSH? ([] = use SSM only)
14. WAF            — Enable AWS WAF on the load balancer?
→ After all answers collected: set is_complete=true

══════════════════════════════════════════════════════════
AWS PROD FLOW (ask in order, one per turn):
══════════════════════════════════════════════════════════
1.  Region         — which AWS region?
2.  Traffic Scale  — daily active users? (determines instance type, ASG, ALB)
                     <500 DAU       → t3.medium, no ASG
                     500-2000 DAU   → t3.large, ASG 2-4, ALB
                     2000-10000 DAU → t3.xlarge OR c5.xlarge, ASG 3-8, ALB
                     >10000 DAU     → c5.2xlarge OR m5.2xlarge, ASG 4-12, ALB
3.  High Avail.    — Multi-AZ for RDS and ElastiCache? (automatic failover in <60s)
4.  ASG Scaling    — CPU % to trigger scale-out? (recommend 65-70%)
5.  Health Check   — ALB health check path? (/health, /api/health, /)
6.  Database       — SQL or NoSQL?
                     SQL   → RDS Aurora / PostgreSQL / MySQL — ask engine + instance class
                     NoSQL → DynamoDB (serverless) OR DocumentDB — ask pricing mode
                     None  → skip
7.  DB Read Replicas — Add read replicas for read-heavy traffic?
8.  Cache          — ElastiCache Redis? — ask node type (cache.r6g.large recommended for prod)
9.  File Storage   — S3 + versioning + lifecycle rules?
10. CDN            — CloudFront with WAF integration?
11. Domain & SSL   — Custom domain? (Route 53 + ACM)
12. WAF + Shield   — AWS WAF rules + AWS Shield Standard for DDoS?
13. Background Jobs— SQS + Dead Letter Queue for background jobs?
14. Email Sending  — SES for transactional email?
15. User Auth      — AWS Cognito OR external (Firebase, Auth0, Clerk)?
16. Alerts         — CloudWatch alarms + SNS alert email?
17. Secrets        — Secrets Manager for secrets + auto-rotation?
18. Server Access  — EC2 key pair OR SSM Session Manager?
19. SSH CIDR       — IP ranges for SSH?
20. Audit Logs     — CloudTrail + VPC Flow Logs for compliance?
21. VPC Design     — Private subnets for DB/cache (recommended) OR simple public subnet?
→ After all answers: set is_complete=true

══════════════════════════════════════════════════════════
GCP DEV FLOW (ask in order, one per turn):
══════════════════════════════════════════════════════════
1.  Region         — which GCP region? (any valid, e.g. us-central1, europe-west1, asia-south1)
2.  Database       — SQL or NoSQL?
                     SQL   → Cloud SQL (PostgreSQL / MySQL) — ask engine
                     NoSQL → Firestore (document DB) OR Bigtable (wide-column)
                     None  → skip
3.  Cache          — Memorystore Redis needed? — ask tier
4.  File Storage   — Cloud Storage bucket for uploads/media? — ask bucket name
5.  Domain & SSL   — Custom domain? → Cloud DNS + Google-managed SSL cert
6.  CDN            — Cloud CDN for static frontend assets?
7.  Background Jobs— Cloud Tasks for async jobs? OR Pub/Sub for event streaming?
8.  Email Sending  — SendGrid / Mailgun (external, inject as env var)?
9.  User Auth      — Firebase Authentication OR IAP (Identity-Aware Proxy)?
10. Alerts         — Cloud Monitoring alert email + Uptime Checks?
11. Secrets        — Secret Manager for env secrets?
12. VM Access      — SSH key OR IAP Tunnel (no open ports, recommended)?
13. WAF / DDoS     — Cloud Armor for DDoS protection and WAF rules?
→ After all answers: set is_complete=true

══════════════════════════════════════════════════════════
GCP PROD FLOW (ask in order, one per turn):
══════════════════════════════════════════════════════════
1.  Region         — which GCP region?
2.  Traffic Scale  — daily active users?
                     <500 DAU       → e2-standard-2, no MIG
                     500-2000 DAU   → n2-standard-4, Regional MIG 2-4, HTTP(S) LB
                     2000-10000 DAU → n2-standard-8, Regional MIG 3-8, HTTP(S) LB
                     >10000 DAU     → n2-standard-16 OR c2-standard-8, MIG 4-12, HTTP(S) LB
3.  High Avail.    — Regional MIG (multi-zone HA) OR single-zone?
4.  ASG Scaling    — CPU % to trigger autoscaler? (recommend 65-70%)
5.  Health Check   — Health check path? (/health, /api/health, /)
6.  Database       — SQL or NoSQL?
                     SQL   → Cloud SQL HA (PostgreSQL / MySQL) — ask tier + failover replica
                     NoSQL → Firestore (realtime/document) OR Bigtable (analytical) — ask mode
                     None  → skip
7.  DB Read Replicas — Cloud SQL read replicas for read-heavy traffic?
8.  Cache          — Memorystore Redis? — ask tier (STANDARD_HA for prod)
9.  File Storage   — Cloud Storage + versioning + lifecycle policies?
10. CDN            — Cloud CDN + HTTP(S) Global Load Balancer?
11. Domain & SSL   — Custom domain? (Cloud DNS + Certificate Manager)
12. WAF + DDoS     — Cloud Armor (WAF rules + DDoS adaptive protection)?
13. Messaging      — Pub/Sub for event streaming AND/OR Cloud Tasks for async jobs?
14. Email Sending  — SendGrid / Mailgun (injected as env var)?
15. User Auth      — Firebase Authentication OR IAP?
16. Alerts         — Cloud Monitoring + Alerting + Uptime Checks?
17. Secrets        — Secret Manager + automatic rotation?
18. VM Access      — IAP Tunnel (recommended) OR SSH key?
19. Audit Logs     — Cloud Audit Logs + VPC Flow Logs?
20. VPC Design     — Private Google Access for DB/secrets (recommended)?
→ After all answers: set is_complete=true

══════════════════════════════════════════════════════════
DIGITALOCEAN DEV FLOW (ask in order, one per turn):
══════════════════════════════════════════════════════════
1.  Region         — which DO region? (nyc3, sfo3, fra1, sgp1, ams3, blr1, lon1, tor1)
2.  Database       — SQL or NoSQL?
                     SQL   → DO Managed PostgreSQL or MySQL — ask engine
                     NoSQL → DO Managed MongoDB — ask version
                     None  → skip
3.  Cache          — DO Managed Redis needed? — ask node size
4.  File Storage   — DO Spaces (S3-compatible) for uploads/media? — ask bucket name
5.  Domain & SSL   — Custom domain? → DO DNS + Let's Encrypt SSL (free via Certbot on Droplet)
6.  CDN            — DO Spaces CDN for static assets?
7.  Background Jobs— Redis-based queue (Sidekiq, Celery) on same Droplet?
8.  Email Sending  — SendGrid / Mailgun (injected as env var)?
9.  User Auth      — external (Firebase, Auth0) — just inject as env var?
10. Alerts         — DO Monitoring alert email (CPU, disk, memory)?
11. Firewall       — DO Cloud Firewall: allow ports 80, 443, SSH?
12. SSH Key        — your DO SSH key name (must exist in DO account)?
→ After all answers: set is_complete=true

══════════════════════════════════════════════════════════
DIGITALOCEAN PROD FLOW (ask in order, one per turn):
══════════════════════════════════════════════════════════
1.  Region         — which DO region?
2.  Traffic Scale  — daily active users? (determines Droplet plan and scaling)
                     <500 DAU       → s-1vcpu-2gb (1 Droplet, no LB)
                     500-2000 DAU   → s-2vcpu-4gb, DO LB, 2-4 Droplets
                     2000-10000 DAU → s-4vcpu-8gb or c-4, DO LB, 3-8 Droplets
                     >10000 DAU     → c-8 or c2-8vcpu-16gb, DO LB, 4-12 Droplets
3.  High Avail.    — Multiple Droplets behind DO Load Balancer? (Zero-downtime)
4.  Health Check   — LB health check path? (/health, /api/health, /)
5.  Database       — SQL or NoSQL?
                     SQL   → DO Managed PostgreSQL / MySQL — ask plan (basic or production-tier)
                     NoSQL → DO Managed MongoDB — ask plan
                     None  → skip
6.  DB Standby     — DO Managed DB includes automatic standby in production cluster?
7.  Cache          — DO Managed Redis? — ask node plan (db-s-1vcpu-1gb for prod)
8.  File Storage   — DO Spaces + CDN + versioning?
9.  Domain & SSL   — Custom domain? (DO DNS)
10. Firewall       — DO Cloud Firewall (restrict SSH to your IPs)?
11. Background Jobs— Worker Droplet for background jobs (Celery/Sidekiq)?
12. Email Sending  — SendGrid / Mailgun (injected as env var)?
13. Alerts         — DO Monitoring + alert email (CPU, disk, memory)?
14. SSH Key        — your DO SSH key name in DO account?
15. Secrets        — Store secrets in DO App Platform env vars or .env on Droplet?
→ After all answers: set is_complete=true
"""

_BRIDGE = """\
KEY RULES:
1. Be thorough and professional — this is for a company deploying a real product.
2. Explain YOUR reasoning per turn — e.g., "With 2000 DAU you need Auto Scaling because..."
3. suggestions[] must always have 2-4 clear, actionable choices for the current question.
4. ONE question per turn. Never combine multiple unrelated questions.
5. For PROD: traffic sizing (DAU) MUST be the first question after environment + provider.
6. Always return ONLY valid JSON.

COMPLETENESS GATE — before setting is_complete:true, verify:
  ALL DEPLOYMENTS:
  ✅ cloud_provider  — "aws", "gcp", or "digitalocean"
  ✅ environment     — "dev" or "production"

  AWS:
  ✅ aws_region
  ✅ database_type   — engine or "none"
  ✅ has_cache
  ✅ alert_email
  ✅ ssh_key_name
  ✅ ssh_allowed_cidrs

  GCP:
  ✅ gcp_region
  ✅ database_type
  ✅ has_cache
  ✅ alert_email
  ✅ ssh_key_name

  DIGITALOCEAN:
  ✅ do_region
  ✅ database_type   — engine or "none"
  ✅ has_cache
  ✅ alert_email
  ✅ ssh_key_name

  PRODUCTION ONLY (all clouds):
  ✅ daily_active_users
  ✅ traffic_tier
  ✅ use_asg
  ✅ use_alb
  ✅ enable_multi_az

If ANY required field is missing, keep is_complete:false.
"""


# ── Completeness validator ────────────────────────────────────────────────────

def _is_prod(cp: Dict[str, Any]) -> bool:
    return str(cp.get("environment", "")).lower() in ("prod", "production")


def _derive_traffic_params(cp: Dict[str, Any]) -> None:
    """
    Given daily_active_users in cp, auto-set traffic_tier, instance_type/machine_type,
    use_asg, use_alb, and autoscaling_config min/max.
    """
    dau = cp.get("daily_active_users")
    if dau is None:
        return
    try:
        # Handle plain int/float
        dau = int(float(str(dau).strip()))
    except (TypeError, ValueError):
        # LLM sometimes returns ranges like "500-2000 DAU" or "~1000 users"
        # Extract the first number found
        nums = re.findall(r'\d+', str(dau))
        if not nums:
            return
        dau = int(nums[0])
    # Store the sanitized integer back so future calls don't re-parse
    cp["daily_active_users"] = dau

    provider = str(cp.get("cloud_provider", "aws")).lower()
    is_gcp = provider == "gcp"
    is_do  = provider == "digitalocean"

    if dau < 500:
        tier = "low"
        if is_gcp:
            itype = "e2-small"
        elif is_do:
            itype = "s-1vcpu-2gb"
        else:
            itype = "t3.small"
        asg, alb, mn, mx = False, False, 1, 1
    elif dau < 2000:
        tier = "medium"
        if is_gcp:
            itype = "e2-medium"
        elif is_do:
            itype = "s-2vcpu-4gb"
        else:
            itype = "t3.medium"
        asg, alb, mn, mx = True, True, 2, 4
    elif dau < 10000:
        tier = "high"
        if is_gcp:
            itype = "e2-standard-2"
        elif is_do:
            itype = "s-4vcpu-8gb"
        else:
            itype = "t3.large"
        asg, alb, mn, mx = True, True, 3, 8
    else:
        tier = "extreme"
        if is_gcp:
            itype = "e2-standard-4"
        elif is_do:
            itype = "c-8"
        else:
            itype = "t3.xlarge"
        asg, alb, mn, mx = True, True, 4, 12

    cp["traffic_tier"] = tier
    if is_gcp:
        cp["machine_type"] = itype
    elif is_do:
        cp["droplet_size"] = itype
    else:
        cp["instance_type"] = itype

    cp["use_asg"] = asg
    cp["use_alb"] = alb
    cp["instance_count"] = mn

    asg_cfg = cp.setdefault("autoscaling_config", {})
    if not isinstance(asg_cfg, dict):
        asg_cfg = {}
        cp["autoscaling_config"] = asg_cfg
    asg_cfg.setdefault("min_instances", mn)
    asg_cfg.setdefault("max_instances", mx)


def _validate_completeness(cp: Dict[str, Any]) -> List[str]:
    """
    Returns a list of still-missing fields that must be collected before
    is_complete can be set to True.
    """
    missing: List[str] = []
    prod = _is_prod(cp)
    provider = str(cp.get("cloud_provider", "aws")).lower()
    is_gcp = provider == "gcp"
    is_do  = provider == "digitalocean"

    env = str(cp.get("environment", "")).lower()
    if env not in ("dev", "development", "prod", "production"):
        missing.append("environment (dev or production)")

    # ── PRODUCTION-FIRST: traffic must be asked before anything else ──
    if prod:
        if cp.get("daily_active_users") is None:
            missing.append("daily_active_users (e.g. 500 — determines instance size and scaling)")
            return missing

        _derive_traffic_params(cp)

        if cp.get("traffic_tier") is None:
            missing.append("traffic_tier (derived from daily_active_users)")
        if cp.get("use_asg") is None:
            missing.append("use_asg (derived from traffic_tier)")
        if cp.get("use_alb") is None:
            missing.append("use_alb (derived from traffic_tier)")

        tier = cp.get("traffic_tier", "low")
        if tier != "low" and cp.get("enable_multi_az") is None:
            missing.append("enable_multi_az (high availability — required for your traffic level)")

        if cp.get("use_asg"):
            asg = cp.get("autoscaling_config") or {}
            if not asg.get("cpu_threshold"):
                missing.append("autoscaling_config.cpu_threshold (CPU % to trigger scale-out, e.g. 70)")
            if not asg.get("health_check_path"):
                missing.append("autoscaling_config.health_check_path (e.g. /health or /)")

    # ── SHARED fields (both dev and prod) ────────────────────────────────
    if is_gcp:
        if not cp.get("gcp_region") and not cp.get("region"):
            missing.append("gcp_region (e.g. us-central1, us-east1, europe-west1)")
    elif is_do:
        if not cp.get("do_region") and not cp.get("region"):
            missing.append("do_region (e.g. nyc3, sfo3, fra1, sgp1, ams3)")
    else:
        if not cp.get("aws_region") and not cp.get("region"):
            missing.append("aws_region (e.g. us-east-1, us-west-2, eu-west-1)")

    itype = str(cp.get("instance_type") or cp.get("machine_type") or cp.get("droplet_size") or "")
    if not itype:
        if not prod:
            if is_gcp:
                cp["machine_type"] = "e2-micro"
            elif is_do:
                cp["droplet_size"] = "s-1vcpu-2gb"
            else:
                cp["instance_type"] = "t3.micro"
        else:
            if is_gcp:
                label = "machine_type"
            elif is_do:
                label = "droplet_size"
            else:
                label = "instance_type"
            missing.append(f"{label} (will be derived from daily_active_users)")
    elif not is_gcp and not is_do and itype == "t2.micro":
        cp["instance_type"] = "t3.micro"

    if is_gcp:
        if cp.get("iap_tunnel") is None and cp.get("ssh_key_name") is None:
            missing.append("vm_access_method (SSH key name, or confirm IAP Tunnel — recommended for GCP)")
    elif is_do:
        # DO always requires SSH key by name (looked up in DO account)
        if cp.get("ssh_key_name") is None:
            missing.append("ssh_key_name (your DigitalOcean SSH key name)")
    else:
        if cp.get("ssh_key_name") is None and cp.get("key_pair_name") is None:
            missing.append("ssh_key_name (EC2 key pair name, or confirm SSM-only access)")
        if cp.get("ssh_allowed_cidrs") is None:
            missing.append("ssh_allowed_cidrs (your IP for SSH, or [] to configure later)")

    if cp.get("alert_email") is None:
        if is_gcp:
            alert_svc = "Cloud Monitoring"
        elif is_do:
            alert_svc = "DO Monitoring"
        else:
            alert_svc = "CloudWatch"
        missing.append(f"alert_email (for {alert_svc} alerts, or confirm you want to skip)")

    return missing


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int, handling LLM strings like '500-2000 DAU'."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    import re as _re
    nums = _re.findall(r'\d+', str(value))
    return int(nums[0]) if nums else default


class ConversationManager:
    """TerraBot — multi-cloud (AWS + GCP) intelligent Terraform conversation guide."""

    def __init__(self) -> None:
        self.llm_service = AsyncLLMService()
        self.github_service = GithubService()
        self.sessions_collection = self._init_mongo()

    def _init_mongo(self):
        try:
            from pymongo import MongoClient
            uri = getattr(config, "MONGODB_URI", None)
            db  = getattr(config, "MONGODB_DATABASE", None)
            if uri and db:
                return MongoClient(uri)[db]["sessions"]
        except Exception as e:
            logger.error("MongoDB init failed: %s", e)
        return None

    # ── Session lifecycle ──────────────────────────────────────────────────────

    async def create_session(
        self,
        owner: str = "",
        repo: str = "",
        github_token: str = "",
        github_branch: str = "",
    ) -> Dict[str, Any]:
        if self.sessions_collection is None:
            raise RuntimeError("MongoDB not available.")

        sid = f"sess_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"

        if not owner.strip() or not repo.strip():
            return {
                "session_id": sid,
                "bot_response": (
                    "Hey! 👋 I'm **TerraBot** — your cloud Terraform guide.\n"
                    "I'll analyze your GitHub README and generate production-ready infrastructure.\n"
                    "What's your GitHub repo? (e.g., owner: `facebook`, repo: `react`)"
                ),
                "suggestions": [],
            }

        readme = await self._fetch_readme(owner, repo, github_token, github_branch)
        if not readme:
            return {
                "session_id": sid,
                "bot_response": (
                    f"Couldn't fetch the README for **{owner}/{repo}**.\n"
                    "The repo may be private (provide a token) or README is on a different branch."
                ),
                "suggestions": ["Retry with token", "Change branch"],
            }

        analysis  = await self._analyze_readme(readme)
        extracted = analysis.get("extracted_params", {})

        svcs = extracted.get("detected_services", [])
        if not isinstance(svcs, list):
            svcs = []
        for s in AWS_CORE:
            if s not in svcs:
                svcs.append(s)
        extracted["detected_services"] = {"aws": svcs[:15]}
        extracted.update({
            "github_owner":   owner,
            "github_repo":    repo,
            "github_branch":  github_branch,
            "cloud_provider": "aws",  # Default; overridden once user answers Step 0
            "readme_context": self._build_readme_context(readme, extracted, owner, repo),
        })

        self._apply_safe_defaults(extracted)

        greeting = str(analysis.get("message") or "Which cloud provider would you like to deploy on - **AWS**, **GCP**, or **DigitalOcean**?")
        session = ConversationSession(
            session_id=sid, provider="aws",
            messages=[{"role": "assistant", "content": greeting}],
            collected_parameters=extracted,
            is_complete=False, status=ConversationStatus.ACTIVE,
        )
        self.sessions_collection.insert_one(session.dict())
        logger.info("[%s] Session created for %s/%s", sid, owner, repo)
        return {
            "session_id": sid,
            "bot_response": greeting,
            "suggestions": ["AWS", "GCP"],
        }

    async def _fetch_readme(self, owner: str, repo: str, token: str, branch: str) -> str:
        try:
            try:
                return await self.github_service.fetch_readme(
                    owner=owner, repo=repo, token=token, branch=branch)
            except TypeError:
                return await self.github_service.fetch_readme(
                    repo_url=f"https://github.com/{owner}/{repo}", token=token, branch=branch)
        except Exception as e:
            logger.error("README fetch failed: %s", e)
            return ""

    def get_session(self, sid: str) -> Optional[ConversationSession]:
        if self.sessions_collection is None:
            return None
        try:
            data = self.sessions_collection.find_one({"session_id": sid})
            if data:
                data.pop("_id", None)
                return ConversationSession(**data)
        except Exception as e:
            logger.error("get_session %s: %s", sid, e)
        return None

    def _save_session(self, session: ConversationSession) -> None:
        if self.sessions_collection is not None:
            try:
                self.sessions_collection.update_one(
                    {"session_id": session.session_id},
                    {"$set": session.dict(exclude={"_id"})},
                    upsert=True,
                )
            except Exception as e:
                logger.error("save_session failed: %s", e)

    # ── Message processing ─────────────────────────────────────────────────────

    async def process_message(self, session_id: str, user_message: str) -> ChatMessageResponse:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if session.status != ConversationStatus.ACTIVE:
            raise ValueError(f"Session {session_id} not active")

        session.messages.append({"role": "user", "content": user_message})

        raw  = await self._call_llm(session)
        data = self._parse_json(raw)

        self._deep_merge(session.collected_parameters, data["extracted_params"])
        self._consolidate_asg_config(session.collected_parameters)

        if _is_prod(session.collected_parameters):
            _derive_traffic_params(session.collected_parameters)

        self._apply_safe_defaults(session.collected_parameters)

        # ── Completeness gate ──────────────────────────────────────────────
        llm_says_complete = bool(data["is_complete"])
        missing_fields    = _validate_completeness(session.collected_parameters)

        if llm_says_complete and missing_fields:
            logger.warning(
                "[%s] LLM set is_complete=True but %d field(s) still missing: %s",
                session_id, len(missing_fields), missing_fields,
            )
            data["is_complete"] = False
            missing_str = "\n".join(f"  • {f}" for f in missing_fields)
            data["message"] = (
                data["message"].rstrip() +
                f"\n\nBefore I can generate your infrastructure, I still need:\n{missing_str}"
            )

        session.is_complete = bool(data["is_complete"])
        session.updated_at  = datetime.now()

        if session.is_complete:
            self._apply_defaults(session.collected_parameters)
            session.status = ConversationStatus.COMPLETE
            cost = self._calculate_cost(session.collected_parameters)
            provider = str(session.collected_parameters.get("cloud_provider", "aws")).upper()
            data["message"] = (
                f"✅ Perfect! I have everything needed for your {provider} infrastructure.\n\n"
                f"**💰 Cost Estimate:**\n{cost}\n\n"
                "Generating `main.tf`, `variables.tf`, `outputs.tf` and a GitHub Actions workflow now! 🚀"
            )

        session.messages.append({"role": "assistant", "content": data["message"]})
        self._save_session(session)

        return ChatMessageResponse(
            session_id=session_id,
            bot_response=data["message"],
            collected_parameters=session.collected_parameters,
            is_complete=session.is_complete,
            suggestions=data.get("suggestions", []),
        )

    @staticmethod
    def _apply_safe_defaults(cp: Dict[str, Any]) -> None:
        """Replace known bad placeholder values with safe defaults."""
        if cp.get("key_pair_name") == "REPLACE_ME":
            cp["key_pair_name"] = ""
        if cp.get("ssh_key_name") == "REPLACE_ME":
            cp["ssh_key_name"] = ""
        if str(cp.get("alert_email", "")).endswith("REPLACE_ME@example.com"):
            cp["alert_email"] = ""

        cidrs = cp.get("ssh_allowed_cidrs")
        if isinstance(cidrs, list) and cidrs == ["0.0.0.0/0"]:
            cp["ssh_allowed_cidrs"] = []

        if cp.get("instance_type") == "t2.micro":
            cp["instance_type"] = "t3.micro"

        # Sanitize daily_active_users — LLM sometimes returns strings like
        # "500-2000 DAU", "~1000 users", "500-2000", etc. Extract first integer.
        dau = cp.get("daily_active_users")
        if dau is not None and not isinstance(dau, int):
            try:
                cp["daily_active_users"] = int(float(str(dau).strip()))
            except (TypeError, ValueError):
                nums = re.findall(r'\d+', str(dau))
                if nums:
                    cp["daily_active_users"] = int(nums[0])
                else:
                    # Cannot parse at all — remove so the bot re-asks
                    cp.pop("daily_active_users", None)

    @staticmethod
    def _consolidate_asg_config(cp: dict) -> None:
        """Gather ASG sub-keys into 'autoscaling_config'."""
        _ALIASES: dict[str, list[str]] = {
            "min_instances":     ["min_instances", "asg_min", "autoscaling_min", "min_size"],
            "max_instances":     ["max_instances", "asg_max", "autoscaling_max", "max_size"],
            "cpu_threshold":     ["cpu_threshold", "asg_cpu", "cpu_utilization", "cpu_target"],
            "health_check_path": ["health_check_path", "health_check"],
        }
        cfg = cp.setdefault("autoscaling_config", {}) if isinstance(cp.get("autoscaling_config"), dict) else {}
        if not isinstance(cp.get("autoscaling_config"), dict):
            cp["autoscaling_config"] = cfg

        for canonical, aliases in _ALIASES.items():
            if canonical in cfg:
                continue
            for alias in aliases:
                if alias in cp and cp[alias] not in (None, ""):
                    cfg[canonical] = cp.pop(alias)
                    break
        t = cfg.get("cpu_threshold")
        if isinstance(t, (int, float)) and t > 1:
            cfg["cpu_threshold"] = round(t / 100, 2)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        try:
            m = re.search(r'(\{.*\})', raw.strip(), re.DOTALL)
            data = json.loads(m.group(1) if m else raw)
        except Exception:
            data = {}
        data.setdefault("message", "Could you elaborate on that?")
        data.setdefault("extracted_params", {})
        data.setdefault("suggestions", [])
        data.setdefault("is_complete", False)
        if not isinstance(data["extracted_params"], dict):
            data["extracted_params"] = {}
        return data

    # ── LLM call ──────────────────────────────────────────────────────────────

    async def _call_llm(self, session: ConversationSession) -> str:
        cp         = session.collected_parameters
        readme_ctx = str(cp.get("readme_context", ""))[:3500]
        snapshot   = json.dumps(cp, indent=2)
        env        = str(cp.get("environment", "") or "NOT SET").upper()
        turns      = sum(1 for m in session.messages if m["role"] == "user")
        provider   = str(cp.get("cloud_provider", "aws")).lower()

        mode = config.DEPLOYMENT_MODE.upper()
        context = (
            f"\nREADME CONTEXT:\n{readme_ctx}\n\n"
            f"STATE: {provider.upper()} | mode={mode} | env={env} | turn={turns}\n"
            f"COLLECTED:\n{snapshot}\n"
        )

        messages = [
            {"role": "system", "content": _SYSTEM + "\n\n" + _BRIDGE + context + self._svc_hints(session)}
        ]
        for m in session.messages:
            if m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})

        return await self.llm_service.chat_completion(
            messages=messages, temperature=0.5, max_tokens=16000,
            response_format={"type": "json_object"}, timeout=120,
            use_mcp=use_mcp,
        )

    def _svc_hints(self, session: ConversationSession) -> str:
        cp       = session.collected_parameters
        provider = str(cp.get("cloud_provider", "aws")).lower()
        is_gcp   = provider == "gcp"
        is_do    = provider == "digitalocean"

        raw_svcs = cp.get("detected_services") or []
        if isinstance(raw_svcs, dict):
            key = "gcp" if is_gcp else ("do" if is_do else "aws")
            svcs = raw_svcs.get(key, [])
        else:
            svcs = raw_svcs

        prod = _is_prod(cp)
        tier = cp.get("traffic_tier", "")
        dau  = cp.get("daily_active_users")

        pending: List[str] = []

        if not prod:
            # ══ DEV MODE ══
            if is_gcp:
                if not cp.get("gcp_region") and not cp.get("region"):
                    pending.append(
                        "  - GCP Region (REQUIRED): e.g. us-central1 (Iowa), us-east1 (S. Carolina), "
                        "europe-west1 (Belgium). Pick closest to your users."
                    )
                if cp.get("iap_tunnel") is None and cp.get("ssh_key_name") is None:
                    pending.append(
                        "  - VM Access (REQUIRED): Use IAP Tunnel (recommended — no open ports, no key) "
                        "or provide an SSH public key?"
                    )
                if cp.get("alert_email") is None:
                    pending.append(
                        "  - Alert Email: for Cloud Monitoring CPU/error alerts. Say 'skip' to disable."
                    )
                for svc, key, hint in [
                    ("cloud_sql",     "db_config",      "Cloud SQL: engine (PostgreSQL/MySQL), tier (db-f1-micro for dev)"),
                    ("firestore",     "db_config",      "Firestore mode: Native (realtime) or Datastore?"),
                    ("memorystore",   "cache_config",   "Memorystore Redis: tier BASIC, capacity 1 GB for dev"),
                    ("cloud_storage", "storage_config", "Cloud Storage: bucket name, public read yes/no"),
                ]:
                    if svc in svcs and not cp.get(key):
                        pending.append(f"  - {hint}")
            elif is_do:
                # DO dev
                if not cp.get("do_region") and not cp.get("region"):
                    pending.append(
                        "  - DO Region (REQUIRED): e.g. nyc3 (New York), fra1 (Frankfurt), sgp1 (Singapore). "
                        "Tip: pick closest to your users."
                    )
                if cp.get("ssh_key_name") is None:
                    pending.append(
                        "  - SSH Key (REQUIRED): your DigitalOcean SSH key name for Droplet access. "
                        "Say 'skip' to use password-based SSH (not recommended)."
                    )
                if cp.get("alert_email") is None:
                    pending.append(
                        "  - Alert Email: for DO Monitoring alerts. Say 'skip' to disable."
                    )
                for svc, key, hint in [
                    ("pg",     "db_config",      "DO Managed PostgreSQL: node plan (db-s-1vcpu-1gb for dev)"),
                    ("mysql",  "db_config",      "DO Managed MySQL: node plan (db-s-1vcpu-1gb for dev)"),
                    ("mongo",  "db_config",      "DO Managed MongoDB: node plan (db-s-1vcpu-1gb for dev)"),
                    ("redis",  "cache_config",   "DO Managed Redis: node plan (db-s-1vcpu-1gb for dev)"),
                    ("spaces", "storage_config", "DO Spaces: bucket name, public access yes/no"),
                ]:
                    if svc in svcs and not cp.get(key):
                        pending.append(f"  - {hint}")
            else:
                # AWS dev
                if not cp.get("aws_region") and not cp.get("region"):
                    pending.append(
                        "  - AWS Region (REQUIRED): e.g. us-east-1 (N. Virginia), ap-south-1 (Mumbai). "
                        "Tip: pick closest to your users."
                    )
                if cp.get("ssh_key_name") is None and cp.get("key_pair_name") is None:
                    pending.append(
                        "  - EC2 Key Pair (REQUIRED): your AWS key pair name for SSH. "
                        "Say 'skip' to use SSM Session Manager instead."
                    )
                if cp.get("ssh_allowed_cidrs") is None:
                    pending.append(
                        "  - SSH CIDR (REQUIRED): your IP to restrict SSH — e.g. ['1.2.3.4/32']. "
                        "Say 'skip' to defer."
                    )
                if cp.get("alert_email") is None:
                    pending.append(
                        "  - Alert Email: email for CloudWatch alerts. Say 'skip' to disable."
                    )
                for svc, key, hint in [
                    ("rds",         "rds_config",     "RDS: engine (MySQL/PostgreSQL), skip Multi-AZ for dev"),
                    ("dynamodb",    "db_config",      "DynamoDB: table name, billing mode (PAY_PER_REQUEST for dev)"),
                    ("elasticache", "cache_config",   "ElastiCache: node type → cache.t3.micro for dev"),
                    ("s3",          "storage_config", "S3: bucket name, public access yes/no"),
                    ("sqs",         "sqs_config",     "SQS: queue name, message retention"),
                ]:
                    if svc in svcs and not cp.get(key):
                        pending.append(f"  - {hint}")

        else:
            # ══ PROD MODE ══

            if dau is None:
                if is_do:
                    svc_name = "DigitalOcean"
                elif is_gcp:
                    svc_name = "GCP"
                else:
                    svc_name = "AWS"
                pending.append(
                    f"  - 🚦 TRAFFIC SIZING (ask this FIRST): How many daily active users at launch? "
                    f"This determines Droplet/instance plan, load balancer, and autoscaling for {svc_name}. "
                    f"Examples: 200 DAU → small single server, 1000 DAU → medium + load balancer, "
                    f"5000 DAU → large + {svc_name} LB (3–8 servers)."
                )
                return "\n\nPROD SETUP — cover one question per turn (START HERE):\n" + "\n".join(pending) + "\n"

            if tier in ("medium", "high", "extreme") and cp.get("enable_multi_az") is None:
                if is_do:
                    ha_detail = "multiple Droplets behind DO Load Balancer — seamless traffic distribution."
                elif is_gcp:
                    ha_detail = "Regional MIG (multi-zone failover in GCP) — ~60s failover time."
                else:
                    ha_detail = "Multi-AZ for RDS + ElastiCache — automatic failover in ~60s."
                pending.append(
                    f"  - 🔄 HIGH AVAILABILITY: With {_safe_int(dau):,} DAU you need zero-downtime. "
                    f"Enable {ha_detail} "
                    f"Yes = higher reliability, No = cheaper single-zone."
                )

            if cp.get("use_asg"):
                asg = cp.get("autoscaling_config") or {}
                if not asg.get("cpu_threshold"):
                    pending.append(
                        f"  - ⚡ AUTO SCALING threshold: at what CPU% should we add a new VM? "
                        f"Recommend 70% — gives headroom before users feel slowness. "
                        f"(Setup: {asg.get('min_instances', 2)}–{asg.get('max_instances', 4)} VMs)"
                    )
                if not asg.get("health_check_path"):
                    if is_do:
                        hc_name = "DO Load Balancer"
                    elif is_gcp:
                        hc_name = "GCP HTTP Health Check"
                    else:
                        hc_name = "ALB"
                    pending.append(
                        f"  - 🏥 HEALTH CHECK path for the {hc_name}: e.g. /health, /api/health, / "
                        f"— must return HTTP 200."
                    )

            if cp.get("custom_domain") is None:
                if is_do:
                    dns_hint = "DO DNS + Let's Encrypt SSL (via Certbot on Droplet)"
                elif is_gcp:
                    dns_hint = "Cloud DNS + Google-managed SSL"
                else:
                    dns_hint = "Route 53 + ACM SSL cert (free)"
                pending.append(
                    f"  - 🌐 CUSTOM DOMAIN: do you have a domain (e.g. myapp.com)? "
                    f"Yes → we'll configure {dns_hint}. "
                    f"No → use the LB's auto-generated IP/DNS."
                )

            if cp.get("alert_email") is None:
                if is_do:
                    alert_svc = "DO Monitoring"
                elif is_gcp:
                    alert_svc = "Cloud Monitoring + Uptime Checks"
                else:
                    alert_svc = "CloudWatch"
                pending.append(
                    f"  - 📧 ALERT EMAIL: where should {alert_svc} send CPU spike / error alerts? "
                    f"Essential for production — you want to know before users complain. "
                    f"Say 'skip' to disable."
                )

            if is_gcp:
                if cp.get("iap_tunnel") is None and cp.get("ssh_key_name") is None:
                    pending.append(
                        "  - 🔑 VM ACCESS: IAP Tunnel (recommended — no open ports, full audit log) "
                        "or provide SSH public key? For production, IAP is the GCP best practice."
                    )
            elif is_do:
                if cp.get("ssh_key_name") is None:
                    pending.append(
                        "  - 🔑 SSH KEY: your DO SSH key name as saved in your DigitalOcean account. "
                        "Used to access Droplets securely — no password needed."
                    )
            else:
                if cp.get("ssh_key_name") is None and cp.get("key_pair_name") is None:
                    pending.append(
                        "  - 🔑 SSH ACCESS: your EC2 key pair name, or 'skip' for SSM Session Manager. "
                        "For prod, SSM is often better — no open port 22, full audit trail."
                    )
                if cp.get("ssh_allowed_cidrs") is None:
                    pending.append(
                        "  - 🛡️  SSH CIDR: restrict SSH to your office/VPN IP. "
                        "NEVER use 0.0.0.0/0 in production. e.g. ['203.0.113.5/32']."
                    )

            if is_gcp:
                if not cp.get("gcp_region") and not cp.get("region"):
                    pending.append(
                        "  - 🌍 GCP REGION: us-central1 (USA), us-east1 (S. Carolina), europe-west1 (Belgium), "
                        "asia-east1 (Taiwan), asia-south1 (Mumbai). Regional MIG works in all main regions."
                    )
            elif is_do:
                if not cp.get("do_region") and not cp.get("region"):
                    pending.append(
                        "  - 🌍 DO REGION: nyc3 (New York), sfo3 (San Francisco), fra1 (Frankfurt), "
                        "sgp1 (Singapore), ams3 (Amsterdam). DO LB is region-scoped."
                    )
            else:
                if not cp.get("aws_region") and not cp.get("region"):
                    pending.append(
                        "  - 🌍 AWS REGION: us-east-1 (USA), eu-west-1 (Europe), ap-south-1 (India), "
                        "ap-southeast-1 (SE Asia). Multi-AZ works in all main regions."
                    )

            if is_gcp:
                for svc, key, hint in [
                    ("cloud_sql", "db_config",
                     f"Cloud SQL HA: engine, tier (db-n1-standard-1 for medium traffic), "
                     f"failover replica={'YES (already enabled)' if cp.get('enable_multi_az') else 'TBD'}"),
                    ("firestore",     "db_config",      "Firestore mode: Native (realtime/document) or Datastore?"),
                    ("memorystore",   "cache_config",   "Memorystore Redis: STANDARD_HA tier recommended for prod, capacity 1-5 GB"),
                    ("cloud_storage", "storage_config", "Cloud Storage: bucket name, versioning, lifecycle rules"),
                    ("pubsub",        "pubsub_config",  "Pub/Sub: topic + subscription names, message retention"),
                    ("cloud_tasks",   "tasks_config",   "Cloud Tasks: queue name, max concurrent dispatches"),
                ]:
                    if svc in svcs and not cp.get(key):
                        pending.append(f"  - {hint}")
            elif is_do:
                for svc, key, hint in [
                    ("pg",     "db_config",
                     f"DO Managed PostgreSQL: node plan → {'db-s-2vcpu-4gb' if tier in ('high','extreme') else 'db-s-1vcpu-2gb'}"),
                    ("mysql",  "db_config",
                     f"DO Managed MySQL: node plan → {'db-s-2vcpu-4gb' if tier in ('high','extreme') else 'db-s-1vcpu-2gb'}"),
                    ("mongo",  "db_config",  "DO Managed MongoDB: node plan, version (6 recommended)"),
                    ("redis",  "cache_config",
                     f"DO Managed Redis: node plan → {'db-s-1vcpu-2gb' if tier in ('high','extreme') else 'db-s-1vcpu-1gb'}"),
                    ("spaces", "storage_config", "DO Spaces: bucket name + CDN endpoint, region"),
                ]:
                    if svc in svcs and not cp.get(key):
                        pending.append(f"  - {hint}")
            else:
                for svc, key, hint in [
                    ("rds", "rds_config",
                     f"RDS config: engine, Multi-AZ={'YES' if cp.get('enable_multi_az') else 'TBD'}, "
                     f"instance class → {'db.t3.medium' if tier in ('high','extreme') else 'db.t3.small'}"),
                    ("dynamodb",    "db_config",
                     "DynamoDB: table name, billing mode (PAY_PER_REQUEST recommended for prod)"),
                    ("elasticache", "cache_config",
                     f"ElastiCache: node type → {'cache.t3.medium' if tier in ('high','extreme') else 'cache.t3.micro'}, "
                     f"Multi-AZ={'YES' if cp.get('enable_multi_az') else 'NO'}"),
                    ("s3",          "storage_config", "S3: bucket name, versioning yes/no, public access"),
                    ("sqs",         "sqs_config",     "SQS: queue names, visibility timeout, DLQ yes/no"),
                    ("ses",         "ses_config",     "SES: verified domain or email for transactional email sending"),
                    ("cognito",     "auth_config",    "Cognito: User Pool name, MFA yes/no, OAuth flows needed"),
                    ("cloudfront",  "cdn_config",     "CloudFront: origin domain, price class, custom error pages"),
                    ("waf",         "waf_config",     "WAF: managed rule groups (SQL injection, rate limiting)"),
                ]:
                    if svc in svcs and not cp.get(key):
                        pending.append(f"  - {hint}")

        # Secrets Manager — all providers
        if is_do:
            secrets_key = "use_do_secrets"
        elif is_gcp:
            secrets_key = "use_secret_manager"
        else:
            secrets_key = "use_secrets_manager"
        if not cp.get(secrets_key):
            secret_vars = [
                ev.get("name", "") for ev in (cp.get("required_env_vars") or [])
                if isinstance(ev, dict) and ev.get("is_secret")
            ]
            if secret_vars:
                if is_do:
                    svc_name = "DO App Platform env vars"
                elif is_gcp:
                    svc_name = "GCP Secret Manager"
                else:
                    svc_name = "AWS Secrets Manager"
                pending.append(
                    f"  - 🔐 {svc_name}: README has {len(secret_vars)} secret(s) "
                    f"({', '.join(secret_vars[:3])}{'...' if len(secret_vars) > 3 else ''}). "
                    f"Store them securely? Strongly recommended for all environments."
                )

        prefix = "\n\nPROD SETUP — cover one question per turn:\n" if prod else "\n\nDEV SETUP — cover one per turn:\n"
        return (prefix + "\n".join(pending) + "\n") if pending else ""

    # ── README analysis ────────────────────────────────────────────────────────

    async def _analyze_readme(self, readme: str) -> Dict[str, Any]:
        """
        Analyze the repo README to extract infrastructure parameters.
        Uses the Terraform MCP server for enriched context if enabled.
        """
        use_mcp = ["terraform"] if config.ENABLE_TERRAFORM_MCP else False
        raw = await self.llm_service.chat_completion(
            messages=[{"role": "user", "content": _README_PROMPT + readme[:18000]}],
            temperature=0.5, max_tokens=16000,
            response_format={"type": "json_object"}, timeout=120,
            use_mcp=use_mcp,
        )
        m = re.search(r'(\{.*\})', raw.strip(), re.DOTALL)
        try:
            return json.loads(m.group(1) if m else raw)
        except Exception:
            return {"message": "README analyzed.", "extracted_params": {}}

    # ── README context builder ─────────────────────────────────────────────────

    def _build_readme_context(self, readme: str, e: Dict[str, Any], owner: str, repo: str) -> str:
        def s(k, d=""): return str(e.get(k) or d).strip()
        def b(k): return e.get(k, False)

        ports_str = ", ".join(
            f"{p.get('port')}/{p.get('protocol','tcp')} ({p.get('description','')})"
            for p in (e.get("ports") or [])[:10] if isinstance(p, dict)
        )
        runtime_str = " | ".join(
            f"{r.get('name')}:{r.get('port')}"
            for r in (e.get("runtime_services") or [])[:8] if isinstance(r, dict)
        )
        env_str = "\n".join(
            f"  [{cat.upper()}]: {', '.join(v) if isinstance(v, list) else v}"
            for cat, v in (e.get("env_var_groups") or {}).items() if v
        )
        ext_str = ", ".join(
            sv.get("name", "") for sv in (e.get("external_services") or []) if isinstance(sv, dict)
        )
        warnings = e.get("infrastructure_warnings") or []
        crit = "\n".join(
            f"  🚨 {w.get('message','')} → {w.get('recommendation','')}"
            for w in warnings if isinstance(w, dict) and w.get("severity") == "critical"
        ) or "  None"
        all_w = "\n".join(
            f"  [{w.get('severity','info').upper()}] {w.get('message','')}"
            for w in warnings if isinstance(w, dict)
        ) or "  None"
        excerpt = "\n".join(ln.strip() for ln in readme.splitlines() if ln.strip())[:2000]

        return (
            f"PROJECT: {s('project_name') or repo} ({owner}/{repo})\n"
            f"WORKLOAD: {s('workload_description')} | PLATFORM: {s('current_deployment_platform','unknown')}\n"
            f"LANGUAGE: {s('language')}\n"
            f"\nPORTS: {ports_str or 'Not listed'}\n"
            f"RUNTIME SERVICES: {runtime_str or 'Main app only'}\n"
            f"START: {s('app_start_command')} | INSTALL: {s('install_command')} | BUILD: {s('build_command')}\n"
            f"PROCESS MANAGER: {s('process_manager')}\n"
            f"\nDATABASE: {'YES — ' + s('database_type') if b('has_database') else 'NONE'}\n"
            f"  Hosting: {s('database_hosting_model')} | ORM: {s('database_orm')} | Var: {s('database_connection_env_var')}\n"
            f"CACHE: {'YES — ' + s('cache_type') + ' (' + s('cache_purpose') + ')' if b('has_cache') else 'NONE'}\n"
            f"WEBSOCKETS: {'YES — ' + s('websocket_library') if b('has_websockets') else 'None'}\n"
            f"FRONTEND: {'YES — ' + s('frontend_type') + ' via ' + s('frontend_served_by') if b('has_frontend') else 'None'}\n"
            f"DOCKER: {'YES — ' + ', '.join(e.get('docker_services') or []) if b('has_docker') else 'No'}\n"
            f"STORAGE: {'YES — ' + s('storage_description') + ' (' + s('storage_provider') + ')' if b('storage_needs') else 'None'}\n"
            f"JOBS: {'YES — ' + s('background_job_description') if b('background_jobs') else 'None'}\n"
            f"\nEXTERNAL SERVICES (env var injection only — never provision): {ext_str or 'None'}\n"
            f"\nREQUIRED ENV VARS:\n{env_str or '  Not detected'}\n"
            f"\n🚨 CRITICAL WARNINGS:\n{crit}\n"
            f"ALL WARNINGS:\n{all_w}\n"
            f"\nREADME EXCERPT:\n{excerpt}"
        )

    # ── Public utility methods ─────────────────────────────────────────────────

    def get_collected_parameters(self, session_id: str) -> Dict[str, Any]:
        s = self.get_session(session_id)
        return dict(s.collected_parameters or {}) if s else {}

    def add_run_to_session(self, session_id: str, run_id: str) -> None:
        s = self.get_session(session_id)
        if not s:
            return
        runs = s.collected_parameters.get("run_ids", [])
        if not isinstance(runs, list):
            runs = []
        if run_id and run_id not in runs:
            runs.append(run_id)
        s.collected_parameters["run_ids"] = runs
        s.updated_at = datetime.now()
        self._save_session(s)

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.sessions_collection is None:
            return []
        try:
            docs = list(self.sessions_collection.find(
                {},
                {"_id": 0, "session_id": 1, "status": 1, "is_complete": 1, "updated_at": 1,
                 "collected_parameters.github_owner": 1, "collected_parameters.github_repo": 1,
                 "collected_parameters.cloud_provider": 1},
            ).sort("updated_at", -1).limit(max(1, min(int(limit or 20), 100))))
            return [{
                "session_id":  d.get("session_id"),
                "provider":    (d.get("collected_parameters") or {}).get("cloud_provider", "aws"),
                "status":      d.get("status"),
                "is_complete": d.get("is_complete", False),
                "updated_at":  str(d.get("updated_at", "")),
                "repo": (
                    f"{(d.get('collected_parameters') or {}).get('github_owner','')}"
                    f"/{(d.get('collected_parameters') or {}).get('github_repo','')}".strip("/")
                ),
            } for d in docs]
        except Exception as e:
            logger.error("list_sessions: %s", e)
            return []

    def delete_session(self, session_id: str) -> bool:
        if self.sessions_collection is None:
            return False
        try:
            return bool(self.sessions_collection.delete_one({"session_id": session_id}).deleted_count)
        except Exception as e:
            logger.error("delete_session %s: %s", session_id, e)
            return False

    def build_terraform_request(self, session_id: str) -> Dict[str, Any]:
        s = self.get_session(session_id)
        if not s:
            raise ValueError(f"Session {session_id} not found")
        p = dict(s.collected_parameters or {})
        self._apply_defaults(p)
        self._apply_safe_defaults(p)

        provider = str(p.get("cloud_provider", "aws")).lower()
        is_gcp = provider == "gcp"
        is_do  = provider == "digitalocean"
        if is_gcp:
            region = p.get("gcp_region")
        elif is_do:
            region = p.get("do_region")
        else:
            region = p.get("aws_region")
        if not region:
            if is_gcp:
                region = p.get("region", "us-central1")
            elif is_do:
                region = p.get("region", "nyc3")
            else:
                region = p.get("region", "us-east-1")

        ssh_key_name = p.get("ssh_key_name") or p.get("key_pair_name") or ""
        if ssh_key_name in ("REPLACE_ME", "REPLACE_ME_KEY"):
            ssh_key_name = ""

        alert_email = p.get("alert_email") or ""
        if "REPLACE_ME" in str(alert_email):
            alert_email = ""

        return {
            "cloud_provider":          provider,
            "environment":             p.get("environment", "dev"),
            "project_name":            p.get("project_name") or p.get("github_repo") or "app",
            "workload_description":    p.get("workload_description", ""),
            "language":                p.get("language", ""),
            "dependencies":            p.get("dependencies", []),
            "ports":                   p.get("ports", []),
            "ssh_allowed_cidrs":       [c for c in (p.get("ssh_allowed_cidrs") or []) if isinstance(c, str) and c.strip()],
            "instance_type":           (
                p.get("machine_type") if is_gcp
                else p.get("droplet_size") if is_do
                else p.get("instance_type", "t3.micro")
            ) or ("e2-micro" if is_gcp else ("s-1vcpu-2gb" if is_do else "t3.micro")),
            "instance_count":          p.get("instance_count", 1),
            "storage_size_gb":         p.get("storage_size_gb", 20 if (is_gcp or is_do) else 8),
            "storage_type":            p.get("storage_type", "pd-standard" if is_gcp else ("do" if is_do else "gp2")),
            "vpc_cidr":                p.get("vpc_cidr", "10.0.0.0/16"),
            "subnet_count":            p.get("subnet_count", 2),
            "enable_public_ip":        p.get("enable_public_ip", True),
            "aws_region":              None if (is_gcp or is_do) else region,
            "gcp_region":              region if is_gcp else None,
            "do_region":               region if is_do else None,
            "gcp_project":             p.get("gcp_project", ""),
            "aws_az":                  p.get("aws_az") or (region + "a" if not is_gcp and not is_do else None),
            "ssh_username":            p.get("ssh_username", "ubuntu"),
            "github_owner":            p.get("github_owner", ""),
            "github_repo":             p.get("github_repo", ""),
            "github_branch":           p.get("github_branch", ""),
            "readme_context":          p.get("readme_context", ""),
            "has_database":            p.get("has_database", False),
            "database_type":           p.get("database_type", "none"),
            "database_hosting_model":  p.get("database_hosting_model", "managed_cloud"),
            "rds_config":              p.get("rds_config", {}),
            "has_cache":               p.get("has_cache", False),
            "cache_type":              p.get("cache_type", "none"),
            "cache_config":            p.get("cache_config", {}),
            "storage_needs":           p.get("storage_needs", False),
            "storage_config":          p.get("storage_config", {}),
            "has_frontend":            p.get("has_frontend", False),
            "frontend_type":           p.get("frontend_type", ""),
            "frontend_served_by":      p.get("frontend_served_by", ""),
            "has_websockets":          p.get("has_websockets", False),
            "has_message_queue":       p.get("has_message_queue", False),
            "has_load_balancer":       p.get("has_load_balancer", False),
            "has_alb":                 p.get("use_alb", False),
            "has_asg":                 p.get("use_asg", False),
            "autoscaling_config":      p.get("autoscaling_config", {}),
            "enable_monitoring":       p.get("enable_monitoring", True),
            "monitoring_config":       p.get("monitoring_config", {}),
            "enable_backups":          p.get("enable_backups", False),
            "enable_multi_az":         p.get("enable_multi_az", False),
            "cdn_enabled":             p.get("cdn_enabled", False),
            "background_jobs":         p.get("background_jobs", False),
            "use_secrets_manager":     p.get("use_secrets_manager", False) or p.get("use_secret_manager", False),
            "use_do_secrets":           p.get("use_do_secrets", False),
            "daily_active_users":      p.get("daily_active_users", 0),
            "traffic_tier":            p.get("traffic_tier", "low"),
            "required_env_vars":       p.get("required_env_vars", []),
            "optional_env_vars":       p.get("optional_env_vars", []),
            "env_var_groups":          p.get("env_var_groups", {}),
            "runtime_services":        p.get("runtime_services", []),
            "external_services":       p.get("external_services", []),
            "app_start_command":       p.get("app_start_command", ""),
            "install_command":         p.get("install_command", ""),
            "build_command":           p.get("build_command", ""),
            "process_manager":         p.get("process_manager", ""),
            "infrastructure_warnings": p.get("infrastructure_warnings", []),
            "detected_services":       p.get("detected_services", {}),
            "expected_traffic":        p.get("expected_traffic", ""),
            "log_retention_days":      p.get("log_retention_days", 30),
            "alert_email":             alert_email,
            "ssh_key_name":            ssh_key_name,
            "custom_domain":           p.get("custom_domain", ""),
            "secrets_management":      p.get("secrets_management", "none"),
            # GCP-specific
            "iap_tunnel":              p.get("iap_tunnel", False),
            "gcp_service_account":     p.get("gcp_service_account", ""),
            # DigitalOcean-specific
            "droplet_size":            p.get("droplet_size", ""),
            "do_spaces_bucket":        p.get("do_spaces_bucket", ""),
            "do_firewall_rules":       p.get("do_firewall_rules", []),
            "do_project_name":         p.get("do_project_name", ""),
        }

    # ── Defaults & cost ────────────────────────────────────────────────────────

    @staticmethod
    def _apply_defaults(p: Dict[str, Any]) -> None:
        prod     = _is_prod(p)
        tier     = p.get("traffic_tier", "low")
        provider = str(p.get("cloud_provider", "aws")).lower()
        is_gcp   = provider == "gcp"
        is_do    = provider == "digitalocean"

        p.setdefault("vpc_cidr",          "10.0.0.0/16")
        p.setdefault("subnet_count",      2 if prod else 1)
        p.setdefault("storage_size_gb",   20 if (prod or is_gcp or is_do) else 8)
        p.setdefault("storage_type",      "pd-standard" if is_gcp else "gp2")
        p.setdefault("enable_public_ip",  not prod)
        p.setdefault("monitoring_enabled", True)
        p.setdefault("ssh_username",      "ubuntu")

        if is_gcp:
            p.setdefault("gcp_region", p.get("region", "us-central1"))
        elif is_do:
            p.setdefault("do_region", p.get("region", "nyc3"))
        else:
            p.setdefault("aws_region", p.get("region", "us-east-1"))

        if prod:
            if p.get("daily_active_users") is not None:
                _derive_traffic_params(p)
            else:
                if is_gcp:
                    p.setdefault("machine_type", "e2-small")
                elif is_do:
                    p.setdefault("droplet_size", "s-1vcpu-2gb")
                else:
                    p.setdefault("instance_type", "t3.small")
                p.setdefault("use_asg", False)
                p.setdefault("use_alb", False)
            p.setdefault("enable_multi_az", tier in ("medium", "high", "extreme"))
            p.setdefault("backup_enabled",  p.get("has_database", False))
        else:
            if is_gcp:
                p.setdefault("machine_type", "e2-micro")
            elif is_do:
                p.setdefault("droplet_size", "s-1vcpu-1gb")
            else:
                if not p.get("instance_type") or p.get("instance_type") == "t2.micro":
                    p["instance_type"] = "t3.micro"
            p.setdefault("use_asg",         False)
            p.setdefault("use_alb",         False)
            p.setdefault("enable_multi_az", False)
            p.setdefault("backup_enabled",  False)

    def _calculate_cost(self, p: dict) -> str:
        prod     = _is_prod(p)
        tier     = p.get("traffic_tier", "low")
        dau      = p.get("daily_active_users", 0) or 0
        provider = str(p.get("cloud_provider", "aws")).lower()
        is_gcp   = provider == "gcp"
        is_do    = provider == "digitalocean"

        if is_gcp:
            itype = str(p.get("machine_type") or "")
            if not itype or itype == "None":
                itype = "e2-micro" if not prod else "e2-small"
        elif is_do:
            itype = str(p.get("droplet_size") or "")
            if not itype or itype == "None":
                itype = "s-1vcpu-1gb" if not prod else "s-1vcpu-2gb"
        else:
            itype = str(p.get("instance_type") or "")
            if not itype or itype == "None":
                itype = "t3.micro" if not prod else "t3.small"

        min_inst  = int((p.get("autoscaling_config") or {}).get("min_instances", 1) or 1)
        max_inst  = int((p.get("autoscaling_config") or {}).get("max_instances", 1) or 1)
        disk_gb   = float(p.get("storage_size_gb", 20 if (is_gcp or is_do) else 8) or (20 if (is_gcp or is_do) else 8))
        has_db    = p.get("has_database", False)
        db_host   = str(p.get("database_hosting_model") or "").lower()
        has_cache = p.get("has_cache", False)
        has_lb    = bool(p.get("use_alb"))
        has_asg   = bool(p.get("use_asg"))
        multi_az  = bool(p.get("enable_multi_az"))

        AWS_VM = {"t3.micro": 7.50, "t3.small": 15.18, "t3.medium": 30.37, "t3.large": 60.74, "t3.xlarge": 121.47}
        AWS_DB = {"db.t3.micro": 12.41, "db.t3.small": 24.82, "db.t3.medium": 49.64, "db.t3.large": 99.28}
        AWS_LC = {"cache.t3.micro": 12.24, "cache.t3.small": 24.48, "cache.t3.medium": 48.96}

        GCP_VM = {"e2-micro": 7.11, "e2-small": 14.23, "e2-medium": 28.46, "e2-standard-2": 56.91, "e2-standard-4": 113.83}
        GCP_DB = {"db-f1-micro": 9.37, "db-g1-small": 18.74, "db-n1-standard-1": 37.49, "db-n1-standard-2": 74.98}
        GCP_LC = {"basic-1": 35.00, "standard-1": 70.00}

        DO_VM  = {"s-1vcpu-1gb": 6.00, "s-1vcpu-2gb": 12.00, "s-2vcpu-4gb": 24.00,
                  "s-4vcpu-8gb": 48.00, "c-4": 80.00, "c-8": 160.00}
        DO_DB  = {"db-s-1vcpu-1gb": 15.00, "db-s-1vcpu-2gb": 25.00,
                  "db-s-2vcpu-4gb": 50.00, "db-s-4vcpu-8gb": 100.00}
        DO_LC  = {"db-s-1vcpu-1gb": 15.00, "db-s-1vcpu-2gb": 25.00}

        lines: List[str] = []
        total = 0.0

        if is_gcp:
            vm_map = GCP_VM
        elif is_do:
            vm_map = DO_VM
        else:
            vm_map = AWS_VM
        unit   = vm_map.get(itype, 15.0)

        if not prod and itype in ("t3.micro", "e2-micro", "s-1vcpu-1gb"):
            lines.append(f"  • VM (1× {itype}): $0.00/mo (smallest plan)")
        elif has_asg:
            lo, hi = min_inst * unit, max_inst * unit
            total += lo
            if is_do:
                svc_name = "DO LB"
            elif is_gcp:
                svc_name = "MIG"
            else:
                svc_name = "ASG"
            lines.append(f"  • {svc_name} ({min_inst}–{max_inst}× {itype}): ${lo:.2f}–${hi:.2f}/mo")
        else:
            cost = min_inst * unit
            total += cost
            lines.append(f"  • VM ({min_inst}× {itype}): ${cost:.2f}/mo")

        total_disk = min_inst * disk_gb
        if not prod and total_disk <= 30 and not is_do:
            lines.append(f"  • Storage ({int(total_disk)}GB): $0.00/mo ✅ Free Tier")
        else:
            if is_do:
                d_unit = 0.10  # DO block storage $0.10/GB
            elif is_gcp:
                d_unit = 0.04
            else:
                d_unit = 0.10
            disk_cost = total_disk * d_unit
            total += disk_cost
            lines.append(f"  • Storage ({int(total_disk)}GB): ${disk_cost:.2f}/mo")

        if has_lb:
            if is_do:
                lb_cost = 12.00  # DO LB base cost
            elif is_gcp:
                lb_cost = 18.25
            else:
                lb_cost = 16.20
            total += lb_cost
            lines.append(f"  • Load Balancer: ${lb_cost:.2f}/mo")

        if has_db and db_host not in ("atlas", "external_uri"):
            db_cfg = p.get("rds_config") or p.get("db_config") or {}
            if is_gcp:
                db_tier = db_cfg.get("tier") or (
                    "db-n1-standard-1" if tier in ("high", "extreme") else
                    "db-g1-small" if tier == "medium" else "db-f1-micro"
                )
                db_cost = GCP_DB.get(db_tier, 18.74)
            elif is_do:
                db_tier = db_cfg.get("node_size") or db_cfg.get("size") or (
                    "db-s-2vcpu-4gb" if tier in ("high", "extreme") else
                    "db-s-1vcpu-2gb" if tier == "medium" else "db-s-1vcpu-1gb"
                )
                db_cost = DO_DB.get(db_tier, 25.00)
            else:
                db_tier = db_cfg.get("instance_class") or (
                    "db.t3.medium" if tier in ("high", "extreme") else
                    "db.t3.small" if tier == "medium" else "db.t3.micro"
                )
                db_cost = AWS_DB.get(db_tier, 24.82)

            if multi_az and not is_do:  # DO Managed DB includes standby in the cluster price
                db_cost *= 2
            if not prod and db_tier in ("db.t3.micro", "db-f1-micro") and not multi_az and not is_do:
                lines.append(f"  • Database ({db_tier}): $0.00/mo ✅ Free Tier")
            else:
                total += db_cost
                lines.append(f"  • Database ({db_tier}{' HA' if multi_az else ''}): ${db_cost:.2f}/mo")

        if has_cache:
            if is_gcp:
                c_cost = GCP_LC.get("standard-1" if multi_az else "basic-1", 35.00)
            elif is_do:
                c_cfg  = p.get("cache_config") or {}
                c_tier = c_cfg.get("size") or c_cfg.get("node_size") or (
                    "db-s-1vcpu-2gb" if tier in ("high", "extreme") else "db-s-1vcpu-1gb"
                )
                c_cost = DO_LC.get(c_tier, 15.00)
            else:
                c_cfg  = p.get("cache_config") or {}
                c_tier = c_cfg.get("instance_class") or (
                    "cache.t3.medium" if tier in ("high", "extreme") else "cache.t3.micro"
                )
                c_cost = AWS_LC.get(c_tier, 24.48)
                if multi_az:
                    c_cost *= 2
            total += c_cost
            lines.append(f"  • Cache: ${c_cost:.2f}/mo")

        if p.get("custom_domain"):
            total += 0.50
            lines.append("  • DNS/SSL: $0.50/mo")

        dau_str = f" for ~{_safe_int(dau):,} DAU" if dau else ""
        header  = (
            f"💰 **{provider.upper()} Production Cost Estimate{dau_str}**:" if prod
            else f"💰 **{provider.upper()} Dev Cost Estimate:**"
        )

        return (
            header + "\n" +
            "\n".join(lines) + "\n"
            f"  {'─' * 46}\n"
            f"  **Estimated: ~${total:.2f}/month**"
            + (" (at minimum capacity)" if has_asg else "")
        )

    # ── Static helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConversationManager._deep_merge(base[k], v)
            else:
                base[k] = v