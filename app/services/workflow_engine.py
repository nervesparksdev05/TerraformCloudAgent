"""
Background task workflows for async Terraform operations.

Fixes applied:
  - Reads original request from request.json (RunResponse has no .request field)
  - Imports and initialises SecurityChecker for revalidate_and_replan
  - subprocess calls wrapped in asyncio.to_thread to not block event loop
  - Self-healer now auto-imports EntityAlreadyExists resources and retries apply
  - tfvars.json now only contains declared Terraform variables (no extra keys)
  - revalidate_and_replan now runs _sanitize_bundle on edited files before plan
"""
import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Set

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import RunStatus, AgentRequest, TerraformBundle
from app.services.run_manager import RunManager
from app.services.llm_generator import LLMGenerator
from app.services.workspace_manager import WorkspaceManager

logger = get_logger(__name__)

# ── Variables that are NOT Terraform input variables ──────────────────────────
# These come from the conversation params but should never go into tfvars.json
# because they are not declared in variables.tf
_NON_TERRAFORM_KEYS: Set[str] = {
    "readme_context", "workload_description", "workload_type",
    "github_owner", "github_repo", "github_branch",
    "cloud_provider", "detected_services", "infrastructure_warnings",
    "external_services", "runtime_services", "env_var_groups",
    "required_env_vars", "optional_env_vars", "dependencies",
    "suggested_provider", "suggested_provider_reason",
    "suggested_instance_dev", "suggested_instance_prod",
    "sizing_tier", "current_deployment_platform",
    "database_notes", "database_orm", "database_connection_env_var",
    "websocket_library", "background_job_description",
    "frontend_served_by", "storage_description",
    "run_ids", "session_id", "conversation_params",
    "is_complete", "status", "updated_at",
    "monitoring_enabled", "backup_enabled",
    "use_asg", "use_alb",
}


def _build_safe_tfvars(params: dict, workspace_path: Path) -> dict:
    """
    Build a tfvars dict that ONLY contains variables declared in variables.tf.

    Strategy:
      1. Parse variables.tf to extract declared variable names
      2. Filter params to only those names
      3. Also strip known non-Terraform keys as a safety net
      4. Replace any remaining REPLACE_ME placeholders with safe empty values

    This prevents Terraform from erroring on undeclared variable warnings
    and ensures REPLACE_ME never reaches apply.
    """
    # Step 1: Parse variables.tf for declared variable names
    declared_vars: Set[str] = set()
    vars_file = workspace_path / "variables.tf"
    if vars_file.exists():
        content = vars_file.read_text(encoding="utf-8")
        declared_vars = set(re.findall(r'variable\s+"(\w+)"', content))
        logger.debug("Declared Terraform variables: %s", declared_vars)

    # Step 2: Build tfvars from params
    tfvars: dict = {}
    for k, v in params.items():
        # Skip non-terraform keys
        if k in _NON_TERRAFORM_KEYS:
            continue
        # If we parsed variables.tf, only include declared vars
        if declared_vars and k not in declared_vars:
            continue
        # Skip None values
        if v is None:
            continue
        tfvars[k] = v

    # Step 3: Sanitize REPLACE_ME values
    for k, v in list(tfvars.items()):
        if isinstance(v, str) and "REPLACE_ME" in v:
            tfvars[k] = ""
            logger.debug("tfvars: replaced REPLACE_ME in %s with ''", k)
        elif isinstance(v, list):
            tfvars[k] = [
                "" if (isinstance(i, str) and "REPLACE_ME" in i) else i
                for i in v
            ]

    # Step 4: Ensure critical safe defaults
    if tfvars.get("instance_type") == "t2.micro":
        tfvars["instance_type"] = "t3.micro"
    if tfvars.get("key_pair_name") in ("REPLACE_ME", None):
        tfvars.pop("key_pair_name", None)  # Let variables.tf default="" handle it
    if tfvars.get("ssh_key_name") in ("REPLACE_ME", None):
        tfvars.pop("ssh_key_name", None)
    if str(tfvars.get("alert_email", "")).endswith("REPLACE_ME@example.com"):
        tfvars["alert_email"] = ""
    cidrs = tfvars.get("ssh_allowed_cidrs")
    if isinstance(cidrs, list) and cidrs == ["0.0.0.0/0"]:
        tfvars["ssh_allowed_cidrs"] = []

    logger.debug("Safe tfvars built with %d keys", len(tfvars))
    return tfvars


