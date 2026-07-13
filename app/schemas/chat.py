from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from app.models.chart import ChartSpec




class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    provider: Optional[str] = None  # 'claude', 'gemini', 'matcha' — None = use admin default_ai_provider
    context: Optional[str] = None        # None = Auto-detect, or 'revenue', 'expense'
    max_retries: int = Field(default=3, ge=0, le=5, description="Max retry attempts when SQL fails (0-5)")
    mode: Optional[str] = Field(default="hybrid", description="Query mode: 'hybrid' (recommended, cost-effective) or 'mcp' (full tool access)")


class TrainingRequest(BaseModel):
    """Request to train RAG with corrected SQL"""
    question: str
    sql: str
    context: Optional[str] = "revenue"



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
    """AI-recommended chart configuration (extended)"""
    # Original fields
    category_column: Optional[str] = Field(default=None, description="Column for X-axis labels")
    measure_column: Optional[str] = Field(default=None, description="Column for Y-axis values")
    series_column: Optional[str] = Field(default=None, description="Column for grouping/series (for grouped charts)")
    # Extended fields (populated by enrich_chart_config)
    suggested_type: Optional[str] = Field(default=None, description="ECharts-ready chart type")
    available_types: Optional[List[str]] = Field(default=None, description="Chart types this data supports")
    column_roles: Optional[List[Dict[str, Any]]] = Field(default=None, description="Column role metadata")
    title: Optional[str] = Field(default=None, description="Chart title in Thai")
    sort_by: Optional[str] = Field(default=None, description="Sort hint: value_desc, value_asc, category_asc, original")
    show_data_labels: Optional[bool] = Field(default=None, description="Whether to show data labels on chart")
    warning: Optional[str] = Field(default=None, description="Chart compatibility warning")
    is_time_axis: Optional[bool] = Field(default=None, description="True when category_column is a time dimension")
    max_series: Optional[int] = Field(default=None, description="Max series/pie-slices shown before bucketing the rest into 'อื่นๆ' (Wave 4)")
    chart_spec: Optional[ChartSpec] = Field(default=None, description="Renderer-neutral declarative chart contract")


class ChatResponse(BaseModel):
    id: Optional[int] = None
    conversation_id: Optional[str] = None
    question: str
    answer: str
    sql_query: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    execution_time_ms: float = 0.0
    retry_count: int = Field(default=0, description="Number of retries performed")
    retry_history: Optional[List[RetryAttempt]] = Field(default=None, description="Retry attempt details")
    warnings: Optional[List[DataWarning]] = Field(default=None, description="Data interpretation warnings")
    confidence: Optional[Confidence] = Field(default=None, description="Confidence score for this response")
    visualization: Optional[str] = Field(default=None, description="Recommended visualization type: bar_chart, line_chart, etc.")
    chart_config: Optional[ChartConfig] = Field(default=None, description="AI-recommended chart column configuration")
    display_hint: Optional[str] = Field(default=None, description="Table display hint: flat, hierarchical, crosstab")
    hierarchy_columns: Optional[List[str]] = Field(default=None, description="Ordered column names for hierarchical display")
    is_chart_only: bool = Field(default=False, description="True when no SQL was re-executed (chart switch only)")
