"""
Plan 5: Migration Script Integration Tests
============================================
Tests the config table migration from business DB to separate config.db.
"""

import importlib
import os
import sys
import sqlite3
import pytest
from pathlib import Path

# Import migration script directly (scripts/ is not a package)
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_script_path = os.path.join(_project_root, "scripts", "migrate_config_to_separate_db.py")
spec = importlib.util.spec_from_file_location("migrate_config_to_separate_db", _script_path)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
migrate = _mod.migrate
get_table_schema = _mod.get_table_schema
copy_table_data = _mod.copy_table_data
CONFIG_TABLES = _mod.CONFIG_TABLES


@pytest.fixture
def source_db(tmp_path):
    """Create a source SQLite DB with sample config tables."""
    db_path = str(tmp_path / "source.sqlite")
    conn = sqlite3.connect(db_path)

    # Create a few config tables
    conn.execute("""
        CREATE TABLE schema_contexts (
            id INTEGER PRIMARY KEY,
            context_name TEXT NOT NULL,
            display_name_th TEXT,
            description TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        INSERT INTO schema_contexts (context_name, display_name_th, is_active)
        VALUES ('revenue', 'รายได้', 1), ('expense', 'ค่าใช้จ่าย', 1)
    """)

    conn.execute("""
        CREATE TABLE schema_metadata (
            id INTEGER PRIMARY KEY,
            column_name TEXT NOT NULL,
            data_type TEXT,
            description TEXT
        )
    """)
    conn.execute("""
        INSERT INTO schema_metadata (column_name, data_type)
        VALUES ('REVENUE_VALUE', 'REAL'), ('YEAR', 'INTEGER')
    """)

    conn.execute("""
        CREATE TABLE admin_config (
            id INTEGER PRIMARY KEY,
            config_key TEXT NOT NULL,
            config_value TEXT
        )
    """)
    conn.execute("""
        INSERT INTO admin_config (config_key, config_value)
        VALUES ('default_ai_provider', 'matcha')
    """)

    # Create a business table that should NOT be migrated
    conn.execute("""
        CREATE TABLE revenue (
            id INTEGER PRIMARY KEY,
            YEAR INTEGER,
            REVENUE_VALUE REAL
        )
    """)
    conn.execute("INSERT INTO revenue VALUES (1, 2025, 150000)")

    conn.commit()
    conn.close()
    return db_path


class TestMigrationCopiesData:
    """Migration copies all config rows correctly."""

    def test_copies_all_data(self, source_db, tmp_path):
        """Config table rows in source == destination after migration."""
        dest_path = str(tmp_path / "config.db")

        migrate(source_db, dest_path, dry_run=False, drop_source=False)

        dest = sqlite3.connect(dest_path)

        # Check schema_contexts
        rows = dest.execute("SELECT COUNT(*) FROM schema_contexts").fetchone()[0]
        assert rows == 2

        # Check schema_metadata
        rows = dest.execute("SELECT COUNT(*) FROM schema_metadata").fetchone()[0]
        assert rows == 2

        # Check admin_config
        rows = dest.execute("SELECT COUNT(*) FROM admin_config").fetchone()[0]
        assert rows == 1

        dest.close()

    def test_config_tables_created(self, source_db, tmp_path):
        """All existing config tables are created in dest."""
        dest_path = str(tmp_path / "config.db")

        migrate(source_db, dest_path, dry_run=False, drop_source=False)

        dest = sqlite3.connect(dest_path)
        tables = [
            r[0] for r in dest.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        dest.close()

        assert "schema_contexts" in tables
        assert "schema_metadata" in tables
        assert "admin_config" in tables
        # Business tables should NOT be copied
        assert "revenue" not in tables


class TestMigrationDropSource:
    """Migration with --drop-source removes tables from source."""

    def test_source_tables_dropped(self, source_db, tmp_path):
        """After migration with drop_source, config tables gone from source."""
        dest_path = str(tmp_path / "config_drop.db")

        migrate(source_db, dest_path, dry_run=False, drop_source=True)

        source = sqlite3.connect(source_db)
        tables = [
            r[0] for r in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        source.close()

        assert "schema_contexts" not in tables
        assert "schema_metadata" not in tables
        # Business table should remain
        assert "revenue" in tables


class TestMigrationDryRun:
    """Dry run doesn't modify anything."""

    def test_dry_run_no_dest_created(self, source_db, tmp_path):
        """Dry run → destination file not created."""
        dest_path = str(tmp_path / "config_dry.db")

        migrate(source_db, dest_path, dry_run=True, drop_source=False)

        # Dest should not exist (dry run)
        assert not os.path.exists(dest_path)

    def test_dry_run_source_unchanged(self, source_db, tmp_path):
        """Dry run → source DB unchanged."""
        source = sqlite3.connect(source_db)
        before_count = source.execute("SELECT COUNT(*) FROM schema_contexts").fetchone()[0]
        source.close()

        dest_path = str(tmp_path / "config_dry2.db")
        migrate(source_db, dest_path, dry_run=True, drop_source=True)

        source = sqlite3.connect(source_db)
        after_count = source.execute("SELECT COUNT(*) FROM schema_contexts").fetchone()[0]
        source.close()

        assert before_count == after_count


class TestGetTableSchema:
    """get_table_schema() helper."""

    def test_returns_create_statement(self, source_db):
        """Returns CREATE TABLE SQL for existing table."""
        conn = sqlite3.connect(source_db)
        sql = get_table_schema(conn, "schema_contexts")
        conn.close()
        assert sql is not None
        assert "CREATE TABLE" in sql

    def test_returns_none_for_missing(self, source_db):
        """Returns None for non-existent table."""
        conn = sqlite3.connect(source_db)
        sql = get_table_schema(conn, "nonexistent_table")
        conn.close()
        assert sql is None
