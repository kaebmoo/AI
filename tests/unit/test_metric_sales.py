"""sales_vs_target (sales 1.4.0): a year to date summed from monthly amounts, ยอดขาย/เป้า beside the %, units
without a target left out and "มากกว่าเป้า" read from the contract's words. The portal and MCP answered
"หน่วยงานที่ยอดขายมากกว่าเป้า" with 71 units (the Sales report: 5) and a 92.38% company as above target,
because free SQL mixed 8.รายได้อื่น into both sides (audit 463–466, 2026-10-25)."""

from dataclasses import fields, replace
from pathlib import Path
import sqlite3

import duckdb
import pytest
import yaml

from app.services.ai.metric_compiler import CompileRequest, Metric, _threshold_side, compile, plan_with_reason, resolve
from app.services.database_adapter import check_select
from app.services.datafeed_knowledge import _validate_metric


LIVE_CONTRACT = Path("/Users/seal/Documents/GitHub/_worktrees/NT-Report-metrics/DataFeed/contracts/sales.yaml")
CONTRACT = Path(__file__).parent.parent / "fixtures" / "sales_metrics_1_4_1.yaml"
TABLE = "feed_sales_fact_sales"
QUESTION = "หน่วยงานที่ยอดขายมากกว่าเป้ามีหน่วยไหนบ้าง"


def test_fixture_matches_the_live_contract_when_present():
    if not LIVE_CONTRACT.exists():
        pytest.skip("NT-Report contract not available on this machine")
    assert yaml.safe_load(LIVE_CONTRACT.read_text())["metrics"] == yaml.safe_load(CONTRACT.read_text())["metrics"]


@pytest.fixture(scope="module")
def declared():
    return yaml.safe_load(CONTRACT.read_text())["metrics"]


@pytest.fixture(scope="module")
def resolved(declared):
    rows = []
    for declaration in declared:
        values = {f.name: declaration.get(f.name) for f in fields(Metric)}
        values.update(metric_id=declaration["id"], synonyms=tuple(values["synonyms"]),
                      dimensions=tuple(values["dimensions"]), dataset=f"feed_sales_{values['dataset']}")
        rows.append(Metric(**values))
    return resolve(rows)


@pytest.fixture(scope="module")
def databases():
    rows = []  # (year_month, metric, business_group, unit_fname, amount)
    for month in range(202601, 202610):
        rows += [(month, "target", "4.Fixed Line & Broadband", "ฝ่าย A", 100),
                 (month, "actual", "4.Fixed Line & Broadband", "ฝ่าย A", 120),
                 (month, "actual", "8.รายได้อื่น", "ฝ่าย A", 1000),
                 (month, "target", "1.Hard Infrastructure", "ฝ่าย B", 100),
                 (month, "actual", "1.Hard Infrastructure", "ฝ่าย B", 90),
                 (month, "actual", "8.รายได้อื่น", "ฝ่าย B", 50),     # would lift B to 144% if mixed in
                 (month, "actual", "5.Digital", "ฝ่าย C", 10),         # no target
                 (month, "target", "8.รายได้อื่น", "ฝ่าย D", 500),     # รายได้อื่น only (ฝ่ายบริหารการเงินฯ)
                 (month, "actual", "8.รายได้อื่น", "ฝ่าย D", 600)]
    rows += [(202512, "actual", "4.Fixed Line & Broadband", "ฝ่าย A", 99999),  # outside the year to date
             (202610, "actual", "1.Hard Infrastructure", "ฝ่าย B", 99999)]
    connections = [duckdb.connect(":memory:"), sqlite3.connect(":memory:")]
    for conn in connections:
        conn.execute(f"CREATE TABLE {TABLE} (year_month INTEGER, metric TEXT, business_group TEXT, "
                     "unit_fname TEXT, amount DOUBLE)")
        conn.executemany(f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?, ?)", rows)
    yield connections
    for conn in connections:
        conn.close()


