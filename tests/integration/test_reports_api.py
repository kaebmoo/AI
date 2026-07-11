"""F6: reports API — full flow (inline mode), ownership, expiry."""

import sqlite3
from datetime import datetime, timedelta

import pytest
from unittest.mock import patch

from app.models.chat import ChatHistory
from app.models.session import UserSession
from app.services import report_service


@pytest.fixture
def reports_client(client, test_user, db_session, tmp_path, monkeypatch):
    """Authenticated client + temp business DB + inline export mode."""
    session = UserSession(
        user_id=test_user.id,
        session_token="reports_test_token",
        platform="web",
        expires_at=datetime.utcnow() + timedelta(hours=24),
        last_activity=datetime.utcnow(),
    )
    db_session.add(session)
    db_session.commit()
    client.headers["X-Session-Token"] = "reports_test_token"

    db_path = tmp_path / "biz.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE revenue (id INTEGER, val REAL)")
    conn.executemany("INSERT INTO revenue VALUES (?, ?)", [(i, i * 2.0) for i in range(10)])
    conn.commit()
    conn.close()

    from app.config import settings
    monkeypatch.setattr(settings, "BUSINESS_DB_PATH", str(db_path))
    monkeypatch.setattr(report_service, "EXPORT_DIR", tmp_path / "exports")

    import app.api.v1.reports as reports_module
    monkeypatch.setattr(reports_module, "_celery_available", False)  # force inline
    return client


@pytest.fixture
def chat_entry(db_session, test_user):
    chat = ChatHistory(
        user_id=test_user.id, question="รายได้",
        generated_sql="SELECT * FROM revenue", ai_response="...",
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    return chat


class TestReportsFlow:
    def test_full_flow_post_get_download(self, reports_client, chat_entry):
        resp = reports_client.post("/api/v1/reports/", json={"chat_history_id": chat_entry.id})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "done"  # inline mode completes synchronously
        export_id = body["id"]

        resp = reports_client.get(f"/api/v1/reports/{export_id}")
        assert resp.status_code == 200
        assert resp.json()["row_count"] == 10

        resp = reports_client.get(f"/api/v1/reports/{export_id}/download")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
        assert resp.content[:2] == b"PK"  # xlsx = zip

        resp = reports_client.get("/api/v1/reports/")
        assert any(e["id"] == export_id for e in resp.json())

    def test_other_users_export_forbidden(self, reports_client, chat_entry, db_session, admin_user):
        from app.models.report_export import ReportExport
        other_export = ReportExport(user_id=admin_user.id, question="x", sql_text="SELECT 1", status="done")
        db_session.add(other_export)
        db_session.commit()

        resp = reports_client.get(f"/api/v1/reports/{other_export.id}")
        assert resp.status_code == 403

    def test_expired_download_410(self, reports_client, chat_entry, db_session):
        resp = reports_client.post("/api/v1/reports/", json={"chat_history_id": chat_entry.id})
        export_id = resp.json()["id"]

        from app.core.time_utils import utcnow
        from app.models.report_export import ReportExport
        export = db_session.query(ReportExport).filter(ReportExport.id == export_id).first()
        export.expires_at = utcnow() - timedelta(hours=1)
        db_session.commit()

        resp = reports_client.get(f"/api/v1/reports/{export_id}/download")
        assert resp.status_code == 410

    def test_requires_auth(self, client):
        resp = client.post("/api/v1/reports/", json={"chat_history_id": 1})
        assert resp.status_code == 401

    def test_per_user_hourly_rate_limit(self, reports_client, chat_entry, db_session, test_user):
        """P2 review fix: limit is per USER (DB count), not per IP."""
        from app.core.time_utils import utcnow
        from app.models.report_export import ReportExport
        import app.api.v1.reports as reports_module

        for _ in range(reports_module.EXPORTS_PER_HOUR):
            db_session.add(ReportExport(user_id=test_user.id, question="x", sql_text="SELECT 1",
                                        status="done", created_at=utcnow()))
        db_session.commit()

        resp = reports_client.post("/api/v1/reports/", json={"chat_history_id": chat_entry.id})
        assert resp.status_code == 429
