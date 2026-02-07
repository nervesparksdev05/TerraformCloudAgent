"""
Background task workflows for async Terraform operations
"""
import asyncio
from pathlib import Path
from typing import Optional

from app.core.logger import get_logger
from app.models.schemas import RunStatus, AgentRequest, TerraformBundle
from app.services.run_manager import RunManager
from app.services.llm_generator import LLMGenerator
from app.services.security_checker import SecurityChecker
from app.services.workspace_manager import WorkspaceManager
from app.services.terraform_runner import TerraformRunner

logger = get_logger(__name__)

class WorkflowEngine:
    """Handles background execution of Terraform workflows"""
    
    def __init__(self):
        self.run_manager = RunManager()
        self.llm_generator = LLMGenerator()
        self.security_checker = SecurityChecker()
        self.workspace_manager = WorkspaceManager()
    
    async def execute_planning_phase(
        self, 
        run_id: str, 
        request: Optional[AgentRequest] = None,
        feedback: Optional[str] = None
    ) -> None:
        """
        Background task: Generate or refine Terraform plan
        Transitions: CREATED/PLANNING -> PLANNING -> PLANNED (or FAILED)
        """
        try:
            # Update status to PLANNING
            self.run_manager.update_run_status(run_id, RunStatus.PLANNING)
            
            # Fetch run data if request not provided (refinement case)
            if not request:
                run = self.run_manager.get_run(run_id)
                if not run:
                    raise ValueError(f"Run {run_id} not found")
                # Construct pseudo-request from run data for context
                request = AgentRequest(
                    request=run.request,
                    provider=run.provider
                )
                
            logger.info(f"[{run_id}] Starting planning phase (Refinement: {bool(feedback)})")
            
            workspace_path = self.run_manager.get_workspace_path(run_id)
            
            # Generate or Refine Terraform code
            if feedback:
                # Load current code from workspace (or could be passed in)
                # For now, we'll assume the workspace has the current state
                # In a real app, might want to read main.tf/variables.tf into memory
                # But refine_terraform expects a dict.
                # Let's read the bundle from file if possible or reconstruction
                # Simpler: The LLM needs the code. 
                # Let's read the files we wrote previously.
                current_code = self.workspace_manager.read_terraform_files(workspace_path)
                
                bundle = self.llm_generator.refine_terraform(
                    base_request=request.request,
                    current_code=current_code,
                    feedback=feedback,
                    provider=request.provider
                )
            else:
                bundle = self.llm_generator.generate_terraform(
                    request.request, 
                    provider=request.provider
                )
            
            # Security validation
            validation = self.security_checker.validate(bundle, provider=request.provider)
            
            if not validation["valid"]:
                error_msg = f"Security validation failed: {validation['reason']}"
                logger.error(f"[{run_id}] {error_msg}")
                self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=error_msg)
                return
            
            # Write Terraform files to workspace
            self.workspace_manager.write_terraform_files(workspace_path, bundle)
            if not feedback: # Only write request on first pass
                self.workspace_manager.write_request_json(workspace_path, request)
            
            # Run terraform plan (non-destructive)
            plan_output = await self._run_terraform_plan(workspace_path)
            
            # Update run state with plan
            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.PLANNED
                run.plan_output = plan_output
                self.run_manager.save_run_state(run_id, run)
            
            logger.info(f"[{run_id}] Planning phase complete")
            
        except Exception as e:
            logger.error(f"[{run_id}] Planning failed: {str(e)}")
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))
    
    async def execute_apply_phase(self, run_id: str) -> None:
        """
        Background task: Apply Terraform plan
        Transitions: APPROVED -> APPLYING -> COMPLETED (or FAILED)
        """
        try:
            # Update status
            self.run_manager.update_run_status(run_id, RunStatus.APPLYING)
            logger.info(f"[{run_id}] Starting apply phase")
            
            workspace_path = self.run_manager.get_workspace_path(run_id)
            
            # Run terraform apply
            outputs = await self._run_terraform_apply(workspace_path)
            
            # Update run state with outputs
            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.COMPLETED
                run.outputs = outputs
                self.run_manager.save_run_state(run_id, run)
            
            logger.info(f"[{run_id}] Apply phase complete")
            
        except Exception as e:
            logger.error(f"[{run_id}] Apply failed: {str(e)}")
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))
    
    async def execute_destroy_phase(self, run_id: str) -> None:
        """
        Background task: Destroy Terraform infrastructure
        Transitions: COMPLETED -> DESTROYING -> DESTROYED (or FAILED)
        """
        try:
            # Update status
            self.run_manager.update_run_status(run_id, RunStatus.DESTROYING)
            logger.info(f"[{run_id}] Starting destroy phase")
            
            workspace_path = self.run_manager.get_workspace_path(run_id)
            
            # Run terraform destroy
            await self._run_terraform_destroy(workspace_path)
            
            # Update run state
            run = self.run_manager.get_run(run_id)
            if run:
                run.status = RunStatus.DESTROYED
                run.outputs = None  # Clear outputs since resources are gone
                self.run_manager.save_run_state(run_id, run)
            
            logger.info(f"[{run_id}] Destroy phase complete")
            
        except Exception as e:
            logger.error(f"[{run_id}] Destroy failed: {str(e)}")
            self.run_manager.update_run_status(run_id, RunStatus.FAILED, error=str(e))
    
    async def _run_terraform_plan(self, workspace_path: Path) -> str:
        """Run terraform init + plan and return output"""
        # This is a simplified version - in production, use proper async subprocess
        import subprocess
        
        # Init
        subprocess.run(
            ["terraform", "init"],
            cwd=workspace_path,
            check=True,
            capture_output=True
        )
        
        # Plan
        result = subprocess.run(
            ["terraform", "plan", "-no-color"],
            cwd=workspace_path,
            check=True,
            capture_output=True,
            text=True
        )
        
        return result.stdout
    
    async def _run_terraform_apply(self, workspace_path: Path) -> dict:
        """Run terraform apply and return outputs"""
        import subprocess
        import json
        
        # Apply
        subprocess.run(
            ["terraform", "apply", "-auto-approve", "-no-color"],
            cwd=workspace_path,
            check=True,
            capture_output=True
        )
        
        # Get outputs
        result = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=workspace_path,
            check=True,
            capture_output=True,
            text=True
        )
        
        return json.loads(result.stdout) if result.stdout else {}
    
    async def _run_terraform_destroy(self, workspace_path: Path) -> None:
        """Run terraform destroy"""
        import subprocess
        
        # Destroy all infrastructure
        subprocess.run(
            ["terraform", "destroy", "-auto-approve", "-no-color"],
            cwd=workspace_path,
            check=True,
            capture_output=True
        )
        
        logger.debug(f"Terraform destroy completed for {workspace_path}")
