"""Numeric dimension filters are gated by metadata and preserve SQL literal types."""

from dataclasses import fields, replace
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import duckdb
import pytest
from sqlalchemy import create_engine, text
import yaml

from app.services.ai import hybrid_flow, metric_compiler as compiler
from app.services.database_adapter import check_select


BU = "feed_revenue_fact_bu_monthly"
TOTAL = "feed_revenue_fact_total_monthly"
BG1 = "1.Hard Infrastructure"
BG4 = "4.Fixed Line & Broadband"
BG8 = "8.รายได้อื่น"


@pytest.fixture(scope="module")
def metrics():
    contract = yaml.safe_load((Path(__file__).parents[1] / "fixtures/revenue_metrics_draft.yaml").read_text())
    rows = []
    for declaration in contract["metrics"]:
        values = {f.name: declaration.get(f.name) for f in fields(compiler.Metric)}
        values["metric_id"] = declaration["id"]
        values["synonyms"] = tuple(values["synonyms"] or ())
        values["terms"] = values["terms"] or {}
        values["datasets"] = tuple({**item, "name": f"feed_{contract['domain']}_{item['name']}"}
                                   for item in values["datasets"])
        total = values["official_total"]
        values["official_total"] = {**total, "dataset": f"feed_{contract['domain']}_{total['dataset']}"}
        rows.append(compiler.Metric(**values))
    return rows


@pytest.fixture(scope="module")
def resolved(metrics):
    return compiler.resolve(metrics)


@pytest.fixture(scope="module")
def databases():
    bu_rows, total_rows = [], []
    for month in range(1, 10):
        period = 202600 + month
        bu_rows += [(period, 1, BG1, 100, 100 * month),
                    (period, 4, BG4, 200, 200 * month),
                    (period, 8, BG8, 30, 210 if month == 9 else 30 * month)]
        total_rows.append((period, 330, 2910 if month == 9 else 330 * month))
    connections = [duckdb.connect(":memory:"), sqlite3.connect(":memory:")]
    for conn in connections:
        conn.execute(f"CREATE TABLE {BU} (year_month INTEGER, bu_seq INTEGER, bu TEXT, "
                     "revenue DOUBLE, revenue_ytd DOUBLE)")
        conn.executemany(f"INSERT INTO {BU} VALUES (?, ?, ?, ?, ?)", bu_rows)
        conn.execute(f"CREATE TABLE {TOTAL} (year_month INTEGER, revenue DOUBLE, revenue_ytd DOUBLE)")
        conn.executemany(f"INSERT INTO {TOTAL} VALUES (?, ?, ?)", total_rows)
    yield connections
    for conn in connections:
        conn.close()


@pytest.fixture
def intent():
    return {"intent_type": "aggregation", "metric_id": "revenue", "dimensions": [],
            "filters": [{"column": "bu_seq", "operator": "=", "value": 8}],
            "time_range": {"year": 2026, "month": 9, "cumulative": True}}


def execute(req, resolved, databases):
    compiled = compiler.compile(req, resolved)
    check_select(compiled.sql, {compiled.table})
    results = [sorted(conn.execute(compiled.sql).fetchall()) for conn in databases]
    assert results[0] == results[1]
    return compiled, results[0]


def test_numeric_equality_keeps_the_integer(intent, resolved, databases):
    req, reason = compiler.plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL}, numeric={"bu_seq"})
    assert reason is None and type(req.filters[0]["value"]) is int and req.filters[0]["value"] == 8
    assert compiler.plan(intent, "รายได้", resolved, [], 202609, {TOTAL}, numeric={"bu_seq"}) == req
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == BU and rows == [(210,)]
    assert '"bu_seq" = 8' in compiled.sql and "'8'" not in compiled.sql
    assert not compiler.supports(intent, resolved["revenue"])


def test_numeric_in_with_bu_dimension(intent, resolved, databases):
    intent.update(dimensions=["bu"], filters=[{"column": "bu_seq", "operator": "IN", "value": [1, 4]}])
    req, reason = compiler.plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL}, numeric={"bu_seq"})
    assert reason is None and req.filters[0]["value"] == [1, 4]
    compiled, rows = execute(req, resolved, databases)
    assert compiled.table == BU and rows == [(BG1, 900), (BG4, 1800)]
    assert '"bu_seq" IN (1, 4)' in compiled.sql


