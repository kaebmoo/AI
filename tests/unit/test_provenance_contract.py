"""Plan 8.1 — the contract's writers: they replace their own earlier declaration, never a person's row.

D-C (owner 2026-09-21): contract against admin waits for a person every time — the admin's row stays in use and
the contract's version waits in knowledge_proposals. What the admin owns on a declared row (keywords, priority,
on/off) the contract never touches. What a new contract no longer declares goes — the contract's own rows only.
"""

import copy
import sqlite3

import pytest

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
