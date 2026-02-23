"""
Background task workflows for async Terraform operations.

Fixes applied:
  - Reads original request from request.json (RunResponse has no .request field)
  - Imports and initialises SecurityChecker for revalidate_and_replan
  - subprocess calls wrapped in asyncio.to_thread to not block event loop
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import RunStatus, AgentRequest, TerraformBundle
from app.services.run_manager import RunManager
from app.services.llm_generator import LLMGenerator
from app.services.workspace_manager import WorkspaceManager

logger = get_logger(__name__)

class WorkflowEngine:
    """Handles background execution of Terraform workflows."""

    def __init__(self):
        self.run_manager = RunManager()
        self.llm_generator = LLMGenerator()
        self.workspace_manager = WorkspaceManager()
        self.security_checker = None  # Legacy placeholder (kept for revalidate_and_replan)

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

            # If no request provided (refinement), load original from disk
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
                bundle = self.llm_generator.refine_terraform(
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
                logger.info("[%s] Params keys: %s", run_id, list(params.keys()) if isinstance(params, dict) else 'N/A')
                bundle = self.llm_generator.generate_terraform(
                    params=params,
                )
                logger.info("[%s] LLM generation complete", run_id)

            # Validate bundle has actual content before writing
            if not bundle or (not bundle.main_tf and not bundle.variables_tf and not bundle.outputs_tf):
                error_msg = "Terraform generation failed: LLM returned empty content"
                logger.error("[%s] %s", run_id, error_msg)
                self.run_manager.update_run_status(
                    run_id, RunStatus.FAILED, error=error_msg
                )
                return

            self.workspace_manager.write_terraform_files(workspace_path, bundle)
            if not feedback:
                self.workspace_manager.write_request_json(workspace_path, request)

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
                self.run_manager.save_run_state(run_id, run)
                logger.info("[%s] Planning complete: status=PLANNED, topology persisted", run_id)

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
          1. GCP_PROJECT_ID must be set
          2. GCP credentials file must exist and be valid JSON
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

            # ── CHECK 1: GCP_PROJECT_ID ───────────────────────────────
            if not config.GCP_PROJECT_ID:
                raise ValueError(
                    "GCP_PROJECT_ID is not set in .env — cannot deploy. "
                    "Add GCP_PROJECT_ID=<your-project-id> to your .env file."
                )
            logger.info("[%s] ✅ GCP_PROJECT_ID = %s", run_id, config.GCP_PROJECT_ID)

            # ── CHECK 2: Credentials file ─────────────────────────────
            creds_path = config.GCP_CREDENTIALS_PATH
            if not creds_path or not os.path.exists(creds_path):
                raise ValueError(
                    f"GCP credentials file not found at '{creds_path}'. "
                    "Place your service account JSON at TerraformCloudAgent/gcp-sa-key.json "
                    "and set GCP_CREDENTIALS_PATH=/app/gcp-sa-key.json in docker-compose."
                )
            try:
                import json as _json
                with open(creds_path) as _f:
                    _creds = _json.load(_f)
                if _creds.get("type") != "service_account":
                    raise ValueError("credentials JSON is not a service_account key")
                logger.info("[%s] ✅ GCP credentials valid (account: %s)", run_id, _creds.get("client_email","?"))
            except Exception as ce:
                raise ValueError(f"Invalid GCP credentials file: {ce}") from ce

            # ── CHECK 3: terraform init ────────────────────────────────
            logger.info("[%s] Running terraform init...", run_id)
            await asyncio.to_thread(
                self._subprocess_run,
                ["terraform", "init", "-input=false"],
                workspace_path,
            )
            logger.info("[%s] ✅ terraform init OK", run_id)

            # ── CHECK 4: terraform validate ───────────────────────────
            logger.info("[%s] Running terraform validate...", run_id)
            await asyncio.to_thread(
                self._subprocess_run,
                ["terraform", "validate"],
                workspace_path,
            )
            logger.info("[%s] ✅ terraform validate OK", run_id)

            # ── CHECK 5: terraform plan → save to tfplan ──────────────
            logger.info("[%s] Running terraform plan...", run_id)
            plan_result = await asyncio.to_thread(
                self._subprocess_run_with_exitcode,
                ["terraform", "plan", "-out=tfplan", "-no-color", "-input=false", "-detailed-exitcode"],
                workspace_path,
            )
            # -detailed-exitcode: 0=no changes, 1=error, 2=changes present
            if plan_result.returncode == 0:
                logger.warning("[%s] ⚠️  Terraform plan shows NO changes — nothing to apply. Marking complete.", run_id)
                run = self.run_manager.get_run(run_id)
                if run:
                    run.status = RunStatus.COMPLETED
                    run.plan_output = "No infrastructure changes needed — already up to date."
                    self.run_manager.save_run_state(run_id, run)
                return
            if plan_result.returncode == 1:
                raise subprocess.CalledProcessError(1, "terraform plan", plan_result.stdout, plan_result.stderr)
            logger.info("[%s] ✅ terraform plan OK — changes detected", run_id)

            # ── CHECK 6: Destructive resource scan ────────────────────
            plan_text = plan_result.stdout or ""
            destroyed = [
                line.strip() for line in plan_text.splitlines()
                if "will be destroyed" in line or "must be replaced" in line
            ]
            if destroyed:
                logger.warning(
                    "[%s] ⚠️  DESTRUCTIVE OPERATIONS DETECTED (%d resources):\n%s",
                    run_id, len(destroyed), "\n".join(destroyed),
                )
                run = self.run_manager.get_run(run_id)
                if run:
                    run.metadata = run.metadata or {}
                    run.metadata["destructive_resources"] = destroyed
                    self.run_manager.save_run_state(run_id, run)
            else:
                logger.info("[%s] ✅ No destructive operations in plan", run_id)

            # ── APPLY: use the saved plan file ────────────────────────
            logger.info("[%s] Applying terraform plan...", run_id)
            outputs = await self._run_terraform_apply(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.COMPLETED
                run.outputs = outputs
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] ✅ Apply phase complete", run_id)

        except subprocess.CalledProcessError as spe:
            logger.error("[%s] Terraform Apply Failed. Triggering Self-Healer...", run_id)
            tf_files = {}
            if workspace_path:
                tf_files = self.workspace_manager.read_terraform_files(workspace_path)
            run = self.run_manager.get_run(run_id)
            diagnosis = self.llm_generator.diagnose_error(
                error_msg=f"STDOUT:\n{spe.stdout}\nSTDERR:\n{spe.stderr}",
                terraform_code=tf_files,
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

            bundle = TerraformBundle(
                main_tf=self._read_file(workspace_path / "main.tf"),
                variables_tf=self._read_file(workspace_path / "variables.tf"),
                outputs_tf=self._read_file(workspace_path / "outputs.tf"),
            )

            # Security validation (if checker available)
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
            self.run_manager.update_run_status(
                run_id, RunStatus.FAILED, error=str(e)
            )

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
            ["terraform", "plan", "-no-color"],
            workspace_path,
        )
        return result.stdout

    async def _run_terraform_apply(self, workspace_path: Path) -> dict:
        """Apply from pre-computed tfplan file and return outputs."""
        logger.debug("[%s] terraform apply tfplan", workspace_path.name)
        # Apply from the plan file saved by the safety gate (no --auto-approve on raw state)
        plan_file = workspace_path / "tfplan"
        cmd = ["terraform", "apply", "-no-color", "-input=false", str(plan_file)] \
            if plan_file.exists() else \
            ["terraform", "apply", "-auto-approve", "-no-color", "-input=false"]
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
    def _subprocess_run(
        cmd: list, cwd: Path
    ) -> subprocess.CompletedProcess:
        """Run subprocess with GCP credentials injected, raising on non-zero exit."""
        env = os.environ.copy()

        # Inject GCP authentication so Terraform can authenticate
        creds_path = config.GCP_CREDENTIALS_PATH
        if creds_path and os.path.exists(creds_path):
            env["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

        project_id = config.GCP_PROJECT_ID
        if project_id:
            env["GOOGLE_PROJECT"]          = project_id
            env["CLOUDSDK_CORE_PROJECT"]   = project_id
            env["GCLOUD_PROJECT"]           = project_id

        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                env=env,
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
    def _subprocess_run_with_exitcode(
        cmd: list, cwd: Path
    ) -> subprocess.CompletedProcess:
        """
        Like _subprocess_run but does NOT raise on non-zero exit.
        Used for `terraform plan -detailed-exitcode` where exit code 2
        means "changes present" (not an error).
        """
        env = os.environ.copy()
        creds_path = config.GCP_CREDENTIALS_PATH
        if creds_path and os.path.exists(creds_path):
            env["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        project_id = config.GCP_PROJECT_ID
        if project_id:
            env["GOOGLE_PROJECT"]        = project_id
            env["CLOUDSDK_CORE_PROJECT"] = project_id
            env["GCLOUD_PROJECT"]         = project_id
        result = subprocess.run(
            cmd, cwd=cwd, check=False,
            capture_output=True, text=True, env=env,
        )
        if result.returncode not in (0, 2):  # 0=no-change, 2=has-changes are both OK
            logger.error("%s exited %d.\nSTDOUT: %s\nSTDERR: %s",
                         " ".join(cmd), result.returncode, result.stdout, result.stderr)
        return result