"""Plan 7 Phase 4.5 — DSR: erase one user's traces, nobody else's; idempotent."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base_class import Base
from app.models.chat import ChatHistory
from app.models.chat_session import ChatSessionData
from app.models.conversation import Conversation
from app.models.query_audit import QueryAudit
from app.models.report_export import ReportExport
from app.models.user import User
from app.services import query_audit, user_data


@pytest.fixture
def db(tmp_path, monkeypatch):
    import app.models  # noqa: F401
    import app.models.admin_agent  # noqa: F401
    import app.models.feedback_models  # noqa: F401
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    Base.metadata.create_all(engine)
    exports = tmp_path / "exports"
    exports.mkdir()
    monkeypatch.setattr("app.services.report_service.EXPORT_DIR", exports)
    session = sessionmaker(bind=engine)()
    for uid in (1, 2):
        session.add(User(id=uid, email=f"u{uid}@nt.test", hashed_password="x"))
        session.add(Conversation(id=f"c{uid}", user_id=uid, title="t"))
        session.add(ChatHistory(id=uid, user_id=uid, conversation_id=f"c{uid}", question="q", ai_response="a",
                                result_data='[{"v": 1}]'))
        session.add(ChatSessionData(conversation_id=f"c{uid}", last_data="[1]", last_columns="[]"))
        path = exports / f"e{uid}.xlsx"
        path.write_text("rows")
        session.add(ReportExport(id=f"e{uid}", user_id=uid, chat_history_id=uid, question="q", sql_text="SELECT 1",
                                 status="done", file_path=str(path)))
        session.flush()
        session.execute(text("INSERT INTO user_feedback (chat_id, rating) VALUES (:c, 'THUMBS_UP')"), {"c": uid})
        session.execute(text("INSERT INTO chart_feedback_events (conversation_id, user_id, question, profile_json, decision_json) "
                             "VALUES (:c, :u, 'q', '{}', '{}')"), {"c": f"c{uid}", "u": uid})
        session.execute(text("INSERT INTO admin_agent_conversations (id, user_id) VALUES (:u, :u)"), {"u": uid})
        session.execute(text("INSERT INTO admin_agent_messages (conversation_id, role, content) VALUES (:u, 'tool', 'x')"), {"u": uid})
    session.commit()
    for uid in (1, 2):
        query_audit.record(session, user_id=uid, question="ยอดขายของฉัน", sql_query="SELECT 1", row_count=3)
    # a file the export row points at, outside the export directory, must never be removed
    outside = tmp_path / "outside.xlsx"
    outside.write_text("keep")
    session.add(ReportExport(id="evil", user_id=1, question="q", sql_text="SELECT 1", status="done", file_path=str(outside)))
    session.commit()
    yield session, exports, outside
    session.close()


def counts(session, uid):
    one = lambda sql: session.execute(text(sql), {"u": uid}).scalar()  # noqa: E731
    return {
        "history": one("SELECT COUNT(*) FROM chat_history WHERE user_id = :u"),
        "conversations": one("SELECT COUNT(*) FROM conversations WHERE user_id = :u"),
        "session_data": one("SELECT COUNT(*) FROM chat_session_data WHERE conversation_id = 'c' || :u"),
        "feedback": one("SELECT COUNT(*) FROM user_feedback WHERE chat_id = :u"),
        "chart_feedback": one("SELECT COUNT(*) FROM chart_feedback_events WHERE user_id = :u"),
        "exports": one("SELECT COUNT(*) FROM report_exports WHERE user_id = :u"),
        "agent": one("SELECT COUNT(*) FROM admin_agent_messages WHERE conversation_id = :u"),
    }


def test_dry_run_counts_and_touches_nothing(db):
    session, exports, _ = db
    would = user_data.erase_user_data(session, 1)  # dry_run is the default
    assert would["history"] == 1 and would["exports"] == 2 and would["export_files"] == 2 and would["audit_anonymised"] == 1
    assert counts(session, 1)["history"] == 1 and (exports / "e1.xlsx").exists()


def test_erase_removes_this_user_only_and_is_idempotent(db):
    session, exports, outside = db
    with patch("app.services.query_engine.clear_query_cache", return_value=5) as cleared:
        done = user_data.erase_user_data(session, 1, dry_run=False)
    assert cleared.called and done["query_cache_cleared"] == 5
    assert set(counts(session, 1).values()) == {0}
    assert set(counts(session, 2).values()) == {1}  # the other user is untouched
    assert not (exports / "e1.xlsx").exists() and (exports / "e2.xlsx").exists()
    assert outside.exists() and done["export_files"] == 1  # a path outside the export directory is never unlinked
    mine, theirs = session.query(QueryAudit).order_by(QueryAudit.id).all()
    assert (mine.user_id, mine.question, mine.sql_query, mine.row_count) == (None, None, "SELECT 1", 3)  # the row stays, the person goes
    assert (theirs.user_id, theirs.question) == (2, "ยอดขายของฉัน")
    assert session.get(User, 1) is not None  # the account is not this endpoint's business

    again = user_data.erase_user_data(session, 1, dry_run=False)
    assert {k: v for k, v in again.items() if k != "query_cache_cleared"} == dict.fromkeys(
        ["feedback", "chart_feedback", "exports", "session_data", "history", "conversations", "admin_agent_messages",
         "admin_agent_conversations", "audit_anonymised", "export_files"], 0)


def test_older_app_db_without_every_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE chat_history (id INTEGER PRIMARY KEY, user_id INT)"))
        conn.execute(text("CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id INT)"))
        conn.execute(text("INSERT INTO chat_history (user_id) VALUES (1), (1), (2)"))
    session = sessionmaker(bind=engine)()
    with patch("app.services.query_engine.clear_query_cache", return_value=0):
        assert user_data.erase_user_data(session, 1, dry_run=False)["history"] == 2
    assert session.execute(text("SELECT COUNT(*) FROM chat_history")).scalar() == 1


def test_endpoint_records_the_erasure_and_404s_unknown_users(db):
    from app.api.v1.admin import user_data as api

    session, _, _ = db
    admin = MagicMock(id=2)
    with pytest.raises(HTTPException) as exc:
        api.erase_data_of_user(99, dry_run=False, current_user=admin, db=session)
    assert exc.value.status_code == 404
    assert "would_erase" in api.erase_data_of_user(1, dry_run=True, current_user=admin, db=session)
    assert session.query(QueryAudit).filter_by(channel="dsr_erase").count() == 0
    with patch("app.services.query_engine.clear_query_cache", return_value=0):
        assert api.erase_data_of_user(1, dry_run=False, current_user=admin, db=session)["erased"]["history"] == 1
    trail = session.query(QueryAudit).filter_by(channel="dsr_erase").one()
    assert trail.user_id == 2 and "user 1" in trail.question and '"history": 1' in trail.result_columns
