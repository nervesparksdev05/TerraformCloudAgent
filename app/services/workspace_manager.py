"""
Workspace management for Terraform runs
"""
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Tuple

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import TerraformBundle, AgentRequest

logger = get_logger(__name__)


class WorkspaceManager:
    """Manages isolated workspaces for Terraform runs"""
    
    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        logger.info(f"Workspace manager initialized: {self.base_dir.absolute()}")
    
    def create_run_workspace(self) -> Tuple[str, Path]:
        """
        Create a new isolated workspace for a run
        
        Returns:
            Tuple of (run_id, workspace_path)
        """
        # Generate unique run ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}"
        
        # Create workspace directory
        workspace_path = self.base_dir / run_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created workspace: {run_id}")
        return run_id, workspace_path
    
    def write_terraform_files(self, workspace_path: Path, bundle: TerraformBundle) -> None:
        """
        Write Terraform files to workspace
        
        Args:
            workspace_path: Path to workspace directory
            bundle: TerraformBundle containing the code
        """
        files = {
            "main.tf": bundle.main_tf,
            "variables.tf": bundle.variables_tf,
            "outputs.tf": bundle.outputs_tf
        }
        
        for filename, content in files.items():
            file_path = workspace_path / filename
            file_path.write_text(content, encoding="utf-8")
            logger.debug(f"Wrote {filename} ({len(content)} bytes)")

        # Handle CI/CD workflow
        if bundle.github_workflow_yaml:
            workflow_path = workspace_path / ".github" / "workflows"
            workflow_path.mkdir(parents=True, exist_ok=True)
            (workflow_path / "deploy.yml").write_text(bundle.github_workflow_yaml, encoding="utf-8")
            logger.debug(f"Wrote .github/workflows/deploy.yml ({len(bundle.github_workflow_yaml)} bytes)")
    
    def read_terraform_files(self, workspace_path: Path) -> dict:
        """
        Read Terraform files from workspace
        
        Args:
            workspace_path: Path to workspace directory
            
        Returns:
            Dictionary with main.tf, variables.tf, outputs.tf content
        """
        files = ["main.tf", "variables.tf", "outputs.tf"]
        content = {}
        
        try:
            for filename in files:
                file_path = workspace_path / filename
                if file_path.exists():
                    content[filename] = file_path.read_text(encoding="utf-8")
                else:
                    content[filename] = ""
            return content
        except Exception as e:
            logger.error(f"Error reading terraform files: {str(e)}")
            return {}
    
    def write_request_json(self, workspace_path: Path, request: AgentRequest) -> None:
        """
        Write original request to workspace for reference
        
        Args:
            workspace_path: Path to workspace directory
            request: Original user request
        """
        request_file = workspace_path / "request.json"
        request_data = {
            "request": request.request,
            "provider": request.provider,
            "auto_approve": request.auto_approve,
            "timestamp": datetime.now().isoformat()
        }
        request_file.write_text(json.dumps(request_data, indent=2), encoding="utf-8")
        logger.debug("Wrote request.json")
    
    def get_log_path(self, workspace_path: Path) -> Path:
        """Get path for Terraform execution logs"""
        return workspace_path / "terraform.log"
    
    def cleanup_workspace(self, workspace_path: Path) -> None:
        """
        Delete a workspace directory
        
        Args:
            workspace_path: Path to workspace to delete
        """
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
            logger.info(f"Cleaned up workspace: {workspace_path.name}")
    
    def list_workspaces(self) -> list:
        """List all workspace directories"""
        if not self.base_dir.exists():
            return []
        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]
