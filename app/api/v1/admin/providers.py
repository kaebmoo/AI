"""AI provider and model management admin endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services.admin_config_service import AdminConfigService

router = APIRouter()


@router.get("/providers", response_model=List[dict])
def list_providers(
    include_inactive: bool = Query(False, description="Include inactive providers"),
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Get all AI providers. Admin only."""
    config_service = AdminConfigService()
    return config_service.get_all_providers(include_inactive=include_inactive)


@router.post("/providers", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_provider(
    data: dict,
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Create a new AI provider. Admin only."""
    config_service = AdminConfigService()
    provider_key = data.get("id") or data.get("provider_id")
    success = config_service.create_provider(
        provider_id=provider_key,
        name=data.get("name"),
        display_name=data.get("display_name"),
        icon=data.get("icon", "bulb"),
        api_key_env_var=data.get("api_key_env_var"),
        api_url_env_var=data.get("api_url_env_var"),
        default_api_url=data.get("default_api_url"),
        description=data.get("description"),
        priority=data.get("priority", 0),
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create provider")
    return {"status": "success", "message": "Provider created"}


@router.put("/providers/{provider_id}", response_model=dict)
def update_provider(
    provider_id: str,
    data: dict,
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Update an existing AI provider. Admin only."""
    config_service = AdminConfigService()
    success = config_service.update_provider(
        provider_id=provider_id,
        name=data.get("name"),
        display_name=data.get("display_name"),
        icon=data.get("icon"),
        is_active=data.get("is_active"),
        is_default=data.get("is_default"),
        api_key_env_var=data.get("api_key_env_var"),
        api_url_env_var=data.get("api_url_env_var"),
        default_api_url=data.get("default_api_url"),
        description=data.get("description"),
        priority=data.get("priority"),
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update provider")
    return {"status": "success", "message": "Provider updated"}


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(
    provider_id: str,
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Delete an AI provider. Admin only."""
    config_service = AdminConfigService()
    success = config_service.delete_provider(provider_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete provider")
    return None


@router.get("/providers/{provider_id}/models", response_model=List[dict])
def list_models(
    provider_id: str,
    include_inactive: bool = Query(False, description="Include inactive models"),
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Get all models for a provider. Admin only."""
    config_service = AdminConfigService()
    return config_service.get_models_by_provider(provider_id, include_inactive=include_inactive)


@router.post("/providers/{provider_id}/models", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_model(
    provider_id: str,
    data: dict,
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Create a new AI model for a provider. Admin only."""
    config_service = AdminConfigService()
    success = config_service.create_model(
        provider_id=provider_id,
        model_id=data.get("model_id"),
        display_name=data.get("display_name"),
        is_default=data.get("is_default", False),
        context_window=data.get("context_window"),
        supports_vision=data.get("supports_vision", False),
        description=data.get("description"),
        priority=data.get("priority", 0),
        tier=data.get("tier", "default"),
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create model")
    return {"status": "success", "message": "Model created"}


@router.put("/models/{model_id}", response_model=dict)
def update_model(
    model_id: int,
    data: dict,
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Update an existing AI model. Admin only."""
    config_service = AdminConfigService()
    success = config_service.update_model(
        model_pk_id=model_id,
        display_name=data.get("display_name"),
        is_active=data.get("is_active"),
        is_default=data.get("is_default"),
        context_window=data.get("context_window"),
        supports_vision=data.get("supports_vision"),
        description=data.get("description"),
        priority=data.get("priority"),
        tier=data.get("tier"),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Model not found or update failed")
    return {"status": "success", "message": "Model updated"}


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: int,
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Delete an AI model. Admin only."""
    config_service = AdminConfigService()
    success = config_service.delete_model(model_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete model")
    return None
