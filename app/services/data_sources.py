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
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.services.database_adapter import DuckDBFileAdapter, execute_select

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

    @property
    def version(self) -> str:
        """Changes with every verified build — part of the query-cache validity check."""
        return self.adapter.version if self.adapter else self.name

    @property
    def engine(self):
        """SQLAlchemy engine for schema inspection of this source."""
        if self.adapter is None:
            from app.db.session import business_engine
            return business_engine
        return self.adapter.engine


LEGACY_SOURCE = ResolvedSource(name=LEGACY, source_type=LEGACY)


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
        if not context_name:
            return LEGACY_SOURCE
        try:
            with self._engine().connect() as conn:
                row = None
                # Same row, same order as context_store.get_context_info (exact, '_'→' ',
                # ' '→'_', active only) — the prompt and the data must come from one context
                for name in dict.fromkeys([context_name, context_name.replace("_", " "),
                                           context_name.replace(" ", "_")]):
                    row = conn.execute(text(
                        "SELECT sc.source_id, ds.* "
                        "FROM schema_contexts sc LEFT JOIN data_sources ds ON ds.id = sc.source_id "
                        "WHERE sc.name = :ctx AND sc.is_active = 1"
                    ), {"ctx": name}).mappings().first()
                    if row is not None:
                        break
                if row is None or row["source_id"] is None:
                    return LEGACY_SOURCE
                if row["id"] is None:
                    raise ValueError(f"Context '{context_name}' points to missing data source id {row['source_id']}")
                if row["source_type"] == LEGACY:
                    return LEGACY_SOURCE
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
        return ResolvedSource(row["name"], DUCKDB_FILE, adapter)

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
