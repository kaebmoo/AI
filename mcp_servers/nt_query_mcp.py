"""
NT Query MCP Server
Execute and validate SQL queries for NT AI Assistant

Supports: SQLite, PostgreSQL, MSSQL

Usage:
    python -m mcp_servers.nt_query_mcp

Environment Variables:
    METADATA_DB_URL: Database connection string (default: sqlite:///nt_fi_report.sqlite)
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nt_query_mcp")

# =========================================================
# Reuse Database Components from nt_metadata_mcp
# =========================================================

@dataclass
class DatabaseConfig:
    """Database connection configuration"""
    engine: str  # sqlite, postgresql, mssql
    connection_string: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Create config from environment variables"""
        db_url = os.getenv(
            "METADATA_DB_URL",
            f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nt_fi_report.sqlite')}"
        )

        if db_url.startswith("sqlite"):
            engine = "sqlite"
        elif "postgresql" in db_url or "postgres" in db_url:
            engine = "postgresql"
        elif "mssql" in db_url or "sqlserver" in db_url:
            engine = "mssql"
        else:
            engine = os.getenv("DB_ENGINE", "sqlite")

        return cls(engine=engine, connection_string=db_url)


class QueryDatabaseAdapter:
    """Database adapter for query execution"""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine = config.engine

    def _get_connection(self):
        """Get database connection based on engine.

        SQLite opens read-only at the connection level (defense in depth —
        regex validation is the first layer, mode=ro is the enforcement layer).
        """
        if self.engine == "sqlite":
            import sqlite3
            from pathlib import Path
            path = self.config.connection_string.replace("sqlite:///", "").replace("sqlite://", "")
            resolved = Path(path).resolve()
            if not resolved.exists():
                # mode=ro would fail anyway — fail loud with a readable message
                raise FileNotFoundError(f"Business DB not found at {resolved} (from METADATA_DB_URL)")
            # as_uri() handles spaces/special chars; no immutable=1 — ETL updates the file while running
            conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn

        elif self.engine == "postgresql":
            try:
                import psycopg2
                import psycopg2.extras
                return psycopg2.connect(self.config.connection_string)
            except ImportError:
                raise ImportError("Please install psycopg2: pip install psycopg2-binary")

        elif self.engine == "mssql":
            try:
                import pyodbc
                return pyodbc.connect(self.config.connection_string)
            except ImportError:
                raise ImportError("Please install pyodbc: pip install pyodbc")

        raise ValueError(f"Unsupported engine: {self.engine}")

    def execute_query(self, sql: str, params: tuple = None, max_rows: int = None) -> List[Dict]:
        """Execute query and return results as list of dicts.

        max_rows: client-side row cap via fetchmany — engine-agnostic (works on
        MSSQL where appending LIMIT would be a syntax error).
        """
        # PostgreSQL only: psycopg2's default cursor loads the FULL result set
        # into the client on execute() (fetchmany doesn't help) — wrap in a
        # subquery to cap server-side. Do NOT do this for MSSQL (T-SQL rejects
        # CTEs inside a FROM-subquery); pyodbc streams batches so fetchmany suffices.
        if self.engine == "postgresql" and max_rows:
            sql = f"SELECT * FROM ({sql.rstrip().rstrip(';')}) AS _lim LIMIT {int(max_rows)}"

        conn = self._get_connection()

        try:
            if self.engine == "postgresql":
                import psycopg2.extras
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                cursor = conn.cursor()

            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            if not cursor.description:
                return []

            rows = cursor.fetchmany(max_rows) if max_rows else cursor.fetchall()

            if self.engine == "postgresql":
                return [dict(row) for row in rows]
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

        finally:
            conn.close()

    def get_placeholder(self) -> str:
        """Get parameter placeholder for the database engine"""
        if self.engine == "mssql":
            return "?"
        elif self.engine == "postgresql":
            return "%s"
        else:  # sqlite
            return "?"


# =========================================================
# Initialize MCP Server
# =========================================================

mcp = FastMCP(
    name="NT Query Server",
    instructions="Execute and validate SQL queries for NT AI Assistant. Provides tools for SQL validation, execution, sample data retrieval, and Thai language SQL explanation."
)

