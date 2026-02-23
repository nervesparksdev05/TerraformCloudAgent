"""conversation_manager.py — TerraBot: GCP-only Terraform conversation engine."""
from __future__ import annotations

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

GCP_CORE = ["compute_engine", "vpc", "firewall_rules", "iam_service_accounts"]
GCP_TOP15 = GCP_CORE + [
    "cloud_storage", "cloud_sql", "memorystore", "cloud_load_balancing",
    "cloud_dns", "cloud_monitoring", "persistent_disk", "managed_instance_groups",
    "gke", "pubsub", "cloud_cdn",
]

# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are TerraBot 🤖 — a senior GCP Terraform expert.
You have already analysed the README and know which GCP services are needed.
Your job: collect config parameters for those services through sharp, expert questions.

GLOBAL RULES:
- ONE question per turn, no exceptions.
- Format every question as: README finding → why it matters → options → recommendation → question.
- Capture every answer in extracted_params immediately.
- Set is_complete:true ONLY after every relevant detected service has a config answer.
- GCP terminology only. Never mention AWS, Azure or on-prem alternatives.

Return ONLY JSON:
{"message":"...","extracted_params":{},"is_complete":false,"suggestions":[]}


══ DEV ENVIRONMENT PLAYBOOK ══
(When environment=DEVELOPMENT. Short, practical, cost-first.)

Goal: get the app running cheaply. No HA, no load balancer, no autoscaling, no monitoring.

Step 1 — GCP Region
  Ask which region. Recommend us-central1 (cheapest for most stacks).
  suggestions: ["us-central1", "us-east1", "europe-west1", "asia-south1"]

Step 2 — Instance type
  Look at the detected runtime services and ports. Recommend e2-micro for a simple API,
  e2-small if the README mentions multiple services running in the same VM.
  suggestions: ["e2-micro", "e2-small", "e2-medium"]

Step 3 — Disk size
  Only ask if the app has file uploads, media storage, or large logs. Default 20 GB.
  Skip this step if no storage need is detected.

Step 4 — Per detected service config (one service per turn):
  For each service in DETECTED_SERVICES that has no config yet:
  - cloud_sql     → ask engine (MySQL/PG), tier (recommend db-f1-micro), storage GB, skip HA
  - memorystore   → ask memory size (recommend 1 GB BASIC), purpose (cache / sessions / pub-sub)
  - cloud_storage → ask bucket name, class (recommend STANDARD), public (yes/no)
  - gke           → ask node count, machine type (recommend e2-small)
  - pubsub        → ask topic names, retention (recommend 7 days)
  Do NOT ask about: managed_instance_groups, cloud_load_balancing, cloud_cdn, cloud_monitoring,
  cloud_dns, autoscaling, backups, or IAM beyond default SA.

Step 5 — REQUIRED SECRETS (always ask — both DEV and PROD)
  The README lists env vars marked is_secret=true (API keys, passwords, tokens, URIs).
  These MUST be stored in GCP Secret Manager — never hardcoded in Terraform state.
  Explain: "Your README requires these secrets: {list}. I'll create a Secret Manager secret for each
  and have the VM fetch them at boot time via 'gcloud secrets versions access'.
  You'll upload the actual values to Secret Manager after deployment."
  Ask: confirm the list of secrets to store + whether they want to add any additional ones.
  Store in extracted_params.secrets_to_store (list of secret names).
  Set extracted_params.use_secret_manager = true.
  suggestions: ["Confirm — store all listed secrets", "Add more secrets", "Skip secrets for now"]

Step 6 — SSH CIDR
  Ask what CIDR to allow SSH from. Warn against 0.0.0.0/0.
  suggestions: ["<your_ip>/32", "10.0.0.0/8", "0.0.0.0/0 (not recommended)"]

After step 6 (and all detected services covered) → is_complete:true.


══ PROD ENVIRONMENT PLAYBOOK ══
(When environment=PRODUCTION. Deep, scalable, production-grade.)

CRITICAL: Follow this EXACT order. Never jump ahead.

