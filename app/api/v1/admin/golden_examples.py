"""Golden examples admin endpoints."""

from typing import List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.feedback_models import GoldenExample
from app.models.user import User
from app.schemas.admin_schemas import (
    GoldenExampleCreate,
    GoldenExampleListResponse,
    GoldenExampleResponse,
    GoldenExampleUpdate,
)
from app.services.ai_service import AIService
from app.services.provenance import ACTIVE, MANUAL, mark_human_edit
from app.services.query_engine import clear_query_cache
from ._shared import mark_brain_dirty

router = APIRouter()


@router.get("/golden-examples", response_model=GoldenExampleListResponse)
def list_golden_examples(
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all golden examples. Admin only."""
    query = db.query(GoldenExample)
    if category:
        query = query.filter(GoldenExample.category == category)
    if is_active is not None:
        query = query.filter(GoldenExample.is_active == is_active)

    total = query.count()
    examples = query.order_by(GoldenExample.usage_count.desc(), GoldenExample.created_at.desc()).offset(offset).limit(limit).all()
    categories = db.query(GoldenExample.category).distinct().filter(GoldenExample.category.isnot(None)).all()
    category_list = [category_row[0] for category_row in categories if category_row[0]]

    return GoldenExampleListResponse(
        examples=[GoldenExampleResponse.model_validate(example) for example in examples],
        total=total,
        categories=category_list,
    )


@router.get("/golden-examples/categories", response_model=List[str])
def list_golden_example_categories(
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all golden example categories. Admin only."""
    categories = db.query(GoldenExample.category).distinct().filter(GoldenExample.category.isnot(None)).all()
    return [category_row[0] for category_row in categories if category_row[0]]


@router.get("/golden-examples/{example_id}", response_model=GoldenExampleResponse)
def get_golden_example(
    example_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single golden example. Admin only."""
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")
    return GoldenExampleResponse.model_validate(example)


@router.post("/golden-examples", response_model=GoldenExampleResponse, status_code=status.HTTP_201_CREATED)
def create_golden_example(
    data: GoldenExampleCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    ai_service: AIService = Depends(deps.get_ai_service),
):
    """Create golden example manually. Admin only. Also trains Vanna."""
    example = GoldenExample(**data.model_dump(), added_by=current_user.id, source=MANUAL, status=ACTIVE)
    db.add(example)
    db.commit()
    db.refresh(example)

    if cast(bool, example.is_active):
        ai_service.train(
            question=cast(str, example.question_pattern),
            sql_query=cast(str, example.expected_sql),
        )

    clear_query_cache()
    mark_brain_dirty()
    return GoldenExampleResponse.model_validate(example)


@router.put("/golden-examples/{example_id}", response_model=GoldenExampleResponse)
def update_golden_example(
    example_id: int,
    data: GoldenExampleUpdate,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    ai_service: AIService = Depends(deps.get_ai_service),
):
    """Update golden example. Admin only. Also retrains Vanna if active."""
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(example, key, value)
    mark_human_edit(example, "golden_examples", update_data)

    db.commit()
    db.refresh(example)

    if cast(bool, example.is_active):
        ai_service.train(
            question=cast(str, example.question_pattern),
            sql_query=cast(str, example.expected_sql),
        )

    clear_query_cache()
    mark_brain_dirty()
    return GoldenExampleResponse.model_validate(example)


@router.delete("/golden-examples/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_golden_example(
    example_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Delete golden example. Admin only."""
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")

    db.delete(example)
    db.commit()
    clear_query_cache()
    mark_brain_dirty()
    return None
