"""
NT AI Assistant - Admin API Schemas
=========================================
Pydantic schemas for Admin API endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# ============================================================
# Schema Metadata Schemas
# ============================================================

class SchemaMetadataBase(BaseModel):
    """Base schema for schema metadata"""
    table_name: str = Field(..., description="Table/view name")
    column_name: str = Field(..., description="Column name")
    display_name_th: Optional[str] = Field(None, description="Thai display name")
    display_name_en: Optional[str] = Field(None, description="English display name")
    description: Optional[str] = Field(None, description="Column description")
    data_type: Optional[str] = Field(None, description="Data type (INTEGER, TEXT, REAL)")
    format_hint: Optional[str] = Field(None, description="Format hint")
    example_value: Optional[str] = Field(None, description="Example value")
    is_summable: bool = Field(False, description="Can use SUM()")
    is_groupable: bool = Field(True, description="Can use GROUP BY")
    hierarchy_level: Optional[int] = Field(None, description="Organization hierarchy level")
    sample_values: Optional[List[str]] = Field(None, description="Sample values")
    special_notes: Optional[str] = Field(None, description="Special notes for AI")
    conversion_sql: Optional[str] = Field(None, description="SQL for conversion")
    dimension_group: Optional[str] = Field(None, description="Dimension family group name")


class SchemaMetadataCreate(SchemaMetadataBase):
    """Schema for creating schema metadata"""
    pass


class SchemaMetadataUpdate(BaseModel):
    """Schema for updating schema metadata"""
    display_name_th: Optional[str] = None
    display_name_en: Optional[str] = None
    description: Optional[str] = None
    data_type: Optional[str] = None
    format_hint: Optional[str] = None
    example_value: Optional[str] = None
    is_summable: Optional[bool] = None
    is_groupable: Optional[bool] = None
    hierarchy_level: Optional[int] = None
    sample_values: Optional[List[str]] = None
    special_notes: Optional[str] = None
    conversion_sql: Optional[str] = None
    dimension_group: Optional[str] = None


class SchemaMetadataResponse(SchemaMetadataBase):
    """Schema for schema metadata response"""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================
# Semantic Mapping Schemas
# ============================================================

class SemanticMappingBase(BaseModel):
    """Base schema for semantic mapping"""
    keyword: str = Field(..., description="Search keyword (e.g., 'นป.', 'อสังหาริมทรัพย์')")
    keyword_type: str = Field('term', description="Type: 'abbreviation', 'term', 'synonym'")
    target_column: str = Field(..., description="Target column name")
    target_condition: str = Field(..., description="SQL condition (e.g., \"= 'value'\")")
    full_condition: Optional[str] = Field(None, description="Full SQL condition for complex cases")
    description: Optional[str] = Field(None, description="Description")
    priority: int = Field(0, description="Priority (higher = more priority)")
    is_active: bool = Field(True, description="Is active")
    context_name: Optional[str] = Field(
        None,
        description="Scope to a specific context (e.g. 'transfer price'). NULL = global (all contexts)."
    )


class SemanticMappingCreate(SemanticMappingBase):
    """Schema for creating semantic mapping"""
    pass


class SemanticMappingUpdate(BaseModel):
    """Schema for updating semantic mapping"""
    keyword: Optional[str] = None
    keyword_type: Optional[str] = None
    target_column: Optional[str] = None
    target_condition: Optional[str] = None
    full_condition: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    context_name: Optional[str] = None


class SemanticMappingResponse(SemanticMappingBase):
    """Schema for semantic mapping response"""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================
# Business Rule Schemas
# ============================================================

class BusinessRuleBase(BaseModel):
    """Base schema for business rule"""
    rule_code: str = Field(..., description="Unique rule code")
    rule_name: str = Field(..., description="Rule name")
    rule_description: Optional[str] = Field("", description="Rule description")
    table_name: Optional[str] = Field(None, description="Applies to specific table (NULL = ALL)")
    applies_to: Optional[str] = Field(None, description="Comma-separated column names")
    example_correct: Optional[str] = Field(None, description="Correct SQL example")
    example_wrong: Optional[str] = Field(None, description="Wrong SQL example")
    severity: str = Field('warning', description="Severity: 'error', 'warning', 'info'")
    is_active: bool = Field(True, description="Is active")

    @field_validator('rule_description', mode='before')
    @classmethod
    def set_description_default(cls, v):
        return v or ""


class BusinessRuleCreate(BusinessRuleBase):
    """Schema for creating business rule"""
    pass


class BusinessRuleUpdate(BaseModel):
    """Schema for updating business rule"""
    rule_name: Optional[str] = None
    rule_description: Optional[str] = None
    table_name: Optional[str] = None
    applies_to: Optional[str] = None
    example_correct: Optional[str] = None
    example_wrong: Optional[str] = None
    severity: Optional[str] = None
    is_active: Optional[bool] = None


class BusinessRuleResponse(BusinessRuleBase):
    """Schema for business rule response"""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================
# Golden Example Schemas
# ============================================================

class GoldenExampleBase(BaseModel):
    """Base schema for golden example"""
    question_pattern: str = Field(..., description="Question pattern")
    expected_sql: str = Field(..., description="Expected SQL query")
    category: Optional[str] = Field(None, description="Category")
    is_active: bool = Field(True, description="Is active")


class GoldenExampleCreate(GoldenExampleBase):
    """Schema for creating golden example"""
    chat_id: Optional[int] = Field(None, description="Source chat ID")


class GoldenExampleUpdate(BaseModel):
    """Schema for updating golden example"""
    question_pattern: Optional[str] = None
    expected_sql: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class GoldenExampleResponse(GoldenExampleBase):
    """Schema for golden example response"""
    id: int
    chat_id: Optional[int] = None
    added_by: Optional[int] = None
    usage_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_validator('usage_count', mode='before')
    def set_usage_count(cls, v):
        return v or 0


# ============================================================
# List Response Schemas
# ============================================================

class SchemaMetadataListResponse(BaseModel):
    """Response for list of schema metadata"""
    columns: List[SchemaMetadataResponse]
    total: int


class SemanticMappingListResponse(BaseModel):
    """Response for list of semantic mappings"""
    mappings: List[SemanticMappingResponse]
    total: int


class BusinessRuleListResponse(BaseModel):
    """Response for list of business rules"""
    rules: List[BusinessRuleResponse]
    total: int


class GoldenExampleListResponse(BaseModel):
    """Response for list of golden examples"""
    examples: List[GoldenExampleResponse]
    total: int
    categories: List[str]


class DashboardStatsResponse(BaseModel):
    """Response for dashboard statistics"""
    total_users: int
    total_mappings: int
    total_rules: int
    total_columns: int


# ==========================
# Data Warnings
# ==========================

class DataWarningBase(BaseModel):
    """Base schema for data warning"""
    code: str
    keywords: str           # JSON array string
    exclude_keywords: Optional[str] = None
    columns_to_check: str   # JSON array string
    message: str
    severity: str = "warning"
    context_name: Optional[str] = None
    is_active: bool = True


class DataWarningCreate(DataWarningBase):
    """Schema for creating data warning"""
    pass


class DataWarningUpdate(BaseModel):
    """Schema for updating data warning"""
    keywords: Optional[str] = None
    exclude_keywords: Optional[str] = None
    columns_to_check: Optional[str] = None
    message: Optional[str] = None
    severity: Optional[str] = None
    context_name: Optional[str] = None
    is_active: Optional[bool] = None


class DataWarningResponse(DataWarningBase):
    """Schema for data warning response"""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DataWarningListResponse(BaseModel):
    """Response for list of data warnings"""
    warnings: List[DataWarningResponse]
    total: int


# ==========================
# Query Complexity Patterns
# ==========================

class QueryPatternBase(BaseModel):
    """Base schema for query complexity pattern"""
    tier: str           # 'simple' or 'complex'
    pattern: str
    description: Optional[str] = None
    is_active: bool = True


class QueryPatternCreate(QueryPatternBase):
    """Schema for creating query pattern"""
    pass


class QueryPatternUpdate(BaseModel):
    """Schema for updating query pattern"""
    tier: Optional[str] = None
    pattern: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class QueryPatternResponse(QueryPatternBase):
    """Schema for query pattern response"""
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QueryPatternListResponse(BaseModel):
    """Response for list of query patterns"""
    patterns: List[QueryPatternResponse]
    total: int


# ==========================
# Schema Contexts
# ==========================

class SchemaContextBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    main_view: Optional[str] = None
    is_active: bool = True
    priority: int = 0
    keywords: Optional[List[str]] = None
    instruction_th: Optional[str] = None
    instruction_en: Optional[str] = None

class SchemaContextCreate(SchemaContextBase):
    pass

class SchemaContextUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    main_view: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    keywords: Optional[List[str]] = None
    instruction_th: Optional[str] = None
    instruction_en: Optional[str] = None

class SchemaContextResponse(SchemaContextBase):
    id: int
    created_at: datetime
    # Assuming standard fields are present in the response
    # name: str
    # display_name: Optional[str]
    # description: Optional[str]
    # main_view: Optional[str]
    # is_active: bool
    # priority: int

    class Config:
        from_attributes = True

class SchemaContextListResponse(BaseModel):
    contexts: List[SchemaContextResponse]
    total: int


# ============================================================
# View Builder Schemas
# ============================================================

class ViewColumnMapping(BaseModel):
    col: str = Field(..., description="Original column name")
    alias: Optional[str] = Field(None, description="New alias for the column")

class ViewCreateRequest(BaseModel):
    view_name: str = Field(..., description="Name of the view to create")
    source_table: str = Field(..., description="Source raw table name")
    mapping: List[ViewColumnMapping] = Field(..., description="List of column mappings")

class ViewMappingSuggestion(BaseModel):
    col: str
    suggested_alias: str
    reason: Optional[str] = None


# ============================================================
# View Column Mapping Response Schemas
# ============================================================

class ViewColumnMappingResponse(BaseModel):
    """Response for a single view-to-source column mapping"""
    id: int
    view_name: str
    view_column: str
    source_table: str
    source_column: str
    mapping_type: str = "alias"
    expression_sql: Optional[str] = None

    class Config:
        from_attributes = True

class ViewMappingsListResponse(BaseModel):
    """Response for listing all mappings of a view"""
    view_name: str
    mappings: List[ViewColumnMappingResponse]
    total: int

class MissingColumnInfo(BaseModel):
    """Info about a column with no source metadata"""
    view_column: str
    source_table: str
    source_column: str

class PropagateMetadataResponse(BaseModel):
    """Response for metadata propagation"""
    view_name: str
    created: int
    updated: int
    skipped: int = 0
    missing_columns: List[MissingColumnInfo] = []
    message: str

class ViewSummaryItem(BaseModel):
    """Summary of a single view's mapping status"""
    view_name: str
    source_table: str
    mapping_count: int
    metadata_with_thai_count: int

