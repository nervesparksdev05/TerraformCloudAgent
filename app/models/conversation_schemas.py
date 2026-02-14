"""
Pydantic models for README-driven conversation flow.

Aligned changes:
- provider is REQUIRED (no default)
- removed form_fields and user_form_input (LLM conversation fills gaps)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

CloudProvider = Literal["aws", "gcp", "azure", "digitalocean"]


class ConversationStatus(str, Enum):
    """Status of conversation session"""
    ACTIVE = "active"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class ConversationSession(BaseModel):
    """Conversation session state"""
    session_id: str = Field(..., description="Unique session identifier")

    # Provider is optional initially (collected via chat)
    provider: Optional[CloudProvider] = Field(None, description="Cloud provider")

    github_url: str = Field(..., description="GitHub repository URL (required)")

    messages: List[Dict[str, Any]] = Field(default_factory=list)
    collected_parameters: Dict[str, Any] = Field(default_factory=dict)

    is_complete: bool = Field(default=False)
    status: ConversationStatus = Field(default=ConversationStatus.ACTIVE)

    run_ids: List[str] = Field(default_factory=list, description="Run IDs generated from this session")

    turn_count: int = Field(default=0, description="Number of interactions in this session")
    topics_addressed: List[str] = Field(default_factory=list, description="Topics already covered in dialogue")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # README-driven fields (kept)
    readme_content: Optional[str] = Field(None, description="Fetched README content")
    readme_analysis: Optional[Dict[str, Any]] = Field(None, description="LLM analysis of README")

    class Config:
        use_enum_values = True


class ChatMessage(BaseModel):
    """User message in conversation"""
    message: str = Field(..., min_length=1, max_length=2000)


class ChatMessageResponse(BaseModel):
    """Response from sending a message in a conversation."""
    session_id: str
    bot_response: str
    collected_parameters: Dict[str, Any]
    is_complete: bool

    suggestions: List[str] = Field(default_factory=list)

    run_id: Optional[str] = Field(None, description="Run ID if Terraform generation was triggered automatically")
    next_question: Optional[str] = None

    # README-driven fields
    readme_preview: Optional[str] = Field(None, description="README content preview")
    readme_analysis_summary: Optional[Dict[str, Any]] = Field(None, description="Summary of README analysis")


class ConversationCreateResponse(BaseModel):
    """Response when creating new conversation"""
    session_id: str
    bot_response: str
    suggestions: List[str] = Field(
        default_factory=list,
        description="Quick-reply chips shown with the opening question",
    )


class TerraformGenerationRequest(BaseModel):
    """Request to generate Terraform from conversation"""
    session_id: str
