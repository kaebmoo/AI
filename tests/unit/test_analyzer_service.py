import pytest
from unittest.mock import AsyncMock, Mock

from app.services.analyzer_service import AnalyzerService


def test_analyze_file_csv_returns_schema_summary(db_session):
    service = AnalyzerService(db_session, Mock())

    result = service.analyze_file(
        b"name,amount\nfoo,10\nbar,20\n",
        "sample.csv",
    )

    assert result["source"] == "sample.csv"
    assert result["total_rows"] == 2
    assert result["columns"][0]["column_name"] == "name"
    assert result["columns"][1]["column_name"] == "amount"
    assert result["columns"][0]["sample_values"] == ["foo", "bar"]


def test_extract_json_payload_handles_fenced_json():
    payload = AnalyzerService.extract_json_payload(
        "```json\n{\"columns\": [], \"potential_mappings\": [], \"business_rules\": []}\n```"
    )

    assert payload == {
        "columns": [],
        "potential_mappings": [],
        "business_rules": [],
    }


@pytest.mark.asyncio
async def test_get_ai_suggestions_uses_provider_generate_content(db_session):
    provider = Mock()
    provider.generate_content = AsyncMock(
        return_value='{"columns": [{"column_name": "amount"}], "potential_mappings": [], "business_rules": []}'
    )
    ai_service = Mock(provider=provider)
    service = AnalyzerService(db_session, ai_service)

    result = await service.get_ai_suggestions(
        {
            "source": "sample.csv",
            "columns": [{"column_name": "amount", "data_type": "int64", "sample_values": ["10"]}],
            "total_rows": 1,
        }
    )

    provider.generate_content.assert_awaited_once()
    assert result["columns"][0]["column_name"] == "amount"


@pytest.mark.asyncio
async def test_get_ai_suggestions_returns_safe_error_payload_on_invalid_json(db_session):
    provider = Mock()
    provider.generate_content = AsyncMock(return_value="not-json")
    ai_service = Mock(provider=provider)
    service = AnalyzerService(db_session, ai_service)

    result = await service.get_ai_suggestions({"source": "sample.csv", "columns": []})

    assert result["columns"] == []
    assert result["potential_mappings"] == []
    assert result["business_rules"] == []
    assert "error" in result