"""
Admin Agent API Endpoints
==========================
Chat interface for admin tool-calling agent.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.models.admin_agent import AdminAgentConversation, AdminAgentMessage
from app.schemas.admin_agent_schemas import (
    AdminChatRequest,
    AdminChatResponse,
    AdminConfirmRequest,
    ConversationSummary,
    ConversationDetail,
    MessageResponse,
)
from app.services.admin_agent import AdminAgent

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/agent/chat", response_model=AdminChatResponse)
async def agent_chat(
    request: AdminChatRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Chat with the Admin Agent. Supports tool calling and confirmation flow."""
    agent = AdminAgent(db)

    result = await agent.chat(
        message=request.message,
        conversation_id=request.conversation_id,
        user_id=current_user.id,
    )

    return AdminChatResponse(**result)


@router.post("/agent/chat/{conversation_id}/confirm", response_model=AdminChatResponse)
async def agent_confirm(
    conversation_id: int,
    request: AdminConfirmRequest = AdminConfirmRequest(),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Confirm a pending tool action in a conversation."""
    if not request.confirmed:
        return AdminChatResponse(
            response="ยกเลิกการดำเนินการ",
            tool_calls=[],
            pending_confirmation=None,
            conversation_id=conversation_id,
        )

    agent = AdminAgent(db)
    result = await agent.confirm_action(
        conversation_id=conversation_id,
        user_id=current_user.id,
    )

    return AdminChatResponse(**result)


@router.get("/agent/conversations", response_model=List[ConversationSummary])
def list_conversations(
    limit: int = 20,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """List admin agent conversations for the current user."""
    conversations = db.query(AdminAgentConversation).filter(
        AdminAgentConversation.user_id == current_user.id
    ).order_by(AdminAgentConversation.updated_at.desc()).limit(limit).all()

    result = []
    for conv in conversations:
        msg_count = db.query(AdminAgentMessage).filter(
            AdminAgentMessage.conversation_id == conv.id
        ).count()

        result.append(ConversationSummary(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
        ))

    return result


@router.get("/agent/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Get a conversation with all messages."""
    conv = db.query(AdminAgentConversation).filter(
        AdminAgentConversation.id == conversation_id,
        AdminAgentConversation.user_id == current_user.id,
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(AdminAgentMessage).filter(
        AdminAgentMessage.conversation_id == conversation_id
    ).order_by(AdminAgentMessage.created_at).all()

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )
