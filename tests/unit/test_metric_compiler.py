"""Contract-backed metric compilation, executed unchanged by DuckDB and SQLite."""

from dataclasses import asdict, fields, replace
import json
import logging
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import duckdb
import pytest
from sqlalchemy import create_engine, text
import yaml

from app.models.schema_models import SchemaMetric
from app.services.ai.metric_compiler import (
    CompileRequest, Metric, compile, dimension_labels, load_metrics, match_metrics, metric_catalog,
    metric_note, resolve, supports,
)
from app.services.database_adapter import check_select


LIVE_CONTRACT = Path("/Users/seal/Documents/GitHub/_worktrees/NT-Report-metrics/DataFeed/contracts/ebt.yaml")
CONTRACT = Path(__file__).parent.parent / "fixtures" / "ebt_metrics_1_5_0.yaml"
S1 = "สายงานขายและปฏิบัติการลูกค้า 1"
S2 = "สายงานขายและปฏิบัติการลูกค้า 2"
NAN = "ส่วนขายและบริการลูกค้า น่าน"
NAN_FILTER = ({"column": "sub_unit", "operator": "=", "value": NAN},)


def test_fixture_matches_the_live_contract_when_present():
    if not LIVE_CONTRACT.exists():
        pytest.skip("NT-Report contract not available on this machine")
    live_contract = yaml.safe_load(LIVE_CONTRACT.read_text())
    fixture = yaml.safe_load(CONTRACT.read_text())
    assert live_contract["metrics"] == fixture["metrics"]


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


