"""Create the config DB's contract metrics table (Plan 8.1 provenance); safe to run repeatedly."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text


def migrate(config_engine=None):
    if config_engine is None:
        from app.db.session import config_engine
    with config_engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS schema_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_name TEXT NOT NULL,
            metric_id TEXT NOT NULL,
            name_th TEXT NOT NULL,
            synonyms TEXT,
            extends TEXT,
            dataset TEXT,
            period TEXT,
            dimensions TEXT,
            terms TEXT,
            expr TEXT NOT NULL,
            official_scope TEXT,
            official_total TEXT,
            reference TEXT,
            unit TEXT,
            note_th TEXT,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            confidence REAL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )"""))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_schema_metrics_context_metric "
                          "ON schema_metrics (context_name, metric_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_schema_metrics_context_name "
                          "ON schema_metrics (context_name)"))
    print("Ensured schema_metrics and its context/metric unique index and context index exist.")
    print("Migration complete (idempotent).")


if __name__ == "__main__":
    migrate()
