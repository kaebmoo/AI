"""A metric's excluded_words send questions it cannot answer to free SQL (practice server r10: "รายได้เทียบเป้า"
compiled as revenue against last year)."""

from dataclasses import fields, replace
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
import yaml

from app.services import datafeed_knowledge as dk
from app.services.ai.metric_compiler import Metric, load_metrics, plan_with_reason, resolve
from scripts.migrate_schema_metrics import migrate
from tests.unit import knowledge_db


@pytest.fixture(scope="module")
def metric():
    contract = yaml.safe_load((Path(__file__).parent.parent / "fixtures" / "revenue_metrics_draft.yaml").read_text())
    declaration = contract["metrics"][0]
    values = {f.name: declaration.get(f.name) for f in fields(Metric)}
    values.update(metric_id=declaration["id"], synonyms=tuple(declaration["synonyms"]), terms=declaration["terms"],
                  datasets=tuple({**d, "name": "feed_revenue_" + d["name"]} for d in declaration["datasets"]),
                  official_total={**declaration["official_total"], "dataset": "feed_revenue_fact_total_monthly"})
    return replace(Metric(**values), excluded_words=("เป้า", "Target"))


COMPARE = {"intent_type": "comparison", "metric_id": "revenue", "dimensions": ["bu"], "filters": [],
           "time_range": {"year": 2026, "month": 9, "cumulative": True}}


@pytest.mark.parametrize("question,word", [
    ("รายได้สะสมเทียบเป้าแยกตามกลุ่มธุรกิจ", "เป้า"),
    ("กลุ่มธุรกิจไหนรายได้ต่ำกว่าเป้าหมาย", "เป้า"),
    ("revenue vs TARGET by BU", "target"),
])
def test_excluded_word_declines_before_planning(metric, question, word):
    assert plan_with_reason(COMPARE, question, resolve([metric]), [], 202609, set()) == (None, f"excluded_word:{word}")


def test_other_questions_and_metrics_without_words_are_unchanged(metric):
    req, reason = plan_with_reason(COMPARE, "รายได้สะสมเทียบกับปีก่อนแยกตามกลุ่มธุรกิจ", resolve([metric]), [], 202609,
                                   set())
    assert reason is None and (req.period, req.base_period, req.dimensions) == (202609, 202509, ("bu",))
    plain = replace(metric, excluded_words=None)
    req, reason = plan_with_reason(COMPARE, "รายได้สะสมเทียบเป้าแยกตามกลุ่มธุรกิจ", resolve([plain]), [], 202609, set())
    assert reason is None and req.base_period == 202509


def test_a_child_does_not_inherit_the_words(metric):
    child = replace(metric, metric_id="revenue_vs_target", extends="revenue", excluded_words=None, datasets=None,
                    dimensions=None, period=None, terms={}, official_total=None)
    resolved = resolve([metric, child])
    assert resolved["revenue_vs_target"].excluded_words is None
    intent = {**COMPARE, "metric_id": "revenue_vs_target"}
    assert plan_with_reason(intent, "รายได้เทียบเป้า", resolved, [], 202609, set())[1] != "excluded_word:เป้า"


def _contract(words):
    columns = [{"name": "year_month", "dtype": "integer"}, {"name": "revenue", "dtype": "double", "agg": "sum"},
               {"name": "revenue_ytd", "dtype": "double", "agg": "point_in_time"}]
    metric = {"id": "revenue", "name_th": "รายได้", "synonyms": ["รายได้"], "dataset": "fact_total_monthly",
              "period": {"column": "year_month", "value": {"cumulative": "revenue_ytd", "month": "revenue"}},
              "dimensions": [], "terms": {"rev": {}}, "expr": "rev"}
    if words is not ...:
        metric["excluded_words"] = words
    return {"domain": "revenue", "schema_version": "1", "primary_dataset": "fact_total_monthly",
            "period_key": "year_month", "datasets": [{"name": "fact_total_monthly", "columns": columns}],
            "metrics": [metric]}


def _sync(tmp_path, contract):
    engine = knowledge_db.make(tmp_path / "k.db")
    with engine.begin() as conn:
        dk.sync_knowledge(conn, "revenue", contract)
    return engine


def test_sync_stores_and_loads_the_words(tmp_path):
    engine = _sync(tmp_path, _contract(["เป้า", "target"]))
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT excluded_words FROM schema_metrics WHERE metric_id = 'revenue'")).scalar()
    assert json.loads(stored) == ["เป้า", "target"]
    assert load_metrics("feed_revenue", engine)[0].excluded_words == ("เป้า", "target")
    engine.dispose()


@pytest.mark.parametrize("words", [[], "เป้า", ["เป้า", ""], [5]])
def test_sync_rejects_invalid_words(tmp_path, caplog, words):
    engine = _sync(tmp_path, _contract(words))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM schema_metrics")).scalar() == 0
    assert "excluded_words must be a non-empty list of words" in caplog.text
    engine.dispose()


def test_absent_words_store_null(tmp_path):
    engine = _sync(tmp_path, _contract(...))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT excluded_words FROM schema_metrics")).scalar() is None
    engine.dispose()


def test_migration_adds_the_column_once(capsys):
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE schema_metrics (id INTEGER PRIMARY KEY, context_name TEXT NOT NULL, "
                                 "metric_id TEXT NOT NULL, name_th TEXT NOT NULL, expr TEXT NOT NULL, ranking TEXT, "
                                 "extra_columns TEXT, datasets TEXT)")
        migrate(engine)
        assert "Added schema_metrics.excluded_words." in capsys.readouterr().out
        assert "excluded_words" in {c["name"] for c in inspect(engine).get_columns("schema_metrics")}
        migrate(engine)
        assert "Added schema_metrics.excluded_words." not in capsys.readouterr().out
    finally:
        engine.dispose()
