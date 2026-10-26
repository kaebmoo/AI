"""Multi-grain metric declarations round trip without changing compiler planning."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models.schema_models import SchemaMetric
from app.services import datafeed_knowledge as dk
from app.services.ai.metric_compiler import load_metrics, resolve
from scripts.migrate_schema_metrics import migrate
from tests.unit import knowledge_db


@pytest.fixture
def engine(tmp_path):
    engine = knowledge_db.make(tmp_path / "x.db")
    yield engine
    engine.dispose()


@pytest.fixture
def contract():
    dimensions = [[], ["bu_seq", "bu"], ["division_name", "unit_name", "cost_center"]]
    names = ["fact_total_monthly", "fact_bu_monthly", "fact_org_monthly"]
    return {
        "domain": "revenue", "schema_version": "1", "primary_dataset": names[0], "period_key": "year_month",
        "datasets": [
            {"name": name, "columns": [
                {"name": "year_month", "dtype": "integer"},
                {"name": "revenue", "dtype": "double", "agg": "sum"},
                {"name": "revenue_ytd", "dtype": "double", "agg": "point_in_time"},
                *({"name": d, "dtype": "string"} for d in dims)]}
            for name, dims in zip(names, dimensions)],
        "metrics": [
            {"id": "revenue", "name_th": "รายได้", "datasets": [
                {"name": name, "dimensions": dims} for name, dims in zip(names, dimensions)],
             "period": {"column": "year_month", "value": {"cumulative": "revenue_ytd", "month": "revenue"}},
             "terms": {"rev": {"where": ""}}, "expr": "rev",
             "official_total": {"dataset": names[0], "column": "revenue_ytd", "month_column": "revenue"}},
            {"id": "revenue_share", "name_th": "สัดส่วนรายได้", "extends": "revenue",
             "expr": "rev * 100 / nullif(rev, 0)"}],
    }


def sync(engine, contract):
    with engine.begin() as conn:
        return dk.sync_knowledge(conn, "revenue", contract)


def stored(engine):
    with engine.connect() as conn:
        return {r["metric_id"]: dict(r) for r in conn.execute(text(
            "SELECT * FROM schema_metrics WHERE context_name = 'feed_revenue' ORDER BY id")).mappings()}


def test_round_trip_inheritance_and_no_second_write(engine, contract):
    original = deepcopy(contract)
    sync(engine, contract)
    rows = stored(engine)
    base = rows["revenue"]
    assert base["dataset"] is None and base["dimensions"] is None
    expected = [{**item, "name": "feed_revenue_" + item["name"]} for item in contract["metrics"][0]["datasets"]]
    assert json.loads(base["datasets"]) == expected
    assert base["datasets"] == json.dumps(expected, ensure_ascii=False, sort_keys=True)
    child = rows["revenue_share"]
    assert all(child[field] is None for field in ("datasets", "dataset", "dimensions", "period"))
    loaded = load_metrics("feed_revenue", engine)
    assert len(loaded) == 2
    assert loaded[0].datasets == tuple(expected)
    assert all(isinstance(item, dict) for item in loaded[0].datasets)
    assert loaded[0].dimensions == ("bu_seq", "bu", "division_name", "unit_name", "cost_center")
    assert loaded[1].datasets is None and loaded[1].dimensions is None
    resolved = resolve(loaded)
    assert resolved["revenue_share"].datasets == loaded[0].datasets
    assert resolved["revenue_share"].dimensions == loaded[0].dimensions
    assert contract == original
    with Session(engine) as session:
        assert session.query(SchemaMetric).filter_by(metric_id="revenue").one().to_dict()["datasets"] == expected
    with engine.begin() as conn:
        conn.execute(text("UPDATE schema_metrics SET updated_at = '2000-01-01 00:00:00'"))
        conn.execute(text("CREATE TRIGGER metrics_no_updates BEFORE UPDATE ON schema_metrics "
                          "BEGIN SELECT RAISE(ABORT, 'unexpected update'); END"))
    before = stored(engine)
    for item in contract["metrics"][0]["datasets"]:
        item.update(dict(reversed(list(item.items()))))
    contract["metrics"][0]["period"]["value"] = {"month": "revenue", "cumulative": "revenue_ytd"}
    sync(engine, contract)
    assert stored(engine) == before


def test_metric_dimensions_union_preserves_first_seen_and_explicit_dimensions(engine, contract):
    sync(engine, contract)
    metric = load_metrics("feed_revenue", engine)[0]
    items = ({"name": "a", "dimensions": ["bu", "unit"]}, {"name": "b", "dimensions": ("unit", "division")})
    assert replace(metric, datasets=items, dimensions=None).dimensions == ("bu", "unit", "division")
    assert replace(metric, datasets=items, dimensions=()).dimensions == ()
    assert replace(metric, datasets=items, dimensions=("explicit",)).dimensions == ("explicit",)
    assert replace(metric, datasets=({"name": "a", "dimensions": []},), dimensions=None).dimensions == ()


@pytest.mark.parametrize("term", [{}, {"where": None}, {"where": ""}, {"where": "  "}])
def test_empty_where_forms_are_valid(engine, contract, term):
    contract["metrics"][0]["terms"]["rev"] = term
    sync(engine, contract)
    assert set(stored(engine)) == {"revenue", "revenue_share"}
    assert json.loads(stored(engine)["revenue"]["terms"])["rev"] == term


@pytest.mark.parametrize("term,reason", [(None, "must be a mapping"), ("revenue", "must be a mapping"),
                                         ({"where": 5}, "where must be a string or null")])
def test_invalid_term_skips_only_its_metric(engine, contract, caplog, term, reason):
    bad = deepcopy(contract["metrics"][0])
    bad.update(id="bad", terms={"rev": term})
    contract["metrics"].append(bad)
    sync(engine, contract)
    assert set(stored(engine)) == {"revenue", "revenue_share"}
    assert "Skipping metric bad" in caplog.text and reason in caplog.text


@pytest.mark.parametrize("case,reason", [
    ("both", "exactly one of dataset / datasets"),
    ("neither", "exactly one of dataset / datasets"),
    ("empty", "datasets must be a non-empty list"),
    ("not_list", "datasets must be a non-empty list"),
    ("unknown", "unknown dataset 'missing'"),
    ("duplicate", "duplicate dataset"),
    ("extra_key", "each datasets item is {name, dimensions}"),
    ("not_dict", "each datasets item is {name, dimensions}"),
    ("missing_key", "each datasets item is {name, dimensions}"),
    ("wrong_dimension", "unknown dimensions ['bu'] in fact_org_monthly"),
    ("dimensions_not_list", "datasets dimensions must be a list of strings"),
    ("dimension_not_string", "datasets dimensions must be a list of strings"),
    ("metric_dimensions", "dimensions come from datasets"),
    ("period_missing", "unknown period column 'year_month'"),
    ("month_missing", "unknown period column 'revenue'"),
    ("cumulative_missing", "unknown period column 'revenue_ytd'"),
    ("term_missing", "term rev: unknown columns ['bu']"),
    ("official_scope_missing", "official_scope: unknown columns ['bu']"),
    ("ranking_scope_missing", "ranking.scope: unknown columns ['bu']"),
])
def test_invalid_datasets_skip_only_the_invalid_metric(engine, contract, caplog, case, reason):
    bad = deepcopy(contract["metrics"][0])
    bad["id"] = "bad"
    good = contract["metrics"][0]
    good.pop("datasets")
    good["dataset"] = "fact_total_monthly"
    contract["metrics"] = [good, bad]
    if case == "both":
        bad["dataset"] = "fact_total_monthly"
    elif case == "neither":
        bad.pop("datasets")
    elif case == "empty":
        bad["datasets"] = []
    elif case == "not_list":
        bad["datasets"] = "fact_total_monthly"
    elif case == "unknown":
        bad["datasets"][0]["name"] = "missing"
    elif case == "duplicate":
        bad["datasets"].append(deepcopy(bad["datasets"][0]))
    elif case == "extra_key":
        bad["datasets"][0]["extra"] = True
    elif case == "not_dict":
        bad["datasets"][0] = "fact_total_monthly"
    elif case == "missing_key":
        bad["datasets"][0].pop("dimensions")
    elif case == "wrong_dimension":
        bad["datasets"][2]["dimensions"] = ["bu"]
    elif case == "dimensions_not_list":
        bad["datasets"][0]["dimensions"] = "bu"
    elif case == "dimension_not_string":
        bad["datasets"][0]["dimensions"] = [5]
    elif case == "metric_dimensions":
        bad["dimensions"] = []
    elif case in ("period_missing", "month_missing", "cumulative_missing"):
        missing = {"period_missing": "year_month", "month_missing": "revenue",
                   "cumulative_missing": "revenue_ytd"}[case]
        contract["datasets"][2]["columns"] = [c for c in contract["datasets"][2]["columns"] if c["name"] != missing]
    elif case == "term_missing":
        bad["terms"]["rev"]["where"] = "bu = '1'"
    elif case == "official_scope_missing":
        bad["official_scope"] = "bu IN ('1')"
    elif case == "ranking_scope_missing":
        bad["ranking"] = {"scope": "bu = '1'"}
    sync(engine, contract)
    assert set(stored(engine)) == {"revenue"}
    assert "Skipping metric bad" in caplog.text and reason in caplog.text


@pytest.mark.parametrize("single", [False, True])
@pytest.mark.parametrize("agg_source", ["column", "control_totals", "default", "column_overrides_control_totals"])
def test_summed_period_respects_aggregation(engine, contract, caplog, single, agg_source):
    metric = contract["metrics"][0]
    contract["metrics"] = [metric]
    if single:
        metric.pop("datasets")
        metric["dataset"] = "fact_total_monthly"
    metric.pop("official_total")
    metric["period"]["value"] = {"month": "revenue_ytd"}
    if agg_source != "column":
        for dataset in contract["datasets"]:
            for column in dataset["columns"]:
                if column["name"] == "revenue_ytd":
                    column.pop("agg")
                    if agg_source == "column_overrides_control_totals":
                        column["agg"] = "sum"
    if agg_source in ("control_totals", "column_overrides_control_totals"):
        contract["control_totals"] = {"measures": [{"name": "revenue_ytd", "agg": "point_in_time"}]}
    sync(engine, contract)
    if agg_source in ("column", "control_totals"):
        assert stored(engine) == {}
        assert "Skipping metric revenue" in caplog.text and "point_in_time" in caplog.text
    else:
        assert set(stored(engine)) == {"revenue"}


@pytest.mark.parametrize("single", [False, True])
def test_monthly_sum_is_allowed(engine, contract, single):
    metric = contract["metrics"][0]
    if single:
        metric.pop("datasets")
        metric["dataset"] = "fact_total_monthly"
    metric.pop("official_total")
    metric["period"]["value"] = {"month": "revenue"}
    sync(engine, contract)
    assert set(stored(engine)) == {"revenue", "revenue_share"}


def test_point_in_time_in_any_candidate_is_rejected(engine, contract, caplog):
    metric = contract["metrics"][0]
    contract["metrics"] = [metric]
    metric.pop("official_total")
    metric["period"]["value"] = {"month": "revenue"}
    contract["datasets"][2]["columns"][1]["agg"] = "point_in_time"
    sync(engine, contract)
    assert stored(engine) == {} and "point_in_time" in caplog.text


@pytest.mark.parametrize("scope", ["official_scope", "ranking"])
def test_scope_columns_and_quoted_literals_are_valid_for_single_dataset(engine, contract, scope):
    metric = contract["metrics"][0]
    metric.pop("datasets")
    metric["dataset"] = "fact_bu_monthly"
    predicate = "bu IN ('unknown_column = 1', 'it''s absent IN (2)')"
    metric[scope] = predicate if scope == "official_scope" else {"scope": predicate}
    sync(engine, contract)
    assert set(stored(engine)) == {"revenue", "revenue_share"}
    metric[scope] = "absent = 1" if scope == "official_scope" else {"scope": "absent = 1"}
    contract["metrics"] = [dict(metric, id="invalid")]
    sync(engine, contract)
    assert "invalid" not in stored(engine)


def old_metrics_table(conn):
    ddl = knowledge_db.DDL.split("CREATE TABLE schema_metrics", 1)[1].split(";", 1)[0]
    conn.exec_driver_sql("CREATE TABLE schema_metrics" + ddl.replace(", datasets TEXT", ""))
    conn.execute(text("INSERT INTO schema_metrics (context_name, metric_id, name_th, dataset, period, dimensions, "
                      "terms, expr) VALUES ('feed_ebt', 'ebt', 'กำไร', 'feed_ebt_fact_ebt', :period, :dimensions, "
                      ":terms, 'rev')"), {
                          "period": json.dumps({"column": "time_key", "value": {"month": "amount", "cumulative": "amount_ytd"}}),
                          "dimensions": json.dumps(["division", "sub_unit"]),
                          "terms": json.dumps({"rev": {"where": "measure_type = 'SUBTOTAL'"}})})


def test_migration_adds_datasets_preserves_rows_and_is_idempotent(capsys):
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            old_metrics_table(conn)
            before = dict(conn.execute(text("SELECT * FROM schema_metrics")).mappings().one())
        migrate(engine)
        assert "Added schema_metrics.datasets." in capsys.readouterr().out
        assert "datasets" in {c["name"] for c in inspect(engine).get_columns("schema_metrics")}
        with engine.connect() as conn:
            after = dict(conn.execute(text("SELECT * FROM schema_metrics")).mappings().one())
        assert after == {**before, "datasets": None}
        migrate(engine)
        assert "Added schema_metrics.datasets." not in capsys.readouterr().out
        with engine.connect() as conn:
            assert dict(conn.execute(text("SELECT * FROM schema_metrics")).mappings().one()) == after
    finally:
        engine.dispose()


def test_load_metrics_from_unmigrated_table():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            old_metrics_table(conn)
        metrics = load_metrics("feed_ebt", engine)
        assert len(metrics) == 1
        metric = metrics[0]
        assert metric.metric_id == "ebt" and metric.dataset == "feed_ebt_fact_ebt"
        assert metric.dimensions == ("division", "sub_unit") and metric.datasets is None
        assert metric.period == {"column": "time_key", "value": {"month": "amount", "cumulative": "amount_ytd"}}
        assert metric.terms == {"rev": {"where": "measure_type = 'SUBTOTAL'"}}
        assert metric.synonyms == ()
    finally:
        engine.dispose()
