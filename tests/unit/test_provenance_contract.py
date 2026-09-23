"""Plan 8.1 — the contract's writers: they replace their own earlier declaration, never a person's row.

D-C (owner 2026-09-21): contract against admin waits for a person every time — the admin's row stays in use and
the contract's version waits in knowledge_proposals. What the admin owns on a declared row (keywords, priority,
on/off) the contract never touches. What a new contract no longer declares goes — the contract's own rows only.
"""

import copy
import sqlite3

import pytest
from sqlalchemy import text

from app.services import datafeed_knowledge as dk
from scripts.datafeed.gen_golden_from_controls import save_examples
from tests.unit import knowledge_db
from tests.unit.test_datafeed_knowledge import CONTRACT

V2 = copy.deepcopy(CONTRACT)
V2["business_rules"] = [{"id": "r2", "text": "กฎใหม่"}]
V2["datasets"][0]["columns"] = [
    {"name": "year_month", "dtype": "Int64", "description": "งวด ค.ศ."},  # changed: the contract's own row
    {"name": "bu", "dtype": "string", "description": "กลุ่มธุรกิจ"},    # changed: a person's row
]                                                                          # revenue: no longer declared

META = "SELECT column_name, description, source FROM schema_metadata ORDER BY column_name"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "config.db"
    engine = knowledge_db.make(path)
    return path, engine


def _sync(engine, contract):
    with engine.begin() as conn:
        dk.sync_knowledge(conn, "x", contract)


def test_the_same_contract_twice_writes_nothing(db):
    path, engine = db
    _sync(engine, CONTRACT)
    first = list(sqlite3.connect(path).iterdump())
    _sync(engine, CONTRACT)
    assert list(sqlite3.connect(path).iterdump()) == first  # not even a timestamp
    assert knowledge_db.rows(path, "SELECT DISTINCT source, status FROM schema_metadata") == [("declared", "active")]


def test_a_new_contract_replaces_its_own_rows_and_waits_for_a_persons(db):
    path, engine = db
    _sync(engine, CONTRACT)
    with engine.begin() as conn:  # what admin endpoints leave behind (tests/unit/test_provenance_people.py)
        conn.exec_driver_sql("UPDATE schema_contexts SET keywords = '[\"mine\"]', priority = 7, is_active = 0")
        conn.exec_driver_sql("UPDATE schema_metadata SET description = 'BG ของ admin', source = 'manual' "
                             "WHERE column_name = 'bu'")
        conn.exec_driver_sql("INSERT INTO schema_metadata (table_name, column_name, description, source) "
                             "VALUES ('feed_x_fact_bu_monthly', 'note', 'คอลัมน์ที่ admin เพิ่ม', 'manual')")
        conn.exec_driver_sql("UPDATE vanna_documentation SET is_active = 0 WHERE doc_key = 'datafeed_x_period_format'")
    _sync(engine, V2)

    assert knowledge_db.rows(path, META) == [
        ("bu", "BG ของ admin", "manual"),              # the person's version stays in use
        ("note", "คอลัมน์ที่ admin เพิ่ม", "manual"),   # not the contract's to withdraw
        ("year_month", "งวด ค.ศ.", "declared"),        # revenue went with the contract that declared it
    ]
    assert knowledge_db.rows(path, "SELECT table_name, row_key, proposed, source, status FROM knowledge_proposals") == [
        ("schema_metadata", '{"column_name": "bu", "table_name": "feed_x_fact_bu_monthly"}',
         '{"data_type": "string", "description": "กลุ่มธุรกิจ", "is_groupable": 1, "is_summable": 0}',
         "declared", "proposed")]
    keywords, priority, active, instruction, source = knowledge_db.rows(
        path, "SELECT keywords, priority, is_active, instruction_th, source FROM schema_contexts")[0]
    assert (keywords, priority, active, source) == ('["mine"]', 7, 0, "declared")  # the admin's fields are theirs
    assert "กฎใหม่" in instruction and "กฎหนึ่ง" not in instruction                  # the contract's are its own
    docs = dict(knowledge_db.rows(path, "SELECT doc_key, is_active FROM vanna_documentation"))
    assert "datafeed_x_rule_r2" in docs and "datafeed_x_rule_r1" not in docs
    assert docs["datafeed_x_period_format"] == 0  # switched off by the admin, not switched back on


