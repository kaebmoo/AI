"""
Phase Completion Tests
=======================
Tests to verify all phase features are properly implemented
"""

import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestPhase1Infrastructure:
    """Test Phase 1: Infrastructure & Core Setup"""

    def test_fastapi_app_exists(self):
        """Test FastAPI app is properly configured"""
        from app.main import app
        assert app is not None
        assert app.title.startswith("NT AI Assistant")

    def test_config_exists(self):
        """Test configuration is properly set up"""
        from app.config import settings
        assert settings is not None
        assert hasattr(settings, 'DATABASE_URL')
        assert hasattr(settings, 'REDIS_URL')
        assert hasattr(settings, 'AI_PROVIDER')

    def test_rate_limiter_attached(self):
        """Test rate limiter is attached to app"""
        from app.main import app
        assert hasattr(app.state, 'limiter')

    def test_rate_limiter_is_slowapi(self):
        """Test rate limiter is slowapi instance"""
        from app.main import app
        limiter_type = str(type(app.state.limiter))
        assert "slowapi" in limiter_type.lower()

    def test_celery_configured(self):
        """Test Celery is properly configured"""
        from app.celery import celery_app
        assert celery_app is not None
        assert celery_app.conf.broker_url is not None

    def test_cache_service_exists(self):
        """Test cache service can be instantiated"""
        from app.services.cache_service import CacheService
        # Use mock URL to avoid needing real Redis
        cache = CacheService(redis_url="redis://mock:6379/0")
        assert cache is not None

    def test_dockerfile_exists(self):
        """Test Dockerfile exists"""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dockerfile_path = os.path.join(project_root, "docker", "Dockerfile")
        assert os.path.exists(dockerfile_path)

    def test_docker_compose_exists(self):
        """Test docker-compose.yml exists"""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        compose_path = os.path.join(project_root, "docker", "docker-compose.yml")
        assert os.path.exists(compose_path)

    def test_logging_module_exists(self):
        """Test logging module is properly set up"""
        from app.core.logging import logging
        assert logging is not None

    def test_middleware_exists(self):
        """Test middleware is properly set up"""
        from app.core.middleware import RequestIDMiddleware
        assert RequestIDMiddleware is not None


class TestPhase2Authentication:
    """Test Phase 2: Authentication & Security"""

    def test_auth_endpoints_registered(self):
        """Test auth endpoints are registered"""
        from app.main import app
        routes = [route.path for route in app.routes]

        assert "/api/v1/auth/login" in routes
        assert "/api/v1/auth/verify" in routes

    def test_otp_service_exists(self):
        """Test OTP service exists"""
        from app.services.otp_service import OTPService
        assert OTPService is not None

    def test_auth_service_exists(self):
        """Test auth service exists"""
        from app.services.auth_service import AuthService
        assert AuthService is not None

    def test_email_service_exists(self):
        """Test email service exists"""
        from app.services.email_service import EmailService
        assert EmailService is not None

    def test_allowed_domains_configured(self):
        """Test allowed email domains are configured"""
        from app.config import settings
        assert settings.ALLOWED_EMAIL_DOMAINS is not None
        assert len(settings.ALLOWED_EMAIL_DOMAINS) > 0

    def test_session_model_exists(self):
        """Test session model exists"""
        from app.models.session import UserSession
        assert UserSession is not None

    def test_user_model_exists(self):
        """Test user model exists"""
        from app.models.user import User
        assert User is not None