@pytest.fixture(scope="module")
def databases():
    rows = []

    def add(division, sub_unit, measure_type, group_1, amount, ytd, group_0=""):
        rows.append((202609, division, sub_unit, measure_type, group_0, group_1, amount, ytd))

    add(S1, NAN, "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 10, 100)
    add(S1, NAN, "ADDITIVE", "08.รายได้อื่น", 1, 5)
    add(S1, NAN, "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 6, 60)
    add(S1, NAN, "ADDITIVE", "01.ค่าใช้จ่ายตอบแทนแรงงาน", 2, 20, "02.ค่าใช้จ่าย")
    add(S1, NAN, "ADDITIVE", "02.ค่าสวัสดิการ", 0.3, 3, "02.ค่าใช้จ่าย")
    add(S1, NAN, "ADDITIVE", "03.ค่าใช้จ่ายพัฒนาและฝึกอบรมบุคลากร", 0.1, 1, "02.ค่าใช้จ่าย")
    add(S1, "ส่วน X", "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 20, 200)
    add(S1, "ส่วน X", "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 15, 150)
    add(S1, "ส่วน X", "ADDITIVE", "01.ค่าใช้จ่ายตอบแทนแรงงาน-ER", 1, 10, "02.ค่าใช้จ่าย")
    add(S1, "ส่วน X", "ADDITIVE", "01.ค่าใช้จ่ายตอบแทนแรงงาน", 3, 30, "02.ค่าใช้จ่าย")
    add(S1, "ส่วน X", "COMPUTED", "3.1 กำไร (ขาดทุน) ของส่วนงาน (1)-(2)", 99, 999)
    add(S2, "ส่วน Y", "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 30, 300)
    add(S2, "ส่วน Y", "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 10, 100)
    add(S2, "ส่วน Y", "ADDITIVE", "02.ค่าสวัสดิการ", 5, 50, "02.ค่าใช้จ่าย")
    add("สายงานอื่น", "ส่วน Z", "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 100, 1000)
    add("สายงานอื่น", "ส่วน Z", "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 10, 100)
    rows += [(202608, *r[1:6], 10000, 100000) for r in rows[:4]]
    connections = [duckdb.connect(":memory:"), sqlite3.connect(":memory:")]
    for conn in connections:
        conn.execute("CREATE TABLE feed_ebt_fact_ebt (time_key INTEGER, division TEXT, sub_unit TEXT, "
                     "measure_type TEXT, group_0 TEXT, group_1 TEXT, amount DOUBLE, amount_ytd DOUBLE)")
        conn.executemany("INSERT INTO feed_ebt_fact_ebt VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.execute("CREATE TABLE feed_ebt_fact_ebt_total_monthly "
                     "(time_key INTEGER, ebt DOUBLE, ebt_month DOUBLE, "
                     "ebt_ex_personnel DOUBLE, ebt_ex_personnel_month DOUBLE)")
        conn.execute("INSERT INTO feed_ebt_fact_ebt_total_monthly VALUES (202609, 295, 29.5, 399, 39.9)")
    yield connections
    for conn in connections:
        conn.close()


def execute(req, resolved, databases):
    compiled = compile(req, resolved)
    # No execution cursor: exercise database_adapter's private DuckDB parser.
    check_select(compiled.sql, {compiled.table})
    assert not compiled.sql.endswith(";")
    results = [conn.execute(compiled.sql).fetchall() for conn in databases]
    assert results[0] == results[1]
    return compiled, results[0]


@pytest.mark.parametrize("metric_id,mode,expected", [
    ("ebt", "cumulative", 35),
    ("ebt_excluding_personnel", "cumulative", 59),
    ("ebt_margin", "cumulative", 35 / 95 * 100),
    ("ebt", "month", 3),
    ("ebt_excluding_personnel", "month", 5.4),
    ("ebt_margin", "month", 3 / 9 * 100),
])
def test_nan(metric_id, mode, expected, resolved, databases):
    compiled, rows = execute(CompileRequest(metric_id, 202609, mode, filters=NAN_FILTER), resolved, databases)
    assert rows[0][0] == pytest.approx(expected)
    assert compiled.table == "feed_ebt_fact_ebt" and not compiled.official
    assert compiled.name_th == resolved[metric_id].name_th
    assert compiled.unit == resolved[metric_id].unit and compiled.note_th == resolved[metric_id].note_th
    assert "official_scope" not in compiled.sql


@pytest.mark.parametrize("metric_id,mode,expected", [
    ("ebt", "cumulative", 295), ("ebt_excluding_personnel", "cumulative", 399),
    ("ebt", "month", 29.5), ("ebt_excluding_personnel", "month", 39.9),
])
def test_official_total(metric_id, mode, expected, resolved, databases):
    compiled, rows = execute(CompileRequest(metric_id, 202609, mode), resolved, databases)
    assert rows == [(expected,)]
    assert compiled.official and compiled.table == "feed_ebt_fact_ebt_total_monthly"
    assert "SUM(" not in compiled.sql


@pytest.mark.parametrize("metric_id,mode,expected", [
    ("ebt", "cumulative", 295), ("ebt_excluding_personnel", "cumulative", 399),
    ("ebt_margin", "cumulative", 295 / 595 * 100),
    ("ebt", "month", 29), ("ebt_excluding_personnel", "month", 39.4),
])
def test_official_scope_from_fact(metric_id, mode, expected, resolved, databases):
    compiled, rows = execute(CompileRequest(metric_id, 202609, mode, official_total_ok=False), resolved, databases)
    assert rows[0][0] == pytest.approx(expected)
    assert compiled.official and compiled.table == "feed_ebt_fact_ebt"
    assert f"AND ({resolved[metric_id].official_scope})" in compiled.sql


def test_grouping_scope_and_ranking(resolved, databases):
    req = CompileRequest("ebt", 202609, "cumulative", dimensions=("division",), order_desc=False)
    compiled, rows = execute(req, resolved, databases)
    # A breakdown without a filter stays inside official_scope: the out-of-scope division is absent...
    assert rows == [(S1, 95), (S2, 200)]
    # ...but a filter that names it still computes it (outside the official total).
    outside = ({"column": "division", "operator": "=", "value": "สายงานอื่น"},)
    _, rows = execute(replace(req, filters=outside), resolved, databases)
    assert rows == [("สายงานอื่น", 900)]
    assert not compiled.official and compiled.sql.endswith('GROUP BY "division" ORDER BY 2 ASC')
    req = replace(req, filters=({"column": "division", "operator": "IN", "value": [S1, S2]},),
                  order_desc=True, limit=1)
    compiled, rows = execute(req, resolved, databases)
    assert rows == [(S2, 200)] and compiled.sql.endswith("ORDER BY 2 DESC LIMIT 1")
    _, rows = execute(replace(req, limit=None), resolved, databases)
    assert rows == [(S2, 200), (S1, 95)]
    _, rows = execute(replace(req, metric_id="ebt_excluding_personnel", limit=None), resolved, databases)
    assert rows == [(S2, 250), (S1, 149)]
    _, rows = execute(replace(req, dimensions=("sub_unit",), limit=None), resolved, databases)
    assert rows == [("ส่วน Y", 200), ("ส่วน X", 60), (NAN, 35)]


@pytest.mark.parametrize("value", ["น่าน", "%น่าน", "%น่าน%"])
def test_like(value, resolved, databases):
    req = CompileRequest("ebt", 202609, "cumulative", filters=({"column": "sub_unit", "operator": "LIKE", "value": value},))
    _, rows = execute(req, resolved, databases)
    assert rows == [(35,)]


def test_computed_rows_and_empty_terms(resolved, databases):
    req = CompileRequest("ebt_excluding_personnel", 202609, "cumulative", official_total_ok=False)
    before = execute(req, resolved, databases)[1]
    for conn in databases:
        conn.execute("UPDATE feed_ebt_fact_ebt SET amount_ytd = 999999 WHERE measure_type = 'COMPUTED'")
    try:
        assert execute(req, resolved, databases)[1] == before == [(399,)]
    finally:
        for conn in databases:
            conn.execute("UPDATE feed_ebt_fact_ebt SET amount_ytd = 999 WHERE measure_type = 'COMPUTED'")
    _, rows = execute(replace(req, filters=({"column": "sub_unit", "operator": "=", "value": "absent"},)), resolved, databases)
    assert rows == [(0,)]
    _, rows = execute(replace(req, metric_id="ebt_margin", filters=NAN_FILTER, period=199901), resolved, databases)
    assert rows == [(None,)]


@pytest.mark.parametrize("question,expected", [
    ("ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร", ["ebt", "ebt_excluding_personnel"]),
    ("EBT ไม่รวมบุคลากร", ["ebt_excluding_personnel"]),
    ("EBT Margin สะสม", ["ebt_margin"]), ("กำไรสะสม", ["ebt"]),
    ("nohr แล้ว EBT Margin แล้ว EBT nohr", ["ebt_excluding_personnel", "ebt_margin", "ebt"]),
    ("คำถามอื่น", []),
])
def test_matching(question, expected, metrics):
    assert match_metrics(question, metrics) == expected


def test_matching_ignores_empty_synonyms(metrics):
    metric = replace(metrics[0], synonyms=("", " "), name_th="")
    assert match_metrics(" ", [metric]) == []


def test_prompt_names_only(metrics):
    assert metric_catalog([]) == metric_note([], metrics) == ""
    assert metric_note(["ebt_excluding_personnel", "ebt"], metrics) == (
        "metric ที่ประกาศไว้และตรงกับคำในคำถาม: ebt_excluding_personnel = EBT ไม่รวมค่าใช้จ่ายบุคลากร; "
        "ebt = EBT (กำไรก่อนภาษี ตามรายงาน EBT)")
    assert metric_catalog(metrics) == "\n".join(
        f"- {m.metric_id}: {m.name_th} (คำพ้อง: {', '.join(m.synonyms)})" for m in metrics)
    for forbidden in ("measure_type", "SUM(", "rev - other", "amount_ytd", "official_scope"):
        assert forbidden not in metric_catalog(metrics) + metric_note(["ebt"], metrics)


def test_structural_resolution(metrics, resolved):
    base, child, margin = metrics
    effective = resolved[child.metric_id]
    assert effective.dataset == base.dataset and effective.period == base.period
    assert effective.dimensions == base.dimensions and effective.official_scope == base.official_scope
    assert effective.terms == base.terms | child.terms and child.terms != effective.terms
    for key in ("expr", "name_th", "synonyms", "unit", "note_th", "official_total", "reference"):
        assert getattr(effective, key) == getattr(child, key)
    assert resolved[margin.metric_id].official_total is None
    assert resolve([child, base, margin]).keys() == {"ebt", "ebt_margin"}
    override = replace(child, dimensions=(), official_scope="", terms={"rev": {"where": "1 = 0"}})
    result = resolve([base, override])[child.metric_id]
    assert result.dimensions == () and result.official_scope == "" and result.terms["rev"] == {"where": "1 = 0"}


@pytest.mark.parametrize("updates,expected", [
    ({}, True), ({"intent_type": "ranking"}, True),
    ({"intent_type": "trend"}, False), ({"intent_type": "comparison"}, False),
    ({"dimensions": ["absent"]}, False), ({"dimensions": "division"}, False),
    ({"filters": [{"column": "cost_center_xyz", "operator": "=", "value": "x"}]}, False),
    ({"filters": [{"column": "division", "operator": ">", "value": "x"}]}, False),
    ({"filters": [{"column": "division", "operator": "=", "value": 1}]}, False),
    ({"filters": [{"column": "division", "operator": "IN", "value": ["a", 1]}]}, False),
    ({"ordering": {"column": "division", "direction": "DESC"}}, True),
    ({"ordering": {"column": None}}, True),
    ({"ordering": {"column": "ebt", "direction": "DESC"}}, True),
    ({"ordering": {"column": "EBT (กำไรก่อนภาษี ตามรายงาน EBT)", "direction": "DESC"}}, True),
    ({"ordering": {"column": "ebt_month"}, "intent_type": "ranking"}, True),
    ({"ordering": {"column": "EBT สะสม"}, "metrics": ["EBT สะสม"]}, True),
    ({"ordering": {"column": "revenue", "direction": "DESC"}}, False),
    ({"ordering": {"column": "division", "direction": "random"}}, False),
])
def test_supports(updates, expected, resolved):
    intent = {"intent_type": "aggregation", "dimensions": ["division"], "filters": list(NAN_FILTER)} | updates
    assert supports(intent, resolved["ebt"]) is expected


@pytest.mark.parametrize("expr", [
    "rev; drop table x", "rev || other", "unknown_term + rev", "sum(rev)", "rev > 0",
    "'rev'", "rev -- other", "rev /* other */", "nullif(rev)", "nullif(rev, 0, 1)",
    "(rev", "rev)", "", "rev other", "rev +", "rev // 2",
])
def test_reject_expr(expr, resolved):
    metric = replace(resolved["ebt"], expr=expr)
    with pytest.raises(ValueError):
        compile(CompileRequest("ebt", 202609, "cumulative"), resolved | {"ebt": metric})


@pytest.mark.parametrize("updates", [
    {"metric_id": "unknown"}, {"mode": "year"}, {"dimensions": ("absent",)},
    {"filters": ({"column": "cost_center_xyz", "operator": "=", "value": "x"},)},
    {"filters": ({"column": "division", "operator": ">", "value": "x"},)},
    {"filters": ({"column": "division", "operator": "IN", "value": []},)},
    {"period": "202609 OR 1=1"}, {"limit": "1; drop table x"}, {"limit": -1}, {"order_desc": "DESC"},
])
def test_reject_request(updates, resolved):
    with pytest.raises(ValueError):
        compile(replace(CompileRequest("ebt", 202609, "cumulative"), **updates), resolved)


def test_reference_cycles_and_mismatched_sources(resolved):
    base = resolved["ebt"]
    a = replace(base, metric_id="a", extends="b", expr="b + rev", official_total=None)
    b = replace(base, metric_id="b", expr="a")
    with pytest.raises(ValueError, match="Cyclic"):
        compile(CompileRequest("a", 202609, "cumulative"), {"a": a, "b": b})
    with pytest.raises(ValueError, match="same dataset"):
        compile(CompileRequest("a", 202609, "cumulative"), {"a": a, "b": replace(b, dataset="other")})


def test_arithmetic_and_quoting(resolved, databases):
    base = replace(resolved["ebt"], expr="-(rev - other) + +exp * 2 / (1 + 1) + 1e-2 - .5", official_total=None)
    compiled, rows = execute(CompileRequest("ebt", 202609, "cumulative", filters=NAN_FILTER), {"ebt": base}, databases)
    assert rows[0][0] == pytest.approx(-35.49)
    assert "NULLIF" not in compiled.sql
    quoted = replace(base, dataset='select"table', name_th='ชื่อ"วัด', dimensions=('group"dim',),
                     period={"column": 'period"key', "value": {"cumulative": 'value"col'}},
                     terms={"rev": {"where": "1 = 1"}}, expr="rev")
    for conn in databases:
        conn.execute('CREATE TABLE "select""table" ("period""key" INTEGER, "value""col" DOUBLE, "group""dim" TEXT)')
        conn.execute('INSERT INTO "select""table" VALUES (?, ?, ?)', (202609, 7.0, "O'Brien"))
    req = CompileRequest("ebt", 202609, "cumulative", dimensions=('group"dim',),
                         filters=({"column": 'group"dim', "operator": "=", "value": "O'Brien"},))
    compiled, rows = execute(req, {"ebt": quoted}, databases)
    assert rows == [("O'Brien", 7)] and "'O''Brien'" in compiled.sql


def test_loading_active_json_rows_and_no_cache(metrics, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SchemaMetric.__table__.create(engine)
    try:
        with engine.begin() as conn:
            for metric in metrics:
                values = asdict(metric)
                for key in ("synonyms", "period", "dimensions", "terms", "official_total", "reference"):
                    if values[key] is not None:
                        values[key] = json.dumps(values[key], ensure_ascii=False)
                columns = ", ".join(values)
                params = ", ".join(":" + key for key in values)
                conn.execute(text(f"INSERT INTO schema_metrics ({columns}, context_name, status, is_active) "
                                  f"VALUES ({params}, :context, 'active', 1)"), values | {"context": "test"})
            for metric_id, context, status, active in [
                ("other", "elsewhere", "active", 1), ("proposed", "test", "proposed", 1),
                ("rejected", "test", "rejected", 1), ("disabled", "test", "active", 0),
            ]:
                conn.execute(text("INSERT INTO schema_metrics (metric_id, name_th, expr, context_name, status, is_active) "
                                  "VALUES (:id, 'hidden', '1', :context, :status, :active)"),
                             {"id": metric_id, "context": context, "status": status, "active": active})
        assert load_metrics("test", engine) == metrics
        assert load_metrics("test' OR 1=1 --", engine) == []
        monkeypatch.setitem(sys.modules, "app.db.session", SimpleNamespace(config_engine=engine))
        assert load_metrics("test") == metrics
        with engine.begin() as conn:
            conn.execute(text("UPDATE schema_metrics SET is_active = 0 WHERE metric_id = 'ebt'"))
        assert load_metrics("test", engine) == metrics[1:]
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO schema_metrics (metric_id, name_th, expr, context_name, status, is_active) "
                              "VALUES ('minimal', 'name', '1', 'minimal', 'active', 1)"))
        minimal = load_metrics("minimal", engine)[0]
        assert minimal.synonyms == () and minimal.terms == {} and minimal.dimensions is None
    finally:
        engine.dispose()


def test_loading_fails_open(caplog):
    engine = create_engine("sqlite:///:memory:")
    unreachable = Mock()
    unreachable.connect.side_effect = RuntimeError("offline")
    try:
        with caplog.at_level(logging.DEBUG, logger="app.services.ai.metric_compiler"):
            assert load_metrics("missing", engine) == []
            assert load_metrics("offline", unreachable) == []
        assert "Declared metrics unavailable" in caplog.text
    finally:
        engine.dispose()


def test_compile_ranks_cost_centers_by_value_at_one_period(resolved):
    """The live defect (query_audit 407): a prompt-built SQL measured revenue only and summed
    amount_ytd over nine months. The compiled form has all four terms at a single period."""
    req = CompileRequest("ebt", 202609, "cumulative", dimensions=("cost_center", "division"),
                         order_desc=True, limit=10)
    sql = compile(req, resolved).sql
    assert "= 202609" in sql and "BETWEEN" not in sql
    assert sql.count("CASE WHEN") == 4 and sql.count("amount_ytd") == 4 and '"amount"' not in sql
    assert "รวมรายได้ทั้งสิ้น" in sql and "รวมค่าใช้จ่ายทั้งสิ้น" in sql and "08.รายได้อื่น" in sql and "-ER" in sql
    assert sql.endswith("ORDER BY 3 DESC LIMIT 10")


def test_catalog_names_the_dimensions_with_their_meaning(metrics, tmp_path):
    """"ฝ่ายไหนมี EBT สูงสุด" was grouped by division (2026-10-24): the prompt's schema table shows only the main view
    (fact_ebt_division_monthly), so the model never saw that `unit` is a ฝ่าย. The catalog now says so."""
    from tests.unit import knowledge_db
    engine = knowledge_db.make(tmp_path / "labels.db", seed="""
        INSERT INTO schema_metadata (table_name, column_name, description) VALUES
          ('feed_ebt_fact_ebt', 'division', 'สายงาน — ระดับ 1 ของโครงสร้างองค์กร; EBT report รวมเฉพาะ 2 สายงาน'),
          ('feed_ebt_fact_ebt', 'unit', 'ฝ่าย — ระดับ 3 ของโครงสร้างองค์กร 4 ระดับ'),
          ('feed_ebt_fact_ebt', 'unit_short_name', 'ชื่อย่อของฝ่าย (เช่น กกง., อป.2) — คู่กับชื่อเต็ม unit_fname'),
          ('feed_ebt_fact_ebt', 'amount_ytd', 'ยอดสะสม'),
          ('feed_ebt_fact_ebt_division_monthly', 'division', 'other table');
    """)
    labels = dimension_labels(metrics, engine)
    assert labels == {"division": "สายงาน", "unit": "ฝ่าย", "unit_short_name": "ชื่อย่อของฝ่าย (เช่น กกง., อป.2)"}
    catalog = metric_catalog(metrics, labels)
    ebt_line = catalog.split("\n- ebt_excluding_personnel")[0]
    assert "มิติ/ตัวกรองที่ใช้ได้" in ebt_line and "unit (ฝ่าย)" in ebt_line and "sub_unit," in ebt_line
    assert "division (สายงาน)" in ebt_line and "cost_center" in ebt_line
    for forbidden in ("measure_type", "SUM(", "rev - other", "amount_ytd", "official_scope"):
        assert forbidden not in catalog
    assert metric_catalog(metrics) == metric_catalog(metrics, None)  # names only, as before
    assert dimension_labels([], engine) == {}
    assert dimension_labels(metrics, object()) is None  # unusable engine → catalog falls back to names
