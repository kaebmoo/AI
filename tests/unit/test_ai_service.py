"""
Unit Tests for AI Service
==========================
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from app.services.ai import hybrid_flow
from app.services.ai_service import (
    AIService,
    AIProvider,
    COLUMN_HIERARCHIES,
    ClaudeProvider,
    GeminiProvider,
    QueryResult,
    create_claude_service,
    create_gemini_service,
    get_column_hierarchies,
)


class DummyProvider(AIProvider):
    name = "dummy"

    def __init__(self, content_response: str = "", explain_response: str = "ok"):
        self.api_key = "dummy-key"
        self.model = "dummy-model"
        self.content_response = content_response
        self.explain_response = explain_response

    async def generate_sql(self, question, system_prompt, tools, history=[]):
        return {"response": Mock(), "tokens_used": 0}

    async def explain_result(self, question, sql, data, system_prompt, dimension_families=None, hierarchy_info=None, schema_metadata=None):
        return self.explain_response

    async def generate_content(self, prompt, system_prompt=None, history=None):
        return self.content_response


@pytest.fixture
def legacy_ai_service(monkeypatch):
    def fake_init_legacy_provider(self, provider_name, api_key, model, **kwargs):
        self.provider = DummyProvider()

    monkeypatch.setattr(AIService, "_init_legacy_provider", fake_init_legacy_provider)
    return AIService(provider="claude", api_key="test-key", mcp_client=Mock())


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


class TestAIServiceCharacterization:
    def test_module_reexports_hierarchy_surface(self):
        assert isinstance(COLUMN_HIERARCHIES, dict)
        assert callable(get_column_hierarchies)

    def test_extract_sql_prefers_sql_fenced_block(self, legacy_ai_service):
        response = """วิเคราะห์เสร็จแล้ว

```sql
SELECT SUM(REVENUE_VALUE) AS total FROM revenue
```

**คำอธิบาย:** รายได้รวม
"""

        assert legacy_ai_service._extract_sql(response) == "SELECT SUM(REVENUE_VALUE) AS total FROM revenue"

    def test_extract_explanation_removes_sql_blocks(self, legacy_ai_service):
        response = """```sql
SELECT * FROM revenue
```

**คำอธิบาย:** รายได้รวมแยกตามเดือน"""

        assert legacy_ai_service._extract_explanation(response) == "รายได้รวมแยกตามเดือน"

    def test_parse_intent_json_from_fenced_block(self, legacy_ai_service):
        payload = """ก่อนวิเคราะห์
