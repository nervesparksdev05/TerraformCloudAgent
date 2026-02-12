"""
Conversation Manager – Friendly multi-turn chatbot for EC2 Terraform parameters.

Collects infrastructure requirements through warm, beginner-friendly conversation,
then builds structured params for LLMGenerator to produce Terraform files.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.core import config
from app.core.logger import get_logger
from app.models.conversation_schemas import (
    ChatMessageResponse,
    ConversationSession,
    ConversationStatus,
)

logger = get_logger(__name__)


class ConversationManager:
    """
    Friendly chatbot that collects EC2 deployment parameters.

    Flow:
      1. Warm conversation across 6 stages (1 question per turn)
      2. Deep-merge extracted params each turn
      3. Apply secure defaults on completion
      4. build_terraform_request() → structured dict for LLMGenerator
    """

    # ================================================================
    # SYSTEM PROMPT
    # ================================================================

    SYSTEM_PROMPT = """\
You are a friendly, warm cloud infrastructure expert — like a helpful senior DevOps engineer pair-programming with a colleague. The user may know nothing about cloud — YOU guide them with patience, encouragement, and simple language.

🎯 YOUR PERSONALITY:
- Warm, encouraging, patient ("Great choice!", "Perfect!", "That works well!")
- Use cloud-native terminology based on provider:
  * AWS → "EC2 instances", "regions" (us-east-1, eu-west-1)
  * GCP → "Compute Engine instances", "regions" (us-central1, europe-west1)
  * Azure → "Virtual Machines", "regions" (eastus, westeurope)
  * DigitalOcean → "Droplets", "regions" (nyc1, sfo3)
- Explain jargon in parentheses when you first use it
- If user says "you choose" / "I don't know" / "default" → pick the best option, explain why briefly, and move on
- Acknowledge their answer before asking the next question
- Keep messages under 120 words (except the final summary)
- Use bold and bullets for clarity

⚠️ HARD RULES:
1. You are a parameter collector — NEVER output Terraform/HCL code.
2. Ask exactly ONE question per turn. No compound questions.
3. Extract every parameter the user implies — even in passing. Don't re-ask what you already have.
4. If user says "no" / "none" / "skip" → record it and move on IMMEDIATELY. Never re-ask.
5. Check [Collected so far: {...}] every turn — skip stages where you have all params.
6. NEVER accept 0.0.0.0/0 for SSH. Explain the risk, suggest their IP/32 or VPN CIDR.
7. Use cloud-specific terms consistently throughout the conversation.
8. CRITICAL: Your "message" MUST always end with a question for the next step, unless "is_complete": true.
9. If you have collected all parameters for the current stage, increment `current_stage` in your response.

═══════════════════════════════════════════════════════════════
CONVERSATION STAGES (work through IN ORDER, skip what you have)
═══════════════════════════════════════════════════════════════

STAGE 1 — What, Where & Which Cloud
  Collect: workload_type (web_server|api|app_server|database|batch|custom)
           workload_description (1-2 sentence summary)
           cloud_provider (aws|gcp|azure|digitalocean)
           region (cloud-specific region code)
           environment (dev|staging|prod — default "dev" if unclear)
  Strategy: 
    1. Ask "What are you deploying?" → infer workload_type
    2. Ask "Which cloud provider?" → AWS, GCP, Azure, or DigitalOcean
    3. Ask "Which region/location?" → suggest popular regions for chosen cloud
       AWS: us-east-1 (Virginia), us-west-2 (Oregon), eu-west-1 (Ireland)
       GCP: us-central1 (Iowa), us-east1 (S. Carolina), europe-west1 (Belgium)
       Azure: eastus (Virginia), westus2 (Washington), westeurope (Netherlands)
       DigitalOcean: nyc1, nyc3, sfo3, lon1, fra1
    4. Use cloud-native terminology in all future responses

STAGE 2 — Size & Resources
  Collect: instance_count (1-100; suggest 2 for prod)
           instance_type (cloud-specific: t3.micro for AWS, e2-micro for GCP, etc.)
           ami_os (amazon-linux-2|ubuntu-22.04|ubuntu-20.04|rhel-9|windows-server-2022)
  Strategy: Recommend type+count based on workload and cloud provider.
           Use cloud-native terms ("EC2 instance" vs "Compute Engine instance" vs "Droplet")
           Mention approximate hourly cost for transparency.

