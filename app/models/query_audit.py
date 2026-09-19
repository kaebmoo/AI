from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text

from app.core.time_utils import utcnow
from app.db.base_class import Base


class QueryAudit(Base):
    """One row per question that reached QueryEngine — chat, /api/v1/query and telegram alike
    (Plan 7 Phase 4.5). Who asked, under which key / workspace / scope, what SQL ran, which columns
    and how many rows came back. Never the rows themselves."""
    __tablename__ = "query_audit"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=utcnow, index=True)
    user_id = Column(Integer, nullable=True, index=True)      # no FK: survives the user's DSR as an anonymous row
    api_key_id = Column(Integer, nullable=True, index=True)
    channel = Column(String, nullable=True)                   # chat / telegram / the caller's `source` on /api/v1/query
    workspace = Column(String, nullable=True)
    context_name = Column(String, nullable=True)
    scope = Column(Text, nullable=True)                       # JSON as sent by the caller
    question = Column(Text, nullable=True)
    sql_query = Column(Text, nullable=True)
    result_columns = Column(Text, nullable=True)              # JSON list
    row_count = Column(Integer, default=0)
    provider = Column(String, nullable=True)
    llm_policy = Column(String, nullable=True)
    cache_hit = Column(Boolean, default=False)
    error = Column(Text, nullable=True)                       # includes refusals: scope / allowlist / policy
    execution_time_ms = Column(Float, default=0.0)
    request_group = Column(String, nullable=True, index=True)  # Phase 5: a multi-context question and its sub-questions

    __table_args__ = (Index("ix_query_audit_ws_ctx", "workspace", "context_name"),)
