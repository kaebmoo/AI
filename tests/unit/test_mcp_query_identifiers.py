import sqlite3

import pytest

from mcp_servers.nt_query_mcp import DatabaseConfig, QueryDatabaseAdapter, safe_column, safe_table


def _adapter(tmp_path):
    db_path = tmp_path / "mcp_query.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute('CREATE TABLE revenue_search ("กลุ่มธุรกิจ" TEXT, YEAR INTEGER)')
    conn.commit()
    conn.close()
    return QueryDatabaseAdapter(DatabaseConfig("sqlite", f"sqlite:///{db_path}"))


def test_safe_table_and_column_allow_real_identifiers(tmp_path):
    db = _adapter(tmp_path)

    assert safe_table(db, "revenue_search") == '"revenue_search"'
    assert safe_column(db, "revenue_search", "กลุ่มธุรกิจ") == '"กลุ่มธุรกิจ"'


def test_safe_table_and_column_reject_injection(tmp_path):
    db = _adapter(tmp_path)

    with pytest.raises(ValueError):
        safe_table(db, 'revenue_search"; DROP TABLE revenue_search;--')
    with pytest.raises(ValueError):
        safe_column(db, "revenue_search", 'YEAR" FROM revenue_search; DROP TABLE revenue_search;--')