def test_a_context_whose_instruction_a_person_rewrote_keeps_it(db):
    path, engine = db
    _sync(engine, CONTRACT)
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE schema_contexts SET instruction_th = 'admin เขียนเอง', source = 'manual'")
    _sync(engine, V2)
    assert knowledge_db.rows(path, "SELECT instruction_th FROM schema_contexts") == [("admin เขียนเอง",)]
    assert knowledge_db.rows(path, "SELECT table_name FROM knowledge_proposals") == [("schema_contexts",)]


def test_golden_regeneration_keeps_the_examples_a_person_accepted(db):
    path, _ = db
    conn = sqlite3.connect(path)
    conn.executescript("""
        INSERT INTO golden_examples (id, question_pattern, expected_sql, category, is_active, source)
            VALUES (51, 'รายได้รวมเดือนมกราคม 2567', 'SELECT 1', 'feed_x', 1, 'declared'),
                   (52, 'รายได้เดือนสิงหาคม 2567', 'SELECT 2', 'feed_x', 1, 'declared'),
                   (125, 'รายได้รวม', 'SELECT revenue_ytd', 'feed_x', 1, 'manual'),
                   (126, 'รายได้ BG1 มกราคม 2567', 'SELECT admin', 'feed_x', 1, 'manual');""")
    examples = [("รายได้รวมเดือนมกราคม 2567", "SELECT 1"),        # unchanged
                ("รายได้ BG1 มกราคม 2567", "SELECT generated"),   # a person's version of the same question
                ("รายได้เดือนมีนาคม 2568", "SELECT 3")]            # new
    assert save_examples(conn, "feed_x", examples) == (1, 1, 1)
    assert save_examples(conn, "feed_x", examples) == (0, 0, 0)  # a second run: nothing new, nothing proposed twice
    conn.commit()
    assert knowledge_db.rows(path, "SELECT id, question_pattern, expected_sql, source FROM golden_examples "
                                   "WHERE id != 127 ORDER BY id") == [
        (51, "รายได้รวมเดือนมกราคม 2567", "SELECT 1", "declared"),
        (125, "รายได้รวม", "SELECT revenue_ytd", "manual"),
        (126, "รายได้ BG1 มกราคม 2567", "SELECT admin", "manual")]
    assert knowledge_db.rows(path, "SELECT question_pattern, source FROM golden_examples WHERE id = 127") == [
        ("รายได้เดือนมีนาคม 2568", "declared")]
    assert len(knowledge_db.rows(path, "SELECT 1 FROM knowledge_proposals WHERE status = 'proposed'")) == 1


def test_golden_regeneration_changes_only_the_contracts_row_when_a_person_asked_the_same_question(db):
    """golden_examples has no key: a person's row beside the contract's, same question, used to be rewritten too."""
    path, _ = db
    conn = sqlite3.connect(path)
    conn.executescript("""
        INSERT INTO golden_examples (id, question_pattern, expected_sql, category, is_active, source, status) VALUES
            (60, 'รายได้รวมปีนี้', 'SELECT admin', 'feed_x', 1, 'manual', 'active'),
            (61, 'รายได้รวมปีนี้', 'SELECT old', 'feed_x', 1, 'declared', 'active');""")
    assert save_examples(conn, "feed_x", [("รายได้รวมปีนี้", "SELECT new")]) == (1, 0, 0)
    conn.commit()
    assert knowledge_db.rows(path, "SELECT id, expected_sql, source FROM golden_examples ORDER BY id") == [
        (60, "SELECT admin", "manual"), (61, "SELECT new", "declared")]


