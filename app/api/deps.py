from datetime import datetime
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from app.db.session import SessionLocal
from app.services.auth_service import AuthService
from app.models.user import User
from app.config import settings
from app.services.ai_service import AIService, create_gemini_service, create_claude_service, create_matcha_service
from app.services.mcp_client import MCPClientService

# Header scheme for session token
header_scheme = APIKeyHeader(name="X-Session-Token", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_current_user(
    request: Request,
    token: Optional[str] = Depends(header_scheme),
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from session token.
    Token can be passed in X-Session-Token header OR Authorization: Bearer header.
    """
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

def get_ai_service(
    db: Session = Depends(get_db),
    mcp_client: MCPClientService = Depends(get_mcp_client)
) -> AIService:
    """
    Dependency to get initialized AIService based on config.
    Prioritizes DB config > Env var > Default
    """
    config_service = AdminConfigService(db)
    ai_config = config_service.get_ai_config()
    default_provider = ai_config.get("default_provider", "matcha")
    
    # Get API key using service (handles fallback)
    api_key = config_service.get_provider_api_key(default_provider)
    
    if default_provider == "gemini":
        if not api_key:
             raise HTTPException(status_code=500, detail="GOOGLE_AI_API_KEY not configured")
        return create_gemini_service(
            api_key=api_key,
            mcp_client=mcp_client,
            model=ai_config.get("gemini_model", settings.GEMINI_MODEL)
        )
    elif default_provider == "claude":
        if not api_key:
             raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        return create_claude_service(
            api_key=api_key,
            mcp_client=mcp_client,
            model=ai_config.get("claude_model", settings.CLAUDE_MODEL)
        )
    elif default_provider == "matcha":
        if not api_key:
             raise HTTPException(status_code=500, detail="MATCHA_AI_API_KEY not configured")
        
        # Matcha specific: Get URL from config or settings fallback
        api_url = ai_config.get("matcha_api_url") or settings.MATCHA_API_URL
        if not api_url:
             raise HTTPException(status_code=500, detail="MATCHA_API_URL not configured")
             
        return create_matcha_service(
            api_key=api_key,
            api_url=api_url,
            mcp_client=mcp_client,
            model=ai_config.get("matcha_model", settings.MATCHA_MODEL)
        )
    else:
        raise HTTPException(status_code=500, detail=f"Unknown AI Provider: {default_provider}")

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require admin role
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
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
from app.db.session import engine

def get_schema_service() -> SchemaService:
    """
    Dependency to get SchemaService with global engine
    """
    return SchemaService(db_engine=engine)
