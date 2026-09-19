"""API key management admin endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.admin_schemas import APIKeyCreateRequest, APIKeyCreateResponse, APIKeyResponse
from app.services.api_key_service import APIKeyService, KEY_PREFIX

router = APIRouter()


@router.post("/api-keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: APIKeyCreateRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Create a new API key. The raw key is returned once.

    workspace / allowed_contexts (Plan 7 Phase 4a) bind the key to those contexts and to the query
    API; a binding that could never work is refused here (400), not discovered as 403s later.
    """
    from app.services.workspaces import resolve_key_binding

    try:
        workspace_id, allowed = resolve_key_binding(request.workspace, request.allowed_contexts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    service = APIKeyService(db)
    raw_key, api_key = service.create_key(
        user_id=current_user.id,
        name=request.name,
        scopes=request.scopes,
        rate_limit_per_minute=request.rate_limit_per_minute,
        rate_limit_per_day=request.rate_limit_per_day,
        workspace_id=workspace_id,
        allowed_contexts=allowed,
    )
    return APIKeyCreateResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        user_id=api_key.user_id,
        scopes=api_key.scopes,
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        rate_limit_per_day=api_key.rate_limit_per_day,
        is_active=api_key.is_active,
        last_used_at=str(api_key.last_used_at) if api_key.last_used_at else None,
        created_at=str(api_key.created_at) if api_key.created_at else None,
        workspace_id=api_key.workspace_id,
        allowed_contexts=api_key.allowed_contexts,
        raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list)
def list_api_keys(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """List all API keys for the current user."""
    service = APIKeyService(db)
    keys = service.list_keys(user_id=current_user.id)
    return [
        APIKeyResponse(
            id=key.id,
            key_prefix=key.key_prefix,
            name=key.name,
            user_id=key.user_id,
            scopes=key.scopes,
            rate_limit_per_minute=key.rate_limit_per_minute,
            rate_limit_per_day=key.rate_limit_per_day,
            is_active=key.is_active,
            last_used_at=str(key.last_used_at) if key.last_used_at else None,
            created_at=str(key.created_at) if key.created_at else None,
            workspace_id=key.workspace_id,
            allowed_contexts=key.allowed_contexts,
        ).model_dump()
        for key in keys
    ]


@router.delete("/api-keys/{key_id}")
def revoke_api_key(
    key_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Revoke an API key."""
    service = APIKeyService(db)
    success = service.revoke_key(key_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "key_id": key_id}


@router.get("/api-keys/{key_id}/usage")
def get_api_key_usage(
    key_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
):
    """Get usage statistics for an API key."""
    service = APIKeyService(db)
    return service.get_usage_stats(key_id, days=days)
