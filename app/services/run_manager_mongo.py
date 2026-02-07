"""
Service for managing run state and persistence using MongoDB
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from app.core import config
from app.core.logger import get_logger
from app.core.database import db
from app.models.schemas import RunResponse, RunStatus, AgentRequest

logger = get_logger(__name__)

class RunManager:
    """Manages the lifecycle and persistence of Terraform runs (MongoDB-backed)"""
    
    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.use_mongodb = db.is_connected
        
        if self.use_mongodb:
            logger.info("✅ RunManager using MongoDB persistence")
        else:
            logger.warning("⚠️  RunManager using file-based fallback")

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
        """Load run state from MongoDB or disk"""
        if self.use_mongodb:
            # Try MongoDB first
            run_data = db.get_run(run_id)
            if run_data:
                try:
                    return RunResponse(**run_data)
                except Exception as e:
                    logger.error(f"Failed to parse run data: {e}")
                    return None
        
        # Fallback to file-based
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
        """Persist run state to MongoDB and/or disk"""
        # Convert to dict
        state_dict = state.model_dump()
        
        if self.use_mongodb:
            # Save to MongoDB
            existing = db.get_run(run_id)
            if existing:
                db.update_run(run_id, state_dict)
            else:
                db.insert_run(state_dict)
        
        # Always save to file as backup
        workspace_path = self.base_dir / run_id
        state_file = workspace_path / "state.json"
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
        return (self.base_dir / run_id).absolute()
    
    def save_chat_message(self, run_id: str, role: str, content: str) -> bool:
        """Save a chat message to MongoDB"""
        if self.use_mongodb:
            return db.save_chat_message(run_id, role, content)
        return False
    
    def get_chat_history(self, run_id: str) -> list:
        """Get chat history from MongoDB"""
        if self.use_mongodb:
            return db.get_chat_history(run_id)
        return []
        
    def _save_request(self, workspace_path: Path, request: AgentRequest) -> None:
        """Save original request for audit"""
        request_file = workspace_path / "request.json"
        data = request.model_dump()
        data["timestamp"] = datetime.now().isoformat()
        request_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
