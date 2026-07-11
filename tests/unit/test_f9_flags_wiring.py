"""P1 review fix: F9 flags set via admin config must actually reach QueryEngine/hybrid flow."""

import asyncio

from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.base import QueryResult
from app.services import query_engine as qe_module
from app.services.query_engine import QueryEngine


class TestFeatureFlagsExposeF9Keys:
    def _service_with(self, values: dict):
        from app.services.admin_config_service import AdminConfigService
        svc = AdminConfigService(db=MagicMock())
        svc.get_config = lambda key, default=None: values.get(key, default)
        return svc

    def test_f9_keys_present_with_defaults(self):
        flags = self._service_with({}).get_feature_flags()
        assert flags["template_answers_enabled"] is False
        assert flags["intent_state_enabled"] is False
        assert flags["escalation_ladder_enabled"] is False
        assert flags["escalation_tool_loop_enabled"] is False
        assert flags["query_latency_budget_s"] == 45.0

    def test_admin_enabled_values_flow_through(self):
        flags = self._service_with({
            "template_answers_enabled": "true",
            "escalation_ladder_enabled": "true",
            "query_latency_budget_s": "90",
        }).get_feature_flags()
        assert flags["template_answers_enabled"] is True
        assert flags["escalation_ladder_enabled"] is True
        assert flags["query_latency_budget_s"] == 90.0

    def test_invalid_budget_falls_back(self):
        flags = self._service_with({"query_latency_budget_s": "not-a-number"}).get_feature_flags()
        assert flags["query_latency_budget_s"] == 45.0
        flags = self._service_with({"query_latency_budget_s": "-5"}).get_feature_flags()
        assert flags["query_latency_budget_s"] == 45.0


class TestFlagsReachHybridFlow:
    def test_query_engine_forwards_f9_flags_to_query_hybrid(self):
        qe_module._query_cache.clear()
        qe_module._dedup_store.clear()

        admin_config = MagicMock()
        admin_config.get_ai_config.return_value = {"default_provider": "matcha"}
        admin_config.get_feature_flags.return_value = {
            "template_answers_enabled": True,
            "intent_state_enabled": True,
            "escalation_ladder_enabled": True,
            "escalation_tool_loop_enabled": True,
            "query_latency_budget_s": 90.0,
        }
        admin_config.get_provider_record.return_value = None

        engine = QueryEngine(mcp_client=MagicMock(), admin_config=admin_config)
        engine._schema_service = MagicMock()
        engine._schema_service.build_system_prompt.return_value = "sys"
        engine._schema_service.get_all_contexts.return_value = [{"name": "revenue", "keywords": [], "priority": 0}]

        provider = MagicMock()
        provider.is_configured.return_value = True
        provider.get_model.return_value = None
        provider.model = "m"

        result = QueryResult(question="q", sql_query="SELECT 1", data=[{"v": 1}],
                             explanation="ok", tokens_used=1, provider="matcha")
        ai_service = MagicMock()
        ai_service.query_hybrid = AsyncMock(return_value=result)
        warning_detector = MagicMock()
        warning_detector.detect = AsyncMock(return_value=[])

        with patch.object(qe_module.provider_registry, "create_provider", return_value=provider), \
             patch.object(qe_module, "AIService", return_value=ai_service), \
             patch.object(qe_module, "WarningDetector", return_value=warning_detector):
            asyncio.run(engine.query("รายได้รวม", user_id=1))

        kwargs = ai_service.query_hybrid.call_args.kwargs
        assert kwargs["template_answers_enabled"] is True
        assert kwargs["intent_state_enabled"] is True
        assert kwargs["escalation_ladder_enabled"] is True
        assert kwargs["escalation_tool_loop_enabled"] is True
        assert kwargs["latency_budget_s"] == 90.0

        qe_module._query_cache.clear()
        qe_module._dedup_store.clear()
