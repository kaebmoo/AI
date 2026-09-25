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


def test_the_cumulative_columns_pass2_names_are_active_rows_only(db):
    from app.services.ai.hybrid_flow import _cumulative_columns
    _, engine = db
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE schema_metadata SET data_type = 'double', is_summable = 0 WHERE table_name = 'v'")
    assert _cumulative_columns("v", engine) == ["col_on"]


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
    assert not {"ค่าในระดับรอ", "alias_level_wait"} & terms  # an active value under a level still waiting
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


def test_the_brain_trains_the_ddl_of_contexts_in_use_only(db):
    """_sync_ddl read is_active alone — a proposed context's main view was trained (Codex review 2026-09-22)."""
    from app.services.vanna_service import VannaService
    _, engine = db
    with engine.begin() as conn:
        for view in ("v", "v_wait", "v_no"):
            conn.exec_driver_sql(f"CREATE TABLE {view} (x INTEGER)")
    trainer = MagicMock()
    trainer._keep = SimpleNamespace(context=lambda name: True, view=lambda name: True)
    VannaService._sync_ddl(trainer, _service(engine))
    trained = [call.kwargs["ddl"] for call in trainer.train.call_args_list]
    assert trained == ["CREATE TABLE v (x INTEGER)"]


def test_the_admin_agents_tools_hand_its_model_active_rows_only(db):
    """The Admin Agent (and nt_admin_mcp, which runs the same tools) sends a tool's result to its model: a search
    returned proposals and rejected rows as if in use (Codex review round 2, R2-2)."""
    import asyncio
    import json

    from app.tools.admin.example_tools import SearchExamplesTool
    from app.tools.admin.mapping_tools import SearchMappingsTool
    from app.tools.admin.rule_tools import SearchRulesTool
    from app.tools.admin.system_tools import ListContextsTool
    _, engine = db
    with engine.begin() as conn:  # in use by status, switched off by a person: not knowledge either
        conn.exec_driver_sql("INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, is_active, "
                             "status) VALUES ('R_OFF', 'ปิด', 'ปิด', 0, 'active')")
    session = sessionmaker(bind=engine)()
    sent = json.dumps([asyncio.run(tool().execute({}, session))["data"]
                       for tool in (SearchExamplesTool, SearchMappingsTool, SearchRulesTool, ListContextsTool)],
                      ensure_ascii=False, default=str)
    for mark in ("q_on", "kw_on", "R_ON", "ctx_on"):
        assert mark in sent
    for mark in ("q_wait", "q_no", "kw_wait", "kw_no", "R_WAIT", "R_NO", "R_OFF", "ctx_wait", "ctx_no"):
        assert mark not in sent


def test_an_add_tools_duplicate_answer_names_a_waiting_or_rejected_row_without_its_content(db, monkeypatch):
    """AddMapping / AddRule answer "already there" to the agent's model: the fallback returned the row's condition /
    description whatever its status — a proposal's or a rejected row's content reached the model (review round 2).
    DedupEngine's own answer carried only id + type; the tools' fallback (DedupEngine failing) carried the content."""
    import asyncio
    import json

    from app.services import dedup_engine
    from app.tools.admin.mapping_tools import AddMappingTool
    from app.tools.admin.rule_tools import AddRuleTool
    path, engine = db
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE schema_semantic_mapping SET target_condition = 'COND_' || keyword")
        conn.exec_driver_sql("UPDATE schema_business_rules SET rule_description = 'DESC_' || rule_code")
    session = sessionmaker(bind=engine)()

    def ask(tool, params):
        return json.dumps(asyncio.run(tool().execute(params, session)), ensure_ascii=False, default=str)

    for dedup_fails in (True, False):  # the tools' own fallback (where the content leaked), then DedupEngine's path
        with monkeypatch.context() as m:
            if dedup_fails:
                m.setattr(dedup_engine, "DedupEngine", None)
            for kw in ("kw_wait", "kw_no"):
                sent = ask(AddMappingTool, {"keyword": kw, "target_column": "c", "target_value": "x"})
                assert f"COND_{kw}" not in sent and '"success": false' in sent
            for code in ("R_WAIT", "R_NO"):
                sent = ask(AddRuleTool, {"rule_code": code, "description": "x", "rule_category": "filter"})
                assert f"DESC_{code}" not in sent and '"success": false' in sent
            assert "COND_kw_on" in ask(AddMappingTool, {"keyword": "kw_on", "target_column": "c", "target_value": "x"})
            assert "DESC_R_ON" in ask(AddRuleTool, {"rule_code": "R_ON", "description": "x", "rule_category": "filter"})
    assert knowledge_db.rows(path, "SELECT count(*) FROM schema_semantic_mapping") == [(3,)]  # nothing added
