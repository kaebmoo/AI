"""
Tests for Vanna Documentation — DB-driven knowledge docs + brain sync.
Covers: sync/vanna (6), CRUD API (5), brain sync status (3), RAG quality (2) = 16 tests.
"""

import sqlite3
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient


# ─── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def in_memory_config_db():
    """Create in-memory SQLite DB with vanna_documentation and admin_config tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE vanna_documentation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'guide',
            context_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE admin_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_key TEXT NOT NULL UNIQUE,
            config_value TEXT,
            config_type TEXT NOT NULL DEFAULT 'general',
            category TEXT DEFAULT 'ai',
            display_name TEXT,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            is_sensitive INTEGER DEFAULT 0,
            validation_regex TEXT,
            default_value TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            metadata TEXT
        )
    """)
    conn.execute("""
        INSERT INTO admin_config (config_key, config_value, config_type, category)
        VALUES ('last_brain_sync_at', NULL, 'system', 'system')
    """)
    conn.execute("""
        INSERT INTO admin_config (config_key, config_value, config_type, category)
        VALUES ('last_brain_relevant_change_at', NULL, 'system', 'system')
    """)
    conn.execute("""
        CREATE TABLE schema_business_rules (
            id INTEGER PRIMARY KEY, rule_code TEXT, rule_name TEXT,
            rule_description TEXT, table_name TEXT, applies_to TEXT,
            example_correct TEXT, example_wrong TEXT, severity TEXT, is_active INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE schema_semantic_mapping (
            id INTEGER PRIMARY KEY, keyword TEXT, keyword_type TEXT,
            target_column TEXT, target_condition TEXT, full_condition TEXT,
            description TEXT, priority INTEGER, is_active INTEGER, context_name TEXT
        )
    """)
    conn.commit()
    yield conn
    conn.close()


# ─── Sync / Vanna Unit Tests ────────────────────────────────────

