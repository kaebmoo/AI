from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime
from app.db.base_class import Base
import enum

class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    version = Column(Integer, nullable=False)
    system_prompt = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True) # Admin user
    is_active = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    
    # SQLite doesn't support JSON type natively in all versions, but SQLAlchemy handles it
    # Storing few_shot_examples as JSON string or proper JSON type
    few_shot_examples = Column(JSON, nullable=True)

class GoldenExample(Base):
    __tablename__ = "golden_examples"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chat_history.id"), nullable=True)
    question_pattern = Column(Text, nullable=False)
    expected_sql = Column(Text, nullable=False)
    category = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    added_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class FeedbackRating(str, enum.Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"

class FeedbackCategory(str, enum.Enum):
    WRONG_DATA = "wrong_data"
    INCOMPLETE = "incomplete"
    HARD_TO_UNDERSTAND = "hard_to_understand"
    SLOW = "slow"
    SQL_ERROR = "sql_error"
    PERFECT = "perfect"
    OTHER = "other"

class UserFeedback(Base):
    __tablename__ = "user_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chat_history.id"), nullable=False)
    rating = Column(Enum(FeedbackRating), nullable=False)
    feedback_category = Column(Enum(FeedbackCategory), nullable=True)
    feedback_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Review fields
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    is_golden_example = Column(Boolean, default=False)
    
    # Relations
    # Relations
    chat = relationship("ChatHistory", backref=backref("feedback", uselist=False))

class TrendingQuery(Base):
    __tablename__ = "trending_queries"
    
    id = Column(Integer, primary_key=True, index=True)
    question = Column(String, index=True, nullable=False)
    count = Column(Integer, default=1)
    date = Column(DateTime, default=datetime.utcnow) # Represents the day/period
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
