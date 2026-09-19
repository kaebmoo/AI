"""Plan 7 Phase 4.5 — audit of questions: one row per QueryEngine.query, searchable, exportable."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.query_audit import QueryAudit
from app.providers.base import QueryResult
from app.services import query_audit
from app.services import query_engine as qe
from app.services.data_sources import LEGACY_SOURCE, ScopeError

ADMIN = MagicMock()


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")  # empty app DB: the audit creates its own table
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def run(db, result=None, raises=None, **kwargs):
    admin_config = MagicMock()
    admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
    admin_config.get_feature_flags.return_value = {}
    admin_config.get_provider_record.return_value = None
    engine = qe.QueryEngine(mcp_client=MagicMock(), db_session=db, admin_config=admin_config)
    engine._schema_service = MagicMock()
    engine._schema_service.build_system_prompt.return_value = "prompt"
    provider = MagicMock()
    provider.get_model.return_value = None
    ai_service = MagicMock()
    ai_service.query_hybrid = AsyncMock(return_value=result, side_effect=raises)
    detector = MagicMock()
    detector.detect = AsyncMock(return_value=[])
    resolver = MagicMock()
    resolver.for_context.return_value = LEGACY_SOURCE
    qe._dedup_store.clear()
    with patch.object(qe, "source_resolver", resolver), patch.object(qe, "stores_results", return_value=True), \
         patch.object(qe, "workspace_of_context", return_value="nt-report"), \
         patch.object(qe.provider_registry, "create_provider", return_value=provider), \
         patch.object(qe, "AIService", return_value=ai_service), patch.object(qe, "WarningDetector", return_value=detector):
        return asyncio.run(engine.query("ยอดขายเดือนนี้", context="revenue", **kwargs))


ANSWER = QueryResult(question="ยอดขายเดือนนี้", sql_query="SELECT bu, SUM(v) AS total FROM t GROUP BY bu",
                     data=[{"bu": "ZQXSECRET", "total": 918273.5}, {"bu": "B", "total": 2}],
                     explanation="", tokens_used=0, provider="matcha")


def test_every_question_leaves_a_row_without_the_rows(db):
    qe._query_cache.clear()
    run(db, ANSWER, user_id=7, api_key_id=3, channel="nt-report-portal", scope={"year_month": 202607})
    run(db, ANSWER, user_id=7, api_key_id=3, channel="nt-report-portal", scope={"year_month": 202607})  # cache hit
    first, second = db.query(QueryAudit).order_by(QueryAudit.id).all()
    assert (first.user_id, first.api_key_id, first.channel, first.workspace, first.context_name) == \
        (7, 3, "nt-report-portal", "nt-report", "revenue")
    assert json.loads(first.scope) == {"year_month": 202607} and first.question == "ยอดขายเดือนนี้"
    assert first.sql_query == ANSWER.sql_query and json.loads(first.result_columns) == ["bu", "total"]
    assert (first.row_count, first.provider, first.llm_policy, first.cache_hit, first.error) == (2, "matcha", "full", False, None)
    assert second.cache_hit is True and second.row_count == 2
    stored = " ".join(str(getattr(first, c.name)) for c in QueryAudit.__table__.columns)
    assert "ZQXSECRET" not in stored and "918273" not in stored  # which columns and how many rows — never the values
    qe._query_cache.clear()


def test_refusals_and_failures_are_audited_and_still_raised(db):
    with pytest.raises(ScopeError):
        run(db, raises=ScopeError("scope ไม่รู้จัก ['org']"), api_key_id=3, scope={"org": "X"})
    row = db.query(QueryAudit).one()
    assert row.error.startswith("ScopeError") and row.api_key_id == 3 and json.loads(row.scope) == {"org": "X"}
    assert row.context_name == "revenue" and row.sql_query is None


def test_audit_trouble_never_breaks_the_answer(db, caplog):
    with patch.object(query_audit, "Session", side_effect=RuntimeError("disk full")):
        assert run(db, ANSWER).query_result.data
    assert "query audit NOT written" in caplog.text  # loud, unlike a silent pass
    assert run(None, ANSWER).query_result.data  # no session (scripts / eval) = nothing to write to


def test_search_and_csv_export(db):
    from app.api.v1.admin import analytics as api

    for i, (ctx, key, err) in enumerate([("feed_sales", 1, None), ("feed_sales", 2, "ScopeError: x"), ("revenue", 1, None)]):
        query_audit.record(db, user_id=i, api_key_id=key, workspace="nt-report" if ctx.startswith("feed") else "default",
                           context_name=ctx, question=f"คำถาม {i}", sql_query=f"SELECT {i} FROM {ctx}", error=err, row_count=i)

    def search(**kw):
        params = dict(skip=0, limit=50, date_from=None, date_to=None, user_id=None, api_key_id=None, workspace=None,
                      context=None, has_error=False, q=None, format="json")
        return api.get_query_audit(**{**params, **kw}, _current_user=ADMIN, db=db)

    assert search()["total"] == 3
    assert [r["context_name"] for r in search(api_key_id=1)["items"]] == ["revenue", "feed_sales"]  # newest first
    assert search(workspace="nt-report", has_error=True)["items"][0]["error"] == "ScopeError: x"
    assert search(q="FROM revenue")["total"] == 1 and search(q="คำถาม 1")["total"] == 1
    assert search(date_from="2999-01-01")["total"] == 0
    with pytest.raises(HTTPException) as exc:
        search(date_from="yesterday")
    assert exc.value.status_code == 400
    export = search(format="csv", context="feed_sales")
    body = export.body.decode("utf-8-sig")
    assert export.media_type.startswith("text/csv") and body.splitlines()[0].startswith("id,created_at,user_id,api_key_id")
    assert "คำถาม 1" in body and "คำถาม 2" not in body and len(body.splitlines()) == 3


def test_query_endpoint_tells_the_engine_which_key_and_caller(tmp_path):
    """/api/v1/query is the channel Phase 4 opened to other systems — before Phase 4.5 it left no trace."""
    from types import SimpleNamespace

    from app.api.v1 import query as query_api
    from app.core.llm_policy import LLMPolicyError

    def call(state, body):
        request = SimpleNamespace(state=state, app=SimpleNamespace(state=SimpleNamespace(mcp_client=MagicMock())))
        engine = MagicMock()
        engine.query = AsyncMock(side_effect=LLMPolicyError("stop"))
        with patch("app.services.query_engine.QueryEngine", return_value=engine), pytest.raises(HTTPException) as exc, \
             patch.object(query_api, "allowed_contexts", return_value=None):
            asyncio.run(query_api.simple_query(body, request, current_user=SimpleNamespace(id=1), db=MagicMock(),
                                               admin_config=MagicMock()))
        assert exc.value.status_code == 403  # a policy refusal is a 403, not a 200 with an error text
        return engine.query.call_args.kwargs

    kwargs = call(SimpleNamespace(api_key=SimpleNamespace(id=42)),
                  query_api.SimpleQueryRequest(question="q", source="nt-report-portal"))
    assert (kwargs["api_key_id"], kwargs["channel"], kwargs["user_id"]) == (42, "nt-report-portal", 1)
    kwargs = call(SimpleNamespace(), query_api.SimpleQueryRequest(question="q"))
    assert (kwargs["api_key_id"], kwargs["channel"]) == (None, "api")
