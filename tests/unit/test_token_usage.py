"""
F7.1: providers populate last_usage from real SDK responses.
F7.2: hybrid flow reports real token totals (not the hardcoded 500).
F7.3: query trace emitted as one parseable JSON line.
"""

import asyncio
import json
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.base import TokenUsage
from app.services.ai import trace as trace_module
from app.services.ai.trace import QueryTrace, emit, new_trace, record_usage


class TestMatchaUsage:
    def _provider(self):
        from app.providers.matcha_provider import MatchaProvider
        return MatchaProvider(api_key="k", api_url="https://x/v1/chat", model="gpt-4.1")

    def test_record_usage_from_response(self):
        p = self._provider()
        p._record_usage({"usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}})
        assert p.last_usage.input_tokens == 120
        assert p.last_usage.output_tokens == 30
        assert p.last_usage.total == 150
        assert p.last_usage.model == "gpt-4.1"

    def test_missing_usage_defaults_zero(self):
        p = self._provider()
        p._record_usage({})
        assert p.last_usage.total == 0


class TestClaudeUsage:
    def test_record_usage_with_cache_fields(self):
        from app.providers.claude_provider import ClaudeProvider
        p = ClaudeProvider(api_key="k", model="claude-sonnet-4-6")
        response = MagicMock()
        response.usage.input_tokens = 1000
        response.usage.output_tokens = 200
        response.usage.cache_read_input_tokens = 800
        response.usage.cache_creation_input_tokens = 0
        p._record_usage(response)
        assert p.last_usage.input_tokens == 1000
        assert p.last_usage.cache_read_input_tokens == 800
        assert p.last_usage.total == 1200

    def test_missing_usage_object(self):
        from app.providers.claude_provider import ClaudeProvider
        p = ClaudeProvider(api_key="k")
        response = MagicMock(spec=[])  # no usage attribute
        p._record_usage(response)
        assert p.last_usage.total == 0


class TestGeminiUsage:
    def test_record_usage_from_usage_metadata(self):
        from app.providers.gemini_provider import GeminiProvider
        p = GeminiProvider(api_key="k", model="gemini-3-flash")
        response = MagicMock()
        response.usage_metadata.prompt_token_count = 500
        response.usage_metadata.candidates_token_count = 100
        response.usage_metadata.cached_content_token_count = 50
        p._record_usage(response)
        assert p.last_usage.input_tokens == 500
        assert p.last_usage.output_tokens == 100
        assert p.last_usage.cache_read_input_tokens == 50

    def test_none_metadata(self):
        from app.providers.gemini_provider import GeminiProvider
        p = GeminiProvider(api_key="k")
        response = MagicMock()
        response.usage_metadata = None
        p._record_usage(response)
        assert p.last_usage.total == 0


class TestHybridRealTokens:
    def test_generate_sql_attempt_uses_real_usage(self):
        from app.services.ai.hybrid_flow import generate_sql_attempt

        service = MagicMock()
        service.provider.generate_content = AsyncMock(return_value="```sql\nSELECT 1\n```")
        service.provider.last_usage = TokenUsage(input_tokens=700, output_tokens=42, model="m")

        trace = new_trace("q")
        text, tokens, err = asyncio.run(
            generate_sql_attempt(service, "prompt", "sys", None, 0, trace=trace)
        )
        assert err is None
        assert tokens == 742  # real usage, not 500
        assert trace.usage[0]["stage"] == "sql_gen"
        assert "sql_gen_a0" in trace.stages

    def test_no_usage_reports_zero(self):
        from app.services.ai.hybrid_flow import generate_sql_attempt

        service = MagicMock()
        service.provider.generate_content = AsyncMock(return_value="text")
        service.provider.last_usage = None
        _, tokens, err = asyncio.run(generate_sql_attempt(service, "p", "s", None, 0))
        assert err is None
        assert tokens == 0


class TestQueryTrace:
    def test_emit_single_parseable_json_line(self, caplog):
        trace = QueryTrace(request_id="req-1", question_preview="รายได้รวม")
        trace.stages = {"rag": 0.1, "sql_gen_a0": 2.0}
        trace.usage = [{"stage": "sql_gen", "attempt": 0, "model": "m",
                        "input_tokens": 10, "output_tokens": 5, "cache_read": 0, "cache_creation": 0}]
        trace.total_s = 2.5
        with caplog.at_level(logging.INFO, logger="app.services.ai.trace"):
            emit(trace)
        lines = [r.message for r in caplog.records if r.message.startswith("query_trace ")]
        assert len(lines) == 1
        payload = json.loads(lines[0][len("query_trace "):])
        assert payload["request_id"] == "req-1"
        assert payload["stages"]["sql_gen_a0"] == 2.0
        assert payload["usage"][0]["input_tokens"] == 10
        assert payload["cache_hit"] is False

    def test_question_preview_truncated(self):
        trace = new_trace("x" * 500)
        assert len(trace.question_preview) == 80

    def test_record_usage_none_is_noop(self):
        trace = new_trace("q")
        provider = MagicMock()
        provider.last_usage = None
        record_usage(trace, "explain", provider)
        assert trace.usage == []
