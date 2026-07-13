"""
F12: End-to-end proof that chat_history persists the POST-enrichment render
payload (the one _format_response mutates with the real max_series/warning),
not a pre-enrichment snapshot — POST /chat/ then GET /conversations/{id} must
return an identical chart_config.
"""
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.models.session import UserSession


def _mock_qe_result(question, sql, data, chart_config, visualization="bar_chart", context="revenue"):
    """Mock QueryEngineResult matching real shape: result.query_result.xxx + result.context_name."""
    qr = MagicMock()
    qr.question = question
    qr.sql_query = sql
    qr.data = data
    qr.error = None
    qr.explanation = {
        "explanation": "อธิบายผลลัพธ์",
        "visualization": visualization,
        "chart_config": chart_config,
        "display_hint": "flat",
        "hierarchy_columns": None,
    }
    qr.tokens_used = 50
    qr.retry_count = 0
    qr.retry_history = None
    qr.confidence = None

    result = MagicMock()
    result.query_result = qr
    result.context_name = context
    result.execution_time_ms = 42.0
    result.warnings = None
    return result


@pytest.fixture
def chat_render_client(client, test_user, db_session):
    from app.main import app
    from app.api import deps

    session = UserSession(
        user_id=test_user.id,
        session_token="chat_render_token",
        platform="web",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        last_activity=datetime.utcnow(),
    )
    db_session.add(session)
    db_session.commit()
    client.headers["X-Session-Token"] = "chat_render_token"

    mock_admin_config = MagicMock()
    mock_admin_config.get_chart_max_series.return_value = 3
    app.dependency_overrides[deps.get_admin_config_service] = lambda: mock_admin_config

    if not hasattr(app.state, "mcp_client"):
        app.state.mcp_client = MagicMock()

    yield client

    app.dependency_overrides.pop(deps.get_admin_config_service, None)


class TestChatRenderPersistenceRoundTrip:
    def test_chart_config_matches_between_chat_and_conversation(self, chat_render_client):
        # 7 distinct series values with max_series=3 → _format_response must
        # inject max_series=3 and recompute a "แสดง Top-" warning.
        data = [{"month": i, "total": i * 10} for i in range(1, 8)]
        chart_config = {
            "category_column": "month",
            "measure_column": "total",
            "series_column": "month",
        }
        mock_result = _mock_qe_result("รายได้รายเดือน", "SELECT 1", data, chart_config)

        with patch("app.api.v1.chat.QueryEngine") as MockEngine:
            instance = MockEngine.return_value
            instance.query = AsyncMock(return_value=mock_result)
            resp = chat_render_client.post("/api/v1/chat/", json={"question": "รายได้รายเดือน"})

        assert resp.status_code == 200
        chat_response = resp.json()
        assert chat_response["chart_config"]["max_series"] == 3
        assert chat_response["chart_config"]["warning"].startswith("แสดง Top-")

        conversation_id = chat_response["conversation_id"]
        conv_resp = chat_render_client.get(f"/api/v1/conversations/{conversation_id}")
        assert conv_resp.status_code == 200
        msg = conv_resp.json()["messages"][-1]

        # Persisted payload must carry every non-null field the client actually
        # saw — proves persistence happened AFTER _format_response's mutation,
        # not before. (chat_response has extra null-valued ChartConfig keys
        # because /chat/ re-serializes through the ChatResponse pydantic model;
        # the persisted dict is the raw pre-pydantic payload, by design — see
        # plan A.4 note on using Dict[str, Any] instead of the ChartConfig schema.)
        chat_chart_config_nonnull = {k: v for k, v in chat_response["chart_config"].items() if v is not None}
        assert msg["chart_config"] == chat_chart_config_nonnull
        assert msg["visualization"] == chat_response["visualization"]
        assert msg["data"] == chat_response["data"]
        assert msg["data_truncated"] is False
