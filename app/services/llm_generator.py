"""llm_generator.py — TerraBot: Multi-cloud Terraform generator (AWS / GCP / DigitalOcean) powered by Gemini."""
from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from app.services import langfuse_service
from app.services.llm_service import LLMService, AsyncLLMService
from app.services.mcp_service import mcp_manager, ValidationResult

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class LLMGenerator:
    """Generate production-grade Terraform files for AWS, GCP, and DigitalOcean from conversation parameters."""

    _SYSTEM = """\
You are a senior AWS Terraform engineer specialising in the AWS Free Tier. Generate complete, production-ready Terraform for AWS.

══ STRICT AWS FREE TIER RULES ══
1. INSTANCES: ALWAYS default to 't3.micro' (Free Tier eligible in all regions). NEVER default to 't2.micro' — some accounts/regions reject it with InvalidParameterCombination.
2. STORAGE: Keep EBS volumes to 'gp3'. Total storage must not exceed 30GB.
3. DATABASE: Default to 'db.t3.micro' for RDS.
4. NETWORKING: Use Default VPC where possible. Avoid expensive NAT Gateways; use Public IPs.
5. NO SURPRISE COSTS: Never include ALBs, NLBs, or expensive KMS keys unless explicitly requested.

══ TERRAFORM/PROVIDER BLOCK (MANDATORY) ══
6. EVERY generated main.tf MUST start with a MULTI-LINE terraform block. Single-line blocks cause HCL parse errors.
   terraform {
     required_providers {
       aws = {
         source  = "hashicorp/aws"
         version = "~> 5.0"
       }
     }
   }
   provider "aws" {
     region = var.aws_region
   }
   CRITICAL: NEVER put the terraform/required_providers block on a single line. Terraform fmt REJECTS single-line nested blocks.

══ IDEMPOTENCY RULES (prevent EntityAlreadyExists on re-deploy) ══
7. IAM NAMING: ALWAYS use 'name_prefix' (not 'name') for aws_iam_role, aws_iam_policy, aws_iam_instance_profile.
8. SECRETS MANAGER: Use 'name_prefix' for aws_secretsmanager_secret. Set recovery_window_in_days = 0.

RULES:
- Never hardcode values — always use var.* in main.tf
- Tag all resources with Project = var.project_name
- Every variable must have type, description, and a sensible default in variables.tf — INCLUDING sensitive/secret variables (use default = "")
- BANNED: Never use 'data "template_file"'. It is deprecated.
- USER DATA SCRIPT:
  * Start with: #!/bin/bash, set -e, exec > /var/log/user-data.log 2>&1
  * Access Terraform variables directly as '${var.VARIABLE_NAME}'
  * Bash shell variables (APP_DIR, ENV_FILE, REPO_URL) MUST be written as '$${VAR_NAME}' so Terraform renders them as '${VAR_NAME}' for the shell
  * SYSTEMD SERVICE FILE: Inside <<'EOT' (single-quoted heredoc), shell variables are NOT expanded. WorkingDirectory, EnvironmentFile, ExecStart MUST use hardcoded literal paths (e.g. WorkingDirectory=/home/ubuntu/app). NEVER use $${APP_DIR} or ${APP_DIR} inside <<'EOT'
  * NODE.JS INSTALL: ALWAYS install Node.js via NodeSource (curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs). NEVER use 'sudo apt install nodejs npm' — it installs an ancient v12 that breaks modern apps
  * ENV FILE: Write ALL env vars (both secret and non-secret) to .env using 'cat > $${ENV_FILE} <<\'ENVEOF\'' with Terraform variable interpolation. Secret vars default to "" and user updates them after deploy
- CONSISTENCY: Variable names in 'main.tf' must exactly match 'variables.tf'
- SSH must NEVER allow 0.0.0.0/0 — use var.ssh_allowed_cidrs. Default MUST be [] (empty list)
- AMI: NEVER hardcode an AMI ID. ALWAYS use data "aws_ami" lookup with filter ubuntu-jammy-22.04, owners=["099720109477"]. Reference as data.aws_ami.ubuntu.id. Do NOT create an ami_id variable.
- VPC/SUBNET: ALWAYS use 'data "aws_vpc"' (default=true) and 'data "aws_subnet"' (default_for_az=true). NEVER use 'resource "aws_default_vpc"' or 'resource "aws_default_subnet"' — those are write resources.
- SECURITY GROUPS: ALWAYS use 'aws_security_group' with inline ingress/egress blocks. NEVER use aws_vpc_security_group_ingress_rule or aws_vpc_security_group_egress_rule.
- KEY PAIR (OPTIONAL): key_name = (var.key_pair_name != "" && var.key_pair_name != "REPLACE_ME") ? var.key_pair_name : null. Default for key_pair_name MUST be "" (empty string), never "REPLACE_ME".
- SNS EMAIL (OPTIONAL): aws_sns_topic_subscription MUST include count = (var.alert_email != "" && var.alert_email != "REPLACE_ME@example.com") ? 1 : 0. Default for alert_email MUST be "" (empty string).
- SECRETS MANAGER: Only generate Secrets Manager resources when use_secrets_manager is explicitly true. Otherwise, secret values go directly into .env as "" placeholders.
- Resource naming: {project_name}-{environment}-{resource_type}
- OUTPUTS: The 'sensitive' argument on an output MUST be a static boolean (true or false). NEVER use a variable expression like sensitive = (var.x == "foo") — Terraform forbids variables in sensitive and will fail at init. Always set sensitive = false or omit entirely.
- SNS: NEVER use 'confirmation_timeout_on_create' — this argument was removed in AWS provider v4.0.
- Output every operational value: IPs, URLs, SSH commands
- Return ONLY valid JSON: {"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}
"""

    _DO_SYSTEM = """\
You are a senior DigitalOcean Terraform engineer. Generate complete, production-ready Terraform for DigitalOcean.

== REQUIRED PROVIDER BLOCK ==
1. EVERY generated main.tf MUST start with:
   terraform {
     required_providers {
       digitalocean = { source = "digitalocean/digitalocean", version = "~> 2.0" }
     }
   }
   provider "digitalocean" { token = var.do_token }

== REQUIRED VARIABLES ==
2. Always declare these in variables.tf:
   - do_token      (sensitive = true, no default)
   - do_region     (default = "nyc3")
   - project_name
   - environment
   - ssh_key_name  (the DO SSH key name, not fingerprint)
   - alert_email

== SSH KEY LOOKUP ==
3. ALWAYS look up the SSH key by name using a data source:
   data "digitalocean_ssh_key" "main" { name = var.ssh_key_name }
   Reference: data.digitalocean_ssh_key.main.id
   NEVER hardcode a fingerprint or ID.

== DROPLET ==
4. Use resource "digitalocean_droplet" with:
   - image = "ubuntu-22-04-x64"
   - region = var.do_region
   - size = var.droplet_size
   - ssh_keys = [data.digitalocean_ssh_key.main.id]
   - Name pattern: {project_name}-{environment}-app-{count.index}

== VPC ==
5. Always create a digitalocean_vpc:
   - name: {project_name}-{environment}-vpc
   - region: var.do_region
   - ip_range: "10.10.0.0/16"

== FIREWALL ==
6. Always create a digitalocean_firewall with:
   - Allow inbound: 80/TCP, 443/TCP from 0.0.0.0/0
   - Allow inbound: 22/TCP from var.ssh_allowed_cidrs (default = ["0.0.0.0/0"] for DO, user restricts)
   - Allow all outbound

== LOAD BALANCER ==
7. When use_alb = true, create a digitalocean_loadbalancer:
   - forwarding_rule: entry_port=80 → target_port=80
   - healthcheck: port=var.health_check_port, path=var.health_check_path
   - region = var.do_region
   - Attach all Droplets via droplet_ids

== MANAGED DATABASE ==
8. For SQL: use resource "digitalocean_database_cluster" with engine and version.
   For Redis: use engine = "redis".
   Always use private_network_uuid = digitalocean_vpc.main.id

== SPACES ==
9. If storage_needs = true:
   - resource "digitalocean_spaces_bucket" with region = var.do_region
   - Optionally add digitalocean_spaces_bucket_cors_configuration

== DOMAIN / DNS ==
10. If custom_domain is set:
    - resource "digitalocean_domain" for the root domain
    - resource "digitalocean_record" A records pointing to Droplet IP or LB IP

== MONITORING ALERTS ==
11. If alert_email is set:
    - resource "digitalocean_monitor_alert" for CPU utilization > 80%
    - alerts block: email = [var.alert_email]

== PROJECT GROUPING ==
12. Always create a digitalocean_project to group all resources logically.

== STARTUP SCRIPT ==
13. User data for Droplet (same pattern as AWS):
    - #!/bin/bash, set -e
    - Install deps, clone repo, write .env, start app with systemd
    - Use ${var.VARIABLE_NAME} for Terraform variables in user_data (templatefile-style)
    - Use $${BASH_VAR} for Bash shell variables

== NAMING ==
14. Pattern: {project_name}-{environment}-{resource_type}

== SECRET HANDLING ==
15. Secret env vars default to "" in variables.tf and are written to .env as placeholders.

== OUTPUTS ==
16. Output: Droplet IPs, LB IP, database connection string, Spaces endpoint. The 'sensitive' argument on an output MUST be a static boolean (true or false). NEVER use a variable expression like sensitive = (var.x == "foo").

RETURN ONLY valid JSON: {"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}
"""

    _GCP_SYSTEM = """\
You are a senior Google Cloud (GCP) Terraform engineer. Generate complete, production-ready Terraform for GCP.

== REQUIRED PROVIDER BLOCK ==
1. EVERY generated main.tf MUST start with:
   terraform {
     required_providers {
       google = { source = "hashicorp/google", version = "~> 5.0" }
     }
   }
   provider "google" {
     project = var.gcp_project_id
     region  = var.gcp_region
   }

== REQUIRED VARIABLES ==
2. Always declare these in variables.tf:
   - gcp_project_id (default = "")
   - gcp_region     (default = "us-central1")
   - project_name
   - environment
   - machine_type
   - ssh_username   (default = "ubuntu")
   - ssh_key_name   (optional, default = "")

== COMPUTE ENGINE ==
3. Use resource "google_compute_instance":
   - machine_type = var.machine_type
   - boot_disk { initialize_params { image = "ubuntu-os-cloud/ubuntu-2204-lts" } }
   - network_interface { network = "default"  access_config {} }
   - tags = ["http-server", "https-server", "allow-ssh"]
   - Name pattern: {project_name}-{environment}-app-{count.index}
   - metadata: Set "ssh-keys" if var.ssh_key_name is provided.

== FIREWALL ==
4. Create a google_compute_firewall if needed, or rely on default network allowing port 80/443/22.

== MANAGED DATABASE ==
5. For SQL: use "google_sql_database_instance".

== CLOUD STORAGE ==
6. If storage_needs = true:
   - resource "google_storage_bucket" with location = var.gcp_region

== STARTUP SCRIPT ==
7. Provide metadata_startup_script on the compute instance:
   - #!/bin/bash, set -e
   - Bash shell variables (APP_DIR, ENV_FILE) MUST be written as `$${VAR_NAME}` so Terraform renders them as `${VAR_NAME}` for the shell
   - Install deps, clone repo, write .env with Terraform variables, start app with systemd
   - Use Terraform interpolation for setup (e.g., `${var.my_var}`)

== SECRET HANDLING ==
8. Secret env vars default to "" in variables.tf and are written to .env as placeholders.

== OUTPUTS ==
9. Output: Compute Engine IPs, DB connection, Storage URL. The 'sensitive' argument on an output MUST be a static boolean (true or false). NEVER use a variable expression like sensitive = (var.x == "foo").

RETURN ONLY valid JSON: {"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}
"""

    def __init__(self) -> None:
        self.llm_service = AsyncLLMService()

    # ── Public API ─────────────────────────────────────────────────────────────

    async def generate_terraform(self, params: Dict[str, Any]) -> TerraformBundle:
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        if not isinstance(params, dict):
            params = {}

        # Ensure expected collection types
        for k in ("detected_services", "iam_services", "env_var_groups"):
            if k in params and not isinstance(params[k], dict):
                params[k] = {}
        for k in ("ports", "dependencies", "ssh_allowed_cidrs", "required_env_vars"):
            if k in params and not isinstance(params[k], list):
                params[k] = []

        # Select system prompt based on provider
        provider = str(params.get("cloud_provider", "aws")).lower()
        
        if provider == "digitalocean":
            user_prompt = self._build_do_prompt(params)
            system_prompt = self._DO_SYSTEM
        elif provider == "gcp":
            user_prompt = self._build_gcp_prompt(params)
            system_prompt = self._GCP_SYSTEM
        else:
            user_prompt = self._build_prompt(params)
            system_prompt = self._SYSTEM

        session_id = params.get("session_id", "unknown_mcp_session")
        user_id = params.get("user_id")
        username = params.get("username")