```json
{"intent_type":"trend","metrics":["REVENUE_VALUE"]}
```
"""

        assert legacy_ai_service._parse_intent_json(payload) == {
            "intent_type": "trend",
            "metrics": ["REVENUE_VALUE"],
        }

    def test_prepare_data_for_explanation_aggregates_large_dataset(self):
        rows = []
        for index in range(240):
            rows.append({
                "category": f"C{index % 4}",
                "year": 2025,
                "month": (index % 12) + 1,
                "amount": float(index + 1),
            })

        prepared = AIService._prepare_data_for_explanation(rows)

        assert len(prepared) <= 200
        expected = {}
        for row in rows:
            key = (row["category"], row["year"], row["month"])
            expected[key] = expected.get(key, 0.0) + row["amount"]

        actual = {
            (row["category"], row["year"], row["month"]): row["amount"]
            for row in prepared
        }
        assert actual == expected

    def test_detect_hierarchy_level_prefers_parent_in_drilldown(self, monkeypatch, legacy_ai_service):
        hierarchy = {
            "revenue": [
                {"level": 0, "label_th": "กลุ่มธุรกิจ", "label_en": "Business", "columns": ["BUSINESS_GROUP"], "detection_keywords": ["กลุ่มธุรกิจ"]},
                {"level": 1, "label_th": "กลุ่มบริการ", "label_en": "Service", "columns": ["SERVICE_GROUP"], "detection_keywords": ["กลุ่มบริการ", "fixed line"]},
                {"level": 2, "label_th": "บริการ", "label_en": "Product", "columns": ["PRODUCT_NAME"], "detection_keywords": ["บริการ", "แต่ละบริการ"]},
            ]
        }
        monkeypatch.setattr("app.services.ai_service.get_column_hierarchies", lambda: hierarchy)

        detected = legacy_ai_service._detect_hierarchy_level("แต่ละบริการของกลุ่ม Fixed Line", "revenue")

        assert detected is not None
        assert detected["level"] == 1
        assert detected["label_en"] == "Service"

    def test_format_value_matches_marks_use_this_level(self, legacy_ai_service):
        hierarchy = [
            {"level": 1, "label_th": "กลุ่มบริการ", "label_en": "Service", "columns": ["SERVICE_GROUP"]},
            {"level": 2, "label_th": "บริการ", "label_en": "Product", "columns": ["PRODUCT_NAME"]},
        ]
        value_matches = [
            {"keyword": "fixed line", "column_name": "SERVICE_GROUP", "column_value": "Fixed Line"},
            {"keyword": "fixed line", "column_name": "PRODUCT_NAME", "column_value": "FTTx"},
        ]

        formatted = legacy_ai_service._format_value_matches(
            value_matches,
            hierarchy=hierarchy,
            detected_level={"level": 1},
        )

        assert "USE THIS LEVEL" in formatted
        assert "different level — do NOT use" in formatted

    def test_train_returns_false_without_vanna(self, legacy_ai_service):
        legacy_ai_service.vanna = None

        assert legacy_ai_service.train("รายได้รวม", "SELECT 1") is False

    async def test_suggest_mappings_falls_back_when_response_is_not_json(self, legacy_ai_service):
        legacy_ai_service.provider = DummyProvider(content_response="not-json")

        result = await legacy_ai_service.suggest_mappings(
            columns=[{"name": "TOTAL_REVENUE", "type": "REAL"}],
            samples={"TOTAL_REVENUE": [100, 200]},
        )

        assert result == [{
            "col": "TOTAL_REVENUE",
            "alias": "total revenue",
            "reason": "ชื่อเดิมโดยแปลง underscore เป็น space",
        }]

    async def test_explain_result_delegates_to_provider(self, legacy_ai_service):
        legacy_ai_service.provider = DummyProvider(explain_response="สรุปผล")

        result = await legacy_ai_service.explain_result(
            question="รายได้รวม",
            sql="SELECT 1",
            data=[{"total": 1}],
            system_prompt="system",
        )

        assert result == "สรุปผล"

    async def test_query_with_retry_claude_returns_text_without_tool_calls(self, legacy_ai_service):
        response = Mock()
        response.content = [Mock(type="text", text="คำอธิบายจาก Claude")]

        legacy_ai_service.provider = Mock()
        legacy_ai_service.provider.generate_sql = AsyncMock(return_value={
            "response": response,
            "tokens_used": 12,
        })
        legacy_ai_service.mcp_client.get_tools = AsyncMock(return_value=[])

        result = await legacy_ai_service.query_with_retry("รายได้รวม")

        assert result.explanation == "คำอธิบายจาก Claude"
        assert result.tokens_used == 12
        assert result.provider == "claude"

    async def test_query_with_retry_matcha_executes_tool_and_returns_data(self, legacy_ai_service):
        legacy_ai_service.provider_name = "matcha"
        legacy_ai_service.provider = Mock()
        legacy_ai_service.provider.generate_sql = AsyncMock(side_effect=[
            {
                "response": {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "function": {
                                            "name": "execute_query",
                                            "arguments": '{"sql":"SELECT 1 AS total"}',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                "tokens_used": 20,
            },
            {
                "response": {
                    "choices": [
                        {
                            "message": {
                                "content": "สรุปผลลัพธ์",
                            }
                        }
                    ]
                },
                "tokens_used": 5,
            },
        ])
        legacy_ai_service.mcp_client.get_tools = AsyncMock(return_value=[])
        legacy_ai_service.mcp_client.call_tool = AsyncMock(return_value='[{"total":1}]')

        result = await legacy_ai_service.query_with_retry("รายได้รวม")

        assert result.sql_query == "SELECT 1 AS total"
        assert result.data == [{"total": 1}]
        assert result.explanation == "สรุปผลลัพธ์"
        assert result.tokens_used == 25

    def test_build_history_context_uses_recent_messages(self):
        history = [
            {"role": "user", "content": "เก่า 1"},
            {"role": "assistant", "content": "เก่า 2"},
            {"role": "user", "content": "ล่าสุด 1"},
            {"role": "assistant", "content": "ล่าสุด 2"},
            {"role": "user", "content": "ล่าสุด 3"},
        ]

        context = hybrid_flow.build_history_context(history)

        assert "เก่า 1" not in context
        assert "ล่าสุด 1" in context
        assert "ล่าสุด 3" in context
        assert "ประวัติสนทนาก่อนหน้า" in context

    def test_build_retry_user_prompt_includes_previous_error(self):
        prompt = hybrid_flow.build_retry_user_prompt(
            question="รายได้รวม",
            context_table="revenue",
            context_thai="รายได้",
            retry_history=[{"sql": "SELECT * FROM bad", "error": "column not found"}],
        )

        assert "SELECT * FROM bad" in prompt
        assert "column not found" in prompt
        assert "ต้องใช้ตาราง revenue เท่านั้น" in prompt

    async def test_validate_sql_attempt_parses_string_payload(self, legacy_ai_service):
        legacy_ai_service.mcp_client.call_tool = AsyncMock(return_value='{"valid": true, "issues": []}')

        validation, error = await hybrid_flow.validate_sql_attempt(legacy_ai_service, "SELECT 1")

        assert error is None
        assert validation == {"valid": True, "issues": []}

    async def test_execute_sql_attempt_returns_execution_error_message(self, legacy_ai_service):
        legacy_ai_service.mcp_client.call_tool = AsyncMock(side_effect=RuntimeError("boom"))

        exec_data, error = await hybrid_flow.execute_sql_attempt(legacy_ai_service, "SELECT 1")

        assert exec_data is None
        assert error == "Execution error: boom"

    async def test_build_confidence_result_returns_none_without_validation_server(self, legacy_ai_service):
        legacy_ai_service.mcp_client.servers = {}

        confidence = await hybrid_flow.build_confidence_result(
            legacy_ai_service,
            sql_query="SELECT 1",
            question="รายได้รวม",
            context_name="revenue",
            data=[{"total": 1}],
        )

        assert confidence is None

    async def test_build_explanation_returns_empty_result_message(self, legacy_ai_service):
        explanation = await hybrid_flow.build_explanation(
            legacy_ai_service,
            question="รายได้รวม",
            sql_query="SELECT 1",
            data=[],
            cheap_model=None,
            prepare_data_for_explanation=legacy_ai_service.prepare_data_for_explanation,
            dim_families=None,
            hierarchy_info=None,
            schema_metadata=None,
        )

        assert "ไม่พบข้อมูลที่ตรงกับเงื่อนไข" in explanation
        assert "SELECT 1" in explanation

    async def test_generate_sql_attempt_returns_error_message(self, legacy_ai_service):
        legacy_ai_service.provider = Mock()
        legacy_ai_service.provider.generate_content = AsyncMock(side_effect=RuntimeError("gen failed"))

        response_text, tokens_used, error = await hybrid_flow.generate_sql_attempt(
            legacy_ai_service,
            user_prompt="ถาม",
            system_prompt="system",
            history=None,
            attempt=0,
        )

        assert response_text is None
        assert tokens_used == 0
        assert error == "generate_content error: gen failed"

    async def test_verify_values_if_needed_skips_when_disabled(self, legacy_ai_service):
        hint = await hybrid_flow.verify_values_if_needed(
            legacy_ai_service,
            sql_query="SELECT 1",
            question="รายได้รวม",
            context_name="revenue",
            context_table="revenue",
            should_verify=False,
            log_value_corrections=Mock(),
        )

        assert hint is None

    async def test_build_first_attempt_prompt_falls_back_to_initial_prompt(self, legacy_ai_service, monkeypatch):
        monkeypatch.setattr(hybrid_flow, "extract_intent", AsyncMock(return_value=None))

        user_prompt, two_pass_enabled = await hybrid_flow.build_first_attempt_prompt(
            service=legacy_ai_service,
            question="รายได้รวม",
            system_prompt="system",
            history=None,
            context_name="revenue",
            context_table="revenue",
            context_thai="รายได้",
            two_pass_enabled=True,
            cheap_model=None,
            detect_hierarchy_level=lambda question, context_name: None,
            format_value_matches=lambda value_matches, hierarchy=None, detected_level=None: "",
            get_vanna_context_string=lambda question: "",
            lookup_values_from_question=lambda question, context_name, table_name: [],
            on_status=None,
            attempt=0,
            max_retries=2,
        )

        assert two_pass_enabled is False
        assert "ต้องใช้ตาราง revenue เท่านั้น" in user_prompt

    async def test_run_hybrid_attempt_returns_none_on_generation_error(self, legacy_ai_service, monkeypatch):
        monkeypatch.setattr(
            hybrid_flow,
            "generate_sql_attempt",
            AsyncMock(return_value=(None, 0, "generate_content error: failed")),
        )

        result, total_tokens, sql_query = await hybrid_flow.run_hybrid_attempt(
            service=legacy_ai_service,
            question="รายได้รวม",
            system_prompt="system",
            history=None,
            on_status=None,
            context_name="revenue",
            context_table="revenue",
            attempt=0,
            max_retries=2,
            value_verification_enabled=True,
            cheap_model=None,
            user_prompt="prompt",
            temp_schema=Mock(),
            retry_history=[],
            total_tokens=0,
            extract_sql=legacy_ai_service.extract_sql,
            extract_explanation=legacy_ai_service.extract_explanation,
            log_value_corrections=Mock(),
            prepare_data_for_explanation=legacy_ai_service.prepare_data_for_explanation,
            start_request=0.0,
        )

        assert result is None
        assert total_tokens == 0
        assert sql_query is None
