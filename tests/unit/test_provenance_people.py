"""Plan 8.1 — a person's write is labelled as theirs, and the rule every other writer checks.

A machine never replaces what a person (manual) or the data owner's contract (declared) decided; the contract
replaces its own earlier declaration and what a machine wrote; only a person touches a rejected row. A person
who edits only fields the contract never writes (keywords, priority, dimension family…) leaves a row declared.
"""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app.schemas.admin_schemas import SemanticMappingCreate
from app.services import provenance as p
from tests.unit import knowledge_db

SEED = """
INSERT INTO data_sources (id, name, source_type, contract_file) VALUES (4, 'datafeed_revenue', 'duckdb_file', '/c.yaml');
INSERT INTO schema_contexts (id, name, main_view, keywords, instruction_th, source_id) VALUES
    (16, 'feed_revenue', 'feed_revenue_fact_bu_monthly', '["รายได้"]', 'จาก contract', 4);
INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, level_columns, detection_keywords)
    VALUES ('ctx', 0, 'สายงาน', 'Division', '["division"]', '["สายงาน"]');
INSERT INTO master_hierarchy_values (context_name, level, value) VALUES ('ctx', 0, 'A'), ('ctx', 0, 'B');
"""


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "config.db"
    return path, knowledge_db.make(path, SEED)


@pytest.mark.parametrize("writer, source, status, allowed", [
    ("manual", "declared", "active", True), ("manual", "manual", "rejected", True),
    ("declared", "declared", "active", True), ("declared", "inferred", "proposed", True),
    ("declared", "manual", "active", False), ("declared", "declared", "rejected", False),
    ("inferred", "inferred", "active", True), ("inferred", "learned", "proposed", True),
    ("inferred", "declared", "active", False), ("inferred", "manual", "active", False),
    ("learned", "inferred", "rejected", False),
    ("inferred", None, "active", False), ("inferred", "auto", "active", False),  # unknown = a person's
])
def test_who_may_replace_a_row(writer, source, status, allowed):
    assert p.may_replace(writer, source, status) is allowed


def test_editing_only_what_the_contract_never_writes_leaves_a_row_declared():
    assert p.after_human_edit("schema_contexts", "declared", ["keywords", "priority"]) == "declared"
    assert p.after_human_edit("schema_contexts", "declared", ["keywords", "instruction_th"]) == "manual"
    assert p.after_human_edit("schema_metadata", "declared", ["dimension_group"]) == "declared"
    assert p.after_human_edit("schema_metadata", "inferred", ["dimension_group"]) == "manual"
    assert p.after_human_edit("schema_semantic_mapping", "learned", ["keyword"]) == "manual"


def test_one_waiting_version_per_key_and_a_rejected_one_is_not_proposed_again(db):
    path, engine = db
    key, values = {"name": "feed_revenue"}, {"instruction_th": "v2"}
    with engine.begin() as conn:
        assert p.propose(conn, "schema_contexts", key, values, "declared", reason="a person changed it")
        assert p.propose(conn, "schema_contexts", key, {"instruction_th": "v3"}, "declared")  # replaces the waiting one
    assert [(json.loads(p), s) for p, s in knowledge_db.rows(path, "SELECT proposed, status FROM knowledge_proposals")] == [
        ({"instruction_th": "v3"}, "proposed")]
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE knowledge_proposals SET status = 'rejected'")
        assert not p.propose(conn, "schema_contexts", key, {"instruction_th": "v3"}, "declared")  # said no already
        assert p.propose(conn, "schema_contexts", key, {"instruction_th": "v4"}, "declared")  # a new version waits
    assert len(knowledge_db.rows(path, "SELECT 1 FROM knowledge_proposals")) == 2


def test_a_person_takes_a_keyword_a_machine_only_proposed(db, monkeypatch):
    from app.api.v1.admin import mappings
    path, engine = db
    monkeypatch.setattr(mappings, "mark_brain_dirty", lambda: None)
    monkeypatch.setattr(mappings, "clear_query_cache", lambda: None)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition, source, "
                             "status, confidence) VALUES ('ftth', 'UNKNOWN', '', 'learned', 'proposed', 0.5)")
    session = sessionmaker(bind=engine)()

    class _Schema:
        def refresh_cache(self):
            pass

    data = SemanticMappingCreate(keyword="ftth", target_column="PRODUCT_NAME", target_condition="LIKE '%FTTx%'")
    mappings.create_semantic_mapping(data=data, _current_user=None, db=session, schema_service=_Schema())
    assert knowledge_db.rows(path, "SELECT target_column, source, status, confidence FROM schema_semantic_mapping") == [
        ("PRODUCT_NAME", "manual", "active", 0.5)]
    with pytest.raises(HTTPException):  # a keyword in use is still a duplicate
        mappings.create_semantic_mapping(data=data, _current_user=None, db=session, schema_service=_Schema())


def test_a_person_editing_a_contract_context(db):
    from app.services.schema import context_store
    from app.services.schema_service import SchemaService
    path, engine = db
    service = SchemaService(config_engine=engine, business_engine=engine)
    context_store.update_context(service, 16, {"keywords": ["รายได้", "income"], "priority": 3})
    assert knowledge_db.rows(path, "SELECT source, status FROM schema_contexts WHERE id = 16") == [("declared", "active")]
    context_store.update_context(service, 16, {"instruction_th": "admin เขียนเอง"})
    assert knowledge_db.rows(path, "SELECT source FROM schema_contexts WHERE id = 16") == [("manual",)]
    created = context_store.create_context(service, {"name": "new", "display_name": "ใหม่", "description": None,
                                                     "main_view": "v", "is_active": 1, "priority": 0, "keywords": ["ใหม่"],
                                                     "instruction_th": None, "instruction_en": None})
    assert (created["source"], created["status"]) == ("manual", "active")


def test_a_person_accepting_a_proposed_level_takes_its_values_in_use(db, monkeypatch):
    from app.services import hierarchy_service as hs
    path, engine = db
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE master_hierarchy SET source = 'inferred', status = 'proposed'")
        conn.exec_driver_sql("UPDATE master_hierarchy_values SET source = 'inferred', status = 'proposed'")
    monkeypatch.setattr(hs.settings, "CONFIG_DB_URL", f"sqlite:///{path}")
    hs.HierarchyService().upsert_level("ctx", 0, {"detection_keywords": ["สายงาน", "division"]})
    assert knowledge_db.rows(path, "SELECT source, status FROM master_hierarchy") == [("manual", "active")]
    assert knowledge_db.rows(path, "SELECT DISTINCT status FROM master_hierarchy_values") == [("active",)]
    hs.HierarchyService().create_value("ctx", {"level": 0, "value": "A", "aliases": ["a"]})
    assert knowledge_db.rows(path, "SELECT source, status FROM master_hierarchy_values WHERE value = 'A'") == [
        ("manual", "active")]