STAGE 3 — Storage
  Collect: storage_size_gb (8-16384; default 20)
           storage_type (gp3|gp2|io2|st1; default gp3)
  Strategy: "I'll use 20 GB gp3 encrypted — want to change?" Move fast.

STAGE 4 — Networking & Security
  Collect: ports (list of {port, protocol, source_cidr, description})
           ssh_allowed_cidrs (REJECT 0.0.0.0/0)
           load_balancer_type (application|network|none)
  Auto-set: vpc_cidr="10.0.0.0/16", subnet_type="both", subnet_count=2, enable_public_ip=true
  Strategy: Infer ports from workload (web→80,443; api→443; db→5432). Ask SSH CIDR explicitly.

STAGE 5 — IAM Permissions
  Collect: iam_services (dict: service → list of actions)
           iam_role_name (auto-generate if not specified)
  Always include baseline:
    cloudwatch: [logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents, cloudwatch:PutMetricData]
    ssm: [ssm:UpdateInstanceInformation, ssm:GetParameter]
  Strategy: Infer from workload ("stores in S3" → s3 perms). Present inference, ask to confirm.
  ⚠️ If user says "that's all" → STOP asking about IAM. Move to Stage 6.

STAGE 6 — Monitoring & Extras
  Collect: monitoring_enabled (bool; default true)
           detailed_monitoring (bool; true for prod)
           auto_scaling_enabled (bool; suggest true for prod multi-instance)
           auto_scaling_config ({min, max, target_cpu} — only if enabled)
           backup_enabled (bool)
           log_retention_days (7|14|30|90|365)
  Strategy: Batch 2-3 yes/no toggles in one question. Apply smart defaults by env.

═══════════════════════════════════════════════════════════════
RESPONSE FORMAT (strict JSON — every turn)
═══════════════════════════════════════════════════════════════

Return ONLY valid JSON. No markdown fences, no text outside JSON.

{
  "message": "<your friendly response — use **bold** and • bullets>",
  "thinking": "<1-2 sentences: which stage, what's missing>",
  "current_stage": <int 1-6>,
  "extracted_params": {
    // ONLY params extracted THIS turn. Exact key names from stages above.
    // Dicts (like iam_services): emit only NEW keys — orchestrator deep-merges.
    // Lists (like ports): emit FULL updated list each time.
    // Booleans: true/false not strings. Numbers: numbers not strings.
  },
  "next_question": "<category hint>",
  "is_complete": <bool — true ONLY when checklist passes>,
  "suggestions": ["<up to 4 quick-reply options>"],
  "aws_mcp_query": "<MCP command string or null>"
}

═══════════════════════════════════════════════════════════════
COMPLETION CHECKLIST (is_complete=true ONLY when ALL present)
═══════════════════════════════════════════════════════════════

Required (non-null):
  ☐ workload_type  ☐ workload_description  ☐ environment
  ☐ instance_count  ☐ instance_type  ☐ region  ☐ ami_os
  ☐ storage_size_gb  ☐ storage_type
  ☐ ports (at least one)  ☐ ssh_allowed_cidrs (NOT 0.0.0.0/0)
  ☐ iam_services (at minimum baseline cloudwatch+ssm)
  ☐ monitoring_enabled


When is_complete=true, calculate and show estimated monthly cost before summary:

💵 COST ESTIMATION (CRITICAL - MUST SHOW):
1. Calculate monthly cost based on cloud provider:

   AWS Pricing:
   - Compute: instance_type × instance_count × hourly_rate × 730 hours
     Examples: t3.micro=$0.0104/hr, t3.small=$0.0208/hr, t3.medium=$0.0416/hr
   - Storage: storage_size_gb × $0.10/GB/month (gp3) or $0.08/GB (gp2)
   - Load Balancer: $16.20/month (ALB) or $22/month (NLB) if enabled
   - Data transfer: First 100 GB free, then $0.09/GB

   GCP Pricing:
   - Compute: e2-micro=$0.008/hr, e2-small=$0.033/hr, e2-medium=$0.067/hr
   - Storage: $0.17/GB/month (pd-standard), $0.10/GB (pd-balanced)
   - Load Balancer: ~$18/month

   Azure Pricing:
   - Compute: B1s=$0.0104/hr, B2s=$0.0416/hr (similar to AWS)
   - Storage: $0.05/GB/month (Standard HDD), $0.12/GB (Standard SSD)

   DigitalOcean Pricing:
   - Droplets: Basic droplets from $4/month (512MB), $6/month (1GB), $12/month (2GB)
   - Storage: $0.10/GB/month

2. Show detailed breakdown in this EXACT format:

💵 **Estimated Monthly Cost: $XX.XX**

**Breakdown:**
• Compute: {instance_count} × {instance_type} × 730 hrs = **${compute_cost}**
• Storage: {storage_size_gb} GB × ${storage_rate}/GB = **${storage_cost}**
• Load Balancer: **${lb_cost}** (if enabled, else $0.00)
• Data Transfer: ~**${transfer_cost}** (estimated 100 GB/month)

**Total: ${total_cost}/month**

3. Then show ✅ summary of ALL params grouped by stage.

═══════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLES
═══════════════════════════════════════════════════════════════

--- Turn 1 ---
User: "I want to deploy a website"
{
  "message": "Awesome, let's get your website up and running! 🚀\\n\\nTo recommend the best setup, could you tell me a bit about it? For example:\\n• Is it a **static site** (HTML/CSS) or a **dynamic app** (Node.js, Python, PHP)?\\n• Is this for **production** (real users) or **development/testing**?",
  "thinking": "Stage 1: Got workload_type=web_server. Need workload_description and environment.",
  "current_stage": 1,
  "extracted_params": {"workload_type": "web_server"},
  "next_question": "workload_details",
  "is_complete": false,
  "suggestions": ["Static site (HTML/CSS)", "Node.js app", "Python/Django app", "It's for production"],
  "aws_mcp_query": "list_instance_types web_server us-east-1"
}

