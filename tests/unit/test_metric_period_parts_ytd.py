"""A declared month <= M feeds months 1..M through the existing YTD rules."""

from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path

import pytest
import yaml

from app.services.ai.metric_compiler import Metric, compile, plan_with_reason, resolve


@pytest.fixture(scope="module")
def metric():
    path = Path(__file__).parent.parent / "fixtures" / "revenue_metrics_draft.yaml"
    contract = yaml.safe_load(path.read_text())
    declaration = contract["metrics"][0]
    values = {f.name: declaration.get(f.name) for f in fields(Metric)}
    values["metric_id"] = declaration["id"]
    values["synonyms"] = tuple(values["synonyms"] or ())
    values["terms"] = values["terms"] or {}
    values["datasets"] = tuple({**item, "name": f"feed_{contract['domain']}_{item['name']}"}
                               for item in values["datasets"])
    total = values["official_total"]
    values["official_total"] = {**total, "dataset": f"feed_{contract['domain']}_{total['dataset']}"}
    return Metric(**values)


@pytest.fixture(scope="module")
def resolved(metric):
    return resolve([replace(metric, period={**metric.period, "parts": {"year": "year", "month": "month"}})])


@pytest.fixture
def intent():
    return {
        "intent_type": "aggregation", "metric_id": "revenue", "dimensions": [],
        "filters": [{"column": "bu_seq", "operator": "=", "value": 8},
                    {"column": "year", "operator": "=", "value": 2026},
                    {"column": "month", "operator": "<=", "value": 9}],
        "time_range": {"year": 2026, "month": 9, "cumulative": True},
    }


def test_practice_r5_compiles_cumulative_column(resolved, intent):
    original = deepcopy(intent)
    req, reason = plan_with_reason(intent, "รายได้อื่น (กลุ่มธุรกิจ 8) สะสมปีนี้เท่าไร", resolved, [],
                                   202609, set(), numeric={"bu_seq"})
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters) == (
        202609, "cumulative", (), ({"column": "bu_seq", "operator": "=", "value": 8},))
    compiled = compile(req, resolved)
    assert compiled.table == "feed_revenue_fact_bu_monthly"
    assert "= 202609" in compiled.sql and "BETWEEN" not in compiled.sql
    assert intent == original


@pytest.mark.parametrize("month,period", [(3, 202603), ("9", 202609), (1, 202601), (12, 202612)])
def test_month_upper_bound_uses_existing_ytd_rules(resolved, intent, month, period):
    intent.update(filters=[{"column": "year", "operator": "=", "value": 2026},
                           {"column": "month", "operator": "<=", "value": month}],
                  time_range={"year": 2026})
    req, reason = plan_with_reason(intent, "รายได้", resolved, [], 202612, set())
    assert reason is None
    assert (req.period, req.mode, req.filters) == (period, "cumulative", ())


@pytest.mark.parametrize("time_range", [{"year": 2026}, {}])
def test_month_only_uses_time_range_or_reference_year(resolved, intent, time_range):
    intent.update(filters=[{"column": "month", "operator": "<=", "value": 9}], time_range=time_range)
    req, reason = plan_with_reason(intent, "รายได้", resolved, [], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.filters) == (202609, "cumulative", ())


@pytest.mark.parametrize("column,operator,value,reason", [
    ("month", "<=", 0, "period_filter:value"),
    ("month", "<=", 13, "period_filter:value"),
    ("month", "<=", True, "period_filter:value"),
    ("month", "<=", [9], "period_filter:value"),
    ("month", "<=", 9.0, "period_filter:value"),
    ("month", "<=", "9.0", "period_filter:value"),
    ("month", "<=", " 9", "period_filter:value"),
    ("month", "<", 9, "period_filter:operator"),
    ("month", ">=", 1, "period_filter:operator"),
    ("month", ">", 1, "period_filter:operator"),
    ("year", "<=", 2026, "period_filter:operator"),
])
def test_invalid_part_filters_decline(resolved, intent, column, operator, value, reason):
    intent["filters"] = [{"column": column, "operator": operator, "value": value}]
    assert plan_with_reason(intent, "รายได้", resolved, [], 202609, set()) == (None, reason)


def test_duplicate_month_part_declines(resolved, intent):
    intent["filters"] = [{"column": "month", "operator": "<=", "value": 9},
                         {"column": "month", "operator": "=", "value": 9}]
    assert plan_with_reason(intent, "รายได้", resolved, [], 202609, set()) == (None, "period_filter:value")


def test_comparison_pairs_year_to_date_ends(resolved, intent):
    intent.update(intent_type="comparison",
                  filters=[{"column": "year", "operator": "IN", "value": [2025, 2026]},
                           {"column": "month", "operator": "<=", "value": 9}])
    req, reason = plan_with_reason(intent, "รายได้เทียบปีก่อน", resolved, [], 202609, set())
    assert reason is None
    assert (req.period, req.base_period, req.mode, req.filters) == (202609, 202509, "cumulative", ())


def test_practice_r6_cumulative_question_compiles(resolved, intent):
    intent["dimensions"] = ["year_month"]
    original = deepcopy(intent)
    req, reason = plan_with_reason(intent, "รายได้อื่น (กลุ่มธุรกิจ 8) สะสมปีนี้เท่าไร", resolved, [],
                                   202609, set(), numeric={"bu_seq"})
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters) == (
        202609, "cumulative", (), ({"column": "bu_seq", "operator": "=", "value": 8},))
    compiled = compile(req, resolved)
    assert compiled.table == "feed_revenue_fact_bu_monthly"
    assert "= 202609" in compiled.sql and "BETWEEN" not in compiled.sql
    assert plan_with_reason(intent, "รายได้อื่น (กลุ่มธุรกิจ 8) ปีนี้เท่าไร", resolved, [],
                            202609, set(), numeric={"bu_seq"}) == (None, "shape:dimension:year_month")
    assert intent == original


def test_without_cumulative_column_sums_months(metric, intent):
    metric = replace(metric, period={"column": "year_month", "parts": {"year": "year", "month": "month"},
                                    "value": {"month": "revenue"}}, official_total=None)
    resolved = resolve([metric])
    intent.update(dimensions=["bu"], filters=intent["filters"][1:])
    req, reason = plan_with_reason(intent, "รายได้", resolved, [], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters) == (202609, "cumulative", ("bu",), ())
    assert "BETWEEN 202601 AND 202609" in compile(req, resolved).sql


def test_without_parts_preserves_month_filter_decline(metric, intent):
    intent["filters"] = [{"column": "month", "operator": "<=", "value": 9}]
    assert plan_with_reason(intent, "รายได้", resolve([metric]), [], 202609, set()) == (
        None, "shape:filter:month")
