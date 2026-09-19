"""
Plan 3: Audit Service Tests
=============================
AuditService against the real DDL of migration 028 (config_audit_log) — a home-made
table here once hid that the service wrote to a table that didn't exist.
"""

import json
import logging
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.audit_service import AuditService

MIGRATION = Path(__file__).resolve().parents[2] / "database" / "migrations" / "028_audit_log.sql"


@pytest.fixture
def audit_db(tmp_path):
    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.close()
    session = sessionmaker(bind=create_engine(f"sqlite:///{path}"))()
    yield session
    session.close()


# (action, source) exactly as the callers pass them: admin tools, scheduler auto-apply
@pytest.mark.parametrize("action,source,stored", [
    ("INSERT", "admin_agent", "create"),
    ("INSERT", "auto_analyzer", "create"),
    ("UPDATE", "manual", "update"),
    ("DELETE", "api", "delete"),
    ("toggle", "onboarding", "toggle"),
])
def test_log_change_lands_in_config_audit_log(audit_db, action, source, stored):
    AuditService(audit_db).log_change(
        action=action, table_name="schema_semantic_mapping", record_id=1,
        old_value={"target_column": "BUSINESS"}, new_value={"keyword": "ดาต้าคอม"},
        source=source, user_id=7,
    )
    rows = AuditService(audit_db).get_recent(source=source)
    assert len(rows) == 1
    row = rows[0]
    assert (row["action"], row["source"], row["created_by"], row["record_id"]) == (stored, source, 7, 1)
    assert json.loads(row["new_value"]) == {"keyword": "ดาต้าคอม"}
    assert json.loads(row["old_value"]) == {"target_column": "BUSINESS"}


def test_get_recent_filters_by_table(audit_db):
    audit = AuditService(audit_db)
    audit.log_change(action="INSERT", table_name="golden_examples", record_id=1)
    audit.log_change(action="INSERT", table_name="schema_business_rules", record_id=2)
    assert [r["record_id"] for r in audit.get_recent(table_name="schema_business_rules")] == [2]
    assert len(audit.get_recent()) == 2


@pytest.mark.parametrize("action,source", [("SELECT", "manual"), ("INSERT", "not_a_source")])
def test_unwritable_audit_is_an_error_not_a_silent_loss(audit_db, caplog, action, source):
    with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
        AuditService(audit_db).log_change(action=action, table_name="schema_semantic_mapping", source=source)
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
    assert AuditService(audit_db).get_recent() == []


def test_missing_table_is_an_error(tmp_path, caplog):
    session = sessionmaker(bind=create_engine(f"sqlite:///{tmp_path / 'empty.db'}"))()
    with caplog.at_level(logging.ERROR, logger="app.services.audit_service"):
        AuditService(session).log_change(action="INSERT", table_name="x")
    session.close()
    assert caplog.records and caplog.records[0].levelno == logging.ERROR
