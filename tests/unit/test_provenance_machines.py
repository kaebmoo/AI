"""Plan 8.1 — the machine writers: what a person or the contract owns is never changed, run twice or ten times.

A machine's guess is `inferred`; bootstrap's levels wait for a person (8.0 §3.1: the heuristic was wrong for 3 of
the 4 feed contexts). A row a person owns keeps its content and the machine's version waits in knowledge_proposals.
"""

import json
import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services import hierarchy_service as hs
from app.services.context_onboarding import ConfigApplicator, ConfigGenerator
from tests.unit import knowledge_db

SEED = """
INSERT INTO schema_contexts (name, display_name, main_view, keywords, instruction_th) VALUES
    ('ctx_person', 'ของคน', 'v_org', '["คน"]', 'คนเขียน');
INSERT INTO schema_metadata (table_name, column_name, display_name_th, description) VALUES
    ('v_org', 'division', NULL, 'คนเขียน'), ('v_org', 'dept', 'ฝ่าย', 'คนเขียน');
INSERT INTO schema_business_rules (rule_code, rule_name, rule_description) VALUES ('R1', 'ของคน', 'คนเขียน');
INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition) VALUES ('นป.', 'division', '= ''นป.''');
INSERT INTO golden_examples (question_pattern, expected_sql, category, is_active) VALUES ('รายได้รายสายงาน', 'SELECT คน', 'x', 1);
INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, level_columns, detection_keywords,
    source, parent_column, source_view) VALUES
    ('ctx_h', 0, 'สายงาน', 'Division', '["division"]', '["สายงาน"]', 'manual', NULL, 'v_org'),
    ('ctx_h', 1, 'ฝ่าย', 'Department', '["dept"]', '["ฝ่าย"]', 'auto', 'division', 'v_org');
INSERT INTO master_hierarchy_values (context_name, level, value, parent_value, aliases, source) VALUES
    ('ctx_h', 0, 'A', NULL, '["a", "เอ"]', 'manual');
"""
HUMAN = ("manual", "declared")


def _human_rows(path):
    """Every row a person or the contract owns, every column — what no machine may move."""
    conn = sqlite3.connect(path)
    try:
        out = {}
        for table in ("schema_contexts", "schema_metadata", "schema_business_rules", "golden_examples",
                      "schema_semantic_mapping", "master_hierarchy", "master_hierarchy_values"):
            out[table] = conn.execute(f"SELECT * FROM {table} WHERE source IN (?, ?) ORDER BY id", HUMAN).fetchall()
        return out
    finally:
        conn.close()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "config.db"
    engine = knowledge_db.make(path, SEED)
    business = create_engine(f"sqlite:///{tmp_path / 'biz.db'}")
    with business.begin() as c:
        c.execute(text("CREATE TABLE org (division TEXT, dept TEXT, v REAL)"))
        c.execute(text("INSERT INTO org VALUES ('A', 'A1', 1), ('A', 'A2', 1), ('B', 'B1', 1)"))
        c.execute(text("CREATE VIEW v_org AS SELECT * FROM org"))
    monkeypatch.setattr(hs.settings, "CONFIG_DB_URL", f"sqlite:///{path}")
    monkeypatch.setattr(hs, "_data_engine", lambda context_name: business)
    return path, engine, business


def _proposals(path):
    return knowledge_db.rows(path, "SELECT table_name, row_key, source FROM knowledge_proposals ORDER BY id")


def test_bootstrap_guesses_wait_for_a_person_and_leave_a_persons_level(db, monkeypatch):
    path, _, _ = db
    monkeypatch.setattr(hs.HierarchyService, "auto_extract", lambda self, ctx=None: [])
    before = _human_rows(path)
    hs.HierarchyService().bootstrap_from_view("ctx_h", "v_org")  # level 0 is a person's
    hs.HierarchyService().bootstrap_from_view("ctx_new", "v_org")
    hs.HierarchyService().bootstrap_from_view("ctx_new", "v_org")  # a second run: same guesses, still waiting
    assert _human_rows(path) == before
    assert knowledge_db.rows(path, "SELECT level, source, status FROM master_hierarchy WHERE context_name = 'ctx_new' "
                                   "ORDER BY level") == [(0, "inferred", "proposed"), (1, "inferred", "proposed")]
    assert [p for p in _proposals(path) if '"ctx_h"' in p[1]] == [  # both levels are people's (the migration
        ("master_hierarchy", '{"context_name": "ctx_h", "level": 0}', "inferred"),  # labels every existing level
        ("master_hierarchy", '{"context_name": "ctx_h", "level": 1}', "inferred")]  # manual — RESULT §7.5)


