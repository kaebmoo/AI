"""Plan 8.1 migration: every knowledge row says where it came from, and nothing else about it changes.

The tables keep their own UNIQUE keys (a proposed row cannot sit beside the active one), so a version that
waits for a person goes to knowledge_proposals — one open proposal per key and proposer.
"""

import sqlite3

import pytest
from sqlalchemy import create_engine, text

from scripts.migrate_knowledge_provenance import TABLES, migrate

DDL = """
CREATE TABLE data_sources (id INTEGER PRIMARY KEY, name TEXT UNIQUE, contract_file TEXT);
CREATE TABLE source_tables (id INTEGER PRIMARY KEY, source_id INTEGER, table_name TEXT);
CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, main_view TEXT,
    is_active BOOLEAN DEFAULT 1, source_id INTEGER);
CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY, table_name TEXT NOT NULL, column_name TEXT NOT NULL,
    description TEXT, UNIQUE(table_name, column_name));
CREATE TABLE schema_business_rules (id INTEGER PRIMARY KEY, rule_code TEXT NOT NULL UNIQUE, is_active BOOLEAN DEFAULT 1);
CREATE TABLE golden_examples (id INTEGER PRIMARY KEY, question_pattern TEXT NOT NULL, category VARCHAR,
    is_active BOOLEAN, added_by INTEGER);
CREATE TABLE schema_semantic_mapping (id INTEGER PRIMARY KEY, keyword TEXT NOT NULL UNIQUE, is_active BOOLEAN DEFAULT 1);
CREATE TABLE master_hierarchy (id INTEGER PRIMARY KEY, context_name TEXT NOT NULL, level INTEGER NOT NULL,
    is_active BOOLEAN DEFAULT 1, source TEXT DEFAULT 'auto', UNIQUE(context_name, level));
CREATE TABLE master_hierarchy_values (id INTEGER PRIMARY KEY, context_name TEXT NOT NULL, level INTEGER NOT NULL,
    value TEXT NOT NULL, source TEXT DEFAULT 'auto', is_active BOOLEAN DEFAULT 1, UNIQUE(context_name, level, value));
CREATE TABLE data_warnings (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, is_active INTEGER DEFAULT 1);
CREATE TABLE vanna_documentation (id INTEGER PRIMARY KEY, doc_key TEXT NOT NULL UNIQUE, category TEXT,
    context_name TEXT, updated_at DATETIME DEFAULT '2026-03-23 06:57:55');
CREATE TRIGGER update_vanna_doc_timestamp AFTER UPDATE ON vanna_documentation FOR EACH ROW
BEGIN UPDATE vanna_documentation SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id; END;

INSERT INTO data_sources VALUES (1, 'legacy', NULL), (4, 'datafeed_revenue', '/x/contract.yaml');
INSERT INTO source_tables VALUES (1, 4, 'feed_revenue_fact_bu_monthly');
INSERT INTO schema_contexts VALUES (1, 'revenue', 'revenue_search', 1, 1), (16, 'feed_revenue', 'feed_revenue_fact_bu_monthly', 1, 4);
INSERT INTO schema_metadata VALUES (1, 'revenue_search', 'year', 'ปี'), (2, 'feed_revenue_fact_bu_monthly', 'bu', 'กลุ่มธุรกิจ');
INSERT INTO schema_business_rules VALUES (1, 'REVENUE_UNIT', 1);
INSERT INTO golden_examples VALUES (1, 'รายได้รายสายงาน', 'revenue', 1, NULL),
    (51, 'รายได้รวมทั้งบริษัทเดือนมกราคม 2567 เท่าไร', 'feed_revenue', 1, NULL),
    (125, 'รายได้รวม', 'feed_revenue', 1, 'golive-F11-review'), (40, 'แบบ cascading', 'pl_monthly_cascading', 0, NULL);
INSERT INTO schema_semantic_mapping VALUES (1, 'นป.', 1);
INSERT INTO master_hierarchy VALUES (1, 'revenue', 0, 1, 'manual'), (2, 'feed_revenue', 0, 1, 'auto');
INSERT INTO master_hierarchy_values VALUES (1, 'revenue', 0, 'Digital', 'manual', 1), (2, 'feed_revenue', 0, '3.mobile', 'auto', 1);
INSERT INTO data_warnings VALUES (1, 'OTHER_REVENUE_NOT_NET', 1);
INSERT INTO vanna_documentation (id, doc_key, category, context_name) VALUES
    (1, 'guide_tables', 'guide', NULL), (511, 'datafeed_revenue_rule_ytd', 'datafeed', 'feed_revenue');
"""


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "config.db"
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    conn.close()
    return path


