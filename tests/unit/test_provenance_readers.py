"""Plan 8.1 — the prompt, RAG, routing and a key's reach read `active` rows only.

A machine's proposal (bootstrap's levels, the learner's mappings, a user's SQL correction) and a row a person
rejected sit in the same tables as the knowledge in use; every reader that feeds a model — or decides what a key
may reach — must leave them out, or a guess is used before anyone has looked at it.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import sessionmaker

from tests.unit import knowledge_db

# each table: one row in use, one waiting for a person, one a person said no to
SEED = """
CREATE TABLE keyword_value_index (keyword TEXT, column_name TEXT, column_value TEXT, table_name TEXT, context_name TEXT);
CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT UNIQUE, is_active BOOLEAN DEFAULT 1);
INSERT INTO workspaces (id, name) VALUES (1, 'default');
INSERT INTO schema_contexts (name, main_view, keywords, priority, workspace_id) VALUES
    ('ctx_on', 'v', '["ใช้"]', 3, 1), ('ctx_wait', 'v_wait', '["รอ"]', 2, 1), ('ctx_no', 'v_no', '["ไม่"]', 1, 1);
INSERT INTO schema_metadata (table_name, column_name, description) VALUES
    ('v', 'col_on', 'ใช้'), ('v', 'col_wait', 'รอ'), ('v', 'col_no', 'ไม่');
INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, table_name) VALUES
    ('R_ON', 'ใช้', 'ใช้', 'v'), ('R_WAIT', 'รอ', 'รอ', 'v'), ('R_NO', 'ไม่', 'ไม่', 'v');
INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition) VALUES
    ('kw_on', 'c', '= 1'), ('kw_wait', 'c', '= 2'), ('kw_no', 'c', '= 3');
INSERT INTO golden_examples (question_pattern, expected_sql, category, is_active) VALUES
    ('q_on', 'SELECT 1', 'ctx_on', 1), ('q_wait', 'SELECT 2', 'ctx_on', 1), ('q_no', 'SELECT 3', 'ctx_on', 1);
INSERT INTO data_warnings (code, keywords, columns_to_check, message) VALUES
    ('W_ON', '["ใช้"]', '[]', 'ใช้'), ('W_WAIT', '["รอ"]', '[]', 'รอ'), ('W_NO', '["ไม่"]', '[]', 'ไม่');
INSERT INTO vanna_documentation (doc_key, title, content) VALUES
    ('d_on', 'ใช้', 'ใช้'), ('d_wait', 'รอ', 'รอ'), ('d_no', 'ไม่', 'ไม่');
INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, level_columns, detection_keywords) VALUES
    ('ctx_on', 0, 'ระดับใช้', 'On', '["col_on"]', '["ระดับใช้"]'),
    ('ctx_on', 1, 'ระดับรอ', 'Wait', '["col_wait"]', '["ระดับรอ"]'),
    ('ctx_on', 2, 'ระดับไม่', 'No', '["col_no"]', '["ระดับไม่"]');
INSERT INTO master_hierarchy_values (context_name, level, value, aliases) VALUES
    ('ctx_on', 0, 'ค่าใช้', '["alias_on"]'), ('ctx_on', 0, 'ค่ารอ', '["alias_wait"]'),
    ('ctx_on', 0, 'ค่าไม่', '["alias_no"]'), ('ctx_on', 1, 'ค่าในระดับรอ', '["alias_level_wait"]');
