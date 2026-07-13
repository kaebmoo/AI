from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import json
import logging

from app.api import deps
from app.models.user import User
from app.models.chat import ChatHistory
from app.models.conversation import Conversation
from app.core.time_utils import utcnow
from app.providers.chart_postprocessor import compact_explanation_currency

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---

class ConversationItem(BaseModel):
    id: str
    title: Optional[str] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0
    preview: Optional[str] = None


class ConversationListResponse(BaseModel):
    items: List[ConversationItem]
    total: int
    page: int
    page_size: int


class ConversationMessageItem(BaseModel):
    id: int
    question: str
    ai_response: Optional[str] = None
    created_at: Optional[datetime] = None
    generated_sql: Optional[str] = None
    sql_result_summary: Optional[str] = None
    tokens_used: int = 0
    context_name: Optional[str] = None
    is_bookmarked: bool = False
    feedback_rating: Optional[int] = None
    execution_time_ms: float = 0.0
    # F12: render payload สำหรับ restore กราฟ/ตาราง/pivot ตอนเปิดประวัติ
    data: Optional[List[Dict[str, Any]]] = None
    visualization: Optional[str] = None
    chart_config: Optional[Dict[str, Any]] = None
    display_hint: Optional[str] = None
    hierarchy_columns: Optional[List[str]] = None
    warnings: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[Dict[str, Any]] = None
    data_truncated: bool = False


class ConversationDetailResponse(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0
    messages: List[ConversationMessageItem] = []


class ConversationCreateResponse(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: Optional[datetime] = None


class ConversationUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    is_archived: Optional[bool] = None


class ConversationUpdateResponse(BaseModel):
    id: str
    title: Optional[str] = None
    updated_at: Optional[datetime] = None


def _safe_json(text_val, default=None):
    """F12: parse JSON แบบกันพัง — แถวเก่า (NULL) หรือ JSON เสีย คืน default แทนที่จะ 500"""
    if not text_val:
        return default
    try:
        return json.loads(text_val)
    except (ValueError, TypeError):
        logger.warning("Corrupted render payload JSON in chat_history — returning None")
        return default


# --- Endpoints ---

@router.get("/", response_model=ConversationListResponse)
def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """List conversations for the current user, ordered by most recent activity."""
    query = db.query(Conversation).filter(
        Conversation.user_id == current_user.id,
        Conversation.is_archived == False,
    )

    if search:
        query = query.filter(Conversation.title.ilike(f"%{search}%"))

    total = query.count()

    conversations = query.order_by(desc(Conversation.updated_at)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = []
    for conv in conversations:
        # Get preview from latest message
        latest_msg = db.query(ChatHistory.question).filter(
            ChatHistory.conversation_id == conv.id
        ).order_by(desc(ChatHistory.created_at)).first()

        preview = None
        if latest_msg and latest_msg.question:
            preview = latest_msg.question[:80]
            if len(latest_msg.question) > 80:
                preview += "..."

        items.append(ConversationItem(
            id=conv.id,
            title=conv.title,
            updated_at=conv.updated_at,
            message_count=conv.message_count,
            preview=preview,
        ))

    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """Get a single conversation with all its messages."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this conversation")

    # Get messages ordered by created_at ASC
    messages = db.query(ChatHistory).filter(
        ChatHistory.conversation_id == conversation_id
    ).order_by(ChatHistory.created_at.asc()).all()

    message_items = []
    for m in messages:
        meta = _safe_json(m.render_meta, {}) or {}
        message_items.append(ConversationMessageItem(
            id=m.id,
            question=m.question,
            ai_response=compact_explanation_currency(m.ai_response) if m.ai_response else None,
            created_at=m.created_at,
            generated_sql=m.generated_sql,
            sql_result_summary=m.sql_result_summary,
            tokens_used=m.tokens_used or 0,
            context_name=m.context_name,
            is_bookmarked=m.is_bookmarked or False,
            feedback_rating=m.feedback_rating,
            execution_time_ms=m.execution_time_ms or 0.0,
            data=_safe_json(m.result_data),
            visualization=meta.get("visualization"),
            chart_config=meta.get("chart_config"),
            display_hint=meta.get("display_hint"),
            hierarchy_columns=meta.get("hierarchy_columns"),
            warnings=meta.get("warnings"),
            confidence=meta.get("confidence"),
            data_truncated=bool(meta.get("data_truncated", False)),
        ))

    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=conv.message_count,
        messages=message_items,
    )


@router.post("/", response_model=ConversationCreateResponse)
def create_conversation(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """Create a new empty conversation."""
    conv = Conversation(
        user_id=current_user.id,
        title=None,
        message_count=0,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return ConversationCreateResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
    )


@router.patch("/{conversation_id}", response_model=ConversationUpdateResponse)
def update_conversation(
    conversation_id: str,
    body: ConversationUpdateRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """Update conversation title or archive status."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if body.title is not None:
        conv.title = body.title
    if body.is_archived is not None:
        conv.is_archived = body.is_archived

    conv.updated_at = utcnow()
    db.commit()
    db.refresh(conv)

    return ConversationUpdateResponse(
        id=conv.id,
        title=conv.title,
        updated_at=conv.updated_at,
    )


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    """Soft delete (archive) a conversation."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conv.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    conv.is_archived = True
    conv.updated_at = utcnow()
    db.commit()

    return {"success": True}