--- Turn 2 ---
User: "It's a Node.js app for production, it stores files in S3"
{
  "message": "Great choice! A **production Node.js app with S3 storage** — I know exactly what you need.\\n\\nFor production I recommend **2 instances** across multiple availability zones (so if one goes down, the other keeps running). A **t3.small** (2 vCPU, 2 GB RAM, ~$15/mo each) handles moderate Node.js traffic well.\\n\\nDoes that sound right, or do you expect heavier traffic?",
  "thinking": "Stage 1 done. Stage 2: inferred S3 IAM perms. Need to confirm instance_count, instance_type, region, ami_os.",
  "current_stage": 2,
  "extracted_params": {
    "workload_description": "Node.js web app with S3 file uploads",
    "environment": "prod",
    "iam_services": {"s3": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"]}
  },
  "next_question": "instance_count_and_type",
  "is_complete": false,
  "suggestions": ["2 × t3.small sounds good", "I need larger instances", "Just 1 for now", "3+ for high traffic"],
  "aws_mcp_query": "recommend web_server moderate us-east-1"
}

--- Turn 3 ---
User: "2 t3.small, us-east-1, Ubuntu"
{
  "message": "Perfect! **2 × t3.small** in **us-east-1** running **Ubuntu 22.04** 👍\\n\\nFor storage I'll set up a **20 GB gp3** encrypted volume (fast and cost-effective). Want to change the size or type, or are defaults fine?",
  "thinking": "Stage 2 done. Stage 3: need storage confirmation.",
  "current_stage": 3,
  "extracted_params": {"instance_count": 2, "instance_type": "t3.small", "region": "us-east-1", "ami_os": "ubuntu-22.04"},
  "next_question": "storage",
  "is_complete": false,
  "suggestions": ["Defaults are fine", "I need more storage", "Use io2 for high IOPS"],
  "aws_mcp_query": "validate_instance_type t3.small us-east-1"
}

--- Turn 4 ---
User: "defaults are fine"
{
  "message": "Got it — **20 GB gp3 encrypted** ✅\\n\\nNow for security: your web app needs **ports 80** (HTTP) and **443** (HTTPS) open to the internet. I'll also set up SSH access — but only from YOUR IP for security.\\n\\n**What's your IP address or office/VPN range?** (e.g., 203.0.113.50/32)",
  "thinking": "Stage 3 done. Stage 4: web→ports 80,443. Need SSH CIDR.",
  "current_stage": 4,
  "extracted_params": {"storage_size_gb": 20, "storage_type": "gp3"},
  "next_question": "ssh_cidr",
  "is_complete": false,
  "suggestions": ["My IP is (I'll type it)", "Use 10.0.0.0/8 (VPN)", "I'll use SSM instead of SSH"],
  "aws_mcp_query": null
}

--- Turn 5 ---
User: "203.0.113.50/32, and add a load balancer"
{
  "message": "I'll set up an **Application Load Balancer** distributing traffic to both instances with HTTP→HTTPS redirect 🔒\\n\\nSecurity groups:\\n• Ports **80 & 443** — open to internet\\n• Port **22 (SSH)** — only from **203.0.113.50/32**\\n\\nSince your app uses S3, I've already noted those permissions. Does it need access to any **other AWS services** — like RDS, DynamoDB, SQS, or Secrets Manager?",
  "thinking": "Stage 4 done. Stage 5: have s3 perms. Ask about additional services.",
  "current_stage": 5,
  "extracted_params": {
    "ssh_allowed_cidrs": ["203.0.113.50/32"],
    "ports": [
      {"port": 80, "protocol": "tcp", "source_cidr": "0.0.0.0/0", "description": "HTTP"},
      {"port": 443, "protocol": "tcp", "source_cidr": "0.0.0.0/0", "description": "HTTPS"},
      {"port": 22, "protocol": "tcp", "source_cidr": "203.0.113.50/32", "description": "SSH"}
    ],
    "load_balancer_type": "application",
    "vpc_cidr": "10.0.0.0/16", "subnet_type": "both", "subnet_count": 2, "enable_public_ip": true
  },
  "next_question": "iam_additional",
  "is_complete": false,
  "suggestions": ["Also needs RDS", "Also uses SQS", "S3 is all it needs", "Add Secrets Manager"],
  "aws_mcp_query": null
}

--- Turn 6 ---
User: "it talks to RDS, use Secrets Manager for creds. That's all for permissions"
{
  "message": "I'll create a custom IAM role **web-server-prod-role** with:\\n• **S3** — read/write uploads\\n• **RDS** — database authentication\\n• **Secrets Manager** — read DB credentials\\n• **CloudWatch** — logs & metrics (always included)\\n• **SSM** — instance management (always included)\\n\\nAlmost done! For production I recommend:\\n• ✅ Detailed CloudWatch monitoring\\n• ✅ Log retention: 30 days\\n• ✅ Auto-scaling (2–6 instances, target 70% CPU)\\n• ✅ EBS backup snapshots\\n\\nShall I enable all of these?",
  "thinking": "Stage 5 done — user said 'that's all'. Stage 6: recommend prod defaults.",
  "current_stage": 6,
  "extracted_params": {
    "iam_services": {
      "rds": ["rds-db:connect"],
      "secretsmanager": ["secretsmanager:GetSecretValue"],
      "cloudwatch": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "cloudwatch:PutMetricData"],
      "ssm": ["ssm:UpdateInstanceInformation", "ssm:GetParameter"]
    },
    "iam_role_name": "web-server-prod-role"
  },
  "next_question": "monitoring_extras",
  "is_complete": false,
  "suggestions": ["Enable all recommended", "Skip auto-scaling", "Customize", "Just monitoring"],
  "aws_mcp_query": null
}

