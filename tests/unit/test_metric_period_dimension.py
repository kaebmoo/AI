"""Single-period questions can restate the period in pass-1 dimensions."""

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


@pytest.fixture(scope="module", params=[False, True], ids=["no-parts", "parts"])
def resolved(metric, request):
    if request.param:
        metric = replace(metric, period={**metric.period, "parts": {"year": "year", "month": "month"}})
    return resolve([metric])


@pytest.fixture
def intent():
    return {"intent_type": "aggregation", "metric_id": "revenue", "dimensions": ["year_month"],
            "filters": [], "time_range": {"year": 2026, "month": 9, "cumulative": True}}


def test_practice_single_period_keeps_numeric_business_filter(resolved, intent):
    intent["filters"] = [{"column": "bu_seq", "operator": "=", "value": 8}]
    original = deepcopy(intent)
    req, reason = plan_with_reason(intent, "รายได้สะสมของกลุ่มธุรกิจลำดับที่ 8", resolved, [], 202609, set(),
                                   numeric={"bu_seq"})
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters) == (
        202609, "cumulative", (), ({"column": "bu_seq", "operator": "=", "value": 8},))
    assert compile(req, resolved).table == "feed_revenue_fact_bu_monthly"
    assert intent == original


@pytest.mark.parametrize("dimensions", [["bu", "year_month"], ("bu", "YEAR_MONTH")])
def test_only_period_dimensions_are_removed(resolved, intent, dimensions):
    intent["dimensions"] = dimensions
    req, reason = plan_with_reason(intent, "รายได้แยกกลุ่มธุรกิจ", resolved, [], 202609, set())
    assert reason is None
    assert req.dimensions == ("bu",)


def test_declared_parts_as_dimensions(metric, intent):
    metric = replace(metric, period={**metric.period, "parts": {"year": "year", "month": "month"}})
    intent["dimensions"] = ["year", "month", "bu"]
    req, reason = plan_with_reason(intent, "รายได้แยกกลุ่มธุรกิจ", resolve([metric]), [], 202609, set())
    assert reason is None
    assert req.dimensions == ("bu",)


def test_equality_period_filter_pins_without_time_range_month(resolved, intent):
    intent.update(filters=[{"column": "year_month", "operator": "=", "value": 202609}], time_range={})
    req, reason = plan_with_reason(intent, "รายได้", resolved, [], 202609, set())
    assert reason is None
    assert (req.period, req.dimensions, req.filters) == (202609, (), ())


def test_synthetic_parts_equality_pins_without_time_range_month(metric, intent):
    metric = replace(metric, period={**metric.period, "parts": {"year": "year", "month": "month"}})
    intent.update(dimensions=["YEAR", "month", "bu"], time_range={},
                  filters=[{"column": "year", "operator": "=", "value": 2026},
                           {"column": "month", "operator": "=", "value": 9}])
    original = deepcopy(intent)
    req, reason = plan_with_reason(intent, "รายได้", resolve([metric]), [], 202609, set())
    assert reason is None
    assert (req.period, req.dimensions, req.filters) == (202609, ("bu",), ())
    assert intent == original


@pytest.mark.parametrize("time_range", [{}, {"year": 2026}, {"month": "9"}, None])
def test_unpinned_period_dimension_still_declines(resolved, intent, time_range):
    intent["time_range"] = time_range
    assert plan_with_reason(intent, "รายได้", resolved, [], 202609, set()) == (
        None, "shape:dimension:year_month")


@pytest.mark.parametrize("period_filters", [
    [{"column": "year_month", "operator": "BETWEEN", "value": [202601, 202609]}],
    [{"column": "year_month", "operator": "IN", "value": list(range(202601, 202610))}],
    [{"column": "year_month", "operator": ">=", "value": 202601},
     {"column": "year_month", "operator": "<=", "value": 202609}],
    [{"column": "year_month", "operator": "<=", "value": 202609}],
])
@pytest.mark.parametrize("question,cumulative,strips", [
    ("รายได้สะสม", True, True),
    ("รายได้", True, False),
    ("รายได้สะสม", False, False),
    ("รายได้รายเดือนสะสม", True, False),
])
def test_period_ranges_strip_only_for_explicit_cumulative_question(
        resolved, intent, period_filters, question, cumulative, strips):
    intent["filters"] = period_filters
    intent["time_range"]["cumulative"] = cumulative
    req, reason = plan_with_reason(intent, question, resolved, [], 202609, set())
    if strips:
        assert reason is None
        assert (req.period, req.mode, req.dimensions) == (202609, "cumulative", ())
    else:
        expected = "period_filter:range" if not cumulative and len(period_filters) == 1 \
            and period_filters[0]["operator"] == "<=" else "shape:dimension:year_month"
        assert (req, reason) == (None, expected)


@pytest.mark.parametrize("word", [
    "รายเดือน", "แต่ละเดือน", "ทุกเดือน", "เดือนละ", "ตามเดือน", "เดือนไหน", "เดือนใด", "แนวโน้ม",
    "รายปี", "แต่ละปี", "ปีไหน", "ไตรมาส", "Trend", "Monthly",
])
def test_trend_words_keep_dimension(resolved, intent, word):
    assert plan_with_reason(intent, "รายได้ " + word, resolved, [], 202609, set()) == (
        None, "shape:dimension:year_month")


def test_comparison_still_strips_period_and_returns_pair(resolved, intent):
    intent.update(intent_type="comparison", time_range=None,
                  filters=[{"column": "year_month", "operator": "IN", "value": [202608, 202609]}])
    original = deepcopy(intent)
    req, reason = plan_with_reason(intent, "รายได้ Monthly กันยายนเทียบสิงหาคม", resolved, [], 202609, set())
    assert reason is None
    assert (req.base_period, req.period, req.dimensions, req.filters) == (202608, 202609, (), ())
    assert intent == original


def test_time_key_period_is_metric_agnostic(metric, intent):
    metric = replace(metric, metric_id="ebt", name_th="EBT", synonyms=("EBT",),
                     dataset="feed_ebt_fact_ebt", datasets=None, dimensions=("bu",),
                     period={"column": "time_key", "value": {"cumulative": "amount_ytd", "month": "amount"}},
                     official_total=None)
    intent.update(metric_id="ebt", dimensions=["time_key"])
    req, reason = plan_with_reason(intent, "EBT สะสม", resolve([metric]), [], 202609, set())
    assert reason is None
    assert (req.period, req.dimensions) == (202609, ())
