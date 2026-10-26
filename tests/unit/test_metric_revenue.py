"""Revenue chooses a declared grain and reads reclassified YTD at the asked period."""

from dataclasses import fields, replace
from pathlib import Path
import sqlite3

import duckdb
import pytest
from sqlalchemy import create_engine, text
import yaml

from app.services.ai.metric_compiler import CompileRequest, Metric, compile, dimension_labels, plan_with_reason, resolve
from app.services.ai.sql_invariants import check
from app.services.database_adapter import check_select


CONTRACT = Path(__file__).parent.parent / "fixtures" / "revenue_metrics_draft.yaml"
TOTAL = "feed_revenue_fact_total_monthly"
BU = "feed_revenue_fact_bu_monthly"
ORG = "feed_revenue_fact_org_monthly"
BG1 = "1.Hard Infrastructure"
BG4 = "4.Fixed Line & Broadband"
BG8 = "8.รายได้อื่น"


@pytest.fixture(scope="module")
def metrics():
    contract = yaml.safe_load(CONTRACT.read_text())
    rows = []
    for declaration in contract["metrics"]:
        values = {f.name: declaration.get(f.name) for f in fields(Metric)}
        values["metric_id"] = declaration["id"]
        values["synonyms"] = tuple(values["synonyms"] or ())
        values["terms"] = values["terms"] or {}
        values["datasets"] = tuple({**item, "name": f"feed_{contract['domain']}_{item['name']}"}
                                   for item in values["datasets"])
        total = values["official_total"]
        values["official_total"] = {**total, "dataset": f"feed_{contract['domain']}_{total['dataset']}"}
        rows.append(Metric(**values))
    assert [m.metric_id for m in rows] == ["revenue"]
    return rows


@pytest.fixture(scope="module")
def resolved(metrics):
    return resolve(metrics)


@pytest.fixture(scope="module")
def databases():
    bu_rows, org_rows, total_rows = [], [], []
    for month in range(1, 10):
        period = 202600 + month
        bu_rows += [(period, 1, BG1, 100, 100 * month),
                    (period, 4, BG4, 200, 200 * month),
                    (period, 8, BG8, 30, 210 if month == 9 else 30 * month)]
        org_rows += [(period, "D1", "U1", "C1", 130, 1110 if month == 9 else 130 * month),
                     (period, "D2", "U2", "C2", 200, 200 * month)]
        total_rows.append((period, 330, 2910 if month == 9 else 330 * month))
    connections = [duckdb.connect(":memory:"), sqlite3.connect(":memory:")]
    for conn in connections:
        conn.execute(f"CREATE TABLE {BU} (year_month INTEGER, bu_seq INTEGER, bu TEXT, "
                     "revenue DOUBLE, revenue_ytd DOUBLE)")
        conn.executemany(f"INSERT INTO {BU} VALUES (?, ?, ?, ?, ?)", bu_rows)
        conn.execute(f"CREATE TABLE {ORG} (year_month INTEGER, division_name TEXT, unit_name TEXT, "
                     "cost_center TEXT, revenue DOUBLE, revenue_ytd DOUBLE)")
        conn.executemany(f"INSERT INTO {ORG} VALUES (?, ?, ?, ?, ?, ?)", org_rows)
        conn.execute(f"CREATE TABLE {TOTAL} (year_month INTEGER, revenue DOUBLE, revenue_ytd DOUBLE)")
        conn.executemany(f"INSERT INTO {TOTAL} VALUES (?, ?, ?)", total_rows)
    yield connections
    for conn in connections:
        conn.close()


def execute(req, resolved, databases):
    compiled = compile(req, resolved)
    check_select(compiled.sql, {compiled.table})
    assert not compiled.sql.endswith(";")
    results = [conn.execute(compiled.sql).fetchall() for conn in databases]
    # GROUP BY without ORDER BY need not return groups in the same order.
    if " ORDER BY " not in compiled.sql:
        results = [sorted(rows) for rows in results]
    assert results[0] == results[1]
    return compiled, results[0]