--- Turn 7 ---
User: "enable all"
{
  "message": "Excellent! Here's your complete setup:\\n\\n✅ **Workload**: Node.js web app with S3 uploads (production)\\n✅ **Compute**: 2 × t3.small in us-east-1, Ubuntu 22.04\\n✅ **Storage**: 20 GB gp3, encrypted\\n✅ **Network**: VPC 10.0.0.0/16, public + private subnets, 2 AZs\\n✅ **Load Balancer**: Application LB with HTTPS\\n✅ **Ports**: 80, 443 (public) · 22 (203.0.113.50/32 only)\\n✅ **IAM**: web-server-prod-role (S3, RDS, Secrets Manager, CloudWatch, SSM)\\n✅ **Monitoring**: Detailed CloudWatch + 30-day logs\\n✅ **Auto-Scaling**: 2–6 instances, 70% CPU target\\n✅ **Backup**: EBS snapshots enabled\\n✅ **Security**: IMDSv2 enforced, EBS encrypted, SSH restricted\\n\\n🚀 Ready to generate your Terraform files!",
  "thinking": "All stages complete. Checklist passes.",
  "current_stage": 6,
  "extracted_params": {
    "monitoring_enabled": true, "detailed_monitoring": true,
    "cloudwatch_logs_enabled": true, "log_retention_days": 30,
    "auto_scaling_enabled": true, "auto_scaling_config": {"min": 2, "max": 6, "target_cpu": 70},
    "backup_enabled": true, "enable_imdsv2": true
  },
  "next_question": null,
  "is_complete": true,
  "suggestions": [],
  "aws_mcp_query": null
}