def execute(req, resolved, databases):
    compiled = compile(req, resolved)
    check_select(compiled.sql, {compiled.table})
    results = [conn.execute(compiled.sql).fetchall() for conn in databases]
    # an unordered GROUP BY may come back in either order
    assert (results[0] == results[1]) if " ORDER BY " in compiled.sql else sorted(results[0]) == sorted(results[1])
    return compiled, [tuple(round(v, 4) if isinstance(v, float) else v for v in row) for row in results[0]]


def test_year_to_date_is_the_sum_of_service_sales_months(resolved, databases):
    compiled, rows = execute(CompileRequest("sales_vs_target", 202609, "cumulative"), resolved, databases)
    assert 'BETWEEN 202601 AND 202609' in compiled.sql
    head = compiled.sql.split(" FROM ")[0]
    assert head.index('AS "ยอดขายบริการ (บาท)"') < head.index('AS "เป้ายอดขาย (บาท)"') < head.index("(%)")
    assert rows == [(1980, 1800, 110.0)]  # A 1080 + B 810 + C 90 against 900 + 900; no BG 8, no 202512 / 202610
    month, rows = execute(CompileRequest("sales_vs_target", 202609, "month"), resolved, databases)
    assert '"year_month" AS INTEGER) = 202609' in month.sql and rows == [(220, 200, 110.0)]


def test_breakdown_leaves_out_units_without_a_target(resolved, databases):
    compiled, rows = execute(CompileRequest("sales_vs_target", 202609, "cumulative", dimensions=("unit_fname",)),
                             resolved, databases)
    assert "HAVING" in compiled.sql and compiled.compare is None
    assert sorted(rows) == [("ฝ่าย A", 1080, 900, 120.0), ("ฝ่าย B", 810, 900, 90.0)]


@pytest.mark.parametrize("side,order,expected", [
    ("above", True, [("ฝ่าย A", 1080, 900, 120.0)]),
    ("below", False, [("ฝ่าย B", 810, 900, 90.0)]),
])
def test_threshold_keeps_the_asked_side_of_the_line(resolved, databases, side, order, expected):
    req = CompileRequest("sales_vs_target", 202609, "cumulative", dimensions=("unit_fname",), order_desc=order,
                         threshold=side)
    compiled, rows = execute(req, resolved, databases)
    assert rows == expected
    assert compiled.compare == f"แสดงเฉพาะหน่วยที่ ยอดขายเทียบเป้า (% Achievement) (%) {'≥' if side == 'above' else '<'} 100"
    assert compiled.sql.endswith(f"ORDER BY 4 {'DESC' if order else 'ASC'}")


def test_a_summed_period_compares_two_years_to_date(resolved, databases):
    metric = resolved["sales_vs_target"]
    req = CompileRequest("sales_vs_target", 202609, "cumulative", dimensions=("unit_fname",), base_period=202509)
    compiled, rows = execute(req, {**resolved, "sales_vs_target": replace(metric, ranking=None)}, databases)
    assert "BETWEEN 202501 AND 202509 OR" in compiled.sql and "BETWEEN 202601 AND 202609" in compiled.sql
    assert rows == []  # no unit has rows in both years to date


def test_an_official_total_needs_a_year_to_date_column(resolved):
    metric = replace(resolved["sales_vs_target"], official_total={"dataset": "t", "column": "c", "month_column": "m"})
    with pytest.raises(ValueError):
        compile(CompileRequest("sales_vs_target", 202609, "cumulative"), {"sales_vs_target": metric})