class TestSyncDocumentation:
    """Tests 1-6: Vanna sync behavior."""

    def test_sync_documentation_has_no_file_dependency(self):
        """Test 1: _sync_documentation does NOT read any files."""
        # Mock VannaService to avoid chromadb dependency
        from unittest.mock import MagicMock

        mock_service = MagicMock()
        mock_service.engine.connect.return_value.__enter__ = MagicMock(
            return_value=MagicMock(execute=MagicMock(return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))))
        )
        mock_service.engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_service.get_all_contexts.return_value = []

        with patch('builtins.open', side_effect=AssertionError("open() should not be called")):
            # We can't instantiate VannaService without chromadb, so test the logic pattern
            # Verify the code path doesn't reference open() or os.path.exists()
            import inspect
            from app.services.vanna_service import VannaService
            source = inspect.getsource(VannaService._sync_documentation)
            assert 'open(' not in source, "_sync_documentation should not call open()"
            assert 'os.path.exists' not in source, "_sync_documentation should not call os.path.exists()"
            assert 'guide_path' not in source, "_sync_documentation should not reference guide_path"

            # Also verify _sync_context_summaries doesn't USE instruction_th
            # (comments mentioning it are OK, but get/access patterns are not)
            ctx_source = inspect.getsource(VannaService._sync_context_summaries)
            assert "get('instruction_th')" not in ctx_source, (
                "_sync_context_summaries must not access instruction_th — "
                "it contains rule-like content already trained via business_rules"
            )
            assert "['instruction_th']" not in ctx_source, (
                "_sync_context_summaries must not access instruction_th"
            )

    def test_sync_context_summaries_generates_per_context(self):
        """Test 2: _sync_context_summaries generates one summary per context."""
        mock_self = MagicMock()
        mock_self.train = MagicMock()

        mock_service = MagicMock()
        mock_service.get_all_contexts.return_value = [
            {'name': 'revenue', 'display_name': 'Revenue', 'main_view': 'revenue_search',
             'description': 'Revenue data', 'instruction_th': ''},
            {'name': 'expense', 'display_name': 'Expense', 'main_view': 'v_expense_mart',
             'description': 'Expense data', 'instruction_th': ''},
        ]
        mock_service.get_schema_metadata.return_value = [
            {'column_name': 'REVENUE_VALUE', 'is_summable': True, 'is_groupable': False},
            {'column_name': 'YEAR', 'is_summable': False, 'is_groupable': True},
        ]

        with patch('app.services.vanna_service.VannaService._sync_context_summaries.__module__', 'app.services.vanna_service'):
            from app.services.vanna_service import VannaService
            VannaService._sync_context_summaries(mock_self, mock_service)

        assert mock_self.train.call_count == 2
        for call in mock_self.train.call_args_list:
            assert 'documentation' in call.kwargs

    def test_sync_context_summaries_handles_empty_contexts(self):
        """Test 3: Empty contexts list → no crash, no train calls."""
        mock_self = MagicMock()
        mock_self.train = MagicMock()

        mock_service = MagicMock()
        mock_service.get_all_contexts.return_value = []

        from app.services.vanna_service import VannaService
        VannaService._sync_context_summaries(mock_self, mock_service)

        mock_self.train.assert_not_called()

    def test_sync_context_summaries_handles_missing_hierarchy(self):
        """Test 4: Missing hierarchy_service → still trains structural info."""
        mock_self = MagicMock()
        mock_self.train = MagicMock()

        mock_service = MagicMock()
        mock_service.get_all_contexts.return_value = [
            {'name': 'revenue', 'display_name': 'Revenue', 'main_view': 'rev',
             'description': 'Test', 'instruction_th': ''},
        ]
        mock_service.get_schema_metadata.return_value = []

        with patch.dict('sys.modules', {'app.services.hierarchy_service': None}):
            from app.services.vanna_service import VannaService
            VannaService._sync_context_summaries(mock_self, mock_service)

        assert mock_self.train.call_count == 1

    def test_sync_documentation_reads_vanna_documentation_table(self, in_memory_config_db):
        """Test 5: Manual docs from vanna_documentation table get trained."""
        conn = in_memory_config_db
        conn.execute(
            "INSERT INTO vanna_documentation (doc_key, title, content) VALUES (?, ?, ?)",
            ('test_doc', 'Test Title', 'Test content for Vanna'),
        )
        conn.commit()

        # Create a mock engine that returns our in-memory connection
        from sqlalchemy import create_engine, text
        engine = create_engine("sqlite:///:memory:")

        # Copy table structure + data into SQLAlchemy engine
        with engine.connect() as sa_conn:
            sa_conn.execute(text("""
                CREATE TABLE vanna_documentation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_key TEXT, title TEXT, content TEXT,
                    category TEXT DEFAULT 'guide', context_name TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME, updated_at DATETIME, status TEXT NOT NULL DEFAULT 'active'
                )
            """))
            sa_conn.execute(text("""
                CREATE TABLE schema_business_rules (
                    id INTEGER PRIMARY KEY, rule_code TEXT, rule_name TEXT,
                    rule_description TEXT, table_name TEXT, applies_to TEXT,
                    example_correct TEXT, example_wrong TEXT, severity TEXT, is_active INTEGER,
                    status TEXT NOT NULL DEFAULT 'active'
                )
            """))
            sa_conn.execute(text("""
                CREATE TABLE schema_semantic_mapping (
                    id INTEGER PRIMARY KEY, keyword TEXT, keyword_type TEXT,
                    target_column TEXT, target_condition TEXT, full_condition TEXT,
                    description TEXT, priority INTEGER, is_active INTEGER, context_name TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                )
            """))
            sa_conn.execute(text(
                "INSERT INTO vanna_documentation (doc_key, title, content, is_active) VALUES (:k, :t, :c, 1)"
            ), {"k": "test_doc", "t": "Test Title", "c": "Test content for Vanna"})
            sa_conn.commit()

        mock_self = MagicMock()
        mock_self.train = MagicMock()

        mock_service = MagicMock()
        mock_service.engine = engine
        mock_service.get_all_contexts.return_value = []

        from app.services.vanna_service import VannaService
        VannaService._sync_documentation(mock_self, mock_service)

        # Should have called train with the doc content
        doc_calls = [
            c for c in mock_self.train.call_args_list
            if 'documentation' in c.kwargs and 'Test content for Vanna' in c.kwargs['documentation']
        ]
        assert len(doc_calls) == 1

    def test_migration_creates_table(self):
        """Test 6: Migration SQL creates table and allows insert/query."""
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'database', 'migrations', '031_vanna_documentation.sql'
        )

        conn = sqlite3.connect(":memory:")
        # Create admin_config first (needed for INSERT OR IGNORE)
        conn.execute("""
            CREATE TABLE admin_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT UNIQUE, config_value TEXT,
                config_type TEXT, category TEXT, display_name TEXT,
                description TEXT, is_active INTEGER, is_sensitive INTEGER,
                validation_regex TEXT, default_value TEXT,
                created_at TEXT, updated_at TEXT, updated_by TEXT, metadata TEXT
            )
        """)

        with open(migration_path, 'r') as f:
            sql = f.read()

        conn.executescript(sql)

        # Verify table exists
        cursor = conn.execute("SELECT count(*) FROM vanna_documentation")
        assert cursor.fetchone()[0] >= 5  # 5 seed docs

        # Verify sync tracking keys
        cursor = conn.execute(
            "SELECT config_key FROM admin_config WHERE config_type='system' ORDER BY config_key"
        )
        keys = [row[0] for row in cursor.fetchall()]
        assert 'last_brain_relevant_change_at' in keys
        assert 'last_brain_sync_at' in keys

        conn.close()


