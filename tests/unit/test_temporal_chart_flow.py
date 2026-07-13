from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.providers.chart_postprocessor import postprocess_chart_result
from app.services.ai.hybrid_flow import build_explanation
from app.services.ai.response_utils import prepare_data_for_explanation


TIME_METADATA = [
    {"column_name": "month", "dimension_group": "time_period"},
    {"column_name": "account", "is_groupable": 1},
    {"column_name": "amount", "is_summable": 1},
]


def monthly_rows(categories=19, months=12):
    return [
        {"account": f"A{category}", "month": month, "amount": (category + 1) * month}
        for month in range(1, months + 1)
        for category in range(categories)
    ]


def test_large_numeric_payload_keeps_temporal_column_and_grain():
    rows = monthly_rows()[:217]

    prepared = prepare_data_for_explanation(rows, schema_metadata=TIME_METADATA)

    assert len(prepared) <= 200
    assert "month" in prepared[0]
    assert len({row["month"] for row in prepared}) == 12
    assert len({row["account"] for row in prepared}) > 1


def test_top_n_is_applied_inside_each_month_and_preserves_totals():
    rows = monthly_rows()

    prepared = prepare_data_for_explanation(rows, schema_metadata=TIME_METADATA)

    assert len(prepared) <= 200
    for month in range(1, 13):
        expected = sum(row["amount"] for row in rows if row["month"] == month)
        actual = sum(row["amount"] for row in prepared if row["month"] == month)
        assert actual == pytest.approx(expected)


def test_quarter_reduction_keeps_negative_values_and_quarter_totals():
    rows = [
        {
            "account": f"A{category}",
            "quarter": quarter,
            "amount": (-1 if category % 2 else 1) * (category + 1) * quarter,
        }
        for quarter in range(1, 5)
        for category in range(60)
    ]
    metadata = [
        {"column_name": "quarter", "dimension_group": "time_period"},
        {"column_name": "amount", "is_summable": 1},
    ]

    prepared = prepare_data_for_explanation(rows, schema_metadata=metadata)

    assert len(prepared) <= 200
    assert {row["quarter"] for row in prepared} == {1, 2, 3, 4}
    assert any(row["amount"] < 0 for row in prepared)
    for quarter in range(1, 5):
        expected = sum(row["amount"] for row in rows if row["quarter"] == quarter)
        actual = sum(row["amount"] for row in prepared if row["quarter"] == quarter)
        assert actual == pytest.approx(expected)


def test_non_temporal_large_category_payload_uses_other_bucket():
    rows = [
        {"account": f"A{category}", "amount": -category if category % 2 else category}
        for category in range(250)
    ]

    prepared = prepare_data_for_explanation(rows)

    assert len(prepared) == 200
    assert any(row["account"] == "อื่นๆ" for row in prepared)
    assert sum(row["amount"] for row in prepared) == pytest.approx(
        sum(row["amount"] for row in rows)
    )


def _service_with_explanation(result):
    provider = SimpleNamespace(
        model="test-model",
        explain_result=AsyncMock(return_value=result),
    )
    return SimpleNamespace(provider=provider), provider


@pytest.mark.asyncio
async def test_build_explanation_re_enriches_chart_from_full_data():
    rows = monthly_rows()
    service, provider = _service_with_explanation({
        "explanation": "สรุปค่าใช้จ่ายรายเดือน",
        "visualization": "bar_chart",
        "chart_config": {
            "category_column": "account",
            "measure_column": "amount",
        },
    })

    result = await build_explanation(
        service,
        question="ค่าใช้จ่ายรายหมวดบัญชี รายเดือน",
        sql_query="SELECT account, month, SUM(amount) AS amount FROM expense",
        data=rows,
        cheap_model=None,
        prepare_data_for_explanation=prepare_data_for_explanation,
        dim_families=None,
        hierarchy_info=None,
        schema_metadata=TIME_METADATA,
    )

    explain_payload = provider.explain_result.await_args.args[2]
    assert len(explain_payload) <= 200
    assert "month" in explain_payload[0]
    assert result["explanation"] == "สรุปค่าใช้จ่ายรายเดือน"
    assert result["visualization"] == "heatmap"
    assert result["chart_config"]["category_column"] == "account"
    assert result["chart_config"]["series_column"] == "month"


@pytest.mark.asyncio
async def test_build_explanation_auto_detects_when_provider_omits_chart_config():
    service, _ = _service_with_explanation({
        "explanation": "สรุปผลรายเดือน",
    })

    result = await build_explanation(
        service,
        question="ค่าใช้จ่ายรายเดือน",
        sql_query="SELECT account, month, SUM(amount) AS amount FROM expense",
        data=monthly_rows(),
        cheap_model=None,
        prepare_data_for_explanation=prepare_data_for_explanation,
        dim_families=None,
        hierarchy_info=None,
        schema_metadata=TIME_METADATA,
    )

    assert result["explanation"] == "สรุปผลรายเดือน"
    assert result["chart_config"]["series_column"] == "month"
    assert result["chart_config"]["category_column"] == "account"
    assert result["visualization"] == "heatmap"


def test_shared_postprocessor_preserves_provider_title_and_uses_full_shape():
    result = postprocess_chart_result(
        {
            "explanation": "แนวโน้มรายเดือน",
            "chart_title": "ค่าใช้จ่ายรายเดือน",
            "visualization": "bar_chart",
            "chart_config": {
                "category_column": "account",
                "measure_column": "amount",
            },
        },
        monthly_rows(),
        schema_metadata=TIME_METADATA,
    )

    assert result["chart_config"]["title"] == "ค่าใช้จ่ายรายเดือน"
    assert result["chart_config"]["series_column"] == "month"
    assert result["visualization"] == "heatmap"