@pytest.mark.parametrize("question,side", [
    (QUESTION, "above"), ("ฝ่ายไหนยอดขายเกินเป้าบ้าง", "above"), ("ฝ่ายที่ทำได้ถึงเป้า", "above"),
    ("ฝ่ายไหนยังไม่ถึงเป้า", "below"), ("หน่วยงานที่ต่ำกว่าเป้า", "below"),
    ("มีฝ่ายไหนบ้างที่ไม่ผ่านเป้า", "below"), ("ฝ่ายไหนผ่านเป้า", "above"),  # sales 1.4.1 (live audit 502)
    ("ยอดขายเทียบเป้ารายฝ่าย", None), ("ฝ่ายที่เกินเป้าและฝ่ายที่ไม่ถึงเป้า", None),
])
def test_threshold_side_from_the_contract_words(resolved, question, side):
    assert _threshold_side(question, resolved["sales_vs_target"].ranking["threshold"]) == side


@pytest.mark.parametrize("intent_type", ["aggregation", "comparison", "ranking"])
def test_plan_reads_the_question_against_the_target(resolved, intent_type):
    """pass 1 may call "ยอดขายมากกว่าเป้า" a comparison: against the target, not against last year."""
    intent = {"intent_type": intent_type, "metric_id": "sales_vs_target", "dimensions": ["unit_fname"],
              "filters": [], "ordering": {"column": "achievement_pct", "direction": "DESC"}
              if intent_type == "comparison" else None}
    req, reason = plan_with_reason(intent, QUESTION, resolved, ["sales_vs_target"], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.base_period, req.threshold, req.order_desc) == (
        202609, "cumulative", None, "above", True)


def test_plan_keeps_totals_and_plain_breakdowns_without_a_threshold(resolved):
    total = {"intent_type": "comparison", "metric_id": "sales_vs_target", "dimensions": [], "filters": []}
    req, _ = plan_with_reason(total, "ยอดขายรวมทั้งบริษัทเทียบกับเป้า", resolved, ["sales_vs_target"], 202609, set())
    assert (req.dimensions, req.threshold, req.base_period) == ((), None, None)
    plain = {**total, "intent_type": "aggregation", "dimensions": ["unit_fname"]}
    req, _ = plan_with_reason(plain, "ยอดขายเทียบเป้ารายฝ่าย", resolved, ["sales_vs_target"], 202609, set())
    assert (req.threshold, req.order_desc) == (None, None)
    # targets sit at ฝ่าย level: a ส่วน breakdown is not declared and goes to free SQL
    sub_unit = {**plain, "dimensions": ["sub_unit_fname"]}
    assert plan_with_reason(sub_unit, "ส่วนไหนเกินเป้า", resolved, [], 202609, set()) == (
        None, "shape:dimension:sub_unit_fname")


def test_sync_validation_accepts_the_contract_and_rejects_bad_declarations(declared):
    columns = {"year_month", "metric", "amount", "business_group", "service_group", "product_code", "product_name",
               "sales_line", "sales_group", "sales_dept", "unit_fname", "sales_line_current", "sales_group_current",
               "sales_dept_current", "unit_fname_current", "geo_cluster", "geo_region_broad"}
    metric = declared[0]
    _validate_metric(metric, {"fact_sales": columns}, set())
    for bad in ({"extra_columns": [{"expr": "unknown", "name_th": "x"}]}, {"extra_columns": [{"expr": "actual"}]},
                {"extra_columns": []}, {"ranking": {"positive": "nope"}},
                {"ranking": {"threshold": {"value": "100", "above": ["เกินเป้า"]}}},
                {"ranking": {"threshold": {"value": 100}}},
                {"official_total": {"dataset": "fact_sales", "column": "amount", "month_column": "amount"}}):
        with pytest.raises(ValueError):
            _validate_metric({**metric, **bad}, {"fact_sales": columns}, set())


