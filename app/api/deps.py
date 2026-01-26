from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request, Header
from sqlalchemy.orm import Session
from fastapi.security import APIKeyHeader

from app.db.session import SessionLocal
from app.services.auth_service import AuthService
from app.models.user import User

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
