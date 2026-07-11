"""
NT AI Assistant - Provider Base Classes
========================================
Abstract base class and shared dataclasses for AI providers.
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)

# In-memory cache for model tier lookup
_model_tier_cache: Optional[Dict] = None  # {(provider_id, tier): model_id}
_model_tier_cache_ts: float = 0.0
_MODEL_TIER_CACHE_TTL = 3600  # 1 hour


def _load_model_tiers_from_db() -> Optional[Dict]:
    """Load model tier mappings from ai_models table."""
    try:
        from app.db.session import ConfigSessionLocal
        db = ConfigSessionLocal()
        try:
            from sqlalchemy import text
            rows = db.execute(text(
                "SELECT provider_id, model_id, tier FROM ai_models "
                "WHERE is_active = 1 ORDER BY is_default DESC, priority DESC"
            )).fetchall()
            mapping = {}
            for row in rows:
                key = (row[0], row[2] or "default")
                if key not in mapping:  # First match wins (highest priority/default)
                    mapping[key] = row[1]
            return mapping
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"Could not load model tiers from DB: {e}")
        return None


def lookup_model_by_tier(provider_name: str, tier: str) -> Optional[str]:
    """Look up model_id from DB by provider and tier. Returns None if not found."""
    global _model_tier_cache, _model_tier_cache_ts

    now = time.time()
    if _model_tier_cache is not None and (now - _model_tier_cache_ts) < _MODEL_TIER_CACHE_TTL:
        return _model_tier_cache.get((provider_name, tier))

    db_data = _load_model_tiers_from_db()
    if db_data is not None:
        _model_tier_cache = db_data
        _model_tier_cache_ts = now
        return db_data.get((provider_name, tier))

    return None


def clear_model_tier_cache():
    """Clear model tier cache. Called by admin API after mutations."""
    global _model_tier_cache, _model_tier_cache_ts
    _model_tier_cache = None
    _model_tier_cache_ts = 0.0


@dataclass
class ConfidenceResult:
    """Confidence score for query result"""
    score: int
    level: str  # high, medium, low, very_low
    level_th: str
    color: str  # green, yellow, orange, red
    factors: List[Dict]
    recommendation: str


@dataclass
class TokenUsage:
    """Real token usage from one provider API call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    model: str = ""

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class QueryResult:
    """Result from AI query"""
    question: str
    sql_query: str
    data: List[Dict]
    explanation: Union[str, Dict]  # Can be str or dict with visualization/chart_config
    tokens_used: int
    provider: str
    raw_response: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    retry_history: Optional[List[Dict]] = None
    confidence: Optional[ConfidenceResult] = None
    usage_breakdown: Optional[List[Dict]] = None  # per-stage TokenUsage dicts (F7.2)


@dataclass
class RetryStatus:
    """Status update during retry process"""
    attempt: int
    max_attempts: int
    status: str
    message: str
    sql_query: Optional[str] = None
    error: Optional[str] = None


class AIProvider(ABC):
    """Abstract base class for AI providers.

    ``last_usage`` holds the TokenUsage of the most recent API call. Callers
    read it immediately after the call. This is safe ONLY because provider
    instances are created fresh per request (see registry.create_provider)
    and calls within a request are sequential — do NOT share a provider
    instance across concurrent requests.
    """

    name: str = ""
    last_usage: Optional[TokenUsage] = None

    def is_configured(self) -> bool:
        """Check if provider has required credentials. Override in subclass."""
        return True

    def get_model(self, tier: str = "default") -> str:
        """Return model name for given tier.

        Lookup order:
        1. DB (ai_models table with matching provider + tier) — admin-configurable
        2. Fallback to self.model (current default model for this provider)

        This ensures cheap model always stays within the same provider family.
        If admin hasn't configured a cheap model in DB, the default model is used
        for all tiers — no cross-provider model fallback.
        """
        # provider_name comes from each subclass (e.g. "matcha", "claude", "gemini")
        provider_name = getattr(self, '_provider_name', self.__class__.__name__.lower().replace('provider', ''))
        db_model = lookup_model_by_tier(provider_name, tier)
        if db_model:
            return db_model
        # No tier-specific model in DB → use the default model
        return self.model

    @abstractmethod
    async def generate_sql(
        self,
        question: str,
        system_prompt: str,
        tools: List[Dict],
        history: List[Dict] = [],
    ) -> Dict[str, Any]:
        """Generate SQL from question using Tools"""
        pass

    @abstractmethod
    async def explain_result(
        self,
        question: str,
        sql: str,
        data: List[Dict],
        system_prompt: str,
        dimension_families: Optional[Dict[str, List[str]]] = None,
        hierarchy_info: Optional[list] = None,
        schema_metadata: Optional[list] = None,
    ) -> Union[str, Dict]:
        """Explain query result"""
        pass

    @abstractmethod
    async def generate_content(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> str:
        """Generate content with optional native multi-turn history."""
        pass

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],  # JSON Schema (type/properties/required/enum subset)
        system_prompt: Optional[str] = None,
        schema_name: str = "result",
    ) -> Optional[Dict]:
        """Return a dict conforming to schema, or None if unsupported/invalid.

        Callers MUST have a text-parse fallback — None is a normal outcome.
        """
        return None

    @staticmethod
    def _validate_required(data: Any, schema: Dict[str, Any]) -> Optional[Dict]:
        """Shallow check that required keys exist. Returns data or None."""
        if not isinstance(data, dict):
            return None
        for key in schema.get("required", []):
            if key not in data:
                return None
        return data