# pass 1 intents as the practice server logged them (gpt-4.1-mini, 2026-10-25 14:51–14:53)
OBSERVED = [
    ("หน่วยงานที่ยอดขายมากกว่าเป้ามีหน่วยไหนบ้าง",
     {"intent_type": "ranking", "metrics": ["amount", "target_amt"], "metric_id": "sales_vs_target",
      "dimensions": ["unit_fname"], "filters": [{"column": "metric", "operator": "=", "value": "actual"},
                                               {"column": "year_month", "operator": "BETWEEN", "value": [202601, 202609]}],
      "time_range": {"year": 2026, "month": 9, "cumulative": True}, "ordering": {"column": "amount", "direction": "DESC"},
      "matched_mappings": [{"keyword": "มากกว่าเป้า", "sql_condition": "x"}]},
     (202609, "cumulative", ("unit_fname",), (), "above", True)),
    ("ยอดขายรวมทั้งบริษัท ม.ค.-ก.ย. 2569 เทียบกับเป้า",
     {"intent_type": "comparison", "metrics": ["amount", "target_amt"], "metric_id": "sales_vs_target", "dimensions": [],
      "filters": [{"column": "metric", "operator": "IN", "value": ["actual", "target"]},
                  {"column": "year_month", "operator": "BETWEEN", "value": [202601, 202609]}],
      "time_range": {"year": 2026, "month": 9, "cumulative": True}, "ordering": None, "matched_mappings": []},
     (202609, "cumulative", (), (), None, None)),
    ("ยอดขายของฝ่ายบริหารงานกลาง และฝ่ายแสวงหาโอกาสและพัฒนาธุรกิจ ม.ค.-ก.ย. 2569 เทียบเป้า",
     {"intent_type": "comparison", "metrics": ["amount", "target_amt"], "metric_id": "sales_vs_target",
      "dimensions": ["unit_fname", "year_month"],
      "filters": [{"column": "unit_fname", "operator": "LIKE", "value": "%ฝ่ายบริหารงานกลาง%"},
                  {"column": "unit_fname", "operator": "LIKE", "value": "%ฝ่ายแสวงหาโอกาสและพัฒนาธุรกิจ%"},
                  {"column": "metric", "operator": "=", "value": "actual"},
                  {"column": "year_month", "operator": "BETWEEN", "value": [202601, 202609]}],
      "time_range": {"year": 2026, "month": 9, "cumulative": True}, "ordering": None, "matched_mappings": []},
     (202609, "cumulative", ("unit_fname",), ("unit_fname", "unit_fname"), None, None)),
    ("ยอดขายเทียบเป้า เดือนกันยายน 2569",
     {"intent_type": "comparison", "metrics": ["amount", "target_amt"], "metric_id": "sales_vs_target", "dimensions": [],
      "filters": [{"column": "year_month", "operator": "=", "value": 202609}],
      "time_range": {"year": 2026, "month": 9, "cumulative": False}, "ordering": None,
      "matched_mappings": [{"keyword": "ยอดขายเทียบเป้า", "sql_condition": "metric = 'actual' OR metric = 'target'"}]},
     (202609, "month", (), (), None, None)),
]


@pytest.mark.parametrize("question,intent,expected", OBSERVED)
def test_plan_takes_the_intents_pass_1_actually_writes(resolved, question, intent, expected):
    req, reason = plan_with_reason(intent, question, resolved, ["sales_vs_target"], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.dimensions, tuple(f["column"] for f in req.filters), req.threshold,
            req.order_desc) == expected


def test_a_filter_outside_the_definition_still_declines(resolved):
    """Only values the terms choose are dropped: metric = 'forecast' is not the metric's own definition."""
    intent = {**OBSERVED[0][1], "filters": [{"column": "metric", "operator": "=", "value": "forecast"}]}
    assert plan_with_reason(intent, QUESTION, resolved, [], 202609, set()) == (None, "shape:filter:metric")


def test_named_units_are_alternatives_and_keep_their_rows(resolved, databases):
    """Two LIKE filters on unit_fname are "A and B" (OR); a named unit without a target keeps its row."""
    filters = ({"column": "unit_fname", "operator": "LIKE", "value": "%ฝ่าย A%"},
               {"column": "unit_fname", "operator": "LIKE", "value": "%ฝ่าย C%"})
    req = CompileRequest("sales_vs_target", 202609, "cumulative", dimensions=("unit_fname",), filters=filters)
    compiled, rows = execute(req, resolved, databases)
    assert '("unit_fname" LIKE \'%ฝ่าย A%\' OR "unit_fname" LIKE \'%ฝ่าย C%\')' in compiled.sql
    assert sorted(rows) == [("ฝ่าย A", 1080, 900, 120.0), ("ฝ่าย C", 90, 0, None)]