@pytest.mark.parametrize("kwargs", [{}, {"numeric": None}, {"numeric": set()}])
@pytest.mark.parametrize("operator,value", [("=", 8), ("IN", [1, 4])])
def test_numbers_need_explicit_numeric_dimensions(intent, resolved, kwargs, operator, value):
    intent["filters"][0].update(operator=operator, value=value)
    assert compiler.plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL}, **kwargs) == (
        None, f"shape:filter:{operator}")


def test_number_on_text_column_declines(intent, resolved):
    intent["filters"][0]["column"] = "bu"
    assert compiler.plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL}, numeric={"bu_seq"}) == (
        None, "shape:filter:=")


@pytest.mark.parametrize("operator,value", [
    ("=", True), ("=", float("nan")), ("=", float("inf")), ("=", float("-inf")),
    ("IN", [1, "4"]), ("IN", []), ("IN", [True]), ("IN", [1, float("nan")]),
    ("IN", [float("inf")]), ("LIKE", 8), (">", 8),
])
def test_invalid_numeric_filters_decline(intent, resolved, operator, value):
    intent["filters"][0].update(operator=operator, value=value)
    assert compiler.plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL}, numeric={"bu_seq"}) == (
        None, f"shape:filter:{operator}")


@pytest.mark.parametrize("value,literal", [(8.0, "8.0"), ("8", "'8'")])
def test_float_and_string_literals_keep_their_type(intent, resolved, databases, value, literal):
    intent["filters"][0]["value"] = value
    req, reason = compiler.plan_with_reason(intent, "รายได้", resolved, [], 202609, {TOTAL}, numeric={"bu_seq"})
    assert reason is None and type(req.filters[0]["value"]) is type(value)
    compiled, rows = execute(req, resolved, databases)
    assert f'"bu_seq" = {literal}' in compiled.sql and rows == [(210,)]
    if isinstance(value, str):
        old_req = compiler.plan(intent, "รายได้", resolved, [], 202609, {TOTAL})
        assert compiler.compile(old_req, resolved).sql == compiled.sql


@pytest.mark.parametrize("operator,value,literal,expected", [
    ("=", 8, "= 8", [(210,)]), ("=", 8.0, "= 8.0", [(210,)]),
    ("IN", [1, 4], "IN (1, 4)", [(2700,)]),
    ("IN", [1, 4.0], "IN (1, 4.0)", [(2700,)]),
])
def test_direct_compile_numbers(resolved, databases, operator, value, literal, expected):
    req = compiler.CompileRequest("revenue", 202609, "cumulative",
                                  filters=({"column": "bu_seq", "operator": operator, "value": value},))
    compiled, rows = execute(req, resolved, databases)
    assert f'"bu_seq" {literal}' in compiled.sql and rows == expected


@pytest.mark.parametrize("operator,value", [
    ("=", True), ("=", float("nan")), ("=", float("inf")), ("=", float("-inf")),
    ("IN", [1, "4"]), ("IN", []), ("IN", [True]), ("IN", [1, float("nan")]),
    ("IN", [float("inf")]), ("LIKE", 8),
])
def test_direct_compile_rejects_invalid_values(resolved, operator, value):
    req = compiler.CompileRequest("revenue", 202609, "cumulative",
                                  filters=({"column": "bu_seq", "operator": operator, "value": value},))
    with pytest.raises(ValueError, match="Unsupported filter operator or value"):
        compiler.compile(req, resolved)


@pytest.fixture
def config_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_metadata "
                          "(table_name TEXT, column_name TEXT, data_type TEXT, status TEXT)"))
    yield engine
    engine.dispose()


