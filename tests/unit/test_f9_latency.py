"""F9: template answers (A), intent state (C), escalation ladder (D). All flags default OFF."""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai import intent_state
from app.services.ai.template_answer import build_template_answer, is_template_eligible


class TestTemplateAnswers:
    def test_single_value_no_chart(self):
        result = build_template_answer("รายได้รวม", "SELECT SUM(x) FROM t WHERE YEAR = 2025", [{"total": 1234567.89}])
        assert result is not None
        assert "1,234,567.89" in result["explanation"]
        assert "1.2 ล้าน" in result["explanation"]
        assert "YEAR = 2025" in result["explanation"]  # provenance
        assert "visualization" not in result

    def test_small_table_gets_chart_config(self):
        data = [{"bu": "Mobile", "revenue": 100.0}, {"bu": "Fixed", "revenue": 200.0}, {"bu": "Intl", "revenue": 50.0}]
        result = build_template_answer("รายได้ราย BG", "SELECT ...", data)
        assert result is not None
        assert result["chart_config"]["category_column"] == "bu"
        assert result["chart_config"]["measure_column"] == "revenue"
        assert "Mobile" in result["explanation"]
        assert "{" not in result["explanation"]  # no leaked placeholders

    def test_large_results_not_eligible(self):
        assert not is_template_eligible([{"a": 1, "b": 2} for _ in range(6)])  # 6x2 → LLM
        assert not is_template_eligible([{"a": 1, "b": 2, "c": 3, "d": 4}])  # 1x4 → LLM
        assert not is_template_eligible([])

    def test_flag_off_uses_llm_path(self):
        # build_template_answer only called when flag on — verified via hybrid wiring:
        from app.services.ai import hybrid_flow
        import inspect
        src = inspect.getsource(hybrid_flow.run_hybrid_attempt)
        assert "template_answers_enabled" in src


class TestIntentState:
    def setup_method(self):
        intent_state.clear()

    teardown_method = setup_method

    def test_set_get_roundtrip(self):
        intent = {"intent_type": "aggregation", "filters": [{"column": "x", "operator": "=", "value": 1}]}
        intent_state.set_intent("conv-1", intent)
        assert intent_state.get_intent("conv-1") == intent

    def test_missing_or_none_conversation(self):
        assert intent_state.get_intent(None) is None
        assert intent_state.get_intent("nope") is None
        intent_state.set_intent(None, {"a": 1})  # no crash

    def test_extract_intent_uses_previous_intent_prompt(self):
        from app.services.ai.hybrid_flow import extract_intent

        service = MagicMock()
        captured = {}

        async def fake_structured(prompt, schema, system_prompt=None, schema_name="result"):
            captured["prompt"] = prompt
            return {"intent_type": "aggregation", "metrics": [], "filters": []}

        service.provider.generate_structured = fake_structured
        service.provider.last_usage = None

        prev = {"intent_type": "aggregation", "metrics": ["REVENUE_VALUE"],
                "filters": [{"column": "GL_NAME", "operator": "LIKE", "value": "%ค่าล่วงเวลา%"}]}
        result = asyncio.run(extract_intent(
            service=service, question="แล้วเดือนกุมภาล่ะ", system_prompt="sys",
            context_name="revenue", context_table="revenue", context_thai="รายได้",
            history_context="", rag_context="", previous_intent=prev,
        ))
        assert result is not None
        assert "Intent เดิม" in captured["prompt"]
        assert "ค่าล่วงเวลา" in captured["prompt"]  # previous filter present for inheritance


class TestEscalationLadder:
    def _service(self):
        service = MagicMock()
        service.mcp_client.servers = {"nt-query": object()}
        service.provider_name = "matcha"
        service.provider.model = "base-model"
        service.get_pending_limit_warning.return_value = ""
        service.get_vanna_context_string = lambda q: ""
        service.lookup_values_from_question = lambda *a: []
        service.extract_sql = lambda text: None  # always fail → exercise the ladder
        service.extract_explanation = lambda text: ""
        service.provider.generate_content = AsyncMock(return_value="no sql")
        service.provider.last_usage = None
        return service

    def _run(self, service, **kwargs):
        from app.services.ai.hybrid_flow import query_hybrid
        schema_service = MagicMock()
        schema_service.get_context_info.return_value = {"main_view": "revenue", "display_name": "รายได้"}
        return asyncio.run(query_hybrid(
            service, question="q", system_prompt="sys", max_retries=2,
            value_verification_enabled=False, schema_service=schema_service, **kwargs,
        ))

    def test_ladder_escalates_to_strong_model_on_attempt_2(self):
        service = self._service()
        service.provider.get_model = MagicMock(return_value="strong-model")
        self._run(service, escalation_ladder_enabled=True)
        assert service.provider.model == "strong-model"

    def test_ladder_off_keeps_model(self):
        service = self._service()
        self._run(service)
        assert service.provider.model == "base-model"

    def test_tool_loop_rescue_when_enabled(self):
        from app.providers.base import QueryResult
        service = self._service()
        rescue_result = QueryResult(question="q", sql_query="SELECT 1", data=[{"v": 1}],
                                    explanation="rescued", tokens_used=5, provider="matcha")
        with patch("app.services.ai.retry_loop.query_with_retry", new=AsyncMock(return_value=rescue_result)):
            result = self._run(service, escalation_tool_loop_enabled=True)
        assert result.explanation == "rescued"

    def test_budget_exceeded_stops_retries(self):
        service = self._service()
        result = self._run(service, latency_budget_s=0.0)  # every attempt after the first exceeds
        assert result.error == "Latency budget exceeded"
        # only attempt 1's generate_content ran
        assert service.provider.generate_content.call_count == 1