# Global database adapter
_db_adapter: Optional[QueryDatabaseAdapter] = None


def get_db() -> QueryDatabaseAdapter:
    """Get or create database adapter"""
    global _db_adapter
    if _db_adapter is None:
        config = DatabaseConfig.from_env()
        _db_adapter = QueryDatabaseAdapter(config)
        logger.info(f"Connected to {config.engine} database")
        if config.engine == "mssql":
            # Read-only enforcement for MSSQL happens at the credential level
            logger.warning("MSSQL: ensure the login used here is read-only (SELECT/db_datareader only)")
    return _db_adapter


def quote_identifier(db: QueryDatabaseAdapter, name: str) -> str:
    if db.engine == "mssql":
        return f"[{name.replace(']', ']]')}]"
    return '"' + name.replace('"', '""') + '"'


def table_columns(db: QueryDatabaseAdapter, table_name: str) -> List[str]:
    quoted_table = quote_identifier(db, table_name)
    if db.engine == "sqlite":
        rows = db.execute_query(f"PRAGMA table_info({quoted_table})")
        return [row["name"] for row in rows]
    ph = db.get_placeholder()
    if db.engine == "postgresql":
        rows = db.execute_query(
            f"SELECT column_name AS name FROM information_schema.columns WHERE table_name = {ph}",
            (table_name,),
        )
    elif db.engine == "mssql":
        rows = db.execute_query(
            f"SELECT COLUMN_NAME AS name FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = {ph}",
            (table_name,),
        )
    else:
        rows = []
    return [row["name"] for row in rows]


