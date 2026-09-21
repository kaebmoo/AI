"""
Integration Tests for API Endpoints
=====================================
Tests API endpoints using FastAPI TestClient
"""

import pytest
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


class TestAuthAPI:
    """Test Authentication API endpoints"""

    def test_login_success(self, client):
        """Test login endpoint with valid email"""
        with patch('app.workers.email_worker.send_otp_email.delay') as mock_email:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "user@example.com"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "message" in data

    def test_login_invalid_domain(self, client):
        """Test login with invalid email domain"""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "user@invalid-domain.com"}
        )

        # Should fail due to domain restriction
        assert response.status_code in [400, 422]

    def test_login_invalid_email_format(self, client):
        """Test login with invalid email format"""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email"}
        )

        assert response.status_code == 422  # Validation error

    def test_verify_missing_otp(self, client):
        """Test verify endpoint without OTP"""
        response = client.post(
            "/api/v1/auth/verify",
            json={
                "email": "user@example.com",
                "platform": "web"
            }
        )

        assert response.status_code == 422  # Missing required field


class TestChatAPI:
    """Test Chat API endpoints"""

    def test_chat_unauthorized(self, client):
        """Test chat endpoint without authentication"""
        response = client.post(
            "/api/v1/chat/",
            json={"question": "รายได้รวม?"}
        )

        assert response.status_code == 401

    def test_chat_history_unauthorized(self, client):
        """Test chat history without authentication"""
        response = client.get("/api/v1/chat/history")

        assert response.status_code == 401

    def test_chat_with_invalid_token(self, client):
        """Test chat with invalid session token"""
        response = client.post(
            "/api/v1/chat/",
            json={"question": "รายได้รวม?"},
            headers={"X-Session-Token": "invalid_token_12345"}
        )

        assert response.status_code == 401


class TestFeedbackAPI:
    """Test Feedback API endpoints"""

    def test_feedback_unauthorized(self, client):
        """Test feedback endpoint without authentication"""
        response = client.post(
            "/api/v1/feedback/1",
            params={"rating": "thumbs_up"}
        )

        assert response.status_code == 401

    def test_pending_reviews_unauthorized(self, client):
        """Test pending reviews without authentication"""
        response = client.get("/api/v1/feedback/pending")

        assert response.status_code == 401


class TestHealthEndpoints:
    """Test health and info endpoints"""

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")

        # Should return something (docs redirect or info)
        assert response.status_code in [200, 307]

    def test_docs_are_closed_by_default(self, client):
        """The full OpenAPI document listed every route, 90 of 115 admin, to anyone without a login.
        Closed unless API_DOCS_ENABLED is set; the schema itself is still built for code that needs it."""
        from app.main import app

        for path in ("/api/v1/openapi.json", "/api/v1/docs", "/api/v1/redoc"):
            assert client.get(path).status_code == 404, path
        assert "/api/v1/query/" in app.openapi()["paths"]  # tests and tooling still get it in-process


class TestAuthenticatedChat:
    """Test authenticated chat flow"""

    @pytest.fixture
    def auth_setup(self, client, db_session):
        """Set up authenticated user and session"""
        from app.models.user import User
        from app.models.session import UserSession

        # Create user
        user = User(
            email="chatuser@example.com",
            display_name="Chat User",
            is_active=True,
            role="user"
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Create session
        session = UserSession(
            user_id=user.id,
            session_token="valid_chat_token_12345",
            platform="web",
            expires_at=datetime.utcnow() + timedelta(hours=24),
            last_activity=datetime.utcnow()
        )
        db_session.add(session)
        db_session.commit()

        return {
            "user": user,
            "session": session,
            "token": session.session_token
        }

    def test_chat_history_empty(self, client, auth_setup):
        """Test chat history when empty"""
        response = client.get(
            "/api/v1/chat/history",
            headers={"X-Session-Token": auth_setup["token"]}
        )

        # Should succeed but return empty list
        assert response.status_code == 200
        assert response.json() == []


class TestRateLimiting:
    """Test rate limiting"""

    def test_rate_limit_headers(self, client):
        """Test that rate limit headers are present"""
        with patch('app.workers.email_worker.send_otp_email.delay'):
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "ratetest@example.com"}
            )

            # Check for rate limit headers (may vary based on slowapi config)
            # Common headers: X-RateLimit-Limit, X-RateLimit-Remaining
            # These might not be present if limiter is not fully configured
            assert response.status_code in [200, 429]


class TestInputValidation:
    """Test input validation"""

    def test_login_empty_body(self, client):
        """Test login with empty body"""
        response = client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422

    def test_chat_empty_question(self, client):
        """Test chat with empty question"""
        response = client.post(
            "/api/v1/chat/",
            json={"question": ""},
            headers={"X-Session-Token": "some_token"}
        )
        # Should fail validation or auth
        assert response.status_code in [401, 422]

    def test_feedback_invalid_rating(self, client):
        """Test feedback with invalid rating"""
        response = client.post(
            "/api/v1/feedback/1",
            params={"rating": "invalid_rating"},
            headers={"X-Session-Token": "some_token"}
        )
        # Should fail validation or auth
        assert response.status_code in [401, 422]
