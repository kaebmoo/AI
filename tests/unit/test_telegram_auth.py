"""
Plan 4: Telegram Auth Tests
=============================
Tests user registration via email OTP and session lookup.
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from datetime import datetime, timedelta

from app.telegram.auth import TelegramAuth
from app.models.user import User
from app.models.session import UserSession


class TestGetUserByChatId:
    """TelegramAuth.get_user_by_chat_id()."""

    def test_user_found(self, db_session, test_user):
        """Chat ID with active session → returns user."""
        # Create telegram session for test_user
        session = UserSession(
            user_id=test_user.id,
            session_token="tg_token_abc",
            platform="telegram",
            telegram_chat_id=12345,
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()

        auth = TelegramAuth()
        user = auth.get_user_by_chat_id(12345, db_session)
        assert user is not None
        assert user.id == test_user.id

    def test_user_not_found(self, db_session):
        """Chat ID with no session → returns None."""
        auth = TelegramAuth()
        user = auth.get_user_by_chat_id(99999, db_session)
        assert user is None


class TestStartRegistration:
    """TelegramAuth.start_registration()."""

    def test_email_not_found(self, db_session):
        """Email not in system → error message."""
        auth = TelegramAuth()
        result = auth.start_registration(12345, "nobody@example.com", db_session)
        assert result["success"] is False
        assert "ไม่พบ" in result["message"]

    def test_email_found_sends_otp(self, db_session, test_user):
        """Email found → OTP sent."""
        auth = TelegramAuth()

        with patch("app.telegram.auth.OTPService") as MockOTP:
            instance = MockOTP.return_value
            instance.request_otp.return_value = (True, "OTP sent")

            with patch("app.telegram.auth.EmailService"):
                result = auth.start_registration(12345, "test@example.com", db_session)

            assert result["success"] is True
            assert "OTP" in result["message"]

    def test_already_registered(self, db_session, test_user):
        """Already registered chat_id → error."""
        session = UserSession(
            user_id=test_user.id,
            session_token="existing_tg",
            platform="telegram",
            telegram_chat_id=12345,
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()

        auth = TelegramAuth()
        result = auth.start_registration(12345, "test@example.com", db_session)
        assert result["success"] is False
        assert "ลงทะเบียนแล้ว" in result["message"]


class TestVerifyOTP:
    """TelegramAuth.verify_otp()."""

    def test_no_pending_otp(self, db_session):
        """No OTP request for chat_id → error."""
        auth = TelegramAuth()
        result = auth.verify_otp(99999, "123456", db_session)
        assert result["success"] is False
        assert "ไม่พบ" in result["message"]

    def test_otp_success(self, db_session, test_user):
        """Correct OTP → session created, user linked."""
        from app.models.otp import OTPRequest

        otp_req = OTPRequest(
            email="test@example.com",
            otp_code="hashed",
            platform="telegram",
            telegram_chat_id=55555,
            expires_at=datetime.utcnow() + timedelta(minutes=10),
            created_at=datetime.utcnow(),
            attempts=0,
        )
        db_session.add(otp_req)
        db_session.commit()

        auth = TelegramAuth()

        with patch("app.telegram.auth.OTPService") as MockOTP:
            instance = MockOTP.return_value
            instance.verify_otp.return_value = (True, "Verified")

            with patch("app.telegram.auth.EmailService"):
                result = auth.verify_otp(55555, "123456", db_session)

        assert result["success"] is True
        assert "สำเร็จ" in result["message"]


class TestIsAdmin:
    """TelegramAuth.is_admin()."""

    def test_admin_user_returns_true(self, db_session, admin_user):
        """Admin user's chat_id → True."""
        session = UserSession(
            user_id=admin_user.id,
            session_token="admin_tg_token",
            platform="telegram",
            telegram_chat_id=77777,
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()

        auth = TelegramAuth()
        assert auth.is_admin(77777, db_session) is True

    def test_regular_user_returns_false(self, db_session, test_user):
        """Regular user's chat_id → False."""
        session = UserSession(
            user_id=test_user.id,
            session_token="user_tg_token",
            platform="telegram",
            telegram_chat_id=88888,
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()

        auth = TelegramAuth()
        assert auth.is_admin(88888, db_session) is False

    def test_unknown_chat_returns_false(self, db_session):
        """Unknown chat_id → False."""
        auth = TelegramAuth()
        assert auth.is_admin(11111, db_session) is False
