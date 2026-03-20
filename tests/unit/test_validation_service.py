"""
Unit Tests for ValidationService (Plan 1B Phase A)
====================================================
Tests validation logic extracted from MCP servers.
"""

import pytest
from app.services.validation_service import ValidationService


class TestValidateSQL:
    """Test SQL validation."""

    def setup_method(self):
        self.service = ValidationService()

    def test_validate_sql_safe_select(self):
        """Safe SELECT query is valid."""
        result = self.service.validate_sql("SELECT * FROM revenue WHERE YEAR = 2025")
        assert result["valid"] is True
        assert result["sql_type"] == "SELECT"
        assert len(result["issues"]) == 0

    def test_validate_sql_blocks_drop(self):
        """DROP TABLE is blocked."""
        result = self.service.validate_sql("DROP TABLE revenue")
        assert result["valid"] is False
        assert any("DROP" in issue for issue in result["issues"])

    def test_validate_sql_blocks_insert(self):
        """INSERT is blocked."""
        result = self.service.validate_sql("INSERT INTO revenue VALUES (1, 2)")
        assert result["valid"] is False
        assert any("INSERT" in issue for issue in result["issues"])

    def test_validate_sql_blocks_injection(self):
        """SQL injection pattern is detected."""
        result = self.service.validate_sql("SELECT * FROM revenue; DROP TABLE users")
        assert result["valid"] is False

    def test_validate_sql_empty(self):
        """Empty SQL is invalid."""
        result = self.service.validate_sql("")
        assert result["valid"] is False
        assert "empty" in result["issues"][0].lower()

    def test_validate_sql_multiple_statements(self):
        """Multiple SQL statements are blocked."""
        result = self.service.validate_sql("SELECT 1; SELECT 2")
        assert result["valid"] is False
        assert any("Multiple" in issue for issue in result["issues"])

    def test_validate_sql_with_cte(self):
        """WITH (CTE) queries are allowed."""
        result = self.service.validate_sql("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert result["valid"] is True
        assert result["sql_type"] == "WITH"

    def test_validate_sql_warns_select_star(self):
        """SELECT * triggers a warning."""
        result = self.service.validate_sql("SELECT * FROM revenue")
        assert result["valid"] is True
        assert any("SELECT *" in w for w in result["warnings"])

    def test_validate_sql_warns_no_where(self):
        """Missing WHERE triggers a warning."""
        result = self.service.validate_sql("SELECT SUM(REVENUE_VALUE) FROM revenue")
        assert any("WHERE" in w for w in result["warnings"])


class TestCheckBusinessRules:
    """Test business rule checking from DB."""

    def test_check_rules_no_db(self):
        """Without DB, rules check passes by default."""
        service = ValidationService(db=None)
        result = service.check_business_rules("SELECT * FROM revenue")
        assert result["passed"] is True


class TestCalculateConfidence:
    """Test confidence scoring."""

    def setup_method(self):
        self.service = ValidationService()

    def test_high_confidence(self):
        """Perfect query gets high confidence."""
        result = self.service.calculate_confidence(
            sql_validation_passed=True,
            rules_passed=True,
            has_similar_example=True,
            example_similarity=0.9,
            result_row_count=10,
            execution_success=True,
        )
        assert result["score"] >= 85
        assert result["level"] == "high"
        assert result["color"] == "green"

    def test_low_confidence(self):
        """Failed query gets low confidence."""
        result = self.service.calculate_confidence(
            sql_validation_passed=False,
            sql_issues_count=2,
            rules_passed=False,
            rules_violations_count=1,
            execution_success=False,
        )
        assert result["score"] < 40
        assert result["level"] in ("low", "very_low")

    def test_medium_confidence(self):
        """Partial success gets medium confidence."""
        result = self.service.calculate_confidence(
            sql_validation_passed=True,
            rules_passed=True,
            has_similar_example=False,
            result_row_count=5,
            execution_success=True,
        )
        assert 40 <= result["score"] < 85

    def test_confidence_has_required_fields(self):
        """Confidence result has all required fields."""
        result = self.service.calculate_confidence()
        for key in ("score", "max_score", "level", "level_th", "color", "factors", "recommendation", "summary"):
            assert key in result
