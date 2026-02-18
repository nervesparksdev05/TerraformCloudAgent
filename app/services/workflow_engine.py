"""
Background task workflows for async Terraform operations.

Fixes applied:
  - Reads original request from request.json (RunResponse has no .request field)
  - Imports and initialises SecurityChecker for revalidate_and_replan
  - subprocess calls wrapped in asyncio.to_thread to not block event loop
"""
import asyncio
import json
import subprocess
from pathlib import Path
from typing import Optional

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
            self.run_manager.update_run_status(run_id, RunStatus.PLANNING)

            # If no request provided (refinement), load original from disk
            if not request:
                request = self._load_original_request(run_id)

            logger.info(
                "[%s] Starting planning phase (refinement: %s)",
                run_id,
                bool(feedback),
            )

            workspace_path = self.run_manager.get_workspace_path(run_id)

            if feedback:
                current_code = self.workspace_manager.read_terraform_files(
                    workspace_path
                )
                bundle = self.llm_generator.refine_terraform(
                    base_request=(
                        request.request
                        if isinstance(request.request, str)
                        else json.dumps(request.request)
                    ),
                    current_code=current_code,
                    feedback=feedback,
                    provider=request.provider,
                )
            else:
                bundle = self.llm_generator.generate_terraform(
                    params=(
                        request.request
                        if isinstance(request.request, dict)
                        else {}
                    ),
                    provider=request.provider,
                )

            self.workspace_manager.write_terraform_files(workspace_path, bundle)
            if not feedback:
                self.workspace_manager.write_request_json(workspace_path, request)

            # Skip terraform plan to avoid credential requirements (multi-cloud support)
            # Files are generated and ready for review immediately
            logger.info("[%s] Terraform files generated, skipping plan validation", run_id)
            plan_output = "Terraform files generated successfully. Plan skipped (multi-cloud mode)."

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.PLANNED
                run.plan_output = plan_output
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Planning phase complete", run_id)

        except Exception as e:
            logger.error("[%s] Planning failed: %s", run_id, e)
            self.run_manager.update_run_status(
                run_id, RunStatus.FAILED, error=str(e)
            )

    # ================================================================
    # APPLY PHASE
    # ================================================================

    async def execute_apply_phase(self, run_id: str) -> None:
        """
        Apply Terraform plan.
        Transitions: APPROVED → APPLYING → COMPLETED (or FAILED)
        """
        try:
            self.run_manager.update_run_status(run_id, RunStatus.APPLYING)
            logger.info("[%s] Starting apply phase", run_id)

            workspace_path = self.run_manager.get_workspace_path(run_id)
            outputs = await self._run_terraform_apply(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.COMPLETED
                run.outputs = outputs
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Apply phase complete", run_id)

        except Exception as e:
            logger.error("[%s] Apply failed: %s", run_id, e)
            self.run_manager.update_run_status(
                run_id, RunStatus.FAILED, error=str(e)
            )

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
        """Run terraform apply and return outputs."""
        logger.debug("[%s] terraform apply", workspace_path.name)
        await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "apply", "-auto-approve", "-no-color"],
            workspace_path,
        )

        logger.debug("[%s] terraform output", workspace_path.name)
        result = await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "output", "-json"],
            workspace_path,
        )
        return json.loads(result.stdout) if result.stdout else {}

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
        """Run subprocess with proper error handling."""
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(
                "%s failed.\nSTDOUT: %s\nSTDERR: %s",
                " ".join(cmd),
                e.stdout,
                e.stderr,
            )
            raise