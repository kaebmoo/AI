"""
Migration script (Plan 7 Phase 4a): workspaces + scoped API keys.

config DB: workspaces, schema_contexts.workspace_id — every existing context → 'default'
app DB:    api_keys.workspace_id, api_keys.allowed_contexts (JSON list) — NULL/NULL = unrestricted,
           so every key issued before this migration behaves as before

Safe to run multiple times (idempotent). The app adds the api_keys columns itself on first key
lookup (every lookup would fail without them); the config side needs this script.

Usage:
    python scripts/migrate_workspaces.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

DEFAULT_WORKSPACE = "default"


def migrate_config(config_engine) -> None:
    with config_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT,
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("INSERT INTO workspaces (name, display_name) VALUES (:n, 'Default') ON CONFLICT(name) DO NOTHING"),
                     {"n": DEFAULT_WORKSPACE})
    if "workspace_id" not in {c["name"] for c in inspect(config_engine).get_columns("schema_contexts")}:
        with config_engine.begin() as conn:
            conn.execute(text("ALTER TABLE schema_contexts ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id)"))
        print("Added schema_contexts.workspace_id")
    with config_engine.begin() as conn:
        bound = conn.execute(text(
            "UPDATE schema_contexts SET workspace_id = (SELECT id FROM workspaces WHERE name = :n) WHERE workspace_id IS NULL"
        ), {"n": DEFAULT_WORKSPACE}).rowcount
    print(f"Bound {bound} context(s) to workspace '{DEFAULT_WORKSPACE}'")


def migrate_app(app_engine) -> None:
    from app.services.workspaces import ensure_api_key_columns

    ensure_api_key_columns(app_engine)  # the app also does this on first key lookup


def migrate(config_engine=None, app_engine=None) -> None:
    if config_engine is None or app_engine is None:
        from app.db.session import config_engine as default_config, engine as default_app
        config_engine, app_engine = config_engine or default_config, app_engine or default_app
    migrate_config(config_engine)
    migrate_app(app_engine)
    print("Migration complete (idempotent).")


if __name__ == "__main__":
    migrate()