@pytest.mark.parametrize("official_total_ok", [True, False])
@pytest.mark.parametrize("mode,expected", [("cumulative", 2910), ("month", 330)])
def test_total_uses_the_official_or_smallest_table(resolved, databases, official_total_ok, mode, expected):
    req = CompileRequest("revenue", 202609, mode, official_total_ok=official_total_ok)
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == TOTAL and rows == [(expected,)]
    assert ("CASE WHEN (1 = 1)" in compiled.sql) is (not official_total_ok)
    assert check(compiled.sql, {"revenue_ytd"}, {"revenue"}, ["year_month"]) == []


@pytest.mark.parametrize("mode,expected", [
    ("cumulative", [(BG1, 900), (BG4, 1800), (BG8, 210)]),
    ("month", [(BG1, 100), (BG4, 200), (BG8, 30)]),
])
def test_by_bu_reads_one_period(resolved, databases, mode, expected):
    compiled, rows = execute(CompileRequest("revenue", 202609, mode, dimensions=("bu",)), resolved, databases)
    assert compiled.table == BU and rows == expected
    assert "= 202609" in compiled.sql and "BETWEEN" not in compiled.sql
    assert check(compiled.sql, {"revenue_ytd"}, {"revenue"}, ["year_month"]) == []


def test_a_filter_alone_selects_the_bu_table(resolved, databases):
    req = CompileRequest("revenue", 202609, "cumulative", filters=({"column": "bu", "operator": "=", "value": BG8},))
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == BU and rows == [(210,)]


@pytest.mark.parametrize("ranking", [False, True])
def test_by_unit_selects_the_org_table(resolved, databases, ranking):
    req = CompileRequest("revenue", 202609, "cumulative", dimensions=("unit_name",),
                         order_desc=True if ranking else None, limit=1 if ranking else None)
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == ORG
    assert rows == ([("U2", 1800)] if ranking else [("U1", 1110), ("U2", 1800)])


def test_comparison_keeps_each_terms_period_predicate(resolved, databases):
    req = CompileRequest("revenue", 202609, "cumulative", dimensions=("bu",), base_period=202608)
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == BU
    assert rows == [(BG1, 800, 900, 100), (BG4, 1600, 1800, 200), (BG8, 240, 210, -30)]
    assert check(compiled.sql, {"revenue_ytd"}, {"revenue"}, ["year_month"]) == []


@pytest.mark.parametrize("dimensions,filters", [
    (("bu", "unit_name"), ()),
    (("bu",), ({"column": "unit_name", "operator": "=", "value": "U1"},)),
])
def test_incompatible_dimensions_and_filters_decline(resolved, dimensions, filters):
    req = CompileRequest("revenue", 202609, "cumulative", dimensions=dimensions, filters=filters)
    with pytest.raises(ValueError, match="dataset"):
        compile(req, resolved)
    intent = {"intent_type": "aggregation", "metric_id": "revenue", "dimensions": list(dimensions),
              "filters": list(filters), "time_range": {"year": 2026, "month": 9, "cumulative": True}}
    assert plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL, BU, ORG}) == (None, "shape:dimension_set")


@pytest.mark.parametrize("intent_type,dimensions,table,expected", [
    ("ranking", ["bu"], BU, [(BG4, 1800), (BG1, 900), (BG8, 210)]),
    ("aggregation", [], TOTAL, [(2910,)]),
])
def test_planned_requests_use_the_chosen_table(resolved, databases, intent_type, dimensions, table, expected):
    intent = {"intent_type": intent_type, "metric_id": "revenue", "dimensions": dimensions,
              "filters": [{"column": "year_month", "operator": "=", "value": 202609}],
              "time_range": {"year": 2026, "month": 9, "cumulative": True}}
    req, reason = plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL, BU, ORG})
    assert reason is None and req.filters == ()
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == table and rows == expected


def test_planned_comparison_removes_the_period_dimension(resolved, databases):
    intent = {"intent_type": "comparison", "metric_id": "revenue", "dimensions": ["bu", "year_month"],
              "filters": [{"column": "year_month", "operator": "IN", "value": [202608, 202609]}],
              "time_range": {"year": 2026, "month": 9, "cumulative": True}}
    req, reason = plan_with_reason(intent, "รายได้เทียบเดือนก่อน", resolved, [], 202609, {TOTAL, BU, ORG})
    assert reason is None and req.dimensions == ("bu",) and req.filters == ()
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == BU and rows[-1] == (BG8, 240, 210, -30)


