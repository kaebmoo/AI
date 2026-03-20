"""
Plan 4B: Query Endpoint Integration Tests
===========================================
Tests /query/ endpoint with authentication and error handling.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.models.session import UserSession


def _mock_qe_result(explanation="test", error=None, data=None, sql="SELECT 1", context="revenue"):
    """Mock QueryEngineResult: result.query_result.xxx + result.context_name."""
    qr = MagicMock()
    qr.explanation = explanation
    qr.error = error
    qr.data = data or []
    qr.sql_query = sql

    result = MagicMock()
    result.query_result = qr
    result.context_name = context
    result.execution_time_ms = 50.0
    return result


@pytest.fixture
def query_client(client, test_user, db_session):
    """Create an authenticated test client with mcp_client on app state."""
    from app.main import app
    from app.api import deps

    session = UserSession(
        user_id=test_user.id,
        session_token="qe_auth_token",
        platform="web",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        last_activity=datetime.utcnow(),
    )
    db_session.add(session)
    db_session.commit()
    client.headers["X-Session-Token"] = "qe_auth_token"

    mock_ai = MagicMock()
    app.dependency_overrides[deps.get_ai_service] = lambda: mock_ai

    if not hasattr(app.state, "mcp_client"):
        app.state.mcp_client = MagicMock()

    yield client

    app.dependency_overrides.pop(deps.get_ai_service, None)


class TestQueryEndpoint:
    """Integration tests for POST /query/."""

    def test_query_basic_success(self, query_client):
        """POST /query/ → 200 with answer, context, execution_time."""
        mock_result = _mock_qe_result(
            explanation="รายได้รวม 100 ล้านบาท",
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
        assert "execution_time_ms" in data
        assert data["execution_time_ms"] >= 0

    def test_query_with_context(self, query_client):
        """POST /query/ with context parameter → uses specified context."""
        mock_result = _mock_qe_result(context="expense")

        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = query_client.post(
                "/api/v1/query/",
                json={"question": "ค่าใช้จ่าย", "context": "expense"},
            )

        assert resp.status_code == 200

    def test_query_error_handling(self, query_client):
        """POST /query/ with failing query → error field populated."""
        with patch("app.services.query_engine.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(side_effect=Exception("DB connection failed"))
            resp = query_client.post("/api/v1/query/", json={"question": "test"})

        assert resp.status_code == 200  # Errors are returned in response body
        data = resp.json()
        assert data.get("error") is not None

    def test_query_contexts_public(self, client):
        """GET /query/contexts → public endpoint, no auth."""
        resp = client.get("/api/v1/query/contexts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
