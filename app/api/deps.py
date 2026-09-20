import logging
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from app.db.session import SessionLocal
from app.services.auth_service import AuthService
from app.models.user import User
from app.config import settings
from app.services.ai_service import AIService
from app.providers.registry import provider_registry
from app.services.mcp_client import MCPClientService

logger = logging.getLogger(__name__)

# Header schemes for authentication
header_scheme = APIKeyHeader(name="X-Session-Token", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_config_db() -> Generator:
    """Get Config DB session (schema_contexts, mappings, rules, admin_config etc.)"""
    from app.db.session import ConfigSessionLocal
    db = ConfigSessionLocal()
    try:
        yield db
    finally:
        db.close()

def enforce_key_surface(api_key, path: str) -> None:
    """A key bound to a workspace/allowlist (Plan 7 Phase 4a) works on the query API only:
    /chat, /admin, … take a context too and know nothing about allowlists."""
    from app.services.workspaces import is_restricted

    # /mcp (Phase 6) authenticates in its own gate (app/api/v1/mcp_facade.py) — listed so the rule reads whole
    prefixes = (f"{settings.API_V1_STR}/query", f"{settings.API_V1_STR}/mcp")
    if is_restricted(api_key) and not any(path == p or path.startswith(p + "/") for p in prefixes):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="API key นี้ใช้ได้เฉพาะ /api/v1/query")


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(header_scheme),
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Depends(api_key_header),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from session token OR API key.
    Priority: X-API-Key > X-Session-Token > Authorization: Bearer
    """
    # 1. Try API key first
    if x_api_key:
        try:
            from app.services.api_key_service import APIKeyService, KEY_PREFIX
            api_key_service = APIKeyService(db)
            api_key, refusal = api_key_service.check_key(x_api_key)
            if refusal == "rate_limited":
                # a real key over its quota is not "unauthenticated": say so instead of falling through to 401
                from app.core.outbound import ERRORS
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                    detail=ERRORS["rate_limited"][1])
            if api_key:
                enforce_key_surface(api_key, request.url.path)
                # Track usage
                api_key_service.track_usage(api_key.id)
                # Store API key info in request state for scope checking
                request.state.api_key = api_key
                # Return the key owner (only if still active)
                user = db.query(User).filter(User.id == api_key.user_id).first()
                if user and user.is_active:
                    return user
        except HTTPException:
            raise  # a valid but restricted key off the query API: 403, not a fall-through to session auth
        except (ImportError, ValueError, AttributeError) as e:
            logger.debug(f"API key auth failed, falling through to session auth: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error in API key auth: {e}")
            # Still fall through to session auth

    # 2. Session token auth
    final_token = token or bearer_token

    if not final_token:
        # Fallback: Check raw Authorization header manually if schemes fail
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            final_token = auth_header.split(" ")[1]
    if not final_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    auth_service = AuthService(db)
    session = auth_service.validate_session(final_token)

    if not session or not session.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    return session.user

def get_mcp_client(request: Request) -> MCPClientService:
    """Get initialized MCP Client from app state"""
    if not hasattr(request.app.state, "mcp_client"):
         # For testing or if lifespan failed? 
         # We shouldn't fallback to creating new one usually as it spawns processes
         raise HTTPException(status_code=500, detail="MCP Client not initialized")
    return request.app.state.mcp_client

from app.services.admin_config_service import AdminConfigService

def get_admin_config_service() -> Generator:
    """AdminConfigService with its own config-DB session, closed after the request."""
    svc = AdminConfigService()
    try:
        yield svc
    finally:
        svc.close()

def get_ai_service(
    mcp_client: MCPClientService = Depends(get_mcp_client),
    config_service: AdminConfigService = Depends(get_admin_config_service),
) -> AIService:
    """
    Dependency to get initialized AIService based on config.
    Prioritizes DB config > Env var > Default.
    Uses provider_registry for auto-discovery and fallback.
    """
    ai_config = config_service.get_ai_config()
    default_provider = ai_config.get("default_provider", "matcha")

    # Build kwargs from config
    provider_kwargs = {}
    api_key = config_service.get_provider_api_key(default_provider)
    if not api_key:
        raise HTTPException(status_code=500, detail=f"{default_provider.upper()} API key not configured")

    provider_kwargs["api_key"] = api_key

    if default_provider == "claude":
        provider_kwargs["model"] = ai_config.get("claude_model", settings.CLAUDE_MODEL)
        provider_kwargs["extended_thinking"] = ai_config.get("claude_extended_thinking", False)
        provider_kwargs["thinking_budget_tokens"] = ai_config.get("claude_thinking_budget_tokens", 8000)
    elif default_provider == "gemini":
        provider_kwargs["model"] = ai_config.get("gemini_model", settings.GEMINI_MODEL)
    elif default_provider == "matcha":
        api_url = ai_config.get("matcha_api_url") or settings.MATCHA_API_URL
        if not api_url:
            raise HTTPException(status_code=500, detail="MATCHA_API_URL not configured")
        provider_kwargs["api_url"] = api_url
        provider_kwargs["model"] = ai_config.get("matcha_model", settings.MATCHA_MODEL)

    provider_instance = provider_registry.create_provider(default_provider, **provider_kwargs)
    if not provider_instance:
        raise HTTPException(status_code=500, detail=f"Unknown AI Provider: {default_provider}")

    return AIService(provider=provider_instance, mcp_client=mcp_client)

def require_admin(request: Request, current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin role.

    If the request was authenticated with an API key, the key must also carry
    the 'admin' (or 'full') scope — an admin-owned key scoped to 'query' cannot
    reach admin endpoints.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    api_key = getattr(request.state, "api_key", None)
    if api_key is not None:
        from app.services.api_key_service import APIKeyService, KEY_PREFIX
        if not APIKeyService.has_scope(api_key, "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key lacks 'admin' scope"
            )

    return current_user

def require_viewer(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require viewer role or higher
    """
    if current_user.role not in ["admin", "viewer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer privileges required"
        )
    return current_user

from app.services.schema_service import SchemaService
from app.db.session import config_engine, business_engine

def get_schema_service() -> SchemaService:
    """
    Dependency to get SchemaService.
    - config_engine: for config tables (schema_contexts, mappings, rules)
    - business_engine: for inspecting business views/tables
    """
    return SchemaService(db_engine=config_engine, business_engine=business_engine)
