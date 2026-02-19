"""
Service for managing run state and persistence using file-based storage
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import RunResponse, RunStatus, AgentRequest, TerraformBundle

import re
logger = get_logger(__name__)

RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

class RunManager:
    """Manages the lifecycle and persistence of Terraform runs"""
    
    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)

    def _validate_run_id(self, run_id: str) -> str:
        """Validate run_id to prevent path traversal"""
        if not RUN_ID_PATTERN.match(run_id):
            # Log security warning but raise ValueError
            logger.warning(f"Invalid run_id attempt: {run_id}")
            raise ValueError(f"Invalid run_id: {run_id}")
        return run_id

    def create_run(self, request: AgentRequest) -> RunResponse:
        """Initialize a new run workspace and state"""
        # Generate ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}"
        
        # Create workspace
        workspace_path = self.base_dir / run_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        # Initial State
        run_state = RunResponse(
            run_id=run_id,
            status=RunStatus.CREATED,
            provider=request.provider,
            log_path=str(workspace_path.absolute()),
            outputs=None
        )
        
        # Save request and initial state
        self._save_request(workspace_path, request)
        self.save_run_state(run_id, run_state)
        
        logger.info(f"Created run: {run_id}")
        return run_state

    def get_run(self, run_id: str) -> Optional[RunResponse]:
        """Load run state from disk"""
        try:
            self._validate_run_id(run_id)
        except ValueError:
            return None
            
        workspace_path = self.base_dir / run_id
        state_file = workspace_path / "state.json"
        
        if not state_file.exists():
            return None
            
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return RunResponse(**data)
        except Exception as e:
            logger.error(f"Failed to load run state for {run_id}: {e}")
            return None

    def save_run_state(self, run_id: str, state: RunResponse) -> None:
        """Persist run state to disk"""
        self._validate_run_id(run_id)
        workspace_path = self.base_dir / run_id
        state_file = workspace_path / "state.json"
        
        # Use model_dump_json for Pydantic v2
        state_json = state.model_dump_json(indent=2)
        state_file.write_text(state_json, encoding="utf-8")
        logger.debug(f"Saved state for {run_id}")

    def update_run_status(self, run_id: str, status: RunStatus, error: Optional[str] = None) -> Optional[RunResponse]:
        """Update status and optional error message"""
        run = self.get_run(run_id)
        if not run:
            return None
            
        run.status = status
        if error:
            run.error = error
            
        self.save_run_state(run_id, run)
        return run
    
    def get_workspace_path(self, run_id: str) -> Path:
        """Get absolute path to workspace directory"""
        self._validate_run_id(run_id)
        return (self.base_dir / run_id).absolute()

    def get_run_files(self, run_id: str) -> Dict[str, str]:
        """Read Terraform files from workspace and return a dict"""
        workspace_path = self.get_workspace_path(run_id)
        files = {}
        
        # Standard Terraform files to look for
        file_map = {
            "main.tf": "main.tf",
            "variables.tf": "variables.tf",
            "outputs.tf": "outputs.tf"
        }
        
        for filename, key in file_map.items():
            p = workspace_path / filename
            if p.exists():
                try:
                    files[key] = p.read_text(encoding="utf-8")
                    logger.debug(f"Read {filename} for {run_id}")
                except Exception as e:
                    logger.error(f"Failed to read {filename} for {run_id}: {e}")
                    
        return files
        
    def _save_request(self, workspace_path: Path, request: AgentRequest) -> None:
        """Save original request for audit"""
        request_file = workspace_path / "request.json"
        # model_dump is Pydantic v2
        data = request.model_dump()
        data["timestamp"] = datetime.now().isoformat()
        request_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
