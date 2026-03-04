"""
NT AI Assistant - Provider Package
===================================
Auto-discoverable AI provider implementations.

Usage:
    from app.providers.registry import provider_registry
    provider = provider_registry.get("claude")

    # Or with fallback
    provider = provider_registry.get_fallback("claude")
"""

from app.providers.base import AIProvider, ConfidenceResult, QueryResult, RetryStatus
from app.providers.registry import provider_registry

__all__ = [
    "AIProvider",
    "ConfidenceResult",
    "QueryResult",
    "RetryStatus",
    "provider_registry",
]
