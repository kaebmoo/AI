"""
Data source registry + per-request resolver (Plan 7 Phase 1)
=============================================================
context → schema_contexts.source_id → data_sources → engine.

- 'legacy'      = the business DB เดิม (BUSINESS_DB_PATH, SQL executed by the nt_query MCP server)
- 'duckdb_file' = files under data_sources.root_path, read in place through DuckDBFileAdapter
                  (zero-import: nothing is copied into the business DB)

A context with no source_id (or a config DB not yet migrated) is legacy, so every
context that existed before Plan 7 behaves exactly as before.
A file-source context never falls back to legacy: an unusable source raises —
a silent fallback would answer from the stale imported copy.

Scope (Phase 3): while ``request_scope`` holds a caller's scope (set per request by
QueryEngine), every resolution returns the source seen through it — ScopedDuckDB /
ScopedSQLite — so the LLM's SQL, the prompt's data range and the value lookup all read
the same filtered rows. A scope the context can't enforce raises ScopeError (HTTP 400).
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.llm_policy import FULL, SCHEMA_ONLY, normalize, parse_allowlist
from app.services.database_adapter import DuckDBFileAdapter, ScopedDuckDB, ScopedSQLite, execute_select

logger = logging.getLogger(__name__)

LEGACY = "legacy"
DUCKDB_FILE = "duckdb_file"

# MCP tools that read the business DB but have no file-source implementation yet —
# on a file source they fail closed instead of silently reading the legacy DB
_LEGACY_ONLY_DATA_TOOLS = {"get_sample_values", "get_table_stats"}


@dataclass(frozen=True)
class ResolvedSource:
    name: str
    source_type: str
    adapter: Optional[DuckDBFileAdapter] = None  # None = legacy
    llm_data_policy: str = FULL  # Phase 4.5: what of this source's data may reach an LLM provider
    llm_providers: Optional[frozenset] = None  # llm_provider_allowlist; None = any provider

    @property
    def version(self) -> str:
        """Changes with every verified build — part of the query-cache validity check."""
        return self.adapter.version if self.adapter else self.name

    @property
    def data_as_of(self) -> Optional[Dict[str, Any]]:
        """Freshness of the verified build answers are read from; None = legacy / no manifest."""
        manifest = self.adapter.manifest if self.adapter else None
        if not manifest:
            return None
        return {"period": manifest.get("period"), "built_at": manifest.get("built_at"),
                "build_id": manifest.get("build_id")}

    @property
    def engine(self):
        """SQLAlchemy engine for schema inspection of this source."""
        if self.adapter is None:
            from app.db.session import business_engine
            return business_engine
        return self.adapter.engine


LEGACY_SOURCE = ResolvedSource(name=LEGACY, source_type=LEGACY)

# The caller's scope for the current request, e.g. {"year_month": 202607} — None = unscoped
request_scope: ContextVar[Optional[Dict[str, Any]]] = ContextVar("request_scope", default=None)
# Phase 4a: the request comes from an API key bound to a workspace/allowlist — a legacy context is
# then its main view and nothing else, and a context that doesn't resolve is refused (never the legacy DB)
request_pinned: ContextVar[bool] = ContextVar("request_pinned", default=False)


class ScopeError(ValueError):
    """The scope can't be enforced on this context (undeclared key, bad value) → HTTP 400, never ignored."""


def _literal(value: Any) -> str:
    # Rendered into TEMP view DDL (no bind parameters there): ints and strings only
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ScopeError(f"ค่า scope ต้องเป็นตัวเลขจำนวนเต็มหรือข้อความ: {value!r}")
    if isinstance(value, int):
        return str(value)
    if "\x00" in value:
        raise ScopeError("ค่า scope มีอักขระที่ไม่อนุญาต")
    return "'" + value.replace("'", "''") + "'"


def _predicate(column: str, value: Any) -> str:
    col = '"' + column.replace('"', '""') + '"'
    if isinstance(value, list):
        if not value or len(value) > 1000:
            raise ScopeError("รายการค่า scope ต้องมี 1–1000 ค่า")
        return f"{col} IN ({', '.join(_literal(v) for v in value)})"
    return f"{col} = {_literal(value)}"


