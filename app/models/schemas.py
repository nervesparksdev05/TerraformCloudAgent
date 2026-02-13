"""Pydantic schemas for API request/response validation"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


from enum import Enum

CloudProvider = Literal["aws", "gcp", "azure", "digitalocean"]


class RunStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    PLANNED = "planned"
    COST_ESTIMATED = "cost_estimated"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    APPLYING = "applying"
    COMPLETED = "completed"
    DESTROYING = "destroying"
    DESTROYED = "destroyed"
    FAILED = "failed"


class AgentRequest(BaseModel):
    """User request for infrastructure deployment"""
    request: Union[str, Dict[str, Any]] = Field(
        ...,
        description="Natural language description OR structured parameters dict",
    )

    provider: CloudProvider = Field(
        default="aws",
        description="Cloud provider (aws, gcp, azure, or digitalocean)"
    )

    auto_approve: bool = Field(
        default=False,
        description="Auto-approve terraform apply (use with caution)"
    )

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
        description="Cloud provider used: 'aws', 'gcp', 'azure', or 'digitalocean'",
    )
    log_path: str = Field(..., description="Path to run logs and workspace")

    # Optional fields populated as run progresses
    plan_output: Optional[str] = Field(None, description="Terraform plan output")
    cost_estimate: Optional[Dict[str, Any]] = Field(None, description="Cost estimation details")

    outputs: Optional[Dict[str, Any]] = Field(
        None,
        description="Terraform outputs (only present on success)"
    )
    error: Optional[str] = Field(
        None,
        description="Error message (only present on failure)"
    )

    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata for the run (e.g. conversation parameters)"
    )

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "run_id": "run_20260207_203000_abc123",
                "status": "planned",
                "provider": "aws",
                "log_path": "runs/run_20260207_203000_abc123",
                "cost_estimate": {"total_monthly_cost": "25.50", "currency": "USD"},
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
