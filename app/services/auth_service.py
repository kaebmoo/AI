import secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.session import UserSession
from app.config import settings
# from app.core.security import create_access_token # Not using JWT for now, using Session Token as per plan

class AuthService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create_user(self, email: str) -> User:
        """Get existing user or create new one"""
        user = self.db.query(User).filter(User.email == email).first()
        
        if not user:
            # Extract name from email
            name_part = email.split("@")[0]
            display_name = name_part.replace(".", " ").title()
            
            user = User(
                email=email,
                display_name=display_name,
                is_active=True,
                role="user"
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        
        return user
    
    def create_session(
        self,
        user: User,
        platform: str,
        telegram_chat_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UserSession:
        """Create new user session"""
        session_token = secrets.token_urlsafe(32)
        
        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            platform=platform,
            telegram_chat_id=telegram_chat_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRY_HOURS),
            last_activity=datetime.utcnow()
        )
        self.db.add(session)
        self.db.commit()
        
        return session
    
    def validate_session(self, session_token: str) -> Optional[UserSession]:
        """Validate and refresh session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token,
            UserSession.expires_at > datetime.utcnow()
        ).first()
        
        if session:
            # Update last activity
            session.last_activity = datetime.utcnow()
            
            # Refresh token if close to expiry
            hours_until_expiry = (session.expires_at - datetime.utcnow()).total_seconds() / 3600
            if hours_until_expiry < settings.SESSION_REFRESH_THRESHOLD_HOURS:
                session.expires_at = datetime.utcnow() + timedelta(hours=settings.SESSION_EXPIRY_HOURS)
            
            self.db.commit()
        
        return session
    
    def validate_telegram_session(self, chat_id: int) -> Optional[UserSession]:
        """Validate Telegram session by chat_id"""
        return self.db.query(UserSession).filter(
            UserSession.telegram_chat_id == chat_id,
            UserSession.platform == "telegram",
            UserSession.expires_at > datetime.utcnow()
        ).first()
    
    def logout(self, session_token: str):
        """Invalidate session"""
        session = self.db.query(UserSession).filter(
            UserSession.session_token == session_token
        ).first()
        
        if session:
            session.expires_at = datetime.utcnow()
            self.db.commit()