═══════════════════════════════════════════════════════════════
EDGE CASES
═══════════════════════════════════════════════════════════════
• "I don't know" → Pick best default, explain why, confirm.
• Multiple params in one message → Extract ALL, skip ahead.
• "0.0.0.0/0 for SSH" → REFUSE. Explain brute-force risk. Ask for specific CIDR.
• User asks "what options" → Use MCP query (list_instance_types, list_regions).
• "just use defaults" → Apply all defaults, show summary, set is_complete=true.
• User goes back to change → Update param, acknowledge, continue.
• User asks about AWS → Answer briefly, return to collection.
"""

    # ================================================================
    # INIT
    # ================================================================

    def __init__(self) -> None:
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        self.sessions: Dict[str, ConversationSession] = {}
        self.openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        
        # MongoDB connection for session persistence
        try:
            from pymongo import MongoClient
            mongo_uri = config.MONGODB_URI
            mongo_db = config.MONGODB_DATABASE
            if mongo_uri and mongo_db:
                client = MongoClient(mongo_uri)
                db = client[mongo_db]
                self.sessions_collection = db["sessions"]
                logger.info("ConversationManager initialized with MongoDB persistence")
            else:
                self.sessions_collection = None
                logger.warning("MongoDB not configured - sessions will not persist")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self.sessions_collection = None
        
        logger.info("ConversationManager initialised")

    # ================================================================
    # SESSION MANAGEMENT
    # ================================================================

    def create_session(self, provider: str = "aws") -> Dict[str, Any]:
        sid = f"sess_{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(4)}"
        self.sessions[sid] = ConversationSession(
            session_id=sid,
            provider=provider,
            messages=[],
            collected_parameters={},
            is_complete=False,
            status=ConversationStatus.ACTIVE,
        )
        
        # Persist to MongoDB
        if self.sessions_collection:
            try:
                self.sessions_collection.insert_one(self.sessions[sid].dict())
            except Exception as e:
                logger.error(f"Failed to persist session {sid}: {e}")
                
        logger.info("Created session: %s", sid)
        return {
            "session_id": sid,
            "bot_response": (
                "Hey there! 👋 I'm your cloud infrastructure buddy. "
                "I'll help you deploy to **AWS, GCP, Azure, or DigitalOcean** "
                "— no cloud expertise needed!\n\n"
                "**What would you like to deploy?** "
                "(e.g., a website, an API, a database server, an application)"
            ),
            "suggestions": [
                "A website",
                "An API backend",
                "A database server",
                "A web application",
                "You choose for me",
            ],
        }

    def get_session(self, sid: str) -> Optional[ConversationSession]:
        return self.sessions.get(sid)

    # ================================================================
    # MESSAGE PROCESSING
    # ================================================================

    async def process_message(
        self, session_id: str, user_message: str
    ) -> ChatMessageResponse:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        if session.status != ConversationStatus.ACTIVE:
            raise ValueError(
                f"Session {session_id} not active (status: {session.status})"
            )

        session.messages.append({"role": "user", "content": user_message})
        raw = await self._call_llm(session)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("LLM JSON parse failed: %s", raw[:300])
            data = {
                "message": "Sorry, could you rephrase that? I hit a hiccup 😅",
                "extracted_params": {},
                "suggestions": [],
                "is_complete": False,
            }

        # Normalize field types
        data.setdefault("message", "Could you tell me a bit more?")
        data.setdefault("extracted_params", {})
        data.setdefault("suggestions", [])
        data.setdefault("is_complete", False)
        if not isinstance(data["extracted_params"], dict):
            data["extracted_params"] = {}
        if not isinstance(data["suggestions"], list):
            data["suggestions"] = []

        # Deep-merge extracted params
        self._deep_merge(
            session.collected_parameters, data["extracted_params"]
        )
        session.is_complete = bool(data["is_complete"])
        session.updated_at = datetime.now()

        if session.is_complete:
            self._apply_defaults(session.collected_parameters)
            session.status = ConversationStatus.COMPLETE
            
            # Inject cost calculation into the message
            cost_breakdown = self._calculate_cost(session.collected_parameters)
            if cost_breakdown and "💰" not in data["message"]:
                data["message"] = cost_breakdown + data["message"]
            
            logger.info(
                "[%s] Complete – %d params",
                session_id,
                len(session.collected_parameters),
            )

        session.messages.append(
            {"role": "assistant", "content": data["message"]}
        )
        
        # Update MongoDB
        if self.sessions_collection:
            try:
                self.sessions_collection.update_one(
                    {"session_id": session_id},
                    {
                        "$set": {
                            "messages": session.messages,
                            "collected_parameters": session.collected_parameters,
                            "is_complete": session.is_complete,
                            "status": session.status,
                            "updated_at": session.updated_at
                        }
                    }
                )
            except Exception as e:
                logger.error(f"Failed to update session {session_id}: {e}")

        return ChatMessageResponse(
            session_id=session_id,
            bot_response=data["message"],
            collected_parameters=session.collected_parameters,
            is_complete=session.is_complete,
            suggestions=data.get("suggestions", []),
            next_question=data.get("next_question"),
        )

    # ================================================================
    # LLM CALL
    # ================================================================

    async def _call_llm(self, session: ConversationSession) -> str:
        snapshot = json.dumps(session.collected_parameters, indent=2)
        context = (
            f"\n\n[Collected so far: {snapshot}]\n"
            f"[Provider: {session.provider.upper()}] "
            f"[Turns: {len(session.messages)}]"
        )

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT + context}
        ]
        for msg in session.messages:
            if msg["role"] in ("user", "assistant"):
                messages.append(
                    {"role": msg["role"], "content": msg["content"]}
                )

        try:
            resp = await self.openai_client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                temperature=0.15,
                response_format={"type": "json_object"},
                max_tokens=1200,
            )
            body = resp.choices[0].message.content
            data = json.loads(body)

            return json.dumps(data)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON: %s", e)
            return json.dumps({
                "message": "Could you rephrase that? I couldn't understand.",
                "extracted_params": {},
                "suggestions": [],
                "is_complete": False,
                "current_stage": 1,
            })
        except Exception:
            logger.exception("LLM call failed")
            raise

    # ================================================================
    # BUILD TERRAFORM REQUEST (conversation → LLMGenerator)
    # ================================================================

    def build_terraform_request(self, session_id: str) -> Dict[str, Any]:
        """
        Build structured dict that LLMGenerator.generate_terraform() expects.

        Maps conversation param names → generator param names.
        Called by main.py after conversation is complete.
        """
        session = self.get_session(session_id)
        if not session or not session.is_complete:
            raise ValueError("Session not found or incomplete")

        p = dict(session.collected_parameters)

        return {
            # ── Keys LLMGenerator._build_structured_prompt() reads ──
            "terraform_resource_type": "aws_instance",
            "resource_description": "EC2 instance",
            "service_type": p.get("workload_type", "web_server"),
            "cloud_provider": session.provider or "aws",
            "environment": p.get("environment", "dev"),
            "instance_count": p.get("instance_count", 1),
            "instance_type": p.get("instance_type", "t3.micro"),
            "region": p.get("region", "us-east-1"),
            "os_image": p.get("ami_os", "ubuntu-22.04"),
            "storage_size": p.get("storage_size_gb", 20),
            "storage_type": p.get("storage_type", "gp3"),
            "database_type": "none",
            # ── Rich context for better Terraform generation ──
            "workload_description": p.get("workload_description", ""),
            "vpc_cidr": p.get("vpc_cidr", "10.0.0.0/16"),
            "subnet_type": p.get("subnet_type", "both"),
            "subnet_count": p.get("subnet_count", 2),
            "enable_public_ip": p.get("enable_public_ip", True),
            "ports": p.get("ports", []),
            "ssh_allowed_cidrs": p.get("ssh_allowed_cidrs", []),
            "load_balancer_type": p.get("load_balancer_type", "none"),
            "enable_https": p.get("enable_https", False),
            "iam_services": p.get("iam_services", {}),
            "iam_role_name": p.get("iam_role_name", ""),
            "monitoring_enabled": p.get("monitoring_enabled", True),
            "detailed_monitoring": p.get("detailed_monitoring", False),
            "cloudwatch_logs_enabled": p.get(
                "cloudwatch_logs_enabled", True
            ),
            "log_retention_days": p.get("log_retention_days", 30),
            "auto_scaling_enabled": p.get("auto_scaling_enabled", False),
            "auto_scaling_config": p.get("auto_scaling_config"),
            "backup_enabled": p.get("backup_enabled", False),
            "enable_imdsv2": p.get("enable_imdsv2", True),
            "storage_encrypted": p.get("storage_encrypted", True),
        }

    # ================================================================
    # HELPERS
    # ================================================================

    @staticmethod
    def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> None:
        """Recursively merge overlay into base in place."""
        for key, value in overlay.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                ConversationManager._deep_merge(base[key], value)
            else:
                base[key] = value

    @staticmethod
    def _apply_defaults(params: Dict[str, Any]) -> None:
        """Fill missing params with secure, environment-aware defaults."""
        is_prod = params.get("environment") == "prod"
        multi = params.get("instance_count", 1) > 1

        defaults: Dict[str, Any] = {
            "vpc_cidr": "10.0.0.0/16",
            "subnet_type": "both",
            "subnet_count": 2,
            "enable_public_ip": True,
            "storage_encrypted": True,
            "storage_size_gb": 20,
            "storage_type": "gp3",
            "load_balancer_type": (
                "application" if is_prod and multi else "none"
            ),
            "enable_https": is_prod and multi,
            "detailed_monitoring": is_prod,
            "cloudwatch_logs_enabled": True,
            "log_retention_days": 30,
            "monitoring_enabled": True,
            "auto_scaling_enabled": False,
            "backup_enabled": False,
            "enable_imdsv2": True,
        }
        for key, value in defaults.items():
            params.setdefault(key, value)

        # Ensure baseline IAM services always present
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
        iam.setdefault(
            "ssm",
            [
                "ssm:UpdateInstanceInformation",
                "ssm:GetParameter",
            ],
        )

    # ================================================================
    # PARAMETER RETRIEVAL
    # ================================================================

    def get_collected_parameters(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        return session.collected_parameters

    def is_session_complete(self, session_id: str) -> bool:
        session = self.get_session(session_id)
        return session.is_complete if session else False

    # ================================================================
    # COST CALCULATION
    # ================================================================

    def _calculate_cost(self, params: dict) -> str:
        """Calculate estimated monthly cost and return formatted string."""
        try:
            instance_count = params.get("instance_count", 1)
            instance_type = params.get("instance_type", "t3.micro")
            storage_size = params.get("storage_size_gb", 20)
            storage_type = params.get("storage_type", "gp3")
            lb_type = params.get("load_balancer_type", "none")
            
            # AWS pricing (simplified)
            instance_prices = {
                "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416,
                "t3.large": 0.0832, "t3.xlarge": 0.1664,
                "t2.micro": 0.0116, "t2.small": 0.023, "t2.medium": 0.0464,
            }
            storage_prices = {"gp3": 0.08, "gp2": 0.10, "io2": 0.125}
            lb_prices = {"application": 16.20, "network": 22.00, "none": 0.00}
            
            hourly_rate = instance_prices.get(instance_type, 0.02)
            storage_rate = storage_prices.get(storage_type, 0.08)
            lb_cost = lb_prices.get(lb_type, 0.00)
            
            compute_cost = instance_count * hourly_rate * 730
            storage_cost = storage_size * storage_rate
            total_cost = compute_cost + storage_cost + lb_cost
            
            cost_breakdown = f"""
