"""
F1.2: Row-limit truncation warning must reach the user in hybrid mode,
triggered by the `truncated` flag in the execute_query dict payload.
"""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ai.hybrid_flow import LIMIT_WARNING_MESSAGE, query_hybrid


class FakeAIService:
    """Minimal stand-in for AIService with a real pending-warning slot."""

    def __init__(self, call_tool_side_effect, explanation="คำอธิบายผลลัพธ์"):
        self._pending = ""
        self.provider_name = "matcha"
        self.mcp_client = MagicMock()
        self.mcp_client.servers = {"nt-query": object()}  # no nt-validation → confidence skipped
        self.mcp_client.call_tool = AsyncMock(side_effect=call_tool_side_effect)
        self.provider = MagicMock()
        self.provider.model = "m1"
        self.provider.generate_content = AsyncMock(
            return_value="```sql\nSELECT * FROM revenue\n```\nคำอธิบาย"
        )
        self.provider.explain_result = AsyncMock(return_value=explanation)

    def get_pending_limit_warning(self):
        return self._pending

    def set_pending_limit_warning(self, warning):
        self._pending = warning

    # Helpers query_hybrid pulls off the service
    @staticmethod
    def extract_sql(text):
        return "SELECT * FROM revenue" if "SELECT" in text else None

    @staticmethod
    def extract_explanation(text):
        return "คำอธิบาย"

    def get_vanna_context_string(self, question):
        return ""

    def lookup_values_from_question(self, question, context_name, table_name):
        return []

    def detect_hierarchy_level(self, question, context_name):
        return None

    def format_value_matches(self, matches, hierarchy=None, detected_level=None):
        return ""

    def log_value_corrections(self, corrections, question, context_name):
        pass

    def prepare_data_for_explanation(self, data):
        return data


def _run(service):
    with patch(
        "app.services.ai.hybrid_flow.resolve_context_info",
        return_value=(MagicMock(), "revenue", "รายได้"),
    ), patch(
        "app.services.ai.hybrid_flow.load_execution_metadata",
        return_value=(None, None, None),
    ):
        return asyncio.run(
            query_hybrid(
                service,
                question="รายได้ทั้งหมด",
                system_prompt="sys",
                max_retries=1,
                value_verification_enabled=False,
            )
        )


def _call_tool_factory(exec_payloads):
    """exec_payloads: list of dicts returned by successive execute_query calls."""
    exec_iter = iter(exec_payloads)

    async def call_tool(tool_name, args):
        if tool_name == "validate_sql":
            return json.dumps({"valid": True})
        if tool_name == "execute_query":
            return json.dumps(next(exec_iter))
        return None

    return call_tool


class TestHybridLimitWarning:
    def test_truncated_dict_payload_appends_warning_str(self):
        service = FakeAIService(_call_tool_factory([
            {"success": True, "data": [{"v": 1}], "truncated": True},
        ]))
        result = _run(service)
        assert result.error is None
        assert isinstance(result.explanation, str)
        assert result.explanation.endswith(LIMIT_WARNING_MESSAGE)

    def test_truncated_dict_payload_appends_warning_dict(self):
        service = FakeAIService(
            _call_tool_factory([{"success": True, "data": [{"v": 1}], "truncated": True}]),
            explanation={"explanation": "คำอธิบาย", "chart_config": {}},
        )
        result = _run(service)
        assert result.error is None
        assert isinstance(result.explanation, dict)
        assert result.explanation["explanation"].endswith(LIMIT_WARNING_MESSAGE)

    def test_not_truncated_no_warning(self):
        service = FakeAIService(_call_tool_factory([
            {"success": True, "data": [{"v": 1}], "truncated": False},
        ]))
        result = _run(service)
        assert result.error is None
        assert LIMIT_WARNING_MESSAGE not in str(result.explanation)

    def test_failed_truncated_attempt_does_not_leak_warning_into_retry(self):
        # Attempt 1: truncated but execution fails → retry.
        # Attempt 2: success, not truncated → must NOT carry attempt 1's warning.
        service = FakeAIService(_call_tool_factory([
            {"success": False, "error": "boom", "truncated": True},
            {"success": True, "data": [{"v": 1}], "truncated": False},
        ]))
        result = _run(service)
        assert result.error is None
        assert LIMIT_WARNING_MESSAGE not in str(result.explanation)

    def test_legacy_list_payload_at_limit_appends_warning(self):
        rows = [{"v": i} for i in range(1000)]

        async def call_tool(tool_name, args):
            if tool_name == "validate_sql":
                return json.dumps({"valid": True})
            if tool_name == "execute_query":
                return json.dumps(rows)
            return None

        service = FakeAIService(call_tool)
        result = _run(service)
        assert result.error is None
        assert str(result.explanation).endswith(LIMIT_WARNING_MESSAGE)
