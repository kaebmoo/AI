"""F8: generate_structured per provider + extract_intent structured-first."""

import asyncio
import json

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

SCHEMA = {
    "type": "object",
    "properties": {"intent_type": {"type": "string"}, "metrics": {"type": "array"}},
    "required": ["intent_type", "metrics"],
}


class TestClaudeStructured:
    def _provider(self, response):
        from app.providers.claude_provider import ClaudeProvider
        p = ClaudeProvider(api_key="k")
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=response)
        p._client = client
        return p

    def test_forced_tool_call_returns_input(self):
        block = MagicMock()
        block.type = "tool_use"
        block.input = {"intent_type": "aggregation", "metrics": ["REVENUE_VALUE"]}
        response = MagicMock()
        response.content = [block]
        response.usage.input_tokens = 10
        response.usage.output_tokens = 5
        p = self._provider(response)
        result = asyncio.run(p.generate_structured("q", SCHEMA))
        assert result == {"intent_type": "aggregation", "metrics": ["REVENUE_VALUE"]}
        assert p.last_usage.total == 15

    def test_no_tool_use_block_returns_none(self):
        block = MagicMock()
        block.type = "text"
        response = MagicMock()
        response.content = [block]
        p = self._provider(response)
        assert asyncio.run(p.generate_structured("q", SCHEMA)) is None

    def test_missing_required_key_returns_none(self):
        block = MagicMock()
        block.type = "tool_use"
        block.input = {"intent_type": "aggregation"}  # metrics missing
        response = MagicMock()
        response.content = [block]
        p = self._provider(response)
        assert asyncio.run(p.generate_structured("q", SCHEMA)) is None


class TestMatchaStructured:
    def _mock_response(self, status=200, content=None):
        request = httpx.Request("POST", "https://x")
        payload = {
            "choices": [{"message": {"content": content or json.dumps(
                {"intent_type": "aggregation", "metrics": []})}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
        return httpx.Response(status, json=payload, request=request)

    def test_json_schema_happy_path(self):
        from app.providers.matcha_provider import MatchaProvider
        p = MatchaProvider(api_key="k", api_url="https://x/v1/chat")
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=self._mock_response())):
            result = asyncio.run(p.generate_structured("q", SCHEMA))
        assert result["intent_type"] == "aggregation"
        assert p._supports_json_schema is True
        assert p.last_usage.total == 10

    def test_gateway_rejects_json_schema_falls_back_to_json_object(self):
        from app.providers.matcha_provider import MatchaProvider
        p = MatchaProvider(api_key="k", api_url="https://x/v1/chat")
        request = httpx.Request("POST", "https://x")
        bad = httpx.Response(400, json={"error": "unknown parameter response_format"}, request=request)
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=[bad, self._mock_response()])):
            result = asyncio.run(p.generate_structured("q", SCHEMA))
        assert result["intent_type"] == "aggregation"
        assert p._supports_json_schema is False

    def test_capability_remembered(self):
        from app.providers.matcha_provider import MatchaProvider
        p = MatchaProvider(api_key="k", api_url="https://x/v1/chat")
        p._supports_json_schema = False
        post = AsyncMock(return_value=self._mock_response())
        with patch("httpx.AsyncClient.post", new=post):
            asyncio.run(p.generate_structured("q", SCHEMA))
        assert post.call_count == 1  # went straight to json_object — no probing
        body = post.call_args[1]["json"]
        assert body["response_format"] == {"type": "json_object"}


class TestGeminiStructured:
    def test_json_string_parsed(self):
        from app.providers.gemini_provider import GeminiProvider
        p = GeminiProvider(api_key="k")
        response = MagicMock()
        response.text = json.dumps({"intent_type": "ranking", "metrics": ["x"]})
        response.usage_metadata.prompt_token_count = 5
        response.usage_metadata.candidates_token_count = 2
        response.usage_metadata.cached_content_token_count = 0
        with patch.object(GeminiProvider, "_run_async", new=AsyncMock(return_value=response)):
            result = asyncio.run(p.generate_structured("q", SCHEMA))
        assert result["intent_type"] == "ranking"

    def test_invalid_json_returns_none(self):
        from app.providers.gemini_provider import GeminiProvider
        p = GeminiProvider(api_key="k")
        response = MagicMock()
        response.text = "not json"
        with patch.object(GeminiProvider, "_run_async", new=AsyncMock(return_value=response)):
            assert asyncio.run(p.generate_structured("q", SCHEMA)) is None


class TestExtractIntentStructuredFirst:
    def _service(self, structured_result, text_result="{}"):
        service = MagicMock()
        service.provider.generate_structured = AsyncMock(return_value=structured_result)
        service.provider.generate_content = AsyncMock(return_value=text_result)
        service.provider.last_usage = None
        service.parse_intent_json = MagicMock(return_value=json.loads(text_result) if text_result else None)
        return service

    def _run(self, service):
        from app.services.ai.hybrid_flow import extract_intent
        return asyncio.run(extract_intent(
            service=service, question="q", system_prompt="sys",
            context_name="revenue", context_table="revenue", context_thai="รายได้",
            history_context="", rag_context="",
        ))

    def test_structured_success_skips_text_parse(self):
        intent = {"intent_type": "aggregation", "metrics": [], "filters": []}
        service = self._service(intent)
        result = self._run(service)
        assert result == intent
        service.provider.generate_content.assert_not_called()
        service.parse_intent_json.assert_not_called()

    def test_structured_none_falls_back_to_text(self):
        fallback = {"intent_type": "detail", "metrics": [], "filters": []}
        service = self._service(None, text_result=json.dumps(fallback))
        result = self._run(service)
        assert result == fallback
        service.provider.generate_content.assert_called_once()