class ViewSummaryListResponse(BaseModel):
    """Response for listing all views with mapping summary"""
    views: List[ViewSummaryItem]
    total: int


# ============================================================
# Dimension Family Schemas
# ============================================================

class DimensionFamilyColumn(BaseModel):
    column_name: str
    source: str = Field(..., description="Source: 'db', 'auto', or 'ai'")

class DimensionFamilyItem(BaseModel):
    family_name: str
    columns: List[DimensionFamilyColumn]
    source: str = Field(..., description="Overall source: 'db', 'auto', or 'mixed'")

class DimensionFamilyListResponse(BaseModel):
    table_name: str
    families: List[DimensionFamilyItem]
    total: int

class DimensionFamilyAnalyzeRequest(BaseModel):
    table_name: str = Field(..., description="Table to analyze")
    context_name: Optional[str] = Field(None, description="Optional context for analysis")

class DimensionFamilySuggestion(BaseModel):
    family_name: str
    columns: List[str]

class DimensionFamilyAnalyzeResponse(BaseModel):
    table_name: str
    suggested_families: List[DimensionFamilySuggestion]
    llm_reasoning: str = ""
    provider_used: str = ""

class DimensionFamilyAssignment(BaseModel):
    column_name: str
    dimension_group: Optional[str] = Field(None, description="Family name, or null to clear")

