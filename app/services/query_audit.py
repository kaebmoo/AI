"""Audit of questions (Plan 7 Phase 4.5): written once per QueryEngine.query, searched and exported
through GET /admin/query-audit. Separate from AuditService (config changes)."""

import json
import logging
import threading
from typing import Any, Dict, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.models.query_audit import QueryAudit

logger = logging.getLogger(__name__)

_tables_checked = set()
# record() runs in a worker thread: two requests arriving together on a not-yet-migrated table would
# both find the column missing and both ALTER, and SQLite has no ADD COLUMN IF NOT EXISTS — the loser
# used to lose only its audit row, and now would lose the answer with it
_check_lock = threading.Lock()


def ensure_table(bind) -> None:
    """query_audit exists with today's columns — once per process per database (idempotent)."""
    if str(bind.url) in _tables_checked:
        return
    with _check_lock:
        if str(bind.url) in _tables_checked:  # someone did it while we waited
            return
        QueryAudit.__table__.create(bind, checkfirst=True)  # an app DB created before Phase 4.5
        if "request_group" not in {c["name"] for c in inspect(bind).get_columns("query_audit")}:
            with bind.begin() as conn:  # a table created before Phase 5
                conn.execute(text("ALTER TABLE query_audit ADD COLUMN request_group VARCHAR"))
        _tables_checked.add(str(bind.url))


class AuditUnavailable(Exception):
    """The audit row of a request that holds an API key could not be written, so the answer does not
    leave (NIST AU-5: no auditing, no auditable action). Channels without a key keep answering —
    chat_history is their trace — and the loss is an ERROR in the log."""


def record(db: Optional[Session], engine_result=None, scope: Optional[Dict[str, Any]] = None, **fields: Any) -> bool:
    """True when the row is in the database. Never raises — but a lost audit row is an ERROR in the
    log, not a silent pass, and a caller that holds an API key must act on a False.

    Own short session on the caller's engine: the caller's transaction is not committed by us.
    No session (scripts, eval) = nothing to write to."""
    if db is None:
        return False
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
        return True
    except Exception as exc:
        logger.error("query audit NOT written (%s): %s", fields.get("context_name"), exc)
        return False


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
