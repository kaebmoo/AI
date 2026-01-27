"""
Unit Tests for Auth Service
============================
"""

import pytest
from datetime import datetime, timedelta

from app.services.auth_service import AuthService
from app.models.user import User
from app.models.session import UserSession


class TestAuthService:
    """Test cases for AuthService"""

    def test_get_or_create_user_new(self, db_session):
        """Test creating a new user"""
        service = AuthService(db_session)

        user = service.get_or_create_user("newuser@example.com")

        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.display_name == "Newuser"
        assert user.is_active is True
        assert user.role == "user"

    def test_get_or_create_user_existing(self, db_session, test_user):
        """Test getting existing user"""
        service = AuthService(db_session)

        user = service.get_or_create_user(test_user.email)

        assert user.id == test_user.id
        assert user.email == test_user.email

    def test_create_session(self, db_session, test_user):
        """Test creating a new session"""
        service = AuthService(db_session)

        session = service.create_session(
            user=test_user,
            platform="web",
            ip_address="127.0.0.1",
            user_agent="pytest"
        )

        assert session is not None
        assert session.user_id == test_user.id
        assert session.platform == "web"
        assert len(session.session_token) > 20
        assert session.expires_at > datetime.utcnow()

    def test_validate_session_valid(self, db_session, test_session):
        """Test validating a valid session"""
        service = AuthService(db_session)

        session = service.validate_session(test_session.session_token)

        assert session is not None
        assert session.id == test_session.id

    def test_validate_session_invalid_token(self, db_session):
        """Test validating with invalid token"""
        service = AuthService(db_session)

        session = service.validate_session("invalid_token_12345")

        assert session is None

    def test_validate_session_expired(self, db_session, test_user):
        """Test validating an expired session"""
        # Create expired session
        expired_session = UserSession(
            user_id=test_user.id,
            session_token="expired_token_12345",
            platform="web",
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired
            last_activity=datetime.utcnow() - timedelta(hours=2)
        )
        db_session.add(expired_session)
        db_session.commit()

        service = AuthService(db_session)

        session = service.validate_session("expired_token_12345")

        assert session is None

    def test_validate_session_refreshes_expiry(self, db_session, test_user):
        """Test that session expiry is refreshed when close to expiry"""
        from app.config import settings

        # Create session close to expiry
        close_to_expiry = UserSession(
            user_id=test_user.id,
            session_token="close_to_expiry_token",
            platform="web",
            expires_at=datetime.utcnow() + timedelta(minutes=30),  # Close to expiry
            last_activity=datetime.utcnow()
        )
        db_session.add(close_to_expiry)
        db_session.commit()

        original_expiry = close_to_expiry.expires_at

        service = AuthService(db_session)
        session = service.validate_session("close_to_expiry_token")

        # Session should be refreshed (new expiry time)
        assert session is not None
        assert session.expires_at > original_expiry

    def test_validate_telegram_session(self, db_session, test_user):
        """Test validating Telegram session by chat_id"""
        # Create telegram session
        telegram_session = UserSession(
            user_id=test_user.id,
            session_token="telegram_token_12345",
            platform="telegram",
            telegram_chat_id=123456789,
            expires_at=datetime.utcnow() + timedelta(hours=24),
            last_activity=datetime.utcnow()
        )
        db_session.add(telegram_session)
        db_session.commit()

        service = AuthService(db_session)

        session = service.validate_telegram_session(123456789)

        assert session is not None
        assert session.telegram_chat_id == 123456789

    def test_logout(self, db_session, test_session):
        """Test logout invalidates session"""
        service = AuthService(db_session)

        service.logout(test_session.session_token)

        # Session should now be expired
        db_session.refresh(test_session)
        assert test_session.expires_at <= datetime.utcnow()

        # Validate should fail
        session = service.validate_session(test_session.session_token)
        assert session is None
