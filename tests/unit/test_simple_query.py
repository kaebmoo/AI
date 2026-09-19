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
    """GET /query/contexts."""

    def test_contexts_list(self, client):
        """GET /query/contexts → list (public, no auth needed)."""
        resp = client.get("/api/v1/query/contexts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


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