@pytest.mark.parametrize("mapping,question", [
    ({"keyword": "ยอดขาย", "sql_condition": "metric = 'actual'"}, "ยอดขายรวมทั้งบริษัท ม.ค.-ก.ย. 2569 เทียบกับเป้า"),
    ({"keyword": "ยอดขายบริการรวมทั้งบริษัท", "sql_condition": "BUSINESS_GROUP != 'รายได้อื่น'"},
     "ยอดขายบริการรวมทั้งบริษัท ม.ค.-ก.ย. 2569 เทียบเป้า YTD ได้กี่ %"),
])
def test_invented_mappings_that_name_or_restate_the_metric_do_not_block(resolved, mapping, question):
    """Practice server 2026-10-25 15:0x: pass 1 named the metric's own value ("ยอดขายบริการ…") or repeated its
    selector (metric = 'actual') as a mapping — both fell to free SQL and summed 8.รายได้อื่น again."""
    intent = {"intent_type": "comparison", "metric_id": "sales_vs_target", "dimensions": [], "filters": [],
              "time_range": {"year": 2026, "month": 9, "cumulative": True}, "matched_mappings": [mapping]}
    req, reason = plan_with_reason(intent, question, resolved, [], 202609, set())
    assert reason is None and (req.period, req.mode) == (202609, "cumulative")


def test_a_mapping_with_a_real_selection_still_blocks(resolved):
    intent = {"intent_type": "aggregation", "metric_id": "sales_vs_target", "dimensions": [], "filters": [],
              "matched_mappings": [{"keyword": "มือถือ", "sql_condition": "business_group = '3.Mobile'"}]}
    assert plan_with_reason(intent, "ยอดขายมือถือเทียบเป้า", resolved, [], 202609, set()) == (
        None, "mapping_triggered:มือถือ")


@pytest.mark.parametrize("question,time_range,expected", [
    ("ยอดขายของฝ่าย A ม.ค.-ก.ย. 2569 เทียบเป้า", {"year": 2026, "month": 9, "cumulative": False}, (202609, "cumulative")),
    ("ยอดขายเทียบเป้า มกราคม ถึง มิถุนายน 2569", {"year": 2026, "month": 6, "cumulative": False}, (202606, "cumulative")),
    ("ยอดขายเทียบเป้า เดือนกันยายน 2569", {"year": 2026, "month": 9, "cumulative": False}, (202609, "month")),
])
def test_a_january_span_in_the_question_is_a_year_to_date(resolved, question, time_range, expected):
    """Practice round 3: "ม.ค.-ก.ย. 2569" arrived as time_range {month: 9, cumulative: false} and compiled September alone."""
    intent = {"intent_type": "aggregation", "metric_id": "sales_vs_target", "dimensions": ["unit_fname"], "filters": [],
              "time_range": time_range}
    req, reason = plan_with_reason(intent, question, resolved, [], 202609, set())
    assert reason is None and (req.period, req.mode) == expected


@pytest.mark.parametrize("intent_type", ["lookup", "detail"])
def test_a_lookup_against_the_target_is_read_like_an_aggregation(resolved, intent_type):
    """Practice rounds 3 (lookup) and 8 (detail): the detail one went to free SQL and returned 0 rows."""
    intent = {"intent_type": intent_type, "metric_id": "sales_vs_target", "dimensions": ["unit_fname"], "filters": []}
    req, reason = plan_with_reason(intent, QUESTION, resolved, [], 202609, set())
    assert reason is None and (req.threshold, req.order_desc, req.base_period) == ("above", True, None)