STEP 1 — TRAFFIC & SCALE (ALWAYS first after environment is set)
  This is the most important question. Every tier recommendation downstream depends on it.
  Ask: expected daily active users (DAU) OR concurrent users OR requests/sec.
  Explain: "Your answer drives instance type, count, DB tier, cache size, and autoscaling thresholds."
  Offer four brackets the user can pick from:
    Starter   : < 1,000 DAU  (single VM, db-f1-micro, 1 GB cache)
    Growth    : 1k – 50k DAU (2-VM MIG, db-n1-standard-1 regional HA, 2 GB cache)
    Scale     : 50k – 500k DAU (3+ VM MIG + autoscaling, db-n1-standard-2 HA+replica, 4 GB HA cache)
    Enterprise: 500k+ DAU    (discuss architecture first)
  Store answer in extracted_params.traffic_tier AND extracted_params.expected_users.

STEP 2 — GCP REGION
  After traffic is known, recommend region considering: user geography (from README hints),
  latency, GDPR compliance if EU users detected, cost.
  Reference the traffic answer: "For {traffic_tier} traffic targeting {geography}, I recommend..."
  suggestions: ["us-central1", "us-east1", "europe-west1", "asia-south1", "asia-east1"]

STEP 3 — HIGH AVAILABILITY ARCHITECTURE
  Ask if they need multi-zone HA or a simpler setup.
  Recommendation MUST be derived from traffic_tier:
    Starter   → single Compute Engine VM with startup script (no LB)
    Growth+   → Managed Instance Group (MIG) + HTTP(S) Load Balancer
  Explain what MIG + LB gives: auto-healing, zero-downtime updates, traffic distribution.
  Store: extracted_params.use_mig (true/false), extracted_params.use_load_balancer (true/false)

STEP 4 — INSTANCE TYPE & COUNT
  Recommended machine type MUST reference traffic_tier and detected runtime services:
    Starter   → e2-small  × 1
    Growth    → e2-standard-2  × 2
    Scale     → e2-standard-4  × 3 + autoscaling
  Justify with: "Your {runtime} stack on {traffic_tier} traffic needs {vCPU}vCPU/{RAM}GB RAM..."
  suggestions derive from traffic_tier.

STEPS 5–15 — PER-SERVICE CONFIG (one service per turn, only detected services)
  For each service found in DETECTED_SERVICES that has no config yet, ask the right questions.
  Every recommendation MUST say: "Since you’re at {traffic_tier}..."

  cloud_sql (if detected):
    Ask engine (MySQL / PostgreSQL), tier, storage GB, HA (REGIONAL vs ZONAL), backup schedule.
    Tier defaults by traffic_tier:
      Starter → db-g1-small ZONAL,  Growth → db-n1-standard-1 REGIONAL,  Scale → db-n1-standard-2 REGIONAL + read replica

  memorystore (if detected):
    Ask memory size GB and tier (BASIC vs STANDARD_HA).
    Defaults: Starter→ 1 GB BASIC, Growth→ 2 GB STANDARD_HA, Scale→ 4 GB STANDARD_HA

  cloud_storage (if detected):
    Ask bucket name, storage class, versioning, lifecycle (auto-delete old versions), public CDN access.

  managed_instance_groups (if use_mig=true):
    Ask min/max instance count, CPU scale-up threshold, health-check HTTP path.
    Defaults: Starter N/A, Growth min=2/max=5 @70% CPU, Scale min=3/max=20 @60% CPU

  cloud_load_balancing (if use_mig=true):
    Ask if they need SSL (recommend yes), domain name (can skip for now).

  cloud_dns (if custom domain wanted):
    Ask domain name, ask if they want Cloud-managed SSL cert.

  cloud_cdn (if detected or use_mig=true and cloud_storage detected):
    Ask CDN origin (GCS bucket or backend service), cache mode (CACHE_ALL_STATIC vs USE_ORIGIN_HEADERS).

  gke (if detected):
    Ask Autopilot vs Standard, node pool machine type, min/max nodes.
    Defaults by traffic_tier.

  pubsub (if detected):
    Ask topic/subscription names, message retention (recommend 7 days), dead-letter topic (yes/no).

  cloud_monitoring (always for PROD):
    Ask alert email address and top 3 metrics to watch.
    Suggest based on detected stack (e.g. "For Socket.IO: active connections + memory + CPU").

  secret_manager (always for PROD):
    Ask which env vars should go into Secret Manager (pre-fill from README’s is_secret=true vars).

  iam_service_accounts (always for PROD):
    Ask if they want least-privilege service accounts per service (recommend yes).

  ssh_cidr (always):
    Ask SSH source CIDR. Warn: 0.0.0.0/0 is a security risk in production.
    suggestions: ["<your_ip>/32", "corporate_vpn_cidr"]

