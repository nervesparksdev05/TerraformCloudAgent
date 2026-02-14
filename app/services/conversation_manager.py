"""
Conversation Manager - README-driven deployment flow (Aligned, NO FORMS).

Flow:
1) User provides GitHub URL + provider (+ optional github_token)
2) Fetch README (GitHubService)
3) Analyze README (ReadmeAnalyzer) -> terraform_hints aligned with Terraform generator prompt
4) Chatbot collects ONLY critical missing inputs for real deployment
5) Build provider-neutral params -> LLM generates Terraform
6) User can request updates -> existing run edit/refine flow applies (Run endpoints)

NOTE:
- Validation (terraform fmt / terraform validate / tflint) should live in WorkflowEngine after files are generated.
  This file only manages conversation + building the terraform request payload.
"""

import json
import secrets
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.logger import get_logger
from app.models.conversation_schemas import (
    ChatMessageResponse,
    ConversationSession,
    ConversationStatus,
)
from app.services.github_service import get_github_service
from app.services.readme_analyzer import get_readme_analyzer
from app.services.llm_generator import LLMGenerator

logger = get_logger(__name__)


_ALLOWED_PROVIDERS = {"aws", "gcp", "azure", "digitalocean"}
_ALLOWED_ENVS = {"dev", "staging", "prod"}


