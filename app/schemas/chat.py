from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict




class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    provider: Optional[str] = "gemini"  # 'claude', 'gemini', or 'matcha'
    context: Optional[str] = None        # None = Auto-detect, or 'revenue', 'expense'
    max_retries: int = Field(default=3, ge=0, le=5, description="Max retry attempts when SQL fails (0-5)")
    mode: Optional[str] = Field(default="hybrid", description="Query mode: 'hybrid' (recommended, cost-effective) or 'mcp' (full tool access)")



class RetryAttempt(BaseModel):
    """Single retry attempt info"""
    attempt: int
    error_type: str
    error: str
    sql: Optional[str] = None


class DataWarning(BaseModel):
    """Warning message about data interpretation"""
    code: str
    message: str
    severity: str = "info"  # info, warning, important


class ConfidenceFactor(BaseModel):
    """Factor used in confidence calculation"""
    name: str
    score: int
    max: int
    detail: str


class Confidence(BaseModel):
    """Confidence score for query result"""
    score: int = Field(description="Confidence score 0-100")
    level: str = Field(description="Level: high, medium, low, very_low")
    level_th: str = Field(description="Level in Thai")
    color: str = Field(description="Color indicator: green, yellow, orange, red")
    factors: List[ConfidenceFactor] = Field(default=[], description="Factors used in calculation")
    recommendation: str = Field(description="Recommendation message in Thai")


class ChartConfig(BaseModel):
    """AI-recommended chart configuration"""
    category_column: Optional[str] = Field(default=None, description="Column for X-axis labels")
    measure_column: Optional[str] = Field(default=None, description="Column for Y-axis values")
    series_column: Optional[str] = Field(default=None, description="Column for grouping/series (for grouped charts)")


class ChatResponse(BaseModel):
    id: int
    conversation_id: Optional[str] = None
    question: str
    answer: str
    sql_query: Optional[str]
    data: Optional[List[Dict[str, Any]]] = None
    execution_time_ms: float
    retry_count: int = Field(default=0, description="Number of retries performed")
    retry_history: Optional[List[RetryAttempt]] = Field(default=None, description="Retry attempt details")
    warnings: Optional[List[DataWarning]] = Field(default=None, description="Data interpretation warnings")
    confidence: Optional[Confidence] = Field(default=None, description="Confidence score for this response")
    visualization: Optional[str] = Field(default=None, description="Recommended visualization type: bar_chart, line_chart, etc.")
    chart_config: Optional[ChartConfig] = Field(default=None, description="AI-recommended chart column configuration")
