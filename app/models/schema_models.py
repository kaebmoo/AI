"""
NT AI Assistant - Schema Metadata Models
==============================================
SQLAlchemy models for schema metadata, semantic mappings, and business rules.
Used by Admin API and SchemaService for AI context management.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime
from app.db.base_class import ConfigBase


class SchemaMetadata(ConfigBase):
    """
    Stores column metadata for AI context.
    Contains information about each column in the revenue database.
    """
    __tablename__ = "schema_metadata"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(100), nullable=False, index=True)
    column_name = Column(String(100), nullable=False)
    display_name_th = Column(String(200), nullable=True)  # Thai display name
    display_name_en = Column(String(200), nullable=True)  # English display name
    description = Column(Text, nullable=True)
    data_type = Column(String(50), nullable=True)  # INTEGER, TEXT, REAL
    format_hint = Column(String(100), nullable=True)  # e.g., 'YYYY-MM-DD', 'Code'
    example_value = Column(String(500), nullable=True)
    is_summable = Column(Boolean, default=False)  # Can use SUM()
    is_groupable = Column(Boolean, default=True)  # Can use GROUP BY
    hierarchy_level = Column(Integer, nullable=True)  # Org hierarchy level
    sample_values = Column(JSON, nullable=True)  # JSON array of sample values
    special_notes = Column(Text, nullable=True)  # Special notes for AI
    conversion_sql = Column(Text, nullable=True)  # SQL for value conversion
    dimension_group = Column(String(100), nullable=True)  # Family group for related columns
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_schema_metadata_table_column', 'table_name', 'column_name', unique=True),
    )

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "display_name_th": self.display_name_th,
            "display_name_en": self.display_name_en,
            "description": self.description,
            "data_type": self.data_type,
            "format_hint": self.format_hint,
            "example_value": self.example_value,
            "is_summable": self.is_summable,
            "is_groupable": self.is_groupable,
            "hierarchy_level": self.hierarchy_level,
            "sample_values": self.sample_values,
            "special_notes": self.special_notes,
            "conversion_sql": self.conversion_sql,
            "dimension_group": self.dimension_group,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SchemaSemanticMapping(ConfigBase):
    """
    Maps keywords (abbreviations, business terms) to SQL conditions.
    Enables AI to understand abbreviations like 'นป.' or terms like 'อสังหาริมทรัพย์'.
    """
    __tablename__ = "schema_semantic_mapping"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(200), nullable=False, unique=True, index=True)  # Search keyword
    keyword_type = Column(String(50), default='term')  # 'abbreviation', 'term', 'synonym'
    target_column = Column(String(100), nullable=False)  # Column to use
    target_condition = Column(String(500), nullable=False)  # SQL condition (e.g., "= 'value'")
    full_condition = Column(Text, nullable=True)  # Full SQL condition for complex cases
    description = Column(Text, nullable=True)  # Description for reference
    priority = Column(Integer, default=0)  # Higher = more priority
    is_active = Column(Boolean, default=True)
    # NULL = global (all contexts), value = scoped to specific context e.g. 'transfer price'
    context_name = Column(String(100), nullable=True, default=None)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_semantic_mapping_type', 'keyword_type'),
        Index('ix_semantic_mapping_active', 'is_active'),
        Index('ix_semantic_mapping_context', 'context_name'),
    )

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "keyword": self.keyword,
            "keyword_type": self.keyword_type,
            "target_column": self.target_column,
            "target_condition": self.target_condition,
            "full_condition": self.full_condition,
            "description": self.description,
            "priority": self.priority,
            "is_active": self.is_active,
            "context_name": self.context_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_sql_condition(self) -> str:
        """Get the full SQL condition string"""
        if self.full_condition:
            return self.full_condition
        return f"{self.target_column} {self.target_condition}"


class ViewColumnMapping(ConfigBase):
    """
    Maps view columns back to source table columns.
    Enables metadata propagation from raw tables to views.
    """
    __tablename__ = "view_column_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    view_name = Column(String(100), nullable=False, index=True)
    view_column = Column(String(100), nullable=False)
    source_table = Column(String(100), nullable=False)
    source_column = Column(String(100), nullable=False)
    mapping_type = Column(String(20), default='alias')  # alias | expression | passthrough
    expression_sql = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('view_name', 'view_column', name='uq_view_column_mapping'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "view_name": self.view_name,
            "view_column": self.view_column,
            "source_table": self.source_table,
            "source_column": self.source_column,
            "mapping_type": self.mapping_type,
            "expression_sql": self.expression_sql,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SchemaBusinessRule(ConfigBase):
    """
    SQL generation rules for AI.
    Contains rules like 'use || instead of CONCAT in SQLite'.
    """
    __tablename__ = "schema_business_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_code = Column(String(50), nullable=False, unique=True)
    rule_name = Column(String(200), nullable=False)
    rule_description = Column(Text, nullable=False)
    table_name = Column(String(100), nullable=True)  # Applies to specific table, NULL = ALL
    applies_to = Column(String(500), nullable=True)  # Comma-separated column names
    example_correct = Column(Text, nullable=True)
    example_wrong = Column(Text, nullable=True)
    severity = Column(String(20), default='warning')  # 'error', 'warning', 'info'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_business_rules_active', 'is_active'),
    )

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "rule_description": self.rule_description,
            "table_name": self.table_name,
            "applies_to": self.applies_to,
            "example_correct": self.example_correct,
            "example_wrong": self.example_wrong,
            "severity": self.severity,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DataWarningModel(ConfigBase):
    """
    Data warning definitions for data quality alerts.
    Replaces hardcoded DATA_WARNINGS list in warning_detector.py.
    """
    __tablename__ = "data_warnings"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, unique=True)
    keywords = Column(Text, nullable=False)             # JSON array
    exclude_keywords = Column(Text, nullable=True)       # JSON array
    columns_to_check = Column(Text, nullable=False)      # JSON array
    message = Column(Text, nullable=False)
    severity = Column(String(20), default='warning')
    context_name = Column(String(100), nullable=True)    # NULL = all contexts
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_data_warnings_active', 'is_active'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "keywords": self.keywords,
            "exclude_keywords": self.exclude_keywords,
            "columns_to_check": self.columns_to_check,
            "message": self.message,
            "severity": self.severity,
            "context_name": self.context_name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class QueryComplexityPattern(ConfigBase):
    """
    Query complexity patterns for tier-based cost control.
    Replaces hardcoded COMPLEX_PATTERNS/SIMPLE_PATTERNS in query_classifier.py.
    """
    __tablename__ = "query_complexity_patterns"

    id = Column(Integer, primary_key=True, index=True)
    tier = Column(String(20), nullable=False)      # 'simple' or 'complex'
    pattern = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tier', 'pattern', name='uq_tier_pattern'),
    )


class VannaDocumentation(ConfigBase):
    """
    Manually authored knowledge documents for Vanna RAG.
    Replaces static file dependency on docs/DATABASE_TABLES_GUIDE.md.
    Auto-generated context summaries are NOT stored here — they are
    generated on-the-fly by _sync_context_summaries() during brain sync.
    """
    __tablename__ = "vanna_documentation"

    id = Column(Integer, primary_key=True, index=True)
    doc_key = Column(String(100), nullable=False, unique=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), default='guide')
    context_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_vanna_doc_active', 'is_active'),
        Index('ix_vanna_doc_category', 'category'),
    )
