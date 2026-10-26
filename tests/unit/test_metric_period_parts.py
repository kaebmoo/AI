"""Declared year / month columns feed the existing period-filter planning rules."""

from copy import deepcopy
from dataclasses import fields, replace
import json
from pathlib import Path

import pytest
from sqlalchemy import text
import yaml

from app.services import datafeed_knowledge as dk
from app.services.ai.metric_compiler import Metric, compile, load_metrics, plan_with_reason, resolve
from tests.unit import knowledge_db


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
def live_intent():
    return {
        "intent_type": "ranking", "metric_id": "revenue", "dimensions": ["unit_name"],
        "filters": [{"column": "year", "operator": "=", "value": 2026},
                    {"column": "month", "operator": "=", "value": 9}],
        "time_range": {"year": 2026, "month": 9, "cumulative": True},
        "ordering": {"column": "revenue_ytd", "direction": "DESC"}, "limit": 5,
    }


def test_practice_ranking_compiles_one_period(resolved, live_intent):
    original = deepcopy(live_intent)
    req, reason = plan_with_reason(live_intent, "รายได้", resolved, [], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters, req.limit, req.order_desc) == (
        202609, "cumulative", ("unit_name",), (), 5, True)
    compiled = compile(req, resolved)
    assert compiled.table == "feed_revenue_fact_org_monthly"
    assert "= 202609" in compiled.sql and "BETWEEN" not in compiled.sql
    assert live_intent == original


def test_monthly_aggregation(resolved, live_intent):
    live_intent.update(intent_type="aggregation", dimensions=[],
                       time_range={"year": 2026, "month": 9, "cumulative": False})
    req, reason = plan_with_reason(live_intent, "รายได้", resolved, [], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters) == (202609, "month", (), ())


def test_year_only_fills_a_copy_of_time_range(resolved, live_intent):
    live_intent.update(filters=[{"column": "year", "operator": "=", "value": "2026"}],
                       time_range={"month": 9, "cumulative": True})
    original = deepcopy(live_intent)
    req, reason = plan_with_reason(live_intent, "รายได้", resolved, [], 202609, set())
    assert reason is None and (req.period, req.mode, req.filters) == (202609, "cumulative", ())
    assert live_intent == original


@pytest.mark.parametrize("time_range", [{"year": 2026}, {}])
def test_month_only_uses_time_range_or_reference_year(resolved, live_intent, time_range):
    live_intent.update(filters=[{"column": "month", "operator": "=", "value": 9}], time_range=time_range)
    req, reason = plan_with_reason(live_intent, "รายได้", resolved, [], 202609, set())
    assert reason is None and req.period == 202609 and req.filters == ()


@pytest.mark.parametrize("operator,value,period,reason", [
    ("BETWEEN", [1, 9], 202609, None),
    ("BETWEEN", [7, 9], None, "period_filter:range"),
    ("IN", [1, 2, 3], 202603, None),
    ("IN", ["3", "1", "2", "2"], 202603, None),
])
def test_month_ranges_use_existing_ytd_rules(resolved, live_intent, operator, value, period, reason):
    live_intent.update(filters=[{"column": "year", "operator": "=", "value": 2026},
                                {"column": "month", "operator": operator, "value": value}],
                       time_range={"year": 2026})
    req, got = plan_with_reason(live_intent, "รายได้", resolved, [], 202609, set())
    assert got == reason
    if reason:
        assert req is None
    else:
        assert (req.period, req.mode, req.filters) == (period, "cumulative", ())


@pytest.mark.parametrize("months", [[{"column": "month", "operator": "=", "value": 9}], []])
@pytest.mark.parametrize("time_range", [{"month": 9}, {}])
def test_comparison_pairs_and_default_month(resolved, live_intent, months, time_range):
    live_intent.update(intent_type="comparison", dimensions=["bu", "year", "MONTH", "year_month"],
                       filters=[{"column": "YEAR", "operator": "IN", "value": ["2026", "2025", "2026"]},
                                *months], time_range=time_range)
    req, reason = plan_with_reason(live_intent, "รายได้เทียบปีก่อน", resolved, [], 202609, set())
    assert reason is None
    assert (req.period, req.base_period, req.dimensions, req.filters) == (202609, 202509, ("bu",), ())


def test_threshold_comparison_strips_parts(resolved, live_intent):
    metric = replace(resolved["revenue"], ranking={"threshold": {"value": 100, "above": ["ถึงเป้า"]}})
    live_intent.update(intent_type="comparison", dimensions=["bu", "year", "MONTH", "year_month"])
    req, reason = plan_with_reason(live_intent, "รายได้ถึงเป้า", {"revenue": metric}, [], 202609, set())
    assert reason is None and req.dimensions == ("bu",) and req.base_period is None


@pytest.mark.parametrize("column,operator,value,reason", [
    ("month", "=", 13, "period_filter:value"),
    ("month", "=", 0, "period_filter:value"),
    ("month", "=", True, "period_filter:value"),
    ("month", "=", 9.0, "period_filter:value"),
    ("month", "=", "9.0", "period_filter:value"),
    ("month", "=", " 9", "period_filter:value"),
    ("month", "IN", [], "period_filter:value"),
    ("month", "IN", 9, "period_filter:value"),
    ("month", "BETWEEN", [9, 1], "period_filter:value"),
    ("month", "BETWEEN", [1], "period_filter:value"),
    ("month", "BETWEEN", [1, 9, 12], "period_filter:value"),
    ("month", ">=", 9, "period_filter:operator"),
    ("year", ">", 2025, "period_filter:operator"),
    ("year", "BETWEEN", [2025, 2026], "period_filter:operator"),
    ("year", "=", 0, "period_filter:value"),
    ("year", "=", 10000, "period_filter:value"),
    ("year", "IN", [], "period_filter:value"),
])
def test_invalid_part_filters_decline(resolved, live_intent, column, operator, value, reason):
    live_intent["filters"] = [{"column": column, "operator": operator, "value": value}]
    assert plan_with_reason(live_intent, "รายได้", resolved, [], 202609, set()) == (None, reason)


