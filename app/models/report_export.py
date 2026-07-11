"""Report export records (F6) — one row per requested xlsx export."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.time_utils import utcnow
from app.db.base_class import Base


class ReportExport(Base):
    __tablename__ = "report_exports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    chat_history_id = Column(Integer, ForeignKey("chat_history.id"), nullable=True)
    question = Column(Text)
    sql_text = Column(Text)
    status = Column(String, default="pending")  # pending | running | done | failed
    file_path = Column(String, nullable=True)
    row_count = Column(Integer, nullable=True)
    truncated = Column(Boolean, default=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