def test_extracting_values_twice_leaves_a_persons_values_and_follows_the_level(db):
    from scripts.extract_hierarchy import extract_hierarchy_levels, extract_hierarchy_values, load_defs_from_db
    path, _, business = db
    before = _human_rows(path)
    for _ in range(2):
        conn = sqlite3.connect(path)
        defs = load_defs_from_db(conn, "ctx_h")["ctx_h"]
        extract_hierarchy_levels(conn, "ctx_h", defs)
        extract_hierarchy_values(conn, business, "ctx_h", defs)
        conn.commit()
        conn.close()
    assert _human_rows(path) == before  # value A (a person's aliases) and both levels, to the last column
    assert knowledge_db.rows(path, "SELECT level, value, parent_value, source, status FROM master_hierarchy_values "
                                   "WHERE source = 'inferred' ORDER BY level, value") == [
        (0, "B", None, "inferred", "active"),
        (1, "A1", "A", "inferred", "active"), (1, "A2", "A", "inferred", "active"), (1, "B1", "B", "inferred", "active")]
    assert _proposals(path) == []  # a parent read off the data is not a person's kind of fact


def test_values_of_a_proposed_level_are_proposed_too(db):
    from scripts.extract_hierarchy import extract_hierarchy_values, load_defs_from_db
    path, engine, business = db
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE master_hierarchy SET source = 'inferred', status = 'proposed' WHERE level = 1")
    conn = sqlite3.connect(path)
    extract_hierarchy_values(conn, business, "ctx_h", load_defs_from_db(conn, "ctx_h")["ctx_h"])
    conn.commit()
    assert knowledge_db.rows(path, "SELECT DISTINCT status FROM master_hierarchy_values WHERE level = 1") == [("proposed",)]


ANALYSIS = {
    "context": {"name": "ctx_person", "display_name_th": "เดา", "keywords": ["เดา"], "instruction_th": "LLM"},
    "schema_metadata": [{"column_name": "dept", "display_name_th": "LLM", "description": "LLM"},
                        {"column_name": "new_col", "display_name_th": "ใหม่", "description": "LLM"}],
    "business_rules": [{"rule_code": "R1", "rule_name": "LLM", "rule_description": "LLM"},
                       {"rule_code": "R2", "rule_name": "ใหม่", "rule_description": "LLM"}],
    "golden_examples": [{"question": "รายได้รายสายงาน", "sql": "SELECT LLM", "category": "x"},
                        {"question": "คำถามใหม่", "sql": "SELECT 1", "category": "x"}],
    "semantic_mappings": [{"keyword": "นป.", "target_column": "LLM", "target_condition": "= 1"}],
}


def test_onboarding_twice_fills_new_rows_and_queues_what_a_person_owns(db):
    path, _, _ = db
    before = _human_rows(path)
    bundle = ConfigGenerator("v_org").generate(ANALYSIS)
    for _ in range(2):
        result = ConfigApplicator(str(path)).apply(bundle, dry_run=False)
        assert result["errors"] == []
    assert _human_rows(path) == before
    assert sorted(p[0] for p in _proposals(path)) == [
        "golden_examples", "schema_business_rules", "schema_contexts", "schema_metadata", "schema_semantic_mapping"]
    assert knowledge_db.rows(path, "SELECT column_name, source FROM schema_metadata WHERE column_name = 'new_col'") == [
        ("new_col", "inferred")]
    assert knowledge_db.rows(path, "SELECT count(*), source FROM golden_examples WHERE question_pattern = 'คำถามใหม่'") == [
        (1, "inferred")]  # a second apply no longer adds a duplicate
    assert knowledge_db.rows(path, "SELECT source, status FROM schema_business_rules WHERE rule_code = 'R2'") == [
        ("inferred", "active")]


def test_onboarding_replaces_what_it_wrote_itself(db):
    path, _, _ = db
    ConfigApplicator(str(path)).apply(ConfigGenerator("v_org").generate(ANALYSIS), dry_run=False)
    again = {**ANALYSIS, "business_rules": [{"rule_code": "R2", "rule_name": "แก้แล้ว", "rule_description": "LLM"}]}
    ConfigApplicator(str(path)).apply(ConfigGenerator("v_org").generate(again), dry_run=False)
    assert knowledge_db.rows(path, "SELECT rule_name FROM schema_business_rules WHERE rule_code = 'R2'") == [("แก้แล้ว",)]