def safe_table(db: QueryDatabaseAdapter, table_name: str) -> str:
    """Validate table_name against real tables/views, return a quoted identifier.

    Identifiers can't be passed as bind params, so allowlist against the live
    catalog and reject anything unknown before interpolating.
    """
    if db.engine == "sqlite":
        rows = db.execute_query("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    elif db.engine == "postgresql":
        rows = db.execute_query("SELECT table_name AS name FROM information_schema.tables")
    elif db.engine == "mssql":
        rows = db.execute_query("SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES")
    else:
        rows = []
    if table_name not in {r["name"] for r in rows}:
        raise ValueError(f"Unknown table: {table_name}")
    return quote_identifier(db, table_name)


def safe_column(db: QueryDatabaseAdapter, table_name: str, column_name: str) -> str:
    if column_name not in table_columns(db, table_name):
        raise ValueError(f"Unknown column: {column_name}")
    return quote_identifier(db, column_name)


# =========================================================
# MCP Tools
# =========================================================

# Single source of truth for SQL validation — app/services/validation_service.py
# (top-level imports there are stdlib-only, so no app.config chain is dragged in)
from app.services.validation_service import ValidationService

_validator = ValidationService(db=None)


@mcp.tool()
def validate_sql(sql: str) -> Dict[str, Any]:
    """
    ตรวจสอบ SQL ว่าปลอดภัยและถูกต้อง

    Args:
        sql: SQL query to validate

    Returns:
        {
            "valid": bool,
            "issues": ["error messages..."],
            "warnings": ["warning messages..."],
            "sql_type": "SELECT/WITH/etc"
        }

    Example:
        validate_sql("SELECT * FROM revenue_search WHERE year = 2025")
        → {"valid": True, "issues": [], "warnings": ["Consider adding LIMIT..."], "sql_type": "SELECT"}
    """
    return _validator.validate_sql(sql)


@mcp.tool()
def execute_query(
    sql: str,
    limit: int = 100,
    validate_first: bool = True
) -> Dict[str, Any]:
    """
    Execute validated SELECT query and return results

    Args:
        sql: SQL query to execute
        limit: Maximum rows to return (default: 100, max: 1000)
        validate_first: Whether to validate SQL before execution (default: True)

    Returns:
        {
            "success": bool,
            "data": [...],
            "row_count": int,
            "columns": ["col1", "col2", ...],
            "truncated": bool,
            "error": "error message if failed"
        }

    Example:
        execute_query("SELECT year, SUM(revenue) FROM revenue_search GROUP BY year", limit=10)
    """
    # Enforce limit bounds
    limit = min(max(1, limit), 1000)

    # Validate first if requested
    if validate_first:
        validation = validate_sql(sql)
        if not validation["valid"]:
            return {
                "success": False,
                "error": "SQL validation failed",
                "issues": validation["issues"],
                "data": [],
                "row_count": 0,
                "columns": [],
                "truncated": False
            }

    try:
        db = get_db()

        # Row cap via fetchmany (engine-agnostic — no LIMIT string appending,
        # which breaks on MSSQL and misfires on subqueries containing LIMIT).
        # +1 row to detect truncation; `truncated` flag semantics unchanged.
        rows = db.execute_query(sql, max_rows=limit + 1)

        truncated = len(rows) > limit
        if truncated:
            rows = rows[:limit]

        # Get columns from first row or empty
        columns = list(rows[0].keys()) if rows else []

        return {
            "success": True,
            "data": rows,
            "row_count": len(rows),
            "columns": columns,
            "truncated": truncated,
            "error": None
        }

    except Exception as e:
        logger.error(f"Query execution error: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": [],
            "row_count": 0,
            "columns": [],
            "truncated": False
        }


@mcp.tool()
def get_sample_values(
    column_name: str,
    table_name: str = "revenue_search",
    limit: int = 20
) -> Dict[str, Any]:
    """
    ดึงตัวอย่างค่าที่ไม่ซ้ำใน column

    Args:
        column_name: ชื่อ column ที่ต้องการดูค่า
        table_name: ชื่อ table หรือ view (default: revenue_search)
        limit: จำนวนค่าที่ต้องการ (default: 20, max: 100)

    Returns:
        {
            "column": "column_name",
            "table": "table_name",
            "values": ["value1", "value2", ...],
            "total_distinct": int,
            "sample_count": int
        }

    Example:
        get_sample_values("department", "revenue_search", 10)
        → {"column": "department", "values": ["ฝ่ายการเงิน", "ฝ่ายบุคคล", ...], "total_distinct": 45}
    """
    limit = min(max(1, limit), 100)

    try:
        db = get_db()

        # Allowlist + quote identifiers before interpolating.
        quoted_table = safe_table(db, table_name)
        quoted_column = safe_column(db, table_name, column_name)

        # Get sample distinct values
        if db.engine == "mssql":
            values_sql = f'''
                SELECT DISTINCT TOP {limit} {quoted_column}
                FROM {quoted_table}
                WHERE {quoted_column} IS NOT NULL
            '''
        else:
            values_sql = f'''
                SELECT DISTINCT {quoted_column}
                FROM {quoted_table}
                WHERE {quoted_column} IS NOT NULL
                LIMIT {limit}
            '''

        rows = db.execute_query(values_sql)
        values = [row[column_name] for row in rows]

        # Get total distinct count
        count_sql = f'''
            SELECT COUNT(DISTINCT {quoted_column}) as cnt
            FROM {quoted_table}
            WHERE {quoted_column} IS NOT NULL
        '''
        count_result = db.execute_query(count_sql)
        total_distinct = count_result[0]['cnt'] if count_result else 0

        return {
            "column": column_name,
            "table": table_name,
            "values": values,
            "total_distinct": total_distinct,
            "sample_count": len(values)
        }

    except Exception as e:
        logger.error(f"Error getting sample values: {e}")
        return {
            "column": column_name,
            "table": table_name,
            "error": str(e),
            "values": [],
            "total_distinct": 0,
            "sample_count": 0
        }


@mcp.tool()
def explain_sql_thai(sql: str) -> Dict[str, Any]:
    """
    อธิบาย SQL เป็นภาษาไทยแบบทีละขั้นตอน

    Args:
        sql: SQL query to explain

    Returns:
        {
            "steps": ["ขั้นตอนที่ 1...", "ขั้นตอนที่ 2..."],
            "summary": "สรุปสั้นๆ",
            "components": {
                "select": "...",
                "from": "...",
                "where": "...",
                "group_by": "...",
                "order_by": "...",
                "limit": "..."
            }
        }

    Example:
        explain_sql_thai("SELECT department, SUM(revenue) FROM revenue_search WHERE year = 2025 GROUP BY department")
    """
    steps = []
    components = {}
    sql_upper = sql.upper()

    # Parse SELECT clause
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
    if select_match:
        select_clause = select_match.group(1).strip()
        components["select"] = select_clause

        # Analyze SELECT
        if select_clause == '*':
            steps.append("เลือกข้อมูลทุกคอลัมน์")
        else:
            # Check for aggregates
            aggregates = []
            if 'SUM(' in sql_upper:
                aggregates.append("รวมยอด (SUM)")
            if 'COUNT(' in sql_upper:
                aggregates.append("นับจำนวน (COUNT)")
            if 'AVG(' in sql_upper:
                aggregates.append("หาค่าเฉลี่ย (AVG)")
            if 'MAX(' in sql_upper:
                aggregates.append("หาค่าสูงสุด (MAX)")
            if 'MIN(' in sql_upper:
                aggregates.append("หาค่าต่ำสุด (MIN)")

            if aggregates:
                steps.append(f"คำนวณ: {', '.join(aggregates)}")

            # List columns
            cols = [c.strip() for c in select_clause.split(',')]
            non_agg_cols = [c for c in cols if not any(agg in c.upper() for agg in ['SUM(', 'COUNT(', 'AVG(', 'MAX(', 'MIN('])]
            if non_agg_cols:
                steps.append(f"เลือกคอลัมน์: {', '.join(non_agg_cols[:5])}" + ("..." if len(non_agg_cols) > 5 else ""))

    # Parse FROM clause
    from_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
    if from_match:
        table = from_match.group(1)
        components["from"] = table

        # Translate common table names
        table_names_thai = {
            "revenue_search": "ตารางรายได้",
            "v_expense_mart": "ตารางค่าใช้จ่าย",
            "revenue": "ตารางรายได้",
            "expense": "ตารางค่าใช้จ่าย"
        }
        table_thai = table_names_thai.get(table.lower(), f"ตาราง {table}")
        steps.append(f"จาก{table_thai}")

    # Parse JOIN clauses
    join_matches = re.findall(r'(LEFT|RIGHT|INNER|OUTER|CROSS)?\s*JOIN\s+(\w+)', sql, re.IGNORECASE)
    if join_matches:
        for join_type, join_table in join_matches:
            join_type = join_type or "INNER"
            steps.append(f"เชื่อมกับตาราง {join_table} ({join_type} JOIN)")

    # Parse WHERE clause
    where_match = re.search(r'WHERE\s+(.*?)(?:GROUP BY|ORDER BY|HAVING|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
    if where_match:
        where_clause = where_match.group(1).strip()
        components["where"] = where_clause

        # Parse conditions
        conditions = []

        # Year condition
        year_match = re.search(r'year\s*=\s*(\d+)', where_clause, re.IGNORECASE)
        if year_match:
            year = int(year_match.group(1))
            thai_year = year + 543
            conditions.append(f"ปี {year} (พ.ศ. {thai_year})")

        # Month condition
        month_match = re.search(r'month\s*=\s*(\d+)', where_clause, re.IGNORECASE)
        if month_match:
            month = int(month_match.group(1))
            thai_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม",
                         "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
            month_name = thai_months[month] if 1 <= month <= 12 else str(month)
            conditions.append(f"เดือน{month_name}")

        # Other conditions
        if not conditions:
            conditions.append(where_clause[:100] + ("..." if len(where_clause) > 100 else ""))

        steps.append(f"กรองข้อมูล: {', '.join(conditions)}")

    # Parse GROUP BY clause
    group_match = re.search(r'GROUP BY\s+(.*?)(?:HAVING|ORDER BY|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
    if group_match:
        group_clause = group_match.group(1).strip()
        components["group_by"] = group_clause
        steps.append(f"จัดกลุ่มตาม: {group_clause}")

    # Parse HAVING clause
    having_match = re.search(r'HAVING\s+(.*?)(?:ORDER BY|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
    if having_match:
        having_clause = having_match.group(1).strip()
        components["having"] = having_clause
        steps.append(f"กรองกลุ่มที่: {having_clause}")

    # Parse ORDER BY clause
    order_match = re.search(r'ORDER BY\s+(.*?)(?:LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
    if order_match:
        order_clause = order_match.group(1).strip()
        components["order_by"] = order_clause

        order_desc = order_clause
        if 'DESC' in order_clause.upper():
            order_desc = order_clause.replace('DESC', '').replace('desc', '').strip() + " (มากไปน้อย)"
        elif 'ASC' in order_clause.upper():
            order_desc = order_clause.replace('ASC', '').replace('asc', '').strip() + " (น้อยไปมาก)"

        steps.append(f"เรียงลำดับตาม: {order_desc}")

    # Parse LIMIT clause
    limit_match = re.search(r'LIMIT\s+(\d+)', sql, re.IGNORECASE)
    if limit_match:
        limit_val = limit_match.group(1)
        components["limit"] = limit_val
        steps.append(f"แสดงผลไม่เกิน {limit_val} แถว")

    # Generate summary
    if steps:
        summary = " → ".join(steps[:4])
        if len(steps) > 4:
            summary += " → ..."
    else:
        summary = "ไม่สามารถวิเคราะห์ SQL ได้"

    return {
        "steps": steps,
        "summary": summary,
        "components": components
    }


@mcp.tool()
def get_table_stats(table_name: str = "revenue_search") -> Dict[str, Any]:
    """
    ดึงสถิติของตาราง

    Args:
        table_name: ชื่อตารางหรือ view

    Returns:
        {
            "table": "table_name",
            "row_count": int,
            "columns": [...],
            "sample_row": {...}
        }

    Example:
        get_table_stats("revenue_search")
    """
    try:
        db = get_db()

        # Allowlist + quote the table name (validates it exists, blocks injection)
        quoted_table = safe_table(db, table_name)

        # Get row count
        count_sql = f"SELECT COUNT(*) as cnt FROM {quoted_table}"
        count_result = db.execute_query(count_sql)
        row_count = count_result[0]['cnt'] if count_result else 0

        # Get columns (using PRAGMA for SQLite, INFORMATION_SCHEMA for others)
        columns = []
        if db.engine == "sqlite":
            col_result = db.execute_query(f"PRAGMA table_info({quoted_table})")
            columns = [{"name": row["name"], "type": row["type"]} for row in col_result]
        elif db.engine == "postgresql":
            ph = db.get_placeholder()
            col_sql = f"""
                SELECT column_name as name, data_type as type
                FROM information_schema.columns
                WHERE table_name = {ph}
            """
            columns = db.execute_query(col_sql, (table_name,))
        elif db.engine == "mssql":
            ph = db.get_placeholder()
            col_sql = f"""
                SELECT COLUMN_NAME as name, DATA_TYPE as type
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = {ph}
            """
            columns = db.execute_query(col_sql, (table_name,))

        # Get sample row
        if db.engine == "mssql":
            sample_sql = f"SELECT TOP 1 * FROM {quoted_table}"
        else:
            sample_sql = f"SELECT * FROM {quoted_table} LIMIT 1"

        sample_result = db.execute_query(sample_sql)
        sample_row = sample_result[0] if sample_result else {}

        return {
            "table": table_name,
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "sample_row": sample_row
        }

    except Exception as e:
        logger.error(f"Error getting table stats: {e}")
        return {
            "table": table_name,
            "error": str(e),
            "row_count": 0,
            "columns": [],
            "sample_row": {}
        }


# =========================================================
# Main Entry Point
# =========================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NT Query MCP Server")
    parser.add_argument(
        "--db-url",
        help="Database URL (default: from METADATA_DB_URL env or nt_fi_report.sqlite)"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)"
    )

    args = parser.parse_args()

    if args.db_url:
        os.environ["METADATA_DB_URL"] = args.db_url

    logger.info("Starting NT Query MCP Server...")
    mcp.run(transport=args.transport)
