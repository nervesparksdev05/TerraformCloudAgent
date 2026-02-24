"""workspace_manager.py — TerraBot: Filesystem management for Terraform workspaces."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle, AgentRequest

logger = get_logger(__name__)


class WorkspaceManager:
    """
    Manages the on-disk workspace for each Terraform run.

    Defense-in-depth: write_terraform_files() always calls _sanitize_bundle
    before writing, so even if sanitization was somehow skipped during
    generation or after a manual file edit, the sanitizer runs one final
    time before any file hits disk.
    """

    # ── Read ──────────────────────────────────────────────────────────────────

    def read_terraform_files(self, workspace_path: Path) -> Dict[str, str]:
        """Read all .tf files from workspace. Returns {} if path doesn't exist."""
        files: Dict[str, str] = {}
        if not workspace_path or not workspace_path.exists():
            logger.warning("workspace_path does not exist: %s", workspace_path)
            return files

        for fname, key in [
            ("main.tf",      "main_tf"),
            ("variables.tf", "variables_tf"),
            ("outputs.tf",   "outputs_tf"),
        ]:
            p = workspace_path / fname
            if p.exists():
                try:
                    files[key] = p.read_text(encoding="utf-8")
                except Exception as e:
                    logger.error("Failed to read %s: %s", p, e)

        return files

    # ── Write ─────────────────────────────────────────────────────────────────

    def write_terraform_files(self, workspace_path: Path, bundle: TerraformBundle) -> None:
        """
        Write Terraform files to disk.

        Defense-in-depth: sanitize_bundle is called here as the LAST line of
        defense before any .tf file is persisted, regardless of where the bundle
        came from (initial generation, LLM refine, or manual user edit via API).
        """
        if not workspace_path:
            raise ValueError("workspace_path is required")

        workspace_path.mkdir(parents=True, exist_ok=True)

        # Final sanitization pass — catches any REPLACE_ME / bad patterns
        # that slipped through earlier stages or were introduced by user edits
        try:
            from app.services.llm_generator import LLMGenerator
            bundle = LLMGenerator._sanitize_bundle(bundle)
            logger.debug("workspace_manager: _sanitize_bundle applied before write")
        except Exception as e:
            # Never block a write due to sanitizer failure — log and continue
            logger.warning("workspace_manager: _sanitize_bundle failed (%s) — writing unsanitized bundle", e)

        file_map = {
            "main.tf":      bundle.main_tf,
            "variables.tf": bundle.variables_tf,
            "outputs.tf":   bundle.outputs_tf,
        }
        for fname, content in file_map.items():
            if content:
                p = workspace_path / fname
                try:
                    p.write_text(content, encoding="utf-8")
                    logger.debug("Wrote %s (%d bytes)", p, len(content))
                except Exception as e:
                    logger.error("Failed to write %s: %s", p, e)
                    raise

        # Optional: GitHub Actions workflow
        if bundle.github_workflow_yaml:
            gha_dir = workspace_path / ".github" / "workflows"
            gha_dir.mkdir(parents=True, exist_ok=True)
            gha_file = gha_dir / "deploy.yml"
            try:
                gha_file.write_text(bundle.github_workflow_yaml, encoding="utf-8")
                logger.debug("Wrote GitHub Actions workflow to %s", gha_file)
            except Exception as e:
                logger.warning("Failed to write GitHub Actions workflow: %s", e)

    def write_request_json(self, workspace_path: Path, request: AgentRequest) -> None:
        """Persist the original AgentRequest so it can be reloaded later."""
        workspace_path.mkdir(parents=True, exist_ok=True)
        p = workspace_path / "request.json"
        try:
            data = {
                "request":      request.request,
                "provider":     getattr(request, "provider", "aws"),
                "auto_approve": getattr(request, "auto_approve", False),
            }
            p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            logger.debug("Wrote request.json to %s", p)
        except Exception as e:
            logger.error("Failed to write request.json: %s", e)
            raise

    def read_request_json(self, workspace_path: Path) -> Optional[Dict[str, Any]]:
        """Read back the persisted AgentRequest dict. Returns None if not found."""
        p = workspace_path / "request.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to read request.json from %s: %s", workspace_path, e)
            return None

    def workspace_exists(self, workspace_path: Path) -> bool:
        return workspace_path is not None and workspace_path.exists()

    def clean_workspace(self, workspace_path: Path) -> None:
        """Remove all .tf files and state from a workspace (used before re-generation)."""
        if not workspace_path or not workspace_path.exists():
            return
        for pattern in ("*.tf", "*.tfvars", "*.tfvars.json", "tfplan", ".terraform.lock.hcl"):
            for f in workspace_path.glob(pattern):
                try:
                    f.unlink()
                    logger.debug("Removed %s", f)
                except Exception as e:
                    logger.warning("Could not remove %s: %s", f, e)

    def get_workspace_size_bytes(self, workspace_path: Path) -> int:
        if not workspace_path or not workspace_path.exists():
            return 0
        return sum(f.stat().st_size for f in workspace_path.rglob("*") if f.is_file())