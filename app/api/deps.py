from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from fastapi.security import APIKeyHeader

from app.db.session import SessionLocal
from app.services.auth_service import AuthService
from app.models.user import User
from app.config import settings
from app.services.ai_service import AIService, create_gemini_service, create_claude_service, create_matcha_service

# Header scheme for session token
header_scheme = APIKeyHeader(name="X-Session-Token", auto_error=False)

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_current_user(
    request: Request,
    token: Optional[str] = Depends(header_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from session token.
    Token can be passed in X-Session-Token header.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    
    auth_service = AuthService(db)
    session = auth_service.validate_session(token)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
        
    return session.user

from app.services.prompt_manager import PromptManager

def get_ai_service(db: Session = Depends(get_db)) -> AIService:
    """
    Dependency to get initialized AIService based on config.
    """
    # Parse DB path from connection string (assuming sqlite:///./path)
    if "sqlite" in settings.DATABASE_URL:
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    else:
        # For Postgres, we might need a different approach or connection string
        # For now, this service expects a path for SQLiteSchema inspection
        db_path = "nt_revenue.sqlite" 

    prompt_manager = PromptManager(db)

    if settings.AI_PROVIDER == "gemini":
        if not settings.GOOGLE_AI_API_KEY:
             raise HTTPException(status_code=500, detail="GOOGLE_AI_API_KEY not configured")
        return create_gemini_service(
            settings.GOOGLE_AI_API_KEY, 
            db_path=db_path,
            model=settings.GEMINI_MODEL,
            prompt_manager=prompt_manager
        )
    elif settings.AI_PROVIDER == "claude":
        if not settings.ANTHROPIC_API_KEY:
             raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        return create_claude_service(
            settings.ANTHROPIC_API_KEY, 
            db_path=db_path,
            model=settings.CLAUDE_MODEL,
            prompt_manager=prompt_manager
        )
    elif settings.AI_PROVIDER == "matcha":
        if not settings.MATCHA_AI_API_KEY:
             raise HTTPException(status_code=500, detail="MATCHA_AI_API_KEY not configured")
        if not settings.MATCHA_API_URL:
             raise HTTPException(status_code=500, detail="MATCHA_API_URL not configured")
        return create_matcha_service(
            api_key=settings.MATCHA_AI_API_KEY,
            api_url=settings.MATCHA_API_URL,
            db_path=db_path,
            model=settings.MATCHA_MODEL,
            prompt_manager=prompt_manager
        )
    else:
        raise HTTPException(status_code=500, detail=f"Unknown AI Provider: {settings.AI_PROVIDER}")

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

def get_schema_service(db: Session = Depends(get_db)) -> SchemaService:
    """
    Dependency to get SchemaService
    """
    return SchemaService(db)
