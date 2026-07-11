"""Business rules admin endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.schema_models import SchemaBusinessRule
from app.models.user import User
from app.schemas.admin_schemas import (
    BusinessRuleCreate,
    BusinessRuleListResponse,
    BusinessRuleResponse,
    BusinessRuleUpdate,
)
from app.services.query_engine import clear_query_cache
from app.services.schema_service import SchemaService

from ._shared import mark_brain_dirty
from app.core.time_utils import utcnow

router = APIRouter()


@router.get("/rules", response_model=BusinessRuleListResponse)
def list_business_rules(
    severity: Optional[str] = Query(None, description="Filter by severity (error, warning, info)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all business rules. Admin only."""
    query = db.query(SchemaBusinessRule)
    if severity:
        query = query.filter(SchemaBusinessRule.severity == severity)
    if is_active is not None:
        query = query.filter(SchemaBusinessRule.is_active == is_active)

    rules = query.order_by(SchemaBusinessRule.severity, SchemaBusinessRule.rule_code).all()
    return BusinessRuleListResponse(
        rules=[BusinessRuleResponse.model_validate(rule) for rule in rules],
        total=len(rules),
    )


@router.get("/rules/{rule_id}", response_model=BusinessRuleResponse)
def get_business_rule(
    rule_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single business rule. Admin only."""
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")
    return BusinessRuleResponse.model_validate(rule)


@router.post("/rules", response_model=BusinessRuleResponse, status_code=status.HTTP_201_CREATED)
def create_business_rule(
    data: BusinessRuleCreate,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Create new business rule. Admin only."""
    existing = db.query(SchemaBusinessRule).filter(
        SchemaBusinessRule.rule_code == data.rule_code
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Rule code '{data.rule_code}' already exists")

    rule = SchemaBusinessRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return BusinessRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=BusinessRuleResponse)
def update_business_rule(
    rule_id: int,
    data: BusinessRuleUpdate,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Update business rule. Admin only."""
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    rule.updated_at = utcnow()
    db.commit()
    db.refresh(rule)

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return BusinessRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_rule(
    rule_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Delete business rule. Admin only."""
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")

    db.delete(rule)
    db.commit()

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return None


@router.post("/rules/{rule_id}/toggle", response_model=BusinessRuleResponse)
def toggle_business_rule(
    rule_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Toggle business rule active status. Admin only."""
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")

    rule.is_active = not rule.is_active
    rule.updated_at = utcnow()
    db.commit()
    db.refresh(rule)

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return BusinessRuleResponse.model_validate(rule)
