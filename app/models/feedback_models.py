from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship, backref
from datetime import datetime
from app.db.base_class import Base, ConfigBase
import enum
from app.core.time_utils import utcnow
from app.models.schema_models import ProvenanceMixin

class GoldenExample(ProvenanceMixin, ConfigBase):  # Config DB table
    __tablename__ = "golden_examples"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, nullable=True)  # References chat_history.id (no FK — cross-DB)
    question_pattern = Column(Text, nullable=False)
    expected_sql = Column(Text, nullable=False)
    category = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    added_by = Column(Integer, nullable=True)  # References users.id (no FK — cross-DB)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)

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
    created_at = Column(DateTime, default=utcnow)
    
    # Review fields
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    is_golden_example = Column(Boolean, default=False)
    
    # Relations
    # Relations
    chat = relationship("ChatHistory", backref=backref("feedback", uselist=False))


class ChartFeedbackEvent(Base):
    __tablename__ = "chart_feedback_events"
    __table_args__ = (
        Index("ix_chart_feedback_events_conversation_created", "conversation_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    question = Column(Text, nullable=False)
    requested_type = Column(String, nullable=True)
    resolved_type = Column(String, nullable=True)
    requested_type_accepted = Column(Boolean, default=False)
    requested_type_vetoed = Column(Boolean, default=False)
    profile_json = Column(Text, nullable=False)
    decision_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

class TrendingQuery(Base):
    __tablename__ = "trending_queries"
    
    id = Column(Integer, primary_key=True, index=True)
    question = Column(String, index=True, nullable=False)
    count = Column(Integer, default=1)
    date = Column(DateTime, default=utcnow) # Represents the day/period
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
