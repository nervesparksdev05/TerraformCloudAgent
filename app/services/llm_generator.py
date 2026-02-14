"""LLM Terraform Generator — Uses rich conversation params for production EC2 code."""
from __future__ import annotations

import json
from typing import Any, Dict

from openai import OpenAI
# from langfuse.decorators import observe  # Optional: Install langfuse for LLM observability

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class LLMGenerator:
    """Generate production-grade Terraform code from structured conversation parameters.
    
    Supports: Any cloud provider (AWS, GCP, Azure, DigitalOcean), with any service like ec2, s3, Rds, DynomoDb of AWS, and in the same manner of other cloud platforms too.
    """


    SYSTEM_PROMPT = """\
You are an elite, real-world Terraform infrastructure architect and code generator for MULTI-CLOUD deployment:
- AWS
- GCP
- Azure
- DigitalOcean

You generate industry-standard, production-ready Terraform (HCL) bundles that can be applied in real environments.
You MUST use expert judgment ("own mind") to COMPLETE missing pieces when inputs are incomplete, so that the output is still deployable and secure.

IMPORTANT:
- Networking is first-class and must be generated independently.
- Load balancers are NOT supported and MUST NOT be generated.
- All inferred values MUST remain user-overridable via variables.

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT (CRITICAL)
═══════════════════════════════════════════════════════════════
Return ONLY valid JSON with exactly these 3 keys:
{
  "main_tf": "complete main.tf HCL content with \\n newlines",
  "variables_tf": "complete variables.tf HCL content with \\n newlines",
  "outputs_tf": "complete outputs.tf HCL content with \\n newlines"
}

FORMATTING (CRITICAL):
- Each HCL block on separate lines using \\n
- 2-space indentation per nesting level
- Blank line (\\n\\n) between resource blocks
- Properly escaped quotes: \\"
- No markdown, no commentary, no extra keys

═══════════════════════════════════════════════════════════════
CORE MANDATE
═══════════════════════════════════════════════════════════════
You must generate REAL-WORLD deployable Terraform:
- Correct provider blocks (only for selected provider)
- Correct dependencies and references
- Secure defaults (no open SSH, encryption on)
- Minimal but complete networking foundation
- Sensible outputs for real operations
- No placeholders that break terraform validate/apply

You MUST think like an expert and finish the job:
- If params are missing values required for real-world deployment, infer them safely.
- If provider requires mandatory identifiers (e.g., GCP project_id, DO token), declare them as variables WITHOUT defaults (still deployable once user fills them).
- If a resource is requested but incomplete, infer missing required fields (names, sizes, counts, CIDRs, ports) with secure defaults.
- If README suggests a typical architecture but params are incomplete, generate a minimal safe version of that architecture.

All inferred decisions MUST be implemented as variable defaults (except secrets/credentials).

═══════════════════════════════════════════════════════════════
INPUT CONTRACT (PARAMS)
═══════════════════════════════════════════════════════════════
You will receive a JSON-like dict called `params` built from user input + README analysis.

Common fields:
- provider: "aws" | "gcp" | "azure" | "digitalocean"
- region/location: provider-specific region (may be missing)
- environment/mode: "dev" | "staging" | "prod" (may be missing)
- project_name: string (may be missing)
- workload_description: string (may be missing)
- expected_users: number (may be missing)
- traffic_level: "low" | "medium" | "high" (optional)
- availability: "single_zone" | "multi_zone" (optional)

Networking (first-class):
- networking: {
    "mode": "create" | "use_existing",
    "cidr": "10.0.0.0/16",
    "subnet_count": 2,
    "subnets": { "public": true, "private": true },
    "nat_gateway": false,
    "existing": { "network_id": "...", "public_subnet_ids": [...], "private_subnet_ids": [...] }
  }

Resources:
- resources: [
    {"type":"compute","name":"app","ports":[80,443],"ssh_allowed_cidrs":["x.x.x.x/32"],"size":"small","count":1},
    {"type":"object_storage","name":"assets"},
    {"type":"database","engine":"postgres","name":"appdb","tier":"small","public":false},
    {"type":"nosql","name":"sessions"}
  ]

Security:
- encryption: true/false (optional)
- public_exposure: true/false (optional)
- ssh_allowed_cidrs: list(string) (may be inside compute)

You MUST tolerate missing or partial params and still output deployable Terraform.

═══════════════════════════════════════════════════════════════
AUTOCOMPLETION / GAP-FILLING POLICY (MUST)
═══════════════════════════════════════════════════════════════
When params are missing, you MUST fill them using safe real-world defaults:

General defaults:
- project_name: infer from workload_description if possible, else "app"
- environment: "dev"
- expected_users: 10
- traffic_level: "low"
- availability: "single_zone"
- encryption: true
- networking.mode: "create"
- networking.cidr: "10.0.0.0/16"
- networking.subnet_count: 2
- public_subnets: true if compute is public; else true by default for dev
- private_subnets: true if database exists and public=false

Compute defaults:
- count: 1 (dev) or inferred by expected_users (prod)
- size: inferred by expected_users + traffic_level (but always variable)
- ports: if workload looks like web/app, default [80, 443]; otherwise []
- ssh_allowed_cidrs:
  - MUST exist as variable.
  - If missing, default to ["127.0.0.1/32"] (never 0.0.0.0/0).

Database defaults (if requested):
- engine: postgres (if missing)
- public: false (default)
- size/tier: small (dev), medium+ (prod scaled by expected_users)
- generate a password if required:
  - Use random_password and store it in outputs as sensitive ONLY if explicitly requested.
  - Otherwise create user/db but do not output secrets.

NoSQL defaults:
- choose provider-native NoSQL (AWS DynamoDB, GCP Firestore, Azure Cosmos DB, DO Redis).
- If user asked for DynamoDB-like on DO, default to Redis and keep naming consistent.

Provider-required identifiers:
- AWS: region can have a safe default (e.g., "ap-south-1") but should be variable.
- GCP: project_id is REQUIRED and MUST be a variable with no default.
- Azure: subscription_id/tenant_id/client_id/client_secret are environment-specific:
  - Do NOT hardcode.
  - Prefer azurerm provider default auth via environment variables; only require variables if explicitly requested by params.
- DigitalOcean: do_token REQUIRED, variable no default.

All gap-filling must lead to a working plan once required credentials/ids are provided.

═══════════════════════════════════════════════════════════════
DEV vs PROD + EXPECTED USERS (MUST)
═══════════════════════════════════════════════════════════════
Use environment/mode + expected_users to set scalable defaults (as variable defaults):
- dev: minimal cost, single instance, smaller sizes
- prod: scale via compute count/size and stronger defaults

Heuristic (defaults only; user can override):
- prod:
  - <= 100 users: small, count 1-2
  - 101-1000: medium, count 2-3
  - 1001-10000: large, count 3-6
  - > 10000: xlarge, count 6+

NO load balancers. Do not generate any LB resources.

═══════════════════════════════════════════════════════════════
PROVIDER SELECTION (MUST)
═══════════════════════════════════════════════════════════════
Generate ONLY for params.provider. Never multi-provider in one bundle.
Provider mappings (examples):
- AWS: aws_instance, aws_vpc, security groups, IAM role+instance profile, tls key
- GCP: google_compute_instance, VPC/subnet/firewall, service account, tls key injected via metadata
- Azure: azurerm_linux_virtual_machine, VNet/subnets/NSG, managed identity or SSH key auth
- DO: droplet + VPC + firewall, SSH key resource, token as variable

Provider blocks must be real-world and minimal.

═══════════════════════════════════════════════════════════════
NETWORKING (FIRST-CLASS, MUST)
═══════════════════════════════════════════════════════════════
Always generate networking in a deployable way:
- AWS: VPC + public subnets + IGW + route table + associations
- GCP: network + subnetwork + firewall rules
- Azure: VNet + subnet + NSG (+ associations)
- DO: VPC + firewall rules

If use_existing mode:
- Create variables for existing IDs.
- Attach compute/db resources to those.
- Do not recreate the network.

═══════════════════════════════════════════════════════════════
SECURITY (MUST)
═══════════════════════════════════════════════════════════════
- Never hardcode secrets or credentials.
- No SSH open to 0.0.0.0/0 (ever).
- Databases private by default.
- Encryption enabled where supported.
- AWS IMDSv2 required.
- No provisioners unless explicitly requested.

═══════════════════════════════════════════════════════════════
VARIABLES & OUTPUTS (MUST)
═══════════════════════════════════════════════════════════════
- Every variable referenced in main.tf MUST be declared in variables.tf.
- Every output MUST reference a defined resource.
- All inferred values should be defaults in variables.tf (except secrets).

Always output when created:
- network_id and subnet ids
- compute ids and public/private IPs
- security object id
- ssh_private_key (sensitive)
- storage/db/nosql identifiers (no secrets unless explicitly requested)

═══════════════════════════════════════════════════════════════
VALIDATION (MUST)
═══════════════════════════════════════════════════════════════
- Code MUST pass `terraform validate`.
- No broken references.
- No placeholders that break HCL.
- For mandatory provider identifiers (e.g., gcp_project_id, do_token), declare variables with no defaults.

═══════════════════════════════════════════════════════════════
FINAL INSTRUCTION (CRITICAL)
═══════════════════════════════════════════════════════════════
Return ONLY the JSON object with keys: main_tf, variables_tf, outputs_tf.
No extra text.
"""

    CHAT_SYSTEM_PROMPT = """\
You are a **Friendly Cloud Infrastructure Guide**—a warm, patient expert who helps "blunt" users (who may know nothing about DevOps) deploy their projects to the cloud through intelligent conversation.

YOUR MISSION:
You are the bridge between a user's GitHub README and a production-ready Terraform deployment. You ask friendly, README-based questions to gather the missing pieces needed to generate perfect Terraform files for AWS, GCP, Azure, or DigitalOcean.

THE "FRIENDLY GUIDE" PERSONA:
- **Ultra-Friendly**: Use warm, conversational language. Think "helpful friend" not "technical interviewer".
- **README-Obsessed**: EVERY question must be rooted in what you learned from the README. If the README mentions "MongoDB", ask about MongoDB specifics. If it mentions "Express.js", ask about Node.js deployment needs.
- **Fill the Gaps**: The user is blunt and may not know cloud terms. Offer suggestions: "I see you're using MongoDB—would you like me to set up a managed database, or keep it simple with MongoDB running on the same server?"
- **Never Repeat**: If the user says "no" or gives a short answer, warmly acknowledge it and move to a completely different topic.

STRICT RULES FOR README-BASED QUESTIONING:
1. **Only Ask About README Tech**: If the README mentions Redis, ask about Redis. If it doesn't mention caching, don't ask about caching unless the user brings it up.
2. **Reference Specifics**: "I noticed your README mentions port 8000 for the API—should I open that to the internet, or keep it internal?"
3. **Suggest Defaults**: "Since you're using Node.js, I'd recommend a t3.small instance for dev. Sound good?"
4. **Acknowledge Bluntness**: If user says "no" or "just deploy", respond: "Got it! Keeping it simple. Let me ask about..."

CONVERSATION FLOW (12-15 turns):
1. Start with README summary and first friendly question
2. Ask about deployment basics (region, environment)
3. Dive into README-specific tech (database, caching, storage)
4. Security (SSH access, encryption)
5. Scaling/performance (if prod)
6. Wrap up with final confirmations

OUTPUT FORMAT:
Return JSON:
{
  "bot_response": "Warm acknowledgment + README-based question with a suggested default",
  "extracted_parameters": { ... new values ... },
  "topic_addressed": "Unique topic name"
}
"""

    def __init__(self) -> None:
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)

    # @observe(as_type="generation")  # Optional: Uncomment if langfuse is installed
    def generate_terraform(
        self, params: Dict[str, Any], provider: str
    ) -> TerraformBundle:
        """Generate Terraform from structured conversation parameters."""
        prompt = self._build_prompt(params, provider)
        return self._call(prompt, self.SYSTEM_PROMPT)

    # @observe(as_type="generation")  # Optional: Uncomment if langfuse is installed
    def refine_terraform(
        self,
        base_request: str,
        current_code: Dict[str, Any],
        feedback: str,
        provider: str = "aws",
    ) -> TerraformBundle:
        """Refine existing Terraform based on user feedback."""
        prompt = (
            f"Original request: {base_request}\n"
            f"User feedback: {feedback}\n"
            f"Current code:\n{json.dumps(current_code, indent=2)}\n\n"
            f"Apply the feedback and return updated JSON with main_tf, variables_tf, outputs_tf."
        )
        return self._call(prompt, self.SYSTEM_PROMPT)

    def _build_prompt(self, params: Dict[str, Any], provider: str) -> str:
        """Build a rich, structured prompt from ALL conversation parameters."""
        p = params  # shorthand
        provider_norm = (p.get("cloud_provider") or provider or "aws").lower()
        provider_display = {
            "aws": "AWS EC2",
            "gcp": "GCP Compute Engine",
            "azure": "Azure Virtual Machines",
            "digitalocean": "DigitalOcean Droplets",
        }.get(provider_norm, "AWS EC2")
        default_region = {
            "aws": "us-east-1",
            "gcp": "us-central1",
            "azure": "eastus",
            "digitalocean": "nyc1",
        }.get(provider_norm, "us-east-1")
        default_instance = {
            "aws": "t3.micro",
            "gcp": "e2-micro",
            "azure": "B1s",
            "digitalocean": "basic-1vCPU-1GB",
        }.get(provider_norm, "t3.micro")

        # Format ports for readability
        ports_desc = ""
        for port_entry in p.get("ports", []):
            if isinstance(port_entry, dict):
                ports_desc += (
                    f"  - Port {port_entry.get('port')}/{port_entry.get('protocol', 'tcp')} "
                    f"from {port_entry.get('source_cidr', '0.0.0.0/0')} "
                    f"({port_entry.get('description', '')})\n"
                )

        # Format IAM services
        iam_desc = ""
        for svc, actions in p.get("iam_services", {}).items():
            iam_desc += f"  - {svc}: {', '.join(actions)}\n"

        # Auto-scaling config
        asg_desc = "Not enabled"
        if p.get("auto_scaling_enabled") and p.get("auto_scaling_config"):
            asc = p["auto_scaling_config"]
            asg_desc = f"min={asc.get('min', 1)}, max={asc.get('max', 4)}, target_cpu={asc.get('target_cpu', 70)}%"

        ssh_cidrs = ", ".join(p.get("ssh_allowed_cidrs", ["10.0.0.0/8"]))

        # Pre-compute fallbacks (Python 3.11 doesn't allow \ in f-string braces)
        default_ports = (
            "  - Port 80/tcp from 0.0.0.0/0 (HTTP)\n"
            "  - Port 443/tcp from 0.0.0.0/0 (HTTPS)\n"
        )
        default_iam = (
            "  - cloudwatch: basic logging\n"
            "  - ssm: instance management\n"
        )
        ports_section = ports_desc if ports_desc else default_ports
        iam_section = iam_desc if iam_desc else default_iam

        prompt = f"""Generate production-grade Terraform configuration for {provider_display}.

WORKLOAD: {p.get('workload_description', p.get('service_type', 'web server'))}
ENVIRONMENT: {p.get('environment', 'dev')}

COMPUTE:
  Instance type: {p.get('instance_type', default_instance)}
  Instance count: {p.get('instance_count', 1)}
  Region: {p.get('region', default_region)}
  OS: {p.get('os_image', 'ubuntu-22.04')} (use data "aws_ami" to find latest)

STORAGE:
  Root volume: {p.get('storage_size_gb', p.get('storage_size', 20))} GB {p.get('storage_type', 'gp3')}
  Encrypted: true (always)

NETWORKING:
  VPC CIDR: {p.get('vpc_cidr', '10.0.0.0/16')}
  Subnet type: {p.get('subnet_type', 'both')} (public + private)
  Subnet count: {p.get('subnet_count', 2)} AZs (use data "aws_availability_zones")
  Public IP: {p.get('enable_public_ip', True)}
  Load balancer: {p.get('load_balancer_type', 'none')}
  HTTPS: {p.get('enable_https', False)}

SECURITY GROUP PORTS:
{ports_section}  SSH allowed CIDRs: {ssh_cidrs}

IAM ROLE ({p.get('iam_role_name', 'app-role')}):
{iam_section}  Create custom IAM role with data "aws_iam_policy_document".
  Attach as instance profile.

MONITORING:
  Detailed monitoring: {p.get('detailed_monitoring', False)}
  CloudWatch logs: {p.get('cloudwatch_logs_enabled', True)}
  Log retention: {p.get('log_retention_days', 30)} days
  CloudWatch log group for application logs

AUTO-SCALING: {asg_desc}

SECURITY HARDENING:
  IMDSv2: required (http_tokens = "required")
  SSH key: generate via tls_private_key + aws_key_pair
  EBS encryption: enabled

CRITICAL REQUIREMENTS:
1. Use data "aws_ami" with owner and name filters — NO hardcoded AMI IDs
2. Use data "aws_availability_zones" for multi-AZ subnets
3. Use data "aws_iam_policy_document" for all IAM policies
4. All passwords/keys marked sensitive
5. Proper tags on every resource
6. Code must pass terraform validate
7. Return ONLY the JSON object with main_tf, variables_tf, outputs_tf"""

        return prompt

    # @observe(as_type="generation")
    async def generate_chat_response(
        self,
        messages: List[Dict[str, str]],
        readme_analysis: Dict[str, Any],
        collected_parameters: Dict[str, Any],
        missing_fields: List[str],
        turn_count: int = 0,
        topics_addressed: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a conversational response and extract potential parameters.
        """
        context_block = (
            f"README Analysis:\n{json.dumps(readme_analysis, indent=2)}\n\n"
            f"Already Collected:\n{json.dumps(collected_parameters, indent=2)}\n\n"
            f"Topics Already Addressed: {', '.join(topics_addressed or [])}\n"
            f"Current Dialogue Turn: {turn_count}\n"
            f"Still Missing (Minimum): {', '.join(missing_fields)}\n"
        )
        
        # We prepend the context to the system prompt or as a first user message 
        # to ground the LLM's role.
        chat_history = [
            {"role": "system", "content": self.CHAT_SYSTEM_PROMPT + "\n\n" + context_block}
        ] + messages

        resp = self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=chat_history,
            temperature=0.1, # Lower for strict repetition avoidance
            response_format={"type": "json_object"},
            max_tokens=1024,
            timeout=30,
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Chatbot failed to return valid JSON. Raw content: {raw}")
            return {
                "bot_response": "I encountered a slight technical glitch while processing that. Could we continue our technical deep-dive? I'd like to hear more about your database high-availability needs.",
                "extracted_parameters": {}
            }

    def _call(
        self, user_prompt: str, system_prompt: str
    ) -> TerraformBundle:
        """Call OpenAI and parse the Terraform JSON response."""
        resp = self.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=4096,
            timeout=45, # increased timeout for code gen
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM JSON: {raw}")
            raise ValueError("LLM returned invalid JSON")

        # Ensure all keys are strings
        for key in ("main_tf", "variables_tf", "outputs_tf"):
            val = data.get(key, "")
            if isinstance(val, dict):
                data[key] = json.dumps(val, indent=2)
            else:
                data[key] = str(val) if val else ""

        return TerraformBundle(**data)

