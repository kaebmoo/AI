"""
NT Revenue Assistant - Database Adapter
========================================
Abstraction layer for database operations to support multiple database engines.

Supported Engines:
- SQLite (default)
- PostgreSQL
- MSSQL (SQL Server)

Usage:
    adapter = create_adapter(db_url="sqlite:///./revenue.db")
    result = adapter.execute_query("SELECT * FROM revenue_search LIMIT 10")
"""

import sqlite3
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters"""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return the database engine name"""
        pass

    @abstractmethod
    def execute_query(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        """
        Execute a SELECT query and return results as list of dicts.

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            List of dictionaries representing rows
        """
        pass

    @abstractmethod
    def get_schema_info(self, table_name: str) -> List[Dict]:
        """
        Get column information for a table.

        Args:
            table_name: Name of the table

        Returns:
            List of column info dicts with keys: name, type, nullable, etc.
        """
        pass

    @abstractmethod
    def get_syntax_rules(self, language: str = "thai") -> str:
        """
        Get database-specific syntax rules for AI prompt.

        Args:
            language: "thai" or "english"

        Returns:
            Syntax rules text
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the database connection is working"""
        pass

    def validate_query(self, sql: str) -> tuple[bool, str]:
        """
        Validate SQL query for safety (SELECT only, no dangerous operations).

        Returns:
            (is_valid, error_message)
        """
        if not sql:
            return False, "SQL query is empty"

        sql_upper = sql.upper().strip()

        # Check for dangerous operations
        dangerous = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE', 'EXEC']
        for keyword in dangerous:
            # Check for keyword as whole word
            if f' {keyword} ' in f' {sql_upper} ' or sql_upper.startswith(f'{keyword} '):
                return False, f"SQL contains forbidden keyword: {keyword}"

        # Must be SELECT or WITH (CTE)
        normalized_sql = sql_upper.lstrip('(').strip()
        if not (normalized_sql.startswith('SELECT') or normalized_sql.startswith('WITH')):
            return False, "Only SELECT queries (or Common Table Expressions starting with WITH) are allowed"

        return True, ""


class SQLiteAdapter(DatabaseAdapter):
    """SQLite database adapter"""

    def __init__(self, db_path: str):
        """
        Initialize SQLite adapter.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    @property
    def engine_name(self) -> str:
        return "sqlite"

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def execute_query(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        """Execute SQL query and return results"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_schema_info(self, table_name: str) -> List[Dict]:
        """Get column information from SQLite pragma"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": not row["notnull"],
                    "default": row["dflt_value"],
                    "primary_key": bool(row["pk"])
                })
            return columns
        finally:
            conn.close()

    def get_syntax_rules(self, language: str = "thai") -> str:
        """Get SQLite-specific syntax rules"""
        if language == "thai":
            return """**Syntax สำหรับ SQLite:**
- ห้ามใช้ `CONCAT(a, b)` -> ให้ใช้ `a || b` แทน
- ห้ามใช้ `LPAD` -> ให้ใช้ `printf('%02d', CAST(col AS INTEGER))`
- ห้ามใช้ `DATE_FORMAT` -> ให้ใช้ `strftime`
- ห้ามใช้วงเล็บครอบ SELECT ใน UNION: `SELECT ... UNION ALL SELECT ...` ไม่ใช่ `(SELECT ...) UNION ALL (SELECT ...)`
- ใช้ `LIMIT` สำหรับจำกัดจำนวนแถว"""
        else:
            return """**SQLite Syntax:**
- NO `CONCAT(a, b)` -> Use `a || b` instead
- NO `LPAD` -> Use `printf('%02d', CAST(col AS INTEGER))`
- NO `DATE_FORMAT` -> Use `strftime`
- NO parentheses around SELECT in UNION: `SELECT ... UNION ALL SELECT ...` not `(SELECT ...) UNION ALL (SELECT ...)`
- Use `LIMIT` to restrict rows"""

    def test_connection(self) -> bool:
        """Test SQLite connection"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"SQLite connection test failed: {e}")
            return False


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL database adapter"""

    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL adapter.

        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self._conn = None

    @property
    def engine_name(self) -> str:
        return "postgresql"

    def _get_connection(self):
        """Get database connection"""
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(self.connection_string)
            return conn
        except ImportError:
            raise ImportError("Please install psycopg2: pip install psycopg2-binary")

    def execute_query(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        """Execute SQL query and return results"""
        import psycopg2.extras

        conn = self._get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_schema_info(self, table_name: str) -> List[Dict]:
        """Get column information from PostgreSQL information_schema"""
        sql = """
            SELECT
                column_name as name,
                data_type as type,
                is_nullable = 'YES' as nullable,
                column_default as default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """
        return self.execute_query(sql, (table_name,))

    def get_syntax_rules(self, language: str = "thai") -> str:
        """Get PostgreSQL-specific syntax rules"""
        if language == "thai":
            return """**Syntax สำหรับ PostgreSQL:**
- ใช้ `CONCAT(a, b)` หรือ `a || b` ได้
- การจัดรูปแบบวันที่ใช้ `to_char(date, 'YYYY-MM')`
- การแปลงชนิดข้อมูลใช้ `::integer` หรือ `CAST(col AS INTEGER)`
- ห้ามใช้ `strftime` (ของ SQLite)
- ใช้ `LIMIT` สำหรับจำกัดจำนวนแถว"""
        else:
            return """**PostgreSQL Syntax:**
- Use `CONCAT(a, b)` or `a || b`
- Date formatting: `to_char(date, 'YYYY-MM')`
- Type casting: `::integer` or `CAST(col AS INTEGER)`
- NO `strftime` (SQLite specific)
- Use `LIMIT` to restrict rows"""

    def test_connection(self) -> bool:
        """Test PostgreSQL connection"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"PostgreSQL connection test failed: {e}")
            return False


class MSSQLAdapter(DatabaseAdapter):
    """Microsoft SQL Server database adapter"""

    def __init__(self, connection_string: str):
        """
        Initialize MSSQL adapter.

        Args:
            connection_string: MSSQL connection string
        """
        self.connection_string = connection_string

    @property
    def engine_name(self) -> str:
        return "mssql"

    def _get_connection(self):
        """Get database connection"""
        try:
            import pyodbc
            conn = pyodbc.connect(self.connection_string)
            return conn
        except ImportError:
            raise ImportError("Please install pyodbc: pip install pyodbc")

    def execute_query(self, sql: str, params: Optional[tuple] = None) -> List[Dict]:
        """Execute SQL query and return results"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # Get column names
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def get_schema_info(self, table_name: str) -> List[Dict]:
        """Get column information from MSSQL"""
        sql = """
            SELECT
                COLUMN_NAME as name,
                DATA_TYPE as type,
                CASE WHEN IS_NULLABLE = 'YES' THEN 1 ELSE 0 END as nullable,
                COLUMN_DEFAULT as [default]
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """
        return self.execute_query(sql, (table_name,))

    def get_syntax_rules(self, language: str = "thai") -> str:
        """Get MSSQL-specific syntax rules"""
        if language == "thai":
            return """**Syntax สำหรับ MSSQL (SQL Server):**
- การต่อสตริงใช้ `+` เช่น `col1 + '-' + col2` (ห้ามใช้ `||`)
- การจัดรูปแบบวันที่ใช้ `FORMAT(date, 'yyyy-MM')`
- การแปลงชนิดข้อมูลใช้ `CONVERT(INT, col)` หรือ `CAST(col AS INT)`
- ห้ามใช้ `strftime`, `printf`, `LIMIT`
- ใช้ `TOP n` แทน `LIMIT n` เช่น `SELECT TOP 10 * FROM table`"""
        else:
            return """**MSSQL Syntax:**
- String concatenation: Use `+` e.g. `col1 + '-' + col2` (NO `||`)
- Date formatting: `FORMAT(date, 'yyyy-MM')`
- Type casting: `CONVERT(INT, col)` or `CAST(col AS INT)`
- NO `strftime`, `printf`, `LIMIT`
- Use `TOP n` instead of `LIMIT n` e.g. `SELECT TOP 10 * FROM table`"""

    def test_connection(self) -> bool:
        """Test MSSQL connection"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            return True
        except Exception as e:
            logger.error(f"MSSQL connection test failed: {e}")
            return False


# =========================================================
# Factory Function
# =========================================================

def create_adapter(
    db_url: Optional[str] = None,
    db_engine: Optional[str] = None,
    db_path: Optional[str] = None
) -> DatabaseAdapter:
    """
    Create appropriate database adapter based on configuration.

    Args:
        db_url: Database URL/connection string
        db_engine: Explicit engine type ('sqlite', 'postgresql', 'mssql')
        db_path: Path to SQLite database file (shortcut for SQLite)

    Returns:
        DatabaseAdapter instance

    Examples:
        # SQLite
        adapter = create_adapter(db_path="revenue.db")
        adapter = create_adapter(db_url="sqlite:///./revenue.db")

        # PostgreSQL
        adapter = create_adapter(db_url="postgresql://user:pass@localhost/db")

        # MSSQL
        adapter = create_adapter(db_url="mssql://server/db", db_engine="mssql")
    """
    # SQLite shortcut
    if db_path:
        return SQLiteAdapter(db_path)

    if not db_url:
        raise ValueError("Either db_url or db_path must be provided")

    # Detect engine from URL
    if db_engine:
        engine = db_engine.lower()
    elif db_url.startswith("sqlite"):
        engine = "sqlite"
    elif "postgresql" in db_url or "postgres" in db_url:
        engine = "postgresql"
    elif "mssql" in db_url or "sqlserver" in db_url:
        engine = "mssql"
    else:
        raise ValueError(f"Cannot detect database engine from URL: {db_url}")

    # Create adapter
    if engine == "sqlite":
        # Extract path from sqlite:/// URL
        path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
        return SQLiteAdapter(path)

    elif engine == "postgresql":
        return PostgreSQLAdapter(db_url)

    elif engine == "mssql":
        return MSSQLAdapter(db_url)

    else:
        raise ValueError(f"Unsupported database engine: {engine}")


def get_adapter_for_settings() -> DatabaseAdapter:
    """
    Create database adapter from application settings.

    Returns:
        DatabaseAdapter instance configured from settings
    """
    from app.config import settings

    db_url = settings.DATABASE_URL
    db_engine = getattr(settings, 'DB_ENGINE', None)

    return create_adapter(db_url=db_url, db_engine=db_engine)
