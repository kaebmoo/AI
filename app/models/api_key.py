"""
API Key Models
===============
SQLAlchemy models for API key authentication.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index
from app.db.base_class import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(12), nullable=False, index=True)
    name = Column(String(200), default="")
    user_id = Column(Integer, nullable=False)
    scopes = Column(String(100), default="query")  # query, admin, full
    rate_limit_per_minute = Column(Integer, default=30)
    rate_limit_per_day = Column(Integer, default=1000)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class APIKeyUsage(Base):
    __tablename__ = "api_key_usage"

    id = Column(Integer, primary_key=True, index=True)
    api_key_id = Column(Integer, nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    request_count = Column(Integer, default=0)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_api_key_usage_date", "api_key_id", "date", unique=True),
    )
