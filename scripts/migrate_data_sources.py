"""
Migration script (Plan 7 Phase 1): data source registry in the config DB.

- data_sources   — where a context's data lives ('legacy' = BUSINESS_DB_PATH, 'duckdb_file' = files under root_path)
- source_tables  — per-source allowlist: view name → file (relative to root) + column types
- schema_contexts.source_id — every existing context is bound to 'legacy' → behavior unchanged

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

    ds_columns = {c["name"] for c in inspect(config_engine).get_columns("data_sources")}
    if "manifest_file" not in ds_columns:  # registries created before the manifest check
        with config_engine.begin() as conn:
            conn.execute(text("ALTER TABLE data_sources ADD COLUMN manifest_file TEXT"))
        print("Added data_sources.manifest_file")

    existing = {c["name"] for c in inspect(config_engine).get_columns("schema_contexts")}
    with config_engine.begin() as conn:
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
