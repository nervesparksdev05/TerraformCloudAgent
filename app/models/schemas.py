"""
Pydantic schemas for API request/response validation
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

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

    # ✅ REQUIRED — no default provider
    provider: CloudProvider = Field(
        ...,
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


# ===========================
# Validation reporting
# ===========================

class ValidationStep(BaseModel):
    name: Literal["terraform_fmt", "terraform_validate", "tflint"]
    ok: bool
    output: Optional[str] = None


class ValidationReport(BaseModel):
    ok: bool = Field(..., description="Overall pass/fail")
    steps: List[ValidationStep] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)


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
    plan_output: Optional[str] = Field(None, description="Terraform plan output or summary")
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

    # ✅ new
    validation: Optional[ValidationReport] = Field(
        None,
        description="Validation results after generation/refinement"
    )

    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "run_id": "run_20260207_203000_abc123",
                "status": "planned",
                "provider": "aws",
                "log_path": "runs/run_20260207_203000_abc123",
                "validation": {
                    "ok": True,
                    "steps": [
                        {"name": "terraform_fmt", "ok": True},
                        {"name": "terraform_validate", "ok": True},
                        {"name": "tflint", "ok": True}
                    ],
                    "generated_at": "2026-02-12T10:00:00"
                }
            }
        }


class ChatRequest(BaseModel):
    """User message for the chatbot"""
    message: str = Field(..., description="User's question or instruction", min_length=1)


class ChatResponse(BaseModel):
    """Chatbot response"""
    response: str = Field(..., description="Assistant's reply")
    timestamp: str = Field(..., description="Timestamp of response")


class FeedbackCreate(BaseModel):
    """User feedback submission"""
    score: int = Field(..., ge=1, le=5, description="Rating from 1 to 5")
    comment: Optional[str] = Field(None, description="Optional text feedback")
    session_id: str = Field(..., description="Session ID this feedback belongs to")
    trace_id: Optional[str] = Field(None, description="Langfuse trace ID if available")


class FeedbackResponse(FeedbackCreate):
    """Feedback response model"""
    id: str = Field(..., description="Feedback ID")
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "fb_123456",
                "score": 5,
                "comment": "Great experience!",
                "session_id": "sess_20260212_...",
                "trace_id": "trace_abc123",
                "created_at": "2026-02-12T10:00:00"
            }
        }