"""
MARKS = {  # table: (column, marks the proposed row, marks the rejected row)
    "schema_contexts": ("name", "wait", "_no"), "schema_metadata": ("column_name", "wait", "_no"),
    "schema_business_rules": ("rule_code", "WAIT", "_NO"), "schema_semantic_mapping": ("keyword", "wait", "_no"),
    "golden_examples": ("question_pattern", "wait", "_no"), "data_warnings": ("code", "WAIT", "_NO"),
    "vanna_documentation": ("doc_key", "wait", "_no"), "master_hierarchy": ("level_label_th", "รอ", "ไม่"),
    "master_hierarchy_values": ("value", "ค่ารอ", "ค่าไม่"),
}


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "config.db"
    engine = knowledge_db.make(path, SEED)
    with engine.begin() as conn:
        for table, (column, wait, no) in MARKS.items():
            conn.exec_driver_sql(f"UPDATE {table} SET status = 'proposed' WHERE {column} LIKE '%{wait}%'")
            conn.exec_driver_sql(f"UPDATE {table} SET status = 'rejected' WHERE {column} LIKE '%{no}%'")
    from app.services import hierarchy_service as hs
    from app.services.ai import hierarchy_context
    monkeypatch.setattr(hs.settings, "CONFIG_DB_URL", f"sqlite:///{path}")
    monkeypatch.setattr(hierarchy_context, "_HIERARCHY_CACHE", {})
    monkeypatch.setattr(hierarchy_context, "_HIERARCHY_CACHE_TS", 0.0)
    monkeypatch.setattr("app.db.session.ConfigSessionLocal", sessionmaker(bind=engine))
    return path, engine


def _service(engine):
    from app.services.schema_service import SchemaService
    return SchemaService(config_engine=engine, business_engine=engine)


def test_the_system_prompts_parts_read_active_rows_only(db):
    from app.services.schema import context_store
    _, engine = db
    service = _service(engine)
    assert [c["name"] for c in context_store.get_all_contexts(service)] == ["ctx_on"]
    assert context_store.get_context_info(service, "ctx_wait") is None
    assert [m["column_name"] for m in service.get_schema_metadata("v")] == ["col_on"]
    assert [r["rule_code"] for r in service.get_business_rules("v")] == ["R_ON"]
    assert [m["keyword"] for m in service.get_semantic_mappings(context_name="all")] == ["kw_on"]
    rule = service.build_hierarchy_rule_text("ctx_on")
    assert "ระดับใช้" in rule and "ระดับรอ" not in rule and "ระดับไม่" not in rule


def test_level_detection_values_and_known_terms_read_active_rows_only(db, monkeypatch):
    from app.services import hierarchy_service as hs
    from app.services.ai import hierarchy_context
    from app.services.schema import keyword_index
    _, engine = db
    levels = hierarchy_context.load_hierarchies_from_db()["ctx_on"]
    assert [lv["label_th"] for lv in levels] == ["ระดับใช้"]
    monkeypatch.setattr("app.services.data_sources.policy_for_context", lambda ctx: "full")
    found = {m["value"] for q in ("alias_on", "alias_wait", "alias_no", "alias_level_wait")
             for m in hs.HierarchyService().search_aliases("ctx_on", q)}
    assert found == {"ค่าใช้"}
    keyword_index._known_terms_cache.clear()
    terms = set(keyword_index.get_known_terms(_service(engine), "ctx_on"))
    assert "ค่าใช้" in terms and not {"ค่ารอ", "ค่าไม่", "alias_wait", "alias_no"} & terms
    keyword_index._known_terms_cache.clear()


def test_checks_warnings_and_what_a_key_may_reach_read_active_rows_only(db):
    from app.api.v1.query import contexts_for
    from app.services.validation_service import ValidationService
    from app.services.warning_detector import _load_warnings_from_db
    from app.services.workspaces import allowed_contexts
    _, engine = db
    session = sessionmaker(bind=engine)()
    assert [r["rule_code"] for r in ValidationService(session)._load_rules_from_db()] == ["R_ON"]
    assert [w["code"] for w in _load_warnings_from_db()] == ["W_ON"]
    assert allowed_contexts(SimpleNamespace(workspace_id=1, allowed_contexts=None), config_engine=engine) == {"ctx_on"}
    assert [c.name for c in contexts_for(None, session)] == ["ctx_on"]


def test_the_brain_is_trained_on_active_rows_only(db):
    from app.services.vanna_service import VannaService
    _, engine = db
    trainer = MagicMock()
    trainer._keep = SimpleNamespace(context=lambda name: True, view=lambda name: True)
    VannaService._sync_documentation(trainer, _service(engine))
    VannaService._sync_golden_examples(trainer, _service(engine))
    trained = " ".join(str(call) for call in trainer.train.call_args_list)
    assert "kw_on" in trained and "q_on" in trained and "R_ON" in trained and "## ใช้" in trained
    for waiting_or_rejected in ("kw_wait", "kw_no", "q_wait", "q_no", "R_WAIT", "R_NO", "## รอ", "## ไม่"):
        assert waiting_or_rejected not in trained, waiting_or_rejected
