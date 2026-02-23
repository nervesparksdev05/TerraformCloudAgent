"""llm_generator.py — TerraBot: Multi-cloud Terraform generator powered by Gemini + MCP."""
from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

from app.services import langfuse_service
from app.services.llm_service import LLMService
from app.core import config
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle

logger = get_logger(__name__)


class LLMGenerator:
    """Generate production-grade GCP Terraform files from conversation parameters."""

    _SYSTEM = """\
You are a senior GCP Terraform engineer. Generate complete, production-ready Terraform for Google Cloud.

RULES:
- When "MCP REGISTRY CONTEXT" is provided, strictly adhere to the module versions, resource schemas, and argument structures found in it. This is your source of truth for avoiding syntax errors.
- Never hardcode values — always use var.* in main.tf
- Every variable must have type, description, and a sensible default in variables.tf
- SSH must NEVER allow 0.0.0.0/0 — use var.ssh_allowed_cidrs
- Resource naming: {project_name}-{environment}-{resource_type}
- Startup script: clone repo → install deps → build (if needed) → write .env → start app
- Output every operational value: IPs, URLs, SSH commands, connection strings
- Return ONLY valid JSON: {"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}
"""

    _CICD = """\
Generate a .github/workflows/deploy.yml for Terraform on GCP.
Triggers: push to main (apply), PR to main (plan only).
Auth: echo "$GCP_SA_KEY" | base64 --decode > /tmp/sa_key.json && gcloud auth activate-service-account --key-file=/tmp/sa_key.json
Required secrets: GCP_SA_KEY, GCP_PROJECT_ID. State stored in GCS remote backend.
On PR: post terraform plan as PR comment. On push: terraform apply -auto-approve.
Output ONLY raw YAML — no code fences, no explanation.
"""

    def __init__(self) -> None:
        self.llm_service = LLMService()

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_terraform(self, params: Dict[str, Any], session_id: str = None) -> TerraformBundle:
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
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

        user_prompt = self._build_prompt(params)
        
        # 1. Gather MCP context synchronously
        mcp_context = self._gather_mcp_context_sync(user_prompt, session_id)
        if mcp_context:
            user_prompt += f"\n\n--- MCP REGISTRY CONTEXT ---\n{mcp_context}\n----------------------------"

        bundle = self._call(user_prompt, session_id=session_id)
        bundle.github_workflow_yaml = self._generate_workflow(session_id=session_id)
        return self._post_process(bundle)

    def refine_terraform(
        self,
        base_request: str,
        current_code: Dict[str, Any],
        feedback: str,
        readme_context: str = "",
        session_id: str = None,
    ) -> TerraformBundle:
        prompt = (
            f"README context:\n{readme_context}\n\n"
            f"Original request:\n{base_request}\n\n"
            f"Feedback to apply:\n{feedback}\n\n"
            f"Current Terraform:\n{json.dumps(current_code, indent=2)}\n\n"
            "Apply all feedback. Return JSON: {main_tf, variables_tf, outputs_tf}."
        )
        return self._call(prompt, session_id=session_id)

    def diagnose_error(self, error_msg: str, terraform_code: dict) -> dict:
        system = (
            "You are a Senior GCP Cloud Architect diagnosing a Terraform deployment failure.\n"
            "Return ONLY JSON:\n"
            '{"diagnosis": str, "action_type": "manual_action"|"auto_fix", '
            '"suggested_fix": str, "confidence": float}'
        )
        user = f"ERROR:\n{error_msg}\n\nTERRAFORM CODE:\n{json.dumps(terraform_code, indent=2)}"
        try:
            raw = self.llm_service.chat_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.1, response_format={"type": "json_object"},
            )
            return json.loads(raw)
        except Exception as e:
            logger.error("diagnose_error failed: %s", e)
            return {
                "diagnosis": "Failed to analyze error.",
                "action_type": "manual_action",
                "suggested_fix": "Check GCP console permissions and retry.",
                "confidence": 0.0,
            }

    def chat_about_plan(self, context: str) -> str:
        return self.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": (
                    "You are a helpful GCP Terraform expert. Answer questions about Terraform plans "
                    "concisely using GCP-native terminology."
                )},
                {"role": "user", "content": context},
            ],
            temperature=0.3, max_tokens=2000,
        )

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, p: Dict[str, Any]) -> str:
        is_prod        = str(p.get("environment", "dev")).lower() in ("prod", "production")
        github_owner   = p.get("github_owner", "")
        github_repo    = p.get("github_repo", "")
        project_name   = p.get("project_name") or github_repo or "app"
        region         = p.get("gcp_region") or p.get("region") or "us-central1"
        instance_type  = p.get("instance_type") or ("e2-standard-2" if is_prod else "e2-micro")
        instance_count = int(p.get("instance_count", 1) or 1)
        storage_gb     = p.get("storage_size_gb", 20) or 20
        storage_type   = p.get("storage_type") or "pd-balanced"
        os_image       = p.get("os_image") or "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"

        has_db     = p.get("has_database", False)
        db_type    = p.get("database_type", "none")
        db_hosting = p.get("database_hosting_model", "managed_cloud")
        has_cache  = p.get("has_cache", False)
        has_lb     = p.get("has_load_balancer", False) or (is_prod and instance_count > 1)
        has_bkt    = p.get("storage_needs", False)
        auto_scale = p.get("enable_autoscaling", False)
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

        readme_ctx = (p.get("readme_context") or "")[:5000] or "Not available — use conservative GCP defaults."

        return f"""
PROVIDER: GCP
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
  Docker             : {'YES' if p.get('has_docker') else 'NO (install directly on VM)'}
  Background Jobs    : {'YES — ' + str(p.get('background_job_description','')) if p.get('background_jobs') else 'None'}
  File Storage       : {'YES — ' + str(p.get('storage_description','')) if has_bkt else 'None'}
  Process Manager    : {p.get('process_manager', 'auto-detect from language')}

GCP INFRASTRUCTURE:
  gcp_project_id   : {p.get('gcp_project_id') or config.GCP_PROJECT_ID or '<required — set GCP_PROJECT_ID in .env>'}
  gcp_region       : {region}
  gcp_zone         : {p.get('gcp_zone') or region + '-a'}
  instance_type    : {instance_type}
  instance_count   : {instance_count}
  os_image         : {os_image}
  disk             : {int(storage_gb)}GB {storage_type}
  vpc_cidr         : {p.get('vpc_cidr', '10.0.0.0/16')}
  ssh_allowed_cidrs: {ssh_cidrs}
  ssh_username     : {p.get('ssh_username', 'ubuntu')}

FIREWALL PORTS:
{ports_block}

DATABASE:
  type        : {db_type}
  hosting     : {db_hosting}
  cloud_sql_tier  : {p.get('cloud_sql_tier') or ('db-n1-standard-1' if is_prod else 'db-f1-micro')}
  availability    : {'REGIONAL' if is_prod else 'ZONAL'}
  db_storage_gb   : {p.get('db_storage_gb', 20)}

CACHE:
  tier   : {p.get('memorystore_tier') or ('STANDARD_HA' if is_prod else 'BASIC')}
  size_gb: {p.get('memorystore_size_gb', 1)}

MONITORING:
  log_retention_days: {p.get('log_retention_days', 30)}
  alert_email       : {p.get('alert_email', '')}
  custom_domain     : {p.get('custom_domain', '')}

REQUIRED ENV VARS (each must become a Terraform variable and be injected into startup .env):
{env_block}

RUNTIME SERVICES (all must be started in startup script; firewall must open their ports):
{runtime_block}

INFRASTRUCTURE WARNINGS (must be respected):
{warn_block}

GENERATION CHECKLIST:
  include_cloud_sql        : {has_db and db_hosting == 'managed_cloud'}
  include_memorystore      : {has_cache}
  include_cloud_storage    : {has_bkt and p.get('storage_provider','none') not in ('cloudinary','external')}
  include_load_balancer    : {has_lb}
  include_mig_autoscaling  : {auto_scale}
  include_cloud_monitoring : {monitoring}
  include_secret_manager   : True  ← ALWAYS use Secret Manager for any is_secret=true env vars
  include_cloud_dns        : {bool(p.get('custom_domain'))}

SECRETS (is_secret=true vars from README — MUST go into GCP Secret Manager):
{chr(10).join('  - ' + ev.get('name','') for ev in (p.get('required_env_vars') or []) if isinstance(ev, dict) and ev.get('is_secret')) or '  None detected'}
Extra secrets requested: {', '.join(p.get('secrets_to_store') or []) or 'none'}

STARTUP SCRIPT MUST:
  1. Clone: https://github.com/{github_owner}/{github_repo}
  2. Install: {p.get('install_command') or 'auto-detect from language'}
  3. Build:   {p.get('build_command') or 'skip if not needed'}
  4. Write NON-SECRET env vars directly to .env
  5. For EVERY is_secret var: fetch from Secret Manager at boot:
       export SECRET_VALUE=$(gcloud secrets versions access latest \
         --secret="SECRET_NAME" --project="{p.get('gcp_project_id') or config.GCP_PROJECT_ID}" 2>/dev/null || echo "")
       echo "SECRET_NAME=$SECRET_VALUE" >> /app/.env
     Do this for EACH secret — never hardcode secret values in Terraform or startup script.
  6. Start:   {p.get('app_start_command') or 'auto-detect from language/framework'}
  7. Configure process manager ({p.get('process_manager','systemd')}) for auto-restart on reboot

TERRAFORM SECRET MANAGER RESOURCES TO GENERATE (for each is_secret var):
  - google_secret_manager_secret (lifecycle: ignore_changes = [labels])
  - google_secret_manager_secret_version with placeholder value "REPLACE_ME" (user uploads real value later)
  - google_secret_manager_iam_member granting the VM service account roles/secretmanager.secretAccessor
  - google_project_service to enable secretmanager.googleapis.com

Return ONLY JSON: {{"main_tf": "...", "variables_tf": "...", "outputs_tf": "..."}}
"""

    # ── Internals ──────────────────────────────────────────────────────────────
    
    def _gather_mcp_context_sync(self, prompt: str, session_id: str = None) -> str:
        if not config.ENABLE_TERRAFORM_MCP:
            return ""
        try:
            # If we're already inside a running event loop (FastAPI background task),
            # use asyncio.get_event_loop().run_until_complete() via run_in_executor
            # to avoid the RuntimeError from asyncio.run() nesting.
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self._gather_mcp_context_async(prompt, session_id))
                    return future.result(timeout=120)
            except RuntimeError:
                # No running loop — safe to call asyncio.run() directly
                return asyncio.run(self._gather_mcp_context_async(prompt, session_id))
        except Exception as e:
            logger.error("Failed to gather MCP context: %s", e)
            return ""

    async def _gather_mcp_context_async(self, prompt: str, session_id: str = None) -> str:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            import google.generativeai as genai
            from google.generativeai.types import Tool, FunctionDeclaration
        except ImportError as e:
            logger.warning("mcp package missing, skipping MCP context generation: %s", e)
            return ""

        # Create trace for context gathering
        trace = langfuse_service.create_trace(
            name="mcp-context-gather",
            session_id=session_id,
            input=prompt
        )

        server_params = StdioServerParameters(
            command="docker",
            args=["run", "-i", "--rm", "hashicorp/terraform-mcp-server", "--toolsets=registry"],
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()
                    
                    def _sanitize_schema(schema: dict) -> dict:
                        """Recursively remove unsupported validation keys from JSON schema for Gemini compatibility."""
                        # Gemini only supports basic OpenAPI schema. Drop extended JSON schema keywords.
                        drop_keys = {"default", "minimum", "maximum", "minLength", "maxLength", "pattern", "additionalProperties"}
                        cleaned = {}
                        for k, v in schema.items():
                            if k in drop_keys:
                                continue
                            if isinstance(v, dict):
                                cleaned[k] = _sanitize_schema(v)
                            elif isinstance(v, list) and k not in ("required", "enum"):
                                cleaned[k] = [_sanitize_schema(i) if isinstance(i, dict) else i for i in v]
                            else:
                                cleaned[k] = v
                        # Gemini requires `type: object` for the root
                        if schema.get("type") == "object" and "properties" not in cleaned:
                            cleaned["properties"] = {}
                        return cleaned

                    genai_tools = []
                    for t in tools_response.tools:
                        genai_tools.append(
                            Tool(
                                function_declarations=[
                                    FunctionDeclaration(
                                        name=t.name,
                                        description=t.description,
                                        parameters=_sanitize_schema(t.inputSchema)
                                    )
                                ]
                            )
                        )
                    
                    gather_system = (
                        "You are an AI context-gathering agent. Read the user's infrastructure request. "
                        "Determine if you need to look up documentation from the Terraform Registry "
                        "(like 'get_provider_details' or 'search_modules') to understand complex properties or syntaxes. "
                        "Use your tools to query the registry. Once you have enough context, reply with a focused "
                        "technical summary of the module versions and resource arguments needed to write the code. "
                        "Do NOT generate the actual `.tf` code. ONLY summarize the registry data for the coder."
                    )
                    
                    model = genai.GenerativeModel(
                        model_name=config.GEMINI_MODEL,
                        system_instruction=gather_system,
                        tools=genai_tools
                    )
                    chat = model.start_chat()
                    response = chat.send_message(prompt)
                    
                    # Intercept up to 5 tool calls
                    for _ in range(5):
                        if not response.candidates:
                            break
                        part = response.candidates[0].content.parts[0]
                        if not getattr(part, "function_call", None):
                            break  # Native text response
                        
                        fc = part.function_call
                        logger.info("MCP Tool called: %s", fc.name)
                        
                        args = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else dict(fc.args)
                        try:
                            mcp_result = await session.call_tool(fc.name, arguments=args)
                            result_text = "\\n".join(c.text for c in mcp_result.content if c.type == "text")
                        except Exception as e:
                            logger.error("MCP Tool '%s' failed: %s", fc.name, e)
                            result_text = f"Error: {e}"
                            
                        # Feed the tool response back into Gemini
                        # Using dict mapping instead of Part and FunctionResponse imported types
                        response = chat.send_message(
                            {"function_response": {"name": fc.name, "response": {"result": result_text[:10000]}}}
                        )
                    
                    final_text = response.text if hasattr(response, "text") else getattr(
                        response.candidates[0].content.parts[0], "text", "No context gathered."
                    )
                    if trace:
                        langfuse_service.log_generation(
                            trace,
                            name="gemini-mcp-gather",
                            model=config.GEMINI_MODEL,
                            input_messages=[{"role": "user", "content": prompt}],
                            output=final_text
                        )
                    return final_text
        except Exception as e:
            logger.error("Failed async MCP gather: %s", e, exc_info=True)
            if trace:
                trace.update(level="ERROR", statusMessage=str(e))
            return ""

    def _call(self, user_prompt: str, session_id: str = None) -> TerraformBundle:
        full_input = f"System Prompt:\\n{self._SYSTEM}\\n\\nUser Prompt:\\n{user_prompt}"
        trace = langfuse_service.create_trace(
            name="terraform-gen",
            session_id=session_id,
            metadata={"length": len(user_prompt)},
            input=full_input,
        )

        raw = self.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": self._SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.1, max_tokens=16384,
            response_format={"type": "json_object"}, timeout=120,
            _trace=trace,
        )
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
            
        for key in ("main_tf", "variables_tf", "outputs_tf", "github_workflow_yaml"):
            val = data.get(key, "")
            data[key] = json.dumps(val, indent=2) if isinstance(val, dict) else str(val or "")
            
        if trace:
            try:
                trace.update(output=data)
            except Exception as e:
                logger.error("Failed to update Langfuse trace: %s", e)
                
        return TerraformBundle(**data)

    def _generate_workflow(self, session_id: str = None) -> str:
        trace = langfuse_service.create_trace(
            name="cicd-gen",
            session_id=session_id,
            input=self._CICD,
        )
        try:
            raw = self.llm_service.chat_completion(
                messages=[{"role": "user", "content": self._CICD}],
                temperature=0.1, max_tokens=12000, timeout=60,
                _trace=trace,
            )
            result = raw.replace("```yaml", "").replace("```yml", "").replace("```", "").strip()
            if trace:
                try:
                    trace.update(output=result)
                except Exception:
                    pass
            return result
        except Exception as e:
            logger.error("CI/CD workflow generation failed: %s", e)
            if trace:
                try:
                    trace.update(level="ERROR", statusMessage=str(e))
                except Exception:
                    pass
            return "# Error generating CI/CD workflow."

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
            except subprocess.CalledProcessError as e:
                logger.error("terraform validate failed: %s", e.stderr.decode(errors="replace") if e.stderr else "")

        return bundle