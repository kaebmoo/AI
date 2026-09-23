"""Plan 7 hardening — an answer that cannot be recorded is not sent (NIST AU-5).

Only on the channels that hold an API key (REST with a key, the MCP facade): their caller is a
program we cannot ask afterwards, and query_audit is the only trace of what it was told. Chat,
telegram and a signed-in person keep answering — chat_history is their trace — and the lost row is
an ERROR in the log.

The audit is broken here the way it breaks in production: a real app database that cannot be
written (read-only file) and one whose query_audit table cannot be created.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.query import SimpleQueryRequest, run_simple_query
from app.core import outbound
from app.db.base_class import Base
from app.models.query_audit import QueryAudit
from app.services import query_audit
from app.services.query_engine import QueryEngine


@pytest.fixture
def unwritable(tmp_path):
    """A real app DB, then read-only on disk: every INSERT fails, nothing is mocked away."""
    import app.models  # noqa: F401 — every table of the app DB

    path = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    os.chmod(path, 0o444)
    query_audit._tables_checked.clear()
    read_only = create_engine(f"sqlite:///{path}")
    yield sessionmaker(bind=read_only)()
    read_only.dispose()
    os.chmod(path, 0o644)


@pytest.fixture
def writable(tmp_path):
    import app.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'ok.db'}")
    Base.metadata.create_all(engine)
    query_audit._tables_checked.clear()
    return sessionmaker(bind=engine)()


def _result():
    qr = SimpleNamespace(explanation="รายได้ 5 บาท", error=None, data=[{"v": 5}], sql_query="SELECT 1")
    return SimpleNamespace(query_result=qr, context_name="feed_revenue", execution_time_ms=1.0,
                           data_as_of=None, llm_policy="full", provider_used="matcha", cache_hit=False)


def _engine(db):
    engine = QueryEngine(mcp_client=MagicMock(), db_session=db, admin_config=MagicMock())
    engine._query = AsyncMock(return_value=_result())
    engine._workspace = staticmethod(lambda name: "nt-report")
    return engine


def _ask(engine, **kwargs):
    return asyncio.run(engine.query("รายได้รวม", **kwargs))


class TestTheEngine:
    def test_record_says_whether_the_row_is_there(self, unwritable, writable):
        assert query_audit.record(writable, None, None, question="q", channel="api") is True
        assert query_audit.record(unwritable, None, None, question="q", channel="api") is False
        assert query_audit.record(None, None, None, question="q") is False  # scripts, eval: nothing to write to

    def test_a_key_holding_request_gets_no_answer_without_its_row(self, unwritable):
        with pytest.raises(query_audit.AuditUnavailable):
            _ask(_engine(unwritable), api_key_id=7, channel="api:portal")

    def test_chat_and_a_signed_in_person_still_get_theirs(self, unwritable):
        """Fail-open where a person is watching and chat_history keeps the trace."""
        assert _ask(_engine(unwritable), user_id=1).query_result.data == [{"v": 5}]
        assert _ask(_engine(unwritable), user_id=1, channel="telegram").query_result.data == [{"v": 5}]

    def test_the_answer_is_sent_when_the_row_is_written(self, writable):
        assert _ask(_engine(writable), api_key_id=7, channel="api:portal").query_result.data == [{"v": 5}]
        assert writable.query(QueryAudit).count() == 1

    def test_a_cache_hit_is_held_to_the_same_rule(self, unwritable):
        engine = _engine(unwritable)
        engine._query = AsyncMock(return_value=SimpleNamespace(**{**vars(_result()), "cache_hit": True}))
        with pytest.raises(query_audit.AuditUnavailable):
            _ask(engine, api_key_id=7, channel="api:portal")

    def test_a_table_that_cannot_be_created_counts_as_unwritable(self, writable):
        writable.execute(text("DROP TABLE query_audit"))
        writable.commit()
        query_audit._tables_checked.clear()
        with patch.object(QueryAudit.__table__, "create", side_effect=OSError("disk full")), \
                pytest.raises(query_audit.AuditUnavailable):
            _ask(_engine(writable), api_key_id=7, channel="mcp:claude-desktop")


class TestTheChannels:
    @staticmethod
    def _run(db, **kwargs):
        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            MockEngine.return_value = _engine(db)
            MockEngine.return_value.db = db
            return asyncio.run(run_simple_query(
                SimpleQueryRequest(question="q"), user_id=1, allowed=None, db=db,
                admin_config=MagicMock(), mcp_client=MagicMock(), **kwargs))

    def test_rest_with_a_key_is_503_with_a_fixed_message(self, unwritable):
        from fastapi import HTTPException
        from app.api.v1 import query as query_api

        request = SimpleNamespace(state=SimpleNamespace(api_key=SimpleNamespace(id=7)),
                                  app=SimpleNamespace(state=SimpleNamespace(mcp_client=MagicMock())))
        with patch.object(query_api, "run_simple_query",
                          AsyncMock(side_effect=query_audit.AuditUnavailable("no row"))), \
                pytest.raises(HTTPException) as exc:
            asyncio.run(query_api.simple_query(SimpleQueryRequest(question="q"), request,
                                               current_user=SimpleNamespace(id=1), db=unwritable,
                                               admin_config=MagicMock()))
        assert exc.value.status_code == 503 and exc.value.detail == outbound.message("audit_unavailable")
        assert "no row" not in exc.value.detail and "query_audit" not in exc.value.detail

    def test_the_mcp_facade_turns_it_into_a_tool_error_not_an_answer(self):
        assert outbound.code_for(query_audit.AuditUnavailable("x")) == "audit_unavailable"
        # the engine's own MCP session wraps whatever is raised inside an anyio task group
        from tests.unit.test_mcp_facade import _Group
        assert outbound.code_for(_Group("eg", [query_audit.AuditUnavailable("x")])) == "audit_unavailable"

    def test_rest_without_a_key_still_answers(self, unwritable):
        response, _ = self._run(unwritable, api_key_id=None, channel="api")
        assert response.answer == "รายได้ 5 บาท" and response.error is None


class TestMultiContext:
    """Parent row or any sub-question's row: one missing makes the whole answer untraceable."""

    @staticmethod
    def _multi(db, parent_written, part_exc=None):
        from app.services import multi_context as mc

        engine = MagicMock(db=db, admin_config=MagicMock())
        engine._workspace = lambda name: "nt-report"
        engine.query = AsyncMock(side_effect=part_exc) if part_exc else AsyncMock(return_value=_result())
        engine.schema_service.get_all_contexts.return_value = []
        with patch.object(mc, "enabled_workspaces", return_value=frozenset({"nt-report"})), \
                patch.object(mc, "_workspaces", return_value={}), \
                patch.object(mc, "candidates", return_value=[{"name": "feed_revenue", "display_name": "r"},
                                                             {"name": "feed_expense", "display_name": "e"}]), \
                patch.object(mc, "_split", AsyncMock(return_value={
                    "parts": [("feed_revenue", "a"), ("feed_expense", "b")], "operation": "none", "operands": []})), \
                patch.object(mc.query_audit, "record", return_value=parent_written):
            return asyncio.run(mc.answer(engine, "รายได้และค่าใช้จ่าย", api_key_id=7, channel="api:portal"))

    def test_the_parent_row_is_required_too(self, writable):
        with pytest.raises(query_audit.AuditUnavailable):
            self._multi(writable, parent_written=False)
        assert self._multi(writable, parent_written=True).parts  # the same question, recorded, answers

    def test_one_sub_question_without_a_row_stops_the_whole_answer(self, writable):
        with pytest.raises(query_audit.AuditUnavailable):
            self._multi(writable, parent_written=True, part_exc=query_audit.AuditUnavailable("part"))