@pytest.mark.parametrize("column", ["achievement_diff", "amount - target_amt", "amount"])
def test_a_freely_named_ordering_ranks_by_the_metric(resolved, column):
    """Practice rounds 3 and 5: "ฝ่ายไหนทำยอดขายได้เกินเป้ามากที่สุด 3 อันดับ" ordered by a name pass 1 made up."""
    intent = {"intent_type": "ranking", "metric_id": "sales_vs_target", "dimensions": ["unit_fname"], "filters": [],
              "ordering": {"column": column, "direction": "DESC"}, "limit": 3}
    req, reason = plan_with_reason(intent, "ฝ่ายไหนทำยอดขายได้เกินเป้ามากที่สุด 3 อันดับ", resolved, [], 202609, set())
    assert reason is None and (req.threshold, req.order_desc, req.limit) == ("above", True, 3)


@pytest.mark.parametrize("question,limit", [("ฝ่ายไหนยอดขายยังไม่ถึงเป้า", None),
                                            ("ฝ่ายไหนทำยอดขายได้เกินเป้ามากที่สุด 3 อันดับ", 3)])
def test_a_threshold_list_keeps_a_limit_only_when_the_question_gives_a_number(resolved, question, limit):
    """Live audit 471 (2026-10-26): pass 1 sent limit 10 for "ยังไม่ถึงเป้า" and the answer said 10 units in all."""
    intent = {"intent_type": "aggregation", "metric_id": "sales_vs_target", "dimensions": ["unit_fname"], "filters": [],
              "ordering": {"column": "amount", "direction": "ASC"}, "limit": 10 if limit is None else limit}
    req, reason = plan_with_reason(intent, question, resolved, [], 202609, set())
    assert reason is None and req.limit == limit


PORTAL_SCOPE = {"year_month": [*range(202501, 202513), *range(202601, 202610)]}


@pytest.mark.parametrize("period_filter,expected", [
    ({"column": "year_month", "operator": "BETWEEN", "value": [202501, 202609]}, ((202609, "cumulative"), None)),
    ({"column": "year_month", "operator": "IN", "value": PORTAL_SCOPE["year_month"]}, ((202609, "cumulative"), None)),
    ({"column": "year_month", "operator": "BETWEEN", "value": [202503, 202609]}, (None, "period_filter:range")),
])
def test_a_period_filter_that_restates_the_portal_scope_is_not_the_question_period(resolved, period_filter, expected):
    """Live audit 473 (portal): pass 1 wrote the scope 202501…202609 as BETWEEN beside time_range {2026, 9, cumulative}."""
    intent = {"intent_type": "ranking", "metric_id": "sales_vs_target", "dimensions": ["unit_fname"],
              "filters": [{"column": "metric", "operator": "=", "value": "actual"}, period_filter],
              "time_range": {"year": 2026, "month": 9, "cumulative": True},
              "ordering": {"column": "amount", "direction": "DESC"}}
    req, reason = plan_with_reason(intent, QUESTION, resolved, [], 202609, set(), None, PORTAL_SCOPE)
    assert ((req.period, req.mode) if req else None, reason) == expected
    # without the scope the same span is a multi-year sum the metric cannot express
    assert plan_with_reason(intent, QUESTION, resolved, [], 202609, set())[1] == "period_filter:range"


