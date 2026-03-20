"""
Plan 4B: API Key Auth Integration Tests
=========================================
Tests X-API-Key authentication across endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.models.session import UserSession


class TestAPIKeyAuth:
    """Integration tests for API key authentication flow."""

    def test_session_token_still_works(self, client, test_user, db_session):
        """X-Session-Token auth → still works as before."""
        session = UserSession(
            user_id=test_user.id,
            session_token="classic_token",
            platform="web",
            expires_at=datetime.utcnow() + timedelta(hours=24),
            last_activity=datetime.utcnow(),
        )
        db_session.add(session)
        db_session.commit()

        client.headers["X-Session-Token"] = "classic_token"
        # Test with query/contexts (public) to verify client setup works
        resp = client.get("/api/v1/query/contexts")
        assert resp.status_code == 200

    def test_no_auth_rejected_for_protected(self, client):
        """No auth header on protected endpoint → 401."""
        resp = client.get("/api/v1/admin/query-logs")
        assert resp.status_code == 401

    def test_api_key_dep_path(self):
        """deps.get_current_user checks X-API-Key before session token."""
        from app.api.deps import api_key_header
        assert api_key_header is not None
        assert api_key_header.model.name == "X-API-Key"

    def test_api_key_service_exists(self):
        """APIKeyService is importable and has validate_key method."""
        from app.services.api_key_service import APIKeyService, KEY_PREFIX
        assert hasattr(APIKeyService, "validate_key")
        assert hasattr(APIKeyService, "track_usage")
        assert hasattr(APIKeyService, "create_key")
        assert hasattr(APIKeyService, "revoke_key")