def test_copying_metadata_to_a_view_fills_a_stub_and_queues_a_persons_row(db, tmp_path):
    from app.services.schema_service import SchemaService
    from app.services.schema import view_manager
    path, engine, _ = db
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE view_column_mappings (id INTEGER PRIMARY KEY, view_name TEXT, view_column TEXT, "
                             "source_table TEXT, source_column TEXT, mapping_type TEXT)")
        conn.exec_driver_sql("INSERT INTO view_column_mappings (view_name, view_column, source_table, source_column) VALUES "
                             "('v_org', 'division', 'org', 'division'), ('v_org', 'stub', 'org', 'dept')")
        conn.exec_driver_sql("INSERT INTO schema_metadata (table_name, column_name, display_name_th, description, source) "
                             "VALUES ('org', 'division', 'สายงาน', 'จากตารางต้นทาง', 'manual'), "
                             "('org', 'dept', 'ฝ่าย', 'จากตารางต้นทาง', 'manual'), "
                             "('v_org', 'stub', NULL, NULL, 'inferred')")
    before = _human_rows(path)
    for _ in range(2):
        view_manager.propagate_metadata_to_view(SchemaService(config_engine=engine, business_engine=engine), "v_org")
    after = _human_rows(path)
    assert after["schema_metadata"] == before["schema_metadata"]  # v_org.division (a person's, empty name) untouched
    assert knowledge_db.rows(path, "SELECT display_name_th FROM schema_metadata WHERE column_name = 'stub'") == [("ฝ่าย",)]
    assert [p[0] for p in _proposals(path)] == ["schema_metadata"]


def test_analyzer_import_and_detected_families_queue_what_a_person_owns(db, monkeypatch):
    from app.api.v1 import schema_analyzer
    from app.api.v1.admin import schema as admin_schema
    path, engine, _ = db
    session = sessionmaker(bind=engine)()

    class _Svc:
        def refresh_cache(self):
            pass

        def get_table_info(self, table):
            return [{"name": "division", "type": "TEXT"}, {"name": "dept", "type": "TEXT"}]

        def get_dimension_families_with_source(self, table):
            return []

    request = schema_analyzer.ImportRequest(table_name="v_org", metadata=[
        {"column_name": "dept", "display_name_th": "LLM", "display_name_en": "Dept", "description": "LLM",
         "data_type": "TEXT", "is_summable": False, "is_groupable": True},
        {"column_name": "fresh", "display_name_th": "ใหม่", "display_name_en": "New", "description": "LLM",
         "data_type": "TEXT", "is_summable": False, "is_groupable": True}], mappings=[], rules=[])
    before = _human_rows(path)
    assert [schema_analyzer.import_schema_suggestions(request, None, session, _Svc())["waiting_for_a_person"]
            for _ in range(2)] == [1, 0]  # the same suggestion again: nothing new waits
    monkeypatch.setattr(admin_schema, "mark_brain_dirty", lambda: None)
    monkeypatch.setattr(admin_schema, "service_for_table", lambda table, svc: _Svc())
    monkeypatch.setattr("app.services.dimension_detector.detect_families", lambda cols: {"org": ["division", "dept"]})
    for _ in range(2):
        admin_schema.auto_populate_dimension_families("v_org", True, None, session, _Svc())
    assert _human_rows(path) == before
    assert knowledge_db.rows(path, "SELECT source FROM schema_metadata WHERE column_name = 'fresh'") == [("inferred",)]
    assert sorted(p[1] for p in _proposals(path)) == [  # one waiting proposal per row and proposer…
        '{"column_name": "dept", "table_name": "v_org"}', '{"column_name": "division", "table_name": "v_org"}']
    merged = knowledge_db.rows(path, "SELECT proposed FROM knowledge_proposals WHERE row_key LIKE '%dept%'")[0][0]
    assert '"display_name_th":"LLM"' in merged and '"dimension_group":"org"' in merged  # …carrying both writers' fields


def test_onboarding_adds_its_fields_to_a_proposal_another_machine_left(db):
    """_proposal_sql replaced the waiting proposal whole: the column-family detector's dimension_group was lost."""
    path, _, _ = db
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO knowledge_proposals (table_name, row_key, proposed, source) VALUES ('schema_metadata', "
                     "'{\"column_name\": \"dept\", \"table_name\": \"v_org\"}', '{\"dimension_group\": \"org\"}', "
                     "'inferred')")
    for _ in range(2):
        assert ConfigApplicator(str(path)).apply(ConfigGenerator("v_org").generate(ANALYSIS), dry_run=False)["errors"] == []
    (proposed,), = knowledge_db.rows(path, "SELECT proposed FROM knowledge_proposals WHERE table_name = 'schema_metadata' "
                                           "AND row_key LIKE '%\"dept\"%'")
    assert json.loads(proposed)["dimension_group"] == "org" and json.loads(proposed)["description"] == "LLM"
