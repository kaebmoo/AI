"""
Business Database Adapter
===========================
Abstraction layer for connecting to business databases.
Supports SQLite (dev), PostgreSQL, and MSSQL (prod).
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False


class BusinessDBAdapter:
    """Adapter for executing queries against business databases."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine_type = self._detect_engine(db_url)
        self._engine = None

    def _detect_engine(self, db_url: str) -> str:
        if "sqlite" in db_url:
            return "sqlite"
        elif "postgresql" in db_url or "postgres" in db_url:
            return "postgresql"
        elif "mssql" in db_url or "pymssql" in db_url:
            return "mssql"
        return "sqlite"

    @property
    def engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(self.db_url)
        return self._engine

    def execute(self, sql: str, params: Dict = None) -> List[Dict]:
        """Execute a SELECT query and return results as list of dicts."""
        from sqlalchemy import text

        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

    def get_schema(self, table_name: str) -> List[ColumnInfo]:
        """Get column info for a table/view."""
        if self.engine_type == "sqlite":
            return self._get_schema_sqlite(table_name)
        elif self.engine_type == "postgresql":
            return self._get_schema_postgresql(table_name)
        elif self.engine_type == "mssql":
            return self._get_schema_mssql(table_name)
        return []

    def get_tables(self) -> List[str]:
        """Get all table and view names."""
        if self.engine_type == "sqlite":
            rows = self.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name")
        elif self.engine_type == "postgresql":
            rows = self.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
        elif self.engine_type == "mssql":
            rows = self.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_NAME")
        else:
            rows = []

        return [list(r.values())[0] for r in rows]

    def _get_schema_sqlite(self, table_name: str) -> List[ColumnInfo]:
        rows = self.execute(f"PRAGMA table_info('{table_name}')")
        return [
            ColumnInfo(
                name=r["name"],
                data_type=r.get("type", "TEXT"),
                nullable=not r.get("notnull", False),
                primary_key=bool(r.get("pk", 0)),
            )
            for r in rows
        ]

    def _get_schema_postgresql(self, table_name: str) -> List[ColumnInfo]:
        rows = self.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = :tbl AND table_schema = 'public'
            ORDER BY ordinal_position
        """, {"tbl": table_name})
        return [
            ColumnInfo(
                name=r["column_name"],
                data_type=r["data_type"],
                nullable=r["is_nullable"] == "YES",
            )
            for r in rows
        ]

    def _get_schema_mssql(self, table_name: str) -> List[ColumnInfo]:
        rows = self.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = :tbl
            ORDER BY ORDINAL_POSITION
        """, {"tbl": table_name})
        return [
            ColumnInfo(
                name=r["COLUMN_NAME"],
                data_type=r["DATA_TYPE"],
                nullable=r["IS_NULLABLE"] == "YES",
            )
            for r in rows
        ]
