"""conversation_manager.py — TerraBot: AWS-only Terraform conversation engine."""
from __future__ import annotations

import asyncio
import json
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.llm_service import AsyncLLMService
from app.services.github_service import GithubService
from app.services.aws_service import aws_service
from app.services import langfuse_service
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

_SYSTEM = """\
You are TerraBot  — a senior AWS cloud architect and your friendly, patient mentor. Your mission is to guide the user from a blank slate to a fully functional app on AWS.

AWS MCP TOOLS:
- You have live access to the AWS SDK via MCP.
- PROACTIVELY use these tools to check account limits, region availability, and best practices.

TONE & STYLE:
- BE EXCEPTIONALLY FRIENDLY, warm, and encouraging.
- BE A MENTOR: If you ask a question, explain *why* it matters and what the impact on their infra will be.
- BE REASSURING: If they are new to cloud, simplify concepts but keep the expert authority.
- LENGTH: Each response must be at least 4-5 lines of meaningful guidance and explanation.

GLOBAL RULES:
- Ensure the app is production-ready (modular, tagged, clean).
- Capture answers in extracted_params.
- Return ONLY valid JSON — no markdown, no explanation outside JSON.

CRITICAL DEFAULTS (always use these, never deviate):
- ssh_allowed_cidrs: ALWAYS [] as default. NEVER ["0.0.0.0/0"].
- key_pair_name / ssh_key_name: ALWAYS "" as default. NEVER "REPLACE_ME".
- alert_email: ALWAYS "" as default. NEVER "REPLACE_ME@example.com".
- sensitive outputs: ALWAYS static true/false. NEVER a variable expression.

Return ONLY this JSON structure every turn:
{"message":"your friendly, descriptive response here","extracted_params":{},"is_complete":false,"suggestions":["option1","option2"]}

══════════════════════════════════════════════════════════
DEVELOPMENT MODE — questions to collect (in order):
══════════════════════════════════════════════════════════
1. aws_region           — ask once, suggest us-east-1 as cheapest
2. ssh_key_name         — EC2 key pair name or "" for SSM-only
3. ssh_allowed_cidrs    — their IP or [] to defer
4. alert_email          — email or "" to skip
→ instance_type defaults to "t3.micro" — do NOT ask, just confirm
→ No ASG, ALB, Multi-AZ, traffic questions needed

DEV CONVERSATION FLOW (4 questions max, one per turn):
Turn 1: Confirm dev mode + ask region
Turn 2: Ask ssh_key_name (explain SSM option)
Turn 3: Ask ssh_allowed_cidrs (explain security risk of open SSH)
Turn 4: Ask alert_email (explain CloudWatch cost = $0 on free tier)
→ After turn 4: set is_complete=true (all 4 fields collected)

══════════════════════════════════════════════════════════
PRODUCTION MODE — questions to collect (in order):
══════════════════════════════════════════════════════════
STEP 1 — TRAFFIC SIZING (ask FIRST, everything else depends on this):
  Ask: "How many daily active users do you expect at launch?"
  Based on answer, determine traffic_tier and set instance_type:
    < 500 DAU       → traffic_tier="low",    instance_type="t3.small",  use_asg=false, use_alb=false
    500–2000 DAU    → traffic_tier="medium",  instance_type="t3.medium", use_asg=true,  use_alb=true,  min_instances=2, max_instances=4
    2000–10000 DAU  → traffic_tier="high",    instance_type="t3.large",  use_asg=true,  use_alb=true,  min_instances=3, max_instances=8
    > 10000 DAU     → traffic_tier="extreme", instance_type="t3.xlarge", use_asg=true,  use_alb=true,  min_instances=4, max_instances=12
  NEVER ask about instance_type separately — derive it from traffic.

STEP 2 — HIGH AVAILABILITY (only ask if traffic_tier is medium/high/extreme):
  Ask: "Do you need zero-downtime deployments and automatic failover?"
  Yes → enable_multi_az=true for RDS, multi_az_cache=true for ElastiCache
  No  → enable_multi_az=false (save cost)

STEP 3 — AUTO SCALING (only if use_asg=true from Step 1):
  Ask: "What CPU % should trigger adding a new server?" (suggest 70%)
  Also ask: "What's the health check path?" (suggest /health or /)
  Set: autoscaling_config.cpu_threshold, autoscaling_config.health_check_path

STEP 4 — DOMAIN & SSL (one question):
  Ask: "Do you have a custom domain? (e.g. myapp.com)"
  Yes → set custom_domain, enable_ssl=true, add route53+acm to detected_services
  No  → skip route53, use ALB DNS directly

STEP 5 — MONITORING (one question):
  Ask: "What email should receive CloudWatch alerts (CPU spikes, errors)?"
  → Set alert_email (or "" if they skip)

STEP 6 — ACCESS (one question):
  Ask same as dev: ssh_key_name + ssh_allowed_cidrs together in one turn

STEP 7 — REGION (one question):
  Ask: "Which AWS region?" — for prod suggest region closest to their users.
  Remind: Multi-AZ requires a region with ≥ 2 AZs (all main regions qualify).

→ After Step 7: set is_complete=true

PROD CONVERSATION FLOW (7 questions, one per turn):
Turn 1: Confirm prod + ask daily active users
Turn 2: Ask high availability (if medium/high/extreme traffic) OR skip to Turn 3
Turn 3: Ask CPU scale threshold + health check path (if ASG enabled)
Turn 4: Ask custom domain
Turn 5: Ask alert_email
Turn 6: Ask ssh_key_name + ssh_allowed_cidrs together
Turn 7: Ask aws_region
→ set is_complete=true
"""

