"""
Migration script (F12): Add render_meta / result_data columns to chat_history.

These columns store the visualization/chart/table payload the client actually
saw (post-_format_response enrichment) so opening a conversation later can
restore the chart/table/pivot instead of showing text only.

Safe to run multiple times (idempotent).

Usage:
    python scripts/migrate_chat_render_payload.py
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from app.db.session import engine


def migrate():
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("chat_history")}
    with engine.begin() as conn:
        if "render_meta" not in existing:
            conn.execute(text("ALTER TABLE chat_history ADD COLUMN render_meta TEXT"))
            print("Added chat_history.render_meta")
        else:
            print("Column chat_history.render_meta already exists, skipping.")
        if "result_data" not in existing:
            conn.execute(text("ALTER TABLE chat_history ADD COLUMN result_data TEXT"))
            print("Added chat_history.result_data")
        else:
            print("Column chat_history.result_data already exists, skipping.")
    print("Migration complete (idempotent).")


if __name__ == "__main__":
    migrate()
