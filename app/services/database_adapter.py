"""
NT AI Assistant - Database Adapter
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

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
from abc import ABC, abstractmethod
from decimal import Decimal
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
# DuckDB file source (Plan 7 Phase 1 — zero-import)
# =========================================================

# Types a registry row may declare — anything else is rejected (the type string
# is interpolated into the view DDL, so it must never come from free text)
DUCKDB_COLUMN_TYPES = {"BIGINT", "INTEGER", "DOUBLE", "VARCHAR", "BOOLEAN", "DATE", "TIMESTAMP"}

DUCKDB_SYNTAX_RULES = {
    "thai": """   **. DuckDB Syntax (file source):**
       - หารจำนวนเต็มใช้ `//` เช่น `year_month // 100` — `/` ให้ผลเป็นทศนิยมเสมอ (202608 / 100 = 2026.08)
       - วันที่ปัจจุบันใช้ `current_date` (ห้ามใช้ `date('now')`)
       - ห้ามเทียบหลายคอลัมน์กับ subquery ด้วย `=` เช่น `(year, month) = (SELECT ...)` — ใช้ `IN` หรือ subquery คอลัมน์เดียว เช่น `year_month = (SELECT MAX(year_month) FROM ...)`
       - ต่อสตริงใช้ `a || b`, จำกัดแถวใช้ `LIMIT`""",
    "english": """   **. DuckDB Syntax (file source):**
       - Integer division: use `//` e.g. `year_month // 100` — `/` always returns a decimal (202608 / 100 = 2026.08)
       - Current date: `current_date` (NO `date('now')`)
       - NO multi-column `=` against a subquery like `(year, month) = (SELECT ...)` — use `IN` or a single-column subquery e.g. `year_month = (SELECT MAX(year_month) FROM ...)`
       - Concatenate with `a || b`, restrict rows with `LIMIT`""",
}


# SQLite LIKE ignores case, DuckDB LIKE does not. Prompts, golden, ValueVerifier and
# WarningDetector were all built on SQLite semantics ('%HARD INFRA%' must match
# '1.Hard Infrastructure'), so on a file source LIKE runs as ILIKE. String literals
# and quoted identifiers are matched first so a LIKE inside them is left alone.
_LIKE_OR_QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|\bLIKE\b", re.IGNORECASE)


def _sqlite_like(sql: str) -> str:
    return _LIKE_OR_QUOTED.sub(lambda m: "ILIKE" if m.group(0).upper() == "LIKE" else m.group(0), sql)


def _sqlite_value(v):
    """Result values shaped like the SQLite path: DECIMAL → float, and x/0 → None
    (DuckDB gives inf/nan, which is not valid JSON and breaks the SSE answer)."""
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class SourceUnavailable(Exception):
    """The file source is not in a verified, consistent state (e.g. mid-publish).

    Deliberately NOT a ValueError/RuntimeError: the query pipeline must surface it
    to the user, never hand it to the LLM as a "fix your SQL" error.
    """


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class DuckDBFileAdapter(DatabaseAdapter):
    """Read-only DuckDB over CSV files under one source root — nothing is imported.

    Each registered table becomes a view with the name the LLM/golden already
    know (e.g. ``feed_revenue_fact_bu_monthly``) over ``read_csv(<root>/<file>)``,
    typed from the registry (contract dtypes — code columns stay strings).

    Engine-level lock, behind the F4 validator (verified on DuckDB 1.5.5):
      - views live in a small DuckDB file reopened ``read_only`` → no CREATE/DROP/INSERT
      - ``allowed_paths`` = exactly the registered files, then
        ``enable_external_access=false`` → no other file, COPY TO, ATTACH, http,
        extension INSTALL/LOAD
      - ``lock_configuration=true`` → SQL cannot SET any of the above back
      - every query runs on a fresh cursor → TEMP objects die with it
      - execute_query (the untrusted-SQL path) parses with DuckDB's own parser and
        allows one SELECT over registered views/CTEs only — no table functions
        (lock_configuration does not cover e.g. enable_logging(), which can abort
        the process or log other users' SQL)
    """

    def __init__(self, name: str, root: str, tables: List[Dict], cache_dir: str,
                 manifest_file: Optional[str] = None):
        import duckdb

        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError(f"Invalid source name: {name!r}")
        self.name = name
        # Pinned to ONE build: views read the real directory behind <root>, so a re-pointed
        # symlinked latest/ can't mix two builds in one answer (the resolver builds a new
        # adapter for the new build; in-flight requests finish on the old one)
        lexical_root = os.path.abspath(root)
        if not os.path.isdir(lexical_root):
            raise SourceUnavailable(f"ไม่พบโฟลเดอร์ของ source '{name}' ({lexical_root}) — ข้อมูลอาจกำลังถูก publish")
        self.root = os.path.realpath(lexical_root)

        views, by_name = [], {}
        for t in tables:
            lexical = os.path.abspath(os.path.join(lexical_root, t["file_name"]))
            path = os.path.realpath(lexical)
            # '..' (lexical) and symlinked files (real) must both stay under the root
            if (os.path.commonpath([lexical, lexical_root]) != lexical_root
                    or os.path.commonpath([path, self.root]) != self.root):
                raise ValueError(f"File outside source root: {t['file_name']}")
            if not os.path.isfile(path):
                raise SourceUnavailable(f"ไม่พบไฟล์ {t['file_name']} ของ source '{name}' — ข้อมูลอาจกำลังถูก publish")
            views.append((t["table_name"], path, t["columns"]))
            by_name[t["file_name"]] = path
        self.files = sorted(by_name.values())
        self._views = {t.lower() for t, _, _ in views}
        self._watched = self.files + ([os.path.join(self.root, manifest_file)] if manifest_file else [])

        # Verify once per build, then only stat per query (publish race — PLAN_7 §11.7)
        self.manifest = self._verify_manifest(manifest_file, by_name) if manifest_file else None
        self._identity = self._snapshot()
        if self._identity is None:
            raise SourceUnavailable(f"ไฟล์ของ source '{name}' หายระหว่างเตรียม — ข้อมูลอาจกำลังถูก publish")
        self.version = hashlib.sha256(repr(self._identity).encode()).hexdigest()[:12]

        db_path = self._build_view_db(views, cache_dir)
        self._conn = duckdb.connect(db_path, read_only=True, config={
            "autoload_known_extensions": False, "autoinstall_known_extensions": False,
            # every process opens this same file; DuckDB's default spill dir (<db>.tmp, fixed
            # file names) would then be shared and concurrent spills corrupt each other (SIGSEGV).
            # No spill dir also leaves allowed_directories empty. ponytail: no spilling — a
            # query bigger than memory_limit fails loudly; per-process temp dirs if that bites
            "temp_directory": "",
        })
        # Order matters: allowed_paths can't be set after external access is off,
        # and nothing can be set after the lock
        self._conn.execute("SET allowed_paths = ?", [self.files])
        self._conn.execute("SET enable_external_access = false")
        self._conn.execute("SET lock_configuration = true")
        self._cursor_lock = threading.Lock()
        self._sa_engine = None

    def _build_view_db(self, views, cache_dir: str) -> str:
        """Write the view definitions to <cache_dir>/<name>.duckdb (tmp + atomic replace)."""
        import duckdb

        os.makedirs(cache_dir, exist_ok=True)
        # version in the name: a rebuilt build must not reuse DuckDB's instance cache for
        # a path the previous (locked) adapter of this process still has open
        final = os.path.join(cache_dir, f"{self.name}-{self.version}.duckdb")
        self.db_path = final
        tmp = f"{final}.{os.getpid()}.tmp"
        if os.path.exists(tmp):
            os.remove(tmp)
        con = duckdb.connect(tmp)
        try:
            for table, path, columns in views:
                col_defs = []
                for c in columns:
                    col_type = str(c["type"]).upper()
                    if col_type not in DUCKDB_COLUMN_TYPES:
                        raise ValueError(f"Unsupported column type {c['type']!r} in {table}.{c['name']}")
                    col_defs.append(f"{_sql_str(c['name'])}: {_sql_str(col_type)}")
                # types= binds by header NAME (columns= would bind by position: a reordered
                # publish would silently swap values); a missing column fails loudly.
                # Dialect pinned (RFC 4180 as pandas writes it): the sniffer samples the first
                # ~20k rows, so a file whose first quoted field comes later (fact_sales.csv)
                # was sniffed as quote='' and failed on "2G, 3G, 4G"
                select_list = ", ".join(_sql_ident(c["name"]) for c in columns)
                con.execute(
                    f"CREATE VIEW {_sql_ident(table)} AS SELECT {select_list} FROM read_csv("
                    f"{_sql_str(path)}, header=true, delim=',', quote='\"', escape='\"', "
                    f"types={{{', '.join(col_defs)}}})"
                )
        finally:
            con.close()
        os.replace(tmp, final)
        return final

    def _snapshot(self):
        """(inode, size, mtime) of every watched file — None if any is missing."""
        try:
            return tuple((st.st_ino, st.st_size, st.st_mtime_ns) for st in map(os.stat, self._watched))
        except FileNotFoundError:
            return None

    def _verify_manifest(self, manifest_file: str, by_name: Dict[str, str]) -> Dict:
        """The files must be exactly what a passing manifest describes (sha256, once per build)."""
        before = self._snapshot()
        try:
            with open(os.path.join(self.root, manifest_file), encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, ValueError) as e:
            raise SourceUnavailable(f"อ่าน {manifest_file} ไม่ได้ ({e}) — ข้อมูลอาจกำลังถูก publish")
        if not (manifest.get("reconcile") or {}).get("ok"):
            raise SourceUnavailable("manifest reconcile.ok ไม่ผ่าน — ไม่ตอบจากข้อมูลที่ไม่ผ่านการกระทบยอด")
        listed = manifest.get("files") or {}
        for file_name, path in by_name.items():
            if (listed.get(file_name) or {}).get("sha256") != _sha256(path):
                raise SourceUnavailable(f"{file_name} ไม่ตรง manifest — ข้อมูลอาจกำลังถูก publish")
        if before is None or before != self._snapshot():
            raise SourceUnavailable("ไฟล์เปลี่ยนระหว่างตรวจ manifest — ข้อมูลกำลังถูก publish")
        logger.info(f"Source {self.name}: verified build period={manifest.get('period')} "
                    f"built_at={manifest.get('built_at')}")
        return manifest

    def is_current(self) -> bool:
        """False once any file of the verified build changed or vanished (in-place publish)."""
        return self._snapshot() == self._identity

    def _ensure_current(self) -> None:
        if not self.is_current():
            raise SourceUnavailable(f"ข้อมูลของ source '{self.name}' เปลี่ยนหรือกำลังถูก publish — กรุณาถามใหม่อีกครั้ง")

    @property
    def engine_name(self) -> str:
        return "duckdb"

    def cursor(self):
        """Fresh DuckDB cursor on the locked instance (TEMP objects die with it)."""
        with self._cursor_lock:
            return self._conn.cursor()

    @property
    def engine(self):
        """SQLAlchemy engine (duckdb_engine) so SchemaService can inspect the views."""
        if self._sa_engine is None:
            from duckdb_engine import ConnectionWrapper
            from sqlalchemy import create_engine
            from sqlalchemy.pool import NullPool

            self._sa_engine = create_engine(
                "duckdb://", creator=lambda: ConnectionWrapper(self.cursor()), poolclass=NullPool,
            )
        return self._sa_engine

    def _check_select_over_views(self, cur, sql: str) -> None:
        """Allowlist gate, parsed by DuckDB: one SELECT reading only registered views or its own CTEs."""
        tree = json.loads(cur.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
        if tree.get("error") or len(tree.get("statements", [])) != 1:
            raise PermissionError("Only a single SELECT statement is allowed on a file source")
        refs, ctes = [], set()

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "TABLE_FUNCTION":
                    fn = (node.get("function") or {}).get("function_name")
                    raise PermissionError(f"Table function not allowed on a file source: {fn}")
                if node.get("type") == "BASE_TABLE":
                    refs.append(node)
                cte_map = node.get("cte_map")
                if isinstance(cte_map, dict):
                    ctes.update(str(e.get("key", "")).lower() for e in cte_map.get("map", []) if isinstance(e, dict))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(tree["statements"])
        for ref in refs:
            name = str(ref.get("table_name") or "").lower()
            if ref.get("catalog_name") or (ref.get("schema_name") or "") not in ("", "main") \
                    or name not in self._views | ctes:
                raise PermissionError(f"Only registered views can be queried on a file source: {name}")

    def execute_query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None) -> List[Dict]:
        return self.query(sql, params, max_rows)[0]

    def query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None):
        """(rows, column names) — column names survive a zero-row result (xlsx export header)."""
        self._ensure_current()
        cur = self.cursor()
        try:
            sql = _sqlite_like(sql)
            self._check_select_over_views(cur, sql)
            try:
                cur.execute(sql, params) if params else cur.execute(sql)
                if not cur.description:
                    return [], []
                columns = [d[0] for d in cur.description]
                rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
            except Exception as e:
                if not self.is_current():  # files changed under the read (partial / missing file)
                    raise SourceUnavailable(
                        f"ข้อมูลของ source '{self.name}' เปลี่ยนระหว่างอ่าน — กรุณาถามใหม่อีกครั้ง") from e
                raise
        finally:
            cur.close()
        self._ensure_current()  # a publish overlapped the read → the rows may mix two builds
        return [{c: _sqlite_value(v) for c, v in zip(columns, row)} for row in rows], columns

    def get_schema_info(self, table_name: str) -> List[Dict]:
        rows = self.execute_query(f"DESCRIBE {_sql_ident(table_name)}")
        return [
            {"name": r["column_name"], "type": r["column_type"], "nullable": r["null"] == "YES"}
            for r in rows
        ]

    def get_syntax_rules(self, language: str = "thai") -> str:
        return DUCKDB_SYNTAX_RULES["thai" if language == "thai" else "english"]

    def test_connection(self) -> bool:
        try:
            return self.execute_query("SELECT 1 AS ok")[0]["ok"] == 1
        except Exception as e:
            logger.error(f"DuckDB connection test failed ({self.name}): {e}")
            return False


def execute_select(db, sql: str, limit: int = 100, validate_first: bool = True) -> Dict[str, Any]:
    """Validated, row-capped SELECT → the MCP ``execute_query`` payload.

    Single definition shared by the nt_query MCP tool (legacy business DB) and
    the in-process file-source path. ``db`` = anything with
    ``execute_query(sql, max_rows=)``.
    """
    from app.services.validation_service import ValidationService

    limit = min(max(1, limit), 1000)
    if validate_first:
        validation = ValidationService(db=None).validate_sql(
            sql, file_source=getattr(db, "engine_name", None) == "duckdb",
        )
        if not validation["valid"]:
            return {
                "success": False, "error": "SQL validation failed", "issues": validation["issues"],
                "data": [], "row_count": 0, "columns": [], "truncated": False,
            }
    try:
        # Row cap via fetchmany (engine-agnostic — no LIMIT string appending);
        # +1 row to detect truncation
        rows = db.execute_query(sql, max_rows=limit + 1)
        truncated = len(rows) > limit
        if truncated:
            rows = rows[:limit]
        return {
            "success": True, "data": rows, "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [], "truncated": truncated, "error": None,
        }
    except SourceUnavailable:
        raise  # not a SQL problem — the caller must tell the user, not retry the LLM
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        return {"success": False, "error": str(e), "data": [], "row_count": 0, "columns": [], "truncated": False}


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