After ALL of the above detected+mandatory services are covered → is_complete:true.
"""

_BRIDGE = """\
KEY RULES (apply every turn):
1. Always cite the specific README finding that motivates your question before asking.
2. DEV: Ask ONLY what is in the DEV PLAYBOOK. Never ask about HA, LB, MIG, autoscaling,
   monitoring, secrets, domain, or backups.
3. PROD: The traffic_tier is the anchor for EVERY recommendation. Always say
   'Since you’re at {traffic_tier}...' before recommending a tier or count.
4. PROD: Follow the EXACT step order. You MUST ask TRAFFIC before REGION, REGION before HA,
   HA before INSTANCE TYPE. Never reorder.
5. Only ask about services that appear in DETECTED_SERVICES. Do not invent services.
6. suggestions[] must always be specific GCP values: machine types, region names,
   DB tier names, memory sizes, CIDR strings.
7. Keep messages conversational and <=5 lines. No walls of text.
"""

_README_PROMPT = """\
You are TerraBot — senior GCP architect. Analyze this README for production GCP deployment.
Return ONLY valid JSON. No markdown fences, no explanation outside JSON.

REQUIRED STRUCTURE:
{
  "extracted_params": {
    "project_name": "",
    "readme_summary": "A concise 1-2 paragraph summary capturing the core architecture and infra requirements from the README. This acts as the context for future LLM turns.",
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
    "storage_provider": "cloudinary|gcs|s3|none",
    "has_frontend": false,
    "frontend_type": "",
    "frontend_served_by": "same_server|separate_server|cdn|none",
    "background_jobs": false,
    "background_job_description": "",
    "current_deployment_platform": "Render|Heroku|Vercel|Railway|self-hosted|unknown",

    "suggested_provider": "gcp",
    "suggested_provider_reason": ["reason1", "reason2"],
    "suggested_instance_dev": "e2-micro",
    "suggested_instance_prod": "e2-standard-2",
    "dependencies": [],

    "infrastructure_warnings": [
      {
        "severity": "critical|warning|info",
        "category": "database_mismatch|missing_env_var|external_service|port_conflict|hosting_model",
        "message": "",
        "recommendation": ""
      }
    ],
    "detected_services": ["compute_engine", "vpc", "firewall_rules", "iam_service_accounts"]
  },
  "message": "12-15 line greeting (see GREETING FORMAT below)",
  "suggestions": ["Development", "Production"]
}

GREETING FORMAT:
Line 1:    "Welcome! I'm **TerraBot** — I just analyzed your [project] README! 🚀"
Line 2:    "Here's what I found:"
Lines 3-9: one specific bullet per detected tech — version, hosting model, purpose
Lines 10-11: infrastructure needed; if Atlas → say "MongoDB Atlas (external — no Cloud SQL needed, just inject MONGO_URI)"
Lines 12-13: why GCP fits this specific stack (be concrete, not generic)
Lines 14-15: "Since we're deploying to GCP — **Development** (single VM, low cost) or **Production** (HA, MIG, full monitoring)?"

CRITICAL RULES:
1.  Detect database from ORM (Mongoose→MongoDB, psycopg2→PostgreSQL), imports, env vars (MONGO_URI→MongoDB)
2.  database_hosting_model='atlas' → DO NOT include cloud_sql in detected_services
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


