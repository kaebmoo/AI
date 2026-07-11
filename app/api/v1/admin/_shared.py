"""Shared helpers for admin API modules."""

import os
from typing import Iterable

from sqlalchemy.orm import Session

from app.config import settings
from app.models.schema_models import SchemaMetadata
from app.services.schema_service import SchemaService
from app.core.time_utils import utcnow


def ensure_metadata_rows(db: Session, table_name: str, column_names: Iterable[str], service: SchemaService):
    """Ensure schema_metadata rows exist for all columns in a table."""
    existing = {
        row.column_name
        for row in db.query(SchemaMetadata.column_name).filter(
            SchemaMetadata.table_name == table_name
        ).all()
    }

    col_types = {}
    try:
        for col in service.get_table_info(table_name):
            col_types[col["name"]] = col.get("type", "TEXT")
    except Exception:
        pass

    for col_name in column_names:
        if col_name not in existing:
            db.add(
                SchemaMetadata(
                    table_name=table_name,
                    column_name=col_name,
                    data_type=col_types.get(col_name, "TEXT"),
                )
            )
    db.flush()


def get_business_db_path() -> str:
    """Get business DB path. Priority: BUSINESS_DB_PATH > DATABASE_URL > fallback."""
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    if getattr(settings, "BUSINESS_DB_PATH", None):
        db_path = settings.BUSINESS_DB_PATH
        if not os.path.isabs(db_path):
            db_path = os.path.join(project_root, db_path)
        return db_path

    db_url = str(getattr(settings, "DATABASE_URL", ""))
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            db_path = os.path.join(project_root, db_path)
        return db_path

    return os.path.join(project_root, "nt_fi_report.sqlite")


def mark_brain_dirty():
    """Record that brain-relevant config has changed.

    Called after mutations to contexts, mappings, rules, golden examples,
    schema metadata, hierarchy, vanna docs, or onboarding apply.
    Admin sees needs_sync indicator until they trigger Sync Brain.
    """
    try:
        from datetime import datetime
        from app.services.admin_config_service import AdminConfigService
        svc = AdminConfigService()
        try:
            svc.set_config(
                'last_brain_relevant_change_at',
                utcnow().isoformat(),
                config_type='system',
                category='system',
            )
        finally:
            svc.close()
    except Exception:
        pass
