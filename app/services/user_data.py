"""
Data-subject request: erase what we hold about one user (Plan 7 Phase 4.5)
===========================================================================
Zero-import: the business data stays with its owner — on our side a user leaves traces only:
history (questions, SQL, answers, result rows), session data, feedback, export files, admin-agent
conversations, cached answers. The account itself and the API keys are not touched (deactivate those
separately). The query audit keeps its rows but loses the person: user_id and the question text.
"""

import logging
import os
from typing import Dict

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

_MINE = "SELECT id FROM chat_history WHERE user_id = :u"
_MY_CONVERSATIONS = "SELECT id FROM conversations WHERE user_id = :u"
# (label, table, WHERE) — children before parents
_DELETES = (
    ("feedback", "user_feedback", f"chat_id IN ({_MINE})"),
    ("chart_feedback", "chart_feedback_events", "user_id = :u"),
    ("exports", "report_exports", "user_id = :u"),
    ("session_data", "chat_session_data", f"conversation_id IN ({_MY_CONVERSATIONS})"),
    ("history", "chat_history", "user_id = :u"),
    ("conversations", "conversations", "user_id = :u"),
    ("admin_agent_messages", "admin_agent_messages",
     "conversation_id IN (SELECT id FROM admin_agent_conversations WHERE user_id = :u)"),
    ("admin_agent_conversations", "admin_agent_conversations", "user_id = :u"),
)


def erase_user_data(db, user_id: int, dry_run: bool = True) -> Dict[str, int]:
    """Counts per kind; dry_run (the default) only counts. Idempotent. One transaction."""
    from app.services.report_service import EXPORT_DIR

    tables = set(inspect(db.get_bind()).get_table_names())  # older app DBs lack some of these
    params = {"u": user_id}
    done: Dict[str, int] = {}
    files = []
    if "report_exports" in tables:
        files = [row[0] for row in db.execute(text(
            "SELECT file_path FROM report_exports WHERE user_id = :u AND file_path IS NOT NULL"), params)]
    for label, table, where in _DELETES:
        if table not in tables:
            done[label] = 0
        elif dry_run:
            done[label] = db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {where}"), params).scalar() or 0
        else:
            done[label] = db.execute(text(f"DELETE FROM {table} WHERE {where}"), params).rowcount
    done["audit_anonymised"] = 0
    if "query_audit" in tables:
        if dry_run:
            done["audit_anonymised"] = db.execute(text("SELECT COUNT(*) FROM query_audit WHERE user_id = :u"), params).scalar() or 0
        else:
            done["audit_anonymised"] = db.execute(text(
                "UPDATE query_audit SET user_id = NULL, question = NULL WHERE user_id = :u"), params).rowcount
    done["export_files"] = len(files)
    if dry_run:
        db.rollback()
        return done

    db.commit()
    root = os.path.realpath(EXPORT_DIR)
    done["export_files"] = 0
    for path in files:  # after the commit: a file without its row is swept by cleanup_expired; the reverse is a dead link
        real = os.path.realpath(path)
        if os.path.commonpath([root, real]) == root and os.path.isfile(real):  # never outside the export directory
            os.unlink(real)
            done["export_files"] += 1
    from app.services.query_engine import clear_query_cache
    done["query_cache_cleared"] = clear_query_cache()  # the cache isn't keyed by user — drop it all
    logger.info("DSR erase for user %s: %s", user_id, done)
    return done
