"""Semantic mappings admin endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.schema_models import SchemaSemanticMapping
from app.models.user import User
from app.schemas.admin_schemas import (
    SemanticMappingCreate,
    SemanticMappingListResponse,
    SemanticMappingResponse,
    SemanticMappingUpdate,
)
from app.services.query_engine import clear_query_cache
from app.services.schema_service import SchemaService
from ._shared import mark_brain_dirty
from app.core.time_utils import utcnow

router = APIRouter()


@router.get("/mappings", response_model=SemanticMappingListResponse)
def list_semantic_mappings(
    keyword_type: Optional[str] = Query(None, description="Filter by type (abbreviation, term, synonym)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    context_name: Optional[str] = Query(None, description="Filter by context (None=all, 'revenue', 'transfer price', etc.)"),
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all semantic mappings. Admin only."""
    query = db.query(SchemaSemanticMapping)
    if keyword_type:
        query = query.filter(SchemaSemanticMapping.keyword_type == keyword_type)
    if is_active is not None:
        query = query.filter(SchemaSemanticMapping.is_active == is_active)
    if context_name is not None:
        if context_name == "global":
            query = query.filter(SchemaSemanticMapping.context_name.is_(None))
        else:
            query = query.filter(SchemaSemanticMapping.context_name == context_name)

    mappings = query.order_by(SchemaSemanticMapping.priority.desc(), SchemaSemanticMapping.keyword).all()
    return SemanticMappingListResponse(
        mappings=[SemanticMappingResponse.model_validate(mapping) for mapping in mappings],
        total=len(mappings),
    )


@router.get("/mappings/{mapping_id}", response_model=SemanticMappingResponse)
def get_semantic_mapping(
    mapping_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single semantic mapping. Admin only."""
    mapping = db.query(SchemaSemanticMapping).filter(SchemaSemanticMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Semantic mapping not found")
    return SemanticMappingResponse.model_validate(mapping)


@router.post("/mappings", response_model=SemanticMappingResponse, status_code=status.HTTP_201_CREATED)
def create_semantic_mapping(
    data: SemanticMappingCreate,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Create semantic mapping. Admin only."""
    existing = db.query(SchemaSemanticMapping).filter(
        SchemaSemanticMapping.keyword == data.keyword
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Keyword '{data.keyword}' already exists")

    mapping = SchemaSemanticMapping(**data.model_dump())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()

    return SemanticMappingResponse.model_validate(mapping)


@router.put("/mappings/{mapping_id}", response_model=SemanticMappingResponse)
def update_semantic_mapping(
    mapping_id: int,
    data: SemanticMappingUpdate,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Update semantic mapping. Admin only."""
    mapping = db.query(SchemaSemanticMapping).filter(SchemaSemanticMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Semantic mapping not found")

    update_data = data.model_dump(exclude_unset=True)
    if "keyword" in update_data and update_data["keyword"] != mapping.keyword:
        existing = db.query(SchemaSemanticMapping).filter(
            SchemaSemanticMapping.keyword == update_data["keyword"]
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Keyword '{update_data['keyword']}' already exists")

    for key, value in update_data.items():
        setattr(mapping, key, value)

    mapping.updated_at = utcnow()
    db.commit()
    db.refresh(mapping)

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()

    return SemanticMappingResponse.model_validate(mapping)


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_semantic_mapping(
    mapping_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Delete semantic mapping. Admin only."""
    mapping = db.query(SchemaSemanticMapping).filter(SchemaSemanticMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Semantic mapping not found")

    db.delete(mapping)
    db.commit()

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return None
