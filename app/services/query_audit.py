"""Audit of questions (Plan 7 Phase 4.5): written once per QueryEngine.query, searched and exported
through GET /admin/query-audit. Separate from AuditService (config changes)."""

import json
import logging
from typing import Any, Dict, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.query_audit import QueryAudit

logger = logging.getLogger(__name__)

_tables_checked = set()


def ensure_table(bind) -> None:
    """query_audit exists with today's columns — once per process per database (idempotent)."""
    if str(bind.url) in _tables_checked:
        return
    QueryAudit.__table__.create(bind, checkfirst=True)  # an app DB created before Phase 4.5
    if "request_group" not in {c["name"] for c in inspect(bind).get_columns("query_audit")}:
        with bind.begin() as conn:  # a table created before Phase 5
            conn.execute(text("ALTER TABLE query_audit ADD COLUMN request_group VARCHAR"))
    _tables_checked.add(str(bind.url))


def record(db: Optional[Session], engine_result=None, scope: Optional[Dict[str, Any]] = None, **fields: Any) -> None:
    """Never raises — but a lost audit row is an ERROR in the log, not a silent pass.

    Own short session on the caller's engine: the caller's transaction is not committed by us.
    No session (scripts, eval) = nothing to write to."""
    if db is None:
        return
    try:
        if engine_result is not None:
            fields.update(_from_result(engine_result))
        if scope:
            fields["scope"] = json.dumps(scope, ensure_ascii=False, sort_keys=True, default=str)
        bind = db.get_bind()
        ensure_table(bind)
        with Session(bind=bind) as session:
            session.add(QueryAudit(**fields))
            session.commit()
    except Exception as exc:
        logger.error("query audit NOT written (%s): %s", fields.get("context_name"), exc)


def _from_result(engine_result) -> Dict[str, Any]:
    result = engine_result.query_result
    rows = result.data if isinstance(result.data, list) else []
    columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
    return {
        "context_name": engine_result.context_name,
        "sql_query": result.sql_query or None,
        "result_columns": json.dumps(columns, ensure_ascii=False),
        "row_count": len(rows),
        "provider": engine_result.provider_used,
        "llm_policy": engine_result.llm_policy,
        "cache_hit": engine_result.cache_hit,
        "error": result.error or None,
        "execution_time_ms": engine_result.execution_time_ms,
    }
