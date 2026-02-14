"""
Service for managing run state and persistence using file-based storage.

Aligned with README-driven multi-cloud flow:
- Run workspace contains:
  - request.json  (original AgentRequest + timestamp)
  - state.json    (RunResponse)
  - main.tf / variables.tf / outputs.tf (written by WorkspaceManager)
- Run IDs are unique (timestamp + random suffix) to avoid collisions in fast consecutive runs.
"""

import json
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional

from app.core.logger import get_logger
from app.models.schemas import RunResponse, RunStatus, AgentRequest

logger = get_logger(__name__)


class RunManager:
    """Manages the lifecycle and persistence of Terraform runs."""

    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_run(self, request: AgentRequest) -> RunResponse:
        """Initialize a new run workspace and initial state."""
        run_id = self._new_run_id()

        workspace_path = self.base_dir / run_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        run_state = RunResponse(
            run_id=run_id,
            status=RunStatus.CREATED,
            provider=request.provider,
            log_path=str(workspace_path.absolute()),
            outputs=None,
        )

        self._save_request(workspace_path, request)
        self.save_run_state(run_id, run_state)

        logger.info("Created run: %s", run_id)
        return run_state

    def get_run(self, run_id: str) -> Optional[RunResponse]:
        """Load run state from disk."""
        state_file = (self.base_dir / run_id / "state.json")
        if not state_file.exists():
            return None

        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return RunResponse(**data)
        except Exception as e:
            logger.error("Failed to load run state for %s: %s", run_id, e)
            return None

    def save_run_state(self, run_id: str, state: RunResponse) -> None:
        """Persist run state to disk."""
        workspace_path = self.base_dir / run_id
        workspace_path.mkdir(parents=True, exist_ok=True)

        state_file = workspace_path / "state.json"
        state_file.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("Saved state for %s", run_id)

    def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        error: Optional[str] = None
    ) -> Optional[RunResponse]:
        """Update status and optional error message."""
        run = self.get_run(run_id)
        if not run:
            return None

        run.status = status
        if error:
            run.error = error

        self.save_run_state(run_id, run)
        return run

    def get_workspace_path(self, run_id: str) -> Path:
        """Get absolute path to workspace directory."""
        return (self.base_dir / run_id).absolute()

    # ================================================================
    # INTERNALS
    # ================================================================

    def _new_run_id(self) -> str:
        # Prevent collisions if multiple runs created in same second
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = secrets.token_hex(3)  # 6 hex chars
        return f"run_{ts}_{suffix}"

    def _save_request(self, workspace_path: Path, request: AgentRequest) -> None:
        """Save original request for audit/debug."""
        request_file = workspace_path / "request.json"
        data = request.model_dump()  # Pydantic v2
        data["timestamp"] = datetime.now().isoformat()
        request_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

