"""
Unit Tests for OTP Service
===========================
"""

import pytest
import hashlib
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.services.otp_service import OTPService
from app.services.email_service import EmailService
from app.models.otp import OTPRequest
from app.core.exceptions import (
    InvalidDomainError,
    OTPExpiredError,
    TooManyAttemptsError,
    CooldownError
)


class TestOTPService:
    """Test cases for OTPService"""

    def test_validate_email_domain_allowed(self, db_session):
        """Test email validation with allowed domain"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        # example.com is in allowed domains (set in conftest.py)
        assert service.validate_email_domain("user@example.com") is True
        assert service.validate_email_domain("user@test.com") is True

    def test_validate_email_domain_not_allowed(self, db_session):
        """Test email validation with disallowed domain"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        assert service.validate_email_domain("user@gmail.com") is False
        assert service.validate_email_domain("user@yahoo.com") is False

    def test_generate_otp_length(self, db_session):
        """Test OTP generation returns correct length"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        otp = service.generate_otp()
        assert len(otp) == 6  # Default OTP_LENGTH
        assert otp.isdigit()

    def test_hash_otp(self, db_session):
        """Test OTP hashing"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        otp = "123456"
        hashed = service.hash_otp(otp)

        # Should be SHA256 hash
        expected = hashlib.sha256(otp.encode()).hexdigest()
        assert hashed == expected

    def test_verify_otp_success(self, db_session, test_otp_request):
        """Test successful OTP verification"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        success, message = service.verify_otp(
            email="test@example.com",
            otp="123456",  # Matches hash in fixture
            platform="web"
        )

        assert success is True
        assert "verified" in message.lower()

    def test_verify_otp_invalid(self, db_session, test_otp_request):
        """Test OTP verification with wrong code"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        success, message = service.verify_otp(
            email="test@example.com",
            otp="000000",  # Wrong OTP
            platform="web"
        )

        assert success is False
        assert "invalid" in message.lower()

    def test_verify_otp_expired(self, db_session):
        """Test OTP verification with expired code"""
        # Create expired OTP
        otp_hash = hashlib.sha256("123456".encode()).hexdigest()
        expired_otp = OTPRequest(
            email="test@example.com",
            otp_code=otp_hash,
            platform="web",
            expires_at=datetime.utcnow() - timedelta(minutes=5),  # Expired
            created_at=datetime.utcnow() - timedelta(minutes=15),
            attempts=0
        )
        db_session.add(expired_otp)
        db_session.commit()

        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        with pytest.raises(OTPExpiredError):
            service.verify_otp(
                email="test@example.com",
                otp="123456",
                platform="web"
            )

    def test_verify_otp_too_many_attempts(self, db_session):
        """Test OTP verification with too many attempts"""
        otp_hash = hashlib.sha256("123456".encode()).hexdigest()
        otp_request = OTPRequest(
            email="test@example.com",
            otp_code=otp_hash,
            platform="web",
            expires_at=datetime.utcnow() + timedelta(minutes=10),
            created_at=datetime.utcnow(),
            attempts=3  # Max attempts reached
        )
        db_session.add(otp_request)
        db_session.commit()

        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        with pytest.raises(TooManyAttemptsError):
            service.verify_otp(
                email="test@example.com",
                otp="123456",
                platform="web"
            )

    @pytest.mark.asyncio
    async def test_request_otp_invalid_domain(self, db_session):
        """Test OTP request with invalid domain"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        with pytest.raises(InvalidDomainError):
            await service.request_otp(
                email="user@invalid-domain.com",
                platform="web"
            )

    @pytest.mark.asyncio
    async def test_request_otp_cooldown(self, db_session, test_otp_request):
        """Test OTP request during cooldown period"""
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)

        # test_otp_request was just created, so cooldown should apply
        with pytest.raises(CooldownError):
            await service.request_otp(
                email="test@example.com",
                platform="web"
            )


class TestExposeOtpGuard:
    """Fail-closed guard: OTP is only ever returned for explicit dev/test envs."""

    @pytest.mark.parametrize("env", ["development", "test", "local", "DEVELOPMENT"])
    def test_exposed_for_dev_envs(self, env):
        from app.config import settings
        with patch.object(settings, "ENVIRONMENT", env):
            assert settings.expose_otp_in_response() is True

    @pytest.mark.parametrize(
        "env", ["production", "staging", "qa", "prod", "", "typo", "PRODUCTION"]
    )
    def test_hidden_for_everything_else(self, env):
        from app.config import settings
        with patch.object(settings, "ENVIRONMENT", env):
            assert settings.expose_otp_in_response() is False

    def test_request_otp_response_hides_otp_in_production(self, db_session):
        from app.config import settings
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)
        with patch.object(settings, "ENVIRONMENT", "production"), \
                patch("app.services.otp_service.send_otp_email"):
            success, message = service.request_otp(
                email="prod-user@example.com", platform="web"
            )
        assert success is True
        assert "DEV:" not in message

    def test_request_otp_response_shows_otp_in_dev(self, db_session):
        from app.config import settings
        email_service = Mock(spec=EmailService)
        service = OTPService(db_session, email_service)
        with patch.object(settings, "ENVIRONMENT", "development"), \
                patch("app.services.otp_service.send_otp_email"):
            success, message = service.request_otp(
                email="dev-user@example.com", platform="web"
            )
        assert success is True
        assert "DEV:" in message
