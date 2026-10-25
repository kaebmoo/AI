"""Period invariants must catch audit 407 and accept every compiler shape."""

from dataclasses import fields, replace
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from unittest.mock import Mock

import duckdb
import pytest
import yaml

from app.services.ai.metric_compiler import CompileRequest, Metric, compile, resolve
from app.services.ai.sql_invariants import Violation, check


PIT = {"amount_ytd", "ebt", "expense", "sales_base_revenue", "hr_expense", "ebt_ex_personnel"}
SUMMABLE = {"amount", "ebt_month", "expense_month", "sales_base_revenue_month", "hr_expense_month",
            "ebt_ex_personnel_month"}
PERIOD = ["time_key"]
CONTRACT = Path(__file__).parent.parent / "fixtures" / "ebt_metrics_1_6_0.yaml"
I1 = Violation("I1", "ytd_summed_across_periods", ("amount_ytd",), True)
I2 = Violation("I2", "ytd_without_period", ("amount_ytd",), True)
I3 = Violation("I3", "month_summed_as_ytd", ("ebt_month",), False)

AUDIT_407 = """SELECT
    cost_center,
    division,
    SUM(COALESCE(amount_ytd, 0)) - SUM(COALESCE(CASE WHEN group_1 LIKE '%01.ค่าใช้จ่ายตอบแทนแรงงาน-ER%' THEN amount_ytd ELSE 0 END, 0)) AS "EBT สะสม (บาท)"
FROM
    feed_ebt_fact_ebt
WHERE
    CAST(time_key AS INTEGER) BETWEEN 202601 AND 202609
    AND division IN ('สายงานขายและปฏิบัติการลูกค้า 1', 'สายงานขายและปฏิบัติการลูกค้า 2')
    AND measure_type = 'SUBTOTAL'
    AND group_1 = 'รวมรายได้ทั้งสิ้น'
GROUP BY
    cost_center,
    division
ORDER BY
    "EBT สะสม (บาท)" DESC
LIMIT 10
"""


def test_audit_407():
    assert check(AUDIT_407, PIT, SUMMABLE, PERIOD) == [I1]


@pytest.fixture(scope="module")
def metrics():
    contract = yaml.safe_load(CONTRACT.read_text())
    rows = []
    for declaration in contract["metrics"]:
        values = {f.name: declaration.get(f.name) for f in fields(Metric)}
        values["metric_id"] = declaration["id"]
        values["synonyms"] = tuple(values["synonyms"] or ())
        values["dimensions"] = tuple(values["dimensions"]) if values["dimensions"] is not None else None
        values["terms"] = values["terms"] or {}
        if values["dataset"] is not None:
            values["dataset"] = f"feed_{contract['domain']}_{values['dataset']}"
        if values["official_total"] is not None:
            total = values["official_total"]
            values["official_total"] = {**total, "dataset": f"feed_{contract['domain']}_{total['dataset']}"}
        rows.append(Metric(**values))
    assert [m.metric_id for m in rows] == ["ebt", "ebt_excluding_personnel", "ebt_margin"]
    return rows


@pytest.fixture(scope="module")
def resolved(metrics):
    return resolve(metrics)


@pytest.mark.parametrize("metric_id", ["ebt", "ebt_excluding_personnel", "ebt_margin"])
@pytest.mark.parametrize("mode", ["cumulative", "month"])
@pytest.mark.parametrize("shape", [
    {},
    {"dimensions": ("sub_unit",), "order_desc": True, "limit": 10},
    {"filters": ({"column": "sub_unit", "operator": "=", "value": "x"},)},
    {"base_period": 202509},
    {"base_period": 202509, "dimensions": ("sub_unit",), "change": "up"},
])
def test_compiler_shapes(resolved, metric_id, mode, shape):
    sql = compile(CompileRequest(metric_id, 202609, mode, **shape), resolved).sql
    assert check(sql, PIT, SUMMABLE, PERIOD) == []


@pytest.mark.parametrize("mode", ["cumulative", "month"])
def test_compiler_ranking(resolved, mode):
    margin = replace(resolved["ebt_margin"], ranking={"scope": "is_hq = 0", "base": "rev - other", "base_name_th": "ฐาน"})
    sql = compile(CompileRequest("ebt_margin", 202609, mode, dimensions=("sub_unit",), order_desc=True, limit=10),
                  resolved | {"ebt_margin": margin}).sql
    assert check(sql, PIT, SUMMABLE, PERIOD) == []


