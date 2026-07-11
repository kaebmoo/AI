"""Admin configuration and feature flag endpoints."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services.admin_config_service import AdminConfigService
from app.services.schema_service import SchemaService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/config/ai", response_model=dict)
def get_ai_config(
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Get complete AI configuration. Admin only."""
    config_service = AdminConfigService()
    ai_config = config_service.get_ai_config()
    feature_flags = config_service.get_feature_flags()
    return {
        "ai": ai_config,
        "features": feature_flags,
        "fallback_note": "Values shown here may come from database (priority 1) or .env file (priority 2)",
    }


@router.get("/config/ai/effective", response_model=dict)
def get_effective_ai_config(
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Get the effective runtime AI configuration used by admin surfaces."""
    config_service = AdminConfigService()
    return config_service.get_effective_ai_state()


@router.put("/config/ai", response_model=dict)
def update_ai_config(
    config_update: dict,
    current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Update AI configuration. Admin only."""
    config_service = AdminConfigService()
    actor_email = str(current_user.email)
    success = config_service.update_ai_config(updates=config_update, updated_by=actor_email)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")

    config_service.clear_cache()
    return {
        "status": "success",
        "message": "AI configuration updated successfully",
        "updated_by": actor_email,
    }


@router.get("/config/ai/providers", response_model=List[dict])
def get_active_providers(
    _db: Session = Depends(deps.get_config_db),
):
    """Get list of active AI providers. Public endpoint."""
    config_service = AdminConfigService()
    return config_service.get_active_providers()


@router.get("/config/ai/models/{provider}", response_model=List[str])
def get_available_models(
    provider: str,
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Get available models for a specific provider. Admin only."""
    if provider not in ["claude", "gemini", "matcha"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    config_service = AdminConfigService()
    return config_service.get_available_models(provider)


@router.get("/config/features", response_model=dict)
def get_feature_flags(
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Get all feature flags. Admin only."""
    config_service = AdminConfigService()
    return config_service.get_feature_flags()


@router.post("/config/features/{feature_name}/toggle", response_model=dict)
def toggle_feature_flag(
    feature_name: str,
    enabled: bool,
    current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Toggle a feature flag. Admin only."""
    config_service = AdminConfigService()
    actor_email = str(current_user.email)
    success = config_service.toggle_feature(
        feature_name=feature_name,
        enabled=enabled,
        updated_by=actor_email,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to toggle feature")

    return {
        "status": "success",
        "feature": feature_name,
        "enabled": enabled,
        "updated_by": actor_email,
    }


# Numeric tuning values settable from the UI — allowlisted, not arbitrary config writes
_NUMERIC_CONFIG_KEYS = {"query_latency_budget_s"}


@router.put("/config/settings/{key}", response_model=dict)
def set_numeric_config(
    key: str,
    value: float,
    current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Set an allowlisted numeric config value. Admin only."""
    if key not in _NUMERIC_CONFIG_KEYS:
        raise HTTPException(status_code=400, detail=f"Key '{key}' is not settable via this endpoint")
    if value <= 0:
        raise HTTPException(status_code=400, detail="Value must be positive")

    config_service = AdminConfigService()
    success = config_service.set_config(key, str(value), updated_by=str(current_user.email))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set config")
    return {"status": "success", "key": key, "value": value}


@router.post("/config/cache/clear", response_model=dict)
def clear_config_cache(
    _current_user: User = Depends(deps.require_admin),
    _db: Session = Depends(deps.get_config_db),
):
    """Clear configuration cache. Admin only."""
    config_service = AdminConfigService()
    config_service.clear_cache()
    return {"status": "success", "message": "Configuration cache cleared"}


@router.post("/config/rebuild-keyword-index", response_model=dict)
def rebuild_keyword_index(
    _current_user: User = Depends(deps.require_admin),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Rebuild keyword value index for smart value lookup. Admin only."""
    total = 0
    try:
        contexts = schema_service.get_all_contexts()
        for context in contexts:
            ctx_name = context.get("name", "")
            main_view = context.get("main_view", "")
            if ctx_name and main_view:
                try:
                    total += schema_service.build_keyword_index(ctx_name, main_view)
                except Exception as exc:
                    logger.warning("Failed to build index for %s: %s", ctx_name, exc)
    except Exception as exc:
        logger.error("Failed to get contexts for index rebuild: %s", exc)

    return {
        "status": "success",
        "message": f"Keyword index rebuilt: {total} entries",
        "total_entries": total,
    }