_BRIDGE = """\
KEY RULES:
1. Provide 4-5 lines of descriptive text per turn.
2. Explain YOUR reasoning (e.g., "With 2000 DAU you'll need Auto Scaling — here's why...").
3. suggestions[] must always provide clear, actionable choices relevant to the current question.
4. Always return ONLY JSON format.
5. ONE question per turn maximum — never combine multiple unrelated questions.
6. For PRODUCTION, traffic sizing (DAU) MUST be the first question after environment selection.
   Do NOT ask region, SSH, or anything else before knowing traffic volume.

COMPLETENESS GATE — before setting is_complete:true, verify in extracted_params:
  FOR BOTH DEV AND PROD:
  [OK] aws_region         — e.g. "us-east-1"
  [OK] environment        — "dev" or "production"
  [OK] instance_type      — derived from traffic (prod) or "t3.micro" (dev)
  [OK] ssh_key_name       — EC2 key pair name OR "" confirmed SSM-only
  [OK] alert_email        — valid email OR "" confirmed skip
  [OK] ssh_allowed_cidrs  — list of CIDRs OR [] confirmed defer

  FOR PRODUCTION ONLY (additional required fields):
  [OK] daily_active_users — numeric value (e.g. 1000)
  [OK] traffic_tier       — "low" | "medium" | "high" | "extreme"
  [OK] use_asg            — true/false (derived from traffic_tier)
  [OK] use_alb            — true/false (derived from traffic_tier)
  [OK] enable_multi_az    — true/false (asked in Step 2, or false for low traffic)

If ANY of these are missing, keep is_complete:false and ask for the next missing one in order.
"""

_README_PROMPT = """\
You are TerraBot — senior AWS architect. Analyze this README for AWS Free Tier deployment.
Your analysis must be thorough, capturing every technical keyword that could influence the infrastructure.

Return ONLY valid JSON. No markdown fences, no explanation outside JSON.

REQUIRED STRUCTURE:
{
  "extracted_params": {
    "project_name": "",
    "workload_type": "web_server|api|fullstack|saas|batch|microservice|monitoring_tool",
    "workload_description": "2-3 sentences: what it does, who uses it, what infra it needs",
    "language": "e.g. Python 3.11 with FastAPI",
    "runtime_version": "",
    "sizing_tier": "starter|production",
    "ports": [{"port": 8000, "protocol": "tcp", "description": "FastAPI backend"}],

    "has_database": false,
    "database_type": "MongoDB|PostgreSQL|MySQL|SQLite|Redis|none",
    "database_orm": "Mongoose|SQLAlchemy|psycopg2|pymongo|Prisma|TypeORM|none",
    "database_hosting_model": "atlas|managed_cloud|self_hosted_docker|self_hosted_vm|external_uri",
    "database_connection_env_var": "MONGODB_URI",
    "database_notes": "",

    "required_env_vars": [
      {"name": "OPENAI_API_KEY", "description": "", "category": "llm_api", "is_secret": true, "required": true}
    ],
    "optional_env_vars": [],
    "env_var_groups": {
      "database": [], "auth": [], "llm_api": [], "storage": [],
      "monitoring": [], "email": [], "other": []
    },

    "external_services": [
      {"name": "MongoDB Atlas", "type": "managed_database", "env_vars": ["MONGO_URI"], "terraform_action": "inject_as_env_var"}
    ],

    "runtime_services": [
      {"name": "FastAPI", "port": 8000, "start_command": "uvicorn app.main:app --host 0.0.0.0 --port 8000"}
    ],
    "app_start_command": "",
    "app_entry_point": "",
    "build_command": "",
    "install_command": "",
    "process_manager": "pm2|gunicorn|uvicorn|systemd",

    "has_cache": false,
    "cache_type": "Redis|Memcached|none",
    "cache_purpose": "",
    "has_docker": false,
    "docker_services": [],
    "has_message_queue": false,
    "message_queue_type": "none",
    "has_websockets": false,
    "websocket_library": "socket.io|ws|sse|none",
    "storage_needs": false,
    "storage_description": "",
    "storage_provider": "cloudinary|s3|none",
    "has_frontend": false,
    "frontend_type": "",
    "frontend_served_by": "same_server|separate_server|cdn|none",
    "background_jobs": false,
    "background_job_description": "",
    "current_deployment_platform": "Render|Heroku|Vercel|Railway|self-hosted|unknown",

    "suggested_provider": "aws",
    "suggested_provider_reason": ["reason1", "reason2"],
    "suggested_instance_dev": "t3.micro",
    "suggested_instance_prod": "t3.small",
    "dependencies": [],

    "infrastructure_warnings": [
      {
        "severity": "critical|warning|info",
        "category": "database_mismatch|missing_env_var|external_service|port_conflict|hosting_model",
        "message": "",
        "recommendation": ""
      }
    ],
    "detected_services": ["ec2", "vpc", "security_groups", "iam_roles"]
  },
  "message": "Start with a warm, mentor-like greeting. Provide a thorough 4-5 sentence summary of the project. Explain which AWS Free Tier resources would be perfect for this stack and WHY. End by asking if we should target Development or Production.",
  "suggestions": ["Development", "Production"]
}

GREETING FORMAT:
Line 1:    "Welcome! I'm **TerraBot** — I just analyzed your [project] README! "
Line 2:    "Here's what I found:"
Lines 3-9: one specific bullet per detected tech — version, hosting model, purpose
Lines 10-11: infrastructure needed; if Atlas → say "MongoDB Atlas (external — no RDS needed, just inject MONGO_URI)"
Lines 12-13: why AWS Free Tier fits this specific stack (be concrete, not generic)
Lines 14-15: "Since we're deploying to AWS — **Development** (single t3.micro, Free Tier eligible) or **Production** (HA, ASG, ALB, monitoring)?"

CRITICAL RULES:
1.  Detect database from ORM (Mongoose→MongoDB, psycopg2→PostgreSQL), imports, env vars (MONGO_URI→MongoDB)
2.  database_hosting_model='atlas' → DO NOT include rds in detected_services
3.  External services (Atlas, Cloudinary, OpenAI, Clerk) → inject_as_env_var only — never provision in Terraform
4.  CLOUDINARY: always list CLOUDINARY_CLOUD_NAME + CLOUDINARY_API_KEY + CLOUDINARY_API_SECRET separately — never merge into CLOUDINARY_URL
5.  VITE_*/NEXT_PUBLIC_* vars → is_secret:false, mark as frontend_build_time
6.  build_command: npm run build is a build command; npm run dev is NOT
7.  Socket.IO multi-instance without Redis → add warning about missing adapter
8.  docker-compose for local dev but target is VM → warn about deployment mode mismatch
9.  detected_services: only services the app genuinely needs, max 15 items
10. SEED_KEY, ADMIN_KEY, or any seed-endpoint protection var → always include in required_env_vars

README:
"""


