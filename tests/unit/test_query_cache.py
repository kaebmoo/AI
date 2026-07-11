"""
F1.1: Query result cache must be first-turn only (history bypasses cache)
and cache HIT must not mutate the shared cached object.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.base import QueryResult
from app.services import query_engine as qe_module
from app.services.query_engine import QueryEngine


def _make_query_result(question="รายได้รวมปี 2568"):
    return QueryResult(
        question=question,
        sql_query="SELECT SUM(REVENUE_VALUE) FROM revenue",
        data=[{"total": 100}],
        explanation="รายได้รวม 100 บาท",
        tokens_used=10,
        provider="matcha",
    )


@pytest.fixture
def engine():
    """QueryEngine with everything external mocked out."""
    qe_module._query_cache.clear()
    qe_module._dedup_store.clear()

    admin_config = MagicMock()
    admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
    admin_config.get_feature_flags.return_value = {}
    admin_config.get_provider_record.return_value = None

    engine = QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)
    engine._schema_service = MagicMock()
    engine._schema_service.build_system_prompt.return_value = "system prompt"
    engine._schema_service.get_all_contexts.return_value = [{"name": "revenue", "keywords": [], "priority": 0}]
    yield engine
    qe_module._query_cache.clear()
    qe_module._dedup_store.clear()


def _patched_run(engine, question, history=None, user_id=1):
    """Run engine.query with AIService/provider/warnings mocked. Returns (result, ai_service_mock)."""
    provider = MagicMock()
    provider.is_configured.return_value = True
    provider.get_model.return_value = None
    provider.model = "m1"

    ai_service = MagicMock()
    ai_service.query_hybrid = AsyncMock(return_value=_make_query_result(question))

    warning_detector = MagicMock()
    warning_detector.detect = AsyncMock(return_value=[])

    import asyncio
    with patch.object(qe_module.provider_registry, "create_provider", return_value=provider), \
         patch.object(qe_module, "AIService", return_value=ai_service), \
         patch.object(qe_module, "WarningDetector", return_value=warning_detector):
        result = asyncio.run(engine.query(question, history=history, user_id=user_id))
    return result, ai_service


class TestQueryCacheHistoryBehavior:
    def test_first_turn_second_call_hits_cache(self, engine):
        q = "รายได้รวมปี 2568"
        _, ai1 = _patched_run(engine, q, history=None, user_id=1)
        assert ai1.query_hybrid.call_count == 1

        result2, ai2 = _patched_run(engine, q, history=None, user_id=1)
        # Cache HIT — AIService of second call never invoked
        assert ai2.query_hybrid.call_count == 0
        assert result2.query_result.data == [{"total": 100}]

    def test_with_history_bypasses_cache(self, engine):
        q = "แล้วเดือนกุมภาล่ะ"
        history = [{"role": "user", "content": "รายได้เดือนมกราคม"}]
        _, ai1 = _patched_run(engine, q, history=None, user_id=1)
        assert ai1.query_hybrid.call_count == 1

        qe_module._dedup_store.clear()  # dedup is not what we're testing
        _, ai2 = _patched_run(engine, q, history=history, user_id=1)
        # History present → cache must be bypassed, AI called again
        assert ai2.query_hybrid.call_count == 1

    def test_with_history_does_not_store_in_cache(self, engine):
        q = "แล้วเดือนกุมภาล่ะ"
        history = [{"role": "user", "content": "รายได้เดือนมกราคม"}]
        _patched_run(engine, q, history=history, user_id=1)
        assert len(qe_module._query_cache) == 0

    def test_cache_hit_does_not_mutate_cached_entry(self, engine):
        q = "รายได้รวมปี 2568"
        _patched_run(engine, q, history=None, user_id=1)
        assert len(qe_module._query_cache) == 1
        cached_entry = next(iter(qe_module._query_cache.values()))["result"]
        original_time = cached_entry.execution_time_ms

        result2, _ = _patched_run(engine, q, history=None, user_id=1)
        # Returned object is a copy; the cached entry is untouched
        assert result2 is not cached_entry
        assert cached_entry.execution_time_ms == original_time