@pytest.mark.parametrize("predicate,pinned", [
    ("CAST(time_key AS INTEGER) = 202609", True),
    ("time_key BETWEEN 202601 AND 202609", False),
])
@pytest.mark.parametrize("source", ["cte", "subquery"])
def test_source_period_is_seen_through(source, predicate, pinned):
    body = f"SELECT * FROM feed_ebt_fact_ebt WHERE {predicate}"
    if source == "cte":
        sql = f"WITH x AS ({body}) SELECT a.cost_center, SUM(COALESCE(a.amount_ytd,0)) FROM x a GROUP BY 1"
    else:
        sql = f"SELECT a.cost_center, SUM(COALESCE(a.amount_ytd,0)) FROM ({body}) a GROUP BY 1"
    assert check(sql, PIT, SUMMABLE, PERIOD) == ([] if pinned else [I1])


@pytest.mark.parametrize("predicate", [
    "time_key::INTEGER = 202609",
    "TRY_CAST(time_key AS INTEGER) = 202609",
    "time_key = '202609'",
    "202609 = CAST(f.time_key AS INTEGER)",
    "time_key IN (202609)",
    "time_key = (SELECT MAX(time_key) FROM feed_ebt_fact_ebt)",
    "(SELECT MAX(time_key) FROM feed_ebt_fact_ebt) = time_key",
    "cost_center = '1' AND (time_key = 202609 AND division = 'x')",
])
def test_single_period_predicates(predicate):
    sql = f"SELECT SUM(f.amount_ytd) FROM feed_ebt_fact_ebt f WHERE {predicate}"
    assert check(sql, PIT, SUMMABLE, PERIOD) == []


@pytest.mark.parametrize("tail", [
    "WHERE time_key IN (202608, 202609)",
    "WHERE time_key >= 202601",
    "",
    "WHERE time_key = 202609 OR cost_center = '1'",
    "WHERE time_key = other_column",
    "WHERE time_key IN (other_column)",
    "WHERE cost_center = (SELECT cost_center FROM f WHERE time_key = 202609)",
])
@pytest.mark.parametrize("function", ["SUM", "AVG"])
def test_unpinned_aggregates(tail, function):
    sql = f"SELECT {function}(COALESCE(amount_ytd, 0)) FROM feed_ebt_fact_ebt {tail}"
    assert check(sql, PIT, SUMMABLE, PERIOD) == [I1]


@pytest.mark.parametrize("sql,expected", [
    ("SELECT time_key, SUM(amount_ytd) FROM f GROUP BY time_key", []),
    ("SELECT SUM(amount_ytd) FROM f GROUP BY CAST(time_key AS INTEGER)", []),
    ("SELECT SUM(amount_ytd) OVER (PARTITION BY time_key) FROM f", []),
    ("SELECT AVG(amount_ytd) OVER (PARTITION BY CAST(time_key AS INTEGER)) FROM f", []),
    ("SELECT SUM(amount_ytd) OVER (ORDER BY time_key) FROM f", [I1]),
    ("SELECT SUM(amount_ytd), SUM(amount_ytd) OVER (PARTITION BY time_key) FROM f", [I1]),
    ("SELECT SUM(CASE WHEN time_key = 202609 THEN amount_ytd END) - "
     "SUM(CASE WHEN time_key = 202509 THEN amount_ytd END) FROM feed_ebt_fact_ebt "
     "WHERE time_key IN (202509, 202609)", []),
    ("SELECT SUM(COALESCE(CASE WHEN x = 1 AND time_key = 202609 THEN amount_ytd END, 0)) FROM f", []),
    ("SELECT SUM(CASE WHEN x = 1 OR time_key = 202609 THEN amount_ytd END) FROM f", [I1]),
    ("SELECT cost_center, amount_ytd FROM feed_ebt_fact_ebt WHERE cost_center = '1'", [I2]),
    ("SELECT cost_center, time_key, amount_ytd FROM feed_ebt_fact_ebt WHERE cost_center = '1'", []),
    ("SELECT cost_center, amount_ytd FROM feed_ebt_fact_ebt WHERE time_key = 202609", []),
    ("SELECT amount_ytd FROM f WHERE time_key = 202609 OR x = 1", []),
    ("SELECT MAX(amount_ytd) FROM f", [I2]),
    ("SELECT amount_ytd FROM f ORDER BY time_key", [I2]),
    ("SELECT SUM(ebt_month) FROM feed_ebt_fact_ebt_total_monthly "
     "WHERE time_key BETWEEN 202601 AND 202609", [I3]),
    ("SELECT SUM(ebt_month) FROM feed_ebt_fact_ebt_total_monthly WHERE time_key = 202609", []),
    ("SELECT SUM(amount_ytd) FROM f JOIN g ON f.k = g.k AND g.time_key = 202609", []),
    ("SELECT amount_ytd FROM f JOIN g ON f.k = g.k AND g.time_key >= 202601", []),
    ("SELECT SUM(amount_ytd) FROM f JOIN g ON g.time_key = 202609 OR f.k = g.k", [I1]),
    ("WITH x AS (SELECT amount_ytd FROM f) SELECT * FROM x WHERE time_key = 202609", [I2]),
    ("SELECT * FROM (SELECT SUM(amount_ytd) FROM f) x WHERE time_key = 202609", [I1]),
    ("SELECT (SELECT SUM(amount_ytd) FROM f) FROM g WHERE time_key = 202609", [I1]),
    ("SELECT amount_ytd, (SELECT time_key FROM g) FROM f", [I2]),
    ("WITH x AS (SELECT * FROM f WHERE time_key = 202609), y AS (SELECT * FROM x) "
     "SELECT SUM(amount_ytd) FROM y", []),
    ("WITH x AS (SELECT * FROM f WHERE time_key = 202609), y AS (SELECT * FROM g) "
     "SELECT SUM(amount_ytd) FROM x CROSS JOIN y", [I1]),
    ("WITH x AS (SELECT * FROM f WHERE time_key = 202609) "
     "SELECT SUM(amount_ytd) FROM f JOIN x ON f.k = x.k", []),
    ("WITH x AS (SELECT * FROM f WHERE time_key = 202609) "
     "SELECT amount_ytd FROM x", []),
    ("WITH x AS (SELECT * FROM f WHERE time_key = 202609) "
     "SELECT SUM(amount_ytd) FROM (WITH x AS (SELECT * FROM g) SELECT * FROM x) y", [I1]),
    ("SELECT SUM(amount_ytd) FROM f UNION ALL SELECT SUM(amount_ytd) FROM g WHERE time_key = 202609", [I1]),
])
def test_block_invariants(sql, expected):
    assert check(sql, PIT, SUMMABLE, PERIOD) == expected


