from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db.base_class import Base


def generate_conversation_id():
    return str(uuid.uuid4())


class Conversation(Base):
    """
    Conversation groups related chat messages together.
    Each conversation has a title (auto-generated from first message) and belongs to a user.
    """
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_conversation_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_archived = Column(Boolean, default=False)
    message_count = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "ChatHistory",
        back_populates="conversation",
        order_by="ChatHistory.created_at",
        foreign_keys="ChatHistory.conversation_id",
        primaryjoin="Conversation.id == ChatHistory.conversation_id",
    )