class ConversationManager:
    """
    README-driven conversation manager (no forms).

    Stages:
    - ACTIVE: session created, README analyzed, chat ongoing
    - COMPLETE: minimum required inputs collected to generate Terraform
    """

    def __init__(self) -> None:
        # MongoDB persistence (optional)
        try:
            from app.core.database import db_manager

            if getattr(db_manager, "_client", None) is None:
                try:
                    db_manager.initialize()
                except Exception:
                    pass

            try:
                self.sessions_collection = db_manager.get_collection("sessions")
                logger.info("ConversationManager initialized with MongoDB persistence")
            except Exception:
                self.sessions_collection = None
                logger.warning("MongoDB unavailable, sessions will not be persisted")

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB connection: {e}")
            self.sessions_collection = None

        if self.sessions_collection is not None:
            self._ensure_indexes()

        # In-memory cache
        self.sessions: Dict[str, ConversationSession] = {}

        # Dependencies
        self.github_service = get_github_service()
        self.readme_analyzer = get_readme_analyzer()
        self.llm_generator = LLMGenerator()

        logger.info("ConversationManager initialized (README-driven, no forms)")

    def _ensure_indexes(self) -> None:
        try:
            # TTL index for automatic cleanup after 30 days
            self.sessions_collection.create_index(
                "updated_at",
                expireAfterSeconds=30 * 24 * 60 * 60,
            )
            # Ensure session_id is unique
            self.sessions_collection.create_index("session_id", unique=True)
            logger.info("Ensured indexes on sessions collection")
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")

    # ================================================================
    # SESSION MANAGEMENT
    # ================================================================

    def create_session(
        self,
        github_url: str,
        provider: Optional[str] = None,
        github_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new session.

        Provider is OPTIONAL - if not provided, bot will ask during chat.
        """
        provider = (provider or "").strip().lower() if provider else None
        if provider and provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"Invalid provider '{provider}'. Must be one of: {sorted(_ALLOWED_PROVIDERS)}")

        sid = f"sess_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"

        collected: Dict[str, Any] = {}
        if provider:
            collected["provider"] = provider
        if github_token:
            collected["github_token"] = github_token

        session = ConversationSession(
            session_id=sid,
            provider=provider,
            github_url=github_url,
            messages=[],
            collected_parameters=collected,
            is_complete=False,
            status=ConversationStatus.ACTIVE,
        )

        self.sessions[sid] = session

        # Persist to MongoDB
        if self.sessions_collection is not None:
            try:
                self.sessions_collection.insert_one(session.dict())
            except Exception as e:
                logger.error(f"Failed to persist session {sid}: {e}")

        logger.info(f"Created session: {sid} for repo: {github_url} (provider={provider or 'not set'})")

        # Conditional bot message
        if provider:
            return {
                "session_id": sid,
                "bot_response": (
                    "🚀 **README-Driven Deployment**\n\n"
                    f"Repo: `{github_url}`\n"
                    f"Provider: **{provider.upper()}**\n\n"
                    "Next: fetch README → analyze → then I'll ask only what's missing for real-world Terraform."
                ),
                "suggestions": [],
            }
        else:
            return {
                "session_id": sid,
                "bot_response": (
                    "🚀 **README-Driven Deployment**\n\n"
                    f"Repo: `{github_url}`\n\n"
                    "I'll fetch and analyze your README, then ask a few questions to generate production-ready Terraform.\n\n"
                    "**First: Which cloud provider?** (aws/gcp/azure/digitalocean)"
                ),
                "suggestions": ["aws", "gcp", "azure", "digitalocean"],
            }

    def get_session(self, sid: str) -> Optional[ConversationSession]:
        # In-memory first
        if sid in self.sessions:
            return self.sessions[sid]

        # MongoDB next
        if self.sessions_collection is not None:
            try:
                doc = self.sessions_collection.find_one({"session_id": sid})
                if doc:
                    doc.pop("_id", None)
                    session = ConversationSession(**doc)
                    self.sessions[sid] = session
                    logger.info(f"Loaded session {sid} from MongoDB")
                    return session
            except Exception as e:
                logger.error(f"Failed to load session {sid}: {e}")

        return None

    # ================================================================
    # README ANALYSIS
    # ================================================================

    async def analyze_readme(self, session_id: str) -> ChatMessageResponse:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        github_token = session.collected_parameters.get("github_token")

        # 1) Fetch README
        logger.info(f"Fetching README for {session.github_url}")
        readme_data = await self.github_service.fetch_readme(session.github_url, github_token)
        session.readme_content = readme_data["content"]

        # 2) Analyze README (should return terraform_hints aligned with generator prompt)
        logger.info(f"Analyzing README ({len(readme_data['content'])} chars)")
        analysis = await self.readme_analyzer.analyze(readme_data["content"], session.github_url)
        session.readme_analysis = analysis

        # 3) Store context + hints (as context, not final)
        tf_hints = analysis.get("terraform_hints") or {}
        session.collected_parameters["terraform_hints"] = tf_hints
        session.collected_parameters["readme_context"] = {
            "repo_url": session.github_url,
            "tech_stack": analysis.get("tech_stack", {}),
            "dependencies": analysis.get("dependencies", []),
            "deployment_hints": analysis.get("deployment_hints", []),
            "environment_variables": analysis.get("environment_variables", []),
            "ports": analysis.get("ports", []),
        }

        session.updated_at = datetime.now()
        self._save_session(session)

        # Response summary
        tech_stack = analysis.get("tech_stack", {})
        confidence = float(analysis.get("confidence", 0.0) or 0.0)
        ports = analysis.get("ports", [])
        port_list = ", ".join(
            str(p.get("port"))
            for p in ports
            if isinstance(p, dict) and p.get("port") is not None
        ) or "8000"

        missing = self._missing_minimum_inputs(session)

        summary_prompt = [
            {"role": "system", "content": "You just analyzed the user's GitHub README. You are a Friendly Cloud Infrastructure Guide. Provide a warm, enthusiastic summary of what you found in their README (tech stack, dependencies, ports). Then ask ONE friendly, README-specific question to start the conversation. For example: 'I see you're using MongoDB on port 27017—would you like a managed database or should I keep it simple and run it on the same server?' Keep it conversational and suggest a default."}
        ]
        
        chat_resp = await self.llm_generator.generate_chat_response(
            messages=summary_prompt,
            readme_analysis=session.readme_analysis,
            collected_parameters=session.collected_parameters,
            missing_fields=missing,
            turn_count=session.turn_count,
            topics_addressed=session.topics_addressed,
        )
        
        msg = chat_resp.get("bot_response", "Analysis complete!")
        # 5) Finalize Response & History
        msg = chat_resp.get("bot_response", "Analysis complete!")
        session.messages.append(
            {"role": "assistant", "content": msg, "timestamp": datetime.now().isoformat()}
        )
        session.turn_count += 1  # Analysis counts as a turn
        session.updated_at = datetime.now()
        self._save_session(session)

        return ChatMessageResponse(
            session_id=session_id,
            bot_response=msg,
            collected_parameters=session.collected_parameters,
            is_complete=False,
            suggestions=self._suggestions(session, missing),
            readme_preview=(readme_data["content"][:500] + "...")
            if len(readme_data["content"]) > 500
            else readme_data["content"],
            readme_analysis_summary={
                "language": tech_stack.get("language", "unknown"),
                "framework": tech_stack.get("framework", "unknown"),
                "workload_type": analysis.get("workload_type", "other"),
                "ports": ports,
                "confidence": confidence,
                "reasoning": analysis.get("reasoning", ""),
            },
            form_fields=None,
        )

    # ================================================================
    # CHAT
    # ================================================================

    async def send_message(self, session_id: str, user_message: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # 1) Add user message to history & Increment turn
        session.messages.append(
            {"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()}
        )
        session.turn_count += 1

        # 2) Extract parameters (Fast-path Regex + LLM)
        # We'll let the LLM do the heavy lifting in generate_chat_response,
        # but keep regex for simple, unambiguous values.
        extracted_regex = self._extract_parameters(user_message, session)
        if extracted_regex:
            session.collected_parameters.update(extracted_regex)

        # 3) Identify what's missing
        missing = self._missing_minimum_inputs(session)

        # 4) Generate LLM-driven conversational response
        # Increase history to 20 messages to prevent repetition
        history = [{"role": m["role"], "content": m["content"]} for m in session.messages[-20:]]
        
        chat_resp = await self.llm_generator.generate_chat_response(
            messages=history,
            readme_analysis=session.readme_analysis or {},
            collected_parameters=session.collected_parameters,
            missing_fields=missing,
            turn_count=session.turn_count,
            topics_addressed=session.topics_addressed,
        )

        bot_msg = chat_resp.get("bot_response", "I'm processing your request.")
        extracted_llm = chat_resp.get("extracted_parameters", {})
        topic = chat_resp.get("topic_addressed")
        
        if topic and topic not in session.topics_addressed:
            session.topics_addressed.append(topic)
            
        # Update session with LLM extracted parameters
        if extracted_llm:
            session.collected_parameters.update(extracted_llm)
            # Re-check missing after LLM extraction
            missing = self._missing_minimum_inputs(session)

        # 5) Check completion (Require depth!)
        # Completion triggers ONLY if turn_count >= 12 AND minimum params are met.
        if not missing and session.turn_count >= 12:
            session.is_complete = True
            session.status = ConversationStatus.COMPLETE

        # 6) Finalize bot response
        session.messages.append(
            {"role": "assistant", "content": bot_msg, "timestamp": datetime.now().isoformat()}
        )

        session.updated_at = datetime.now()
        self._save_session(session)

        return {
            "session_id": session_id,
            "bot_response": bot_msg,
            "suggestions": self._suggestions(session, missing),
            "collected_parameters": session.collected_parameters,
            "is_complete": session.is_complete,
        }

    def _compose_bot_message(self, session: ConversationSession, missing: List[str]) -> str:
        if session.readme_analysis is None:
            return "Please run README analysis first: **GET /conversations/{session_id}/analyze**"

        if not missing:
            return "✅ All set. Reply **Generate Terraform** to create the Terraform files."

        return f"I still need: **{missing[0]}**. Please share it."

    def _suggestions(self, session: ConversationSession, missing: List[str]) -> List[str]:
        if not missing:
            return ["Generate Terraform", "Set to prod", "Set to dev", "Change region"]

        m = missing[0].lower()
        if "environment" in m or "mode" in m:
            return ["dev", "staging", "prod"]
        if "expected_users" in m:
            return ["10", "100", "1000"]
        if "region" in m or "location" in m:
            return ["ap-south-1", "us-east-1", "eu-west-1", "us-central1", "westeurope"]
        if "ssh_allowed_cidrs" in m:
            return ["<your_ip>/32", "49.xx.xx.xx/32"]
        if "gcp_project_id" in m:
            return ["my-gcp-project-id"]
        if "digitalocean auth" in m:
            return ["I will set env vars", "Here is do_token: <token>"]
        return []

    # ================================================================
    # REQUIRED MINIMUM INPUTS (LLM fills the rest)
    # ================================================================

    def _missing_minimum_inputs(self, session: ConversationSession) -> List[str]:
        p = session.collected_parameters
        provider = (p.get("provider") or session.provider or "").lower().strip()
        missing: List[str] = []

        # provider is required (should already exist, but keep safe)
        if not provider or provider not in _ALLOWED_PROVIDERS:
            missing.append("provider (aws/gcp/azure/digitalocean)")

        # environment is required to apply dev vs prod defaults
        env = (p.get("environment") or p.get("mode") or "").lower().strip()
        if env not in _ALLOWED_ENVS:
            missing.append("environment/mode (dev/staging/prod)")

        # region/location is strongly recommended for real deployment (soft required)
        if not p.get("region") and not p.get("location"):
            missing.append("region/location (e.g., ap-south-1, us-east-1, us-central1, westeurope)")

        # prod sizing signal
        if env == "prod" and p.get("expected_users") is None:
            missing.append("expected_users (rough number, e.g., 1000)")

        # security: SSH CIDRs (never default to 0.0.0.0/0)
        if p.get("ssh_allowed_cidrs") is None:
            missing.append("ssh_allowed_cidrs (your IP in CIDR, e.g., 49.xx.xx.xx/32)")

        # provider-specific hard requirements (only if you are NOT relying on env-based auth)
        if provider == "gcp" and not p.get("gcp_project_id"):
            missing.append("gcp_project_id (required for GCP)")
        if provider == "digitalocean":
            # Prefer env-based auth, but still prompt for how they will authenticate
            if not p.get("do_token") and not p.get("do_auth_mode"):
                missing.append("DigitalOcean auth (either provide do_token OR confirm you will use env vars)")

        return missing

    # ================================================================
    # PARAM EXTRACTION (lightweight)
    # ================================================================

    def _extract_parameters(self, user_message: str, session: ConversationSession) -> Dict[str, Any]:
        msg = (user_message or "").strip()
        m = msg.lower()
        out: Dict[str, Any] = {}

        # provider
        for prov in _ALLOWED_PROVIDERS:
            if re.search(rf"\b{re.escape(prov)}\b", m):
                out["provider"] = prov
                session.provider = prov
                break

        # environment/mode
        if "production" in m or re.search(r"\bprod\b", m):
            out["environment"] = "prod"
        elif "staging" in m or re.search(r"\bstage\b", m):
            out["environment"] = "staging"
        elif "development" in m or re.search(r"\bdev\b", m):
            out["environment"] = "dev"

        # expected users
        users_match = re.search(r"(expected_users|users)\s*[:=]?\s*(\d+)", m)
        if users_match:
            out["expected_users"] = int(users_match.group(2))

        # region/location patterns:
        # AWS: ap-south-1, us-east-1
        aws_region = re.search(r"\b([a-z]{2}-[a-z]+-\d)\b", m)
        if aws_region:
            reg = aws_region.group(1)
            out["region"] = reg
            # Infer provider if missing
            if "provider" not in out and not session.provider:
                out["provider"] = "aws"
                session.provider = "aws"
        # GCP: us-central1, asia-south1, europe-west1
        gcp_loc = re.search(r"\b([a-z]+-[a-z]+[0-9])\b", m)
        if gcp_loc:
            reg = gcp_loc.group(1)
            if "region" not in out:
                out["location"] = reg
            # Infer provider if missing
            if "provider" not in out and not session.provider:
                out["provider"] = "gcp"
                session.provider = "gcp"

        # Azure: westeurope, eastus, centralindia (loose)
        azure_loc = re.search(r"\b(westeurope|northeurope|eastus|westus|centralindia|southeastasia)\b", m)
        if azure_loc and "region" not in out and "location" not in out:
            out["location"] = azure_loc.group(1)

        # ssh cidrs (allow multiple)
        cidrs = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}\b", msg)
        if cidrs:
            out["ssh_allowed_cidrs"] = cidrs

        # gcp_project_id
        gcp_proj = re.search(r"(gcp_project_id|project_id)\s*[:=]\s*([a-z0-9\-]+)", m)
        if gcp_proj:
            out["gcp_project_id"] = gcp_proj.group(2)

        # DigitalOcean auth
        if re.search(r"\b(do_token|digitalocean_token)\b", m):
            tok = re.search(r"(do_token|digitalocean_token)\s*[:=]\s*([A-Za-z0-9_\-\.]+)", msg)
            if tok:
                out["do_token"] = tok.group(2)
        if "env var" in m or "environment variable" in m:
            # user is indicating they will use env-based auth
            out["do_auth_mode"] = "env"

        return out

    # ================================================================
    # TERRAFORM REQUEST BUILDING (ALIGNED WITH TERRAFORM LLM PROMPT)
    # ================================================================

    def build_terraform_request(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if not session or not session.is_complete:
            raise ValueError("Session not found or incomplete")

        p = session.collected_parameters
        analysis = session.readme_analysis or {}
        tf_hints = analysis.get("terraform_hints") or {}

        provider = (p.get("provider") or session.provider or "").lower().strip()
        if provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"Invalid/missing provider in session: {provider}")

        # Hints expected from analyzer:
        networking = tf_hints.get("networking") or {
            "mode": "create",
            "subnets": {"public": True, "private": False},
            "nat_gateway": False,
        }
        resources = tf_hints.get("resources") or []

        # Apply user overrides
        if isinstance(p.get("networking"), dict):
            networking.update(p["networking"])
        if isinstance(p.get("resources"), list):
            resources = p["resources"]

        # Security defaults (NEVER allow 0.0.0.0/0 for SSH in generator)
        ssh_allowed_cidrs = p.get("ssh_allowed_cidrs") or ["127.0.0.1/32"]

        # Attach SSH CIDRs to compute resources if not present
        for r in resources:
            if isinstance(r, dict) and (r.get("type") or "").lower() == "compute":
                r.setdefault("ssh_allowed_cidrs", ssh_allowed_cidrs)

        env = (p.get("environment") or p.get("mode") or "dev").lower().strip()
        if env not in _ALLOWED_ENVS:
            env = "dev"

        expected_users = p.get("expected_users")
        if expected_users is None:
            expected_users = analysis.get("expected_users_hint") or 10

        req: Dict[str, Any] = {
            "provider": provider,
            # region/location: keep both; provider-specific generator decides
            "region": p.get("region"),
            "location": p.get("location"),
            "environment": env,
            "expected_users": int(expected_users),
            "traffic_level": p.get("traffic_level", "low"),
            "availability": p.get("availability", "single_zone"),
            "project_name": p.get("project_name") or self._infer_project_name(session.github_url),
            "workload_description": analysis.get("reasoning") or f"Infrastructure for {session.github_url}",
            "networking": networking,   # ✅ networking handled, LB removed upstream per your requirement
            "resources": resources,
            "encryption": p.get("encryption", True),
            "public_exposure": p.get("public_exposure", None),
            "ssh_allowed_cidrs": ssh_allowed_cidrs,
            "readme_context": p.get("readme_context") or {
                "repo_url": session.github_url,
                "tech_stack": analysis.get("tech_stack", {}),
                "dependencies": analysis.get("dependencies", []),
                "deployment_hints": analysis.get("deployment_hints", []),
                "environment_variables": analysis.get("environment_variables", []),
                "ports": analysis.get("ports", []),
            },
        }

        # Provider mandatory inputs (pass-through)
        if provider == "gcp":
            req["gcp_project_id"] = p.get("gcp_project_id")
        if provider == "digitalocean":
            # Prefer env-based auth; token optional if they choose env mode
            req["do_token"] = p.get("do_token")
            req["do_auth_mode"] = p.get("do_auth_mode", None)

        return req

    def _infer_project_name(self, github_url: str) -> str:
        try:
            parts = github_url.rstrip("/").split("/")
            repo = parts[-1].replace(".git", "")
            repo = re.sub(r"[^a-zA-Z0-9\-]", "-", repo).strip("-").lower()
            return repo or "app"
        except Exception:
            return "app"

    # ================================================================
    # PERSISTENCE + LISTING
    # ================================================================

    def _save_session(self, session: ConversationSession) -> None:
        if self.sessions_collection is not None:
            try:
                self.sessions_collection.update_one(
                    {"session_id": session.session_id},
                    {"$set": session.dict()},
                    upsert=True,
                )
            except Exception as e:
                logger.error(f"Failed to save session: {e}")

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.sessions_collection is None:
            sessions_list: List[Dict[str, Any]] = []
            for sid, session in list(self.sessions.items())[:limit]:
                sessions_list.append(
                    {
                        "session_id": sid,
                        "title": session.github_url or "New Session",
                        "provider": session.provider,
                        "updated_at": session.updated_at.isoformat()
                        if getattr(session, "updated_at", None)
                        else datetime.now().isoformat(),
                        "is_complete": session.is_complete,
                    }
                )
            return sessions_list

        try:
            cursor = self.sessions_collection.find().sort("updated_at", -1).limit(limit)
            sessions_list: List[Dict[str, Any]] = []
            for doc in cursor:
                sessions_list.append(
                    {
                        "session_id": doc.get("session_id"),
                        "title": doc.get("github_url", "New Session"),
                        "provider": doc.get("provider", "unknown"),
                        "updated_at": doc.get("updated_at", datetime.now()).isoformat(),
                        "is_complete": doc.get("is_complete", False),
                    }
                )
            return sessions_list
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]

        if self.sessions_collection is not None:
            try:
                result = self.sessions_collection.delete_one({"session_id": session_id})
                return result.deleted_count > 0
            except Exception as e:
                logger.error(f"Failed to delete session: {e}")
                return False

        return True

    def add_run_to_session(self, session_id: str, run_id: str) -> None:
        session = self.get_session(session_id)
        if session:
            if not getattr(session, "run_ids", None):
                session.run_ids = []
            session.run_ids.append(run_id)
            session.updated_at = datetime.now()
            self._save_session(session)

    def get_collected_parameters(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        return session.collected_parameters

    def is_session_complete(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        return session.is_complete if session else False