def test_codes_merge_columns_sort_and_preserve_unaggregated_occurrences():
    sql = 'SELECT SUM(f."AMOUNT_YTD"), AVG(f.EBT), f.amount_ytd, f.expense, SUM(f.ebt_month), SUM(f.amount) FROM f'
    assert check(sql, PIT, SUMMABLE, PERIOD) == [
        Violation("I1", "ytd_summed_across_periods", ("amount_ytd", "ebt"), True),
        Violation("I2", "ytd_without_period", ("amount_ytd", "expense"), True),
        Violation("I3", "month_summed_as_ytd", ("amount", "ebt_month"), False),
    ]


@pytest.mark.parametrize("sql", ["nonsense SQL", "SELECT (", "SELECT amount_ytd FROM f; SELECT 1", ""])
def test_invalid_or_multiple_statements(sql):
    assert check(sql, PIT, SUMMABLE, PERIOD) == []


@pytest.mark.parametrize("pit,periods", [((), PERIOD), (PIT, [])])
def test_missing_context_does_not_parse(monkeypatch, pit, periods):
    from app.services.ai import sql_invariants

    monkeypatch.setattr(sql_invariants, "_parser_conn", object())
    assert check("SELECT SUM(amount_ytd), SUM(ebt_month) FROM f", iter(pit), SUMMABLE, periods) == []


def test_case_insensitive_context_and_alternate_period():
    sql = 'SELECT SUM(f."AMOUNT_YTD") FROM f WHERE TRY_CAST(f.effective_month AS INTEGER) = 202609'
    assert check(sql, iter(["AMOUNT_YTD"]), iter(SUMMABLE), ["TIME_KEY", "EFFECTIVE_MONTH"]) == []


def test_duckdb_2_cte_body_shape(monkeypatch):
    from app.services.ai import sql_invariants

    sql = "WITH x AS (SELECT * FROM f WHERE time_key = 202609) SELECT SUM(amount_ytd) FROM x"
    with duckdb.connect(":memory:") as conn:
        tree = json.loads(conn.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    body = tree["statements"][0]["node"]["cte_map"]["map"][0]["value"]
    body["query_node"] = body.pop("query")["node"]
    parser = Mock()
    cursor = parser.cursor.return_value
    cursor.execute.return_value.fetchone.return_value = (json.dumps(tree),)
    monkeypatch.setattr(sql_invariants, "_parser_conn", parser)
    assert check(sql, PIT, SUMMABLE, PERIOD) == []
    cursor.close.assert_called_once_with()


def test_concurrent_calls_use_independent_cursors():
    queries = ["SELECT SUM(amount_ytd) FROM f", "SELECT SUM(amount_ytd) FROM f WHERE time_key = 202609"] * 8
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda sql: check(sql, PIT, SUMMABLE, PERIOD), queries))
    assert results == [[I1], []] * 8