# ─── CRUD API Tests ──────────────────────────────────────────────

class TestVannaDocsCRUD:
    """Tests 7-11: CRUD API endpoints."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Set up test client with mocked dependencies."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db.base_class import ConfigBase
        # Import model to register with ConfigBase.metadata
        from app.models.schema_models import VannaDocumentation  # noqa: F401

        # Create in-memory config DB with ORM metadata
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        ConfigBase.metadata.create_all(bind=engine)

        Session = sessionmaker(bind=engine)

        def get_config_db_override():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        mock_user = MagicMock()
        mock_user.role = 'admin'

        from app.main import app
        from app.api import deps

        app.dependency_overrides[deps.get_config_db] = get_config_db_override
        app.dependency_overrides[deps.require_admin] = lambda: mock_user

        self.client = TestClient(app)
        yield
        app.dependency_overrides.clear()

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_list_vanna_docs(self, mock_dirty):
        """Test 7: GET /vanna-docs returns list."""
        # Create 2 docs first
        self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "doc1", "title": "Doc 1", "content": "Content 1"
        })
        self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "doc2", "title": "Doc 2", "content": "Content 2"
        })

        resp = self.client.get("/api/v1/admin/vanna-docs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["docs"]) == 2

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_create_vanna_doc(self, mock_dirty):
        """Test 8: POST /vanna-docs creates doc."""
        resp = self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "new_doc", "title": "New Doc", "content": "New content",
            "category": "workflow"
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["doc_key"] == "new_doc"
        assert body["category"] == "workflow"
        assert body["is_active"] is True
        mock_dirty.assert_called()

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_create_duplicate_doc_key_fails(self, mock_dirty):
        """Test 9: Duplicate doc_key returns 400."""
        self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "dup", "title": "First", "content": "Content"
        })
        resp = self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "dup", "title": "Second", "content": "Content 2"
        })
        assert resp.status_code == 400

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_update_vanna_doc(self, mock_dirty):
        """Test 10: PUT /vanna-docs/{id} updates fields."""
        create_resp = self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "upd", "title": "Original", "content": "Original content"
        })
        doc_id = create_resp.json()["id"]

        resp = self.client.put(f"/api/v1/admin/vanna-docs/{doc_id}", json={
            "title": "Updated Title", "is_active": False
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Updated Title"
        assert body["is_active"] is False
        assert body["content"] == "Original content"  # unchanged

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_delete_vanna_doc(self, mock_dirty):
        """Test 11: DELETE /vanna-docs/{id} removes doc."""
        create_resp = self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "del_me", "title": "Delete Me", "content": "Content"
        })
        doc_id = create_resp.json()["id"]

        resp = self.client.delete(f"/api/v1/admin/vanna-docs/{doc_id}")
        assert resp.status_code == 204

        get_resp = self.client.get(f"/api/v1/admin/vanna-docs/{doc_id}")
        assert get_resp.status_code == 404


class TestVannaDocsPreMigrationHandling:
    """Regression tests for instances where migration 031 has not been applied yet."""

    @pytest.fixture(autouse=True)
    def setup_client_without_vanna_table(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE admin_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_key TEXT NOT NULL UNIQUE,
                    config_value TEXT,
                    config_type TEXT NOT NULL DEFAULT 'general',
                    category TEXT DEFAULT 'ai',
                    display_name TEXT,
                    description TEXT,
                    is_active INTEGER DEFAULT 1,
                    is_sensitive INTEGER DEFAULT 0,
                    validation_regex TEXT,
                    default_value TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT,
                    metadata TEXT
                )
            """))

        Session = sessionmaker(bind=engine)

        def get_config_db_override():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        mock_user = MagicMock()
        mock_user.role = 'admin'

        from app.main import app
        from app.api import deps

        app.dependency_overrides[deps.get_config_db] = get_config_db_override
        app.dependency_overrides[deps.require_admin] = lambda: mock_user

        self.client = TestClient(app)
        yield
        app.dependency_overrides.clear()

    def test_list_vanna_docs_returns_503_when_table_missing(self):
        resp = self.client.get("/api/v1/admin/vanna-docs")
        assert resp.status_code == 503
        assert "031_vanna_documentation.sql" in resp.json()["detail"]


