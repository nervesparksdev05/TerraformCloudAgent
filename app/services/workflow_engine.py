"""
Background task workflows for async Terraform operations.

Aligned flow (multi-cloud, industry-style):
- Planning phase:
  1) Generate/Refine Terraform files via LLM
  2) Run validations (no cloud creds required):
     - terraform fmt (format)
     - terraform validate (syntax)
     - tflint (best practices)
  3) (Optional) terraform plan if explicitly enabled + creds exist (kept off by default)

- Apply/Destroy:
  - Still uses terraform CLI; requires provider credentials configured in the runtime env.

Notes:
- Reads original request from request.json (RunResponse has no .request field)
- subprocess calls wrapped in asyncio.to_thread to avoid blocking event loop
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Optional, List

from app.core.logger import get_logger
from app.models.schemas import RunStatus, AgentRequest, TerraformBundle
from app.services.run_manager import RunManager
from app.services.llm_generator import LLMGenerator
from app.services.workspace_manager import WorkspaceManager

logger = get_logger(__name__)

# Optional security checker — import if available
try:
    from app.services.security import SecurityChecker
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False


class WorkflowEngine:
    """Handles background execution of Terraform workflows."""

    def __init__(self):
        self.run_manager = RunManager()
        self.llm_generator = LLMGenerator()
        self.workspace_manager = WorkspaceManager()
        self.security_checker = SecurityChecker() if _SECURITY_AVAILABLE else None

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
        Generate or refine Terraform code, then validate locally.

        Transitions:
          CREATED/PLANNING → PLANNING → PLANNED (or FAILED)
        """
        try:
            self.run_manager.update_run_status(run_id, RunStatus.PLANNING)

            # If no request provided (refinement), load original from disk
            if not request:
                request = self._load_original_request(run_id)

            logger.info("[%s] Starting planning phase (refinement=%s)", run_id, bool(feedback))

            workspace_path = self.run_manager.get_workspace_path(run_id)

            # 1) Generate / refine code
            if feedback:
                current_code = self.workspace_manager.read_terraform_files(workspace_path)
                bundle = self.llm_generator.refine_terraform(
                    base_request=(
                        request.request if isinstance(request.request, str) else json.dumps(request.request)
                    ),
                    current_code=current_code,
                    feedback=feedback,
                    provider=request.provider,
                )
            else:
                bundle = self.llm_generator.generate_terraform(
                    params=(request.request if isinstance(request.request, dict) else {}),
                    provider=request.provider,
                )

            # 2) Write files
            self.workspace_manager.write_terraform_files(workspace_path, bundle)
            if not feedback:
                self.workspace_manager.write_request_json(workspace_path, request)

            # 3) Optional security validation (your custom checker)
            if self.security_checker:
                is_valid, error_msg = self.security_checker.validate(bundle, provider=request.provider)
                if not is_valid:
                    msg = f"Security validation failed: {error_msg}"
                    logger.error("[%s] %s", run_id, msg)
                    self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=msg)
                    return
                logger.info("[%s] Security validation passed", run_id)
            else:
                logger.debug("[%s] SecurityChecker not available — skipping security validation", run_id)

            # 4) Run local validations (fmt/validate/tflint)
            validation_output = await self._run_validations(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.PLANNED
                run.plan_output = validation_output
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Planning phase complete", run_id)

        except Exception as e:
            logger.error("[%s] Planning failed: %s", run_id, e)
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))

    # ================================================================
    # APPLY PHASE
    # ================================================================

    async def execute_apply_phase(self, run_id: str) -> None:
        """
        Apply Terraform (requires credentials).
        Transitions: APPROVED → APPLYING → COMPLETED (or FAILED)
        """
        try:
            self.run_manager.update_run_status(run_id, RunStatus.APPLYING)
            logger.info("[%s] Starting apply phase", run_id)

            workspace_path = self.run_manager.get_workspace_path(run_id)

            # init/validate before apply (safe even if already done)
            await self._terraform_init(workspace_path)
            await self._terraform_validate(workspace_path)

            outputs = await self._run_terraform_apply(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.COMPLETED
                run.outputs = outputs
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Apply phase complete", run_id)

        except Exception as e:
            logger.error("[%s] Apply failed: %s", run_id, e)
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))

    # ================================================================
    # DESTROY PHASE
    # ================================================================

    async def execute_destroy_phase(self, run_id: str) -> None:
        """
        Destroy Terraform infra (requires credentials).
        Transitions: COMPLETED → DESTROYING → DESTROYED (or FAILED)
        """
        try:
            self.run_manager.update_run_status(run_id, RunStatus.DESTROYING)
            logger.info("[%s] Starting destroy phase", run_id)

            workspace_path = self.run_manager.get_workspace_path(run_id)

            # init before destroy
            await self._terraform_init(workspace_path)
            await self._run_terraform_destroy(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.DESTROYED
                run.outputs = None
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Destroy phase complete", run_id)

        except Exception as e:
            logger.error("[%s] Destroy failed: %s", run_id, e)
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))

    # ================================================================
    # REVALIDATE (after manual file edits)
    # ================================================================

    async def revalidate_and_replan(self, run_id: str, provider: str) -> None:
        """
        Re-validate (security + fmt/validate/tflint) after manual file edits.
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

            if self.security_checker:
                is_valid, error_msg = self.security_checker.validate(bundle, provider=provider)
                if not is_valid:
                    msg = f"Security validation failed: {error_msg}"
                    logger.error("[%s] %s", run_id, msg)
                    self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=msg)
                    return
                logger.info("[%s] Security validation passed", run_id)

            validation_output = await self._run_validations(workspace_path)

            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.PLANNED
                run.plan_output = validation_output
                self.run_manager.save_run_state(run_id, run)

            logger.info("[%s] Revalidation complete", run_id)

        except Exception as e:
            logger.error("[%s] Revalidation failed: %s", run_id, e)
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))

    # ================================================================
    # VALIDATIONS (fmt, validate, tflint)
    # ================================================================

    async def _run_validations(self, workspace_path: Path) -> str:
        """
        Run formatting + syntax + best-practices checks.

        Returns a single string that is safe to show in run.plan_output.
        """
        output_lines: List[str] = []
        output_lines.append("=== Terraform Validation Summary ===")

        # terraform fmt
        try:
            await self._terraform_fmt(workspace_path)
            output_lines.append("✅ terraform fmt: OK")
        except Exception as e:
            output_lines.append(f"❌ terraform fmt: FAILED ({e})")
            return "\n".join(output_lines)

        # terraform init (needed for validate + providers)
        try:
            await self._terraform_init(workspace_path)
            output_lines.append("✅ terraform init: OK")
        except Exception as e:
            output_lines.append(f"❌ terraform init: FAILED ({e})")
            return "\n".join(output_lines)

        # terraform validate
        try:
            validate_stdout = await self._terraform_validate(workspace_path)
            output_lines.append("✅ terraform validate: OK")
            if validate_stdout.strip():
                output_lines.append("--- validate output ---")
                output_lines.append(validate_stdout.strip())
        except Exception as e:
            output_lines.append(f"❌ terraform validate: FAILED ({e})")
            return "\n".join(output_lines)

        # tflint (optional if installed)
        tflint_installed = await self._is_tool_available("tflint")
        if not tflint_installed:
            output_lines.append("⚠️ tflint: SKIPPED (tflint not installed)")
            output_lines.append("Tip: install tflint to enable best-practices checks.")
            return "\n".join(output_lines)

        try:
            tflint_stdout = await self._tflint(workspace_path)
            output_lines.append("✅ tflint: OK")
            if tflint_stdout.strip():
                output_lines.append("--- tflint output ---")
                output_lines.append(tflint_stdout.strip())
        except subprocess.CalledProcessError as e:
            # tflint returns non-zero for findings; still show output and mark as failed
            out = (e.stdout or "").strip()
            err = (e.stderr or "").strip()
            output_lines.append("❌ tflint: FAILED (findings detected)")
            if out:
                output_lines.append("--- tflint stdout ---")
                output_lines.append(out)
            if err:
                output_lines.append("--- tflint stderr ---")
                output_lines.append(err)

        return "\n".join(output_lines)

    async def _is_tool_available(self, tool: str) -> bool:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [tool, "--version"],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    # ================================================================
    # HELPERS
    # ================================================================

    def _load_original_request(self, run_id: str) -> AgentRequest:
        """
        Load the original AgentRequest from request.json in the workspace.
        """
        workspace_path = self.run_manager.get_workspace_path(run_id)
        request_file = workspace_path / "request.json"

        if not request_file.exists():
            raise ValueError(f"Run {run_id}: request.json not found in workspace")

        data = json.loads(request_file.read_text(encoding="utf-8"))
        return AgentRequest(
            request=data.get("request", ""),
            provider=data.get("provider", "aws"),
            auto_approve=data.get("auto_approve", False),
        )

    @staticmethod
    def _read_file(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ================================================================
    # Terraform / TFLint CLI wrappers
    # ================================================================

    async def _terraform_fmt(self, workspace_path: Path) -> None:
        await asyncio.to_thread(self._subprocess_run, ["terraform", "fmt", "-recursive"], workspace_path)

    async def _terraform_init(self, workspace_path: Path) -> None:
        # -input=false avoids hanging; -upgrade=false keeps it stable
        await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "init", "-input=false", "-no-color"],
            workspace_path,
        )

    async def _terraform_validate(self, workspace_path: Path) -> str:
        result = await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "validate", "-no-color"],
            workspace_path,
        )
        return result.stdout or ""

    async def _tflint(self, workspace_path: Path) -> str:
        # Keep it simple: run in the workspace. If you use rulesets, add .tflint.hcl in repo.
        result = await asyncio.to_thread(
            self._subprocess_run,
            ["tflint", "--no-color"],
            workspace_path,
        )
        return result.stdout or ""

    async def _run_terraform_apply(self, workspace_path: Path) -> dict:
        await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "apply", "-auto-approve", "-no-color"],
            workspace_path,
        )
        result = await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "output", "-json"],
            workspace_path,
        )
        return json.loads(result.stdout) if result.stdout else {}

    async def _run_terraform_destroy(self, workspace_path: Path) -> None:
        await asyncio.to_thread(
            self._subprocess_run,
            ["terraform", "destroy", "-auto-approve", "-no-color"],
            workspace_path,
        )

    @staticmethod
    def _subprocess_run(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
        """
        Run subprocess with proper error handling.
        - check=True raises CalledProcessError for non-zero exit codes
        """
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