def scope_filters(scope: Dict[str, Any], mapping: Dict[str, str], table_columns: Dict[str, Optional[List[str]]]) -> Dict[str, str]:
    """{table: predicate} for every table carrying all the scoped columns.

    mapping: scope key → column (schema_contexts.scope_columns); table_columns: table →
    its columns, or None to trust the mapping (legacy main view). A table missing a scoped
    column is left out — under the scope it can't be queried at all.
    """
    unknown = sorted(set(scope) - set(mapping))
    if unknown:
        raise ScopeError(f"scope ไม่รู้จัก {unknown} — context นี้รองรับ {sorted(mapping) or 'ไม่มี'}")
    where = " AND ".join(_predicate(mapping[key], scope[key]) for key in sorted(scope))
    needed = {mapping[key].lower() for key in scope}
    filters = {t: where for t, cols in table_columns.items()
               if cols is None or needed <= {c.lower() for c in cols}}
    if not filters:
        raise ScopeError(f"ไม่มีตารางใดของ context นี้ที่มีคอลัมน์ {sorted(needed)} ให้บังคับ scope")
    return filters


def _scope_note(scope: Dict[str, Any], tables: List[str], main_view: str) -> str:
    """System-prompt note: the LLM must know the rows are pre-filtered and which tables exist —
    and, when the scope can't filter the context's main view, that it must use another table."""
    note = (
        "\n\n**ขอบเขตข้อมูล (scope) ที่ผู้เรียกกำหนด — บังคับที่ระบบแล้ว:** "
        + ", ".join(f"{k} = {v}" for k, v in sorted(scope.items()))
        + "\n- ข้อมูลทุกแถวที่ query ได้ถูกกรองตาม scope นี้แล้ว — \"ล่าสุด\" / \"ทั้งหมด\" / \"หน่วยงานเรา\" หมายถึงภายใน scope นี้"
        + f"\n- query ได้เฉพาะตาราง: {', '.join(sorted(tables))} (อ้างชื่อตรง ๆ ห้ามมี schema นำหน้า)"
    )
    if main_view and main_view.lower() not in {t.lower() for t in tables}:
        note += (f"\n- ⚠️ ตารางหลัก {main_view} และตารางอื่นนอกรายการข้างบน **ใช้ไม่ได้** ภายใต้ scope นี้ "
                 f"(ระบบจะปฏิเสธ) — ต้องเลือกตารางจากรายการข้างบนแทน แม้คำถามจะไม่ได้ระบุ; "
                 f"ถ้าคำถามต้องใช้ข้อมูลนอก scope ให้ตอบว่าอยู่นอกขอบเขตข้อมูลที่ได้รับสิทธิ์")
    return note


def registered_tables(config_engine=None) -> Dict[str, Dict[str, Any]]:
    """{table: {"context", "columns"}} of every active file source (Phase 4d): whoever inspects a
    table by name — admin schema browser, onboarding, brain DDL — asks here first, because the legacy
    business DB still holds F10's imported copy under the same names. {} = registry not migrated."""
    if config_engine is None:
        from app.db.session import config_engine
    try:
        with config_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT st.table_name, st.columns, sc.name FROM source_tables st "
                "JOIN data_sources ds ON ds.id = st.source_id AND ds.is_active = 1 AND ds.source_type = :t "
                "JOIN schema_contexts sc ON sc.source_id = ds.id "
                "WHERE st.is_active = 1 ORDER BY sc.is_active DESC, sc.id"), {"t": DUCKDB_FILE}).all()
    except (OperationalError, ProgrammingError) as exc:
        if _not_migrated(exc):
            return {}
        raise
    tables: Dict[str, Dict[str, Any]] = {}
    for table, columns, context in rows:
        tables.setdefault(table, {"context": context, "columns": json.loads(columns)})
    return tables


def _row_policy(row) -> Dict[str, Any]:
    # a registry migrated before Phase 4.5 has no policy columns = nobody could have restricted anything;
    # a column that is there but NULL / unknown = schema_only (normalize), a broken allowlist = no provider
    if "llm_data_policy" not in row:
        return {}
    return {"llm_data_policy": normalize(row["llm_data_policy"]),
            "llm_providers": parse_allowlist(row["llm_provider_allowlist"])}


def policy_for_table(table_name: Optional[str], config_engine=None) -> str:
    """Policy of the source a table belongs to — for whoever reads values outside a query request
    (onboarding, admin schema pages): a registered file-source table, else the legacy business DB."""
    if config_engine is None:
        from app.db.session import config_engine
    try:
        with config_engine.connect() as conn:
            row = conn.execute(text(
                "SELECT ds.llm_data_policy FROM source_tables st "
                "JOIN data_sources ds ON ds.id = st.source_id AND ds.is_active = 1 "
                "WHERE st.table_name = :t AND st.is_active = 1"), {"t": table_name or ""}).first()
            if row is None:
                row = conn.execute(text("SELECT llm_data_policy FROM data_sources WHERE name = :n"), {"n": LEGACY}).first()
    except (OperationalError, ProgrammingError) as exc:
        return FULL if _not_migrated(exc) else SCHEMA_ONLY
    return normalize(row[0]) if row else FULL


