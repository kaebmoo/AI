"""
Integration Tests: Context Onboarding API Endpoints
=====================================================
Tests admin API endpoints for context onboarding.
Mocks ContextOnboardingService to avoid needing business DB.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.models.user import User
from app.models.session import UserSession
from app.services.context_onboarding import (
    ConfigBundle,
    InspectionResult,
    ValidationResult,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def admin_client(client, db_session):
    """Create admin-authenticated test client."""
    user = User(
        email="onboard-admin@example.com",
        display_name="Onboard Admin",
        is_active=True,
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    session = UserSession(
        user_id=user.id,
        session_token="admin_onboard_token",
        platform="web",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        last_activity=datetime.utcnow(),
    )
    db_session.add(session)
    db_session.commit()

    client.headers["X-Session-Token"] = session.session_token
    return client


@pytest.fixture
def mock_service():
    """Mock ContextOnboardingService."""
    with patch("app.services.context_onboarding.ContextOnboardingService") as MockCls:
        instance = MagicMock()
        MockCls.return_value = instance

        # list_available_views
        instance.list_available_views.return_value = {
            "unconfigured": [
                {"name": "test_view", "type": "view", "has_config": False, "row_count": 100}
            ],
            "configured": [
                {"name": "revenue", "type": "table", "has_config": True, "row_count": 5000}
            ],
        }

        # inspect
        mock_inspection = MagicMock(spec=InspectionResult)
        mock_inspection.row_count = 100
        mock_inspection.columns = [MagicMock()] * 5
        mock_inspection.detected_structure = "long_table"
        mock_inspection.quality_issues = []
        mock_inspection.to_dict.return_value = {
            "view_name": "test_view",
            "row_count": 100,
            "detected_structure": "long_table",
            "columns": [],
            "cross_column_analyses": [],
            "quality_issues": [],
        }
        instance.inspect.return_value = mock_inspection

        # generate_config
        mock_bundle = ConfigBundle(
            sql_statements=["INSERT INTO schema_contexts VALUES ('test')"],
            summary="Test config",
        )
        instance.generate_config.return_value = mock_bundle

        # apply
        instance.apply.return_value = {"status": "applied", "success": 1, "errors": []}

        # apply_sql_statements
        instance.apply_sql_statements.return_value = {
            "status": "applied", "success": 1, "errors": [],
        }

        # validate
        mock_validation = MagicMock(spec=ValidationResult)
        mock_validation.passed = True
        mock_validation.test_results = []
        mock_validation.issues = []

        async def async_validate(*args, **kwargs):
            return mock_validation
        instance.validate = async_validate

        # analyze (async)
        async def async_analyze(*args, **kwargs):
            return {
                "data_structure": {"type": "long_table"},
                "context": {"name": "test"},
                "business_rules": [{"rule_code": "T1"}],
                "golden_examples": [{"question": "q1"}],
                "semantic_mappings": [{"keyword": "k1"}],
            }
        instance.analyze = async_analyze

        yield instance


# ============================================================
# T7: API Tests
# ============================================================

class TestOnboardingAPI:
    def test_available_views_no_auth(self, client):
        """T7.1: GET available-views without auth returns 401/403."""
        response = client.get("/api/v1/admin/contexts/onboard/available-views")
        assert response.status_code in [401, 403]

    def test_available_views_success(self, admin_client, mock_service):
        """T7.2: GET available-views with admin returns views."""
        with patch("app.api.v1.admin._get_business_db_path", return_value="/tmp/test.db"):
            response = admin_client.get("/api/v1/admin/contexts/onboard/available-views")
        assert response.status_code == 200
        data = response.json()
        assert "unconfigured" in data
        assert "configured" in data
        assert len(data["unconfigured"]) == 1

    def test_inspect_empty_body(self, admin_client):
        """T7.3: POST inspect with empty body returns 422."""
        response = admin_client.post(
            "/api/v1/admin/contexts/onboard/inspect",
            json={},
        )
        assert response.status_code == 422

    def test_inspect_success(self, admin_client, mock_service):
        """T7.4: POST inspect with valid view_name returns inspection."""
        with patch("app.api.v1.admin._get_business_db_path", return_value="/tmp/test.db"):
            response = admin_client.post(
                "/api/v1/admin/contexts/onboard/inspect",
                json={"view_name": "test_view"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "inspection" in data

    def test_onboard_dry_run(self, admin_client, mock_service):
        """T7.5: POST onboard dry_run=true returns preview."""
        with patch("app.api.v1.admin._get_business_db_path", return_value="/tmp/test.db"):
            response = admin_client.post(
                "/api/v1/admin/contexts/onboard",
                json={"view_name": "test_view", "dry_run": True},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "preview"

    def test_onboard_inspect_only(self, admin_client, mock_service):
        """T7.6: POST onboard inspect_only=true returns inspect_only."""
        with patch("app.api.v1.admin._get_business_db_path", return_value="/tmp/test.db"):
            response = admin_client.post(
                "/api/v1/admin/contexts/onboard",
                json={"view_name": "test_view", "inspect_only": True},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inspect_only"

    def test_onboard_missing_view_name(self, admin_client):
        """T7.7: POST onboard without view_name returns 422."""
        response = admin_client.post(
            "/api/v1/admin/contexts/onboard",
            json={"dry_run": True},
        )
        assert response.status_code == 422

    def test_validate_success(self, admin_client, mock_service):
        """T7.8: POST validate returns validation result."""
        with patch("app.api.v1.admin._get_business_db_path", return_value="/tmp/test.db"):
            response = admin_client.post(
                "/api/v1/admin/contexts/onboard/validate",
                json={"view_name": "test_view"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "passed" in data

    def test_apply_sql_success(self, admin_client, mock_service):
        """T7.9: POST apply-sql applies cached SQL statements."""
        with patch("app.api.v1.admin._get_business_db_path", return_value="/tmp/test.db"):
            response = admin_client.post(
                "/api/v1/admin/contexts/onboard/apply-sql",
                json={
                    "view_name": "test_view",
                    "sql_statements": ["INSERT INTO schema_contexts VALUES ('x')"],
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "applied"

    def test_apply_sql_empty_statements(self, admin_client, mock_service):
        """T7.10: POST apply-sql with empty statements returns 400."""
        with patch("app.api.v1.admin._get_business_db_path", return_value="/tmp/test.db"):
            response = admin_client.post(
                "/api/v1/admin/contexts/onboard/apply-sql",
                json={"view_name": "test_view", "sql_statements": []},
            )
        assert response.status_code == 400
