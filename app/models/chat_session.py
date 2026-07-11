"""SQLAlchemy model for chart-only session data storage."""
from sqlalchemy import Column, String, Text, Integer, DateTime
from datetime import datetime

from app.db.base_class import Base
from app.core.time_utils import utcnow


class ChatSessionData(Base):
    """
    Stores last query result data per conversation for chart-only re-render.
    Keyed by conversation_id. Upsert on every successful data query.
    """
    __tablename__ = "chat_session_data"

    conversation_id = Column(String, primary_key=True, index=True)
    last_data = Column(Text, nullable=False)           # JSON: list of row dicts
    last_columns = Column(Text, nullable=False)         # JSON: list of column names
    last_chart_config = Column(Text, nullable=True)     # JSON: chart config dict
    row_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