def test_equal_size_datasets_keep_declaration_order(resolved):
    metric = replace(resolved["revenue"], datasets=(
        {"name": "first", "dimensions": ["bu", "bu_seq"]},
        {"name": "second", "dimensions": ["bu", "division_name"]}))
    req = CompileRequest("revenue", 202609, "cumulative", dimensions=("bu",))
    assert compile(req, {"revenue": metric}).table == "first"


def test_smaller_dataset_wins_even_when_declared_later(resolved, databases):
    metric = replace(resolved["revenue"], datasets=tuple(reversed(resolved["revenue"].datasets)))
    req = CompileRequest("revenue", 202609, "cumulative", official_total_ok=False)
    compiled, rows = execute(req, {"revenue": metric}, databases)
    assert compiled.table == TOTAL and rows == [(2910,)]


def test_without_cumulative_reuses_the_summed_month_path(resolved, databases):
    metric = replace(resolved["revenue"], period={"column": "year_month", "value": {"month": "revenue"}},
                     official_total=None)
    req = CompileRequest("revenue", 202609, "cumulative", dimensions=("bu",))
    compiled, rows = execute(req, {"revenue": metric}, databases)
    assert compiled.table == BU and "BETWEEN 202601 AND 202609" in compiled.sql
    assert rows == [(BG1, 900), (BG4, 1800), (BG8, 270)]


@pytest.mark.parametrize("term", [{}, {"where": None}, {"where": ""}, {"where": "  "}])
@pytest.mark.parametrize("base_period", [None, 202608])
def test_empty_where_forms_include_every_row(resolved, databases, term, base_period):
    metric = replace(resolved["revenue"], terms={"rev": term})
    req = CompileRequest("revenue", 202609, "cumulative", dimensions=("bu",), base_period=base_period)
    compiled, rows = execute(req, {"revenue": metric}, databases)
    assert "CASE WHEN (1 = 1)" in compiled.sql
    assert rows == ([(BG1, 900), (BG4, 1800), (BG8, 210)] if base_period is None else
                    [(BG1, 800, 900, 100), (BG4, 1600, 1800, 200), (BG8, 240, 210, -30)])


@pytest.mark.parametrize("term", [{"where": 5}, {"where": False}, None, "revenue", []])
def test_invalid_terms_raise_value_error(resolved, term):
    metric = replace(resolved["revenue"], terms={"rev": term})
    with pytest.raises(ValueError):
        compile(CompileRequest("revenue", 202609, "cumulative", dimensions=("bu",)), {"revenue": metric})


def test_referenced_metrics_must_share_datasets(resolved, databases):
    metric = resolved["revenue"]
    derived = replace(metric, metric_id="derived", expr="revenue", official_total=None)
    req = CompileRequest("derived", 202609, "cumulative", dimensions=("bu",))
    _, rows = execute(req, resolved | {"derived": derived}, databases)
    assert rows == [(BG1, 900), (BG4, 1800), (BG8, 210)]
    incompatible = replace(derived, datasets=tuple(reversed(metric.datasets)))
    with pytest.raises(ValueError, match="same dataset"):
        compile(req, resolved | {"derived": incompatible})


def test_dimension_labels_use_each_grains_table(metrics):
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE schema_metadata "
                              "(table_name TEXT, column_name TEXT, description TEXT, status TEXT)"))
            conn.execute(text("INSERT INTO schema_metadata VALUES "
                              "(:bu, 'bu', 'กลุ่มธุรกิจ — ระดับ BG', 'active'), "
                              "(:org, 'unit_name', 'ฝ่าย — ระดับหน่วยงาน', 'active'), "
                              "(:total, 'bu', 'ผิดตาราง', 'active')"), {"bu": BU, "org": ORG, "total": TOTAL})
        assert dimension_labels(metrics, engine) == {"bu": "กลุ่มธุรกิจ", "unit_name": "ฝ่าย"}
    finally:
        engine.dispose()
