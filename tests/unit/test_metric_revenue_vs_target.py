"""revenue_vs_target (revenue 2.6.0): pass 1 habits on "มีกลุ่มบริการอะไรบ้างที่ไม่ผ่านเป้า" (practice server rvt r6,
2026-10-27): the side of the line written as a filter on the value column, and a question without time words
sent as one month instead of the year to date (owner 2026-09-25)."""

from dataclasses import fields
from pathlib import Path

import pytest
import yaml

from app.services.ai.metric_compiler import Metric, _names_time, plan_with_reason, resolve


LIVE_CONTRACT = Path("/Users/seal/Documents/GitHub/_worktrees/NT-Report-metrics/DataFeed/contracts/revenue.yaml")
CONTRACT = Path(__file__).parent.parent / "fixtures" / "revenue_vs_target_2_6_0.yaml"
QUESTION = "มีกลุ่มบริการอะไรบ้างที่ไม่ผ่านเป้า"


def test_fixture_matches_the_live_contract_when_present():
    live = yaml.safe_load(LIVE_CONTRACT.read_text())["metrics"] if LIVE_CONTRACT.exists() else []
    declared = [m for m in live if m["id"] == "revenue_vs_target"]
    if not declared:
        pytest.skip("NT-Report contract with revenue_vs_target not available on this machine")
    assert declared == yaml.safe_load(CONTRACT.read_text())["metrics"]


@pytest.fixture(scope="module")
def resolved():
    declaration = yaml.safe_load(CONTRACT.read_text())["metrics"][0]
    values = {f.name: declaration.get(f.name) for f in fields(Metric)}
    values.update(metric_id=declaration["id"], synonyms=tuple(values["synonyms"]),
                  datasets=tuple({**d, "name": f"feed_revenue_{d['name']}"} for d in values["datasets"]))
    return resolve([Metric(**values)])


def intent(filters, time_range, ordering="amount"):
    return {"intent_type": "ranking", "metrics": ["revenue_vs_target"], "metric_id": "revenue_vs_target",
            "aggregate_function": "SUM", "dimensions": ["service_group_nt"], "filters": filters,
            "time_range": time_range, "ordering": {"column": ordering, "direction": "ASC"}, "limit": None,
            "matched_mappings": []}


ACTUAL = {"column": "metric", "operator": "=", "value": "actual"}
SEPTEMBER = [{"column": "year", "operator": "=", "value": 2026}, {"column": "month", "operator": "=", "value": 9}]


def test_a_value_filter_that_spells_the_side_of_the_line_is_dropped(resolved):
    """r6 07:45:44 (portal scope): amount < 'revenue_target' declined as shape:filter:amount; free SQL said 11 (13)."""
    observed = intent([ACTUAL, {"column": "year_month", "operator": "=", "value": 202609},
                       {"column": "amount", "operator": "<", "value": "revenue_target"}],
                      {"year": 2026, "month": 9, "cumulative": True})
    req, reason = plan_with_reason(observed, QUESTION, resolved, ["revenue_vs_target"], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters, req.threshold, req.order_desc, req.limit) == (
        202609, "cumulative", ("service_group_nt",), (), "below", False, None)


@pytest.mark.parametrize("question,value_filter", [
    ("กลุ่มบริการที่ไม่ผ่านเป้าและรายได้เกิน 100 ล้าน", {"column": "amount", "operator": ">", "value": 100000000}),
    ("กลุ่มบริการไหนรายได้ต่ำ", {"column": "amount", "operator": "<", "value": "revenue_target"}),
])
def test_a_value_filter_without_a_named_side_or_with_a_number_still_declines(resolved, question, value_filter):
    observed = intent([value_filter], {"year": 2026, "month": 9, "cumulative": True})
    assert plan_with_reason(observed, question, resolved, [], 202609, set()) == (None, "shape:filter:amount")


@pytest.mark.parametrize("question,mode", [
    (QUESTION, "cumulative"),                                   # r6 without scope: September alone, twice
    ("5 กลุ่มบริการที่รายได้ต่ำกว่าเป้ามากที่สุด", "cumulative"),
    ("กลุ่มบริการที่ไม่ผ่านเป้า เดือนกันยายน 2569", "month"),
    ("กลุ่มบริการที่ไม่ผ่านเป้าเดือนล่าสุด", "month"),
])
def test_a_question_without_time_words_is_the_year_to_date(resolved, question, mode):
    observed = intent([*SEPTEMBER, ACTUAL], {"year": 2026, "month": 9, "cumulative": False}, "amount_ytd")
    req, reason = plan_with_reason(observed, question, resolved, [], 202609, set())
    assert reason is None and (req.period, req.mode) == (202609, mode)


@pytest.mark.parametrize("question,named", [
    (QUESTION, False), ("รายได้เกิน 120000000 บาท", False), ("รายได้ ก.ย. 2569", True), ("รายได้ 09/2569", True),
    ("รายได้ปีนี้เทียบเป้า", True), ("แนวโน้มรายได้เทียบเป้า", True), ("revenue YTD vs target", True),
])
def test_time_words(question, named):
    assert _names_time(question) is named


HIERARCHY = [{"level": 0, "columns": ["bu", "bu_seq"], "label_th": "กลุ่มธุรกิจ",
              "detection_keywords": ["กลุ่มธุรกิจ", "ธุรกิจ", "business group", "business"]},
             {"level": 12, "columns": ["unit_name", "unit_sname"], "label_th": "ฝ่าย", "detection_keywords": ["ฝ่าย"]}]


def test_a_mapping_on_a_level_word_of_the_hierarchy_does_not_block(resolved):
    """Practice server rvt: "รายได้แต่ละกลุ่มธุรกิจเทียบเป้า" came with bu LIKE '%กลุ่มธุรกิจ%' as a mapping; bu's label is
    "business group (BG)" so the Thai level word only reaches plan() through master_hierarchy."""
    observed = {**intent([], {"year": 2026, "month": 9, "cumulative": True}), "intent_type": "comparison",
                "dimensions": ["bu"], "ordering": None,
                "matched_mappings": [{"keyword": "กลุ่มธุรกิจ", "sql_condition": "bu LIKE '%กลุ่มธุรกิจ%'"}]}
    question, labels = "รายได้แต่ละกลุ่มธุรกิจเทียบเป้า", {"bu": "business group (BG)"}
    assert plan_with_reason(observed, question, resolved, [], 202609, set(), labels) == (
        None, "mapping_triggered:กลุ่มธุรกิจ")
    req, reason = plan_with_reason(observed, question, resolved, [], 202609, set(), labels, hierarchy=HIERARCHY)
    assert reason is None and (req.dimensions, req.mode, req.base_period) == (("bu",), "cumulative", None)
    # a level the metric does not declare (ฝ่าย: no unit_name in revenue_vs_target) lends no words
    unit = {**observed, "matched_mappings": [{"keyword": "ฝ่าย", "sql_condition": "unit_name LIKE '%ฝ่าย%'"}]}
    assert plan_with_reason(unit, "รายได้แต่ละกลุ่มธุรกิจของฝ่ายเทียบเป้า", resolved, [], 202609, set(), labels,
                            hierarchy=HIERARCHY)[1] == "mapping_triggered:ฝ่าย"
