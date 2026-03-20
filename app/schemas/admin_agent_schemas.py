"""
Admin Agent Schemas
====================
Pydantic schemas for admin agent API.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class AdminChatRequest(BaseModel):
    message: str = Field(..., description="User message in Thai or English", min_length=1)
    conversation_id: Optional[int] = Field(None, description="Existing conversation ID to continue")


class ToolCallInfo(BaseModel):
    tool_name: str
    tool_args: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None


class PendingConfirmation(BaseModel):
    tool_name: str
    tool_args: Dict[str, Any]
    description: str
    message: str


class AdminChatResponse(BaseModel):
    response: str = Field(..., description="Agent response text (Thai)")
    tool_calls: List[ToolCallInfo] = Field(default_factory=list)
    pending_confirmation: Optional[PendingConfirmation] = None
    conversation_id: int


class AdminConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="Whether to confirm the action")


class ConversationSummary(BaseModel):
    id: int
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str = ""
    tool_name: Optional[str] = None
    tool_args: Optional[str] = None
    tool_result: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConversationDetail(BaseModel):
    id: int
    title: str
    created_at: Optional[datetime] = None
    messages: List[MessageResponse] = []