@pytest.mark.parametrize("column,value", [("month", 9), ("year", 2026)])
def test_duplicate_part_filters_decline(resolved, live_intent, column, value):
    live_intent["filters"] = [{"column": c, "operator": "=", "value": value}
                              for c in (column, column.upper())]
    assert plan_with_reason(live_intent, "รายได้", resolved, [], 202609, set()) == (None, "period_filter:value")


@pytest.mark.parametrize("reference", [None, "202609", True, 202600, 202613, 1000000])
@pytest.mark.parametrize("filters", [
    [{"column": "month", "operator": "=", "value": 9}],
    [{"column": "year", "operator": "IN", "value": [2025, 2026]}],
])
def test_missing_or_invalid_reference_for_default_part(resolved, live_intent, filters, reference):
    live_intent.update(filters=filters, time_range={})
    assert plan_with_reason(live_intent, "รายได้", resolved, [], reference, set()) == (None, "reference_missing")


def test_without_parts_preserves_the_decline(metric, live_intent):
    assert plan_with_reason(live_intent, "รายได้", resolve([metric]), [], 202609, set()) == (
        None, "shape:filter:year")


def test_only_declared_column_names_are_rewritten(resolved, live_intent):
    metric = replace(resolved["revenue"], period={**resolved["revenue"].period,
                                               "parts": {"year": "fiscal_year", "month": "fiscal_month"}})
    assert plan_with_reason(live_intent, "รายได้", {"revenue": metric}, [], 202609, set()) == (
        None, "shape:filter:year")
    for item in live_intent["filters"]:
        item["column"] = "FISCAL_" + item["column"].upper()
    req, reason = plan_with_reason(live_intent, "รายได้", {"revenue": metric}, [], 202609, set())
    assert reason is None and req.period == 202609 and req.filters == ()


@pytest.fixture
def engine(tmp_path):
    engine = knowledge_db.make(tmp_path / "x.db")
    yield engine
    engine.dispose()


@pytest.fixture
def contract():
    names = ["fact_total_monthly", "fact_bu_monthly", "fact_org_monthly"]
    dimensions = [[], ["bu"], ["unit_name"]]
    return {
        "domain": "revenue", "schema_version": "1", "primary_dataset": names[0], "period_key": "year_month",
        "datasets": [
            {"name": name, "columns": [
                *({"name": c, "dtype": "integer"} for c in ("year_month", "year", "month")),
                {"name": "revenue", "dtype": "double", "agg": "sum"},
                {"name": "revenue_ytd", "dtype": "double", "agg": "point_in_time"},
                *({"name": d, "dtype": "string"} for d in dims)]}
            for name, dims in zip(names, dimensions)],
        "metrics": [{
            "id": "revenue", "name_th": "รายได้", "datasets": [
                {"name": name, "dimensions": dims} for name, dims in zip(names, dimensions)],
            "period": {"column": "year_month", "parts": {"year": "year", "month": "month"},
                       "value": {"cumulative": "revenue_ytd", "month": "revenue"}},
            "terms": {"rev": {}}, "expr": "rev",
            "official_total": {"dataset": names[0], "column": "revenue_ytd", "month_column": "revenue"},
        }],
    }


@pytest.mark.parametrize("single", [False, True])
@pytest.mark.parametrize("parts", [{"year": "year", "month": "month"}, {"year": "year"}, {"month": "month"}])
def test_sync_parts_round_trip(engine, contract, single, parts):
    metric = contract["metrics"][0]
    metric["period"]["parts"] = parts
    if single:
        metric.pop("datasets")
        metric["dataset"] = "fact_total_monthly"
    original = deepcopy(contract)
    with engine.begin() as conn:
        dk.sync_knowledge(conn, "revenue", contract)
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT period FROM schema_metrics WHERE metric_id = 'revenue'")).scalar_one()
    assert json.loads(stored) == metric["period"]
    assert load_metrics("feed_revenue", engine)[0].period == metric["period"]
    assert contract == original


@pytest.mark.parametrize("parts", [
    None, [], "year", {}, {"day": "month"}, {"year": 2026}, {"year": ""}, {"year": "  "},
    {"year": "year", "month": "year"}, {"year": "year_month"}, {"month": "missing"},
])
def test_sync_invalid_parts_are_skipped(engine, contract, caplog, parts):
    contract["metrics"][0]["period"]["parts"] = parts
    with engine.begin() as conn:
        dk.sync_knowledge(conn, "revenue", contract)
    assert load_metrics("feed_revenue", engine) == []
    assert "Skipping metric revenue" in caplog.text and "period.parts" in caplog.text


def test_sync_requires_parts_in_every_dataset(engine, contract, caplog):
    contract["datasets"][2]["columns"] = [c for c in contract["datasets"][2]["columns"] if c["name"] != "month"]
    with engine.begin() as conn:
        dk.sync_knowledge(conn, "revenue", contract)
    assert load_metrics("feed_revenue", engine) == []
    assert "Skipping metric revenue" in caplog.text
    assert "unknown period.parts column 'month'" in caplog.text and "fact_org_monthly" in caplog.text
