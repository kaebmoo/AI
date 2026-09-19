"""
Migration script (Plan 7 Phase 1): data source registry in the config DB.

- data_sources   — where a context's data lives ('legacy' = BUSINESS_DB_PATH, 'duckdb_file' = files under root_path)
- source_tables  — per-source allowlist: view name → file (relative to root) + column types
- schema_contexts.source_id — every existing context is bound to 'legacy' → behavior unchanged
- schema_contexts.scope_columns (Phase 3) — JSON {"scope key": "column"}; NULL = the context accepts no scope

Safe to run multiple times (idempotent).

Usage:
    python scripts/migrate_data_sources.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

LEGACY = "legacy"


def migrate(config_engine=None):
    if config_engine is None:
        from app.db.session import config_engine
    with config_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS data_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,          -- 'legacy' | 'duckdb_file'
                root_path TEXT,                     -- duckdb_file: directory the files live in
                manifest_file TEXT,                 -- e.g. manifest.json: verified per build (reconcile + sha256)
                contract_file TEXT,                 -- DataFeed contract yaml the context knowledge is generated from
                knowledge_sha TEXT,                 -- contract sha + schema_version of the last knowledge sync
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS source_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES data_sources(id),
                table_name TEXT NOT NULL,           -- view name the LLM queries
                file_name TEXT NOT NULL,            -- relative to data_sources.root_path
                columns TEXT NOT NULL,              -- JSON [{"name": ..., "type": "BIGINT|DOUBLE|VARCHAR|..."}]
                sha256 TEXT,                        -- from manifest at registration (informational)
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (source_id, table_name)
            )
        """))
        conn.execute(text(
            "INSERT INTO data_sources (name, source_type, description) "
            "VALUES (:name, 'legacy', 'business DB เดิม (BUSINESS_DB_PATH)') ON CONFLICT(name) DO NOTHING"
        ), {"name": LEGACY})

    # Columns added after the first registries were created
    ds_columns = {c["name"] for c in inspect(config_engine).get_columns("data_sources")}
    for column in ("manifest_file",   # verified per build (publish race)
                   "contract_file",   # Phase 2: knowledge re-syncs when this file changes
                   "knowledge_sha"):  # Phase 2: contract sha + schema_version the knowledge came from
        if column not in ds_columns:
            with config_engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE data_sources ADD COLUMN {column} TEXT"))
            print(f"Added data_sources.{column}")
    # Phase 4.5: what of this source's data may reach an LLM provider. DEFAULT 'full' fills every
    # existing row and every later INSERT (behaviour unchanged); NULL / unknown = schema_only at read time.
    if "llm_data_policy" not in ds_columns:
        with config_engine.begin() as conn:
            conn.execute(text("ALTER TABLE data_sources ADD COLUMN llm_data_policy TEXT DEFAULT 'full'"))
            conn.execute(text("ALTER TABLE data_sources ADD COLUMN llm_provider_allowlist TEXT"))  # JSON list; NULL = any
        print("Added data_sources.llm_data_policy, llm_provider_allowlist")

    existing = {c["name"] for c in inspect(config_engine).get_columns("schema_contexts")}
    with config_engine.begin() as conn:
        if "scope_columns" not in existing:  # Phase 3: {"scope key": "column"} the caller's scope may filter on
            conn.execute(text("ALTER TABLE schema_contexts ADD COLUMN scope_columns TEXT"))
            print("Added schema_contexts.scope_columns")
        if "source_id" not in existing:
            conn.execute(text("ALTER TABLE schema_contexts ADD COLUMN source_id INTEGER REFERENCES data_sources(id)"))
            print("Added schema_contexts.source_id")
        else:
            print("Column schema_contexts.source_id already exists, skipping.")
        bound = conn.execute(text(
            "UPDATE schema_contexts SET source_id = (SELECT id FROM data_sources WHERE name = :name) "
            "WHERE source_id IS NULL"
        ), {"name": LEGACY}).rowcount
        print(f"Bound {bound} context(s) to source '{LEGACY}'")
    print("Migration complete (idempotent).")


if __name__ == "__main__":
    migrate()
