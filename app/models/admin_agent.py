"""
Admin Agent Models
===================
SQLAlchemy models for admin agent conversation storage.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from app.db.base_class import Base
from app.core.time_utils import utcnow


class AdminAgentConversation(Base):
    __tablename__ = "admin_agent_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)  # References users.id (no FK constraint — may be in different DB)
    title = Column(String(200), default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AdminAgentMessage(Base):
    __tablename__ = "admin_agent_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("admin_agent_conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, default="")
    tool_name = Column(String(100), nullable=True)
    tool_args = Column(Text, nullable=True)  # JSON string
    tool_result = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_admin_agent_messages_conversation", "conversation_id"),
    )
