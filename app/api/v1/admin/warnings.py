"""Data warnings admin endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.schema_models import DataWarningModel
from app.models.user import User
from app.schemas.admin_schemas import (
    DataWarningCreate,
    DataWarningListResponse,
    DataWarningResponse,
    DataWarningUpdate,
)
from app.services.provenance import ACTIVE, MANUAL, apply_human_edit
from app.services.warning_detector import clear_warnings_cache
from app.core.time_utils import utcnow

router = APIRouter()


@router.get("/warnings", response_model=DataWarningListResponse)
def list_data_warnings(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    context_name: Optional[str] = Query(None, description="Filter by context"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all data warnings. Admin only."""
    query = db.query(DataWarningModel)
    if severity:
        query = query.filter(DataWarningModel.severity == severity)
    if is_active is not None:
        query = query.filter(DataWarningModel.is_active == is_active)
    if context_name:
        query = query.filter(DataWarningModel.context_name == context_name)

    warnings = query.order_by(DataWarningModel.code).all()
    return DataWarningListResponse(
        warnings=[DataWarningResponse.model_validate(warning) for warning in warnings],
        total=len(warnings),
    )


@router.get("/warnings/{warning_id}", response_model=DataWarningResponse)
def get_data_warning(
    warning_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single data warning. Admin only."""
    warning = db.query(DataWarningModel).filter(DataWarningModel.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Data warning not found")
    return DataWarningResponse.model_validate(warning)


@router.post("/warnings", response_model=DataWarningResponse, status_code=status.HTTP_201_CREATED)
def create_data_warning(
    data: DataWarningCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Create new data warning. Admin only."""
    existing = db.query(DataWarningModel).filter(DataWarningModel.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Warning code '{data.code}' already exists")

    warning = DataWarningModel(**data.model_dump(), source=MANUAL, status=ACTIVE)
    db.add(warning)
    db.commit()
    db.refresh(warning)

    clear_warnings_cache()
    return DataWarningResponse.model_validate(warning)


@router.put("/warnings/{warning_id}", response_model=DataWarningResponse)
def update_data_warning(
    warning_id: int,
    data: DataWarningUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Update data warning. Admin only."""
    warning = db.query(DataWarningModel).filter(DataWarningModel.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Data warning not found")

    update_data = data.model_dump(exclude_unset=True)
    apply_human_edit(warning, "data_warnings", update_data)

    warning.updated_at = utcnow()
    db.commit()
    db.refresh(warning)

    clear_warnings_cache()
    return DataWarningResponse.model_validate(warning)


@router.delete("/warnings/{warning_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_warning(
    warning_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Delete data warning. Admin only."""
    warning = db.query(DataWarningModel).filter(DataWarningModel.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Data warning not found")

    db.delete(warning)
    db.commit()

    clear_warnings_cache()
    return None