# ── Completeness validator ────────────────────────────────────────────────────

def _is_prod(cp: Dict[str, Any]) -> bool:
    return str(cp.get("environment", "")).lower() in ("prod", "production")


def _derive_traffic_params(cp: Dict[str, Any]) -> None:
    """
    Given daily_active_users in cp, auto-set traffic_tier, instance_type,
    use_asg, use_alb, and autoscaling_config min/max.
    Called whenever daily_active_users is set or updated.
    """
    dau = cp.get("daily_active_users")
    if dau is None:
        return
    try:
        dau = int(dau)
    except (TypeError, ValueError):
        return

    if dau < 500:
        tier, itype, asg, alb, mn, mx = "low",     "t3.small",  False, False, 1,  1
    elif dau < 2000:
        tier, itype, asg, alb, mn, mx = "medium",  "t3.medium", True,  True,  2,  4
    elif dau < 10000:
        tier, itype, asg, alb, mn, mx = "high",    "t3.large",  True,  True,  3,  8
    else:
        tier, itype, asg, alb, mn, mx = "extreme", "t3.xlarge", True,  True,  4, 12

    cp["traffic_tier"]   = tier
    cp["instance_type"]  = itype
    cp["use_asg"]        = asg
    cp["use_alb"]        = alb
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
    is_complete can be set to True. Single source of truth for the gate.

    Dev:  6 fields
    Prod: 6 shared + 5 prod-only = 11 fields total
    """
    missing: List[str] = []
    prod = _is_prod(cp)

    env = str(cp.get("environment", "")).lower()
    if env not in ("dev", "development", "prod", "production"):
        missing.append("environment (dev or production)")

    # ── PRODUCTION-FIRST: traffic must be asked before anything else ──
    if prod:
        if cp.get("daily_active_users") is None:
            missing.append("daily_active_users (e.g. 500 — determines instance size and scaling)")
            # Return early — nothing else can be determined without traffic scale
            return missing

        # Auto-derive traffic params if not already done
        _derive_traffic_params(cp)

        if cp.get("traffic_tier") is None:
            missing.append("traffic_tier (derived from daily_active_users)")

        if cp.get("use_asg") is None:
            missing.append("use_asg (derived from traffic_tier)")

        if cp.get("use_alb") is None:
            missing.append("use_alb (derived from traffic_tier)")

        # HA / Multi-AZ — required for medium/high/extreme, optional for low
        tier = cp.get("traffic_tier", "low")
        if tier != "low" and cp.get("enable_multi_az") is None:
            missing.append("enable_multi_az (high availability — required for your traffic level)")

        # ASG details if ASG is enabled
        if cp.get("use_asg"):
            asg = cp.get("autoscaling_config") or {}
            if not asg.get("cpu_threshold"):
                missing.append("autoscaling_config.cpu_threshold (CPU % to trigger scale-out, e.g. 70)")
            if not asg.get("health_check_path"):
                missing.append("autoscaling_config.health_check_path (e.g. /health or /)")

    # ── SHARED fields (both dev and prod) ─────────────────────────────
    if not cp.get("aws_region") and not cp.get("region"):
        missing.append("aws_region")

    # instance_type — for prod it's derived; for dev default to t3.micro
    itype = str(cp.get("instance_type") or "")
    if not itype:
        if not prod:
            cp["instance_type"] = "t3.micro"  # silent default for dev
        else:
            missing.append("instance_type (will be derived from daily_active_users)")
    elif itype == "t2.micro":
        cp["instance_type"] = "t3.micro"  # silent upgrade

    # ssh_key_name: None = not asked; "" = SSM-only confirmed
    if cp.get("ssh_key_name") is None and cp.get("key_pair_name") is None:
        missing.append("ssh_key_name (EC2 key pair name, or confirm SSM-only access)")

    if cp.get("alert_email") is None:
        missing.append("alert_email (for CloudWatch alerts, or confirm you want to skip)")

    if cp.get("ssh_allowed_cidrs") is None:
        missing.append("ssh_allowed_cidrs (your IP for SSH, or [] to configure later)")

    return missing


class ConversationManager:
    """TerraBot — AWS-only intelligent Terraform conversation guide."""

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
        user_id: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.sessions_collection is None:
            raise RuntimeError("MongoDB not available.")

        sid = f"terrf@_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"

        if not owner.strip() or not repo.strip():
            return {
                "session_id": sid,
                "bot_response": (
                    "Hey!  I'm **TerraBot** — your AWS Terraform guide.\n"
                    "I'll analyze your GitHub README and generate Free Tier eligible AWS infrastructure.\n"
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

        analysis  = await self._analyze_readme(readme, session_id=sid, user_id=user_id, username=username)
        extracted = analysis.get("extracted_params", {})

        svcs = extracted.get("detected_services", [])
        if not isinstance(svcs, list):
            svcs = []
        for s in AWS_CORE:
            if s not in svcs:
                svcs.append(s)
        extracted["detected_services"] = {"aws": svcs[:15]}
        extracted.update({
            "github_owner": owner, "github_repo": repo,
            "github_branch": github_branch, "cloud_provider": "aws",
            "readme_context": self._build_readme_context(readme, extracted, owner, repo),
        })

        # Ensure safe defaults from README analysis — never REPLACE_ME placeholders
        self._apply_safe_defaults(extracted)

        greeting = str(analysis.get("message") or "Should we target **Development** or **Production**?")
        session = ConversationSession(
            session_id=sid, provider="aws",
            user_id=user_id,
            username=username,
            messages=[{"role": "assistant", "content": greeting}],
            collected_parameters=extracted,
            is_complete=False, status=ConversationStatus.ACTIVE,
        )
        self.sessions_collection.insert_one(session.dict())
        logger.info("[%s] Session created for %s/%s", sid, owner, repo)
        return {"session_id": sid, "bot_response": greeting, "suggestions": ["Development", "Production"]}

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
        session.collected_parameters["cloud_provider"] = "aws"
        self._consolidate_asg_config(session.collected_parameters)

        # For prod: auto-derive traffic params whenever daily_active_users is set/updated
        if _is_prod(session.collected_parameters):
            _derive_traffic_params(session.collected_parameters)

        # Apply safe defaults after every merge to prevent REPLACE_ME from persisting
        self._apply_safe_defaults(session.collected_parameters)

        # ── Completeness gate ──────────────────────────────────────────────
        # Override LLM's is_complete if required fields are still missing
        llm_says_complete = bool(data["is_complete"])
        missing_fields    = _validate_completeness(session.collected_parameters)

        if llm_says_complete and missing_fields:
            logger.warning(
                "[%s] LLM set is_complete=True but %d field(s) still missing: %s",
                session_id, len(missing_fields), missing_fields,
            )
            data["is_complete"] = False
            # Inject a follow-up nudge into the message
            missing_str = "\n".join(f"  • {f}" for f in missing_fields)
            data["message"] = (
                data["message"].rstrip() +
                f"\n\nBefore I can generate your infrastructure, I still need:\n{missing_str}"
            )

        session.is_complete = bool(data["is_complete"])
        session.updated_at  = datetime.utcnow()

        if session.is_complete:
            self._apply_defaults(session.collected_parameters)
            session.status = ConversationStatus.COMPLETE
            cost = self._calculate_cost(session.collected_parameters)
            data["message"] = (
                f"[OK] Perfect! I have everything needed for your AWS infrastructure.\n\n"
                f"** Cost Estimate:**\n{cost}\n\n"
                "Generating `main.tf`, `variables.tf`, `outputs.tf` and a GitHub Actions workflow now! "
            )

        session.messages.append({"role": "assistant", "content": data["message"]})
        self._save_session(session)

        return ChatMessageResponse(
            session_id=session_id,
            bot_response=data["message"],
            collected_parameters=session.collected_parameters,
            is_complete=session.is_complete,
            suggestions=data.get("suggestions", []),
            trace_id=session.last_trace_id,
        )

    @staticmethod
    def _apply_safe_defaults(cp: Dict[str, Any]) -> None:
        """
        Replace known bad placeholder values with safe defaults.
        Called after every LLM merge to prevent REPLACE_ME values
        from leaking into Terraform generation.
        """
        # Fix REPLACE_ME placeholders
        if cp.get("key_pair_name") == "REPLACE_ME":
            cp["key_pair_name"] = ""
        if cp.get("ssh_key_name") == "REPLACE_ME":
            cp["ssh_key_name"] = ""
        if str(cp.get("alert_email", "")).endswith("REPLACE_ME@example.com"):
            cp["alert_email"] = ""

        # Fix insecure SSH CIDR default
        cidrs = cp.get("ssh_allowed_cidrs")
        if isinstance(cidrs, list) and cidrs == ["0.0.0.0/0"]:
            cp["ssh_allowed_cidrs"] = []

        # Fix instance type — never t2.micro
        if cp.get("instance_type") == "t2.micro":
            cp["instance_type"] = "t3.micro"

    @staticmethod
    def _consolidate_asg_config(cp: dict) -> None:
        """Gather ASG sub-keys into 'autoscaling_config'."""
        _ALIASES: dict[str, list[str]] = {
            "min_instances":    ["min_instances", "asg_min", "autoscaling_min", "min_size"],
            "max_instances":    ["max_instances", "asg_max", "autoscaling_max", "max_size"],
            "cpu_threshold":    ["cpu_threshold", "asg_cpu", "cpu_utilization", "cpu_target"],
            "health_check_path":["health_check_path", "health_check"],
        }
        cfg = cp.setdefault("autoscaling_config", {}) if isinstance(cp.get("autoscaling_config"), dict) else {}
        if not isinstance(cp.get("autoscaling_config"), dict):
            cp["autoscaling_config"] = cfg

        for canonical, aliases in _ALIASES.items():
            if canonical in cfg: continue
            for alias in aliases:
                if alias in cp and cp[alias] not in (None, ""):
                    cfg[canonical] = cp.pop(alias)
                    break
        # Note: AWS CloudWatch target tracking expects whole numbers (e.g., 70 = 70%)

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
        readme_ctx = str(session.collected_parameters.get("readme_context", ""))[:3500]
        snapshot   = json.dumps(session.collected_parameters, indent=2)
        env        = str(session.collected_parameters.get("environment", "") or "NOT SET").upper()
        turns      = sum(1 for m in session.messages if m["role"] == "user")

        mode = config.DEPLOYMENT_MODE.upper()
        context = (
            f"\nREADME CONTEXT:\n{readme_ctx}\n\n"
            f"STATE: AWS | mode={mode} | env={env} | turn={turns}\n"
            f"COLLECTED:\n{snapshot}\n"
        )

        region = session.collected_parameters.get("aws_region") or session.collected_parameters.get("region")

        # Fetch live AWS account data — suppress quota errors gracefully
        try:
            aws_ctx = await asyncio.get_event_loop().run_in_executor(
                None, aws_service.format_for_prompt, region
            )
        except Exception:
            aws_ctx = ""

        messages = [{"role": "system", "content": _SYSTEM + "\n\n" + _BRIDGE + context + aws_ctx + self._svc_hints(session)}]
        for m in session.messages:
            if m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})

        # Create Langfuse trace with full input (system prompt + chat history)
        trace = langfuse_service.create_trace(
            name="Conversation Turn",
            session_id=session.session_id,
            user_id=session.user_id,
            username=session.username,
            input=messages,
        )

        # Store trace ID on session so feedback can link to it
        if trace:
            session.last_trace_id = getattr(trace, 'id', None)

        result = await self.llm_service.chat_completion(
            messages=messages, temperature=0.5, max_tokens=16000,
            response_format={"type": "json_object"}, timeout=120,
            _trace=trace
        )

        # Update trace with the LLM output
        if trace:
            try:
                trace.update(output=result[:10000])
            except Exception:
                pass

        return result

    def _svc_hints(self, session: ConversationSession) -> str:
        cp      = session.collected_parameters
        svcs    = (cp.get("detected_services") or {}).get("aws", [])
        prod    = _is_prod(cp)
        tier    = cp.get("traffic_tier", "")
        dau     = cp.get("daily_active_users")

        pending: List[str] = []

        if not prod:
            # ══ DEV MODE — minimal questions ══
            # Region
            if not cp.get("aws_region") and not cp.get("region"):
                pending.append(
                    "  - AWS Region (REQUIRED): which region? e.g. us-east-1 (N. Virginia), "
                    "ap-south-1 (Mumbai). Tip: pick closest to your users."
                )
            # SSH Key
            if cp.get("ssh_key_name") is None and cp.get("key_pair_name") is None:
                pending.append(
                    "  - EC2 Key Pair (REQUIRED): your AWS key pair name for SSH access. "
                    "Say 'skip' to use SSM Session Manager instead (no key needed)."
                )
            # SSH CIDR
            if cp.get("ssh_allowed_cidrs") is None:
                pending.append(
                    "  - SSH CIDR (REQUIRED): your IP address to restrict SSH. "
                    "e.g. ['1.2.3.4/32']. Say 'skip' to defer (SSH will be blocked until set)."
                )
            # Alert email
            if cp.get("alert_email") is None:
                pending.append(
                    "  - Alert Email: email for CloudWatch CPU/error alerts. "
                    "Free on AWS Free Tier. Say 'skip' to disable."
                )
            # Service-specific (dev)
            for svc, key, hint in [
                ("rds",         "rds_config",    "RDS: engine (MySQL/PostgreSQL), skip Multi-AZ for dev"),
                ("elasticache", "cache_config",  "ElastiCache: node type → cache.t3.micro for dev"),
                ("s3",          "storage_config","S3: bucket name, public access yes/no"),
                ("sqs",         "sqs_config",    "SQS: queue name, message retention"),
            ]:
                if svc in svcs and not cp.get(key):
                    pending.append(f"  - {hint}")

        else:
            # ══ PROD MODE — traffic-first ordering ══

            # STEP 1: Traffic (must come first — everything depends on it)
            if dau is None:
                pending.append(
                    "  -  TRAFFIC SIZING (ask this FIRST): How many daily active users at launch? "
                    "This determines instance size, Auto Scaling, and load balancer requirements. "
                    "Examples: 200 DAU → t3.small (1 server), 1000 DAU → t3.medium + ASG, "
                    "5000 DAU → t3.large + ALB + ASG (3–8 servers)."
                )
                return "\n\nPROD SETUP — cover one question per turn (START HERE):\n" + "\n".join(pending) + "\n"

            # STEP 2: HA / Multi-AZ (only if medium+ traffic)
            if tier in ("medium", "high", "extreme") and cp.get("enable_multi_az") is None:
                pending.append(
                    f"  -  HIGH AVAILABILITY: With {int(dau):,} DAU you need zero-downtime failover. "
                    f"Enable Multi-AZ for RDS and ElastiCache? "
                    f"Yes = automatic failover in ~60s if the primary fails. "
                    f"No = single AZ, cheaper but brief downtime on failure."
                )

            # STEP 3: ASG details
            if cp.get("use_asg"):
                asg = cp.get("autoscaling_config") or {}
                if not asg.get("cpu_threshold"):
                    pending.append(
                        f"  -  AUTO SCALING threshold: at what CPU% should we add a new server? "
                        f"Recommend 70% — this gives headroom before users feel slowness. "
                        f"(Current setup: {asg.get('min_instances', 2)}–{asg.get('max_instances', 4)} servers)"
                    )
                if not asg.get("health_check_path"):
                    pending.append(
                        "  -  HEALTH CHECK path: what endpoint does the ALB ping to check server health? "
                        "e.g. /health, /api/health, or / — must return HTTP 200."
                    )

            # STEP 4: Domain
            if cp.get("custom_domain") is None:
                pending.append(
                    "  -  CUSTOM DOMAIN: do you have a domain (e.g. myapp.com)? "
                    "Yes → we'll configure Route 53 + ACM SSL cert (free). "
                    "No → your app will be accessible via the ALB's auto-generated DNS."
                )

            # STEP 5: Alert email
            if cp.get("alert_email") is None:
                pending.append(
                    "  -  ALERT EMAIL: where should CloudWatch send CPU spike / error alerts? "
                    "For production this is essential — you want to know before users complain. "
                    "Say 'skip' to disable."
                )

            # STEP 6: SSH access
            if cp.get("ssh_key_name") is None and cp.get("key_pair_name") is None:
                pending.append(
                    "  -  SSH ACCESS: your EC2 key pair name, or 'skip' for SSM Session Manager. "
                    "For prod, SSM is often better — no open port 22, full audit trail."
                )
            if cp.get("ssh_allowed_cidrs") is None:
                pending.append(
                    "  -   SSH CIDR: restrict SSH to your office/VPN IP. "
                    "NEVER use 0.0.0.0/0 in production. e.g. ['203.0.113.5/32']. "
                    "Say 'skip' to disable SSH (use SSM instead)."
                )

            # STEP 7: Region
            if not cp.get("aws_region") and not cp.get("region"):
                pending.append(
                    "  -  AWS REGION: which region are most of your users in? "
                    "us-east-1 (USA), eu-west-1 (Europe), ap-south-1 (India), ap-southeast-1 (SE Asia). "
                    "Multi-AZ works in all main regions."
                )

            # Service-specific prod additions
            for svc, key, hint in [
                ("rds", "rds_config",
                 f"RDS config: engine, Multi-AZ={'YES (already enabled)' if cp.get('enable_multi_az') else 'TBD'}, "
                 f"instance class → {'db.t3.medium' if tier in ('high','extreme') else 'db.t3.micro'}"),
                ("elasticache", "cache_config",
                 f"ElastiCache: node type → {'cache.t3.medium' if tier in ('high','extreme') else 'cache.t3.micro'}, "
                 f"Multi-AZ={'YES' if cp.get('enable_multi_az') else 'NO'}"),
                ("s3", "storage_config", "S3: bucket name, versioning yes/no, public access"),
                ("sqs", "sqs_config", "SQS: queue names, visibility timeout, DLQ yes/no"),
            ]:
                if svc in svcs and not cp.get(key):
                    pending.append(f"  - {hint}")

        # Secrets Manager — both modes
        if not cp.get("use_secrets_manager"):
            secret_vars = [
                ev.get("name", "") for ev in (cp.get("required_env_vars") or [])
                if isinstance(ev, dict) and ev.get("is_secret")
            ]
            if secret_vars:
                pending.append(
                    f"  -  Secrets Manager: README has {len(secret_vars)} secret(s) "
                    f"({', '.join(secret_vars[:3])}{'...' if len(secret_vars) > 3 else ''}). "
                    f"Store in AWS Secrets Manager? Recommended for prod, optional for dev."
                )

        prefix = "\n\nPROD SETUP — cover one question per turn:\n" if prod else "\n\nDEV SETUP — cover one per turn:\n"
        return (prefix + "\n".join(pending) + "\n") if pending else ""

    # ── README analysis ────────────────────────────────────────────────────────

    async def _analyze_readme(self, readme: str, session_id: str = None, user_id: str = None, username: str = None) -> Dict[str, Any]:
        readme_input = [{"role": "user", "content": _README_PROMPT + readme[:18000]}]

        # Create Langfuse trace with full input (README prompt)
        trace = langfuse_service.create_trace(
            name="README Analysis",
            session_id=session_id,
            user_id=user_id,
            username=username,
            input=readme_input,
        )

        raw = await self.llm_service.chat_completion(
            messages=readme_input,
            temperature=0.5, max_tokens=16000,
            response_format={"type": "json_object"}, timeout=120,
            use_mcp=["aws"] if config.ENABLE_AWS_MCP else False,
            _trace=trace
        )

        # Update trace with the LLM output
        if trace:
            try:
                trace.update(output=raw[:10000])
            except Exception:
                pass

        m = re.search(r'(\{.*\})', raw.strip(), re.DOTALL)
        return json.loads(m.group(1) if m else raw)

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
            f"   {w.get('message','')} → {w.get('recommendation','')}"
            for w in warnings if isinstance(w, dict) and w.get("severity") == "critical"
        ) or "  None"
        all_w = "\n".join(
            f"  [{w.get('severity','info').upper()}] {w.get('message','')}"
            for w in warnings if isinstance(w, dict)
        ) or "  None"
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
            f"\n CRITICAL WARNINGS:\n{crit}\n"
            f"ALL WARNINGS:\n{all_w}\n"
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
                 "collected_parameters.github_owner": 1, "collected_parameters.github_repo": 1},
            ).sort("updated_at", -1).limit(max(1, min(int(limit or 20), 100))))
            return [{
                "session_id":  d.get("session_id"),
                "provider":    "aws",
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
        self._apply_safe_defaults(p)  # Final safety pass before Terraform generation
        region = p.get("aws_region") or p.get("region") or "us-east-1"

        # Resolve ssh_key_name from multiple possible param names
        ssh_key_name = (
            p.get("ssh_key_name") or
            p.get("key_pair_name") or
            ""
        )
        # Never pass REPLACE_ME to Terraform generator
        if ssh_key_name in ("REPLACE_ME", "REPLACE_ME_KEY"):
            ssh_key_name = ""

        # Resolve alert_email
        alert_email = p.get("alert_email") or ""
        if "REPLACE_ME" in str(alert_email):
            alert_email = ""

        return {
            # Identity — forwarded to Langfuse so all downstream traces share the session
            "session_id":           session_id,
            "user_id":              s.user_id,
            "username":             s.username,
            "cloud_provider":       "aws",
            "environment":          p.get("environment", "dev"),
            "project_name":         p.get("project_name") or p.get("github_repo") or "app",
            "workload_description": p.get("workload_description", ""),
            "language":             p.get("language", ""),
            "dependencies":         p.get("dependencies", []),
            "ports":                p.get("ports", []),
            "ssh_allowed_cidrs":    [c for c in (p.get("ssh_allowed_cidrs") or []) if isinstance(c, str) and c.strip()],
            "instance_type":        p.get("instance_type", "t3.micro"),
            "instance_count":       p.get("instance_count", 1),
            "storage_size_gb":      p.get("storage_size_gb", 8),
            "storage_type":         p.get("storage_type", "gp3"),
            "vpc_cidr":             p.get("vpc_cidr", "10.0.0.0/16"),
            "subnet_count":         p.get("subnet_count", 2),
            "enable_public_ip":     p.get("enable_public_ip", True),
            "aws_region":           region,
            "aws_az":               p.get("aws_az") or region + "a",
            "ssh_username":         p.get("ssh_username", "ubuntu"),
            "github_owner":         p.get("github_owner", ""),
            "github_repo":          p.get("github_repo", ""),
            "github_branch":        p.get("github_branch", ""),
            "readme_context":       p.get("readme_context", ""),
            "has_database":         p.get("has_database", False),
            "database_type":        p.get("database_type", "none"),
            "database_hosting_model": p.get("database_hosting_model", "managed_cloud"),
            "rds_config":           p.get("rds_config", {}),
            "has_cache":            p.get("has_cache", False),
            "cache_type":           p.get("cache_type", "none"),
            "cache_config":         p.get("cache_config", {}),
            "storage_needs":        p.get("storage_needs", False),
            "storage_config":       p.get("storage_config", {}),
            "has_frontend":         p.get("has_frontend", False),
            "frontend_type":        p.get("frontend_type", ""),
            "frontend_served_by":   p.get("frontend_served_by", ""),
            "has_websockets":       p.get("has_websockets", False),
            "has_message_queue":    p.get("has_message_queue", False),
            "has_load_balancer":    p.get("has_load_balancer", False),
            "has_alb":              p.get("use_alb", False),
            "has_asg":              p.get("use_asg", False),
            "autoscaling_config":   p.get("autoscaling_config", {}),
            "enable_monitoring":    p.get("enable_monitoring", True),
            "monitoring_config":    p.get("monitoring_config", {}),
            "enable_backups":       p.get("enable_backups", False),
            "enable_multi_az":      p.get("enable_multi_az", False),
            "cdn_enabled":          p.get("cdn_enabled", False),
            "background_jobs":      p.get("background_jobs", False),
            "use_secrets_manager":  p.get("use_secrets_manager", False),
            # Traffic / scaling (prod-specific, harmless for dev)
            "daily_active_users":   p.get("daily_active_users", 0),
            "traffic_tier":         p.get("traffic_tier", "low"),
            "required_env_vars":    p.get("required_env_vars", []),
            "optional_env_vars":    p.get("optional_env_vars", []),
            "env_var_groups":       p.get("env_var_groups", {}),
            "runtime_services":     p.get("runtime_services", []),
            "external_services":    p.get("external_services", []),
            "app_start_command":    p.get("app_start_command", ""),
            "install_command":      p.get("install_command", ""),
            "build_command":        p.get("build_command", ""),
            "process_manager":      p.get("process_manager", ""),
            "infrastructure_warnings": p.get("infrastructure_warnings", []),
            "detected_services":    p.get("detected_services", {}),
            "expected_traffic":     p.get("expected_traffic", ""),
            "log_retention_days":   p.get("log_retention_days", 30),
            "alert_email":          alert_email,
            "ssh_key_name":         ssh_key_name,
            "custom_domain":        p.get("custom_domain", ""),
            "secrets_management":   p.get("secrets_management", "none"),
        }

    # ── Defaults & cost ────────────────────────────────────────────────────────

    @staticmethod
    def _apply_defaults(p: Dict[str, Any]) -> None:
        prod  = _is_prod(p)
        tier  = p.get("traffic_tier", "low")
        count = int(p.get("instance_count", 1) or 1)

        p.setdefault("vpc_cidr",         "10.0.0.0/16")
        p.setdefault("subnet_count",     2 if prod else 1)
        p.setdefault("storage_size_gb",  20 if prod else 8)
        p.setdefault("storage_type",     "gp3")
        p.setdefault("enable_public_ip", not prod)  # prod uses ALB; dev uses public IP
        p.setdefault("monitoring_enabled", True)
        p.setdefault("ssh_username",     "ubuntu")
        p.setdefault("aws_region",       p.get("region", "us-east-1"))

        # For prod: use_asg/use_alb/instance_type are derived from traffic
        # Only set defaults here if traffic derivation hasn't run yet
        if prod:
            if p.get("daily_active_users") is not None:
                _derive_traffic_params(p)  # ensure up to date
            else:
                # No traffic data yet — use conservative prod defaults
                p.setdefault("instance_type",  "t3.small")
                p.setdefault("use_asg",        False)
                p.setdefault("use_alb",        False)
            p.setdefault("enable_multi_az", tier in ("medium", "high", "extreme"))
            p.setdefault("backup_enabled",  p.get("has_database", False))
        else:
            # Dev: always t3.micro, no ASG/ALB
            if not p.get("instance_type") or p.get("instance_type") == "t2.micro":
                p["instance_type"] = "t3.micro"
            p.setdefault("use_asg", False)
            p.setdefault("use_alb", False)
            p.setdefault("enable_multi_az", False)
            p.setdefault("backup_enabled",  False)

    def _calculate_cost(self, p: dict) -> str:
        prod      = _is_prod(p)
        tier      = p.get("traffic_tier", "low")
        dau       = p.get("daily_active_users", 0) or 0
        itype     = str(p.get("instance_type") or ("t3.micro" if not prod else "t3.small"))
        min_inst  = int((p.get("autoscaling_config") or {}).get("min_instances", 1) or 1)
        max_inst  = int((p.get("autoscaling_config") or {}).get("max_instances", 1) or 1)
        disk_gb   = float(p.get("storage_size_gb", 8) or 8)
        has_db    = p.get("has_database", False)
        db_host   = str(p.get("database_hosting_model") or "").lower()
        has_cache = p.get("has_cache", False)
        has_alb   = bool(p.get("use_alb"))
        has_asg   = bool(p.get("use_asg"))
        has_bkt   = p.get("storage_needs") and p.get("storage_provider") == "s3"
        multi_az  = bool(p.get("enable_multi_az"))

        INST = {
            "t3.micro": 7.50, "t3.small": 15.18, "t3.medium": 30.37,
            "t3.large": 60.74, "t3.xlarge": 121.47,
        }
        RDS = {
            "db.t3.micro": 12.41, "db.t3.small": 24.82,
            "db.t3.medium": 49.64, "db.t3.large": 99.28,
        }
        ELC = {
            "cache.t3.micro": 12.24, "cache.t3.small": 24.48,
            "cache.t3.medium": 48.96,
        }

        lines: List[str] = []
        total = 0.0

        # EC2 (always show min cost; for ASG show range)
        unit = INST.get(itype, 15.18)
        if not prod and itype == "t3.micro":
            lines.append(f"  • EC2 (1× {itype}): $0.00/mo [OK] Free Tier")
        elif has_asg:
            lo = min_inst * unit
            hi = max_inst * unit
            total += lo  # estimate on min
            lines.append(f"  • EC2 Auto Scaling ({min_inst}–{max_inst}× {itype}): ${lo:.2f}–${hi:.2f}/mo")
        else:
            cost = min_inst * unit
            total += cost
            lines.append(f"  • EC2 ({min_inst}× {itype}): ${cost:.2f}/mo")

        # EBS
        total_disk = min_inst * disk_gb
        if not prod and total_disk <= 30:
            lines.append(f"  • EBS ({int(total_disk)}GB ): $0.00/mo [OK] Free Tier")
        else:
            ebs = total_disk * 0.10
            total += ebs
            lines.append(f"  • EBS ({int(total_disk)}GB gp3): ${ebs:.2f}/mo")

        # ALB
        if has_alb:
            total += 16.20
            lines.append("  • Application Load Balancer: $16.20/mo")

        # RDS
        if has_db and db_host not in ("atlas", "external_uri"):
            db_cfg  = p.get("rds_config") or {}
            db_tier = db_cfg.get("instance_class") or (
                "db.t3.medium" if tier in ("high", "extreme") else
                "db.t3.small"  if tier == "medium" else
                "db.t3.micro"
            )
            db_cost = RDS.get(db_tier, 24.82)
            if multi_az:
                db_cost *= 2
            if not prod and db_tier == "db.t3.micro" and not multi_az:
                lines.append(f"  • RDS ({db_tier}): $0.00/mo [OK] Free Tier")
            else:
                total += db_cost
                multi_tag = " Multi-AZ" if multi_az else ""
                lines.append(f"  • RDS ({db_tier}{multi_tag}): ${db_cost:.2f}/mo")

        # ElastiCache
        if has_cache:
            c_cfg  = p.get("cache_config") or {}
            c_tier = c_cfg.get("instance_class") or (
                "cache.t3.medium" if tier in ("high", "extreme") else "cache.t3.micro"
            )
            c_cost = ELC.get(c_tier, 24.48)
            if multi_az:
                c_cost *= 2
            total += c_cost
            multi_tag = " Multi-AZ" if multi_az else ""
            lines.append(f"  • ElastiCache ({c_tier}{multi_tag}): ${c_cost:.2f}/mo")

        # S3
        if has_bkt:
            lines.append("  • S3: $0.00/mo [OK] Free Tier (5GB)")

        # CloudWatch
        lines.append("  • CloudWatch: $0.00/mo [OK] Free Tier")

        # Route53 / SSL
        if p.get("custom_domain"):
            total += 0.50
            lines.append("  • Route 53 Hosted Zone: $0.50/mo")
            lines.append("  • ACM SSL Certificate: $0.00/mo [OK] Free")

        dau_str = f" for ~{int(dau):,} DAU" if dau else ""
        header = f" **Production Cost Estimate{dau_str} ({tier} traffic tier)**:" if prod else " **Dev Cost Estimate (AWS Free Tier):**"

        return (
            header + "\n" +
            "\n".join(lines) + "\n"
            f"  {'─' * 46}\n"
            f"  **Estimated: ~${total:.2f}/month**"
            + (" (at minimum capacity — scales up under load)" if has_asg else "")
        )

    # ── Static helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConversationManager._deep_merge(base[k], v)
            else:
                base[k] = v