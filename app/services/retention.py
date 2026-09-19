"""
Result retention (Plan 7 Phase 4.5)
====================================
Stored result rows expire; the question, the SQL and the answer text stay.

Settings (admin_config, overridable per workspace in ``workspaces``):
- ``result_retention_days``  rows older than this are purged; 0 = keep forever (default 30)
- ``store_result_data``      false = result rows are never written (history, session data, query cache)

A workspace override applies to the history of that workspace's contexts. Things that don't know
their context (chat_session_data, query_correction_log, the chat tool's temp CSV) follow the global setting.
"""

import logging
import os
import tempfile
import time
from datetime import timedelta
from typing import Dict, Optional, Tuple

from sqlalchemy import bindparam, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.time_utils import utcnow

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30
TEMP_EXPORT_DIR = os.path.join(tempfile.gettempdir(), "nt_reports")  # app/tools/report_export.py


def _global_settings() -> Tuple[int, bool]:
    days, store = DEFAULT_RETENTION_DAYS, True
    try:
        from app.services.admin_config_service import AdminConfigService
        svc = AdminConfigService()
        try:
            raw_days, raw_store = svc.get_config("result_retention_days"), svc.get_config("store_result_data")
        finally:
            svc.close()
        if raw_days not in (None, ""):
            days = max(0, int(float(raw_days)))  # PUT /config/settings stores numbers as "30.0"
        if raw_store not in (None, ""):
            store = str(raw_store).strip().lower() not in ("false", "0", "no", "off")
    except Exception as exc:  # unreadable config: the defaults above (purge at 30 days, store)
        logger.warning("retention settings unreadable, using defaults: %s", exc)
    return days, store


def _workspace_overrides(config_engine=None) -> Dict[str, Tuple[Optional[int], Optional[bool]]]:
    """{context name: (days, store)} for contexts whose workspace overrides a setting."""
    if config_engine is None:
        from app.db.session import config_engine
    try:
        with config_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT sc.name, w.result_retention_days, w.store_result_data FROM schema_contexts sc "
                "JOIN workspaces w ON w.id = COALESCE(sc.workspace_id, (SELECT id FROM workspaces WHERE name = 'default')) "
                "WHERE w.result_retention_days IS NOT NULL OR w.store_result_data IS NOT NULL")).all()
    except (OperationalError, ProgrammingError):  # workspaces / columns not migrated = no override
        return {}
    return {name: (days, None if store is None else bool(store)) for name, days, store in rows}


def stores_results(context_name: Optional[str], config_engine=None) -> bool:
    """May the rows of an answer from this context be written anywhere (history, session data, cache)?"""
    override = _workspace_overrides(config_engine).get(context_name or "", (None, None))[1]
    return _global_settings()[1] if override is None else override


def purge_results(db, config_engine=None, now=None) -> Dict[str, int]:
    """Drop stored result rows past their retention. Idempotent; metadata is never touched."""
    now = now or utcnow()
    global_days, _ = _global_settings()
    overrides = {ctx: days for ctx, (days, _store) in _workspace_overrides(config_engine).items() if days is not None}
    done = {"chat_history": 0, "chat_session_data": 0, "query_correction_log": 0, "temp_files": 0}

    clear = ("UPDATE chat_history SET result_data = NULL, sql_result_summary = NULL WHERE created_at < :cutoff "
             "AND (result_data IS NOT NULL OR sql_result_summary IS NOT NULL) AND ")
    by_days: Dict[int, list] = {}
    for ctx, days in overrides.items():
        by_days.setdefault(max(0, int(days)), []).append(ctx)
    for days, contexts in by_days.items():
        if days:
            done["chat_history"] += db.execute(
                text(clear + "context_name IN :ctx").bindparams(bindparam("ctx", expanding=True)),
                {"cutoff": _stamp(now - timedelta(days=days)), "ctx": contexts}).rowcount
    if global_days:
        cutoff = _stamp(now - timedelta(days=global_days))
        rest = "(context_name IS NULL OR context_name NOT IN :ctx)" if overrides else "1 = 1"
        stmt = text(clear + rest)
        if overrides:
            stmt = stmt.bindparams(bindparam("ctx", expanding=True))
        done["chat_history"] += db.execute(stmt, {"cutoff": cutoff, **({"ctx": list(overrides)} if overrides else {})}).rowcount
        done["chat_session_data"] = db.execute(
            text("DELETE FROM chat_session_data WHERE updated_at < :cutoff"), {"cutoff": cutoff}).rowcount
        try:
            with db.begin_nested():  # created on first use by AIService — may not exist
                done["query_correction_log"] = db.execute(
                    text("DELETE FROM query_correction_log WHERE created_at < :cutoff"), {"cutoff": cutoff}).rowcount
        except (OperationalError, ProgrammingError):
            pass
        done["temp_files"] = _purge_temp_files(time.time() - global_days * 86400)
    db.commit()
    return done


def _stamp(moment) -> str:
    # the columns hold naive-UTC text ("2026-07-14 01:03:50.284472"); compare like with like
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f")


def _purge_temp_files(older_than: float) -> int:
    removed = 0
    try:
        for entry in os.scandir(TEMP_EXPORT_DIR):
            if entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_mtime < older_than:
                os.unlink(entry.path)
                removed += 1
    except OSError:
        pass
    return removed