def test_golden_regeneration_leaves_a_rejected_example_alone(db):
    path, _ = db
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO golden_examples (id, question_pattern, expected_sql, category, is_active, source, status) "
                 "VALUES (70, 'ถาม', 'SELECT 1', 'feed_x', 1, 'declared', 'rejected')")
    assert save_examples(conn, "feed_x", []) == (0, 0, 0)                     # not withdrawn
    assert save_examples(conn, "feed_x", [("ถาม", "SELECT 1")]) == (0, 0, 0)  # not declared again
    assert save_examples(conn, "feed_x", [("ถาม", "SELECT 2")]) == (0, 0, 1)  # a new version waits for a person
    conn.commit()
    assert knowledge_db.rows(path, "SELECT id, expected_sql, status FROM golden_examples") == [(70, "SELECT 1", "rejected")]


def test_a_person_editing_between_the_contracts_read_and_write_wins(db):
    path, engine = db
    _sync(engine, CONTRACT)
    key = {"table_name": "feed_x_fact_bu_monthly", "column_name": "bu"}
    values = {"description": "contract ฉบับใหม่", "data_type": "string", "is_summable": 0, "is_groupable": 1}
    with engine.begin() as conn:
        stale = conn.execute(text("SELECT source, status, description, data_type, is_summable, is_groupable "
                                  "FROM schema_metadata WHERE column_name = 'bu'")).mappings().first()
        conn.exec_driver_sql("UPDATE schema_metadata SET description = 'คนแก้ระหว่างทาง', source = 'manual' "
                             "WHERE column_name = 'bu'")                      # a person, between the read and the write
        dk._declare(conn, "schema_metadata", key, values, stale, insert={})
        dk._declare(conn, "schema_metadata", key, values, None, insert={})    # read found nothing, the row is there now
    assert knowledge_db.rows(path, "SELECT description, source FROM schema_metadata WHERE column_name = 'bu'") == [
        ("คนแก้ระหว่างทาง", "manual")]
    assert knowledge_db.rows(path, "SELECT table_name, source FROM knowledge_proposals") == [("schema_metadata", "declared")]


def test_golden_regeneration_counts_a_question_written_even_when_a_person_took_one_of_its_rows_meanwhile(db):
    """Two contract rows of one question, one taken by a person between the read and the UPDATE: the other row was
    written, but the count said nothing was (R2-8)."""
    path, _ = db

    class PersonMeanwhile(sqlite3.Connection):
        fired = False

        def execute(self, sql, params=()):
            if sql.startswith("UPDATE golden_examples SET expected_sql") and not self.fired:
                self.fired = True
                super().execute("UPDATE golden_examples SET source = 'manual', expected_sql = 'คน' WHERE id = 81")
            return super().execute(sql, params)

    conn = sqlite3.connect(path, factory=PersonMeanwhile)
    conn.execute("INSERT INTO golden_examples (id, question_pattern, expected_sql, category, source, status) VALUES "
                 "(80, 'ถาม', 'SELECT old', 'feed_x', 'declared', 'active'), "
                 "(81, 'ถาม', 'SELECT old', 'feed_x', 'declared', 'active')")
    assert save_examples(conn, "feed_x", [("ถาม", "SELECT new")]) == (1, 0, 0)  # the contract's row says it now
    conn.commit()
    assert knowledge_db.rows(path, "SELECT id, expected_sql, source FROM golden_examples ORDER BY id") == [
        (80, "SELECT new", "declared"), (81, "คน", "manual")]


def test_a_rejection_outlives_the_contract_withdrawing_and_declaring_the_row_again(db):
    path, engine = db
    _sync(engine, CONTRACT)
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE schema_metadata SET status = 'rejected' WHERE column_name = 'revenue'")
        conn.exec_driver_sql("UPDATE vanna_documentation SET status = 'rejected' WHERE doc_key = 'datafeed_x_rule_r1'")
    _sync(engine, V2)        # withdraws the revenue column and rule r1
    _sync(engine, CONTRACT)  # declares them again
    assert knowledge_db.rows(path, "SELECT source, status FROM schema_metadata WHERE column_name = 'revenue'") == [
        ("declared", "rejected")]
    assert knowledge_db.rows(path, "SELECT source, status FROM vanna_documentation "
                                   "WHERE doc_key = 'datafeed_x_rule_r1'") == [("declared", "rejected")]