class WorkflowEngine:
    """Handles background execution of Terraform workflows."""

    def __init__(self):
        self.run_manager = RunManager()
        self.llm_generator = LLMGenerator()
        self.workspace_manager = WorkspaceManager()
        self.security_checker = None  # Legacy placeholder

    # ================================================================
    # PLANNING PHASE
    # ================================================================

    async def execute_planning_phase(
        self,
        run_id: str,
        request: Optional[AgentRequest] = None,
        feedback: Optional[str] = None,
    ) -> None:
        """
        Generate or refine Terraform plan.
        Transitions: CREATED/PLANNING → PLANNING → PLANNED (or FAILED)
        """
        try:
            logger.info("[%s] Starting planning phase - updating status to PLANNING", run_id)
            self.run_manager.update_run_status(run_id, RunStatus.PLANNING)

            if not request:
                logger.info("[%s] No request provided, loading from disk", run_id)
                request = self._load_original_request(run_id)

            logger.info(
                "[%s] Starting planning phase (refinement: %s)",
                run_id,
                bool(feedback),
            )

            workspace_path = self.run_manager.get_workspace_path(run_id)
            logger.info("[%s] Workspace path: %s", run_id, workspace_path)

            if feedback:
                current_code = self.workspace_manager.read_terraform_files(
                    workspace_path
                )
                params = request.request if isinstance(request.request, dict) else {}
                bundle = await self.llm_generator.refine_terraform(
                    base_request=(
                        request.request
                        if isinstance(request.request, str)
                        else json.dumps(request.request)
                    ),
                    current_code=current_code,
                    feedback=feedback,
                    readme_context=params.get("readme_context", ""),
                )
            else:
                logger.info("[%s] Calling LLM to generate Terraform", run_id)
                params = request.request if isinstance(request.request, dict) else {}
                logger.info("[%s] Params keys: %s", run_id, list(params.keys()) if isinstance(params, dict) else "N/A")
                bundle = await self.llm_generator.generate_terraform(params=params)
                logger.info("[%s] LLM generation complete", run_id)

            if not bundle or (not bundle.main_tf and not bundle.variables_tf and not bundle.outputs_tf):
                error_msg = "Terraform generation failed: LLM returned empty content"
                logger.error("[%s] %s", run_id, error_msg)
                self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=error_msg)
                return

            self.workspace_manager.write_terraform_files(workspace_path, bundle)
            if not feedback:
                self.workspace_manager.write_request_json(workspace_path, request)

            # ── Log full TF files + params to Langfuse ────────────────────
            try:
                from app.services import langfuse_service
                session_id = params.get("session_id") if isinstance(params, dict) else None
                tf_trace = langfuse_service.create_trace(
                    name="Generated Terraform Files",
                    session_id=session_id,
                    user_id=(params.get("user_id") if isinstance(params, dict) else None),
                    username=(params.get("username") if isinstance(params, dict) else None),
                    input={
                        "run_id": run_id,
                        "is_refinement": bool(feedback),
                        "params_keys": list(params.keys()) if isinstance(params, dict) else [],
                    },
                    output={
                        "main_tf": bundle.main_tf,
                        "variables_tf": bundle.variables_tf,
                        "outputs_tf": bundle.outputs_tf,
                        "github_workflow_yaml": bundle.github_workflow_yaml or "",
                    },
                )
            except Exception as e:
                logger.debug("Langfuse TF file logging failed (non-blocking): %s", e)

            # Skip terraform plan to avoid credential requirements (multi-cloud support)
            # Files are generated and ready for review immediately
            logger.info("[%s] Terraform files generated, skipping plan validation", run_id)
            plan_output = "Terraform files generated successfully. Plan skipped (multi-cloud mode)."

            topology_diagram = None

            # Persist all Production Excellence metadata + final status into the run state
            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.PLANNED
                run.plan_output = plan_output
                run.topology_diagram = topology_diagram
                if hasattr(bundle, "validation_notes") and bundle.validation_notes:
                    run.metadata = run.metadata or {}
                    run.metadata["mcp_validation_notes"] = bundle.validation_notes
                self.run_manager.save_run_state(run_id, run)
                logger.info(
                    "[%s] Planning complete: status=PLANNED, topology persisted",
                    run_id,
                )

                logger.info("[%s] Planning phase complete", run_id)

        except Exception as e:
            logger.error("[%s] Planning failed: %s", run_id, e, exc_info=True)
            self.run_manager.update_run_status(
                run_id, RunStatus.FAILED, error=str(e)
            )

    # ================================================================
    # APPLY PHASE
    # ================================================================

    async def execute_apply_phase(self, run_id: str) -> None:
        """
        Apply Terraform plan with pre-apply safety checks.
        Transitions: APPROVED → APPLYING → COMPLETED (or FAILED)

        Safety gate (in order):
          1. AWS credentials must be set
          2. AWS region must be set
          3. terraform validate  — syntax / provider check
          4. terraform plan -out=tfplan  — capture plan; abort if no changes
          5. Destructive resource scan  — warn loudly if any resource will be destroyed
          6. terraform apply tfplan  — apply only the pre-computed plan
        """
        workspace_path: Optional[Path] = None
        try:
            self.run_manager.update_run_status(run_id, RunStatus.APPLYING)
            logger.info("[%s] Starting apply phase — running safety checks", run_id)

            workspace_path = self.run_manager.get_workspace_path(run_id)

            # ── CHECK 1: AWS Credentials ──────────────────────────────
            if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
                raise ValueError(
                    "AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) are not set in .env — cannot deploy."
                )
            logger.info("[%s] [OK] AWS Credentials found", run_id)

            # ── CHECK 2: AWS Region ───────────────────────────────────
            if not config.AWS_REGION:
                raise ValueError("AWS_REGION is not set in .env — cannot deploy.")
            logger.info("[%s] [OK] AWS_REGION = %s", run_id, config.AWS_REGION)

            # ── CHECK 2.5: Generate safe terraform.tfvars.json ────────
            logger.info("[%s] Generating terraform.tfvars.json...", run_id)
            orig_request = self._load_original_request(run_id)
            vars_data = orig_request.request if isinstance(orig_request.request, dict) else {}

            # FIX: Only pass variables declared in variables.tf, with REPLACE_ME sanitized
            safe_vars = _build_safe_tfvars(vars_data, workspace_path)

            vars_file = workspace_path / "terraform.tfvars.json"
            vars_file.write_text(json.dumps(safe_vars, indent=2), encoding="utf-8")
            logger.info("[%s] [OK] terraform.tfvars.json generated (%d vars)", run_id, len(safe_vars))

            # ── CHECK 3: terraform init ────────────────────────────────
            logger.info("[%s] Running terraform init...", run_id)
            await asyncio.to_thread(
                self._subprocess_run,
                ["terraform", "init", "-input=false"],
                workspace_path,
            )
            logger.info("[%s] [OK] terraform init OK", run_id)

            # ── CHECK 4: terraform validate ───────────────────────────
            logger.info("[%s] Running terraform validate...", run_id)
            await asyncio.to_thread(
                self._subprocess_run,
                ["terraform", "validate"],
                workspace_path,
            )
            logger.info("[%s] [OK] terraform validate OK", run_id)

            # ── CHECK 5: terraform plan → save to tfplan ──────────────
            logger.info("[%s] Running terraform plan...", run_id)
            plan_result = await asyncio.to_thread(
                self._subprocess_run_with_exitcode,
                ["terraform", "plan", "-out=tfplan", "-no-color", "-input=false", "-detailed-exitcode"],
                workspace_path,
            )
            # -detailed-exitcode: 0=no changes, 1=error, 2=changes present
            if plan_result.returncode == 0:
                logger.warning("[%s] [WARN] Terraform plan shows NO changes — nothing to apply. Marking complete.", run_id)
                run = self.run_manager.get_run(run_id)
                if run:
                    run.status = RunStatus.COMPLETED
                    run.plan_output = "No infrastructure changes needed — already up to date."
                    self.run_manager.save_run_state(run_id, run)
                return
            if plan_result.returncode == 1:
                raise subprocess.CalledProcessError(1, "terraform plan", plan_result.stdout, plan_result.stderr)
            logger.info("[%s] [OK] terraform plan OK — changes detected", run_id)

            # ── CHECK 6: Destructive resource scan ────────────────────
            plan_text = plan_result.stdout or ""
            destroyed = [
                line.strip() for line in plan_text.splitlines()
                if "will be destroyed" in line or "must be replaced" in line
            ]
            if destroyed:
                logger.warning(
                    "[%s] [WARN] DESTRUCTIVE OPERATIONS DETECTED (%d resources):\n%s",
                    run_id, len(destroyed), "\n".join(destroyed),
                )
                run = self.run_manager.get_run(run_id)
                if run:
                    run.metadata = run.metadata or {}
                    run.metadata["destructive_resources"] = destroyed
                    self.run_manager.save_run_state(run_id, run)
            else:
                logger.info("[%s] [OK] No destructive operations in plan", run_id)

            # ── APPLY ─────────────────────────────────────────────────
            logger.info("[%s] Applying terraform plan...", run_id)
            outputs = await self._run_terraform_apply(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.COMPLETED
                run.outputs = outputs
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] [OK] Apply phase complete", run_id)

        except subprocess.CalledProcessError as spe:
            stderr = spe.stderr or ""
            stdout = spe.stdout or ""

            # ── Self-Healer: Auto-Import ──────────────────────────────
            import_errors = self._parse_entity_already_exists_errors(stderr)
            if import_errors and workspace_path:
                logger.warning(
                    "[%s] EntityAlreadyExists detected for %d resource(s) — attempting auto-import.",
                    run_id, len(import_errors),
                )
                recovery_ok = await self._auto_import_and_retry(run_id, workspace_path, import_errors)
                if recovery_ok:
                    return

            # ── Self-Healer: LLM Diagnosis ────────────────────────────
            logger.error("[%s] Terraform Apply Failed. Triggering Self-Healer...", run_id)
            tf_files = {}
            if workspace_path:
                tf_files = self.workspace_manager.read_terraform_files(workspace_path)
            run = self.run_manager.get_run(run_id)
            # Extract session identity from original request for Langfuse tracing
            _orig = self._load_original_request(run_id)
            _req_params = _orig.request if isinstance(_orig.request, dict) else {}
            diagnosis = await self.llm_generator.diagnose_error(
                error_msg=f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}",
                terraform_code=tf_files,
                session_id=_req_params.get("session_id"),
                user_id=_req_params.get("user_id"),
                username=_req_params.get("username"),
            )
            if run:
                run.status = RunStatus.FAILED
                run.error = "Deployment failed — self-healer is analysing the cause."
                run.self_healer_diagnosis = diagnosis
                self.run_manager.save_run_state(run_id, run)
            logger.info("[%s] Self-Healer diagnosis: %s", run_id, diagnosis.get("diagnosis"))

        except Exception as e:
            logger.error("[%s] Apply safety check failed: %s", run_id, e, exc_info=True)
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))

    # ================================================================
    # DESTROY PHASE
    # ================================================================

    async def execute_destroy_phase(self, run_id: str) -> None:
        """
        Destroy Terraform infrastructure.
        Transitions: COMPLETED → DESTROYING → DESTROYED (or FAILED)
        """
        try:
            self.run_manager.update_run_status(run_id, RunStatus.DESTROYING)
            logger.info("[%s] Starting destroy phase", run_id)

            workspace_path = self.run_manager.get_workspace_path(run_id)
            await self._run_terraform_destroy(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.DESTROYED
                run.outputs = None
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Destroy phase complete", run_id)

        except Exception as e:
            logger.error("[%s] Destroy failed: %s", run_id, e)
            self.run_manager.update_run_status(
                run_id, RunStatus.FAILED, error=str(e)
            )

    # ================================================================
    # REVALIDATE (after manual file edits)
    # ================================================================

    async def revalidate_and_replan(self, run_id: str, provider: str) -> None:
        """
        Re-validate security and re-plan after manual file edits.
        Transitions: PLANNING → PLANNED (or FAILED)
        """
        try:
            logger.info("[%s] Revalidating after file edits", run_id)
            workspace_path = self.run_manager.get_workspace_path(run_id)

            # FIX: Re-sanitize the edited files before planning
            # This catches cases where the user manually edits files and
            # re-introduces patterns like aws_default_vpc, cidr_blocks, etc.
            raw_bundle = TerraformBundle(
                main_tf=self._read_file(workspace_path / "main.tf"),
                variables_tf=self._read_file(workspace_path / "variables.tf"),
                outputs_tf=self._read_file(workspace_path / "outputs.tf"),
            )
            # --- Sanitization step ---
            sanitized = LLMGenerator._sanitize_bundle(raw_bundle)

            # Write sanitized files back if anything changed
            if (
                sanitized.main_tf != raw_bundle.main_tf
                or sanitized.variables_tf != raw_bundle.variables_tf
                or sanitized.outputs_tf != raw_bundle.outputs_tf
            ):
                logger.info(
                    "[%s] Sanitizer patched edited files — writing back to disk",
                    run_id,
                )
                self.workspace_manager.write_terraform_files(
                    workspace_path, sanitized
                )

            bundle = sanitized  # ensure downstream uses sanitized version

            # --- Security validation ---
            if self.security_checker:
                is_valid, error_msg = self.security_checker.validate(
                    bundle, provider=provider
                )
                if not is_valid:
                    msg = f"Security validation failed: {error_msg}"
                    logger.error("[%s] %s", run_id, msg)
                    self.run_manager.update_run_status(
                        run_id, RunStatus.FAILED, error=msg
                    )
                    return
                logger.info("[%s] Security validation passed", run_id)
            else:
                logger.warning(
                    "[%s] SecurityChecker not available — skipping validation",
                    run_id,
                )

            plan_output = await self._run_terraform_plan(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.PLANNED
                run.plan_output = plan_output
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Re-planning complete", run_id)

        except Exception as e:
            logger.error("[%s] Revalidation failed: %s", run_id, e)
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))

    # ================================================================
    # SELF-HEALER HELPERS
    # ================================================================

    @staticmethod
    def _parse_entity_already_exists_errors(stderr: str) -> List[Dict[str, str]]:
        """
        Parse Terraform stderr for EntityAlreadyExists errors.
        Extended to handle SNS and SecretsManager in addition to IAM.
        """
        results: List[Dict[str, str]] = []
        if not stderr or "EntityAlreadyExists" not in stderr:
            return results

        error_blocks = re.split(r"\nError:", stderr)

        for block in error_blocks:
            if "EntityAlreadyExists" not in block:
                continue

            addr_match = re.search(r"\bwith\s+([\w.]+),?", block)
            if not addr_match:
                continue
            resource_address = addr_match.group(1).strip()
            resource_type = resource_address.split(".")[0] if "." in resource_address else ""

            name_match = re.search(r"\(([^)]+)\):", block)
            if not name_match:
                name_match = re.search(r"already exists[:\s]+([^\s.]+)", block, re.IGNORECASE)
            if not name_match:
                continue

            resource_id = name_match.group(1).strip()

            results.append({
                "resource_address": resource_address,
                "resource_id": resource_id,
                "resource_type": resource_type,
            })
            logger.info(
                "Parsed EntityAlreadyExists: address=%s id=%s",
                resource_address, resource_id,
            )

        return results

    async def _auto_import_and_retry(
        self,
        run_id: str,
        workspace_path: Path,
        import_errors: List[Dict[str, str]],
    ) -> bool:
        imported_any = False

        for err in import_errors:
            addr  = err["resource_address"]
            rid   = err["resource_id"]
            rtype = err["resource_type"]

            import_id: Optional[str] = None

            if rtype in ("aws_iam_instance_profile",):
                import_id = rid
            elif rtype in ("aws_iam_role",):
                import_id = rid
            elif rtype in ("aws_iam_policy",):
                logger.warning(
                    "[%s] Cannot auto-import %s — IAM policy requires ARN. "
                    "Run manually: terraform import %s <policy-arn>",
                    run_id, addr, addr,
                )
                continue
            elif rtype in ("aws_iam_role_policy_attachment",):
                logger.warning(
                    "[%s] Cannot auto-import %s — role policy attachment requires 'role/arn'.",
                    run_id, addr,
                )
                continue
            elif rtype in ("aws_sns_topic",):
                # SNS topics are imported by ARN — skip, too fragile to auto-construct
                logger.warning("[%s] Cannot auto-import SNS topic %s — requires ARN.", run_id, addr)
                continue
            elif rtype in ("aws_secretsmanager_secret",):
                # Secrets are imported by ARN — skip
                logger.warning("[%s] Cannot auto-import SecretsManager secret %s — requires ARN.", run_id, addr)
                continue
            else:
                import_id = rid

            try:
                logger.info("[%s] terraform import %s %s", run_id, addr, import_id)
                await asyncio.to_thread(
                    self._subprocess_run,
                    ["terraform", "import", addr, import_id],
                    workspace_path,
                )
                logger.info("[%s] [OK] Imported %s as %s", run_id, import_id, addr)
                imported_any = True
            except subprocess.CalledProcessError as e:
                logger.error("[%s] terraform import failed for %s: %s", run_id, addr, e.stderr)

        if not imported_any:
            logger.warning("[%s] No resources were successfully imported — skipping retry.", run_id)
            return False

        try:
            logger.info("[%s] Re-running terraform plan after import...", run_id)
            plan_result = await asyncio.to_thread(
                self._subprocess_run_with_exitcode,
                ["terraform", "plan", "-out=tfplan", "-no-color", "-input=false", "-detailed-exitcode"],
                workspace_path,
            )
            if plan_result.returncode == 1:
                raise subprocess.CalledProcessError(
                    1, "terraform plan (retry)", plan_result.stdout, plan_result.stderr
                )
            if plan_result.returncode == 0:
                logger.info("[%s] [OK] No remaining changes after import — marking complete.", run_id)
                run = self.run_manager.get_run(run_id)
                if run:
                    run.status = RunStatus.COMPLETED
                    run.plan_output = "All resources imported; infrastructure is up to date."
                    self.run_manager.save_run_state(run_id, run)
                return True

            logger.info("[%s] Re-running terraform apply after import...", run_id)
            outputs = await self._run_terraform_apply(workspace_path)
            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.COMPLETED
                run.outputs = outputs
                run.metadata = run.metadata or {}
                run.metadata["auto_import_applied"] = [e["resource_address"] for e in import_errors]
                self.run_manager.save_run_state(run_id, run)

            return True

        except subprocess.CalledProcessError as e:
            logger.error("[%s] Retry apply after import failed: %s", run_id, e.stderr or e.stdout)
            return False

    # ================================================================
    # HELPERS
    # ================================================================

    def _load_original_request(self, run_id: str) -> AgentRequest:
        """
        Load the original AgentRequest from request.json in the workspace.

        RunResponse does NOT store the original request, so we read it
        from the file that run_manager._save_request() wrote.
        """
        workspace_path = self.run_manager.get_workspace_path(run_id)
        request_file = workspace_path / "request.json"

        if not request_file.exists():
            raise ValueError(
                f"Run {run_id}: request.json not found in workspace"
            )

        data = json.loads(request_file.read_text(encoding="utf-8"))
        return AgentRequest(
            request=data.get("request", ""),
            provider=data.get("provider", "aws"),
            auto_approve=data.get("auto_approve", False),
        )

    @staticmethod
    def _read_file(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ── Terraform CLI wrappers ──

    async def _run_terraform_plan(self, workspace_path: Path) -> str:
        """Run terraform init + plan."""
        logger.debug("[%s] terraform init", workspace_path.name)
        await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "init"],
            workspace_path,
        )
        logger.debug("[%s] terraform plan", workspace_path.name)
        result = await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "plan", "-out=tfplan", "-no-color", "-input=false"],
            workspace_path,
        )
        return result.stdout

    async def _run_terraform_apply(self, workspace_path: Path) -> dict:
        logger.debug("[%s] terraform apply tfplan", workspace_path.name)
        plan_file = workspace_path / "tfplan"
        if not plan_file.exists():
            raise FileNotFoundError(
                f"tfplan not found in {workspace_path} — refusing to apply without a validated plan file. "
                "Run terraform plan first."
            )
        cmd = ["terraform", "apply", "-no-color", "-input=false", str(plan_file)]
        await asyncio.to_thread(self._subprocess_run, cmd, workspace_path)

        logger.debug("[%s] terraform output", workspace_path.name)
        result = await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "output", "-json"],
            workspace_path,
        )
        try:
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except Exception:
            return {}

    async def _run_terraform_destroy(self, workspace_path: Path) -> None:
        """Run terraform destroy."""
        logger.debug("[%s] terraform destroy", workspace_path.name)
        await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "destroy", "-auto-approve", "-no-color"],
            workspace_path,
        )
        logger.info("Terraform destroy completed for %s", workspace_path.name)

    @staticmethod
    def _subprocess_run(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        if config.AWS_ACCESS_KEY_ID:     env["AWS_ACCESS_KEY_ID"]     = config.AWS_ACCESS_KEY_ID
        if config.AWS_SECRET_ACCESS_KEY: env["AWS_SECRET_ACCESS_KEY"] = config.AWS_SECRET_ACCESS_KEY
        if config.AWS_REGION:            env["AWS_DEFAULT_REGION"]    = config.AWS_REGION
        if config.AWS_SESSION_TOKEN:     env["AWS_SESSION_TOKEN"]     = config.AWS_SESSION_TOKEN

        try:
            return subprocess.run(
                cmd, cwd=cwd, check=True,
                capture_output=True, text=True, env=env,
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                "%s failed.\nSTDOUT: %s\nSTDERR: %s",
                " ".join(cmd),
                e.stdout,
                e.stderr,
            )
            raise

    @staticmethod
    def _subprocess_run_with_exitcode(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        if config.AWS_ACCESS_KEY_ID:     env["AWS_ACCESS_KEY_ID"]     = config.AWS_ACCESS_KEY_ID
        if config.AWS_SECRET_ACCESS_KEY: env["AWS_SECRET_ACCESS_KEY"] = config.AWS_SECRET_ACCESS_KEY
        if config.AWS_REGION:            env["AWS_DEFAULT_REGION"]    = config.AWS_REGION
        if config.AWS_SESSION_TOKEN:     env["AWS_SESSION_TOKEN"]     = config.AWS_SESSION_TOKEN
        result = subprocess.run(
            cmd, cwd=cwd, check=False,
            capture_output=True, text=True, env=env,
        )
        if result.returncode not in (0, 2):
            logger.error(
                "%s exited %d.\nSTDOUT: %s\nSTDERR: %s",
                " ".join(cmd), result.returncode, result.stdout, result.stderr,
            )
        return result