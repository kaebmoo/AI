"""
Plan 4B: Simple Query Endpoint Tests
======================================
Tests the /query/ endpoint for external integrations.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.models.session import UserSession


def _mock_query_engine_result(explanation="test", error=None, data=None, sql="SELECT 1", context="revenue"):
    """Create a mock QueryEngineResult matching real shape: result.query_result.xxx + result.context_name."""
    qr = MagicMock()
    qr.explanation = explanation
    qr.error = error
    qr.data = data or []
    qr.sql_query = sql

    result = MagicMock()
    result.query_result = qr
    result.context_name = context
    result.execution_time_ms = 123.4
    result.data_as_of = None
    return result


@pytest.fixture
def query_client(client, test_user, db_session):
    """Create an authenticated test client with mcp_client available."""
    from app.main import app
    from app.api import deps

    session = UserSession(
        user_id=test_user.id,
        session_token="query_test_token",
        platform="web",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        last_activity=datetime.utcnow(),
    )
    db_session.add(session)
    db_session.commit()
    client.headers["X-Session-Token"] = "query_test_token"

    # Override ai_service dependency (query.py no longer uses it but keep for safety)
    mock_ai = MagicMock()
    app.dependency_overrides[deps.get_ai_service] = lambda: mock_ai

    # Set mcp_client on app state so query.py can access it
    if not hasattr(app.state, "mcp_client"):
        app.state.mcp_client = MagicMock()

    yield client

    app.dependency_overrides.pop(deps.get_ai_service, None)


class TestSimpleQueryEndpoint:
    """POST /query/ endpoint tests."""

    def test_query_requires_auth(self, client):
        """POST /query/ without auth → 401."""
        resp = client.post("/api/v1/query/", json={"question": "รายได้รวม"})
        assert resp.status_code == 401

    def test_query_basic(self, query_client):
        """POST /query/ with valid question → answer returned."""
        mock_result = _mock_query_engine_result(
            explanation="รายได้รวมคือ 100 ล้านบาท",
            data=[{"total": 100000000}],
            sql="SELECT SUM(REVENUE_VALUE) FROM revenue",
        )

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = query_client.post("/api/v1/query/", json={"question": "รายได้รวม"})

        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert data["answer"] != ""

    def test_data_as_of_passed_through(self, query_client):
        """Plan 7: file-source answers carry the build they were read from; legacy = null."""
        as_of = {"period": 202608, "built_at": "2026-09-11T01:37:35+00:00", "build_id": None}
        file_result = _mock_query_engine_result(context="feed_revenue")
        file_result.data_as_of = as_of

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            MockEngine.return_value.query = AsyncMock(return_value=file_result)
            resp = query_client.post("/api/v1/query/", json={"question": "q", "context": "feed_revenue"})
        assert resp.json()["data_as_of"] == as_of

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            MockEngine.return_value.query = AsyncMock(return_value=_mock_query_engine_result())
            resp = query_client.post("/api/v1/query/", json={"question": "q"})
        assert resp.json()["data_as_of"] is None

    def test_scope_passed_and_unenforceable_scope_is_400(self, query_client):
        """Plan 7 Phase 3: scope is enforced or refused — never silently dropped."""
        from app.services.data_sources import ScopeError

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            MockEngine.return_value.query = AsyncMock(side_effect=ScopeError("scope ไม่รู้จัก ['division']"))
            resp = query_client.post("/api/v1/query/", json={
                "question": "q", "context": "feed_revenue", "scope": {"division": "x"}})
        assert resp.status_code == 400
        assert MockEngine.return_value.query.call_args.kwargs["scope"] == {"division": "x"}

    def test_pinned_filters_stay_log_only(self, query_client):
        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            MockEngine.return_value.query = AsyncMock(return_value=_mock_query_engine_result())
            resp = query_client.post("/api/v1/query/", json={"question": "q", "pinned_filters": {"year_month": 202607}})
        assert resp.status_code == 200
        assert MockEngine.return_value.query.call_args.kwargs["scope"] is None

    def test_query_with_include_sql(self, query_client):
        """POST /query/ with include_sql=true → SQL included."""
        mock_result = _mock_query_engine_result(sql="SELECT 1 FROM revenue")

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = query_client.post(
                "/api/v1/query/",
                json={"question": "test", "include_sql": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("sql") is not None

    def test_query_with_include_data(self, query_client):
        """POST /query/ with include_data=true → data rows included."""
        mock_result = _mock_query_engine_result(data=[{"col": "val1"}, {"col": "val2"}])

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = query_client.post(
                "/api/v1/query/",
                json={"question": "test", "include_data": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("data") is not None
        assert len(data["data"]) == 2

    def test_query_without_include_data(self, query_client):
        """POST /query/ with include_data=false → data=null."""
        mock_result = _mock_query_engine_result(data=[{"col": "val"}])

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = query_client.post(
                "/api/v1/query/",
                json={"question": "test", "include_data": False},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("data") is None

    def test_query_max_rows_truncation(self, query_client):
        """POST /query/ with max_rows=2 → data truncated to 2."""
        mock_result = _mock_query_engine_result(
            data=[{"v": 1}, {"v": 2}, {"v": 3}, {"v": 4}, {"v": 5}]
        )

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = query_client.post(
                "/api/v1/query/",
                json={"question": "test", "include_data": True, "max_rows": 2},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 2


class TestPortalFields:
    """F11 Phase A: optional portal fields accepted without breaking the contract."""

    def test_query_with_pinned_filters_and_source(self, query_client):
        mock_result = _mock_query_engine_result(explanation="ok", data=[{"v": 1}], context="feed_revenue")

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = query_client.post("/api/v1/query/", json={
                "question": "รายได้รวมเดือนพฤษภาคม 2569",
                "context": "feed_revenue",
                "source": "portal",
                "pinned_filters": {"year_month": 202605},
            })

        assert resp.status_code == 200
        assert resp.json()["context"] == "feed_revenue"
        # context forwarded to the engine
        assert instance.query.call_args.kwargs["context"] == "feed_revenue"


class TestQueryContextsEndpoint:
    """GET /query/contexts — hardening: credentials required (it used to be public, and an unusable
    key listed every context of every workspace)."""

    def test_contexts_list_needs_credentials(self, client):
        assert client.get("/api/v1/query/contexts").status_code == 401
        assert client.get("/api/v1/query/contexts", headers={"X-API-Key": "ntai_" + "0" * 64}).status_code == 401
        assert client.get("/api/v1/query/contexts", headers={"X-API-Key": "not-a-key"}).status_code == 401

    def test_contexts_list_for_a_signed_in_person(self, query_client):
        resp = query_client.get("/api/v1/query/contexts")
        assert resp.status_code == 200 and isinstance(resp.json(), list)

    def test_a_key_sees_its_own_workspace_and_spends_no_quota(self, client, test_user, db_session):
        from app.services.api_key_service import APIKeyService

        service = APIKeyService(db_session)
        raw, key = service.create_key(user_id=test_user.id, name="portal", allowed_contexts='["feed_sales"]')
        with patch("app.api.v1.query.contexts_for", return_value=[]) as listed:
            assert client.get("/api/v1/query/contexts", headers={"X-API-Key": raw}).status_code == 200
        assert listed.call_args.args[0] == frozenset({"feed_sales"})
        assert service.usage_today(key.id) == 0  # listing is not a question

        service.revoke_key(key.id)
        assert client.get("/api/v1/query/contexts", headers={"X-API-Key": raw}).status_code == 401


class TestMultiContextResponse:
    """Plan 7 Phase 5: a question answered from several contexts — `parts` per context, refusals keep their status."""

    @staticmethod
    def _multi():
        from app.providers.base import QueryResult
        from app.services import multi_context as mc
        from app.services.query_engine import QueryEngineResult

        def part(context, value, period):
            result = QueryEngineResult(
                query_result=QueryResult(question="q", sql_query=f"SELECT v FROM {context}", data=[{"v": value}, {"v": 0.0}],
                                         explanation={"explanation": f"คำตอบ {context}"}, tokens_used=0, provider="matcha"),
                context_name=context, data_as_of={"period": period})
            return mc.Part(context=context, question=f"ถาม {context}", result=result)

        return mc.MultiResult(parts=[part("feed_revenue", 3.0, 202608), part("feed_ebt", 2.0, 202607)], answer="รวม",
                              warnings=["งวดไม่เท่ากัน"], execution_time_ms=10.0, request_group="g")

    def test_parts_carry_context_freshness_and_optional_sql_and_data(self, query_client):
        with patch("app.services.multi_context.ask", AsyncMock(return_value=self._multi())):
            body = query_client.post("/api/v1/query/", json={"question": "รายได้และ EBT", "include_sql": True,
                                                              "include_data": True, "max_rows": 1}).json()
        assert body["answer"] == "รวม" and body["context"] == "feed_revenue+feed_ebt" and body["row_count"] == 4
        assert body["data_as_of"] is None and body["error"] is None  # freshness is per part
        first, second = body["parts"]
        assert first == {"context": "feed_revenue", "question": "ถาม feed_revenue", "answer": "คำตอบ feed_revenue", "row_count": 2,
                         "error": None, "data_as_of": {"period": 202608}, "sql": "SELECT v FROM feed_revenue", "data": [{"v": 3.0}]}
        assert second["data_as_of"] == {"period": 202607}
        with patch("app.services.multi_context.ask", AsyncMock(return_value=self._multi())):
            plain = query_client.post("/api/v1/query/", json={"question": "รายได้และ EBT"}).json()
        assert "sql" not in plain["parts"][0] and "data" not in plain["parts"][0]

    def test_single_context_answer_has_no_parts(self, query_client):
        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            MockEngine.return_value.query = AsyncMock(return_value=_mock_query_engine_result(data=[{"v": 1}]))
            body = query_client.post("/api/v1/query/", json={"question": "รายได้รวม"}).json()
        assert body["parts"] is None and body["computed"] is None and body["answer"] == "test"

    def test_refusal_of_a_sub_question_keeps_its_status(self, query_client):
        from app.services.data_sources import ScopeError
        from app.services.workspaces import ContextNotAllowed
        for refusal, status in ((ScopeError("scope"), 400), (ContextNotAllowed("นอกสิทธิ์"), 403)):
            with patch("app.services.multi_context.ask", AsyncMock(side_effect=refusal)):
                assert query_client.post("/api/v1/query/", json={"question": "รายได้และค่าใช้จ่าย"}).status_code == status


class TestNothingInternalLeaves:
    """Plan 7 hardening: /api/v1/query answers a caller outside the process. The engine's prose
    quotes the SQL it ran (a result with no rows) and the text of the exception that stopped it —
    neither leaves here. Chat / telegram are unchanged: there the person needs to see both."""

    # the shape hybrid_flow.py:313/776 produces for a query that ran and matched nothing
    NO_ROWS = ("ไม่พบข้อมูลที่ตรงกับเงื่อนไข\n\nSQL ที่ใช้:\n```sql\nSELECT SUM(x) FROM secret_table\n```\n\n"
               "อาจเป็นเพราะ:\n- ไม่มีข้อมูลที่ตรงกับคำค้นหา")

    @staticmethod
    def _ask(query_client, result=None, exc=None, **body):
        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            MockEngine.return_value.query = AsyncMock(return_value=result, side_effect=exc)
            return query_client.post("/api/v1/query/", json={"question": "q", **body})

    def test_a_result_with_no_rows_never_carries_the_sql(self, query_client):
        from app.core.outbound import NO_DATA

        empty = _mock_query_engine_result(explanation=self.NO_ROWS, data=[], sql="SELECT SUM(x) FROM secret_table")
        body = self._ask(query_client, empty).json()
        assert body["answer"] == NO_DATA and "secret_table" not in body["answer"] and "```sql" not in body["answer"]
        assert body["sql"] is None and body["error"] is None

        asked = self._ask(query_client, empty, include_sql=True).json()  # asked for = its own field, not the prose
        assert asked["sql"] == "SELECT SUM(x) FROM secret_table" and asked["answer"] == NO_DATA

    def test_a_failed_result_gives_a_code_not_the_exception(self, query_client):
        from app.core.outbound import ERRORS

        failed = _mock_query_engine_result(
            explanation="เกิดข้อผิดพลาด: no such table: secret_table (/Users/seal/nt_fi_report.sqlite)",
            error="OperationalError: no such table: secret_table", data=[])
        body = self._ask(query_client, failed).json()
        assert body["error"] == "query_failed" and body["answer"] == ERRORS["query_failed"][1]
        assert "secret_table" not in str(body) and "/Users" not in str(body)

    def test_a_raised_failure_gives_a_code_not_the_exception(self, query_client):
        from app.core.outbound import ERRORS

        body = self._ask(query_client, exc=RuntimeError("boom at /Users/seal/app/services/x.py")).json()
        assert body["error"] == "internal_error" and body["answer"] == ERRORS["internal_error"][1]
        assert "/Users" not in str(body) and "boom" not in str(body)

    def test_a_source_being_published_keeps_its_meaning_without_the_path(self, query_client):
        from app.core.outbound import ERRORS
        from app.services.database_adapter import SourceUnavailable

        body = self._ask(query_client, exc=SourceUnavailable(
            "ไม่พบโฟลเดอร์ของ source 'feed_sales' (/Users/seal/DataFeed/dist/sales/latest) — ข้อมูลอาจกำลังถูก publish")).json()
        assert body["error"] == "source_unavailable" and body["answer"] == ERRORS["source_unavailable"][1]
        assert "publish" in body["answer"] and "/Users" not in str(body)

    def test_a_structured_explanation_is_text_not_str_of_a_dict(self, query_client):
        structured = _mock_query_engine_result(
            explanation={"explanation": "รายได้รวม 100 บาท", "chart_config": {"type": "bar"}}, data=[{"v": 100}])
        answer = self._ask(query_client, structured).json()["answer"]
        assert answer == "รายได้รวม 100 บาท" and "chart_config" not in answer

    def test_duplicate_request_keeps_its_own_code(self, query_client):
        from app.core.outbound import ERRORS

        blocked = _mock_query_engine_result(explanation="คำถามซ้ำ", error="duplicate_request", data=[])
        body = self._ask(query_client, blocked).json()
        assert body["error"] == "duplicate_request" and body["answer"] == ERRORS["duplicate_request"][1]

    def test_a_failed_part_of_a_multi_context_answer_reports_a_code(self, query_client):
        from app.core.outbound import ERRORS
        from app.services.multi_context import MultiResult, Part

        good = Part(context="feed_revenue", question="a", result=_mock_query_engine_result(
            explanation="รายได้ 5 บาท", data=[{"v": 5}], context="feed_revenue"))
        bad = Part(context="feed_expense", question="b", error="Binder Error: secret_col (/Users/seal/x)",
                   error_code="query_failed")
        multi = MultiResult(parts=[good, bad], answer="รวม", warnings=["ตอบได้ 1 จาก 2 ส่วน"], execution_time_ms=1.0)

        with patch("app.services.multi_context.ask", AsyncMock(return_value=multi)), \
                patch("app.services.query_engine.QueryEngine"):
            body = query_client.post("/api/v1/query/", json={"question": "q"}).json()

        parts = body["parts"]
        assert parts[1]["error"] == "query_failed" and parts[1]["answer"] == ERRORS["query_failed"][1]
        assert "secret_col" not in str(body) and "/Users" not in str(body)

    def test_a_key_over_its_quota_is_429_not_401(self, client, test_user, db_session):
        """An existing key that is simply out of budget is not 'unauthenticated' — 401 sent the caller
        looking for a bad key (and let the portal retry with the same one)."""
        from app.services.api_key_service import APIKeyService

        service = APIKeyService(db_session)
        raw, key = service.create_key(user_id=test_user.id, name="portal", rate_limit_per_day=1)
        service.track_usage(key.id)  # the day's budget is now spent

        resp = client.post("/api/v1/query/", json={"question": "q"}, headers={"X-API-Key": raw})
        assert resp.status_code == 429 and "rate limit" in resp.json()["detail"]

        assert service.check_key(raw) == (None, "rate_limited")
        assert service.check_key("ntai_" + "0" * 64) == (None, "unauthorized")

    @pytest.mark.parametrize("exc,code,status,secret", [
        ("scope_unknown", "invalid_scope", 400, "year_month"),
        ("scope_unmigrated", "invalid_scope", 400, "scripts/migrate_data_sources.py"),
        ("policy", "policy_refused", 403, "llm_provider_allowlist"),
        ("forbidden", "context_not_allowed", 403, "feed_secret"),
        ("missing", "context_not_allowed", 403, "feed_secret"),
    ])
    def test_a_refusal_is_not_explained_in_the_words_it_was_refused_in(self, query_client, exc, code, status, secret):
        """400/403 keep their status — the portal branches on it — but the reason names the context's
        scope columns, an internal source and its policy, a migration script, and whether a context
        exists at all. Two different ContextNotAllowed wordings were an existence oracle."""
        from app.core.llm_policy import LLMPolicyError
        from app.core.outbound import ERRORS
        from app.services.data_sources import ScopeError
        from app.services.workspaces import ContextNotAllowed

        raised = {
            "scope_unknown": ScopeError("scope ไม่รู้จัก ['division'] — context นี้รองรับ ['year_month', 'org_code']"),
            "scope_unmigrated": ScopeError("config DB ยังไม่รองรับ scope — รัน scripts/migrate_data_sources.py"),
            "policy": LLMPolicyError("provider 'claude' ไม่อยู่ใน llm_provider_allowlist ของ source 'feed_secret'"),
            "forbidden": ContextNotAllowed("API key นี้ไม่มีสิทธิ์ใช้ context 'feed_secret'"),
            "missing": ContextNotAllowed("ไม่พบ context 'feed_secret' สำหรับ API key นี้"),
        }[exc]

        resp = self._ask(query_client, exc=raised)
        assert resp.status_code == status and resp.json()["detail"] == ERRORS[code][1]
        assert secret not in resp.text
