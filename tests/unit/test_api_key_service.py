"""
Unit Tests for API Key Service (Plan 4B)
==========================================
Tests for API key creation, validation, revocation, and usage tracking.
"""

import pytest
import sqlite3
from datetime import datetime, timedelta

from app.services.api_key_service import APIKeyService, KEY_PREFIX


@pytest.fixture
def api_key_db(tmp_path):
    """Create temp DB with api_keys and api_key_usage tables."""
    db_path = str(tmp_path / "api_key_test.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT NOT NULL,
            name TEXT DEFAULT '',
            user_id INTEGER NOT NULL,
            scopes TEXT DEFAULT 'query',
            rate_limit_per_minute INTEGER DEFAULT 30,
            rate_limit_per_day INTEGER DEFAULT 1000,
            is_active INTEGER DEFAULT 1,
            expires_at TIMESTAMP,
            last_used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE api_key_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            request_count INTEGER DEFAULT 0,
            token_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(api_key_id, date)
        )
    """)

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def api_key_session(api_key_db):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession
    engine = create_engine(f"sqlite:///{api_key_db}")
    session = SASession(engine)
    yield session
    session.close()


class TestAPIKeyService:

    def test_create_api_key(self, api_key_session):
        """Creating a key returns raw key with ntai_ prefix and stores hash."""
        service = APIKeyService(api_key_session)
        raw_key, api_key = service.create_key(user_id=1, name="Test Key")

        assert raw_key.startswith("ntai_")
        assert len(raw_key) > 20
        assert api_key.id is not None
        assert api_key.name == "Test Key"
        assert api_key.user_id == 1
        assert api_key.is_active is True

    def test_validate_api_key_success(self, api_key_session):
        """Valid key returns the APIKey model."""
        service = APIKeyService(api_key_session)
        raw_key, _ = service.create_key(user_id=1, name="Valid Key")

        result = service.validate_key(raw_key)
        assert result is not None
        assert result.name == "Valid Key"

    def test_validate_api_key_wrong(self, api_key_session):
        """Invalid key returns None."""
        service = APIKeyService(api_key_session)
        result = service.validate_key(KEY_PREFIX + "invalid_key_that_doesnt_exist")
        assert result is None

    def test_validate_api_key_no_prefix(self, api_key_session):
        """Key without ntai_ prefix returns None."""
        service = APIKeyService(api_key_session)
        result = service.validate_key("some_random_key")
        assert result is None

    def test_validate_api_key_revoked(self, api_key_session):
        """Revoked key returns None."""
        service = APIKeyService(api_key_session)
        raw_key, api_key = service.create_key(user_id=1, name="To Revoke")
        service.revoke_key(api_key.id)

        result = service.validate_key(raw_key)
        assert result is None

    def test_revoke_api_key(self, api_key_session):
        """Revoking sets is_active to False."""
        service = APIKeyService(api_key_session)
        _, api_key = service.create_key(user_id=1, name="Revokable")

        success = service.revoke_key(api_key.id, user_id=1)
        assert success is True

        # Verify in DB
        from app.models.api_key import APIKey
        key = api_key_session.query(APIKey).filter(APIKey.id == api_key.id).first()
        assert key.is_active is False

    def test_track_usage(self, api_key_session):
        """Usage tracking increments request count."""
        service = APIKeyService(api_key_session)
        _, api_key = service.create_key(user_id=1, name="Usage Test")

        service.track_usage(api_key.id, tokens=100)
        service.track_usage(api_key.id, tokens=50)

        stats = service.get_usage_stats(api_key.id)
        assert stats["total_requests"] == 2
        assert stats["total_tokens"] == 150

    def test_rate_limit_per_day(self, api_key_session):
        """Key exceeding daily limit is rejected."""
        service = APIKeyService(api_key_session)
        raw_key, api_key = service.create_key(
            user_id=1, name="Rate Limited", rate_limit_per_day=2
        )

        # Use up the daily limit
        service.track_usage(api_key.id)
        service.track_usage(api_key.id)

        # Third call should fail validation
        result = service.validate_key(raw_key)
        assert result is None

    def test_list_keys(self, api_key_session):
        """List keys returns all keys for user."""
        service = APIKeyService(api_key_session)
        service.create_key(user_id=1, name="Key 1")
        service.create_key(user_id=1, name="Key 2")
        service.create_key(user_id=2, name="Other User")

        keys = service.list_keys(user_id=1)
        assert len(keys) == 2

    def test_has_scope(self, api_key_session):
        """Scope checking works."""
        service = APIKeyService(api_key_session)
        _, api_key = service.create_key(user_id=1, name="Scoped", scopes="query")

        assert service.has_scope(api_key, "query") is True
        assert service.has_scope(api_key, "admin") is False

        _, full_key = service.create_key(user_id=1, name="Full", scopes="full")
        assert service.has_scope(full_key, "admin") is True
        assert service.has_scope(full_key, "query") is True
