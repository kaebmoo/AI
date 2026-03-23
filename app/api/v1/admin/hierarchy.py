"""Hierarchy management admin endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api import deps
from app.models.user import User
from app.schemas.hierarchy_schemas import (
    HierarchyContextSummary,
    HierarchyDiff,
    HierarchyExtractResult,
    HierarchyLevelCreate,
    HierarchyLevelResponse,
    HierarchyLevelUpdate,
    HierarchySearchResult,
    HierarchyValueCreate,
    HierarchyValueUpdate,
    UnmatchedKeyword,
)
from app.services.hierarchy_service import hierarchy_service
from app.services.query_engine import clear_query_cache

from ._shared import mark_brain_dirty

router = APIRouter()


@router.get("/hierarchy/{context_name}/search", response_model=List[HierarchySearchResult])
def search_hierarchy(
    context_name: str,
    q: str = Query(..., min_length=1, description="Search keyword"),
    limit: int = Query(10, le=50),
):
    """Search hierarchy values by alias match. Public endpoint used by AI pipeline."""
    return hierarchy_service.search_aliases(context_name, q, limit)


@router.get("/hierarchy", response_model=List[HierarchyContextSummary])
def list_hierarchy_contexts(
    current_user: User = Depends(deps.require_admin),
):
    """List all hierarchy contexts with summary."""
    return hierarchy_service.list_contexts()


@router.get("/hierarchy/{context_name}/levels", response_model=List[HierarchyLevelResponse])
def get_hierarchy_levels(
    context_name: str,
    current_user: User = Depends(deps.require_admin),
):
    """Get hierarchy levels for a context."""
    return hierarchy_service.get_levels(context_name)


@router.post("/hierarchy/{context_name}/levels")
def create_hierarchy_level(
    context_name: str,
    body: HierarchyLevelCreate,
    current_user: User = Depends(deps.require_admin),
):
    """Create or update a hierarchy level."""
    result = hierarchy_service.upsert_level(context_name, body.level, body.model_dump())
    clear_query_cache()
    mark_brain_dirty()
    return result


@router.put("/hierarchy/{context_name}/levels/{level}")
def update_hierarchy_level(
    context_name: str,
    level: int,
    body: HierarchyLevelUpdate,
    current_user: User = Depends(deps.require_admin),
):
    """Update a hierarchy level."""
    data = {key: value for key, value in body.model_dump().items() if value is not None}
    result = hierarchy_service.upsert_level(context_name, level, data)
    clear_query_cache()
    mark_brain_dirty()
    return result


@router.delete("/hierarchy/{context_name}/levels/{level}", status_code=204)
def delete_hierarchy_level(
    context_name: str,
    level: int,
    current_user: User = Depends(deps.require_admin),
):
    """Soft-delete a hierarchy level."""
    hierarchy_service.delete_level(context_name, level)
    clear_query_cache()
    mark_brain_dirty()
    return None


@router.get("/hierarchy/{context_name}/values")
def get_hierarchy_values(
    context_name: str,
    level: Optional[int] = None,
    parent_value: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user: User = Depends(deps.require_admin),
):
    """Get hierarchy values with filtering and pagination."""
    return hierarchy_service.get_values(context_name, level, parent_value, search, page, page_size)


@router.post("/hierarchy/{context_name}/values")
def create_hierarchy_value(
    context_name: str,
    body: HierarchyValueCreate,
    current_user: User = Depends(deps.require_admin),
):
    """Create a hierarchy value."""
    result = hierarchy_service.create_value(context_name, body.model_dump())
    clear_query_cache()
    mark_brain_dirty()
    return result


@router.put("/hierarchy/values/{value_id}")
def update_hierarchy_value(
    value_id: int,
    body: HierarchyValueUpdate,
    current_user: User = Depends(deps.require_admin),
):
    """Update a hierarchy value."""
    data = {key: value for key, value in body.model_dump().items() if value is not None}
    result = hierarchy_service.update_value(value_id, data)
    clear_query_cache()
    mark_brain_dirty()
    return result


@router.delete("/hierarchy/values/{value_id}", status_code=204)
def delete_hierarchy_value(
    value_id: int,
    current_user: User = Depends(deps.require_admin),
):
    """Soft-delete a hierarchy value."""
    hierarchy_service.delete_value(value_id)
    clear_query_cache()
    mark_brain_dirty()
    return None


@router.post("/hierarchy/extract", response_model=List[HierarchyExtractResult])
def extract_hierarchy(
    context_name: Optional[str] = None,
    current_user: User = Depends(deps.require_admin),
):
    """Trigger auto-extract hierarchy from data."""
    result = hierarchy_service.auto_extract(context_name)
    clear_query_cache()
    mark_brain_dirty()
    return result


@router.post("/hierarchy/bootstrap")
def bootstrap_hierarchy(
    context_name: str = Query(..., description="New context name"),
    view_name: str = Query(..., description="View/table to extract from"),
    current_user: User = Depends(deps.require_admin),
):
    """Bootstrap a new hierarchy context from scratch."""
    result = hierarchy_service.bootstrap_from_view(context_name, view_name)
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(400, result["error"])
    hierarchy_service._invalidate_cache()
    clear_query_cache()
    mark_brain_dirty()
    return result


@router.get("/hierarchy/views")
def list_available_views(
    current_user: User = Depends(deps.require_admin),
):
    """List available views/tables for hierarchy extraction."""
    return hierarchy_service.get_available_views()


@router.post("/hierarchy/{context_name}/import-csv")
async def import_csv_hierarchy(
    context_name: str,
    file: UploadFile = File(...),
    level: int = Query(..., description="Target hierarchy level"),
    value_column: str = Query(..., description="CSV column containing the value"),
    parent_column: Optional[str] = Query(None, description="CSV column containing the parent value"),
    alias_columns: Optional[str] = Query(None, description="Comma-separated CSV columns to use as aliases"),
    current_user: User = Depends(deps.require_admin),
):
    """Import hierarchy values from an uploaded CSV file."""
    import csv
    import io

    content = await file.read()
    text = content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        from fastapi import HTTPException
        raise HTTPException(400, "CSV file is empty")

    csv_columns = list(rows[0].keys())
    if value_column not in csv_columns:
        from fastapi import HTTPException
        raise HTTPException(400, f"Column '{value_column}' not found. Available: {csv_columns}")
    if parent_column and parent_column not in csv_columns:
        from fastapi import HTTPException
        raise HTTPException(400, f"Column '{parent_column}' not found. Available: {csv_columns}")

    alias_cols = [column.strip() for column in alias_columns.split(",")] if alias_columns else []
    for alias_col in alias_cols:
        if alias_col not in csv_columns:
            from fastapi import HTTPException
            raise HTTPException(400, f"Alias column '{alias_col}' not found. Available: {csv_columns}")

    imported = 0
    for row in rows:
        value = (row.get(value_column) or "").strip()
        if not value:
            continue
        parent = (row.get(parent_column) or "").strip() if parent_column else None

        aliases = [value.lower()]
        for alias_col in alias_cols:
            alias_val = (row.get(alias_col) or "").strip()
            if alias_val and alias_val.lower() not in aliases:
                aliases.append(alias_val.lower())

        hierarchy_service.create_value(
            context_name,
            {"level": level, "value": value, "parent_value": parent or None, "aliases": sorted(aliases)},
        )
        imported += 1

    clear_query_cache()
    mark_brain_dirty()
    return {"success": True, "imported": imported, "filename": file.filename}


@router.get("/hierarchy/{context_name}/diff", response_model=HierarchyDiff)
def get_hierarchy_diff(
    context_name: str,
    current_user: User = Depends(deps.require_admin),
):
    """Compare master hierarchy vs actual data."""
    return hierarchy_service.detect_changes(context_name)


@router.get("/hierarchy/unmatched", response_model=List[UnmatchedKeyword])
def get_unmatched_keywords(
    context_name: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(deps.require_admin),
):
    """Get unmatched keywords that AI used LIKE for but had no alias match."""
    return hierarchy_service.get_unmatched_keywords(context_name, limit)


@router.post("/hierarchy/unmatched/{keyword}/resolve")
def resolve_unmatched_keyword(
    keyword: str,
    context_name: str = Query(...),
    current_user: User = Depends(deps.require_admin),
):
    """Mark an unmatched keyword as resolved."""
    hierarchy_service.resolve_unmatched_keyword(keyword, context_name)
    clear_query_cache()
    mark_brain_dirty()
    return {"success": True}