class TestPhase3CoreFeatures:
    """Test Phase 3: Core Features - Chat & Query"""

    def test_chat_endpoints_registered(self):
        """Test chat endpoints are registered"""
        from app.main import app
        routes = [route.path for route in app.routes]

        assert "/api/v1/chat/" in routes
        assert "/api/v1/chat/history" in routes

    def test_ai_service_exists(self):
        """Test AI service exists"""
        from app.services.ai_service import AIService
        assert AIService is not None

    def test_claude_provider_exists(self):
        """Test Claude provider exists"""
        from app.services.ai_service import ClaudeProvider
        assert ClaudeProvider is not None

    def test_gemini_provider_exists(self):
        """Test Gemini provider exists"""
        from app.services.ai_service import GeminiProvider
        assert GeminiProvider is not None

    def test_factory_functions_exist(self):
        """Test factory functions exist"""
        from app.services.ai_service import create_claude_service, create_gemini_service
        assert create_claude_service is not None
        assert create_gemini_service is not None

    def test_database_service_exists(self):
        """Test database service exists"""
        from app.services.database_service import DatabaseService
        assert DatabaseService is not None

    def test_schema_service_exists(self):
        """Test schema service exists"""
        from app.services.schema_service import SchemaService
        assert SchemaService is not None

    def test_chat_model_exists(self):
        """Test chat history model exists"""
        from app.models.chat import ChatHistory
        assert ChatHistory is not None


class TestPhase35FeedbackLoop:
    """Test Phase 3.5: Feedback Loop & Enhanced Logging"""

    def test_feedback_endpoints_registered(self):
        """Test feedback endpoints are registered"""
        from app.main import app
        routes = [route.path for route in app.routes]

        feedback_routes = [r for r in routes if "/feedback" in r]
        assert len(feedback_routes) > 0

    def test_feedback_submit_endpoint(self):
        """Test feedback submit endpoint exists"""
        from app.main import app
        routes = [route.path for route in app.routes]
        assert any("/feedback/{chat_id}" in r for r in routes)

    def test_feedback_pending_endpoint(self):
        """Test feedback pending endpoint exists"""
        from app.main import app
        routes = [route.path for route in app.routes]
        assert any("/feedback/pending" in r or "/pending" in r for r in routes)

    def test_feedback_service_exists(self):
        """Test feedback service exists"""
        from app.services.feedback_service import FeedbackService
        assert FeedbackService is not None

    def test_feedback_models_exist(self):
        """Test feedback models exist"""
        from app.models.feedback_models import (
            UserFeedback,
            FeedbackRating,
            FeedbackCategory,
            GoldenExample
        )
        assert UserFeedback is not None
        assert FeedbackRating is not None
        assert FeedbackCategory is not None
        assert GoldenExample is not None

    def test_feedback_rating_values(self):
        """Test feedback rating has expected values"""
        from app.models.feedback_models import FeedbackRating
        assert hasattr(FeedbackRating, 'THUMBS_UP')
        assert hasattr(FeedbackRating, 'THUMBS_DOWN')

    def test_pii_redaction_exists(self):
        """Test PII redaction formatter exists"""
        from app.core.logging import PIIRedactingFormatter
        assert PIIRedactingFormatter is not None

    def test_request_id_context_exists(self):
        """Test request ID context variable exists"""
        from app.core.logging import request_id_var
        assert request_id_var is not None


class TestEmailWorker:
    """Test Email Worker (Celery Task)"""

    def test_email_worker_exists(self):
        """Test email worker exists"""
        from app.workers.email_worker import send_otp_email
        assert send_otp_email is not None

    def test_email_worker_is_celery_task(self):
        """Test email worker is a Celery task"""
        from app.workers.email_worker import send_otp_email
        # Celery tasks have a 'delay' method
        assert hasattr(send_otp_email, 'delay')


class TestAPIEndpointsSummary:
    """Summary test for all API endpoints"""

    def test_all_required_endpoints_exist(self):
        """Test all required endpoints are registered"""
        from app.main import app
        routes = [route.path for route in app.routes]

        required_endpoints = [
            "/api/v1/auth/login",
            "/api/v1/auth/verify",
            "/api/v1/chat/",
            "/api/v1/chat/history",
        ]

        for endpoint in required_endpoints:
            assert endpoint in routes, f"Missing endpoint: {endpoint}"

        # Feedback endpoints (may have different path format)
        feedback_routes = [r for r in routes if "/feedback" in r]
        assert len(feedback_routes) >= 2, "Missing feedback endpoints"