def _not_migrated(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "no such" in msg or "does not exist" in msg


class SourceResolver:
    """Resolves a context to its source; caches one adapter per source definition.

    The cache key is a fingerprint of (name, root, tables), so re-registering a
    source takes effect on the next request without a restart.
    """

    def __init__(self, config_engine=None, cache_dir: Optional[str] = None):
        self._config_engine = config_engine
        self._cache_dir = cache_dir
        self._adapters: Dict[str, tuple] = {}  # source name → (fingerprint, adapter)
        self._lock = threading.Lock()

    def _engine(self):
        if self._config_engine is None:
            from app.db.session import config_engine
            return config_engine
        return self._config_engine

    def for_context(self, context_name: Optional[str]) -> ResolvedSource:
        source = self._resolve(context_name)
        scope = request_scope.get()
        if request_pinned.get():
            self._require_context(context_name)
            if not scope and source.adapter is None:
                return self._pinned(context_name, source)
        return self._scoped(context_name, source, scope) if scope else source

    def _main_view(self, context_name: Optional[str]) -> Optional[str]:
        """main_view of the active context with exactly this stored name (no loose matching here)."""
        with self._engine().connect() as conn:
            return conn.execute(text("SELECT main_view FROM schema_contexts WHERE name = :n AND is_active = 1"),
                                {"n": context_name or ""}).scalar()

    def _require_context(self, context_name: Optional[str]) -> None:
        from app.services.workspaces import ContextNotAllowed

        try:
            found = self._main_view(context_name)
        except (OperationalError, ProgrammingError):
            found = None
        if not found:  # unknown, deactivated since the allowlist was read, or loosely spelled
            raise ContextNotAllowed(f"ไม่พบ context '{context_name}' สำหรับ API key นี้")

    def _pinned(self, context_name: str, source: ResolvedSource) -> ResolvedSource:
        """Legacy business DB for a restricted caller: the Phase 3 machinery with a filter that keeps
        every row — the main view is readable, every other table is shadowed empty and refused by the gate."""
        from app.db.session import business_engine

        main_view = self._main_view(context_name)
        note = (f"\n\n**API key นี้ query ได้เฉพาะตาราง {main_view}** (อ้างชื่อตรง ๆ ห้ามมี schema นำหน้า) — "
                f"ตาราง/view อื่นระบบจะปฏิเสธ; ถ้าคำถามต้องใช้ข้อมูลอื่น ให้ตอบว่าอยู่นอกสิทธิ์ของ key นี้")
        return replace(source, adapter=ScopedSQLite(business_engine.url.database, {main_view: "1"}, note))

    def _context_row(self, conn, context_name: str, select: str):
        # Same row, same order as context_store.get_context_info (exact, '_'→' ',
        # ' '→'_', active only) — the prompt and the data must come from one context
        for name in dict.fromkeys([context_name, context_name.replace("_", " "), context_name.replace(" ", "_")]):
            row = conn.execute(text(f"{select} WHERE sc.name = :ctx AND sc.is_active = 1"), {"ctx": name}).mappings().first()
            if row is not None:
                return row
        return None

    def _scoped(self, context_name: Optional[str], source: ResolvedSource, scope: Dict[str, Any]) -> ResolvedSource:
        if not isinstance(scope, dict):
            raise ScopeError("scope ต้องเป็น object เช่น {\"year_month\": 202607}")
        try:
            with self._engine().connect() as conn:
                row = self._context_row(conn, context_name or "", "SELECT sc.main_view, sc.scope_columns FROM schema_contexts sc")
        except (OperationalError, ProgrammingError) as exc:
            if _not_migrated(exc):
                raise ScopeError("config DB ยังไม่รองรับ scope — รัน scripts/migrate_data_sources.py") from exc
            raise
        if row is None:
            raise ScopeError(f"ไม่พบ context '{context_name}' สำหรับบังคับ scope")
        try:
            mapping = json.loads(row["scope_columns"] or "{}")
        except ValueError as exc:
            raise ScopeError(f"scope_columns ของ context '{context_name}' ไม่ใช่ JSON") from exc
        if not isinstance(mapping, dict) or not all(isinstance(v, str) for v in mapping.values()):
            raise ScopeError(f"scope_columns ของ context '{context_name}' ต้องเป็น {{key: column}}")
        if source.adapter is None:  # legacy business DB: the context's main view is the only table
            from app.db.session import business_engine
            filters = scope_filters(scope, mapping, {row["main_view"]: None})
            adapter = ScopedSQLite(business_engine.url.database, filters, _scope_note(scope, list(filters), row["main_view"]))
        else:
            filters = scope_filters(scope, mapping, source.adapter.view_columns)
            adapter = ScopedDuckDB(source.adapter, filters, _scope_note(scope, list(filters), row["main_view"]))
        return replace(source, adapter=adapter)

    def _resolve(self, context_name: Optional[str]) -> ResolvedSource:
        if not context_name:
            return LEGACY_SOURCE
        try:
            with self._engine().connect() as conn:
                row = self._context_row(conn, context_name, (
                    "SELECT sc.source_id, ds.* "
                    "FROM schema_contexts sc LEFT JOIN data_sources ds ON ds.id = sc.source_id"))
                if row is None or row["source_id"] is None:
                    return LEGACY_SOURCE
                if row["id"] is None:
                    raise ValueError(f"Context '{context_name}' points to missing data source id {row['source_id']}")
                policy = _row_policy(row)
                if row["source_type"] == LEGACY:
                    legacy = replace(LEGACY_SOURCE, **policy)
                    return LEGACY_SOURCE if legacy == LEGACY_SOURCE else legacy
                tables = [dict(r) for r in conn.execute(text(
                    "SELECT table_name, file_name, columns FROM source_tables "
                    "WHERE source_id = :sid AND is_active = 1 ORDER BY table_name"
                ), {"sid": row["id"]}).mappings()]
        except (OperationalError, ProgrammingError) as exc:
            if _not_migrated(exc):  # registry not migrated yet → everything is legacy
                return LEGACY_SOURCE
            raise

        if row["source_type"] != DUCKDB_FILE:
            raise ValueError(f"Unsupported source_type '{row['source_type']}' (context '{context_name}')")
        if not row["is_active"]:
            raise ValueError(f"Data source '{row['name']}' is inactive (context '{context_name}')")
        if not tables:
            raise ValueError(f"Data source '{row['name']}' has no registered tables")
        for t in tables:
            t["columns"] = json.loads(t["columns"])
        # .get: a registry migrated before manifest_file existed simply has no manifest check
        adapter = self._adapter(row["name"], row["root_path"], tables, row.get("manifest_file"))
        if row.get("contract_file"):  # Phase 2: knowledge follows the contract (one stat per request)
            from app.services.datafeed_knowledge import ensure_current
            ensure_current(self._engine(), row, adapter.manifest)
        return ResolvedSource(row["name"], DUCKDB_FILE, adapter, **policy)

    def _adapter(self, name: str, root: str, tables: List[Dict], manifest_file: Optional[str]) -> DuckDBFileAdapter:
        # realpath in the key: DuckDB pins allowed_paths to the real files at SET time, so a
        # re-pointed symlinked root (latest/ → 202609/) needs a new adapter, not the old lock
        key = [name, root, os.path.realpath(root) if root else None, tables, manifest_file]
        fp = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]
        with self._lock:
            cached = self._adapters.get(name)
            # is_current: an in-place publish rewrote the verified files → verify the new build
            if cached and cached[0] == fp and cached[1].is_current():
                return cached[1]
            cache_dir = self._cache_dir
            if cache_dir is None:
                from app.config import settings
                cache_dir = settings.DATA_SOURCE_CACHE_DIR
            # raises SourceUnavailable while a publish is in progress — never falls back
            adapter = DuckDBFileAdapter(f"{name}-{fp}", root, tables, cache_dir, manifest_file)
            # One adapter per source: a superseded one is dropped (not closed — in-flight
            # requests may still hold it; its DuckDB instance is freed once they finish).
            # Its view file can go now: an open file stays readable after unlink.
            if cached and cached[1].db_path != adapter.db_path:
                try:
                    os.remove(cached[1].db_path)
                except OSError:
                    pass
            self._adapters[name] = (fp, adapter)
            logger.info(f"Data source '{name}' ready: {len(tables)} views over {adapter.root}")
            return adapter


source_resolver = SourceResolver()


class SourceBoundMCPClient:
    """The request's MCP client, bound to a file source.

    execute_query runs in-process on the source's DuckDB adapter — always through
    the F4 validator, whatever validate_first the caller passed. Data tools with no
    file-source implementation fail closed; everything else (validate_sql,
    confidence summary, ...) goes to the real MCP servers unchanged.
    """

    def __init__(self, inner, source: ResolvedSource):
        self._inner = inner
        self._source = source

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "execute_query":
            result = await asyncio.to_thread(
                execute_select, self._source.adapter,
                arguments.get("sql", ""), int(arguments.get("limit", 100)), True,
            )
            return json.dumps(result, ensure_ascii=False, default=str)
        if tool_name in _LEGACY_ONLY_DATA_TOOLS:
            return json.dumps({
                "success": False,
                "error": f"{tool_name} ยังไม่รองรับ file source '{self._source.name}' — ใช้ execute_query แทน",
            }, ensure_ascii=False)
        return await self._inner.call_tool(tool_name, arguments)