def test_numeric_dimensions_require_every_declared_table(metrics, config_engine):
    single = replace(metrics[0], dataset="single", datasets=None,
                     dimensions=("bu_seq", "shared", "missing", "inactive", "boolean"))
    multiple = replace(metrics[0], dataset=None, datasets=(
        {"name": BU, "dimensions": ["bu_seq", "bu", "shared", "missing", "inactive", "boolean"]},))
    rows = [(BU, "bu_seq", "integer", "active"), (BU, "bu", "VARCHAR(50)", "active"),
            (BU, "shared", "INTEGER", "active"), ("single", "shared", "DOUBLE", None),
            ("single", "bu_seq", "string", "active"), (BU, "missing", "integer", "active"),
            (BU, "inactive", "integer", "active"), ("single", "inactive", "integer", "inactive"),
            (BU, "boolean", "boolean", "active"), ("single", "boolean", "integer", "active"),
            (BU, "undeclared", "integer", "active"), ("unrelated", "bu", "integer", "active")]
    with config_engine.begin() as conn:
        conn.execute(text("INSERT INTO schema_metadata VALUES (:t, :c, :d, :s)"),
                     [{"t": t, "c": c, "d": d, "s": s} for t, c, d, s in rows])
    assert compiler.numeric_dimensions(metrics, config_engine) == {"bu_seq"}
    assert compiler.numeric_dimensions([multiple, single], config_engine) == {"shared"}
    assert compiler.numeric_dimensions([], config_engine) == set()
    assert compiler.numeric_dimensions([replace(single, dimensions=())], config_engine) == set()


@pytest.mark.parametrize("data_type", [
    "integer", "int", "int64", "bigint", "smallint", "tinyint", "double", "float", "real", "decimal", "numeric",
    "INTEGER", "DOUBLE", "DECIMAL(12, 2)", "NUMERIC(10)",
])
def test_numeric_dimensions_type_spellings(metrics, config_engine, data_type):
    with config_engine.begin() as conn:
        conn.execute(text("INSERT INTO schema_metadata VALUES (:t, 'bu_seq', :d, 'active')"),
                     {"t": BU, "d": data_type})
    assert compiler.numeric_dimensions(metrics, config_engine) == {"bu_seq"}


def test_numeric_dimensions_unavailable(metrics, caplog):
    engine = create_engine("sqlite:///:memory:")
    try:
        with caplog.at_level("DEBUG", logger=compiler.__name__):
            assert compiler.numeric_dimensions(metrics, engine) is None
        assert "Numeric dimensions unavailable" in caplog.text
        assert compiler.numeric_dimensions([], engine) == set()
    finally:
        engine.dispose()


async def test_hybrid_passes_numeric_dimensions(metrics, intent, monkeypatch):
    numeric = {"bu_seq"}
    monkeypatch.setattr(compiler, "load_metrics", Mock(return_value=metrics))
    monkeypatch.setattr(compiler, "dimension_labels", Mock(return_value={"bu": "กลุ่มธุรกิจ"}))
    numeric_loader = Mock(return_value=numeric)
    monkeypatch.setattr(compiler, "numeric_dimensions", numeric_loader)
    planner = compiler.plan_with_reason
    recorded = []

    def record_plan(*args, **kwargs):
        recorded.append(kwargs)
        return planner(*args, **kwargs)

    monkeypatch.setattr(compiler, "plan_with_reason", record_plan)
    monkeypatch.setattr(hybrid_flow, "_context_tables", lambda *a: {})
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: [])
    monkeypatch.setattr(hybrid_flow, "reference_period", lambda: 202609)
    monkeypatch.setattr(hybrid_flow, "scope_note", lambda: "")
    monkeypatch.setattr(hybrid_flow, "intent_period_note", lambda: "")
    monkeypatch.setattr(hybrid_flow, "get_column_hierarchies", lambda: {})
    service = SimpleNamespace(
        provider=SimpleNamespace(last_usage=None, generate_structured=AsyncMock(return_value=intent)),
        provider_name="fake", parse_intent_json=lambda text: None,
        format_value_matches=lambda *a, **kw: "", get_pending_limit_warning=lambda: "",
        set_pending_limit_warning=lambda warning: None,
    )
    prompt, two_pass, compiled = await hybrid_flow.build_first_attempt_prompt(
        service=service, question="รายได้สะสมกลุ่มธุรกิจลำดับที่ 8", system_prompt="system", history=None,
        context_name="feed_revenue", context_table=TOTAL, context_thai="รายได้",
        two_pass_enabled=True, cheap_model=None, detect_hierarchy_level=lambda *a: None,
        format_value_matches=service.format_value_matches, get_vanna_context_string=lambda q: "",
        lookup_values_from_question=lambda *a: [], on_status=None, attempt=0, max_retries=1,
    )
    numeric_loader.assert_called_once_with(metrics)
    assert len(recorded) == 1 and recorded[0]["numeric"] is numeric
    assert prompt == "" and two_pass and compiled.table == BU
    assert '"bu_seq" = 8' in compiled.sql
