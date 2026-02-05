"""
NT AI Assistant - Admin API Schemas
=========================================
Pydantic schemas for Admin API endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
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
    rule_description: str = Field(..., description="Rule description")
    table_name: Optional[str] = Field(None, description="Applies to specific table (NULL = ALL)")
    applies_to: Optional[str] = Field(None, description="Comma-separated column names")
    example_correct: Optional[str] = Field(None, description="Correct SQL example")
    example_wrong: Optional[str] = Field(None, description="Wrong SQL example")
    severity: str = Field('warning', description="Severity: 'error', 'warning', 'info'")
    is_active: bool = Field(True, description="Is active")


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
# Prompt Version Schemas
# ============================================================

class PromptVersionBase(BaseModel):
    """Base schema for prompt version"""
    system_prompt: str = Field(..., description="System instruction prompt")
    notes: Optional[str] = Field(None, description="Release notes or description")

class PromptVersionCreate(PromptVersionBase):
    """Schema for creating prompt version"""
    pass

class PromptVersionResponse(PromptVersionBase):
    """Schema for prompt version response"""
    id: int
    version: int
    created_at: datetime
    created_by: Optional[int] = None
    is_active: bool = False
    
    class Config:
        from_attributes = True

class PromptVersionListResponse(BaseModel):
    """Response for list of prompt versions"""
    versions: List[PromptVersionResponse]
    total: int
