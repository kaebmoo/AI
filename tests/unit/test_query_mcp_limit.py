"""
F4.1: business DB opened read-only at the connection level.
F4.2: row cap via fetchmany — no LIMIT string appending.
"""

import sqlite3

import pytest

from mcp_servers import nt_query_mcp
from mcp_servers.nt_query_mcp import DatabaseConfig, QueryDatabaseAdapter


@pytest.fixture
def business_db(tmp_path):
    """Temp SQLite file with 50 rows, wired in as the module's adapter."""
    db_path = tmp_path / "biz test.sqlite"  # space in name — exercises URI escaping
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE revenue (id INTEGER, val REAL)")
    conn.executemany("INSERT INTO revenue VALUES (?, ?)", [(i, i * 1.5) for i in range(50)])
    conn.commit()
    conn.close()

    adapter = QueryDatabaseAdapter(DatabaseConfig(engine="sqlite", connection_string=f"sqlite:///{db_path}"))
    old = nt_query_mcp._db_adapter
    nt_query_mcp._db_adapter = adapter
    yield adapter
    nt_query_mcp._db_adapter = old


class TestReadOnlyConnection:
    def test_write_blocked_at_connection_level(self, business_db):
        result = nt_query_mcp.execute_query("INSERT INTO revenue VALUES (99, 1)", validate_first=False)
        assert result["success"] is False
        assert "readonly" in result["error"].lower()

    def test_read_works(self, business_db):
        result = nt_query_mcp.execute_query("SELECT COUNT(*) AS cnt FROM revenue")
        assert result["success"] is True
        assert result["data"][0]["cnt"] == 50

    def test_missing_file_fails_loud(self):
        adapter = QueryDatabaseAdapter(
            DatabaseConfig(engine="sqlite", connection_string="sqlite:///does/not/exist.sqlite")
        )
        with pytest.raises(FileNotFoundError, match="Business DB not found"):
            adapter._get_connection()


class TestRowCap:
    def test_limit_caps_and_flags_truncated(self, business_db):
        result = nt_query_mcp.execute_query("SELECT * FROM revenue", limit=10)
        assert result["success"] is True
        assert result["row_count"] == 10
        assert result["truncated"] is True

    def test_under_limit_not_truncated(self, business_db):
        result = nt_query_mcp.execute_query("SELECT * FROM revenue WHERE id < 5", limit=10)
        assert result["row_count"] == 5
        assert result["truncated"] is False

    def test_inner_subquery_limit_still_capped(self, business_db):
        # Old substring check ('LIMIT' in sql) would skip capping here
        sql = "SELECT * FROM (SELECT * FROM revenue LIMIT 40) t"
        result = nt_query_mcp.execute_query(sql, limit=10)
        assert result["row_count"] == 10
        assert result["truncated"] is True

    def test_trailing_semicolon_ok(self, business_db):
        result = nt_query_mcp.execute_query("SELECT * FROM revenue;", limit=10)
        assert result["success"] is True
        assert result["row_count"] == 10


class TestValidateSqlDelegation:
    def test_validate_delegates_to_validation_service(self):
        result = nt_query_mcp.validate_sql("DROP TABLE revenue")
        assert result["valid"] is False
        result = nt_query_mcp.validate_sql("SELECT 1")
        assert result["valid"] is True
