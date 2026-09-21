"""
Unit Tests for Admin Tools (Plan 1)
=====================================
Tests for individual admin tool execution.
"""

import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.tools.admin.base import AdminTool
from app.tools.admin.registry import AdminToolRegistry
from tests.unit import knowledge_db


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def admin_tools_db(tmp_path):
    """Create a temp SQLite DB with config tables matching actual ORM models + sample data."""
    db_path = str(tmp_path / "test_admin.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Schema semantic mapping — matches app/models/schema_models.py SchemaSemanticMapping
    c.execute("""
        CREATE TABLE schema_semantic_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            keyword_type TEXT DEFAULT 'term',
            target_column TEXT NOT NULL,
            target_condition TEXT NOT NULL DEFAULT '',
            full_condition TEXT,
            description TEXT,
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            context_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.executemany(
        "INSERT INTO schema_semantic_mapping (keyword, target_column, target_condition, keyword_type, context_name) VALUES (?, ?, ?, ?, ?)",
        [
            ("ดาต้าคอม", "SERVICE_GROUP", "= 'Datacom'", "value_alias", "revenue"),
            ("มือถือ", "SERVICE_GROUP", "= 'Mobile'", "value_alias", "revenue"),
            ("รายได้", "REVENUE_VALUE", "", "column_alias", None),
        ]
    )

    # Business rules — matches app/models/schema_models.py SchemaBusinessRule
    c.execute("""
        CREATE TABLE schema_business_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_code TEXT UNIQUE NOT NULL,
            rule_name TEXT NOT NULL DEFAULT '',
            rule_description TEXT NOT NULL DEFAULT '',
            table_name TEXT,
            applies_to TEXT,
            example_correct TEXT,
            example_wrong TEXT,
            severity TEXT DEFAULT 'warning',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.executemany(
        "INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, severity) VALUES (?, ?, ?, ?)",
        [
            ("FILTER_001", "ต้องระบุ YEAR", "ต้องระบุ YEAR เสมอ", "warning"),
            ("AGG_001", "ห้าม SUM โดยไม่มี GROUP BY", "ห้าม SUM โดยไม่มี GROUP BY", "error"),
        ]
    )

    # Golden examples — matches app/models/feedback_models.py GoldenExample
    c.execute("""
        CREATE TABLE golden_examples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            question_pattern TEXT NOT NULL,
            expected_sql TEXT NOT NULL,
            category TEXT,
            is_active INTEGER DEFAULT 1,
            added_by INTEGER,
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute(
        "INSERT INTO golden_examples (question_pattern, expected_sql, category) VALUES (?, ?, ?)",
        ("รายได้รวมเดือนมกราคม", "SELECT SUM(REVENUE_VALUE) FROM revenue WHERE MONTH=1", "revenue")
    )

    # Schema contexts — used via raw SQL (no ORM model)
    c.execute("""
        CREATE TABLE schema_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_name TEXT UNIQUE,
            display_name_th TEXT,
            main_view TEXT,
            description TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    c.executemany(
        "INSERT INTO schema_contexts (context_name, display_name_th, main_view) VALUES (?, ?, ?)",
        [
            ("revenue", "รายได้", "v_revenue_monthly"),
            ("expense", "ค่าใช้จ่าย", "v_expense_monthly"),
        ]
    )

    conn.commit()
    conn.close()
    knowledge_db.add_provenance(db_path)  # Plan 8.1 columns the models select
    return db_path


@pytest.fixture(autouse=True)
def app_db(tmp_path):
    """App DB for the add tools' audit (DDL of migration 028) — never the real app.db."""
    from pathlib import Path
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    path = str(tmp_path / "test_app.sqlite")
    conn = sqlite3.connect(path)
    conn.executescript(
        (Path(__file__).resolve().parents[2] / "database/migrations/028_audit_log.sql").read_text(encoding="utf-8"))
    conn.close()
    with patch("app.db.session.SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{path}"))):
        yield path


@pytest.fixture
def mock_db_session(admin_tools_db):
    """Create a mock SQLAlchemy-like session backed by the test DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession

    engine = create_engine(f"sqlite:///{admin_tools_db}")
    session = SASession(engine)
    yield session
    session.close()


# ── Registry Tests ────────────────────────────────────────

class TestAdminToolRegistry:
    """Test admin tool auto-discovery and registry."""

    def test_discover_finds_tools(self):
        """Registry discovers tools from admin package."""
        registry = AdminToolRegistry()
        registry.discover()
        assert len(registry.tools) >= 10, f"Expected at least 10 tools, found {len(registry.tools)}"

    def test_get_tool_by_name(self):
        """Can retrieve a specific tool by name."""
        registry = AdminToolRegistry()
        registry.discover()
        tool = registry.get("search_mappings")
        assert tool is not None
        assert tool.name == "search_mappings"

    def test_get_all_specs(self):
        """get_all_specs returns valid function calling specs."""
        registry = AdminToolRegistry()
        registry.discover()
        specs = registry.get_all_specs()
        assert len(specs) >= 10
        for spec in specs:
            assert "function" in spec
            assert "name" in spec["function"]
            assert "parameters" in spec["function"]


# ── Mapping Tool Tests ────────────────────────────────────

class TestSearchMappings:

    async def test_search_mappings_found(self, mock_db_session):
        """Search for existing keyword returns matches."""
        from app.tools.admin.mapping_tools import SearchMappingsTool
        tool = SearchMappingsTool()
        result = await tool.execute({"keyword": "ดาต้าคอม"}, mock_db_session)
        assert result["success"] is True
        assert result["total"] >= 1
        assert any("ดาต้าคอม" in m["keyword"] for m in result["data"])

    async def test_search_mappings_not_found(self, mock_db_session):
        """Search for non-existing keyword returns empty."""
        from app.tools.admin.mapping_tools import SearchMappingsTool
        tool = SearchMappingsTool()
        result = await tool.execute({"keyword": "ไม่มีอยู่จริง"}, mock_db_session)
        assert result["success"] is True
        assert result["total"] == 0


class TestAddMapping:

    async def test_add_mapping_success(self, mock_db_session):
        """Add new mapping succeeds."""
        from app.tools.admin.mapping_tools import AddMappingTool
        tool = AddMappingTool()
        result = await tool.execute({
            "keyword": "อินเตอร์เน็ต",
            "target_column": "SERVICE_GROUP",
            "target_value": "Internet",
        }, mock_db_session)
        assert result["success"] is True
        assert "id" in result["data"]

    async def test_add_mapping_duplicate(self, mock_db_session):
        """Add duplicate mapping returns error."""
        from app.tools.admin.mapping_tools import AddMappingTool
        tool = AddMappingTool()
        result = await tool.execute({
            "keyword": "ดาต้าคอม",
            "target_column": "SERVICE_GROUP",
            "target_value": "Datacom",
        }, mock_db_session)
        assert result["success"] is False
        assert "มี" in result["message"] or "อยู่แล้ว" in result["message"] or "duplicate" in result["message"]


# ── Rule Tool Tests ───────────────────────────────────────

class TestSearchRules:

    async def test_search_rules_by_severity(self, mock_db_session):
        """Search rules filtered by severity returns correct rules."""
        from app.tools.admin.rule_tools import SearchRulesTool
        tool = SearchRulesTool()
        result = await tool.execute({"severity": "error"}, mock_db_session)
        assert result["success"] is True
        for rule in result["data"]:
            assert rule["severity"] == "error"


class TestAddRule:

    async def test_add_rule_success(self, mock_db_session):
        """Add new rule succeeds."""
        from app.tools.admin.rule_tools import AddRuleTool
        tool = AddRuleTool()
        result = await tool.execute({
            "rule_code": "TEST_001",
            "description": "กฎทดสอบ",
            "rule_category": "validation",
        }, mock_db_session)
        assert result["success"] is True

    async def test_add_rule_duplicate_code(self, mock_db_session):
        """Add rule with existing code returns error."""
        from app.tools.admin.rule_tools import AddRuleTool
        tool = AddRuleTool()
        result = await tool.execute({
            "rule_code": "FILTER_001",
            "description": "duplicate",
            "rule_category": "filter",
        }, mock_db_session)
        assert result["success"] is False


# ── Example Tool Tests ────────────────────────────────────

class TestSearchExamples:

    async def test_search_examples(self, mock_db_session):
        """Search examples returns results."""
        from app.tools.admin.example_tools import SearchExamplesTool
        tool = SearchExamplesTool()
        result = await tool.execute({"search_text": "รายได้"}, mock_db_session)
        assert result["success"] is True
        assert result["total"] >= 1


class TestAddExample:

    async def test_add_example(self, mock_db_session):
        """Add new example succeeds."""
        from app.tools.admin.example_tools import AddExampleTool
        tool = AddExampleTool()
        result = await tool.execute({
            "question": "ค่าใช้จ่ายรวมปี 68",
            "sql": "SELECT SUM(EXPENSE_VALUE) FROM expense WHERE YEAR=2025",
            "context_name": "expense",
        }, mock_db_session)
        assert result["success"] is True


# ── System Tool Tests ─────────────────────────────────────

class TestRefreshCache:

    async def test_refresh_cache(self, mock_db_session):
        """Refresh cache succeeds (even if some caches don't exist)."""
        from app.tools.admin.system_tools import RefreshCacheTool
        tool = RefreshCacheTool()
        result = await tool.execute({}, mock_db_session)
        assert result["success"] is True
        assert "refreshed" in result["data"]


class TestListContexts:

    async def test_list_contexts(self, mock_db_session, tmp_path):
        """List contexts returns available contexts (self-contained — no local config.db)."""
        import sqlite3
        from unittest.mock import patch
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        db_path = tmp_path / "config.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT, display_name TEXT, "
            "description TEXT, main_view TEXT, is_active INTEGER)"
        )
        conn.executemany(
            "INSERT INTO schema_contexts (name, display_name, description, main_view, is_active) VALUES (?, ?, ?, ?, 1)",
            [("revenue", "รายได้", "", "revenue_search"), ("expense", "ค่าใช้จ่าย", "", "v_expense_mart")],
        )
        conn.commit()
        conn.close()

        engine = create_engine(f"sqlite:///{db_path}")
        session_factory = sessionmaker(bind=engine)

        from app.tools.admin.system_tools import ListContextsTool
        tool = ListContextsTool()
        with patch("app.db.session.ConfigSessionLocal", session_factory):
            result = await tool.execute({}, mock_db_session)
        assert result["success"] is True
        assert result["total"] >= 2
        names = [c["name"] for c in result["data"]]
        assert "revenue" in names


class TestSearchHierarchy:
    """search_hierarchy used to call a method that doesn't exist — always an error."""

    @pytest.fixture
    def hierarchy_db(self, tmp_path):
        from pathlib import Path
        path = str(tmp_path / "config.sqlite")
        conn = sqlite3.connect(path)
        conn.executescript(
            (Path(__file__).resolve().parents[2] / "database/migrations/009_master_hierarchy.sql").read_text(encoding="utf-8"))
        conn.execute("DELETE FROM master_hierarchy_values")
        conn.execute("DELETE FROM master_hierarchy")
        for ctx in ("revenue", "secret"):
            conn.execute("INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, "
                         "level_columns, detection_keywords) VALUES (?, 0, 'กลุ่มบริการ', 'Service group', "
                         "'[\"SERVICE_GROUP\"]', '[]')", (ctx,))
            conn.execute("INSERT INTO master_hierarchy_values (context_name, level, value, aliases) "
                         "VALUES (?, 0, ?, '[\"datacom\"]')", (ctx, f"DATACOM-{ctx}"))
        conn.commit()
        conn.close()

        def policy(context_name, *args, **kwargs):
            return "full" if context_name == "revenue" else "schema_only"

        with patch("app.services.hierarchy_service._get_conn", side_effect=lambda: sqlite3.connect(path)), \
             patch("app.services.data_sources.policy_for_context", side_effect=policy):
            yield

    async def test_all_contexts_when_none_given_and_policy_kept(self, hierarchy_db):
        from app.tools.admin.system_tools import SearchHierarchyTool
        result = await SearchHierarchyTool().execute({"keyword": "Datacom"}, db=None)
        assert result["success"], result["message"]
        # the restricted context's values never reach the agent's LLM
        assert [(m["value"], m["column"], m["level"]) for m in result["data"]] == [
            ("DATACOM-revenue", "SERVICE_GROUP", "กลุ่มบริการ")]

    async def test_context_and_level_filters(self, hierarchy_db):
        from app.tools.admin.system_tools import SearchHierarchyTool
        tool = SearchHierarchyTool()
        assert (await tool.execute({"keyword": "datacom", "context_name": "secret"}, db=None))["data"] == []
        assert (await tool.execute({"keyword": "datacom", "context_name": "revenue", "level_name": "ฝ่าย"}, db=None))["data"] == []
        assert (await tool.execute({"keyword": "datacom", "context_name": "revenue"}, db=None))["total"] == 1


class TestToolsRunOnTheirOwnDatabase:
    """Two separate DB files, as in production: the Admin Agent holds an app-DB session,
    the config tools' tables are in the config DB, the audit table is in the app DB."""

    @pytest.fixture
    def config_db(self, admin_tools_db):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        with patch("app.db.session.ConfigSessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{admin_tools_db}"))):
            yield admin_tools_db

    async def test_agent_adds_on_config_db_and_audits_on_app_db(self, config_db, app_db):
        from app.db import session as db_session
        from app.services.admin_agent import AdminAgent
        from app.tools.admin.mapping_tools import AddMappingTool

        agent_db = db_session.SessionLocal()  # app DB: has no schema_semantic_mapping
        try:
            result = await AdminAgent(agent_db)._run_tool(AddMappingTool(), {
                "keyword": "บรอดแบนด์", "target_column": "SERVICE_GROUP", "target_value": "Broadband"})
        finally:
            agent_db.close()
        assert result["success"], result["message"]

        config = sqlite3.connect(config_db)
        assert config.execute("SELECT id FROM schema_semantic_mapping WHERE keyword = 'บรอดแบนด์'").fetchone() == (
            result["data"]["id"],)
        config.close()
        app = sqlite3.connect(app_db)
        assert app.execute("SELECT action, table_name, record_id, source FROM config_audit_log").fetchall() == [
            ("create", "schema_semantic_mapping", result["data"]["id"], "admin_agent")]
        app.close()

    def test_each_tool_declares_a_known_database(self, config_db, app_db):
        from app.tools.admin.base import tool_session
        registry = AdminToolRegistry()
        registry.discover()
        for tool in registry.tools.values():
            assert tool.database in ("config", "app"), tool.name
            with tool_session(tool) as db:
                expected = app_db if tool.category == "analysis" else config_db
                assert db.get_bind().url.database == expected, tool.name
