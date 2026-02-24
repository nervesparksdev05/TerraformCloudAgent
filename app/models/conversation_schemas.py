"""
Pydantic models for conversational parameter extraction
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ConversationStatus(str, Enum):
    """Status of conversation session"""
    ACTIVE = "active"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class ConversationSession(BaseModel):
    """Conversation session state"""
    session_id: str = Field(..., description="Unique session identifier")
    provider: str = Field(default="aws", description="Cloud provider")
    messages: List[Dict[str, str]] = Field(default_factory=list)
    collected_parameters: Dict[str, Any] = Field(default_factory=dict)
    is_complete: bool = Field(default=False)
    status: ConversationStatus = Field(default=ConversationStatus.ACTIVE)
    run_ids: List[str] = Field(default_factory=list, description="List of run IDs generated from this session")
    last_trace_id: Optional[str] = Field(None, description="Langfuse trace ID from the last LLM call, used to link feedback")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class ChatMessage(BaseModel):
    """User message in conversation"""
    message: str = Field(..., min_length=1, max_length=1000)


class ChatMessageResponse(BaseModel):
    """Response from sending a message in a conversation."""
    session_id: str
    bot_response: str
    collected_parameters: Dict[str, Any]
    is_complete: bool
    suggestions: List[str] = []
    run_id: Optional[str] = Field(None, description="Run ID if Terraform generation was triggered automatically")
    next_question: Optional[str] = None


class ConversationCreateResponse(BaseModel):
    """Response when creating new conversation"""
    session_id: str
    bot_response: str
    # ← THIS is the only change from your original file
    suggestions: List[str] = Field(
        default_factory=list,
        description="Quick-reply chips shown with the opening question",
    )


class TerraformGenerationRequest(BaseModel):
    """Request to generate Terraform from conversation"""
    session_id: str

class FeedbackRequest(BaseModel):
    """User feedback for LLM context gathering"""
    rating: int = Field(..., ge=1, le=5, description="Star rating from 1 to 5")
    comment: Optional[str] = Field(None, description="Optional feedback comment")
