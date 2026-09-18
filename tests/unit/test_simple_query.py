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
