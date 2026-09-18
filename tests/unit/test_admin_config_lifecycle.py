"""
F2.1: Config DB sessions must be closed — no leaks from deps or QueryEngine.
F2.3: Dedup key released when the request fails, so an immediate retry works.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.base import QueryResult
from app.services import query_engine as qe_module
from app.services.query_engine import QueryEngine


class TestAdminConfigLifecycle:
    def test_get_admin_config_service_closes_session(self):
        from app.api import deps

        mock_session = MagicMock()
        with patch("app.db.session.ConfigSessionLocal", return_value=mock_session):
            gen = deps.get_admin_config_service()
            svc = next(gen)
            assert svc.db is mock_session
            assert mock_session.close.call_count == 0
            with pytest.raises(StopIteration):
                next(gen)  # dependency teardown
            mock_session.close.assert_called_once()

    def test_query_engine_fallback_close_releases_session(self):
        mock_session = MagicMock()
        with patch("app.db.session.ConfigSessionLocal", return_value=mock_session):
            engine = QueryEngine(mcp_client=MagicMock())
            assert engine._owns_admin_config is True
            engine.close()
            mock_session.close.assert_called_once()

    def test_query_engine_injected_config_not_closed(self):
        admin_config = MagicMock()
        engine = QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)
        assert engine._owns_admin_config is False
        engine.close()
        admin_config.close.assert_not_called()


class TestDedupRelease:
    def setup_method(self):
        qe_module._query_cache.clear()
        qe_module._dedup_store.clear()

    teardown_method = setup_method

    def _engine(self):
        admin_config = MagicMock()
        admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
        admin_config.get_feature_flags.return_value = {}
        admin_config.get_provider_record.return_value = None
        engine = QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)
        engine._schema_service = MagicMock()
        engine._schema_service.build_system_prompt.return_value = "sys"
        engine._schema_service.get_all_contexts.return_value = [{"name": "revenue", "keywords": [], "priority": 0}]
        return engine

    def _run(self, engine, question, error=None, exc=None):
        provider = MagicMock()
        provider.is_configured.return_value = True
        provider.get_model.return_value = None
        provider.model = "m1"

        result = QueryResult(
            question=question, sql_query="SELECT 1", data=[{"v": 1}] if not error else [],
            explanation="ok", tokens_used=1, provider="matcha", error=error,
        )
        ai_service = MagicMock()
        if exc:
            ai_service.query_hybrid = AsyncMock(side_effect=exc)
        else:
            ai_service.query_hybrid = AsyncMock(return_value=result)

        warning_detector = MagicMock()
        warning_detector.detect = AsyncMock(return_value=[])

        with patch.object(qe_module.provider_registry, "create_provider", return_value=provider), \
             patch.object(qe_module, "AIService", return_value=ai_service), \
             patch.object(qe_module, "WarningDetector", return_value=warning_detector):
            return asyncio.run(engine.query(question, user_id=1))

    def test_duplicate_within_ttl_blocked(self):
        engine = self._engine()
        self._run(engine, "รายได้รวม")
        qe_module._query_cache.clear()  # force past cache to hit the dedup gate
        result2 = self._run(engine, "รายได้รวม")
        assert result2.query_result.error == "duplicate_request"

    def test_error_result_releases_dedup_key(self):
        engine = self._engine()
        r1 = self._run(engine, "รายได้รวม", error="Max retries exceeded")
        assert r1.query_result.error == "Max retries exceeded"
        # Immediate retry must NOT be blocked
        r2 = self._run(engine, "รายได้รวม")
        assert r2.query_result.error is None

    def test_exception_releases_dedup_key(self):
        engine = self._engine()
        with pytest.raises(RuntimeError):
            self._run(engine, "รายได้รวม", exc=RuntimeError("boom"))
        r2 = self._run(engine, "รายได้รวม")
        assert r2.query_result.error is None


def test_dedup_blocked_result_keeps_the_request_context():
    """REMAIN-9.3: a duplicate request must not be recorded under the default 'revenue' context."""
    qe = qe_module
    admin_config = MagicMock()
    admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
    admin_config.get_feature_flags.return_value = {}
    engine = qe.QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)
    qe._dedup_store.clear()
    qe._dedup_mark("ค่าใช้จ่าย feed", "matcha", 7)  # the same request is already in flight
    blocked = asyncio.run(engine.query("ค่าใช้จ่าย feed", context="feed_expense", user_id=7))
    assert blocked.query_result.error == "duplicate_request" and blocked.context_name == "feed_expense"
    qe._dedup_store.clear()
