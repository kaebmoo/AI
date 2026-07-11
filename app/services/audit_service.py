"""
Audit Service
==============
Records all config changes to audit_log table.
Used by admin tools, auto-analyzer, and admin agent.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.time_utils import utcnow

logger = logging.getLogger(__name__)


class AuditService:
    """Log config changes to audit_log table."""

    def __init__(self, db: Session):
        self.db = db

    def log_change(
        self,
        action: str,            # INSERT, UPDATE, DELETE
        table_name: str,        # schema_semantic_mapping, etc.
        record_id: int = None,
        old_value: dict = None,
        new_value: dict = None,
        source: str = "manual",  # manual, admin_agent, auto_analyzer, onboarding
        user_id: int = None,
    ):
        """Record a config change to the audit_log table."""
        try:
            self.db.execute(text("""
                INSERT INTO audit_log (action, table_name, record_id, old_value, new_value, source, user_id, created_at)
                VALUES (:action, :table_name, :record_id, :old_value, :new_value, :source, :user_id, :created_at)
            """), {
                "action": action,
                "table_name": table_name,
                "record_id": record_id,
                "old_value": json.dumps(old_value, ensure_ascii=False, default=str) if old_value else None,
                "new_value": json.dumps(new_value, ensure_ascii=False, default=str) if new_value else None,
                "source": source,
                "user_id": user_id,
                "created_at": utcnow().isoformat(),
            })
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    def get_recent(
        self,
        limit: int = 50,
        table_name: str = None,
        source: str = None,
    ) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        sql = "SELECT * FROM audit_log WHERE 1=1"
        params: Dict[str, Any] = {}

        if table_name:
            sql += " AND table_name = :table_name"
            params["table_name"] = table_name
        if source:
            sql += " AND source = :source"
            params["source"] = source

        sql += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        try:
            result = self.db.execute(text(sql), params)
            return [dict(zip(result.keys(), row)) for row in result.fetchall()]
        except Exception as e:
            logger.warning(f"Failed to read audit log: {e}")
            return []
