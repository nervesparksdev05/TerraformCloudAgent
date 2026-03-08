"""Pydantic schemas for API request/response validation"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


from enum import Enum

CloudProvider = Literal["aws", "gcp", "digitalocean"]


class RunStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    PLANNED = "planned"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    APPLYING = "applying"
    COMPLETED = "completed"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    FAILED = "failed"
    REJECTED = "rejected"


class AgentRequest(BaseModel):
    """User request for infrastructure deployment"""
    request: Union[str, Dict[str, Any]] = Field(
        ...,
        description="Natural language description OR structured parameters dict",
    )

    provider: CloudProvider = Field(
        default="aws",
        description="Cloud provider (aws, gcp, or digitalocean)"
    )

    auto_approve: bool = Field(
        default=False,
        description="Auto-approve terraform apply (use with caution)"
    )

    user_id: Optional[str] = Field(None, description="ID of the user who triggered this request")
    username: Optional[str] = Field(None, description="Username/Email of the user who triggered this request")

    class Config:
        json_schema_extra = {
            "example": {
                "request": "Create a web server with HTTP and HTTPS access",
                "provider": "aws",
                "auto_approve": False
            }
        }


class TerraformBundle(BaseModel):
    """Generated Terraform configuration files"""
    main_tf: str = Field(..., description="Main Terraform configuration (main.tf)")
    variables_tf: str = Field(..., description="Variables definition (variables.tf)")
    outputs_tf: str = Field(..., description="Outputs definition (outputs.tf)")
    github_workflow_yaml: Optional[str] = Field(None, description="Generated GitHub Actions workflow (deploy.yml)")

    class Config:
        json_schema_extra = {
            "example": {
                "main_tf": "terraform { ... }",
                "variables_tf": "variable \"instance_type\" { ... }",
                "outputs_tf": "output \"instance_id\" { ... }"
            }
        }


class RunResponse(BaseModel):
    """Response from a Terraform run (State)"""
    run_id: str = Field(..., description="Unique identifier for this run")
    status: RunStatus = Field(..., description="Current status of the run")
    provider: CloudProvider = Field(
        ...,
        description="Cloud provider used: 'aws', 'gcp', or 'digitalocean'",
    )
    log_path: str = Field(..., description="Path to run logs and workspace")

    # Optional fields populated as run progresses
    plan_output: Optional[str] = Field(None, description="Terraform plan output")
    topology_diagram: Optional[str] = Field(None, description="Architecture diagram (Mermaid syntax)")

    outputs: Optional[Dict[str, Any]] = Field(
        None,
        description="Terraform outputs (only present on success)"
    )
    error: Optional[str] = Field(
        None,
        description="Error message (only present on failure)"
    )

    self_healer_diagnosis: Optional[Dict[str, Any]] = Field(
        None,
        description="Autonomous diagnostic result for deployment failures"
    )

    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata for the run (e.g. conversation parameters)"
    )

    approval_info: Optional[Dict[str, Any]] = Field(
        None,
        description="Approval details (email sent, token, rejection reason)"
    )

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "run_id": "run_20260207_203000_abc123",
                "status": "planned",
                "provider": "aws",
                "log_path": "runs/run_20260207_203000_abc123",
                "outputs": None
            }
        }


class ChatRequest(BaseModel):
    """User message for the chatbot"""
    message: str = Field(..., description="User's question or instruction", min_length=1)


class ChatResponse(BaseModel):
    """Chatbot response"""
    response: str = Field(..., description="Assistant's reply")
    timestamp: str = Field(..., description="Timestamp of response")
