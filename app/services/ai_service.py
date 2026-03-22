"""Backward-compatible AI service surface.

This module remains the legacy import path while the implementation lives in
the app.services.ai package.
"""

from app.providers.base import AIProvider, ConfidenceResult, QueryResult, RetryStatus  # noqa: F401
from app.providers.claude_provider import ClaudeProvider  # noqa: F401
from app.providers.gemini_provider import GeminiProvider  # noqa: F401
from app.providers.matcha_provider import MatchaProvider  # noqa: F401
from app.providers.retry_config import ai_retry, create_retry_decorator  # noqa: F401
from app.services.ai.factory import (  # noqa: F401
    create_claude_service,
    create_gemini_service,
    create_matcha_service,
)
from app.services.ai.hierarchy_context import (  # noqa: F401
    COLUMN_HIERARCHIES,
    _HIERARCHY_CACHE,
    get_column_hierarchies,
)
from app.services.ai.service import AIService  # noqa: F401

__all__ = [
    "AIProvider",
    "ConfidenceResult",
    "QueryResult",
    "RetryStatus",
    "ClaudeProvider",
    "GeminiProvider",
    "MatchaProvider",
    "ai_retry",
    "create_retry_decorator",
    "AIService",
    "create_claude_service",
    "create_gemini_service",
    "create_matcha_service",
    "COLUMN_HIERARCHIES",
    "_HIERARCHY_CACHE",
    "get_column_hierarchies",
]
