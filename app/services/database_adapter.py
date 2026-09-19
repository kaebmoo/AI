"""
NT AI Assistant - Database Adapter
========================================
In-process, read-only execution of LLM SQL on a context's source:

- DuckDBFileAdapter — files read in place (Plan 7 file source), ScopedDuckDB under a caller's scope
- ScopedSQLite      — the legacy business DB under a scope (unscoped legacy goes through the nt_query MCP server)
- check_select      — the query gate every such SQL passes; execute_select — gate + validator + row cap

The per-engine SQLite/PostgreSQL/MSSQL adapters and their settings factory were never wired
into the query path and were removed (REMAIN-9.9, git history has them) — a future SQL source
gets an adapter with the same contract as DuckDBFileAdapter: read-only, gated, pinned per build.
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


_parser_lock = threading.Lock()
_parser_conn = None


def check_select(sql: str, allowed: set, qualified_ok: bool = True, cur=None) -> None:
    """Allowlist gate, parsed by DuckDB: one SELECT reading only `allowed` tables or its own CTEs.

    qualified_ok=False (a scoped query, Phase 3): every reference must be unqualified so it
    resolves to the per-query TEMP view that applies the scope — `main.<view>` reads around it.
    cur: a DuckDB cursor to parse with; None = a private in-memory DuckDB (legacy SQLite SQL
    parses with DuckDB's parser — what doesn't parse is refused, fail closed).
    """
    global _parser_conn
    if cur is None:
        import duckdb
        with _parser_lock:
            if _parser_conn is None:
                _parser_conn = duckdb.connect()
            cur = _parser_conn.cursor()
    tree = json.loads(cur.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    if tree.get("error") or len(tree.get("statements", [])) != 1 \
            or ((tree["statements"][0] or {}).get("node") or {}).get("type") not in ("SELECT_NODE", "SET_OPERATION_NODE"):
        raise PermissionError("Only a single SELECT statement is allowed on a file source")

    def check(ref, visible):
        name = str(ref.get("table_name") or "").lower()
        schema = ref.get("schema_name") or ""
        if not qualified_ok and (ref.get("catalog_name") or schema):
            raise PermissionError(f"ภายใต้ scope ห้ามอ้างตารางแบบมี schema/catalog นำหน้า: {schema}.{name}")
        if ref.get("catalog_name") or schema not in ("", "main") or name not in allowed | visible:
            if not qualified_ok:
                raise PermissionError(f"ภายใต้ scope ใช้ได้เฉพาะตาราง {sorted(allowed)}: {name}")
            raise PermissionError(f"Only registered views can be queried on a file source: {name}")

    def walk(node, visible: frozenset):
        # CTE names are lexically scoped: a CTE body sees the CTEs before it (itself only when
        # recursive), the statement body sees all of its WITH, and nothing leaks outward — a
        # CTE inside a subquery must not legitimise an outer reference of the same name
        if isinstance(node, list):
            for value in node:
                walk(value, visible)
            return
        if not isinstance(node, dict):
            return
        if node.get("type") == "TABLE_FUNCTION":
            fn = (node.get("function") or {}).get("function_name")
            raise PermissionError(f"Table function not allowed on a file source: {fn}")
        if node.get("type") == "BASE_TABLE":
            check(node, visible)
        cte_map = node.get("cte_map")
        entries = [e for e in (cte_map.get("map") or []) if isinstance(e, dict)] if isinstance(cte_map, dict) else []
        names = [str(e.get("key", "")).lower() for e in entries]
        for i, entry in enumerate(entries):
            body = entry.get("value") or {}
            recursive = ((body.get("query") or {}).get("node") or {}).get("type") == "RECURSIVE_CTE_NODE"
            walk(body, visible | frozenset(names[:i + 1] if recursive else names[:i]))
        inner = visible | frozenset(names)
        for key, value in node.items():
            if key != "cte_map":
                walk(value, inner)

    walk(tree["statements"], frozenset())


def _shadow(execute, name: str, where: str, schema: str = "main") -> None:
    """TEMP view named like the real one: unqualified references read only `where` rows.

    schema = where the real one lives: SQLite `main`; DuckDB `"<db catalog>".main` — its TEMP
    objects sit in catalog temp, schema main, so a bare `main.<view>` would bind to itself.
    """
    execute(f"CREATE TEMP VIEW {_sql_ident(name)} AS SELECT * FROM {schema}.{_sql_ident(name)} WHERE {where}")


def _scope_hash(filters: Dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()[:8]


def _duckdb_engine(cursor_fn):
    """SQLAlchemy engine (duckdb_engine) over fresh cursors — for SchemaService inspection."""
    from duckdb_engine import ConnectionWrapper
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    return create_engine("duckdb://", creator=lambda: ConnectionWrapper(cursor_fn()), poolclass=NullPool)


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
        self.view_columns = {t: [c["name"] for c in cols] for t, _, cols in views}  # scope: which views can be filtered
        self._views = {t.lower() for t in self.view_columns}
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
        self._catalog = _sql_ident(self._conn.execute("SELECT current_database()").fetchone()[0]) + ".main"
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

    def cursor(self, shadows: Optional[Dict[str, str]] = None):
        """Fresh DuckDB cursor on the locked instance (TEMP objects die with it).

        shadows (a scope, Phase 3): TEMP views over every registered view — the listed ones
        filtered by their predicate, all others empty — so unqualified names read scoped rows only.
        """
        with self._cursor_lock:
            cur = self._conn.cursor()
        for name in self.view_columns if shadows is not None else ():
            _shadow(cur.execute, name, shadows.get(name, "false"), self._catalog)
        return cur

    @property
    def engine(self):
        """SQLAlchemy engine (duckdb_engine) so SchemaService can inspect the views."""
        if self._sa_engine is None:
            self._sa_engine = _duckdb_engine(self.cursor)
        return self._sa_engine

    def _check_select_over_views(self, cur, sql: str) -> None:
        check_select(sql, self._views, cur=cur)

    def execute_query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None) -> List[Dict]:
        return self.query(sql, params, max_rows)[0]

    def query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None,
              scope: Optional[Dict[str, str]] = None):
        """(rows, column names) — column names survive a zero-row result (xlsx export header).

        scope: {view: predicate} — only those views, filtered, unqualified (see ScopedDuckDB).
        """
        self._ensure_current()
        cur = self.cursor(scope)
        try:
            sql = _sqlite_like(sql)
            if scope is None:
                self._check_select_over_views(cur, sql)
            else:
                check_select(sql, {t.lower() for t in scope}, qualified_ok=False, cur=cur)
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


class ScopedDuckDB:
    """A file source seen through a caller's scope (Plan 7 Phase 3) — the adapter's interface.

    Every query and every SchemaService connection gets a fresh cursor whose TEMP views
    shadow ALL registered views: scoped ones filtered, the rest empty. Untrusted SQL may
    name only the scoped views, unqualified — so neither the LLM's SQL nor the prompt's
    data range/samples/value lookup can see rows outside the scope.
    """

    engine_name = "duckdb"

    def __init__(self, adapter: "DuckDBFileAdapter", filters: Dict[str, str], note: str = ""):
        self._adapter, self.filters, self.scope_note = adapter, filters, note
        self.manifest = adapter.manifest
        self.version = f"{adapter.version}-{_scope_hash(filters)}"
        self._sa_engine = None

    def is_current(self) -> bool:
        return self._adapter.is_current()

    def cursor(self):
        return self._adapter.cursor(self.filters)

    def query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None):
        return self._adapter.query(sql, params, max_rows, scope=self.filters)

    def execute_query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None) -> List[Dict]:
        return self.query(sql, params, max_rows)[0]

    @property
    def engine(self):
        if self._sa_engine is None:
            self._sa_engine = _duckdb_engine(self.cursor)
        return self._sa_engine


class ScopedSQLite:
    """The legacy business DB seen through a caller's scope (Plan 7 Phase 3).

    Scoped legacy SQL runs in-process (not via the nt_query MCP server) on a fresh
    read-only connection whose TEMP views shadow the scoped tables; untrusted SQL may
    name only those, unqualified — raw tables and other views are refused.
    """

    engine_name = "sqlite"
    manifest = None

    def __init__(self, db_path: str, filters: Dict[str, str], note: str = ""):
        from pathlib import Path

        self._uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        self.filters, self.scope_note = filters, note
        self.version = f"legacy-{_scope_hash(filters)}"
        self._sa_engine = None

    def _connect(self):
        # Shadow EVERY table/view (the non-scoped ones empty), as ScopedDuckDB does: the gate is
        # not the only barrier. Names inside main views still resolve within main, so the scoped
        # view keeps reading its real rows.
        conn = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
        filters = {k.lower(): v for k, v in self.filters.items()}
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'")]
        for name in names:
            _shadow(conn.execute, name, filters.get(name.lower(), "0"))
        return conn

    def query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None):
        check_select(sql, {t.lower() for t in self.filters}, qualified_ok=False)
        conn = self._connect()
        try:
            cur = conn.execute(sql, params or ())
            if not cur.description:
                return [], []
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
        finally:
            conn.close()
        return [dict(zip(columns, row)) for row in rows], columns

    def execute_query(self, sql: str, params: Optional[tuple] = None, max_rows: Optional[int] = None) -> List[Dict]:
        return self.query(sql, params, max_rows)[0]

    @property
    def engine(self):
        if self._sa_engine is None:
            from sqlalchemy import create_engine
            from sqlalchemy.pool import NullPool

            self._sa_engine = create_engine("sqlite://", creator=self._connect, poolclass=NullPool)
        return self._sa_engine


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
