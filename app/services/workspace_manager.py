"""
Workspace management for Terraform runs.

Aligned with the updated flow:
- RunManager is the single source of truth for run_id creation.
- WorkspaceManager focuses on file I/O inside an existing run workspace:
  - write/read Terraform files
  - write request.json (if needed)
  - optional log path + cleanup + list

Notes:
- Avoids duplicate run_id generation (was causing collisions/inconsistency).
- Adds small safety helpers (ensure dir exists, atomic-ish writes).
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict

from app.core.logger import get_logger
from app.models.schemas import TerraformBundle, AgentRequest

logger = get_logger(__name__)


class WorkspaceManager:
    """Manages file operations inside Terraform run workspaces."""

    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Workspace manager initialized: %s", self.base_dir.absolute())

    # ================================================================
    # TERRAFORM FILE I/O
    # ================================================================

    def write_terraform_files(self, workspace_path: Path, bundle: TerraformBundle) -> None:
        """
        Write Terraform files to workspace.

        Args:
            workspace_path: Existing run workspace directory
            bundle: TerraformBundle containing main/variables/outputs
        """
        self._ensure_dir(workspace_path)

        files = {
            "main.tf": bundle.main_tf,
            "variables.tf": bundle.variables_tf,
            "outputs.tf": bundle.outputs_tf,
        }

        for filename, content in files.items():
            self._write_text(workspace_path / filename, content or "")
            logger.debug("Wrote %s (%d bytes)", filename, len(content or ""))

    def read_terraform_files(self, workspace_path: Path) -> Dict[str, str]:
        """
        Read Terraform files from workspace.

        Returns:
            Dict with keys: main.tf, variables.tf, outputs.tf
        """
        files = ["main.tf", "variables.tf", "outputs.tf"]
        content: Dict[str, str] = {}

        for filename in files:
            file_path = workspace_path / filename
            content[filename] = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        return content

    # ================================================================
    # REQUEST JSON (AUDIT)
    # ================================================================

    def write_request_json(self, workspace_path: Path, request: AgentRequest) -> None:
        """
        Write original request to workspace for audit/debug.

        Args:
            workspace_path: Existing run workspace directory
            request: Original AgentRequest
        """
        self._ensure_dir(workspace_path)

        request_file = workspace_path / "request.json"
        request_data = request.model_dump()  # Pydantic v2
        request_data["timestamp"] = datetime.now().isoformat()

        request_file.write_text(json.dumps(request_data, indent=2), encoding="utf-8")
        logger.debug("Wrote request.json")

    # ================================================================
    # LOGS / CLEANUP / LIST
    # ================================================================

    def get_log_path(self, workspace_path: Path) -> Path:
        """Get path for Terraform execution logs (if you choose to write logs)."""
        return workspace_path / "terraform.log"

    def cleanup_workspace(self, workspace_path: Path) -> None:
        """Delete a workspace directory."""
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
            logger.info("Cleaned up workspace: %s", workspace_path.name)

    def list_workspaces(self) -> list:
        """List all workspace directories."""
        if not self.base_dir.exists():
            return []
        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    # ================================================================
    # INTERNALS
    # ================================================================

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        # Simple write; if you want atomic writes later:
        # write to temp file then replace.
        path.write_text(content, encoding="utf-8")
