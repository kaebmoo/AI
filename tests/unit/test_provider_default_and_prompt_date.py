"""
F1.3: ChatRequest.provider must default to None (admin default wins).
F1.4: System prompt cache key must include the current date (daily rebuild).
"""

from datetime import datetime
from unittest.mock import patch

from app.schemas.chat import ChatRequest
from app.services.schema.prompt_builder import build_system_prompt


class TestProviderDefault:
    def test_chat_request_provider_defaults_to_none(self):
        req = ChatRequest(question="รายได้รวม")
        assert req.provider is None

    def test_explicit_provider_preserved(self):
        req = ChatRequest(question="รายได้รวม", provider="claude")
        assert req.provider == "claude"


class _KeyRecorder:
    """Stub SchemaService that records cache keys probed by build_system_prompt."""

    def __init__(self):
        self.probed_keys = []

    def get_cached_value(self, key):
        self.probed_keys.append(key)
        return None

    def set_cached_value(self, key, value):
        pass

    def get_context_info(self, context_name):
        return None  # short-circuits prompt building after the cache probe


class TestPromptCacheKeyDate:
    def test_cache_key_changes_across_days(self):
        service = _KeyRecorder()
        with patch("app.services.schema.prompt_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 10)
            build_system_prompt(service, context_name="revenue")
            mock_dt.now.return_value = datetime(2026, 7, 11)
            build_system_prompt(service, context_name="revenue")

        assert len(service.probed_keys) == 2
        assert service.probed_keys[0] != service.probed_keys[1]
        assert "2026-07-10" in service.probed_keys[0]
        assert "2026-07-11" in service.probed_keys[1]
