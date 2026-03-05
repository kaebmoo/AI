"""
NT AI Assistant - Provider Base Classes
========================================
Abstract base class and shared dataclasses for AI providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union


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
    ) -> Union[str, Dict]:
        """Explain query result"""
        pass

    @abstractmethod
    async def generate_content(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate generic content"""
        pass
