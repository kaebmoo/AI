"""
NT AI Assistant - Test Configuration
==========================================
Pytest fixtures and configuration for testing
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from typing import Generator

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.base_class import Base
from app.models.user import User
from app.models.session import UserSession
from app.models.otp import OTPRequest
from app.models.chat import ChatHistory
from app.models.feedback_models import UserFeedback, GoldenExample
from app.models.conversation import Conversation  # Required for FK resolution
from app.config import settings


# ============================================================
# Database Fixtures
# ============================================================

@pytest.fixture(scope="function")
def test_engine():
    """Create in-memory SQLite engine for testing with shared connection"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool  # Share single connection across all uses
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create database session for testing"""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ============================================================
# User Fixtures
# ============================================================

@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user"""
    user = User(
        email="test@example.com",
        display_name="Test User",
        is_active=True,
        role="user"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create an admin user"""
    user = User(
        email="admin@example.com",
        display_name="Admin User",
        is_active=True,
        role="admin"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_session(db_session: Session, test_user: User) -> UserSession:
    """Create a test session"""
    session = UserSession(
        user_id=test_user.id,
        session_token="test_token_12345",
        platform="web",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        last_activity=datetime.utcnow()
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


# ============================================================
# OTP Fixtures
# ============================================================

@pytest.fixture
def test_otp_request(db_session: Session) -> OTPRequest:
    """Create a test OTP request"""
    import hashlib
    otp_hash = hashlib.sha256("123456".encode()).hexdigest()

    otp_request = OTPRequest(
        email="test@example.com",
        otp_code=otp_hash,
        platform="web",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        created_at=datetime.utcnow(),
        attempts=0
    )
    db_session.add(otp_request)
    db_session.commit()
    db_session.refresh(otp_request)
    return otp_request


# ============================================================
# Chat Fixtures
# ============================================================

@pytest.fixture
def test_chat(db_session: Session, test_user: User) -> ChatHistory:
    """Create a test chat history entry"""
    chat = ChatHistory(
        user_id=test_user.id,
        question="รายได้รวมเดือนมกราคม?",
        generated_sql="SELECT SUM(REVENUE_VALUE) FROM revenue WHERE MONTH=1",
        ai_response="รายได้รวมเดือนมกราคมคือ 150 ล้านบาท",
        tokens_used=100,
        execution_time_ms=500
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    return chat


# ============================================================
# Feedback Fixtures
# ============================================================

@pytest.fixture
def test_feedback(db_session: Session, test_chat: ChatHistory) -> UserFeedback:
    """Create a test feedback"""
    from app.models.feedback_models import FeedbackRating

    feedback = UserFeedback(
        chat_id=test_chat.id,
        rating=FeedbackRating.THUMBS_UP,
        created_at=datetime.utcnow()
    )
    db_session.add(feedback)
    db_session.commit()
    db_session.refresh(feedback)
    return feedback


@pytest.fixture
def test_golden_example(db_session: Session) -> GoldenExample:
    """Create a test golden example"""
    example = GoldenExample(
        question_pattern="รายได้รวมเดือนมกราคม",
        expected_sql="SELECT SUM(REVENUE_VALUE) FROM revenue WHERE MONTH=1",
        category="revenue",
        is_active=True,
    )
    db_session.add(example)
    db_session.commit()
    db_session.refresh(example)
    return example


# ============================================================
# Mock Fixtures
# ============================================================

@pytest.fixture
def mock_email_service():
    """Mock email service"""
    mock = Mock()
    mock.send_otp_email = Mock(return_value=True)
    return mock


@pytest.fixture
def mock_claude_response():
    """Mock Claude API response"""
    return {
        "sql": "SELECT SUM(REVENUE_VALUE) FROM revenue WHERE MONTH=1",
        "explanation": "รายได้รวมเดือนมกราคม",
        "tokens_used": 150,
        "raw_response": "..."
    }


@pytest.fixture
def mock_ai_service(mock_claude_response):
    """Mock AI service"""
    mock = Mock()
    mock.query = Mock(return_value=Mock(
        question="รายได้รวม?",
        sql_query="SELECT SUM(REVENUE_VALUE) FROM revenue",
        data=[{"total": 150000000}],
        explanation="รายได้รวมคือ 150 ล้านบาท",
        tokens_used=100,
        provider="gemini",
        error=None
    ))
    return mock


# ============================================================
# API Client Fixtures
# ============================================================

@pytest.fixture
def client(db_session):
    """Create FastAPI test client with test database"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api import deps

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[deps.get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client, test_session, db_session):
    """Create authenticated test client"""
    # Ensure session is in test database
    db_session.refresh(test_session)
    client.headers["X-Session-Token"] = test_session.session_token
    return client


# ============================================================
# Settings Override
# ============================================================

@pytest.fixture(autouse=True)
def override_settings():
    """Override settings for testing"""
    original_domains = settings.ALLOWED_EMAIL_DOMAINS
    settings.ALLOWED_EMAIL_DOMAINS = ["example.com", "test.com"]
    yield
    settings.ALLOWED_EMAIL_DOMAINS = original_domains