def _dump(path) -> list:
    conn = sqlite3.connect(path)
    try:
        return list(conn.iterdump())
    finally:
        conn.close()


def _source(path, table, row_id):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT source, status, confidence FROM {table} WHERE id = ?", (row_id,)).fetchone()
    finally:
        conn.close()


def test_existing_rows_get_the_provenance_that_matches_how_they_were_written(db):
    migrate(create_engine(f"sqlite:///{db}"))
    expected = {
        ("schema_contexts", 1): "manual", ("schema_contexts", 16): "declared",  # a contract source's context
        ("schema_metadata", 1): "manual", ("schema_metadata", 2): "declared",   # a table the contract registered
        ("golden_examples", 1): "manual", ("golden_examples", 51): "declared",  # generated from control totals
        ("golden_examples", 125): "manual",  # proposed by a session, accepted by the owner (F11)
        ("golden_examples", 40): "manual",
        ("master_hierarchy", 1): "manual", ("master_hierarchy", 2): "manual",  # every level was a person's call
        ("master_hierarchy_values", 1): "manual", ("master_hierarchy_values", 2): "inferred",  # extracted from data
        ("schema_business_rules", 1): "manual", ("schema_semantic_mapping", 1): "manual",
        ("data_warnings", 1): "manual",
        ("vanna_documentation", 1): "manual", ("vanna_documentation", 511): "declared",
    }
    for (table, row_id), source in expected.items():
        assert _source(db, table, row_id) == (source, "active", None), (table, row_id)


def test_a_second_run_changes_nothing_and_old_columns_never_move(db):
    before = sqlite3.connect(db).execute("SELECT id, updated_at FROM vanna_documentation ORDER BY id").fetchall()
    engine = create_engine(f"sqlite:///{db}")
    migrate(engine)
    once = _dump(db)
    migrate(engine)
    assert _dump(db) == once
    # the updated_at trigger is lifted for the backfill and put back unchanged
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT id, updated_at FROM vanna_documentation ORDER BY id").fetchall() == before
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger'").fetchone() == (1,)
    conn.execute("UPDATE vanna_documentation SET category = 'guide' WHERE id = 1")  # still stamps a real edit
    assert conn.execute("SELECT updated_at FROM vanna_documentation WHERE id = 1").fetchone() != (before[0][1],)
    for table in TABLES:
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert {"source", "status", "confidence"} <= columns, table


def test_one_open_proposal_per_key_and_proposer(db):
    engine = create_engine(f"sqlite:///{db}")
    migrate(engine)
    row = {"t": "schema_contexts", "k": '{"name": "feed_revenue"}', "p": '{"instruction_th": "v2"}'}
    insert = text("INSERT INTO knowledge_proposals (table_name, row_key, proposed, source, status) "
                  "VALUES (:t, :k, :p, :s, :st)")
    with engine.begin() as conn:
        conn.execute(insert, {**row, "s": "declared", "st": "rejected"})  # a decided one does not block
        conn.execute(insert, {**row, "s": "declared", "st": "proposed"})
        conn.execute(insert, {**row, "s": "inferred", "st": "proposed"})  # another proposer may wait too
    with pytest.raises(Exception), engine.begin() as conn:
        conn.execute(insert, {**row, "s": "declared", "st": "proposed"})


def test_a_failed_backfill_leaves_the_trigger_and_the_labels_as_they_were(db, monkeypatch):
    """pysqlite began the transaction only at the first UPDATE: the DROP TRIGGER before it committed on its own, and
    a backfill that failed rolled back without the trigger (Codex review 2026-09-22)."""
    import scripts.migrate_knowledge_provenance as mig
    monkeypatch.setattr(mig, "BACKFILL", mig.BACKFILL + ("UPDATE no_such_table SET x = 1",))
    with pytest.raises(sqlite3.OperationalError):
        migrate(create_engine(f"sqlite:///{db}"))
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger'").fetchone() == (1,)
    assert conn.execute("SELECT count(*) FROM vanna_documentation WHERE source IS NOT NULL").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name = 'knowledge_proposals'").fetchone() == (0,)
    monkeypatch.undo()
    migrate(create_engine(f"sqlite:///{db}"))  # the next run completes what the failed one left
    assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger'").fetchone() == (1,)
    assert conn.execute("SELECT count(*) FROM vanna_documentation WHERE source IS NULL").fetchone() == (0,)