class ConversationManager:
    """TerraBot — GCP-only intelligent Terraform conversation guide."""

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

        sid = f"terr_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"

        if not owner.strip() or not repo.strip():
            return {
                "session_id": sid,
                "bot_response": (
                    "Hey! 👋 I'm **TerraBot** — your GCP Terraform guide.\n"
                    "I'll analyze your GitHub README and generate production-grade GCP infrastructure.\n"
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
        for s in GCP_CORE:
            if s not in svcs:
                svcs.append(s)
        extracted["detected_services"] = {"gcp": svcs[:15]}
        extracted.update({
            "github_owner": owner, "github_repo": repo,
            "github_branch": github_branch, "cloud_provider": "gcp",
            "readme_context": self._build_readme_context(readme, extracted, owner, repo),
        })

        greeting = str(analysis.get("message") or "Should we target **Development** or **Production**?")
        session = ConversationSession(
            session_id=sid, provider="gcp",
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
        session.collected_parameters["cloud_provider"] = "gcp"
        self._consolidate_mig_config(session.collected_parameters)
        session.is_complete = bool(data["is_complete"])
        session.updated_at  = datetime.now()

        if session.is_complete:
            self._apply_defaults(session.collected_parameters)
            session.status = ConversationStatus.COMPLETE
            cost = self._calculate_cost(session.collected_parameters)
            data["message"] = (
                f"✅ Perfect! I have everything needed for your GCP infrastructure.\n\n"
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
    def _consolidate_mig_config(cp: dict) -> None:
        """
        Gather any MIG sub-keys the LLM may have extracted separately into one
        'autoscaling_config' dict.  Once all four fields are present the MIG service
        is considered fully configured and will no longer appear in _svc_hints.
        """
        # Aliases the LLM commonly uses for each sub-field
        _ALIASES: dict[str, list[str]] = {
            "min_instances":    ["min_instances", "mig_min_instances", "autoscaling_min", "min_vms"],
            "max_instances":    ["max_instances", "mig_max_instances", "autoscaling_max", "max_vms"],
            "cpu_threshold":    ["cpu_threshold", "mig_cpu_threshold", "cpu_utilization", "cpu_target", "cpu_percent"],
            "health_check_path":["health_check_path", "mig_health_check_path", "health_check", "healthcheck_path"],
        }
        cfg = cp.setdefault("autoscaling_config", {}) if isinstance(cp.get("autoscaling_config"), dict) else {}
        if not isinstance(cp.get("autoscaling_config"), dict):
            cp["autoscaling_config"] = cfg

        for canonical, aliases in _ALIASES.items():
            if canonical in cfg:
                continue  # already have it
            for alias in aliases:
                if alias in cp and cp[alias] not in (None, ""):
                    cfg[canonical] = cp.pop(alias)
                    break
                # also check one level inside autoscaling_config itself (LLM may nest it)
                nested = cp.get("autoscaling_config") or {}
                if isinstance(nested, dict) and alias in nested:
                    cfg[canonical] = nested[alias]
                    break

        # Normalise cpu_threshold to a float 0-1 if expressed as a whole number (e.g. 60 → 0.6)
        t = cfg.get("cpu_threshold")
        if isinstance(t, (int, float)) and t > 1:
            cfg["cpu_threshold"] = round(t / 100, 2)

    def add_message_to_history(self, session_id: str, role: str, content: str) -> None:
        session = self.get_session(session_id)
        if session:
            session.messages.append({"role": role, "content": content})
            self._save_session(session)

    def _build_llm_messages(self, session_id: str, user_message: str) -> List[Dict[str, str]]:
        session = self.get_session(session_id)
        if not session:
            return []
        
        readme_ctx = str(session.collected_parameters.get("readme_context", ""))[:3500]
        snapshot   = json.dumps(session.collected_parameters, indent=2)
        env        = str(session.collected_parameters.get("environment", "") or "NOT SET").upper()
        turns      = sum(1 for m in session.messages if m["role"] == "user")
        
        context = (
            f"\\nREADME CONTEXT:\\n{readme_ctx}\\n\\n"
            f"STATE: GCP | env={env} | turn={turns}\\n"
            f"COLLECTED:\\n{snapshot}\\n"
        )
        messages = [{"role": "system", "content": _SYSTEM + "\\n\\n" + _BRIDGE + context + self._svc_hints(session)}]
        for m in session.messages:
            if m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})
        return messages

    async def _process_llm_response(self, session_id: str, llm_response: str) -> Any:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
            
        data = self._parse_json(llm_response)
        
        self._deep_merge(session.collected_parameters, data.get("extracted_params", {}))
        session.collected_parameters["cloud_provider"] = "gcp"
        self._consolidate_mig_config(session.collected_parameters)
        session.is_complete = bool(data.get("is_complete", False))
        session.updated_at  = datetime.now()
        
        if session.is_complete:
            self._apply_defaults(session.collected_parameters)
            session.status = ConversationStatus.COMPLETE
            cost = self._calculate_cost(session.collected_parameters)
            data["message"] = (
                f"✅ Perfect! I have everything needed for your GCP infrastructure.\\n\\n"
                f"**💰 Cost Estimate:**\\n{cost}\\n\\n"
                "Generating `main.tf`, `variables.tf`, `outputs.tf` and a GitHub Actions workflow now! 🚀"
            )
            
        session.messages.append({"role": "assistant", "content": data.get("message", "")})
        self._save_session(session)
        
        return ChatMessageResponse(
            session_id=session_id,
            bot_response=data.get("message", ""),
            collected_parameters=session.collected_parameters,
            is_complete=session.is_complete,
            suggestions=data.get("suggestions", []),
        )

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

        context = (
            f"\nREADME CONTEXT:\n{readme_ctx}\n\n"
            f"STATE: GCP | env={env} | turn={turns}\n"
            f"COLLECTED:\n{snapshot}\n"
        )

        messages = [{"role": "system", "content": _SYSTEM + "\n\n" + _BRIDGE + context + self._svc_hints(session)}]
        for m in session.messages:
            if m["role"] in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})

        from app.services import langfuse_service
        full_context = "\\n\\n".join([m.get("content", "") for m in messages])
        trace = langfuse_service.create_trace(
            name="conversation-turn",
            session_id=session.session_id,
            user_id="terraform",
            input=full_context,
        )

        raw = await self.llm_service.chat_completion(
            messages=messages, temperature=0.5, max_tokens=16000,
            response_format={"type": "json_object"}, timeout=120,
            _trace=trace,
        )

        if trace:
            try:
                parsed_data = self._parse_json(raw)
                trace.update(output=parsed_data)
            except Exception as e:
                logger.error("Failed to update Langfuse trace output: %s", e)

        return raw

    def _svc_hints(self, session: ConversationSession) -> str:
        cp    = session.collected_parameters
        svcs  = (cp.get("detected_services") or {}).get("gcp", [])
        env   = str(cp.get("environment", "")).upper()
        tier  = str(cp.get("traffic_tier", "")).capitalize() or "unknown"
        is_prod = env == "PRODUCTION"
        t     = f" [{tier} traffic]" if is_prod and tier != "unknown" else ""
        # DEV: only ask about services the app actually needs, nothing prod-only
        dev_checks = [
            ("cloud_sql",     "cloud_sql_tier",    f"Cloud SQL{t}: engine (MySQL/PG), tier → db-f1-micro, storage GB, skip HA"),
            ("memorystore",   "memorystore_tier",   f"Memorystore{t}: memory size (recommend 1 GB BASIC), purpose"),
            ("cloud_storage", "storage_config",     f"Cloud Storage{t}: bucket name, class → STANDARD, public yes/no"),
            ("gke",           "container_config",   f"GKE{t}: node count, machine type → e2-small"),
            ("pubsub",        "messaging_config",   f"Pub/Sub{t}: topic names, retention → 7 days"),
            # Always ask about secrets regardless of env — Secret Manager is used in both DEV and PROD
            ("secret_manager", "use_secret_manager", f"Secret Manager: confirm secret names from README is_secret vars to store (fetched at VM boot, never hardcoded)"),
        ]
        # PROD: full service coverage including HA/MIG/LB/monitoring/security
        prod_checks = dev_checks + [
            ("managed_instance_groups", "autoscaling_config",
             f"MIG{t}: min/max instances, CPU scale threshold, health-check path"),
            ("cloud_load_balancing", "load_balancer_config",
             f"Cloud LB{t}: SSL yes/no, domain name (can skip)"),
            ("cloud_cdn",     "cdn_enabled",       f"Cloud CDN{t}: origin (GCS or backend), cache mode"),
            ("cloud_dns",     "dns_config",         f"Cloud DNS{t}: domain name, managed SSL cert yes/no"),
            ("secret_manager","secret_config",      f"Secret Manager{t}: which env vars (pre-filled from README secrets) go in SM"),
            ("cloud_monitoring", "monitoring_config",
             f"Cloud Monitoring{t}: alert email, top-3 metrics for the detected stack"),
            ("iam_service_accounts", "iam_config",
             f"IAM{t}: least-privilege service accounts per detected service (recommend yes)"),
        ]
        checks = prod_checks if is_prod else dev_checks
        # Build pending list, but handle MIG and secret_manager specially
        pending = []
        for svc, key, hint in checks:
            # secret_manager is handled unconditionally below
            if svc == "secret_manager":
                continue
            if svc not in svcs:
                continue
            if svc == "managed_instance_groups":
                cfg = cp.get("autoscaling_config") or {}
                if not isinstance(cfg, dict):
                    cfg = {}
                missing = [f for f in ("min_instances", "max_instances", "cpu_threshold", "health_check_path")
                           if not cfg.get(f)]
                if missing:
                    pending.append(
                        f"  - MIG{t}: still need → {', '.join(missing)}. "
                        f"Already collected: {json.dumps({k: cfg[k] for k in cfg if cfg[k]})}"
                    )
            elif not cp.get(key):
                pending.append(f"  - {hint}")

        # ── Secret Manager (unconditional — ask whenever README has is_secret vars) ──
        if not cp.get("use_secret_manager"):
            secret_vars = [
                ev.get("name", "") for ev in (cp.get("required_env_vars") or [])
                if isinstance(ev, dict) and ev.get("is_secret")
            ]
            if secret_vars:
                pending.append(
                    f"  - Secret Manager (REQUIRED for both DEV & PROD): "
                    f"README has {len(secret_vars)} secret(s): {', '.join(secret_vars)}. "
                    f"Confirm list \u2192 Terraform will create SM secrets + grant VM SA access. "
                    f"Real values uploaded by user after deploy."
                )

        if not cp.get("ssh_cidr"):
            note = "production (never 0.0.0.0/0)" if is_prod else "dev"
            pending.append(f"  - SSH CIDR: restrict source to a specific IP/range for {note}")
        return ("\n\nDETECTED GCP SERVICES — cover one per turn:\n" + "\n".join(pending) + "\n") if pending else ""

    # ── README analysis ────────────────────────────────────────────────────────

    async def _analyze_readme(self, readme: str) -> Dict[str, Any]:
        prompt = _README_PROMPT + readme[:18000]

        from app.services import langfuse_service
        trace = langfuse_service.create_trace(
            name="readme-analysis",
            session_id=None,
            user_id="terraform",
            input=prompt,
        )

        raw = await self.llm_service.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5, max_tokens=16000,
            response_format={"type": "json_object"}, timeout=120,
            _trace=trace,
        )
        m = re.search(r'(\{.*\})', raw.strip(), re.DOTALL)
        data = json.loads(m.group(1) if m else raw)

        if trace:
            try:
                trace.update(output=data)
            except Exception as e:
                logger.error("Failed to update Langfuse trace output: %s", e)

        return data

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
        summary = str(e.get("readme_summary") or e.get("workload_description", ""))

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
            f"\nREADME SUMMARY:\n{summary}"
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
                "provider":    "gcp",
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
        region = p.get("gcp_region") or p.get("region") or "us-central1"

        return {
            "cloud_provider":       "gcp",
            "environment":          p.get("environment", "dev"),
            "project_name":         p.get("project_name") or p.get("github_repo") or "app",
            "workload_description": p.get("workload_description", ""),
            "language":             p.get("language", ""),
            "dependencies":         p.get("dependencies", []),
            "ports":                p.get("ports", []),
            "ssh_allowed_cidrs":    [c for c in (p.get("ssh_allowed_cidrs") or []) if isinstance(c, str) and c.strip()],
            "instance_type":        p.get("instance_type"),
            "instance_count":       p.get("instance_count", 1),
            "storage_size_gb":      p.get("storage_size_gb", 20),
            "storage_type":         p.get("storage_type", "pd-balanced"),
            "vpc_cidr":             p.get("vpc_cidr", "10.0.0.0/16"),
            "subnet_count":         p.get("subnet_count", 2),
            "enable_public_ip":     p.get("enable_public_ip", True),
            "os_image":             p.get("os_image") or "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts",
            "gcp_project_id":       p.get("gcp_project_id", ""),
            "gcp_region":           region,
            "region":               region,
            "gcp_zone":             p.get("gcp_zone") or region + "-a",
            "ssh_username":         p.get("ssh_username", "ubuntu"),
            "github_owner":         p.get("github_owner", ""),
            "github_repo":          p.get("github_repo", ""),
            "github_branch":        p.get("github_branch", ""),
            "readme_context":       p.get("readme_context", ""),
            "has_database":         p.get("has_database", False),
            "database_type":        p.get("database_type", "none"),
            "database_hosting_model": p.get("database_hosting_model", "managed_cloud"),
            "cloud_sql_tier":       p.get("cloud_sql_tier", ""),
            "has_cache":            p.get("has_cache", False),
            "cache_type":           p.get("cache_type", "none"),
            "memorystore_tier":     p.get("memorystore_tier", ""),
            "memorystore_size_gb":  p.get("memorystore_size_gb", 1),
            "storage_needs":        p.get("storage_needs", False),
            "storage_provider":     p.get("storage_provider", "none"),
            "has_frontend":         p.get("has_frontend", False),
            "frontend_type":        p.get("frontend_type", ""),
            "frontend_served_by":   p.get("frontend_served_by", ""),
            "has_websockets":       p.get("has_websockets", False),
            "websocket_library":    p.get("websocket_library", "none"),
            "has_message_queue":    p.get("has_message_queue", False),
            "has_load_balancer":    p.get("has_load_balancer", False),
            "enable_autoscaling":   p.get("enable_autoscaling", False),
            "enable_monitoring":    p.get("enable_monitoring", True),
            "enable_backups":       p.get("enable_backups", False),
            "enable_cloud_cdn":     p.get("enable_cloud_cdn", False),
            "background_jobs":      p.get("background_jobs", False),
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
            "alert_email":          p.get("alert_email", ""),
            "custom_domain":        p.get("custom_domain", ""),
            "secrets_management":   p.get("secrets_management", "none"),
        }

    # ── Defaults & cost ────────────────────────────────────────────────────────

    @staticmethod
    def _apply_defaults(p: Dict[str, Any]) -> None:
        is_prod = p.get("environment") in ("prod", "production")
        count   = int(p.get("instance_count", 1) or 1)
        p.setdefault("vpc_cidr",         "10.0.0.0/16")
        p.setdefault("subnet_count",     2 if is_prod else 1)
        p.setdefault("storage_size_gb",  20)
        p.setdefault("storage_type",     "pd-balanced")
        p.setdefault("enable_public_ip", True)
        p.setdefault("monitoring_enabled", True)
        p.setdefault("auto_scaling_enabled", is_prod and count > 1)
        p.setdefault("backup_enabled",   is_prod and p.get("has_database", False))
        p.setdefault("ssh_username",     "ubuntu")
        p.setdefault("enable_https",     is_prod and count > 1)
        p.setdefault("enable_cloud_cdn", False)
        p.setdefault("gcp_region",       p.get("region", "us-central1"))

    def _calculate_cost(self, p: dict) -> str:
        is_prod   = p.get("environment") in ("prod", "production")
        count     = int(p.get("instance_count", 1) or 1)
        itype     = str(p.get("instance_type") or "")
        disk_gb   = float(p.get("storage_size_gb", 20) or 20)
        disk_t    = str(p.get("storage_type") or "pd-balanced")
        has_db    = p.get("has_database", False)
        db_host   = str(p.get("database_hosting_model") or "").lower()
        has_cache = p.get("has_cache", False)
        has_lb    = p.get("has_load_balancer", False) or (is_prod and count > 1)
        has_bkt   = p.get("storage_needs", False) and p.get("storage_provider", "none") not in ("cloudinary", "external")
        bkt_gb    = float(p.get("bucket_size_gb", 50) or 50)

        INST = {
            "e2-micro": 7.00, "e2-small": 14.00, "e2-medium": 28.00,
            "e2-standard-2": 48.55, "e2-standard-4": 97.10, "e2-standard-8": 194.20,
            "n1-standard-1": 24.27, "n1-standard-2": 48.54,
            "n2-standard-2": 58.24, "n2-standard-4": 116.48,
        }
        DISK = {"pd-balanced": 0.10, "pd-ssd": 0.17, "pd-standard": 0.04}
        SQL  = {"db-f1-micro": 7.67, "db-g1-small": 25.46, "db-n1-standard-1": 46.48, "db-n1-standard-2": 92.97}
        MEM  = {"BASIC": 0.049, "STANDARD_HA": 0.098}

        lines, total = [], 0.0

        comp = count * INST.get(itype, 14.00)
        total += comp
        lines.append(f"  • Compute Engine ({count}x {itype or 'e2-small'}): ${comp:.2f}/mo")

        disk_cost = count * disk_gb * DISK.get(disk_t, 0.10)
        total += disk_cost
        lines.append(f"  • Persistent Disk ({count}x {int(disk_gb)}GB {disk_t}): ${disk_cost:.2f}/mo")

        if has_lb:
            total += 18.00
            lines.append("  • Cloud Load Balancing: ~$18.00/mo")

        if has_db and db_host not in ("atlas", "external_uri"):
            tier = str(p.get("cloud_sql_tier") or "db-g1-small")
            sc   = SQL.get(tier, 25.46)
            if is_prod and p.get("availability_type") == "REGIONAL":
                sc *= 2
            stc  = float(p.get("db_storage_gb", 20) or 20) * 0.17
            total += sc + stc
            ha = " (REGIONAL HA)" if is_prod and p.get("availability_type") == "REGIONAL" else ""
            lines.append(f"  • Cloud SQL ({tier}{ha}): ${sc:.2f}/mo + ${stc:.2f}/mo storage")
        elif has_db and db_host in ("atlas", "external_uri"):
            lines.append("  • MongoDB Atlas: NOT included — billed by MongoDB Inc. (M0 free · M10 ~$57/mo)")

        if has_cache:
            tier = str(p.get("memorystore_tier") or "BASIC")
            mb   = float(p.get("memorystore_size_gb", 1) or 1)
            mc   = mb * MEM.get(tier, 0.049) * 730
            total += mc
            lines.append(f"  • Memorystore ({tier}, {mb}GB): ${mc:.2f}/mo")

        if has_bkt:
            gcs = bkt_gb * 0.020
            total += gcs
            lines.append(f"  • Cloud Storage (~{int(bkt_gb)}GB Standard): ~${gcs:.2f}/mo")

        if is_prod:
            total += 7.30
            lines.append("  • Cloud NAT: ~$7.30/mo")

        if p.get("enable_monitoring", True):
            mon = 0.01 * count * 30
            total += mon
            lines.append(f"  • Cloud Monitoring & Logging: ~${mon:.2f}/mo")

        return (
            "\n".join(lines) + "\n"
            f"  {'─' * 44}\n"
            f"  💰 **Estimated Total: ~${total:.2f}/month** (excludes egress)"
        )

    # ── Static helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConversationManager._deep_merge(base[k], v)
            else:
                base[k] = v