# ─── Brain Sync Status Tests ────────────────────────────────────

class TestBrainSyncStatus:
    """Tests 12-14: Brain sync tracking."""

    def test_sync_brain_records_timestamp(self):
        """Test 12: POST /sync-brain sets last_brain_sync_at."""
        import inspect
        from app.api.v1.admin.analytics import sync_brain_knowledge

        # Verify the source code contains the sync timestamp logic
        source = inspect.getsource(sync_brain_knowledge)
        assert 'last_brain_sync_at' in source
        assert "config_type='system'" in source
        assert "category='system'" in source
        assert '.close()' in source  # session properly closed

    def test_crud_vanna_doc_marks_brain_dirty(self):
        """Test 13: mark_brain_dirty calls set_config with correct params and closes session."""
        with patch('app.services.admin_config_service.AdminConfigService') as MockConfig:
            mock_svc = MagicMock()
            MockConfig.return_value = mock_svc

            # Re-import to pick up the patched AdminConfigService
            import importlib
            import app.api.v1.admin._shared as shared_mod
            importlib.reload(shared_mod)
            shared_mod.mark_brain_dirty()

            mock_svc.set_config.assert_called_once()
            call_args = mock_svc.set_config.call_args
            assert call_args[0][0] == 'last_brain_relevant_change_at'
            assert call_args[1]['config_type'] == 'system'
            assert call_args[1]['category'] == 'system'
            mock_svc.close.assert_called_once()

    def test_brain_sync_status_needs_sync(self):
        """Test 14: GET /brain-sync-status correctly reports needs_sync."""
        mock_user = MagicMock()

        # Case 1: change > sync → needs_sync=True
        with patch('app.services.admin_config_service.AdminConfigService') as MockConfig:
            mock_svc = MagicMock()
            MockConfig.return_value = mock_svc
            mock_svc.get_config.side_effect = lambda key: {
                'last_brain_sync_at': '2026-03-20T10:00:00',
                'last_brain_relevant_change_at': '2026-03-21T15:00:00',
            }[key]

            # Reload to pick up patched import
            import importlib
            import app.api.v1.admin.vanna_docs as vd_mod
            importlib.reload(vd_mod)
            result = vd_mod.get_brain_sync_status(_current_user=mock_user)
            assert result['needs_sync'] is True
            mock_svc.close.assert_called()

        # Case 2: sync > change → needs_sync=False
        with patch('app.services.admin_config_service.AdminConfigService') as MockConfig:
            mock_svc = MagicMock()
            MockConfig.return_value = mock_svc
            mock_svc.get_config.side_effect = lambda key: {
                'last_brain_sync_at': '2026-03-22T10:00:00',
                'last_brain_relevant_change_at': '2026-03-21T15:00:00',
            }[key]

            importlib.reload(vd_mod)
            result = vd_mod.get_brain_sync_status(_current_user=mock_user)
            assert result['needs_sync'] is False

        # Case 3: both NULL → needs_sync=False
        with patch('app.services.admin_config_service.AdminConfigService') as MockConfig:
            mock_svc = MagicMock()
            MockConfig.return_value = mock_svc
            mock_svc.get_config.return_value = None

            importlib.reload(vd_mod)
            result = vd_mod.get_brain_sync_status(_current_user=mock_user)
            assert result['needs_sync'] is False


# ─── RAG Quality Tests ───────────────────────────────────────────

