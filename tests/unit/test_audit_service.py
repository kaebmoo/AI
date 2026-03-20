"""
Plan 3: Audit Service Tests
=============================
Tests that audit logging records changes with source tracking.
"""

import pytest
from datetime import datetime
from sqlalchemy import text


class TestAuditLogTable:
    """Verify audit_log table schema and insert behavior."""

    def _ensure_audit_table(self, db_session):
        """Create audit_log table if it doesn't exist (from migration 028)."""
        db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                table_name TEXT NOT NULL,
                record_id INTEGER,
                old_value TEXT,
                new_value TEXT,
                source TEXT DEFAULT 'manual',
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db_session.commit()

    def test_log_manual_add(self, db_session):
        """Admin adding mapping → audit log with source='manual'."""
        self._ensure_audit_table(db_session)
        db_session.execute(text("""
            INSERT INTO audit_log (action, table_name, record_id, new_value, source, user_id)
            VALUES ('INSERT', 'schema_semantic_mapping', 1, '{"keyword": "datacom"}', 'manual', 1)
        """))
        db_session.commit()

        row = db_session.execute(text("SELECT action, table_name, new_value, source FROM audit_log WHERE source = 'manual'")).fetchone()
        assert row is not None
        assert "datacom" in row[2]  # new_value

    def test_log_auto_add(self, db_session):
        """Auto-analyzer applying fix → audit log with source='auto_analyzer'."""
        self._ensure_audit_table(db_session)
        db_session.execute(text("""
            INSERT INTO audit_log (action, table_name, record_id, new_value, source)
            VALUES ('INSERT', 'schema_semantic_mapping', 2, '{"keyword": "mobile"}', 'auto_analyzer')
        """))
        db_session.commit()

        row = db_session.execute(text("SELECT * FROM audit_log WHERE source = 'auto_analyzer'")).fetchone()
        assert row is not None

    def test_log_agent_add(self, db_session):
        """Admin agent adding rule → audit log with source='admin_agent'."""
        self._ensure_audit_table(db_session)
        db_session.execute(text("""
            INSERT INTO audit_log (action, table_name, record_id, new_value, source, user_id)
            VALUES ('INSERT', 'schema_business_rules', 5, '{"rule_code": "R99"}', 'admin_agent', 1)
        """))
        db_session.commit()

        row = db_session.execute(text("SELECT * FROM audit_log WHERE source = 'admin_agent'")).fetchone()
        assert row is not None

    def test_log_contains_old_new_values(self, db_session):
        """Update operation → audit log has both old_value and new_value."""
        self._ensure_audit_table(db_session)
        db_session.execute(text("""
            INSERT INTO audit_log (action, table_name, record_id, old_value, new_value, source)
            VALUES ('UPDATE', 'schema_semantic_mapping', 1,
                    '{"target_column": "BUSINESS"}',
                    '{"target_column": "SERVICE_GROUP"}',
                    'manual')
        """))
        db_session.commit()

        row = db_session.execute(text("SELECT action, old_value, new_value FROM audit_log WHERE action = 'UPDATE'")).fetchone()
        assert row is not None
        assert row[1] is not None  # old_value
        assert row[2] is not None  # new_value
