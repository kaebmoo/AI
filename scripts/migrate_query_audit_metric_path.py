"""Add the app DB's query audit metric path; safe to run repeatedly."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect

from app.services.query_audit import ensure_table


def migrate(app_engine=None):
    if app_engine is None:
        from app.db.session import engine as app_engine
    inspector = inspect(app_engine)
    present = inspector.has_table("query_audit") and any(
        c["name"] == "metric_path" for c in inspector.get_columns("query_audit")
    )
    ensure_table(app_engine)
    print("query_audit.metric_path already present." if present else "Added query_audit.metric_path.")
    print("Migration complete (idempotent).")


if __name__ == "__main__":
    migrate()
