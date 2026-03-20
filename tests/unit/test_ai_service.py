"""
Unit Tests for AI Service
==========================
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from app.services.ai_service import (
    AIService,
    ClaudeProvider,
    GeminiProvider,
    QueryResult,
    create_claude_service,
    create_gemini_service
)


class TestClaudeProvider:
    """Test Claude Provider"""

    def test_init(self):
        """Test ClaudeProvider initialization"""
        provider = ClaudeProvider(api_key="test_key", model="claude-3-sonnet")
        assert provider.api_key == "test_key"
        assert provider.model == "claude-3-sonnet"

    async def test_generate_sql_with_tool_use(self):
        """Test SQL generation returns response and token count"""
        # Mock the AsyncAnthropic client
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
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch('anthropic.AsyncAnthropic', return_value=mock_client):
            provider = ClaudeProvider(api_key="test_key")

            result = await provider.generate_sql(
                question="รายได้รวม?",
                system_prompt="You are a SQL assistant",
                tools=[]
            )

            # generate_sql returns {"response": response_obj, "tokens_used": int}
            assert "response" in result
            assert result["tokens_used"] == 150
            # Verify tool_use block is in the response
            assert result["response"].content[0].type == "tool_use"
            assert result["response"].content[0].input["query"] == "SELECT SUM(REVENUE_VALUE) FROM revenue"


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
