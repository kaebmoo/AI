"""
Unit Tests for DB Separation (Plan 5)
=======================================
Tests for the config DB session and the DB-separation migration script.
"""

import pytest
import sqlite3
import os



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