@pytest.mark.parametrize("value_filter", [None, {"column": "amount", "operator": "<", "value": "target"}])
def test_not_passing_the_target_keeps_the_units_below_the_line(resolved, value_filter):
    """Live audit 502 (portal, sales 1.4.0): "มีฝ่ายไหนบ้างที่ไม่ผ่านเป้า" compiled without a side and listed all 29 units
    with a target (24 below). A value filter that spells the side is dropped like revenue_vs_target's."""
    intent = {"intent_type": "ranking", "metric_id": "sales_vs_target", "dimensions": ["unit_fname"],
              "filters": [{"column": "metric", "operator": "=", "value": "actual"},
                          {"column": "year_month", "operator": "BETWEEN", "value": [202601, 202609]},
                          *([value_filter] if value_filter else [])],
              "time_range": {"year": 2026, "month": 9, "cumulative": True},
              "ordering": {"column": "amount", "direction": "ASC"}, "limit": 10}
    req, reason = plan_with_reason(intent, "มีฝ่ายไหนบ้างที่ไม่ผ่านเป้า", resolved, [], 202609, set(), None, PORTAL_SCOPE)
    assert reason is None
    assert (req.period, req.mode, req.filters, req.threshold, req.order_desc, req.limit) == (
        202609, "cumulative", (), "below", False, None)


UNIT = "ฝ่ายขายและปฏิบัติการลูกค้า ภาคกลางตอนล่าง"
AUDIT_503 = {  # practice server s141, the portal question of live audit 503 / 506
    "intent_type": "aggregation", "metrics": ["sales_vs_target"], "metric_id": "sales_vs_target",
    "dimensions": ["service_group"], "filters": [{"column": "sub_unit_fname", "operator": "=", "value": UNIT}],
    "time_range": {"year": 2026, "month": 9, "cumulative": True},
    "ordering": {"column": "sales_vs_target", "direction": "ASC"}, "limit": None,
    "matched_mappings": [{"keyword": "กลุ่มบริการ", "sql_condition": "business_group = '7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม'"}]}
LABELS = {"service_group": "กลุ่มบริการ (รูปแบบ 'N.M.ชื่อ' เช่น 4.3.กลุ่มบริการวงจรเช่า (Datacom))", "unit_fname": "ฝ่าย"}
LOOKUP = [{"keyword": UNIT, "column_name": column, "column_value": UNIT}
          for column in ("sub_unit_fname", "unit_fname_current", "unit_fname")]


def test_a_unit_filter_on_its_cost_center_moves_to_the_declared_unit_column(resolved):
    """Live audit 503 (portal): "<ฝ่าย> มีกลุ่มบริการไหนบ้างที่ไม่ผ่านเป้า" → 0 rows. The mapping pass 1 made up on the level
    word "กลุ่มบริการ" no longer blocks, and the ฝ่าย name it put on sub_unit_fname (undeclared — targets sit at ฝ่าย level)
    goes to unit_fname, the first declared column the value lookup found it in."""
    question = f"{UNIT} มีกลุ่มบริการไหนบ้างที่ไม่ผ่านเป้า"
    req, reason = plan_with_reason(AUDIT_503, question, resolved, [], 202609, set(), LABELS, PORTAL_SCOPE,
                                   value_matches=LOOKUP)
    assert reason is None
    assert (req.period, req.mode, req.dimensions, req.filters, req.threshold, req.order_desc) == (
        202609, "cumulative", ("service_group",), ({"column": "unit_fname", "operator": "=", "value": UNIT},),
        "below", False)


def test_without_the_level_label_or_the_lookup_the_old_declines_stay(resolved):
    question = f"{UNIT} มีกลุ่มบริการไหนบ้างที่ไม่ผ่านเป้า"
    assert plan_with_reason(AUDIT_503, question, resolved, [], 202609, set(), None, PORTAL_SCOPE,
                            value_matches=LOOKUP) == (None, "mapping_triggered:กลุ่มบริการ")
    assert plan_with_reason(AUDIT_503, question, resolved, [], 202609, set(), LABELS, PORTAL_SCOPE) == (
        None, "shape:filter:sub_unit_fname")
    # a value the lookup found only outside the declared columns still declines
    outside = [item for item in LOOKUP if item["column_name"] == "sub_unit_fname"]
    assert plan_with_reason(AUDIT_503, question, resolved, [], 202609, set(), LABELS, PORTAL_SCOPE,
                            value_matches=outside)[1] == "shape:filter:sub_unit_fname"
