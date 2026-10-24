"""Metrics migration is repeatable and the provenance migration tolerates older deployments."""

import pytest
from sqlalchemy import create_engine, inspect, text

from app.services.provenance import DECLARED_FIELDS, missing_provenance
from scripts.migrate_schema_metrics import migrate
from scripts.migrate_knowledge_provenance import migrate as migrate_provenance
from tests.unit import knowledge_db


def test_migration_creates_columns_indexes_defaults_and_is_idempotent():
    engine = create_engine("sqlite://")
    migrate(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("schema_metrics")}
    assert columns == set(DECLARED_FIELDS["schema_metrics"]) | {
        "id", "context_name", "metric_id", "source", "status", "confidence", "is_active", "created_at", "updated_at"}
    indexes = {i["name"]: i for i in inspect(engine).get_indexes("schema_metrics")}
    assert indexes["ux_schema_metrics_context_metric"]["unique"]
    assert indexes["ux_schema_metrics_context_metric"]["column_names"] == ["context_name", "metric_id"]
    assert indexes["ix_schema_metrics_context_name"]["column_names"] == ["context_name"]
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO schema_metrics (context_name, metric_id, name_th, expr) "
                          "VALUES ('feed_ebt', 'ebt', 'กำไร', '1')"))
        before = conn.execute(text("SELECT * FROM schema_metrics")).all()
        assert conn.execute(text("SELECT status, is_active, created_at, updated_at FROM schema_metrics")).one() == (
            "active", 1, before[0]._mapping["created_at"], before[0]._mapping["updated_at"])
        assert before[0]._mapping["created_at"] is not None
    migrate(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT * FROM schema_metrics")).all() == before
    assert inspect(engine).get_indexes("schema_metrics") == list(indexes.values())
    with pytest.raises(Exception), engine.begin() as conn:
        conn.execute(text("INSERT INTO schema_metrics (context_name, metric_id, name_th, expr) "
                          "VALUES ('feed_ebt', 'ebt', 'duplicate', '2')"))
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO schema_metrics (context_name, metric_id, name_th, expr) "
                          "VALUES ('other', 'ebt', 'allowed', '2')"))
    engine.dispose()


def test_provenance_migration_without_schema_metrics(tmp_path):
    engine = knowledge_db.make(tmp_path / "config.db", "DROP TABLE schema_metrics;")
    summary = migrate_provenance(engine)
    assert "schema_metrics" not in summary
    assert "schema_metrics" not in inspect(engine).get_table_names()
    assert missing_provenance(engine) == []
    engine.dispose()


def test_provenance_migration_skips_absent_legacy_tables():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_business_rules (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO schema_business_rules VALUES (1)"))
    assert migrate_provenance(engine) == {"schema_business_rules": [("manual", "active", 1)]}
    assert migrate_provenance(engine) == {"schema_business_rules": [("manual", "active", 1)]}
    engine.dispose()


def test_migration_adds_ranking_to_a_table_created_before_it():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_metrics (id INTEGER PRIMARY KEY, context_name TEXT NOT NULL, "
                          "metric_id TEXT NOT NULL, name_th TEXT NOT NULL, expr TEXT NOT NULL, source TEXT, "
                          "status TEXT NOT NULL DEFAULT 'active', is_active INTEGER DEFAULT 1)"))
        conn.execute(text("INSERT INTO schema_metrics (context_name, metric_id, name_th, expr) VALUES ('c', 'm', 'n', '1')"))
    migrate(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("schema_metrics")}
    assert "ranking" in columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT ranking FROM schema_metrics")).scalar() is None
    migrate(engine)  # second run: nothing to add
    engine.dispose()
