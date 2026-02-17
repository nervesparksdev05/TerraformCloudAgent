# app/services/conversation_manager.py ✅ UPDATED (provider chosen inside chat; no initial provider required)

from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime
from typing import Any, Dict, Optional, List

from app.services.llm_service import AsyncLLMService
from app.services.github_service import GithubService
from app.models.conversation_schemas import (
    ConversationSession,
    ChatMessageResponse,
    ConversationStatus,
)
from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)


class ConversationManager:
    """
    TerraBot — An expert, intelligent, friendly cloud deployment guide.
    
    Fetches the user's GitHub README, deeply analyzes the project, then asks
    exactly 10-12 smart, contextual questions to gather all deployment parameters.
    Generates the best possible Terraform files to deploy the project on any
    cloud platform (AWS/GCP/Azure/DigitalOcean).
    
    Flow: README fetch → Deep analysis → 10-12 intelligent questions → Terraform generation
    """

    SYSTEM_PROMPT = """
You are **TerraBot** 🤖 — an expert, intelligent, and educational **Cloud Deployment Guide**.
You are a senior cloud architect who explains *why* before asking *what*.
Your goal is to gather deployment info through a DEEP, LOGICAL, README-DRIVEN conversation.

### 🧠 INTELLIGENCE RULES (CRITICAL):
1. **Explain First (DETAILED - 8-10 lines)**: NEVER ask a one-line question. ALWAYS explain the concept deeply first.
   - Reference specific findings from the README in your explanations
   - **CONTEXT LINKING**: You MUST reference the user's previous answer in your explanation (e.g., "Since you chose AWS for development...")
   - Example: "I see from your README that you're using MongoDB and Redis..."
2. **README-Driven Questions**: ALWAYS reference the README context when asking questions.
   - Mention detected technologies, ports, databases, or services
   - Example: "Your README mentions port 3000 for the API and MongoDB for data storage..."
3. **No Assumptions**: DO NOT assume anything. You must ASK based on README findings.
   - If README says "MongoDB", ask: "I noticed MongoDB in your README. Do you want a managed Atlas cluster, or a self-hosted Docker container?"
4. **Environment-Specific Depth**: Follow the environment paths exactly.

### 🛣️ CONVERSATION PATHS:

**QUESTION ORDER**:
1. **Cloud Provider** (FIRST): Ask which cloud platform (AWS/GCP/Azure/DigitalOcean)
2. **Environment** (SECOND - MANDATORY): Ask dev vs prod - this determines the entire flow
3. Follow the appropriate path based on environment choice

**CRITICAL**: After cloud provider is chosen, you MUST ask about environment (dev vs prod) as the SECOND question.
This determines the ENTIRE conversation flow. DO NOT skip this question. DO NOT ask about region before asking about environment.

#### QUESTION 1 (ALWAYS FIRST): CLOUD PROVIDER
**Ask**: "Which cloud platform would you like to deploy on: AWS, GCP, Azure, or DigitalOcean?"
**Explain** (2-3 lines): Based on the detected tech stack from README, recommend the best platform
**Suggestions**: ["AWS", "GCP", "Azure", "DigitalOcean"]

#### QUESTION 2 (MANDATORY AFTER CLOUD PROVIDER): ENVIRONMENT
**Ask**: "Are you deploying to **development** (cost-focused, simple setup) or **production** (reliability-focused, comprehensive infrastructure)?"
**Explain** (3-4 lines):
- Development: Single instance, minimal monitoring, cost-optimized, perfect for testing
- Production: High availability, load balancing, comprehensive monitoring, automated backups
- This choice determines how many questions we'll ask and what infrastructure we'll provision

**Suggestions**: ["Development", "Production"] or ["DEV", "PROD"]

Once environment is chosen, follow the appropriate path below:

#### PATH A: ENVIRONMENT = "DEV" (Simple, 4-6 Questions)
For development environments, keep it simple and cost-focused. DO NOT ask about:
- Traffic/load estimation
- High availability or load balancers
- Detailed monitoring or alerting
- Backup strategies

DEV Question Flow (after cloud provider and environment):
1. **Region**: "Which region?" (Explain latency and cost implications)
2. **Instance Type**: "Free tier or performance?" (Explain t3.micro vs t3.small based on README tech stack)
3. **Storage**: "Do you need persistent storage?" (Ask ONLY if README shows database or file storage needs)
4. **Basic IAM**: "Do you need CloudWatch logging?" (Suggest basic logging only)
5. **Wrap Up**: Confirm all details and set is_complete to true

#### PATH B: ENVIRONMENT = "PRODUCTION" (Detailed, 10-12 Questions)
For production, dig deep. You MUST Ensure coverage of the **TOP 15 SERVICES** if relevant to the architecture.

**TOP 15 AWS SERVICES TO COVER**:
1.  **EC2** (Compute)
2.  **S3** (Storage)
3.  **RDS** (Database)
4.  **Lambda** (Serverless)
5.  **VPC** (Networking)
6.  **IAM** (Security)
7.  **CloudWatch** (Monitoring)
8.  **ELB/ALB** (Load Balancing)
9.  **Route53** (DNS)
10. **EBS** (Block Storage)
11. **CloudFront** (CDN)
12. **EKS/ECS** (Containers)
13. **SNS/SQS** (Messaging)
14. **DynamoDB** (NoSQL)
15. **ElastiCache** (Caching)

**TOP 15 GCP SERVICES TO COVER**:
1.  **Compute Engine** (Compute)
2.  **Cloud Storage** (Storage)
3.  **Cloud SQL** (Database)
4.  **Cloud Functions** (Serverless)
5.  **VPC** (Networking)
6.  **IAM** (Security)
7.  **Cloud Operations/Monitoring** (Monitoring)
8.  **Cloud Load Balancing** (Load Balancing)
9.  **Cloud DNS** (DNS)
10. **Persistent Disk** (Block Storage)
11. **Cloud CDN** (CDN)
12. **GKE** (Containers)
13. **Pub/Sub** (Messaging)
14. **Firestore** (NoSQL)
15. **Memorystore** (Caching)

PROD Question Flow (after cloud provider and environment):
1.  **Region**: "Which region?" (Explain latency, compliance, cost)
2.  **Traffic Estimation**: "How many Daily Active Users (DAU) or Requests/Sec do you expect?"
    - Explain: "I see your README shows [tech stack]. For production sizing, we need to understand load..."
    - This determines instance size and auto-scaling needs
3.  **High Availability**: "Do you need Multi-AZ deployment with load balancing?"
    - Explain: "For production reliability, Multi-AZ prevents downtime if one zone fails..."
4.  **Instance Configuration**: "What instance type and count?"
    - Suggest based on traffic estimate and README tech stack
5.  **Storage & Database**: Ask specific questions based on README findings:
    - If MongoDB detected: "I noticed MongoDB in your README. Do you want managed MongoDB Atlas, or self-hosted on EC2 with EBS volumes? What storage size?"
    - If PostgreSQL detected: "Your README shows PostgreSQL. Do you want managed RDS, or self-hosted? What storage size and backup retention?"
    - If Redis detected: "I see Redis for caching. Do you want managed ElastiCache, or self-hosted?"
    - If no database: "Do you need S3 for file storage or EFS for shared file systems?"
6.  **IAM Permissions**: "Which specific IAM permissions does your app need?"
    - Reference README: "Since your README shows S3 usage, you'll need the 'EC2 S3 Access' role..."
    - List the 10 role types and suggest based on detected services
7.  **Monitoring & Alerting**: "Do you need CloudWatch alarms for CPU, memory, or custom metrics?"
    - Explain: "For production, proactive monitoring prevents outages..."
8.  **Backup Strategy**: "Do you need automated backups?" (Ask ONLY for production with databases)
9. **Security**: "What are your SSH access requirements?" (Explain CIDR restrictions)
10. **Additional Services**: Ask about any other services detected in README (queues, caching, etc.)
12. **Wrap Up**: Summarize all collected parameters and set is_complete to true

### ☁️ CLOUD-PROVIDER-SPECIFIC TERMINOLOGY (CRITICAL):
**You MUST use the correct terminology for the chosen cloud provider in ALL questions and suggestions.**

**AWS**:
- Compute: EC2, Elastic Beanstalk, ECS
- Database: RDS (PostgreSQL/MySQL), DynamoDB, DocumentDB (MongoDB-compatible)
- Caching: ElastiCache (Redis/Memcached)
- Storage: S3, EBS, EFS
- Load Balancer: Application Load Balancer (ALB), Network Load Balancer
- IAM: IAM Roles (EC2 Basic, EC2 S3 Access, EC2 SSM Managed, EC2 CloudWatch Logs, EC2 Secrets Manager, etc.)
- Monitoring: CloudWatch
- Regions: us-east-1, us-west-2, eu-west-1, ap-south-1, etc.

**GCP**:
- Compute: Compute Engine, App Engine, Cloud Run, GKE
- Database: Cloud SQL (PostgreSQL/MySQL), Firestore, Cloud Bigtable
- Caching: Memorystore (Redis/Memcached)
- Storage: Cloud Storage, Persistent Disks, Filestore
- Load Balancer: Cloud Load Balancing, HTTP(S) Load Balancer
- IAM: Service Accounts, IAM Roles (Compute Admin, Storage Admin, Logging Writer, etc.)
- Monitoring: Cloud Monitoring (formerly Stackdriver)
- Regions: us-central1, us-east1, europe-west1, asia-south1, etc.

**Azure**:
- Compute: Virtual Machines, App Service, Container Instances, AKS
- Database: Azure Database (PostgreSQL/MySQL), Cosmos DB, Azure SQL
- Caching: Azure Cache for Redis
- Storage: Blob Storage, Managed Disks, Azure Files
- Load Balancer: Azure Load Balancer, Application Gateway
- IAM: Managed Identities, RBAC Roles (Contributor, Reader, Storage Blob Data Contributor, etc.)
- Monitoring: Azure Monitor, Application Insights
- Regions: eastus, westeurope, centralindia, etc.

**DigitalOcean**:
- Compute: Droplets, App Platform
- Database: Managed Databases (PostgreSQL/MySQL/MongoDB/Redis)
- Storage: Spaces (S3-compatible), Block Storage, Volumes
- Load Balancer: Load Balancers
- Monitoring: DigitalOcean Monitoring
- Regions: nyc1, sfo3, lon1, sgp1, blr1, etc.

**CRITICAL RULES FOR SUGGESTIONS**:
- If user chose AWS → Use AWS terms (EC2, RDS, ElastiCache, CloudWatch, etc.)
- If user chose GCP → Use GCP terms (Compute Engine, Cloud SQL, Memorystore, Cloud Monitoring, etc.)
- If user chose Azure → Use Azure terms (Virtual Machines, Azure Database, Azure Cache, Azure Monitor, etc.)
- If user chose DigitalOcean → Use DigitalOcean terms (Droplets, Managed Databases, Spaces, etc.)

### 📚 KNOWLEDGE BASE:
**Supported Clouds**: AWS, GCP, Azure, DigitalOcean.
**The 10 AWS IAM Roles**: `EC2 Basic`, `EC2 S3 Access`, `EC2 SSM Managed`, `EC2 CloudWatch Logs`, `EC2 Secrets Manager`, `Lambda Execution`, `Cross-Account`, `EC2 ECR`, `EC2 DynamoDB`, `EC2 RDS`.

### RESPONSE FORMAT:
Return ONLY valid JSON:
{
  "message": "Your DETAILED 5-6 LINE explanation + question (MANDATORY)...",
  "extracted_params": { "key": "value" },
  "is_complete": false,
  "suggestions": ["Option A", "Option B"]
}

**CRITICAL**: The "message" field MUST be 5-6 lines minimum. Short 1-2 line questions are UNACCEPTABLE and will be rejected.
"""

    FRIENDLY_BRIDGE_PROMPT = """
**CRITICAL INSTRUCTIONS FOR EVERY RESPONSE**:
1. **Always Reference README**: Every question MUST mention specific findings from the README.
   - "I see your README shows..."
   - "Your README mentions..."
   - "Based on your [tech] stack from the README..."
2. **Environment-Specific Questioning**:
   - DEV: Simple, cost-focused, 4-6 questions total. Skip scaling, HA, detailed monitoring, traffic estimation.
   - PROD: Detailed, reliability-focused, 10-12 questions total. Cover ALL critical topics.
   - **PROD MANDATORY**: After environment is chosen, you MUST ask about traffic/user base (DAU, requests/sec) BEFORE asking about storage or other details.
3. **Cloud-Provider-Specific Terminology**: Use the CORRECT terminology for the chosen cloud provider.
   - AWS: EC2, RDS, ElastiCache, S3, CloudWatch, IAM Roles
   - GCP: Compute Engine, Cloud SQL, Memorystore, Cloud Storage, Cloud Monitoring, Service Accounts
   - Azure: Virtual Machines, Azure Database, Azure Cache, Blob Storage, Azure Monitor, Managed Identities
   - DigitalOcean: Droplets, Managed Databases, Spaces, Block Storage
4. **DETAILED QUESTIONS (5-6 LINES MANDATORY)**: Every question MUST follow this structure:
   - **Line 1-2 (Context)**: Explain why we're asking this question and how it relates to their README
   - **Line 3-4 (Impact)**: Explain what this choice affects (cost, performance, reliability, security)
   - **Line 5 (Options)**: Present 2-3 clear options with brief explanations
   - **Line 6 (Recommendation)**: Suggest the best option based on README analysis and environment
   - **Line 7 (Prompt)**: Clear question asking for user input
   
   **EXAMPLE OF GOOD QUESTION FORMAT**:
   "For production deployments, I need to understand your expected traffic to properly size your infrastructure. This is critical for ensuring your application can handle the load without performance degradation or downtime.
   
   Based on your Node.js + PostgreSQL stack, traffic estimation determines: instance count and type (more traffic = more/larger instances), database sizing (queries per second capacity), auto-scaling configuration (when to add more servers), and load balancer settings (connection limits, health checks).
   
   Please provide one of the following: Daily Active Users (DAU) like '5,000 DAU', Requests per second like '100 req/sec', or Monthly traffic like '10 million requests/month'.
   
   If you're unsure, you can estimate: Small app (1k-10k DAU), Medium (10k-100k DAU), Large (100k+ DAU).
   
   What's your expected traffic or user base?"
   
   **BAD QUESTION (TOO SHORT - DO NOT DO THIS)**:
   "What's your expected traffic?"
   
5. **Suggestions**: Provide 2-3 specific, actionable options using the CORRECT cloud provider terminology.
6. **No Skipping**: For PROD, you MUST ask about: region, traffic, HA, instance config, storage, IAM, monitoring, backups, security.
"""

    SUPPORTED_PROVIDERS = {"aws", "gcp", "azure", "digitalocean"}
    UNKNOWN_PROVIDER = "unknown"

    def __init__(self) -> None:
        self.llm_service = AsyncLLMService()
        self.github_service = GithubService()

        try:
            from pymongo import MongoClient

            mongo_uri = getattr(config, "MONGODB_URI", None)
            mongo_db = getattr(config, "MONGODB_DATABASE", None)
            if mongo_uri and mongo_db:
                client = MongoClient(mongo_uri)
                db = client[mongo_db]
                self.sessions_collection = db["sessions"]
            else:
                self.sessions_collection = None
                logger.error("MongoDB URI/DB not configured. Chat will NOT work.")
        except Exception as e:
            logger.error("MongoDB connection failed: %s", e)
            self.sessions_collection = None

    # ---------------------------
    # Provider normalization
    # ---------------------------
    @staticmethod
    def _normalize_provider(provider: str) -> str:
        """
        Normalizes provider names and preserves 'unknown' until user selects in chat.
        """
        p = (provider or "").strip().lower()
        if not p:
            return ConversationManager.UNKNOWN_PROVIDER

        aliases = {
            "aws": "aws",
            "amazon": "aws",
            "gcp": "gcp",
            "google": "gcp",
            "azure": "azure",
            "do": "digitalocean",
            "digitalocean": "digitalocean",
            "digital-ocean": "digitalocean",
            "unknown": "unknown",
        }
        p = aliases.get(p, p)
        if p in ConversationManager.SUPPORTED_PROVIDERS:
            return p
        return ConversationManager.UNKNOWN_PROVIDER

    # ---------------------------
    # Session create
    # ---------------------------
    async def _terminal_print(self, role: str, message: str):
        """Helper to force print to terminal via multiple channels for visibility.
        CRITICAL: This function must NEVER raise an exception, as it's called during session creation.
        """
        try:
            # Use plain text tags instead of emojis for Windows compatibility
            tag = "USER" if role.upper() == "USER" else "BOT"
            output = f"\n[{tag}]: {message}\n"
            
            # Method 1: Try stdout
            try:
                sys.stdout.write(output)
                sys.stdout.flush()
            except Exception:
                # Silently fail - terminal logging is not critical
                pass
            
            # Method 2: Try stderr
            try:
                sys.stderr.write(output)
                sys.stderr.flush()
            except Exception:
                # Silently fail - terminal logging is not critical
                pass
            
            # Method 3: Logger (most reliable)
            try:
                logger.info(f"[{tag}]: {message[:200]}...")  # Truncate for logger
            except Exception:
                # Even logger can fail in extreme cases
                pass
                
        except Exception:
            # Catch-all: NEVER let this function crash the calling code
            pass

    async def create_session(
        self,
        owner: str = "",
        repo: str = "",
        github_token: str = "",
        github_branch: str = "",
    ) -> Dict[str, Any]:
        """
        Creates a session WITHOUT requiring provider.
        Provider is chosen inside chat and saved into collected_parameters.cloud_provider.
        """
        if self.sessions_collection is None:
            raise RuntimeError("MongoDB not available. Cannot create session.")

        sid = f"sess_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"

        if not owner.strip() or not repo.strip():
            bot_response = (
                "Hey there! 👋 I'm TerraBot — your friendly cloud deployment guide!\n"
                "I'll read your project's README and set up the perfect cloud infrastructure for you.\n"
                "No cloud expertise needed — I'll ask just 10-12 smart questions and handle the rest. 🚀\n"
                "To get started, I need your GitHub repo details.\n"
                "What's the owner and repo name? (e.g., 'facebook' and 'react')"
            )
            # 🟢 FORCE PRINT TO TERMINAL
            await self._terminal_print("BOT", bot_response)
            return {"session_id": sid, "bot_response": bot_response, "suggestions": []}

        # Fetch README (owner/repo). If your GithubService only supports repo_url, we fallback.
        readme_content = ""
        try:
            readme_content = await self.github_service.fetch_readme(
                owner=owner,
                repo=repo,
                token=github_token,
                branch=github_branch,
            )
        except TypeError:
            repo_url = f"https://github.com/{owner}/{repo}"
            readme_content = await self.github_service.fetch_readme(
                repo_url=repo_url,
                token=github_token,
                branch=github_branch,
            )
        except Exception as e:
            logger.error("[%s] README fetch failed for %s/%s: %s", sid, owner, repo, e, exc_info=True)
            readme_content = ""

        if not readme_content.strip():
            logger.warning("[%s] README is empty/missing for %s/%s", sid, owner, repo)
            bot_response = (
                f"Hmm 🤔 I tried fetching the README for **{owner}/{repo}** but came up empty.\n"
                "This could happen if the repo is private (I'd need a GitHub token with repo access).\n"
                "Or maybe the README is on a different branch?\n"
                "Don't worry — we can fix this easily!\n"
                "Would you like to retry with a token or specify a different branch?"
            )
            # 🟢 FORCE PRINT TO TERMINAL
            await self._terminal_print("BOT", bot_response)
            return {
                "session_id": sid,
                "bot_response": bot_response,
                "suggestions": ["Retry with token", "Change branch"],
            }

        logger.info("--------------------------------------------------")
        logger.info("[%s] FETCHED README (%d chars):\n%s", sid, len(readme_content), readme_content[:2000])
        if len(readme_content) > 2000:
            logger.info("... (truncated remaining %d chars) ...", len(readme_content) - 2000)
        logger.info("--------------------------------------------------")

        analysis = await self._analyze_readme(readme_content)
        extracted = analysis.get("extracted_params", {}) if isinstance(analysis, dict) else {}
        greeting = str(analysis.get("message") or "") if isinstance(analysis, dict) else ""
        
        logger.info("[%s] README ANALYSIS:\n%s", sid, json.dumps(extracted, indent=2))

        # Seed minimal cross-provider fields (NO cloud_provider here)
        extracted["github_owner"] = owner
        extracted["github_repo"] = repo
        if github_branch:
            extracted["github_branch"] = github_branch

        extracted["readme_context"] = self._build_readme_context(readme_content, extracted, owner, repo)

        # Force provider to remain unknown until user chooses
        extracted.setdefault("cloud_provider", self.UNKNOWN_PROVIDER)

        bot_response = self._normalize_bot_message(greeting, is_complete=False)
        
        # 🟢 FORCE PRINT TO TERMINAL
        await self._terminal_print("BOT", bot_response)

        session = ConversationSession(
            session_id=sid,
            provider=self.UNKNOWN_PROVIDER,
            messages=[],
            collected_parameters=extracted,
            is_complete=False,
            status=ConversationStatus.ACTIVE,
        )

        try:
            self.sessions_collection.insert_one(session.dict())
            logger.info("[%s] Session created and saved to MongoDB", sid)
        except Exception as e:
            logger.error("Failed to persist session %s: %s", sid, e)
            raise RuntimeError(f"Failed to save session to MongoDB: {e}")

        return {
            "session_id": sid,
            "bot_response": bot_response,
            "suggestions": ["AWS", "GCP", "Azure", "DigitalOcean"],
        }

    def get_session(self, sid: str) -> Optional[ConversationSession]:
        if self.sessions_collection is None:
            logger.error("MongoDB not available. Cannot get session.")
            return None

        try:
            data = self.sessions_collection.find_one({"session_id": sid})
            if data:
                if "_id" in data:
                    del data["_id"]
                return ConversationSession(**data)
        except Exception as e:
            logger.error("Failed to fetch session %s from MongoDB: %s", sid, e)
        
        return None

    # ---------------------------
    # Message handling
    # ---------------------------
    async def process_message(self, session_id: str, user_message: str) -> ChatMessageResponse:
        logger.info("[%s] User Message: %s", session_id, user_message)

        session = self.get_session(session_id)
        if not session:
            # If session not found, we can't process message.
            # Caller handles the 404 from get_session or here.
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != ConversationStatus.ACTIVE:
            raise ValueError(f"Session {session_id} not active")

        session.messages.append({"role": "user", "content": user_message})
        
        # 🟢 FORCE PRINT TO TERMINAL
        await self._terminal_print("USER", user_message)

        raw = await self._call_llm(session)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "message": (
                    "Oops! 😅 I had a small hiccup processing that.\n"
                    "No worries — your README context is still my guide.\n"
                    "Let me get back on track with our deployment planning.\n"
                    "Could you repeat your last answer in a short line?\n"
                    "I want to make sure I capture it correctly! 🎯"
                ),
                "extracted_params": {},
                "suggestions": [],
                "is_complete": False,
            }

        data.setdefault("message", "Could you tell me a bit more?")
        data.setdefault("extracted_params", {})
        data.setdefault("suggestions", [])
        data.setdefault("is_complete", False)

        if not isinstance(data["extracted_params"], dict):
            data["extracted_params"] = {}

        self._deep_merge(session.collected_parameters, data["extracted_params"])

        # ✅ keep 'unknown' until user explicitly chooses
        chosen = str(session.collected_parameters.get("cloud_provider") or session.provider or self.UNKNOWN_PROVIDER)
        provider_norm = self._normalize_provider(chosen)

        session.provider = provider_norm
        # only stamp cloud_provider when it's actually supported
        if provider_norm in self.SUPPORTED_PROVIDERS:
            session.collected_parameters["cloud_provider"] = provider_norm
        else:
            session.collected_parameters["cloud_provider"] = self.UNKNOWN_PROVIDER

        session.is_complete = bool(data["is_complete"])
        session.updated_at = datetime.now()

        if session.is_complete:
            # Hard safety: completion cannot happen without provider choice.
            if session.provider not in self.SUPPORTED_PROVIDERS:
                session.is_complete = False
                data["is_complete"] = False
                data["message"] = self._normalize_bot_message(
                    "Hold on! ☁️ Before I can generate your Terraform, I need to know which cloud platform you'd like.\n"
                    "This is crucial because each provider has different resources and pricing.\n"
                    "Based on your project, any of these would work great!\n"
                    "I just need you to pick your favorite.\n"
                    "Which cloud platform would you like: AWS, GCP, Azure, or DigitalOcean? 🎯",
                    is_complete=False,
                )
                data["suggestions"] = ["AWS", "GCP", "Azure", "DigitalOcean"]
            else:
                self._apply_defaults(session.collected_parameters, provider=session.provider)
                session.status = ConversationStatus.COMPLETE

                cost_block = self._calculate_cost(session.collected_parameters, provider=session.provider)
                final_msg = f"{cost_block}\nAll set! I'll generate your Terraform configuration now."
                data["message"] = self._normalize_bot_message(final_msg, is_complete=True)
        else:
            data["message"] = self._normalize_bot_message(data["message"], is_complete=False)

        session.messages.append({"role": "assistant", "content": data["message"]})
        
        # 🟢 FORCE PRINT TO TERMINAL
        await self._terminal_print("BOT", data["message"])

        logger.info("[%s] Bot Response:\n%s", session_id, data["message"])
        logger.info("[%s] Collected Params: %s", session_id, json.dumps(session.collected_parameters, indent=2))

        if self.sessions_collection is not None:
            try:
                self.sessions_collection.update_one(
                    {"session_id": session_id},
                    {"$set": session.dict(exclude={"_id"})},
                    upsert=True
                )
            except Exception as e:
                logger.error("Failed to update session %s: %s", session_id, e)

        return ChatMessageResponse(
            session_id=session_id,
            bot_response=data["message"],
            collected_parameters=session.collected_parameters,
            is_complete=session.is_complete,
            suggestions=data.get("suggestions", []),
            next_question=data.get("next_question"),
        )

    # ---------------------------
    # REQUIRED METHODS for main.py
    # ---------------------------
    def get_collected_parameters(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if not session:
            return {}
        return dict(session.collected_parameters or {})

    def add_run_to_session(self, session_id: str, run_id: str) -> None:
        session = self.get_session(session_id)
        if not session:
            return
        params = session.collected_parameters or {}
        runs = params.get("run_ids")
        if not isinstance(runs, list):
            runs = []
        if run_id and run_id not in runs:
            runs.append(run_id)
        params["run_ids"] = runs
        session.collected_parameters = params
        session.updated_at = datetime.now()

        if self.sessions_collection is not None:
            try:
                self.sessions_collection.update_one(
                    {"session_id": session_id},
                    {"$set": {"collected_parameters": session.collected_parameters, "updated_at": session.updated_at}},
                )
            except Exception as e:
                logger.error("Failed to link run to session %s: %s", session_id, e)

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 20), 100))

        if self.sessions_collection is None:
            logger.error("MongoDB not available. Cannot list sessions.")
            return []

        try:
            docs = list(
                self.sessions_collection.find(
                    {},
                    {
                        "_id": 0,
                        "session_id": 1,
                        "provider": 1,
                        "status": 1,
                        "is_complete": 1,
                        "updated_at": 1,
                        "created_at": 1,
                        "collected_parameters.github_owner": 1,
                        "collected_parameters.github_repo": 1,
                    }
                ).sort("updated_at", -1).limit(limit)
            )
            out = []
            for d in docs:
                cp = (d.get("collected_parameters") or {})
                out.append({
                    "session_id": d.get("session_id"),
                    "provider": d.get("provider") or self.UNKNOWN_PROVIDER,
                    "status": d.get("status"),
                    "is_complete": d.get("is_complete", False),
                    "updated_at": str(d.get("updated_at") or ""),
                    "repo": f"{cp.get('github_owner','')}/{cp.get('github_repo','')}".strip("/"),
                })
            return out
        except Exception as e:
            logger.error("Mongo list_sessions failed: %s", e)
            return []

    def delete_session(self, session_id: str) -> bool:
        if self.sessions_collection is None:
            return False

        try:
            res = self.sessions_collection.delete_one({"session_id": session_id})
            return bool(res.deleted_count)
        except Exception as e:
            logger.error("Failed to delete session %s from mongo: %s", session_id, e)
            return False

    def build_terraform_request(self, session_id: str) -> Dict[str, Any]:
        """
        Returns structured params dict for LLMGenerator.generate_terraform(params, provider).

        IMPORTANT:
        - Provider MUST be chosen in chat before this is called.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        p = dict(session.collected_parameters or {})
        provider = self._normalize_provider(str(p.get("cloud_provider") or session.provider or self.UNKNOWN_PROVIDER))

        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Cloud provider not chosen yet. Please pick one of: {sorted(self.SUPPORTED_PROVIDERS)}"
            )

        p["cloud_provider"] = provider

        # Ensure defaults applied even if caller triggers generation immediately
        self._apply_defaults(p, provider=provider)

        params: Dict[str, Any] = {
            "cloud_provider": provider,
            "environment": p.get("environment", "dev"),
            "workload_description": p.get("workload_description") or p.get("service_type") or "web server",
            "language": p.get("language", "Not specified"),
            "dependencies": p.get("dependencies", []),
            "ports": p.get("ports", []),
            "ssh_allowed_cidrs": p.get("ssh_allowed_cidrs", []),
            "instance_type": p.get("instance_type"),
            "instance_count": p.get("instance_count", 1),
            "storage_size_gb": p.get("storage_size_gb", 20),
            "storage_type": p.get("storage_type"),
            "vpc_cidr": p.get("vpc_cidr", "10.0.0.0/16"),
            "subnet_count": p.get("subnet_count", 2),
            "enable_public_ip": p.get("enable_public_ip", True),
            "os_image": p.get("os_image") or p.get("ami_os") or "ubuntu-22.04",
            "project_name": p.get("project_name") or p.get("github_repo") or "app",
            "readme_context": p.get("readme_context", ""),
            # Enhanced fields for intelligent Terraform generation
            "github_owner": p.get("github_owner", ""),
            "github_repo": p.get("github_repo", ""),
            "has_docker": p.get("has_docker", False),
            "database_type": p.get("database_type", "none"),
            "has_database": p.get("has_database", False),
        }

        if provider == "aws":
            params["aws_region"] = p.get("aws_region") or p.get("region") or "us-east-1"
            params["region"] = params["aws_region"]
            params["iam_services"] = p.get("iam_services", {})
            params["load_balancer_type"] = p.get("load_balancer_type", "none")
            params["enable_https"] = p.get("enable_https", False)

        elif provider == "gcp":
            params["gcp_project_id"] = p.get("gcp_project_id") or ""
            params["gcp_region"] = p.get("gcp_region") or p.get("region") or "us-central1"
            params["region"] = params["gcp_region"]
            params["ssh_username"] = p.get("ssh_username") or "ubuntu"
            if params["os_image"] in ("ubuntu-22.04", "ubuntu-2204", "ubuntu"):
                params["os_image"] = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"

        elif provider == "azure":
            params["azure_location"] = p.get("azure_location") or p.get("region") or "eastus"
            params["region"] = params["azure_location"]
            params["ssh_username"] = p.get("ssh_username") or "azureuser"

        else:  # digitalocean
            params["do_region"] = p.get("do_region") or p.get("region") or "nyc1"
            params["region"] = params["do_region"]
            if params["os_image"] in ("ubuntu-22.04", "ubuntu-2204", "ubuntu"):
                params["os_image"] = "ubuntu-22-04-x64"

        # Never allow empty/non-list SSH CIDRs; keep empty so LLM asks (DO NOT fill 0.0.0.0/0).
        if not isinstance(params.get("ssh_allowed_cidrs"), list):
            params["ssh_allowed_cidrs"] = []
        params["ssh_allowed_cidrs"] = [c for c in params["ssh_allowed_cidrs"] if isinstance(c, str) and c.strip()]

        return params

    # ---------------------------
    # Service-Specific Turn Guidance
    # ---------------------------
    def _build_service_specific_guidance(
        self,
        session: ConversationSession,
        provider: str,
        environment: str
    ) -> str:
        """
        Build service-specific turn guidance based on detected services.
        
        Args:
            session: Current conversation session
            provider: Cloud provider (aws, gcp, azure, digitalocean)
            environment: Environment type (dev, prod)
            
        Returns:
            String with service-specific guidance for the LLM
        """
        detected_services = session.collected_parameters.get("detected_services", {})
        provider_services = detected_services.get(provider, [])
        
        if not provider_services:
            return ""
        
        guidance_parts = ["\n\n🔍 **DETECTED SERVICES** (ask about these based on README):\n"]
        
        # Database services
        if any(s in provider_services for s in ["rds", "cloud_sql", "dynamodb", "firestore"]):
            db_service = "rds" if provider == "aws" else "cloud_sql" if provider == "gcp" else "database"
            if not session.collected_parameters.get("database_instance_type"):
                guidance_parts.append(
                    f"- **Database ({db_service})**: Ask about instance type, storage size, "
                    f"{'Multi-AZ' if provider == 'aws' else 'high availability'}, backup retention\n"
                )
        
        # Storage services
        if any(s in provider_services for s in ["s3", "cloud_storage"]):
            storage_service = "S3" if provider == "aws" else "Cloud Storage"
            if not session.collected_parameters.get("storage_config"):
                guidance_parts.append(
                    f"- **Object Storage ({storage_service})**: Ask about versioning, "
                    f"lifecycle policies, encryption (default: enabled)\n"
                )
        
        # Serverless compute
        if any(s in provider_services for s in ["lambda", "cloud_functions"]):
            func_service = "Lambda" if provider == "aws" else "Cloud Functions"
            if not session.collected_parameters.get("function_config"):
                guidance_parts.append(
                    f"- **Serverless ({func_service})**: Ask about runtime, memory, timeout, "
                    f"trigger type (HTTP, event, schedule)\n"
                )
        
        # Container orchestration
        if any(s in provider_services for s in ["ecs", "eks", "gke"]):
            container_service = "ECS/EKS" if provider == "aws" else "GKE"
            if not session.collected_parameters.get("container_config"):
                guidance_parts.append(
                    f"- **Containers ({container_service})**: Ask about cluster size, "
                    f"node type, auto-scaling, container registry\n"
                )
        
        # Load balancing
        if any(s in provider_services for s in ["elb", "cloud_load_balancing"]):
            lb_service = "ELB (ALB/NLB)" if provider == "aws" else "Cloud Load Balancing"
            if environment == "production" and not session.collected_parameters.get("load_balancer_type"):
                guidance_parts.append(
                    f"- **Load Balancer ({lb_service})**: For production, ask about LB type "
                    f"(HTTP/HTTPS vs TCP), SSL certificate, health checks\n"
                )
        
        # CDN
        if any(s in provider_services for s in ["cloudfront", "cloud_cdn"]):
            cdn_service = "CloudFront" if provider == "aws" else "Cloud CDN"
            if not session.collected_parameters.get("cdn_enabled"):
                guidance_parts.append(
                    f"- **CDN ({cdn_service})**: Ask if they want global content delivery, "
                    f"cache settings, SSL/TLS\n"
                )
        
        # Monitoring
        if any(s in provider_services for s in ["cloudwatch", "cloud_monitoring"]):
            monitor_service = "CloudWatch" if provider == "aws" else "Cloud Monitoring"
            if not session.collected_parameters.get("monitoring_config"):
                guidance_parts.append(
                    f"- **Monitoring ({monitor_service})**: Ask about log retention, "
                    f"custom metrics, alerting (SNS/email)\n"
                )
        
        # Messaging/Queues
        if any(s in provider_services for s in ["sqs", "sns", "pubsub"]):
            msg_service = "SQS/SNS" if provider == "aws" else "Pub/Sub"
            if not session.collected_parameters.get("messaging_config"):
                guidance_parts.append(
                    f"- **Messaging ({msg_service})**: Ask about queue type, "
                    f"message retention, dead-letter queue\n"
                )
        
        # DNS
        if any(s in provider_services for s in ["route53", "cloud_dns"]):
            dns_service = "Route 53" if provider == "aws" else "Cloud DNS"
            if not session.collected_parameters.get("dns_config"):
                guidance_parts.append(
                    f"- **DNS ({dns_service})**: Ask about domain name, "
                    f"routing policy (simple, weighted, geolocation)\n"
                )
        
        if len(guidance_parts) > 1:  # More than just the header
            guidance_parts.append(
                "\n**IMPORTANT**: Ask about ONE service at a time. "
                "Reference the README to show you understand their needs.\n"
            )
            return "".join(guidance_parts)
        
        return ""

    # ---------------------------
    # LLM call
    # ---------------------------
    async def _call_llm(self, session: ConversationSession) -> str:
        snapshot = json.dumps(session.collected_parameters, indent=2)
        readme_ctx = str(session.collected_parameters.get("readme_context") or "")[:3500]

        # Count user turns (questions asked so far)
        user_turns = sum(1 for m in session.messages if m.get("role") == "user")
        
        # Detect environment early
        environment = str(session.collected_parameters.get("environment") or "").lower()
        is_dev = environment in ("dev", "development")
        is_prod = environment in ("prod", "production")
        
        # Environment-specific question targets
        if is_dev:
            total_questions_target = 6  # Dev: 4-6 questions
            min_questions = 4
        elif is_prod:
            total_questions_target = 12  # Prod: 10-12 questions
            min_questions = 10
        else:
            # Environment not yet chosen
            total_questions_target = 12
            min_questions = 10

        turn_guidance = ""
        
        # Check if cloud provider has been chosen
        cloud_provider = str(session.collected_parameters.get("cloud_provider") or "").lower()
        has_cloud_provider = cloud_provider in ("aws", "gcp", "azure", "digitalocean")
        
        if not has_cloud_provider:
            # Very first turn - should ask about cloud provider
            turn_guidance = (
                "\n📊 This is the FIRST question of the conversation.\n"
                "**CRITICAL**: Ask which cloud platform they want to use (AWS, GCP, Azure, or DigitalOcean).\n"
                "Do NOT ask about environment yet - that comes AFTER cloud provider.\n"
            )
        elif has_cloud_provider and not is_dev and not is_prod:
            # Cloud provider chosen but environment NOT chosen - MUST ask about environment
            turn_guidance = (
                "\n📊 Cloud provider has been selected. This is question 2.\n"
                "**CRITICAL**: You MUST NOW ask about environment (dev vs prod).\n"
                "This is MANDATORY and determines the entire question flow:\n"
                "- DEV: Simple, cost-focused, 4-6 questions total (skip traffic, HA, detailed monitoring)\n"
                "- PROD: Detailed, reliability-focused, 10-12 questions total (cover ALL topics)\n\n"
                "Ask: 'Are you deploying to **development** (cost-focused) or **production** (reliability-focused)?'\n"
                "Provide suggestions: ['Development', 'Production'] or ['DEV', 'PROD']\n"
                "Do NOT skip this question. Do NOT ask about region yet.\n"
            )
        elif is_dev:
            if user_turns < min_questions:
                turn_guidance = (
                    f"\n📊 DEV Environment - Question {user_turns + 1} of 4-6.\n"
                    "**CRITICAL**: Keep it SIMPLE. Focus on:\n"
                    "- Region (choose closest/cheapest)\n"
                    "- Instance type (free tier vs paid)\n"
                    "- Basic storage (only if README shows database)\n"
                    "- Basic IAM (CloudWatch logging only)\n"
                    "**SKIP**: Traffic estimation, HA, load balancers, detailed monitoring, backups.\n"
                )
            else:
                turn_guidance = (
                    f"\n⚠️ DEV Environment - Question {user_turns + 1}.\n"
                    "You have asked enough questions for a dev environment.\n"
                    "Wrap up: Summarize collected parameters and set `is_complete: true`.\n"
                )
        elif is_prod:
            # Check what questions have been answered
            region = session.collected_parameters.get("region")
            traffic_info = session.collected_parameters.get("expected_traffic") or session.collected_parameters.get("dau")
            
            if user_turns < min_questions:
                if not region:
                    # First question after environment: Region
                    turn_guidance = (
                        f"\n📊 PROD Environment - Question {user_turns + 1} (Region).\n"
                        f"**CRITICAL**: Ask about region first.\n"
                        f"Cloud Provider: {cloud_provider.upper()}\n"
                        f"Use CORRECT terminology: AWS regions (us-east-1, ap-south-1), GCP regions (us-central1, asia-south1), "
                        f"Azure regions (eastus, centralindia), DigitalOcean regions (nyc1, blr1).\n"
                    )
                elif not traffic_info:
                    # Second question after environment: Traffic/User Base
                    turn_guidance = (
                        f"\n📊 PROD Environment - Question {user_turns + 1} (Traffic Estimation) - MANDATORY.\n"
                        "**CRITICAL**: You MUST NOW ask about traffic/user base estimation.\n"
                        "This is the MOST IMPORTANT production question and determines instance sizing and auto-scaling.\n\n"
                        "Ask about:\n"
                        "- Daily Active Users (DAU)\n"
                        "- OR Requests per second\n"
                        "- OR Concurrent users\n\n"
                        "Explain WHY: 'For production sizing, I need to understand your expected load. This determines instance type, count, and whether we need auto-scaling.'\n"
                        "Reference README: 'I see your README shows [tech stack]...'\n"
                        "DO NOT skip this question. DO NOT ask about storage/database yet.\n"
                    )
                else:
                    # Remaining production questions
                    turn_guidance = (
                        f"\n📊 PROD Environment - Question {user_turns + 1} of 10-12.\n"
                        f"Cloud Provider: {cloud_provider.upper()} - Use CORRECT terminology.\n"
                        "**CRITICAL**: You MUST cover ALL production topics:\n"
                        "- High availability (Multi-AZ, load balancers)\n"
                        "- Storage specifics (based on detected database from README)\n"
                        "- Detailed IAM (based on detected services from README)\n"
                        "- Monitoring & alerting\n"
                        "- Backup strategy (if database detected)\n"
                        "- Security (SSH CIDR restrictions)\n\n"
                        "**Use provider-specific terminology**:\n"
                        f"- AWS: EC2, RDS, ElastiCache, CloudWatch, IAM Roles\n"
                        f"- GCP: Compute Engine, Cloud SQL, Memorystore, Cloud Monitoring, Service Accounts\n"
                        f"- Azure: Virtual Machines, Azure Database, Azure Cache, Azure Monitor, Managed Identities\n"
                        f"- DigitalOcean: Droplets, Managed Databases, Spaces\n"
                        "DO NOT skip any of these topics. Set `is_complete: false`.\n"
                    )
            elif user_turns >= total_questions_target:
                turn_guidance = (
                    f"\n⚠️ PROD Environment - Question {user_turns + 1}.\n"
                    "This is the LAST question turn. You MUST set `is_complete: true` after this response.\n"
                    "Summarize all collected parameters and confirm the deployment plan.\n"
                    "Do NOT ask more questions — wrap up with a friendly deployment summary.\n"
                )
            else:
                turn_guidance = (
                    f"\n💡 PROD Environment - Question {user_turns + 1}.\n"
                    "You can wrap up if you have covered ALL critical topics, otherwise ask 1-2 more questions.\n"
                    "Ensure you've asked about: traffic, HA, storage (based on README DB), IAM (based on README services), monitoring, backups.\n"
                )
        
        # Add service-specific guidance based on detected services
        service_guidance = self._build_service_specific_guidance(
            session,
            provider=cloud_provider,
            environment=environment
        )
        if service_guidance:
            turn_guidance += service_guidance

        context = (
            "\n\n[README Context (authoritative — use this to make intelligent suggestions)]:\n"
            f"{readme_ctx}\n\n"
            f"[Parameters collected so far: {snapshot}]\n"
            f"[Provider: {str(session.provider).upper()}] [Environment: {environment or 'NOT SET'}] [User turns so far: {user_turns}]"
            f"{turn_guidance}\n\n"
            "**REMINDER**: Every question MUST reference specific findings from the README context above.\n"
            "Example: 'I see your README shows MongoDB and Redis...'\n"
        )

        messages = [{
            "role": "system",
            "content": self.SYSTEM_PROMPT + "\n\n" + self.FRIENDLY_BRIDGE_PROMPT + context
        }]

        for msg in session.messages:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        body = await self.llm_service.chat_completion(
            messages=messages,
            temperature=0.5,  # Increased to 0.5 for highly descriptive, educational responses
            max_tokens=1800,  # Sufficient for 8-10 line explanations
            response_format={"type": "json_object"},
            timeout=30,
        )

        # IMPORTANT: body is already JSON (we enforced it in LLMService)
        logger.debug("LLM JSON body (first 500): %s", str(body)[:500])

        # Validate once and return normalized JSON string
        data = json.loads(body)
        return json.dumps(data)

    # ---------------------------
    # README analysis
    # ---------------------------
    async def _analyze_readme(self, readme_content: str) -> Dict[str, Any]:
        prompt = (
            "You are **TerraBot** 🤖 — an expert, intelligent, and friendly Cloud Deployment Guide.\n"
            "You just received a GitHub README. Analyze it deeply and return ONLY valid JSON.\n\n"
            "### JSON STRUCTURE REQUIRED:\n"
            "```json\n"
            "{\n"
            "  \"extracted_params\": {\n"
            "    \"workload_type\": \"...\",\n"
            "    \"language\": \"...\",\n"
            "    \"database_type\": \"...\",\n"
            "    \"detected_services\": {\n"
            "      \"aws\": [\"ec2\", \"s3\", \"rds\"],\n"
            "      \"gcp\": [\"compute_engine\", \"cloud_storage\", \"cloud_sql\"]\n"
            "    },\n"
            "    ... (all other fields)\n"
            "  },\n"
            "  \"message\": \"... (12-15 line detailed greeting) ...\",\n"
            "  \"suggestions\": [\"AWS\", \"GCP\", \"Azure\", \"DigitalOcean\"]\n"
            "}\n"
            "```\n\n"
            "### SERVICES TO DETECT:\n\n"
            "**AWS Services (15)**:\n"
            "- EC2 (Elastic Compute Cloud) - servers, instances, VMs\n"
            "- S3 (Simple Storage Service) - object storage, file uploads, static assets\n"
            "- RDS (Relational Database Service) - PostgreSQL, MySQL, MariaDB\n"
            "- Lambda - serverless functions, event-driven\n"
            "- VPC (Virtual Private Cloud) - networking, subnets\n"
            "- IAM (Identity & Access Management) - permissions, roles\n"
            "- CloudFront - CDN, content delivery\n"
            "- EBS (Elastic Block Store) - volumes, persistent disks\n"
            "- CloudWatch - monitoring, logs, metrics\n"
            "- ELB (Elastic Load Balancing) - load balancers, ALB, NLB\n"
            "- DynamoDB - NoSQL, key-value database\n"
            "- ECS/EKS - containers, Docker, Kubernetes\n"
            "- SNS/SQS - messaging, notifications, queues\n"
            "- Route 53 - DNS, domain management\n"
            "- CloudFormation - infrastructure as code\n\n"
            "**GCP Services (15)**:\n"
            "- Compute Engine - servers, instances, VMs\n"
            "- Cloud Storage - object storage, file uploads\n"
            "- Cloud SQL - PostgreSQL, MySQL managed databases\n"
            "- Cloud Functions - serverless functions\n"
            "- VPC (Virtual Private Cloud) - networking\n"
            "- IAM (Identity & Access Management) - permissions\n"
            "- Cloud CDN - content delivery\n"
            "- Persistent Disk - block storage, volumes\n"
            "- Cloud Monitoring (Stackdriver) - logs, metrics\n"
            "- Cloud Load Balancing - load balancers\n"
            "- Cloud Firestore/Bigtable - NoSQL databases\n"
            "- GKE (Google Kubernetes Engine) - Kubernetes\n"
            "- Pub/Sub - messaging, event streaming\n"
            "- Cloud DNS - domain management\n"
            "- Deployment Manager - infrastructure as code\n\n"
            "### EXTRACT THESE FIELDS (in extracted_params):\n"
            "- **workload_type**: web_server|api|app_server|database|batch|microservice|fullstack|custom\n"
            "- **workload_description**: 2-3 sentences describing what this project does and what it needs to run\n"
            "- **language**: primary language/framework (e.g., 'Node.js with Express', 'Python Flask', 'React + Django')\n"
            "- **ports**: array of {port, protocol, description} — infer from README (e.g., Express default 3000, Flask 5000, React 3000)\n"
            "- **dependencies**: list of services/tools mentioned (databases, caches, queues, etc.)\n"
            "- **has_database**: boolean — does the project use any database?\n"
            "- **database_type**: string — which database (MongoDB, PostgreSQL, MySQL, Redis, etc.) or 'none'\n"
            "- **has_docker**: boolean — does the README mention Docker/docker-compose?\n"
            "- **storage_needs**: boolean — does the app need persistent storage (file uploads, user data, logs)?\n"
            "- **storage_description**: string — brief description of storage needs (e.g., 'User uploaded images', 'Application logs')\n"
            "- **caching_service**: string — which caching service if any (Redis, Memcached, none)\n"
            "- **background_jobs**: boolean — does the app use background job processing (Celery, Bull, Sidekiq, queues)?\n"
            "- **scale_indicators**: string — any mentions of scale expectations ('millions of users', 'high traffic', 'enterprise', etc.) or 'none'\n"
            "- **suggested_provider**: string — which cloud platform would be BEST for this project and why (aws|gcp|azure|digitalocean)\n"
            "- **suggested_instance**: string — what instance size would work best for dev deployment\n"
            "- **project_name**: string — inferred project name\n"
            "- **detected_services**: object with 'aws' and 'gcp' arrays listing detected services from the lists above\n\n"
            "### GREETING (the 'message' field) - ABSOLUTELY CRITICAL:\n\n"
            "**YOU MUST WRITE A DETAILED 12-15 LINE GREETING. THIS IS MANDATORY.**\n\n"
            "**EXACT STRUCTURE TO FOLLOW:**\n\n"
            "Line 1: Welcome! I'm excited to help you deploy [project name]!\n\n"
            "Line 2: I've analyzed your README and here's what I found:\n\n"
            "Lines 3-10: **DETAILED TECHNOLOGY BREAKDOWN** (one bullet per line):\n"
            "• **[Language] [version]** with **[Framework] [version]** for [purpose]\n"
            "• **[Database]** for [purpose] with [ORM/details if any]\n"
            "• **[Caching service]** for [purpose] (if detected)\n"
            "• **[Frontend tech]** for [purpose] (if detected)\n"
            "• **[Background jobs tech]** for [purpose] (if detected)\n"
            "• **Docker** and **docker-compose** for containerization (if detected)\n"
            "• Exposing **port [X]** for [service] and **port [Y]** for [service]\n\n"
            "Lines 11-12: For this stack, you'll need: [list compute, database, storage, load balancer needs with SPECIFIC SERVICE NAMES]\n\n"
            "Lines 13-14: I recommend **[Cloud Platform]** because: [specific reasons tied to detected tech]\n\n"
            "Line 15: **FIRST QUESTION**: Which cloud platform would you like to deploy on: AWS, GCP, Azure, or DigitalOcean?\n\n"
            "**EXAMPLES OF GOOD GREETINGS:**\n\n"
            "Example 1 (Node.js + MongoDB):\n"
            "```\n"
            "Welcome! I'm excited to help you deploy your Express.js API!\n\n"
            "I've analyzed your README and here's what I found:\n"
            "• **Node.js v18** with **Express.js 4.x** for the backend REST API\n"
            "• **MongoDB 5.0** for document storage with **Mongoose ODM** for data modeling\n"
            "• **Redis 7.x** for session management and caching layer\n"
            "• **JWT** for authentication and authorization\n"
            "• **Docker** and **docker-compose** for containerization\n"
            "• Exposing **port 3000** for the Express API and **port 27017** for MongoDB\n\n"
            "For this stack, you'll need **EC2/Compute Engine** for Node.js, **RDS/Cloud SQL** or **DynamoDB/Firestore** for MongoDB, **ElastiCache/Cloud Memorystore** for Redis, and **S3/Cloud Storage** for file uploads. For production, we'll also need **ELB/Cloud Load Balancing** for high availability.\n\n"
            "I recommend **AWS** because it offers seamless MongoDB Atlas integration, managed ElastiCache for Redis, excellent Node.js support with Elastic Beanstalk or EC2, and Docker container support with ECS.\n\n"
            "Which cloud platform would you like to deploy on: AWS, GCP, Azure, or DigitalOcean?\n"
            "```\n\n"
            "Example 2 (Python + PostgreSQL):\n"
            "```\n"
            "Welcome! I'm excited to help you deploy your Django application!\n\n"
            "I've analyzed your README and here's what I found:\n"
            "• **Python 3.11** with **Django 4.2** for the web framework\n"
            "• **PostgreSQL 15** for relational database with **Django ORM**\n"
            "• **Celery** with **Redis** for background task processing\n"
            "• **Gunicorn** as the WSGI server for production\n"
            "• **Nginx** for reverse proxy and static file serving\n"
            "• Exposing **port 8000** for Django and **port 5432** for PostgreSQL\n\n"
            "For this stack, you'll need **EC2/Compute Engine** for Django/Celery workers, **RDS/Cloud SQL** for PostgreSQL, **ElastiCache/Cloud Memorystore** for Redis, and **ELB/Cloud Load Balancing** for production traffic distribution.\n\n"
            "I recommend **AWS** because it offers managed RDS PostgreSQL with automated backups, ElastiCache for Redis, excellent Python support, and Application Load Balancer for traffic distribution.\n\n"
            "Which cloud platform would you like to deploy on: AWS, GCP, Azure, or DigitalOcean?\n"
            "```\n\n"
            "**CRITICAL RULES:**\n"
            "1. Use **bold markdown** for ALL technology names, versions, and key terms\n"
            "2. Mention SPECIFIC versions when available (Node.js v18, Python 3.11, etc.)\n"
            "3. List EVERY detected technology as a separate bullet point\n"
            "4. Explicitly mention ALL exposed ports\n"
            "5. The greeting MUST be 12-15 lines minimum\n"
            "6. Make it feel like you deeply understand their project\n"
            "7. When listing cloud services needed, use SPECIFIC SERVICE NAMES (EC2, RDS, S3, not just 'compute' or 'storage')\n\n"
            "### SUGGESTIONS (must be exactly this):\n"
            "[\"AWS\", \"GCP\", \"Azure\", \"DigitalOcean\"]\n\n"
            f"README:\n{readme_content[:15000]}"
        )
        raw = await self.llm_service.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,  # Increased from 0.2 to match conversation temperature
            response_format={"type": "json_object"},
            timeout=30,
        )
        analysis = json.loads(raw)
        
        # Use ServiceDetector to enhance detection
        from app.services.service_detector import ServiceDetector
        detector = ServiceDetector()
        
        # Detect services for both AWS and GCP
        aws_detected = detector.detect_services(readme_content, provider="aws")
        gcp_detected = detector.detect_services(readme_content, provider="gcp")
        
        # Prioritize services
        aws_services = detector.prioritize_services(aws_detected)
        gcp_services = detector.prioritize_services(gcp_detected)
        
        # Merge AI detection with pattern-based detection
        if "extracted_params" not in analysis:
            analysis["extracted_params"] = {}
        
        analysis["extracted_params"]["detected_services"] = {
            "aws": aws_services[:10],  # Top 10 most relevant
            "gcp": gcp_services[:10]
        }
        
        # Add service categories for better organization
        analysis["extracted_params"]["service_categories"] = {
            "aws": detector.get_service_categories(aws_services[:10], provider="aws"),
            "gcp": detector.get_service_categories(gcp_services[:10], provider="gcp")
        }
        
        logger.info(f"Detected AWS services: {aws_services[:10]}")
        logger.info(f"Detected GCP services: {gcp_services[:10]}")
        
        return analysis

    def _build_readme_context(self, readme: str, extracted: Dict[str, Any], owner: str, repo: str) -> str:
        workload = str(extracted.get("workload_description") or "").strip()
        language = str(extracted.get("language") or "").strip()
        project_name = str(extracted.get("project_name") or repo or "").strip()

        deps = extracted.get("dependencies") or []
        if not isinstance(deps, list):
            deps = [str(deps)]
        deps_str = ", ".join(str(x) for x in deps if x)[:500]

        ports = extracted.get("ports") or []
        ports_str = ""
        if isinstance(ports, list) and ports:
            parts = []
            for p in ports[:8]:
                if isinstance(p, dict):
                    parts.append(f"{p.get('port')}/{p.get('protocol','tcp')}")
                else:
                    parts.append(str(p))
            ports_str = ", ".join(parts)

        # Enhanced context fields
        has_database = extracted.get("has_database", False)
        database_type = str(extracted.get("database_type") or "none").strip()
        has_docker = extracted.get("has_docker", False)
        suggested_provider = str(extracted.get("suggested_provider") or "").strip()
        suggested_instance = str(extracted.get("suggested_instance") or "").strip()
        
        # New deployment-specific fields
        storage_needs = extracted.get("storage_needs", False)
        storage_description = str(extracted.get("storage_description") or "").strip()
        caching_service = str(extracted.get("caching_service") or "none").strip()
        background_jobs = extracted.get("background_jobs", False)
        scale_indicators = str(extracted.get("scale_indicators") or "none").strip()

        excerpt_lines = [ln.strip() for ln in readme.strip().splitlines() if ln.strip()][:40]
        excerpt = "\n".join(excerpt_lines)[:2000]

        return (
            f"Project: {project_name} ({owner}/{repo})\n"
            f"Workload: {workload or 'Not inferred'}\n"
            f"Language/Framework: {language or 'Not specified'}\n"
            f"Dependencies: {deps_str or 'Not listed'}\n"
            f"Ports: {ports_str or 'Not listed'}\n"
            f"Database: {'Yes — ' + database_type if has_database else 'No database detected'}\n"
            f"Docker: {'Yes — Docker/docker-compose detected' if has_docker else 'No Docker detected'}\n"
            f"Storage Needs: {'Yes — ' + storage_description if storage_needs else 'No persistent storage detected'}\n"
            f"Caching: {caching_service if caching_service != 'none' else 'No caching service detected'}\n"
            f"Background Jobs: {'Yes — background job processing detected' if background_jobs else 'No background jobs detected'}\n"
            f"Scale Indicators: {scale_indicators}\n"
            f"Suggested Cloud: {suggested_provider or 'Not determined'}\n"
            f"Suggested Instance: {suggested_instance or 'Not determined'}\n"
            f"README Excerpt:\n{excerpt}"
        )

    # ---------------------------
    # Helpers
    # ---------------------------
    @staticmethod
    def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        for k, v in overlay.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConversationManager._deep_merge(base[k], v)
            else:
                base[k] = v

    @staticmethod
    def _apply_defaults(params: Dict[str, Any], provider: str = "aws") -> None:
        provider = (provider or "aws").lower()

        is_prod = params.get("environment") in ("prod", "production")
        instance_count = int(params.get("instance_count", 1) or 1)
        multi = instance_count > 1

        base_defaults: Dict[str, Any] = {
            "vpc_cidr": "10.0.0.0/16",
            "subnet_type": "public",
            "subnet_count": 2,
            "enable_public_ip": True,
            "storage_size_gb": 20,
            "monitoring_enabled": True,
            "detailed_monitoring": bool(is_prod),
            "auto_scaling_enabled": False,
            "backup_enabled": False,
            "enable_imdsv2": True,
            "ssh_username": params.get("ssh_username") or "ubuntu",
        }

        if provider == "aws":
            base_defaults.update({
                "storage_type": "gp3",
                "load_balancer_type": ("application" if is_prod and multi else "none"),
                "enable_https": bool(is_prod and multi),
            })
        elif provider == "gcp":
            base_defaults.update({
                "storage_type": "pd-balanced",
                "enable_https": bool(is_prod and multi),
            })
            params.setdefault("gcp_region", params.get("region", "us-central1"))
        elif provider == "azure":
            base_defaults.update({
                "storage_type": "StandardSSD_LRS",
                "enable_https": bool(is_prod and multi),
            })
            params.setdefault("azure_location", params.get("region", "eastus"))
        elif provider == "digitalocean":
            base_defaults.update({
                "enable_https": bool(is_prod and multi),
                "load_balancer_type": ("application" if is_prod and multi else "none"),
            })
            params.setdefault("do_region", params.get("region", "nyc1"))

        for key, val in base_defaults.items():
            params.setdefault(key, val)

        if provider == "aws":
            iam = params.setdefault("iam_services", {})
            iam.setdefault(
                "cloudwatch",
                [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "cloudwatch:PutMetricData",
                ],
            )
            iam.setdefault("ssm", ["ssm:UpdateInstanceInformation", "ssm:GetParameter", "ssm:GetParameters"])

    def _calculate_cost(self, params: dict, provider: str = "aws") -> str:
        provider = (provider or "aws").lower()

        instance_count = int(params.get("instance_count", 1) or 1)
        instance_type = str(params.get("instance_type", "") or "")
        storage_size = float(params.get("storage_size_gb", 20) or 20)
        storage_type = str(params.get("storage_type", "") or "")
        lb_type = str(params.get("load_balancer_type", "none") or "none")

        if provider == "aws":
            monthly_instance = {"t3.micro": 7.59, "t3.small": 15.18, "t3.medium": 30.37}.get(instance_type, 15.18)
            storage_price = {"gp3": 0.08, "io2": 0.125}.get(storage_type, 0.08)
            lb_cost = 16.20 if lb_type == "application" else 0.0
            compute_cost = instance_count * monthly_instance
            storage_cost = storage_size * storage_price
            total = compute_cost + storage_cost + lb_cost
            return (
                f"1) Summary: {instance_count}x {instance_type or 't3.small'}, {int(storage_size)}GB {storage_type or 'gp3'}, LB: {lb_type}\n"
                f"2) Cost Breakdown: Compute ${compute_cost:.2f} + Storage ${storage_cost:.2f} + LB ${lb_cost:.2f}\n"
                f"3) Total Estimate: ~${total:.2f}/month (excludes data transfer)"
            )

        if provider == "gcp":
            monthly_instance = {"e2-micro": 7.00, "e2-small": 15.00}.get(instance_type, 12.00)
            storage_price = {"pd-balanced": 0.10, "pd-ssd": 0.17}.get(storage_type, 0.10)
            compute_cost = instance_count * monthly_instance
            storage_cost = storage_size * storage_price
            total = compute_cost + storage_cost
            return (
                f"1) Summary: {instance_count}x {instance_type or 'e2-small'}, {int(storage_size)}GB {storage_type or 'pd-balanced'}\n"
                f"2) Cost Breakdown: Compute ${compute_cost:.2f} + Storage ${storage_cost:.2f}\n"
                f"3) Total Estimate: ~${total:.2f}/month (excludes network egress)"
            )

        if provider == "azure":
            monthly_instance = {"B1s": 10.00, "B2s": 40.00}.get(instance_type, 25.00)
            storage_price = {"StandardSSD_LRS": 0.08, "Premium_LRS": 0.12}.get(storage_type, 0.08)
            compute_cost = instance_count * monthly_instance
            storage_cost = storage_size * storage_price
            total = compute_cost + storage_cost
            return (
                f"1) Summary: {instance_count}x {instance_type or 'B1s'}, {int(storage_size)}GB {storage_type or 'StandardSSD_LRS'}\n"
                f"2) Cost Breakdown: Compute ${compute_cost:.2f} + Storage ${storage_cost:.2f}\n"
                f"3) Total Estimate: ~${total:.2f}/month (excludes bandwidth)"
            )

        monthly_instance = {"basic-1vcpu-1gb": 6.00, "basic-1vcpu-2gb": 12.00}.get(instance_type, 12.00)
        compute_cost = instance_count * monthly_instance
        total = compute_cost
        return (
            f"1) Summary: {instance_count}x {instance_type or 'basic-1vcpu-2gb'} droplet\n"
            f"2) Cost Breakdown: Compute ${compute_cost:.2f}\n"
            f"3) Total Estimate: ~${total:.2f}/month (excludes bandwidth)"
        )

    @staticmethod
    def _normalize_bot_message(message: Any, is_complete: bool) -> str:
        text = str(message or "").strip()
        
        # If empty, provide a safe fallback
        if not text:
            if is_complete:
                return "🚀 All set! I'll generate your Terraform configuration now."
            return "What would you prefer for your deployment? 🤔"

        return text
