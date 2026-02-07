"""
Terraform CLI execution wrapper
"""
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from contextlib import contextmanager

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)


class TerraformRunner:
    """Executes Terraform CLI commands and manages pipeline"""
    
    def __init__(self, workspace_path: Path, log_path: Path):
        self.workspace_path = workspace_path
        self.log_path = log_path
        self.log_file = None
        
    def __enter__(self):
        """Context manager entry - open log file"""
        self.log_file = open(self.log_path, "w", encoding="utf-8")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close log file"""
        if self.log_file:
            self.log_file.close()
    
    def run_pipeline(self, action: str = "apply") -> Tuple[bool, str, Optional[Dict[str, Any]], str]:
        """
        Run complete Terraform pipeline
        
        Args:
            action: 'apply' or 'destroy'
            
        Returns:
            Tuple of (success, plan_summary, outputs, error_message)
        """
        logger.info(f"Starting Terraform pipeline: {action}")
        
        # Step 1: terraform init
        if not self._run_init():
            return False, "", None, "Terraform init failed"
        
        # Step 2: terraform plan
        plan_summary = self._run_plan()
        if not plan_summary:
            return False, "", None, "Terraform plan failed"
        
        # Step 3: terraform apply/destroy
        if action == "apply":
            if not self._run_apply():
                return False, plan_summary, None, "Terraform apply failed"
        elif action == "destroy":
            if not self._run_destroy():
                return False, plan_summary, None, "Terraform destroy failed"
        else:
            return False, "", None, f"Invalid action: {action}"
        
        # Step 4: Get outputs (only for apply)
        outputs = None
        if action == "apply":
            outputs = self._get_outputs()
        
        logger.info(f"Terraform pipeline completed successfully")
        return True, plan_summary, outputs, ""
    
    def _run_init(self) -> bool:
        """Run terraform init"""
        logger.info("Running: terraform init")
        return self._run_command(["terraform", "init", "-no-color"])
    
    def _run_plan(self) -> str:
        """Run terraform plan and return summary"""
        logger.info("Running: terraform plan")
        success = self._run_command(["terraform", "plan", "-no-color", "-out=tfplan"])
        return "Plan created" if success else ""
    
    def _run_apply(self) -> bool:
        """Run terraform apply"""
        logger.info("Running: terraform apply")
        return self._run_command(["terraform", "apply", "-auto-approve", "-no-color", "tfplan"])
    
    def _run_destroy(self) -> bool:
        """Run terraform destroy"""
        logger.info("Running: terraform destroy")
        return self._run_command(["terraform", "destroy", "-auto-approve", "-no-color"])
    
    def _get_outputs(self) -> Optional[Dict[str, Any]]:
        """Get terraform outputs as JSON"""
        logger.info("Getting Terraform outputs")
        try:
            result = subprocess.run(
                ["terraform", "output", "-json"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                outputs_raw = json.loads(result.stdout)
                # Extract values from Terraform output format
                outputs = {k: v.get("value") for k, v in outputs_raw.items()}
                logger.info(f"Retrieved {len(outputs)} outputs")
                return outputs
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get outputs: {str(e)}")
            return None
    
    def _run_command(self, cmd: list) -> bool:
        """
        Run a Terraform command
        
        Args:
            cmd: Command and arguments as list
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.debug(f"Executing: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=config.TERRAFORM_TIMEOUT
            )
            
            # Write to log file
            if self.log_file:
                self.log_file.write(f"\n{'='*60}\n")
                self.log_file.write(f"Command: {' '.join(cmd)}\n")
                self.log_file.write(f"{'='*60}\n")
                self.log_file.write(result.stdout)
                if result.stderr:
                    self.log_file.write("\nSTDERR:\n")
                    self.log_file.write(result.stderr)
                self.log_file.flush()
            
            if result.returncode != 0:
                logger.error(f"Command failed with exit code {result.returncode}")
                logger.error(f"Error: {result.stderr}")
                return False
            
            logger.debug(f"Command succeeded")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {config.TERRAFORM_TIMEOUT}s")
            return False
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            return False