# Top-level trace for the entire TF generation pipeline
        pipeline_trace = langfuse_service.create_trace(
            name="Terraform Pipeline",
            session_id=session_id,
            user_id=user_id,
            username=username,
            input={
                "params": {k: v for k, v in params.items() if k != "readme_context"},
                "prompt_length": len(user_prompt),
            },
        )

        # ── Pre-generation: gather live Terraform Registry context via MCP ──
        mcp_context = ""
        if config.ENABLE_TERRAFORM_MCP:
            try:
                mcp_context = await mcp_manager.gather_registry_context(
                    user_prompt, session_id=session_id
                )
                if mcp_context:
                    logger.info(
                        "[%s] MCP registry context gathered (%d chars)",
                        session_id,
                        len(mcp_context),
                    )
            except Exception as e:
                logger.warning(
                    "[%s] MCP pre-generation context gathering failed: %s — continuing without.",
                    session_id,
                    e,
                )

        if mcp_context:
            user_prompt = (
                "LIVE TERRAFORM REGISTRY CONTEXT (from registry.terraform.io):\n"
                f"{mcp_context}\n\n"
                "Use the above registry data to ensure correct provider version constraints\n"
                "and accurate resource argument names in the generated code.\n\n"
                + user_prompt
            )

        # 2. Call LLM
        bundle = await self._call(
            user_prompt,
            system=system_prompt,
            session_id=session_id,
            user_id=user_id,
            username=username,
        )

        # 3. Generate GitHub workflow
        bundle.github_workflow_yaml = self._generate_workflow(session_id=session_id)

        # 4. Post-process async
        result = await self._post_process_async(
            bundle,
            session_id=session_id,
            user_id=user_id,
            username=username,
        )

        # Record final TF files on the pipeline trace
        if pipeline_trace:
            try:
                pipeline_trace.update(
                    output={
                        "main_tf": result.main_tf[:5000],
                        "variables_tf": result.variables_tf[:3000],
                        "outputs_tf": result.outputs_tf[:2000],
                        "has_workflow": bool(result.github_workflow_yaml),
                        "validation_notes": getattr(result, "validation_notes", None),
                    }
                )
            except Exception:
                pass

        return result

    async def refine_terraform(
        self,
        base_request: str,
        current_code: Dict[str, Any],
        feedback: str,
        readme_context: str = "",
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> TerraformBundle:
        prompt = (
            f"README context:\n{readme_context}\n\n"
            f"Original request:\n{base_request}\n\n"
            f"Feedback to apply:\n{feedback}\n\n"
            f"Current Terraform:\n{json.dumps(current_code, indent=2)}\n\n"
            "Apply all feedback. Return JSON: {main_tf, variables_tf, outputs_tf}."
        )
        return await self._call(prompt, session_id=session_id, user_id=user_id, username=username)

    async def diagnose_error(
        self,
        error_msg: str,
        terraform_code: dict,
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> dict:
        system = (
            "You are a Senior AWS Cloud Architect diagnosing a Terraform deployment failure.\n"
            "Return ONLY JSON:\n"
            '{"diagnosis": str, "action_type": "manual_action"|"auto_fix", '
            '"suggested_fix": str, "confidence": float}'
        )
        user = f"ERROR:\n{error_msg}\n\nTERRAFORM CODE:\n{json.dumps(terraform_code, indent=2)}"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        trace = langfuse_service.create_trace(
            name="Diagnose Error",
            session_id=session_id,
            user_id=user_id,
            username=username,
            input=messages,
        )

        try:
            raw = await self.llm_service.chat_completion(
                messages=messages,
                temperature=0.1, response_format={"type": "json_object"},
                _trace=trace,
            )
            if trace:
                try:
                    trace.update(output=raw[:10000])
                except Exception:
                    pass
            return json.loads(raw)
        except Exception as e:
            logger.error("diagnose_error failed: %s", e)
            fallback = {
                "diagnosis": "Failed to analyze error.",
                "action_type": "manual_action",
                "suggested_fix": "Check AWS IAM permissions and security group rules.",
                "confidence": 0.0,
            }
            if trace:
                try:
                    trace.update(output=json.dumps(fallback), level="ERROR", status_message=str(e))
                except Exception:
                    pass

            return fallback

    async def chat_about_plan(
        self,
        context: str,
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> str:
        messages = [
            {"role": "system", "content": (
                "You are a helpful AWS Terraform expert. Answer questions about Terraform plans "
                "concisely using AWS-native terminology."
            )},
            {"role": "user", "content": context},
        ]

        trace = langfuse_service.create_trace(
            name="Chat About Plan",
            session_id=session_id,
            user_id=user_id,
            username=username,
            input=messages,
        )

        result = await self.llm_service.chat_completion(
            messages=messages,
            temperature=0.3, max_tokens=2000,
            _trace=trace,
        )

        if trace:
            try:
                trace.update(output=result[:10000])
            except Exception:
                pass

        return result

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, p: Dict[str, Any]) -> str:
        is_prod        = str(p.get("environment", "dev")).lower() in ("prod", "production")
        github_owner   = p.get("github_owner", "")
        github_repo    = p.get("github_repo", "")
        project_name   = p.get("project_name") or github_repo or "app"
        region         = p.get("aws_region") or p.get("region") or "us-east-1"
        instance_type  = p.get("instance_type") or ("t3.small" if is_prod else "t3.micro")
        instance_count = int(p.get("instance_count", 1) or 1)
        storage_gb     = p.get("storage_size_gb", 8) or 8
        storage_type   = p.get("storage_type") or "gp3"
        os_image       = p.get("os_image") or "ubuntu-jammy-22.04"
        has_db     = p.get("has_database", False)
        db_type    = p.get("database_type", "none")
        db_hosting = p.get("database_hosting_model", "managed_cloud")
        has_cache  = p.get("has_cache", False)
        has_alb    = p.get("use_alb", False) or (is_prod and instance_count > 1)
        has_bkt    = p.get("storage_needs", False)
        use_asg    = p.get("use_asg", False)
        monitoring = p.get("enable_monitoring", True)

        ssh_cidrs = ", ".join(p.get("ssh_allowed_cidrs") or []) or "MISSING — required, never 0.0.0.0/0"

        # Env vars block
        env_lines = [
            f"  - {ev.get('name')} [{ev.get('category','other')}]: {ev.get('description','')} {'(secret)' if ev.get('is_secret') else ''}"
            for ev in (p.get("required_env_vars") or []) if isinstance(ev, dict)
        ] + [
            f"  - {ev.get('name')} [optional]: {ev.get('description','')}"
            for ev in (p.get("optional_env_vars") or []) if isinstance(ev, dict)
        ]
        env_block = "\n".join(env_lines) or "  None specified — detect from README context."

        # Ports block
        ports_block = "\n".join(
            f"  - {e.get('port')}/{e.get('protocol','tcp')} from {e.get('source_cidr','0.0.0.0/0')} ({e.get('description','')})"
            for e in (p.get("ports") or []) if isinstance(e, dict)
        ) or "  - 80/tcp public (HTTP)\n  - 443/tcp public (HTTPS)"

        # Warnings block
        warn_block = "\n".join(
            f"  [{w.get('severity','warning').upper()}] {w.get('message','')} — {w.get('recommendation','')}"
            for w in (p.get("infrastructure_warnings") or []) if isinstance(w, dict)
        ) or "  None"

        # Runtime services block
        runtime_block = "\n".join(
            f"  - {s.get('name')} port={s.get('port')} cmd={s.get('start_command','')}"
            for s in (p.get("runtime_services") or []) if isinstance(s, dict)
        ) or "  - Main app only"

        readme_ctx = (p.get("readme_context") or "")[:5000] or "Not available — use conservative AWS defaults."

        return f"""
PROVIDER: AWS
PROJECT: {project_name}  (github.com/{github_owner}/{github_repo})
ENVIRONMENT: {p.get('environment', 'dev').upper()}

README CONTEXT (source of truth for startup script and env vars):
{readme_ctx}

STACK:
  Language/Framework : {p.get('language', 'Not specified')}
  Database           : {'YES — ' + db_type + ' (' + db_hosting + ')' if has_db else 'None'}
  Cache              : {'YES — ' + str(p.get('cache_type','')) if has_cache else 'None'}
  Frontend           : {'YES — ' + str(p.get('frontend_type','')) + ' via ' + str(p.get('frontend_served_by','')) if p.get('has_frontend') else 'None'}
  Websockets         : {'YES — ' + str(p.get('websocket_library','')) if p.get('has_websockets') else 'None'}
  Docker             : {'YES' if p.get('has_docker') else 'NO (install directly on EC2)'}
  Background Jobs    : {'YES — ' + str(p.get('background_job_description','')) if p.get('background_jobs') else 'None'}
  File Storage       : {'YES — ' + str(p.get('storage_description','')) if has_bkt else 'None'}
  Process Manager    : {p.get('process_manager', 'auto-detect from language')}

AWS INFRASTRUCTURE:
  aws_region       : {region}
  aws_az           : {p.get('aws_az') or region + 'a'}
  instance_type    : {instance_type}
  instance_count   : {instance_count}
  disk             : {int(storage_gb)}GB {storage_type}
  vpc_cidr         : {p.get('vpc_cidr', '10.0.0.0/16')}
  ssh_allowed_cidrs: {ssh_cidrs}
  ssh_username     : {p.get('ssh_username', 'ubuntu')}
  os_image         : {os_image}
  ssh_key_name     : {p.get('ssh_key_name') or ''}

SECURITY GROUP PORTS:
{ports_block}

DATABASE:
  type        : {db_type}
  hosting     : {db_hosting}
  instance_class  : {(p.get('rds_config') or {}).get('instance_class') or ('db.t3.small' if is_prod else 'db.t3.micro')}
  multi_az        : {is_prod}
  allocated_storage: {(p.get('rds_config') or {}).get('allocated_storage') or 20}

CACHE:
  instance_class: {(p.get('cache_config') or {}).get('instance_class') or ('cache.t3.small' if is_prod else 'cache.t3.micro')}

MONITORING:
  alert_email       : {p.get('alert_email', '')}
  custom_domain     : {p.get('custom_domain', '')}

REQUIRED ENV VARS (each must become a Terraform variable and be injected into startup .env):
{env_block}

RUNTIME SERVICES (all must be started in startup script; security group must open their ports):
{runtime_block}

INFRASTRUCTURE WARNINGS (must be respected):
{warn_block}

GENERATION CHECKLIST:
  include_rds              : {has_db and db_hosting == 'managed_cloud'}
  include_elasticache      : {has_cache}
  include_s3               : {has_bkt and p.get('storage_provider','none') == 's3'}
  include_alb              : {has_alb}
  include_asg              : {use_asg}
  include_cloudwatch       : {monitoring}
  include_secrets_manager  : {p.get('use_secrets_manager', False)}
  include_route53          : {bool(p.get('custom_domain'))}

SECRETS HANDLING:
  use_secrets_manager: {p.get('use_secrets_manager', False)}
  If use_secrets_manager is true:
    - Generate aws_secretsmanager_secret + aws_secretsmanager_secret_version for each is_secret var
    - IAM policy granting EC2 secretsmanager:GetSecretValue
    - Startup script fetches secrets at boot via 'aws secretsmanager get-secret-value'
  If use_secrets_manager is false (DEFAULT for dev):
    - Write ALL env vars (secret and non-secret) directly to .env using Terraform var interpolation
    - Secret vars will have default="" in variables.tf
    - User updates .env on the instance after deploy with real values
    - DO NOT generate any aws_secretsmanager resources

is_secret vars from README:
{chr(10).join('  - ' + ev.get('name','') for ev in (p.get('required_env_vars') or []) if isinstance(ev, dict) and ev.get('is_secret')) or '  None detected'}

STARTUP SCRIPT MUST:
  1. #!/bin/bash + set -e + exec > /var/log/user-data.log 2>&1
  2. Install Node.js via NodeSource: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs
  3. Clone: https://github.com/{github_owner}/{github_repo}
  4. Install: {p.get('install_command') or 'npm install'}
  5. Build:   {p.get('build_command') or 'skip if not needed'}
  6. Write ALL env vars to .env using cat heredoc with Terraform var interpolation
  7. Create systemd service with HARDCODED paths (WorkingDirectory=/home/ubuntu/app)
  8. systemctl daemon-reload + enable + start

Return ONLY JSON: {{"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}}
"""

    # ── Internals ──────────────────────────────────────────────────────────────

    def _generate_workflow(self, session_id: str = None) -> str:
        """
        Generate a GitHub Actions CI/CD workflow (deploy.yml)
        for deploying Terraform to AWS.
        """
        return """name: Deploy Infrastructure

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  AWS_REGION: ${{ secrets.AWS_REGION }}

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init

      - name: Terraform Plan
        run: terraform plan -out=tfplan

      - name: Terraform Apply
        if: github.ref == 'refs/heads/main'
        run: terraform apply -auto-approve tfplan
"""

    async def _call(self, user_prompt: str, system: str = None, session_id: str = None, user_id: str = None, username: str = None) -> TerraformBundle:
        messages = [
            {"role": "system", "content": system or self._SYSTEM},
            {"role": "user",   "content": user_prompt},
        ]

        trace = langfuse_service.create_trace(
            name="Terraform Generation",
            session_id=session_id,
            user_id=user_id,
            username=username,
            input=messages,
        )

        raw = await self.llm_service.chat_completion(
            messages=messages,
            temperature=0.1, max_tokens=32768,
            response_format={"type": "json_object"}, timeout=120,
            _trace=trace,
        )

        if trace:
            try:
                trace.update(output=raw[:10000])
            except Exception:
                pass

        data = json.loads(raw)
        for key in ("main_tf", "variables_tf", "outputs_tf"):
            val = data.get(key, "")
            data[key] = json.dumps(val, indent=2) if isinstance(val, dict) else str(val or "")
        bundle = TerraformBundle(**data)
        return self._sanitize_bundle(bundle)

    # ── DO Prompt builder ──────────────────────────────────────────────────────

    def _build_do_prompt(self, p: Dict[str, Any]) -> str:
        """Build the DigitalOcean-specific Terraform generation prompt."""
        is_prod       = str(p.get("environment", "dev")).lower() in ("prod", "production")
        github_owner  = p.get("github_owner", "")
        github_repo   = p.get("github_repo", "")
        project_name  = p.get("project_name") or github_repo or "app"
        region        = p.get("do_region") or p.get("region") or "nyc3"
        droplet_size  = p.get("droplet_size") or ("s-1vcpu-2gb" if is_prod else "s-1vcpu-1gb")
        instance_count = int(p.get("instance_count", 1) or 1)

        has_db     = p.get("has_database", False)
        db_type    = p.get("database_type", "none")
        db_hosting = p.get("database_hosting_model", "managed_cloud")
        has_cache  = p.get("has_cache", False)
        has_lb     = p.get("use_alb", False) or (is_prod and instance_count > 1)
        has_bkt    = p.get("storage_needs", False)
        use_asg    = p.get("use_asg", False)

        env_lines = [
            f"  - {ev.get('name')} [{ev.get('category','other')}]: {ev.get('description','')} {'(secret)' if ev.get('is_secret') else ''}"
            for ev in (p.get("required_env_vars") or []) if isinstance(ev, dict)
        ] + [
            f"  - {ev.get('name')} [optional]: {ev.get('description','')}"
            for ev in (p.get("optional_env_vars") or []) if isinstance(ev, dict)
        ]
        env_block = "\n".join(env_lines) or "  None specified."

        ports_block = "\n".join(
            f"  - {e.get('port')}/{e.get('protocol','tcp')} ({e.get('description','')})"
            for e in (p.get("ports") or []) if isinstance(e, dict)
        ) or "  - 80/tcp public (HTTP)\n  - 443/tcp public (HTTPS)"

        readme_ctx = (p.get("readme_context") or "")[:5000] or "Not available."
        alert_email = p.get("alert_email", "")
        ssh_key    = p.get("ssh_key_name", "")
        custom_domain = p.get("custom_domain", "")
        hc_path    = (p.get("autoscaling_config") or {}).get("health_check_path", "/")
        domain_line = f"  custom_domain : {custom_domain}" if custom_domain else "  custom_domain : (none)"

        return f"""
PROVIDER: DigitalOcean
PROJECT: {project_name}  (github.com/{github_owner}/{github_repo})
ENVIRONMENT: {p.get('environment', 'dev').upper()}

README CONTEXT (source of truth for startup script and env vars):
{readme_ctx}

STACK:
  Language/Framework : {p.get('language', 'Not specified')}
  Database           : {'YES - ' + db_type + ' (' + db_hosting + ')' if has_db else 'None'}
  Cache              : {'YES - Redis (DO Managed)' if has_cache else 'None'}
  File Storage       : {'YES - DO Spaces' if has_bkt else 'None'}
  Background Jobs    : {'YES' if p.get('background_jobs') else 'None'}
  Process Manager    : {p.get('process_manager', 'auto-detect')}

DIGITALOCEAN INFRASTRUCTURE:
  do_region        : {region}
  droplet_size     : {droplet_size}
  droplet_image    : ubuntu-22-04-x64
  instance_count   : {instance_count}
  ssh_key_name     : {ssh_key or 'REQUIRED - must exist in DO account'}
  alert_email      : {alert_email or '(none)'}
{domain_line}
  load_balancer    : {'YES - DO LB, health check: ' + hc_path if has_lb else 'NO'}
  storage (spaces) : {'YES' if has_bkt else 'NO'}
  do_spaces_bucket : {p.get('do_spaces_bucket', '') or '(auto-generated)'}
  use_asg          : {use_asg}
  enable_multi_az  : {p.get('enable_multi_az', False)}

PORTS TO EXPOSE:
{ports_block}

ENVIRONMENT VARIABLES:
{env_block}

KEY CONSTRAINTS:
- NEVER hardcode the DO token — always var.do_token
- ALWAYS look up SSH key via data "digitalocean_ssh_key" {{ name = var.ssh_key_name }}
- Use count = {instance_count} for digitalocean_droplet resources
- Tag all resources: project = {project_name}, environment = {p.get('environment', 'dev')}
- Use var.do_region for ALL region arguments (Droplet, DB, Spaces, LB)
- Install command : {p.get('install_command') or 'auto-detect'}
- Start command   : {p.get('app_start_command') or 'auto-detect'}

WORKFLOW:
  1. Clone repo from https://github.com/{github_owner}/{github_repo}
  2. Install deps: {p.get('install_command') or 'auto-detect'}
  3. Write env vars to .env using Terraform variable interpolation
  4. Create systemd service (HARDCODED paths: WorkingDirectory=/home/ubuntu/app)
  5. systemctl daemon-reload + enable + start

Return ONLY JSON: {{"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}}
"""

    # ── GCP Prompt builder ──────────────────────────────────────────────────────

    def _build_gcp_prompt(self, p: Dict[str, Any]) -> str:
        """Build the Google Cloud Platform-specific Terraform generation prompt."""
        is_prod       = str(p.get("environment", "dev")).lower() in ("prod", "production")
        github_owner  = p.get("github_owner", "")
        github_repo   = p.get("github_repo", "")
        project_name  = p.get("project_name") or github_repo or "app"
        region        = p.get("gcp_region") or p.get("region") or "us-central1"
        machine_type  = p.get("machine_type") or ("e2-small" if is_prod else "e2-micro")
        instance_count= int(p.get("instance_count", 1) or 1)

        has_db     = p.get("has_database", False)
        db_type    = p.get("database_type", "none")
        db_hosting = p.get("database_hosting_model", "managed_cloud")
        has_cache  = p.get("has_cache", False)

        env_lines = [
            f"  - {ev.get('name')} [{ev.get('category','other')}]: {ev.get('description','')} {'(secret)' if ev.get('is_secret') else ''}"
            for ev in (p.get("required_env_vars") or []) if isinstance(ev, dict)
        ] + [
            f"  - {ev.get('name')} [optional]: {ev.get('description','')}"
            for ev in (p.get("optional_env_vars") or []) if isinstance(ev, dict)
        ]
        env_block = "\n".join(env_lines) or "  None specified."

        ports_block = "\n".join(
            f"  - {e.get('port')}/{e.get('protocol','tcp')} ({e.get('description','')})"
            for e in (p.get("ports") or []) if isinstance(e, dict)
        ) or "  - 80/tcp public (HTTP)\n  - 443/tcp public (HTTPS)"

        readme_ctx = (p.get("readme_context") or "")[:5000] or "Not available."
        
        return f"""
PROVIDER: Google Cloud Platform (GCP)
PROJECT: {project_name}  (github.com/{github_owner}/{github_repo})
ENVIRONMENT: {p.get('environment', 'dev').upper()}

README CONTEXT (source of truth for startup script and env vars):
{readme_ctx}

GCP INFRASTRUCTURE:
  gcp_region       : {region}
  machine_type     : {machine_type}
  instance_count   : {instance_count}
  database         : {'YES - ' + db_type + ' (' + db_hosting + ')' if has_db else 'None'}
  cache            : {'YES - Cloud Memorystore' if has_cache else 'None'}

PORTS TO EXPOSE:
{ports_block}

ENVIRONMENT VARIABLES:
{env_block}

WORKFLOW:
  1. Clone repo from https://github.com/{github_owner}/{github_repo}
  2. Install deps: {p.get('install_command') or 'auto-detect'}
  3. Write env vars to .env using Terraform variable interpolation
  4. Create systemd service (HARDCODED paths: WorkingDirectory=/home/ubuntu/app)
  5. systemctl daemon-reload + enable + start

Return ONLY JSON: {{"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}}
"""

    # ── Post-generation sanitizer ─────────────────────────────────────────────

    @staticmethod
    def _sanitize_bundle(bundle: TerraformBundle) -> TerraformBundle:
        """
        Strip every known-bad pattern from generated HCL BEFORE terraform validate.

        Fix index:
          FIX 1  — sensitive = (var.x ...) in outputs     → terraform init fails
          FIX 2  — aws_default_vpc/subnet resource         → write resource, forbidden
          FIX 3  — aws_vpc_security_group_*_rule           → cidr_blocks not supported
          FIX 4  — confirmation_timeout_on_create in SNS   → removed in provider v4+
          FIX 5  — SNS subscription missing count guard    → apply fails on blank email
          FIX 6  — key_name = var.key_pair_name directly   → InvalidKeyPair on blank value
          FIX 7  — ami_id variable                         → replaced by data source
          FIX 8  — ssh_allowed_cidrs default 0.0.0.0/0     → security risk
          FIX 9  — instance_type default t2.micro          → InvalidParameterCombination
          FIX 10 — key_pair_name default "REPLACE_ME"      → InvalidKeyPair at apply
          FIX 11 — alert_email default "REPLACE_ME@..."    → SNS invalid endpoint at apply
          FIX 12 — missing provider/terraform block        → wrong region/version
          FIX 13 — single-line terraform block             → terraform fmt rejects it
        """
        import re

        main      = bundle.main_tf
        variables = bundle.variables_tf
        outputs   = bundle.outputs_tf

        # ══════════════════════════════════════════════════════════════════
        # outputs.tf fixes
        # ══════════════════════════════════════════════════════════════════

        # FIX 1: Remove any sensitive= that uses a variable expression.
        # Catches all of:
        #   sensitive = (var.key_pair_name == "" || var.key_pair_name == "REPLACE_ME")
        #   sensitive = var.x
        #   sensitive = (var.x)
        outputs = re.sub(
            r'\s*sensitive\s*=\s*(?:\()?(?:var\.\w+|\(var\.[^)]+\))[^,\n}]*(?:\))?',
            '\n  sensitive = false',
            outputs,
        )
        # Belt-and-suspenders: catch any remaining bare var. references in sensitive=
        outputs = re.sub(r'\s*sensitive\s*=\s*var\.\w+', '\n  sensitive = false', outputs)

        # ══════════════════════════════════════════════════════════════════
        # main.tf fixes
        # ══════════════════════════════════════════════════════════════════

        # FIX 2: aws_default_vpc/subnet write resources → data sources
        main = re.sub(
            r'resource\s+"aws_default_vpc"\s+"\w+"\s*\{[^}]*\}',
            'data "aws_vpc" "default" {\n  default = true\n}',
            main, flags=re.DOTALL,
        )
        main = re.sub(
            r'resource\s+"aws_default_subnet"\s+"\w+"\s*\{[^}]*\}',
            'data "aws_subnet" "default" {\n  vpc_id         = data.aws_vpc.default.id\n  default_for_az = true\n}',
            main, flags=re.DOTALL,
        )
        main = re.sub(r'aws_default_vpc\.\w+\.id',    'data.aws_vpc.default.id',    main)
        main = re.sub(r'aws_default_subnet\.\w+\.id', 'data.aws_subnet.default.id', main)

        # FIX 3: aws_vpc_security_group_*_rule → not allowed to use cidr_blocks
        # Remove the resource entirely; LLM must use aws_security_group with inline blocks
        main = re.sub(
            r'resource\s+"aws_vpc_security_group_(?:ingress|egress)_rule"\s+"\w+"\s*\{[^}]*\}',
            '# REMOVED: use aws_security_group with inline ingress/egress blocks',
            main, flags=re.DOTALL,
        )

        # FIX 4: confirmation_timeout_on_create removed in AWS provider v4+
        main = re.sub(r'\s*confirmation_timeout_on_create\s*=\s*\d+', '', main)

        # FIX 5: SNS topic subscription must have count guard for empty/placeholder email
        # Prevents: InvalidParameter: Invalid parameter: Endpoint
        def _add_sns_count_guard(m: re.Match) -> str:
            block = m.group(0)
            if 'count' not in block:
                block = block.replace(
                    '{',
                    '{\n  count = (var.alert_email != "" && var.alert_email != "REPLACE_ME@example.com") ? 1 : 0',
                    1,
                )
            return block

        main = re.sub(
            r'resource\s+"aws_sns_topic_subscription"\s+"\w+"\s*\{[^}]+\}',
            _add_sns_count_guard,
            main, flags=re.DOTALL,
        )

        # FIX 6: key_name must use null when key_pair_name is blank or placeholder
        # Prevents: InvalidKeyPair.NotFound: The key pair 'REPLACE_ME' does not exist
        main = re.sub(
            r'key_name\s*=\s*var\.key_pair_name',
            'key_name = (var.key_pair_name != "" && var.key_pair_name != "REPLACE_ME") ? var.key_pair_name : null',
            main,
        )

        # FIX 12: Ensure terraform + provider block exists
        if 'required_providers' not in main:
            provider_block = (
                'terraform {\n'
                '  required_providers {\n'
                '    aws = {\n'
                '      source  = "hashicorp/aws"\n'
                '      version = "~> 5.0"\n'
                '    }\n'
                '  }\n'
                '}\n\n'
                'provider "aws" {\n'
                '  region = var.aws_region\n'
                '}\n\n'
            )
            main = provider_block + main
        elif 'provider "aws"' not in main:
            main = main + '\nprovider "aws" {\n  region = var.aws_region\n}\n'

        # FIX 13: Reformat single-line terraform { required_providers { ... } } blocks
        # The LLM sometimes generates the entire terraform block on one line which terraform fmt rejects.
        single_line_tf = re.search(
            r'^(\s*)terraform\s*\{\s*required_providers\s*\{\s*aws\s*=\s*\{\s*'
            r'source\s*=\s*"([^"]*)"\s*,?\s*version\s*=\s*"([^"]*)"\s*\}\s*\}\s*\}',
            main, flags=re.MULTILINE,
        )
        if single_line_tf:
            src = single_line_tf.group(2)
            ver = single_line_tf.group(3)
            replacement = (
                'terraform {\n'
                '  required_providers {\n'
                '    aws = {\n'
                f'      source  = "{src}"\n'
                f'      version = "{ver}"\n'
                '    }\n'
                '  }\n'
                '}'
            )
            main = main[:single_line_tf.start()] + replacement + main[single_line_tf.end():]

        # ══════════════════════════════════════════════════════════════════
        # variables.tf fixes
        # ══════════════════════════════════════════════════════════════════

        # FIX 7: Remove obsolete ami_id variable (data source used instead)
        variables = re.sub(
            r'variable\s+"ami_id"\s*\{[^}]*\}\s*',
            '', variables, flags=re.DOTALL,
        )

        # FIX 8: ssh_allowed_cidrs default must be [] not ["0.0.0.0/0"]
        variables = re.sub(
            r'(variable\s+"ssh_allowed_cidrs"[^{]*\{[^}]*default\s*=\s*)\[\s*"0\.0\.0\.0/0"\s*\]',
            r'\1[]',
            variables, flags=re.DOTALL,
        )

        # FIX 9: instance_type default must be t3.micro not t2.micro
        variables = re.sub(
            r'(variable\s+"instance_type"[^{]*\{[^}]*default\s*=\s*)"t2\.micro"',
            r'\1"t3.micro"',
            variables, flags=re.DOTALL,
        )

        # FIX 10: key_pair_name default must be "" not "REPLACE_ME"
        # Prevents InvalidKeyPair.NotFound when user hasn't set a key pair
        variables = re.sub(
            r'(variable\s+"key_pair_name"[^{]*\{[^}]*default\s*=\s*)"REPLACE_ME"',
            r'\1""',
            variables, flags=re.DOTALL,
        )

        # FIX 11: alert_email default must be "" not "REPLACE_ME@example.com"
        # Prevents SNS InvalidParameter: Invalid parameter: Endpoint at apply time
        variables = re.sub(
            r'(variable\s+"alert_email"[^{]*\{[^}]*default\s*=\s*)"REPLACE_ME@example\.com"',
            r'\1""',
            variables, flags=re.DOTALL,
        )

        bundle.main_tf      = main
        bundle.variables_tf = variables
        bundle.outputs_tf   = outputs
        logger.debug("_sanitize_bundle: all 12 fixes applied successfully.")
        return bundle

    async def validate_with_mcp(self, bundle: TerraformBundle) -> ValidationResult:
        """
        Post-generation validation using the Terraform Registry MCP server.
        Delegates to mcp_service.mcp_manager.validate_terraform().
        """
        return await mcp_manager.validate_terraform(bundle.main_tf)

    async def _validate_with_mcp_legacy(self, bundle: TerraformBundle) -> ValidationResult:
        """
        [LEGACY — kept for reference only. Use validate_with_mcp() above.]
        Old inline implementation; replaced by delegation to mcp_manager.
        """
        if not config.ENABLE_TERRAFORM_MCP:
            logger.debug("validate_with_mcp: ENABLE_TERRAFORM_MCP=False — skipping.")
            return ValidationResult(ok=True, notes=["MCP validation skipped (disabled)."])

        notes: List[str] = []
        ok = True
        registry_context: Dict[str, Any] = {}

        try:
            from app.services.mcp_service import mcp_manager

            tools = await mcp_manager.list_tools("terraform", config.TERRAFORM_MCP_SERVER)
            if not tools:
                logger.warning("validate_with_mcp: No MCP tools available — skipping registry check.")
                return ValidationResult(ok=True, notes=["MCP validation skipped (no tools available)."])

            tool_names = {t["name"] for t in tools}
            logger.info("validate_with_mcp: %d MCP tools available", len(tools))

            # ── Check 1: Latest provider version ──────────────────────────────
            if "get_latest_provider_version" in tool_names:
                try:
                    result = await asyncio.wait_for(
                        mcp_manager.call_tool_by_name(
                            "get_latest_provider_version",
                            {"namespace": "hashicorp", "name": "aws"},
                        ),
                        timeout=15.0,
                    )
                    version_info = str(result.content) if result else ""
                    registry_context["aws_provider_version"] = version_info
                    notes.append(f"Registry: hashicorp/aws provider — {version_info[:120]}")
                    logger.info("validate_with_mcp: provider version check OK")
                except asyncio.TimeoutError:
                    logger.warning("validate_with_mcp: provider version check timed out")
                    notes.append("Registry: provider version check timed out.")
                except Exception as e:
                    logger.warning("validate_with_mcp: provider version check failed: %s", e)
                    notes.append(f"Registry: provider version check failed ({e}).")

            # ── Check 2: Verify resource types + collect registry docs ─────────
            if bundle.main_tf:
                import re
                resource_types = list(set(re.findall(r'resource\s+"(aws_[\w]+)"', bundle.main_tf)))
                resource_docs: Dict[str, str] = {}

                for rtype in resource_types[:8]:
                    if "search_providers" in tool_names:
                        try:
                            search_result = await asyncio.wait_for(
                                mcp_manager.call_tool_by_name(
                                    "search_providers",
                                    {
                                        "provider_name": "aws",
                                        "provider_namespace": "hashicorp",
                                        "service_slug": rtype,
                                        "provider_document_type": "resources",
                                    },
                                ),
                                timeout=15.0,
                            )
                            if search_result and search_result.content:
                                raw_search = str(search_result.content)
                                doc_id_match = re.search(r'"provider_doc_id"\s*:\s*"?(\d+)"?', raw_search)
                                if doc_id_match and "get_provider_details" in tool_names:
                                    doc_id = doc_id_match.group(1)
                                    try:
                                        detail_result = await asyncio.wait_for(
                                            mcp_manager.call_tool_by_name(
                                                "get_provider_details",
                                                {"provider_doc_id": doc_id},
                                            ),
                                            timeout=15.0,
                                        )
                                        if detail_result and detail_result.content:
                                            resource_docs[rtype] = str(detail_result.content)[:3000]
                                            notes.append(f"Registry: ✅ {rtype} — docs fetched.")
                                        else:
                                            resource_docs[rtype] = raw_search[:1000]
                                            notes.append(f"Registry: ✅ {rtype} — found in registry.")
                                    except Exception:
                                        resource_docs[rtype] = raw_search[:1000]
                                        notes.append(f"Registry: ✅ {rtype} — found (detail fetch failed).")
                                else:
                                    resource_docs[rtype] = raw_search[:1000]
                                    notes.append(f"Registry: ✅ {rtype} — found in registry.")
                                logger.info("validate_with_mcp: %s → found", rtype)
                            else:
                                notes.append(f"Registry: ⚠️  {rtype} — not found (may need renaming).")
                                ok = False
                                logger.warning("validate_with_mcp: %s → NOT FOUND", rtype)
                        except asyncio.TimeoutError:
                            logger.warning("validate_with_mcp: search timed out for %s", rtype)
                            notes.append(f"Registry: {rtype} — check timed out.")
                        except Exception as e:
                            logger.warning("validate_with_mcp: search failed for %s: %s", rtype, e)
                            notes.append(f"Registry: {rtype} — search error ({e}).")

                if resource_docs:
                    registry_context["resource_docs"] = resource_docs

        except Exception as e:
            logger.error("validate_with_mcp: unexpected error: %s", e, exc_info=True)
            notes.append(f"MCP validation error: {e}")
            ok = True  # Non-blocking

        return ValidationResult(ok=ok, notes=notes, registry_context=registry_context)

    def _post_process(self, bundle: TerraformBundle) -> TerraformBundle:
        """Run terraform fmt + validate if CLI is available."""
        try:
            subprocess.run(["terraform", "--version"], check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("Terraform CLI not found — skipping fmt/validate.")
            return bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "main.tf").write_text(bundle.main_tf, encoding="utf-8")
            (d / "variables.tf").write_text(bundle.variables_tf, encoding="utf-8")
            (d / "outputs.tf").write_text(bundle.outputs_tf, encoding="utf-8")

            try:
                subprocess.run(["terraform", "fmt"], cwd=tmpdir, check=True, capture_output=True)
                bundle.main_tf      = (d / "main.tf").read_text(encoding="utf-8")
                bundle.variables_tf = (d / "variables.tf").read_text(encoding="utf-8")
                bundle.outputs_tf   = (d / "outputs.tf").read_text(encoding="utf-8")
            except subprocess.CalledProcessError as e:
                logger.warning("terraform fmt failed: %s", e.stderr.decode(errors="replace"))

            try:
                subprocess.run(["terraform", "init", "-backend=false"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["terraform", "validate"], cwd=tmpdir, check=True, capture_output=True)
                logger.info("terraform validate: OK")
            except subprocess.CalledProcessError as e:
                logger.error("terraform validate failed: %s", e.stderr.decode(errors="replace") if e.stderr else "")

        return bundle

    async def _auto_fix_with_mcp(
        self,
        bundle: TerraformBundle,
        validation: ValidationResult,
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> TerraformBundle:
        """
        If MCP validation collected registry docs (or found issues), call the LLM
        with that live context so it can patch the Terraform files.
        """
        ctx = validation.registry_context
        if not ctx:
            logger.debug("_auto_fix_with_mcp: no registry context — skipping auto-fix.")
            return bundle

        logger.info("_auto_fix_with_mcp: running LLM auto-fix with registry context.")

        provider_ver  = ctx.get("aws_provider_version", "unknown")
        resource_docs = ctx.get("resource_docs", {})

        docs_block = ""
        for rtype, doc in resource_docs.items():
            docs_block += f"\n### {rtype}\n{doc[:1500]}\n"

        issues_block = "\n".join(
            n for n in validation.notes if "not found" in n or "error" in n.lower()
        ) or "No issues found."

        fix_prompt = f"""\
You are updating Terraform files based on LIVE data fetched from the Terraform Registry.

Hashicorp AWS Provider latest version: {provider_ver}

Registry documentation for resources in this configuration:
{docs_block or 'No documentation available.'}

Validation issues to fix:
{issues_block}

Current Terraform files:
```hcl
# main.tf
{bundle.main_tf}

# variables.tf
{bundle.variables_tf}

# outputs.tf
{bundle.outputs_tf}
```

Instructions:
1. Fix any deprecated or incorrect resource arguments using the registry docs above.
2. Update the required_providers block to use the latest provider version.
3. Correct any resource type names that were flagged as not found.
4. Do NOT change working infrastructure logic — only fix registry-identified issues.
5. Preserve all existing variables and outputs unless they reference incorrect resources.

Return ONLY JSON: {{"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}}
"""
        messages = [
            {"role": "system", "content": self._SYSTEM},
            {"role": "user",   "content": fix_prompt},
        ]

        trace = langfuse_service.create_trace(
            name="Terraform Auto-Fix",
            session_id=session_id,
            user_id=user_id,
            username=username,
            input=messages,
        )

        try:
            raw = await self.llm_service.chat_completion(
                messages=messages,
                temperature=0.05,
                max_tokens=32768,
                response_format={"type": "json_object"},
                timeout=120,
                _trace=trace,
            )
            data = json.loads(raw)
            for key in ("main_tf", "variables_tf", "outputs_tf"):
                val = data.get(key, "")
                data[key] = json.dumps(val, indent=2) if isinstance(val, dict) else str(val or "")

            fixed = TerraformBundle(
                main_tf=data.get("main_tf") or bundle.main_tf,
                variables_tf=data.get("variables_tf") or bundle.variables_tf,
                outputs_tf=data.get("outputs_tf") or bundle.outputs_tf,
                github_workflow_yaml=bundle.github_workflow_yaml,
            )

            if trace:
                try:
                    trace.update(output={
                        "main_tf": fixed.main_tf[:5000],
                        "variables_tf": fixed.variables_tf[:3000],
                        "outputs_tf": fixed.outputs_tf[:2000],
                    })
                except Exception:
                    pass

            logger.info("_auto_fix_with_mcp: auto-fix applied successfully.")
            return fixed

        except Exception as e:
            logger.error("_auto_fix_with_mcp: LLM fix failed (%s) — using original bundle.", e)
            if trace:
                try:
                    trace.update(output={"error": str(e)}, level="ERROR")
                except Exception:
                    pass
            return bundle

    async def _post_process_async(
        self,
        bundle: TerraformBundle,
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> TerraformBundle:
        """
        Full async post-generation pipeline:
          1. terraform fmt  (thread)
          2. terraform validate  (thread)
          3. validate_with_mcp()  — registry check + doc collection
          4. _auto_fix_with_mcp() — LLM fix pass using live registry data (if MCP active)
          5. terraform fmt again on the fixed bundle  (thread, only if step 4 ran)
        """
        bundle = await asyncio.to_thread(self._post_process, bundle)

        if not config.ENABLE_TERRAFORM_MCP:
            return bundle

        validation = await self.validate_with_mcp(
            bundle,
            session_id=session_id,
            user_id=user_id,
            username=username,
        )
        for note in validation.notes:
            logger.info("MCP validation: %s", note)

        has_context = bool(validation.registry_context)
        has_issues  = not validation.ok

        if has_context or has_issues:
            if has_issues:
                logger.warning("MCP registry validation found issues — running auto-fix.")
            else:
                logger.info("MCP registry context available — running auto-fix for best-practice alignment.")

            bundle = await self._auto_fix_with_mcp(
                bundle,
                validation,
                session_id=session_id,
                user_id=user_id,
                username=username,
            )
            bundle = await asyncio.to_thread(self._post_process, bundle)

        return bundle