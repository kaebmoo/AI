from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.base_class import Base

class ChatHistory(Base):
    """
    ChatHistory stores user questions, generated SQL, and AI responses.
    """
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(Integer, ForeignKey("user_sessions.id"), nullable=True) # Optional link to session
    conversation_id = Column(String, index=True, nullable=True) # For grouping chat turn
    question = Column(Text)
    generated_sql = Column(Text, nullable=True)
    sql_result_summary = Column(Text, nullable=True)
    ai_response = Column(Text)
    tokens_used = Column(Integer, default=0)
    execution_time_ms = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_bookmarked = Column(Boolean, default=False)
    feedback_rating = Column(Integer, nullable=True) # 1-5

    # Relationships
    user = relationship("User", back_populates="chats")