class DimensionFamilyBatchUpdate(BaseModel):
    table_name: str
    assignments: List[DimensionFamilyAssignment]

class DimensionFamilyBatchUpdateResponse(BaseModel):
    updated_count: int
    families: List[DimensionFamilyItem]


# ============================================================
# Context Onboarding Schemas
# ============================================================

class OnboardingRequest(BaseModel):
    """Request for context onboarding pipeline."""
    view_name: str = Field(..., description="View/table name to onboard")
    dry_run: bool = Field(True, description="Preview SQL without applying")
    provider: Optional[str] = Field(None, description="AI provider (claude, gemini, matcha)")
    model: Optional[str] = Field(None, description="Model override")
    api_url: Optional[str] = Field(None, description="Custom API URL")
    inspect_only: bool = Field(False, description="Only run inspection (no LLM)")

class InspectRequest(BaseModel):
    """Request for inspect-only endpoint."""
    view_name: str = Field(..., description="View/table name to inspect")

class ValidateRequest(BaseModel):
    """Request for validate endpoint."""
    view_name: str = Field(..., description="View/table name to validate")

class InspectionSummary(BaseModel):
    """Summary of inspection results."""
    row_count: int = 0
    columns: int = 0
    detected_structure: str = "unknown"
    quality_issues: int = 0

class AnalysisSummary(BaseModel):
    """Summary of LLM analysis results."""
    data_structure: dict = Field(default_factory=dict)
    context: dict = Field(default_factory=dict)
    rules_count: int = 0
    examples_count: int = 0
    mappings_count: int = 0

class ConfigSummary(BaseModel):
    """Summary of generated config."""
    summary: str = ""
    sql_count: int = 0
    sql_statements: Optional[List[str]] = None

class ValidationSummary(BaseModel):
    """Summary of validation results."""
    passed: bool = False
    results: List[dict] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)

class OnboardingResponse(BaseModel):
    """Response from onboarding pipeline."""
    status: str = Field(..., description="inspect_only, preview, or applied")
    inspection: InspectionSummary
    analysis: Optional[AnalysisSummary] = None
    config: Optional[ConfigSummary] = None
    apply: Optional[dict] = None
    validation: Optional[ValidationSummary] = None

class AvailableView(BaseModel):
    """A view/table available for onboarding."""
    name: str
    type: str = "view"
    has_config: bool = False
    row_count: Optional[int] = None

class AvailableViewsResponse(BaseModel):
    """Response listing available views for onboarding."""
    unconfigured: List[AvailableView] = Field(default_factory=list)
    configured: List[AvailableView] = Field(default_factory=list)

class ApplySqlRequest(BaseModel):
    """Request to apply pre-generated SQL statements directly."""
    view_name: str = Field(..., description="View name for validation after apply")
    sql_statements: List[str] = Field(..., description="SQL statements from dry-run preview")