class TestRAGQuality:
    """Tests 15-16: RAG quality acceptance criteria."""

    def test_no_duplicate_content_in_corpus(self):
        """Test 15: Seed docs do not duplicate business rule text."""
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'database', 'migrations', '031_vanna_documentation.sql'
        )
        rules_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'database', 'migrations', '003_schema_metadata.sql'
        )

        with open(migration_path, 'r') as f:
            vanna_sql = f.read()

        # Extract seed doc content (between INSERT INTO vanna_documentation and the closing ;)
        # Simple check: known rule codes from migration 003 should NOT appear verbatim in seed docs
        known_rule_codes = ['SQLITE_CONCAT', 'SQLITE_NO_LPAD', 'UNION_NO_PARENS']
        for code in known_rule_codes:
            assert code not in vanna_sql, f"Seed data should not duplicate business rule '{code}'"

    def test_context_summary_is_structural_only(self):
        """Test 16: Context summaries contain structural info, not rule details.
        Uses non-empty instruction_th with rule-like content to catch leakage.
        """
        mock_self = MagicMock()
        trained_docs = []
        mock_self.train = lambda documentation: trained_docs.append(documentation)

        # Use realistic instruction_th with rule-like content (like production data)
        rule_like_instruction = (
            "หน่วยรายได้เป็นบาท ไม่ใช่ล้านบาท "
            "ต้องหารด้วย 1000000 เมื่อแสดงเป็นล้าน "
            "chart ต้องแสดง waterfall เมื่อเปรียบเทียบ"
        )

        mock_service = MagicMock()
        mock_service.get_all_contexts.return_value = [
            {'name': 'revenue', 'display_name': 'Revenue', 'main_view': 'revenue_search',
             'description': 'Revenue data', 'instruction_th': rule_like_instruction},
        ]
        mock_service.get_schema_metadata.return_value = [
            {'column_name': 'REVENUE_VALUE', 'is_summable': True, 'is_groupable': False},
            {'column_name': 'YEAR', 'is_summable': False, 'is_groupable': True},
        ]

        from app.services.vanna_service import VannaService
        VannaService._sync_context_summaries(mock_self, mock_service)

        assert len(trained_docs) == 1
        summary = trained_docs[0]

        # Structural info present
        assert 'REVENUE_VALUE' in summary
        assert 'YEAR' in summary
        assert 'SUM' in summary or 'Summable' in summary
        assert 'GROUP BY' in summary or 'Groupable' in summary

        # Rule/instruction content must NOT leak into structural summary
        assert 'CONCAT' not in summary
        assert 'LPAD' not in summary
        assert 'UNION' not in summary
        assert 'หน่วยรายได้' not in summary, "instruction_th content leaked into context summary"
        assert 'waterfall' not in summary, "instruction_th content leaked into context summary"
        assert '1000000' not in summary, "instruction_th content leaked into context summary"
        assert 'Special instructions' not in summary, "instruction_th section should not exist"


# ─── Route-level mark_brain_dirty Integration Tests ──────────────

