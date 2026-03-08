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
        from app.db.session import SessionLocal
        db = SessionLocal()
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
    """Abstract base class for AI providers"""

    name: str = ""

    def is_configured(self) -> bool:
        """Check if provider has required credentials. Override in subclass."""
        return True

    def get_model(self, tier: str = "default") -> str:
        """Return model name for given tier. Override in subclass for cost control."""
        return ""

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
