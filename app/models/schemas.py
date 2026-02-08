"""
Pydantic models for request and response validation.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


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
    """User request for infrastructure deployment."""

    request: Optional[str] = Field(
        default="",
        description="Natural language description of desired infrastructure",
        max_length=1000,
    )
    provider: Literal["aws", "gcp"] = Field(default="aws")
    region: Optional[str] = Field(default=None)
    method: Optional[Literal["natural_language", "template"]] = Field(default="natural_language")
    template_id: Optional[str] = Field(default=None)
    template_inputs: Optional[Dict[str, Any]] = Field(default=None)
    auto_approve: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_request_content(self) -> "AgentRequest":
        if self.method == "template":
            if not self.template_id:
                raise ValueError("template_id is required when method='template'")
        else:
            if not self.request or len(self.request.strip()) < 10:
                raise ValueError("request must be at least 10 characters when method='natural_language'")
        return self


class TerraformBundle(BaseModel):
    """Generated Terraform configuration files."""

    main_tf: str = Field(..., description="main.tf content")
    variables_tf: str = Field(..., description="variables.tf content")
    outputs_tf: str = Field(..., description="outputs.tf content")


class RunResponse(BaseModel):
    """Response from a Terraform run."""

    run_id: str
    status: RunStatus
    provider: str
    log_path: str
    request: Optional[str] = None
    region: Optional[str] = None
    method: Optional[str] = "natural_language"
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    terraform_code: Optional[TerraformBundle] = None
    plan_output: Optional[str] = None
    cost_estimate: Optional[Dict[str, Any]] = None
    estimated_cost: Optional[float] = None
    resources_add: Optional[int] = 0
    resources_change: Optional[int] = 0
    resources_destroy: Optional[int] = 0
    duration: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    class Config:
        use_enum_values = True


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    response: str
    timestamp: str


class AdminConfirmRequest(BaseModel):
    confirmation: str = Field(..., min_length=1)


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class TemplateParameter(BaseModel):
    """Parameter definition for a template"""
    name: str
    label: str
    type: Literal["select", "number", "text", "boolean"]
    required: bool = True
    default: Optional[Any] = None
    options: Optional[List[Dict[str, str]]] = None
    min: Optional[int] = None
    max: Optional[int] = None
    description: Optional[str] = None


class TemplateDefinition(BaseModel):
    id: str
    name: str
    description: str
    category: str
    providers: List[str]
    chips: List[str]
    parameters: List[TemplateParameter] = []