💰 **Estimated Monthly Cost: ${total_cost:.2f}**

**Breakdown:**
• Compute: {instance_count} × {instance_type} × 730 hrs = **${compute_cost:.2f}**
• Storage: {storage_size} GB {storage_type} = **${storage_cost:.2f}**
• Load Balancer: **${lb_cost:.2f}**

**Total: ~${total_cost:.2f}/month**

*Actual costs may vary based on usage, region, and data transfer.*

---

"""
            return cost_breakdown
        except Exception as e:
            logger.error(f"Cost calculation failed: {e}")
            return ""

    # ================================================================
    # SESSION LISTING & DELETION
    # ================================================================

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent sessions for the sidebar history."""
        if not self.sessions_collection:
            # Fallback to in-memory sessions
            sessions_list = []
            for sid, session in list(self.sessions.items())[:limit]:
                title = "New Conversation"
                if session.messages:
                    for msg in session.messages:
                        if msg.get("role") == "user":
                            content = msg.get("content", "")
                            title = (content[:30] + "...") if len(content) > 30 else content
                            break
                
                sessions_list.append({
                    "session_id": sid,
                    "title": title,
                    "workload_type": session.collected_parameters.get("workload_type", ""),
                    "provider": session.provider,
                    "updated_at": datetime.now().isoformat(),
                    "created_at": datetime.now().isoformat()
                })
            return sessions_list
        
        try:
            cursor = self.sessions_collection.find(
                {}, 
                {"session_id": 1, "messages": 1, "collected_parameters": 1, "provider": 1, "updated_at": 1, "created_at": 1}
            ).sort("updated_at", -1).limit(limit)
            
            sessions = []
            for doc in cursor:
                params = doc.get("collected_parameters", {})
                created = doc.get("created_at")
                
                # Build descriptive title
                workload = params.get("workload_description", "")
                workload_type = params.get("workload_type", "")
                provider = params.get("cloud_provider") or doc.get("provider", "")
                
                if workload:
                    title = workload[:40] + "..." if len(workload) > 40 else workload
                elif workload_type:
                    title = workload_type.replace("_", " ").title()
                else:
                    messages = doc.get("messages", [])
                    for msg in messages:
                        if msg.get("role") == "user":
                            content = msg.get("content", "")
                            title = (content[:30] + "...") if len(content) > 30 else content
                            break
                    else:
                        title = "New Conversation"
                
                if provider:
                    title = f"{title} ({provider.upper()})"
                
                if created:
                    date_str = created.strftime("%b %d")
                    title = f"{title} - {date_str}"
                
                sessions.append({
                    "session_id": doc["session_id"],
                    "title": title,
                    "updated_at": doc.get("updated_at", doc.get("created_at")).isoformat(),
                    "created_at": doc.get("created_at").isoformat(),
                    "workload_type": workload_type,
                    "provider": provider
                })
            return sessions
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from storage."""
        # Remove from in-memory
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        # Remove from MongoDB if available
        if self.sessions_collection:
            try:
                result = self.sessions_collection.delete_one({"session_id": session_id})
                return result.deleted_count > 0
            except Exception as e:
                logger.error(f"Failed to delete session {session_id}: {e}")
                return False
        return True

    def add_run_to_session(self, session_id: str, run_id: str) -> None:
        """Link a run ID to a session."""
        session = self.get_session(session_id)
        if session:
            if not hasattr(session, "run_ids"):
                session.run_ids = []
            session.run_ids.append(run_id)
            session.updated_at = datetime.now()
            
            # Update MongoDB
            if self.sessions_collection:
                try:
                    self.sessions_collection.update_one(
                        {"session_id": session_id},
                        {
                            "$addToSet": {"run_ids": run_id},
                            "$set": {"updated_at": session.updated_at}
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to update session with run_id: {e}")