class TestMarkBrainDirtyRouteIntegration:
    """Verify mark_brain_dirty() is actually called when hitting admin mutation routes.

    These tests use the real TestClient + dependency overrides to exercise the full
    request path, patching mark_brain_dirty at the module level where each route
    file imports it. This catches regressions where a route removes or forgets the call.
    """

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Set up test client with in-memory config DB."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db.base_class import ConfigBase
        from app.models.schema_models import VannaDocumentation  # noqa: F401

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        ConfigBase.metadata.create_all(bind=engine)

        Session = sessionmaker(bind=engine)

        def get_config_db_override():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        mock_user = MagicMock()
        mock_user.role = 'admin'
        mock_user.id = 1

        from app.main import app
        from app.api import deps

        app.dependency_overrides[deps.get_config_db] = get_config_db_override
        app.dependency_overrides[deps.require_admin] = lambda: mock_user

        self.client = TestClient(app)
        yield
        app.dependency_overrides.clear()

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_vanna_docs_create_calls_dirty(self, mock_dirty):
        """Verify POST /vanna-docs calls mark_brain_dirty."""
        resp = self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "route_test", "title": "Test", "content": "Content"
        })
        assert resp.status_code == 201
        mock_dirty.assert_called()

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_vanna_docs_update_calls_dirty(self, mock_dirty):
        """Verify PUT /vanna-docs/{id} calls mark_brain_dirty."""
        create_resp = self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "upd_test", "title": "T", "content": "C"
        })
        doc_id = create_resp.json()["id"]
        mock_dirty.reset_mock()

        resp = self.client.put(f"/api/v1/admin/vanna-docs/{doc_id}", json={"title": "Updated"})
        assert resp.status_code == 200
        mock_dirty.assert_called()

    @patch('app.api.v1.admin.vanna_docs.mark_brain_dirty')
    def test_vanna_docs_delete_calls_dirty(self, mock_dirty):
        """Verify DELETE /vanna-docs/{id} calls mark_brain_dirty."""
        create_resp = self.client.post("/api/v1/admin/vanna-docs", json={
            "doc_key": "del_test", "title": "T", "content": "C"
        })
        doc_id = create_resp.json()["id"]
        mock_dirty.reset_mock()

        resp = self.client.delete(f"/api/v1/admin/vanna-docs/{doc_id}")
        assert resp.status_code == 204
        mock_dirty.assert_called()

    @patch('app.api.v1.admin.rules.mark_brain_dirty')
    def test_rules_create_calls_dirty(self, mock_dirty):
        """Verify POST /rules calls mark_brain_dirty."""
        resp = self.client.post("/api/v1/admin/rules", json={
            "rule_code": "TEST_RULE_DIRTY",
            "rule_name": "Test Rule",
            "rule_description": "For testing",
            "severity": "info",
        })
        assert resp.status_code == 201
        mock_dirty.assert_called()

    @patch('app.api.v1.admin.mappings.mark_brain_dirty')
    def test_mappings_create_calls_dirty(self, mock_dirty):
        """Verify POST /mappings calls mark_brain_dirty."""
        resp = self.client.post("/api/v1/admin/mappings", json={
            "keyword": "test_dirty_kw",
            "target_column": "DIVISION",
            "target_condition": "= 'test'",
        })
        assert resp.status_code == 201
        mock_dirty.assert_called()

    def test_all_brain_relevant_routes_call_mark_brain_dirty(self):
        """Verify all brain-relevant route files import and call mark_brain_dirty.

        This is a source-code-level check that catches regressions where a route
        file removes the import or the call. It complements the route-level tests
        for endpoints that are easy to hit (vanna_docs, rules, mappings) by also
        covering endpoints with complex dependencies (golden_examples, contexts,
        schema, hierarchy, onboarding) that are hard to integration-test in isolation.
        """
        import importlib
        import inspect

        route_modules = [
            'app.api.v1.admin.vanna_docs',
            'app.api.v1.admin.contexts',
            'app.api.v1.admin.mappings',
            'app.api.v1.admin.rules',
            'app.api.v1.admin.golden_examples',
            'app.api.v1.admin.schema',
            'app.api.v1.admin.hierarchy',
            'app.api.v1.admin.onboarding',
        ]

        for module_path in route_modules:
            mod = importlib.import_module(module_path)
            source = inspect.getsource(mod)

            # Must import mark_brain_dirty
            assert 'mark_brain_dirty' in source, (
                f"{module_path} does not reference mark_brain_dirty"
            )

            # Must have at least one call (not just an import)
            # Count occurrences: import line + at least one call = minimum 2
            count = source.count('mark_brain_dirty')
            assert count >= 2, (
                f"{module_path} imports mark_brain_dirty but never calls it "
                f"(found {count} references, need >= 2)"
            )


def test_sync_ddl_trains_context_main_views_from_the_business_db(tmp_path):
    """REMAIN-9.4: DDL comes from the business DB (config DB never had it); raw tables stay out."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from sqlalchemy import create_engine, text
    from app.services.vanna_service import VannaService

    config = create_engine(f"sqlite:///{tmp_path / 'config.db'}")
    business = create_engine(f"sqlite:///{tmp_path / 'biz.db'}")
    with config.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (name TEXT, main_view TEXT, is_active INTEGER)"))
        conn.execute(text("INSERT INTO schema_contexts VALUES ('revenue', 'revenue_search', 1), ('old', 'v_old', 0)"))
    with business.begin() as conn:
        conn.execute(text("CREATE TABLE revenue (YEAR INT, V REAL)"))
        conn.execute(text("CREATE VIEW revenue_search AS SELECT YEAR AS year, V AS revenue FROM revenue"))
        conn.execute(text("CREATE VIEW v_old AS SELECT * FROM revenue"))

    vanna = VannaService.__new__(VannaService)
    vanna.train = MagicMock()
    vanna._sync_ddl(SimpleNamespace(engine=config, business_engine=business))
    trained = [c.kwargs["ddl"] for c in vanna.train.call_args_list]
    assert len(trained) == 1 and "CREATE VIEW revenue_search" in trained[0]