class TestReviewFindings:
    """Both from the independent review of the commit above."""

    def test_the_failed_write_is_not_immediately_tried_again(self, unwritable):
        """The raise sits inside the try that also audits failures, so the database that just refused
        a write was asked for a second one — another wait on the same lock, for nothing."""
        engine = _engine(unwritable)
        with patch.object(query_audit, "record", return_value=False) as record:
            with pytest.raises(query_audit.AuditUnavailable):
                _ask(engine, api_key_id=7, channel="api:portal")
        assert record.call_count == 1

        record.reset_mock()  # an ordinary failure is still audited, exactly once
        engine._query = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(query_audit, "record", record), pytest.raises(RuntimeError):
            _ask(engine, api_key_id=7, channel="api:portal")
        assert record.call_count == 1

    def test_two_requests_can_migrate_the_table_at_once(self, tmp_path):
        """record() runs in a worker thread. SQLite has no ADD COLUMN IF NOT EXISTS: the thread that
        lost this race used to lose its audit row — and would now lose the answer with it."""
        import threading

        import app.models  # noqa: F401

        engine = create_engine(f"sqlite:///{tmp_path / 'pre_phase5.db'}")
        Base.metadata.create_all(engine)
        with engine.begin() as conn:  # an app DB from before Phase 5
            conn.execute(text("DROP INDEX IF EXISTS ix_query_audit_request_group"))
            conn.execute(text("ALTER TABLE query_audit DROP COLUMN request_group"))
        query_audit._tables_checked.clear()

        slow, failures = threading.Event(), []

        def create(*args, **kwargs):  # widen the window both threads used to run through together
            slow.wait(0.2)
            slow.set()

        def go():
            try:
                query_audit.ensure_table(engine)
            except Exception as exc:  # noqa: BLE001 — the point of the test
                failures.append(exc)

        with patch.object(QueryAudit.__table__, "create", create):
            threads = [threading.Thread(target=go) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)

        assert failures == []
        with engine.connect() as conn:
            assert "request_group" in {c["name"] for c in __import__("sqlalchemy").inspect(engine).get_columns("query_audit")}
