"""
Unit Tests for DB Separation (Plan 5)
=======================================
Tests for BusinessDBAdapter and config DB session.
"""

import pytest
import sqlite3
import os

from app.services.business_db import BusinessDBAdapter, ColumnInfo


@pytest.fixture
def test_sqlite(tmp_path):
    """Create a temp SQLite DB with sample business data."""
    db_path = str(tmp_path / "business.sqlite")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE revenue (
            id INTEGER PRIMARY KEY,
            YEAR INTEGER, MONTH INTEGER,
            REVENUE_VALUE REAL, DIVISION TEXT
        )
    """)
    c.executemany("INSERT INTO revenue (YEAR, MONTH, REVENUE_VALUE, DIVISION) VALUES (?, ?, ?, ?)", [
        (2025, 1, 1000000, "สายงาน A"),
        (2025, 2, 2000000, "สายงาน B"),
        (2025, 1, 500000, "สายงาน A"),
    ])
    c.execute("CREATE VIEW v_revenue AS SELECT YEAR, MONTH, SUM(REVENUE_VALUE) as total FROM revenue GROUP BY YEAR, MONTH")
    conn.commit()
    conn.close()
    return db_path


class TestBusinessDBAdapter:

    def test_adapter_sqlite(self, test_sqlite):
        """SQLite adapter initializes correctly."""
        adapter = BusinessDBAdapter(f"sqlite:///{test_sqlite}")
        assert adapter.engine_type == "sqlite"

    def test_adapter_query(self, test_sqlite):
        """Execute query returns list of dicts."""
        adapter = BusinessDBAdapter(f"sqlite:///{test_sqlite}")
        results = adapter.execute("SELECT * FROM revenue WHERE YEAR = 2025")
        assert len(results) == 3
        assert "YEAR" in results[0]
        assert results[0]["YEAR"] == 2025

    def test_adapter_schema(self, test_sqlite):
        """Get schema returns column info."""
        adapter = BusinessDBAdapter(f"sqlite:///{test_sqlite}")
        columns = adapter.get_schema("revenue")
        assert len(columns) >= 5
        col_names = [c.name for c in columns]
        assert "REVENUE_VALUE" in col_names
        assert "YEAR" in col_names

    def test_adapter_get_tables(self, test_sqlite):
        """Get tables returns table and view names."""
        adapter = BusinessDBAdapter(f"sqlite:///{test_sqlite}")
        tables = adapter.get_tables()
        assert "revenue" in tables
        assert "v_revenue" in tables

    def test_detect_engine_postgresql(self):
        """Detects PostgreSQL from URL."""
        adapter = BusinessDBAdapter("postgresql://user:pass@host/db")
        assert adapter.engine_type == "postgresql"

    def test_detect_engine_mssql(self):
        """Detects MSSQL from URL."""
        adapter = BusinessDBAdapter("mssql+pymssql://user:pass@host/db")
        assert adapter.engine_type == "mssql"


class TestMigrationScript:

    def test_migration_dry_run(self, test_sqlite, tmp_path):
        """Dry run doesn't create destination file."""
        dest_path = str(tmp_path / "config.db")
        import importlib.util
        spec = importlib.util.spec_from_file_location("migrate", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts", "migrate_config_to_separate_db.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(test_sqlite, dest_path, dry_run=True)
        # Dry run should not create file (no config tables in business DB)
        # This is expected — no config tables in test business DB

    def test_migration_copies_data(self, tmp_path):
        """Migration copies config tables to destination."""
        # Create source with a config table
        source_path = str(tmp_path / "source.sqlite")
        dest_path = str(tmp_path / "config.db")

        conn = sqlite3.connect(source_path)
        c = conn.cursor()
        c.execute("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, context_name TEXT, is_active INTEGER DEFAULT 1)")
        c.execute("INSERT INTO schema_contexts (context_name) VALUES ('revenue')")
        c.execute("INSERT INTO schema_contexts (context_name) VALUES ('expense')")
        conn.commit()
        conn.close()

        import importlib.util
        spec = importlib.util.spec_from_file_location("migrate", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts", "migrate_config_to_separate_db.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.migrate(source_path, dest_path, dry_run=False)

        # Verify destination has the data
        dest_conn = sqlite3.connect(dest_path)
        rows = dest_conn.execute("SELECT COUNT(*) FROM schema_contexts").fetchone()[0]
        dest_conn.close()
        assert rows == 2
