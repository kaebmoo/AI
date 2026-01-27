"""
Unit Tests for AI Service
==========================
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.services.ai_service import (
    AIService,
    ClaudeProvider,
    GeminiProvider,
    QueryResult,
    create_claude_service,
    create_gemini_service
)


class TestAIServiceValidation:
    """Test SQL validation in AI Service"""

    @pytest.fixture
    def ai_service(self):
        """Create AI service with mocked provider"""
        with patch.object(ClaudeProvider, 'client', new_callable=MagicMock):
            service = AIService(
                provider="claude",
                api_key="test_key",
                db_path=":memory:"
            )
            return service

    def test_validate_sql_valid_select(self, ai_service):
        """Test validation of valid SELECT query"""
        is_valid, error = ai_service.validate_sql(
            "SELECT * FROM revenue WHERE MONTH = 1"
        )
        assert is_valid is True
        assert error == ""

    def test_validate_sql_valid_aggregate(self, ai_service):
        """Test validation of aggregate query"""
        is_valid, error = ai_service.validate_sql(
            "SELECT SUM(REVENUE_VALUE) as total FROM revenue GROUP BY MONTH"
        )
        assert is_valid is True

    def test_validate_sql_empty(self, ai_service):
        """Test validation of empty query"""
        is_valid, error = ai_service.validate_sql("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_sql_none(self, ai_service):
        """Test validation of None query"""
        is_valid, error = ai_service.validate_sql(None)
        assert is_valid is False

    def test_validate_sql_insert_blocked(self, ai_service):
        """Test INSERT is blocked"""
        is_valid, error = ai_service.validate_sql(
            "INSERT INTO revenue VALUES (1, 2, 3)"
        )
        assert is_valid is False
        assert "INSERT" in error

    def test_validate_sql_update_blocked(self, ai_service):
        """Test UPDATE is blocked"""
        is_valid, error = ai_service.validate_sql(
            "UPDATE revenue SET value = 100"
        )
        assert is_valid is False
        assert "UPDATE" in error

    def test_validate_sql_delete_blocked(self, ai_service):
        """Test DELETE is blocked"""
        is_valid, error = ai_service.validate_sql(
            "DELETE FROM revenue WHERE id = 1"
        )
        assert is_valid is False
        assert "DELETE" in error

    def test_validate_sql_drop_blocked(self, ai_service):
        """Test DROP is blocked"""
        is_valid, error = ai_service.validate_sql(
            "DROP TABLE revenue"
        )
        assert is_valid is False
        assert "DROP" in error

    def test_validate_sql_truncate_blocked(self, ai_service):
        """Test TRUNCATE is blocked"""
        is_valid, error = ai_service.validate_sql(
            "TRUNCATE TABLE revenue"
        )
        assert is_valid is False
        assert "TRUNCATE" in error

    def test_validate_sql_non_select_blocked(self, ai_service):
        """Test non-SELECT queries are blocked"""
        is_valid, error = ai_service.validate_sql(
            "SHOW TABLES"
        )
        assert is_valid is False
        assert "SELECT" in error


class TestClaudeProvider:
    """Test Claude Provider"""

    def test_init(self):
        """Test ClaudeProvider initialization"""
        provider = ClaudeProvider(api_key="test_key", model="claude-3-sonnet")
        assert provider.api_key == "test_key"
        assert provider.model == "claude-3-sonnet"

    def test_generate_sql_with_tool_use(self):
        """Test SQL generation with tool use"""
        # Mock the Anthropic client before creating provider
        mock_response = MagicMock()
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.name = "execute_sql"
        mock_tool_block.input = {
            "query": "SELECT SUM(REVENUE_VALUE) FROM revenue",
            "explanation": "รายได้รวม"
        }
        mock_response.content = [mock_tool_block]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch('anthropic.Anthropic', return_value=mock_client):
            provider = ClaudeProvider(api_key="test_key")

            result = provider.generate_sql(
                question="รายได้รวม?",
                system_prompt="You are a SQL assistant"
            )

            assert result["sql"] == "SELECT SUM(REVENUE_VALUE) FROM revenue"
            assert result["explanation"] == "รายได้รวม"
            assert result["tokens_used"] == 150


class TestGeminiProvider:
    """Test Gemini Provider"""

    def test_init(self):
        """Test GeminiProvider initialization"""
        provider = GeminiProvider(api_key="test_key", model="gemini-2.0-flash")
        assert provider.api_key == "test_key"
        assert provider.model == "gemini-2.0-flash"


class TestQueryResult:
    """Test QueryResult dataclass"""

    def test_create_query_result(self):
        """Test creating QueryResult"""
        result = QueryResult(
            question="รายได้รวม?",
            sql_query="SELECT SUM(REVENUE_VALUE) FROM revenue",
            data=[{"total": 1000000}],
            explanation="รายได้รวมคือ 1 ล้านบาท",
            tokens_used=100,
            provider="claude"
        )

        assert result.question == "รายได้รวม?"
        assert result.sql_query == "SELECT SUM(REVENUE_VALUE) FROM revenue"
        assert result.data == [{"total": 1000000}]
        assert result.error is None

    def test_query_result_with_error(self):
        """Test QueryResult with error"""
        result = QueryResult(
            question="Invalid query",
            sql_query="",
            data=[],
            explanation="",
            tokens_used=50,
            provider="claude",
            error="Could not generate SQL"
        )

        assert result.error == "Could not generate SQL"


class TestFactoryFunctions:
    """Test factory functions"""

    def test_create_claude_service(self):
        """Test create_claude_service factory"""
        with patch.object(ClaudeProvider, 'client', new_callable=MagicMock):
            service = create_claude_service(
                api_key="test_key",
                db_path=":memory:"
            )
            assert service.provider_name == "claude"

    def test_create_gemini_service(self):
        """Test create_gemini_service factory"""
        with patch.object(GeminiProvider, 'client', new_callable=MagicMock):
            service = create_gemini_service(
                api_key="test_key",
                db_path=":memory:"
            )
            assert service.provider_name == "gemini"
