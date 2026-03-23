"""Schema contexts admin endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.models.user import User
from app.schemas.admin_schemas import (
    SchemaContextCreate,
    SchemaContextListResponse,
    SchemaContextResponse,
    SchemaContextUpdate,
)
from app.services.query_engine import clear_query_cache
from app.services.schema_service import SchemaService
from ._shared import mark_brain_dirty

router = APIRouter()


@router.get("/contexts", response_model=SchemaContextListResponse)
def list_contexts(
    _current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """List all schema contexts. Admin only."""
    contexts = service.get_all_contexts()
    return SchemaContextListResponse(
        contexts=[SchemaContextResponse.model_validate(context) for context in contexts],
        total=len(contexts),
    )


@router.post("/contexts", response_model=SchemaContextResponse, status_code=status.HTTP_201_CREATED)
def create_context(
    data: SchemaContextCreate,
    _current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Create new schema context. Admin only."""
    try:
        context = service.create_context(data.model_dump())
        clear_query_cache()
        mark_brain_dirty()
        return SchemaContextResponse.model_validate(context)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/contexts/{context_id}", response_model=SchemaContextResponse)
def update_context(
    context_id: int,
    data: SchemaContextUpdate,
    _current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Update schema context. Admin only."""
    try:
        context = service.update_context(context_id, data.model_dump(exclude_unset=True))
        if not context:
            raise HTTPException(status_code=404, detail="Context not found")
        clear_query_cache()
        mark_brain_dirty()
        return SchemaContextResponse.model_validate(context)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/contexts/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_context(
    context_id: int,
    _current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Delete schema context. Admin only."""
    service.delete_context(context_id)
    clear_query_cache()
    mark_brain_dirty()
    return None
