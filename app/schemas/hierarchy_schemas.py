"""
NT AI Assistant - Hierarchy Schemas
====================================
Pydantic models for master hierarchy API.
"""

from pydantic import BaseModel
from typing import List, Optional


# --- Level schemas ---

class HierarchyLevelBase(BaseModel):
    level_label_th: str
    level_label_en: str
    level_columns: List[str]
    detection_keywords: List[str]


class HierarchyLevelCreate(HierarchyLevelBase):
    level: int


class HierarchyLevelUpdate(BaseModel):
    level_label_th: Optional[str] = None
    level_label_en: Optional[str] = None
    level_columns: Optional[List[str]] = None
    detection_keywords: Optional[List[str]] = None


class HierarchyLevelResponse(HierarchyLevelBase):
    context_name: str
    level: int
    source: str
    is_active: bool = True
    value_count: int = 0

    class Config:
        from_attributes = True


# --- Value schemas ---

class HierarchyValueCreate(BaseModel):
    level: int
    value: str
    parent_value: Optional[str] = None
    aliases: List[str] = []


class HierarchyValueUpdate(BaseModel):
    value: Optional[str] = None
    parent_value: Optional[str] = None
    aliases: Optional[List[str]] = None


class HierarchyValueResponse(BaseModel):
    id: int
    context_name: str
    level: int
    value: str
    parent_value: Optional[str] = None
    aliases: List[str] = []
    source: str
    is_active: bool = True
    children_count: int = 0

    class Config:
        from_attributes = True


# --- Search schemas ---

class HierarchySearchResult(BaseModel):
    value: str
    level: int
    level_label_th: str
    context_name: str
    parent_chain: List[str] = []
    matched_alias: str
    column_name: str


# --- Context summary ---

class HierarchyContextSummary(BaseModel):
    context_name: str
    level_count: int
    value_count: int
    manual_count: int
    auto_count: int


# --- Extract/sync ---

class HierarchyExtractResult(BaseModel):
    context_name: str
    new_values: int
    updated_values: int
    total_values: int


class HierarchyChangeItem(BaseModel):
    level: int
    value: str
    parent_value: Optional[str] = None
    change_type: str  # 'new', 'missing', 'unchanged'


class HierarchyDiff(BaseModel):
    context_name: str
    new_values: List[HierarchyChangeItem] = []
    missing_values: List[HierarchyChangeItem] = []
    unchanged_count: int = 0


# --- Unmatched keywords ---

class UnmatchedKeyword(BaseModel):
    keyword: str
    context_name: str
    occurrence_count: int
    last_question: Optional[str] = None
    suggested_column: Optional[str] = None
    suggested_value: Optional[str] = None
