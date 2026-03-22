"""Query pattern admin endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.api import deps
from app.models.schema_models import QueryComplexityPattern
from app.models.user import User
from app.schemas.admin_schemas import (
    QueryPatternCreate,
    QueryPatternListResponse,
    QueryPatternResponse,
    QueryPatternUpdate,
)
from app.services.query_classifier import clear_patterns_cache

router = APIRouter()


@router.get("/query-patterns", response_model=QueryPatternListResponse)
def list_query_patterns(
    tier: Optional[str] = Query(None, description="Filter by tier (simple/complex)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all query complexity patterns. Admin only."""
    query = db.query(QueryComplexityPattern)
    if tier:
        query = query.filter(QueryComplexityPattern.tier == tier)
    if is_active is not None:
        query = query.filter(QueryComplexityPattern.is_active == is_active)

    patterns = query.order_by(QueryComplexityPattern.tier, QueryComplexityPattern.id).all()
    return QueryPatternListResponse(
        patterns=[QueryPatternResponse.model_validate(pattern) for pattern in patterns],
        total=len(patterns),
    )


@router.get("/query-patterns/{pattern_id}", response_model=QueryPatternResponse)
def get_query_pattern(
    pattern_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single query pattern. Admin only."""
    pattern = db.query(QueryComplexityPattern).filter(QueryComplexityPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Query pattern not found")
    return QueryPatternResponse.model_validate(pattern)


@router.post("/query-patterns", response_model=QueryPatternResponse, status_code=status.HTTP_201_CREATED)
def create_query_pattern(
    data: QueryPatternCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Create new query pattern. Admin only."""
    existing = db.query(QueryComplexityPattern).filter(
        QueryComplexityPattern.tier == data.tier,
        QueryComplexityPattern.pattern == data.pattern,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Pattern already exists for tier '{data.tier}'")

    pattern = QueryComplexityPattern(**data.model_dump())
    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    clear_patterns_cache()
    return QueryPatternResponse.model_validate(pattern)


@router.put("/query-patterns/{pattern_id}", response_model=QueryPatternResponse)
def update_query_pattern(
    pattern_id: int,
    data: QueryPatternUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Update query pattern. Admin only."""
    pattern = db.query(QueryComplexityPattern).filter(QueryComplexityPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Query pattern not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pattern, key, value)

    db.commit()
    db.refresh(pattern)

    clear_patterns_cache()
    return QueryPatternResponse.model_validate(pattern)


@router.delete("/query-patterns/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query_pattern(
    pattern_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Delete query pattern. Admin only."""
    pattern = db.query(QueryComplexityPattern).filter(QueryComplexityPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Query pattern not found")

    db.delete(pattern)
    db.commit()

    clear_patterns_cache()
    return None
