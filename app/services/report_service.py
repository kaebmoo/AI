"""
Report Export Service (PLAN F6)
================================
Exports re-run the saved generated_sql against the business DB — NEVER from
session/cached data (which is truncated at 1,000 rows).
"""

import logging
import os
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.time_utils import utcnow
from app.models.chat import ChatHistory
from app.models.report_export import ReportExport
from app.services.validation_service import ValidationService

logger = logging.getLogger(__name__)

EXPORT_DIR = Path("data/exports")
DEFAULT_MAX_ROWS = 100_000
DEFAULT_RETENTION_DAYS = 7


def _config_int(key: str, default: int) -> int:
    """admin_config → default (3-tier, no .env key defined for these)."""
    try:
        from app.services.admin_config_service import AdminConfigService
        svc = AdminConfigService()
        try:
            val = svc.get_config(key)
            return int(val) if val else default
        finally:
            svc.close()
    except Exception:
        return default


class ExportError(Exception):
    """User-facing export error (ownership, validation)."""


def create_export(db: Session, user, chat_history_id: int) -> ReportExport:
    """Validate ownership + SQL, create a pending export record."""
    chat = db.query(ChatHistory).filter(ChatHistory.id == chat_history_id).first()
    if not chat:
        raise ExportError("ไม่พบประวัติคำถามนี้")
    is_admin = getattr(user, "role", "") == "admin"
    if chat.user_id != user.id and not is_admin:
        raise ExportError("ไม่มีสิทธิ์ export คำถามของผู้ใช้อื่น")
    if not (chat.generated_sql or "").strip():
        raise ExportError("คำถามนี้ไม่มี SQL ที่บันทึกไว้")

    validation = ValidationService(db=None).validate_sql(chat.generated_sql)
    if not validation["valid"]:
        raise ExportError(f"SQL ไม่ผ่านการตรวจสอบ: {validation['issues']}")

    export = ReportExport(
        user_id=user.id,
        chat_history_id=chat.id,
        question=chat.question,
        sql_text=chat.generated_sql,
        status="pending",
    )
    db.add(export)
    db.commit()
    db.refresh(export)

    try:
        from app.services.audit_service import AuditService
        AuditService(db).log_change(
            action="INSERT", table_name="report_exports", record_id=None,
            new_value={"export_id": export.id, "chat_history_id": chat.id},
            source="report_export", user_id=user.id,
        )
    except Exception:
        pass
    return export


def _run_export_sql(sql: str, max_rows: int):
    """Execute export SQL on a read-only business DB connection.

    SQLite: mode=ro at connection level (same enforcement as MCP servers, F4.1).
    Non-SQLite (MSSQL prod): read-only is credential-level — use business_engine.
    """
    # SQLite = a sqlite:// URL or a bare file path (no URL scheme) — never guess
    # from the filename extension (.sqlite3 / extensionless files are valid SQLite)
    bp = settings.BUSINESS_DB_PATH or ""
    is_sqlite = bp.startswith("sqlite") or (bp and "://" not in bp)
    if is_sqlite:
        resolved = Path(bp.replace("sqlite:///", "").replace("sqlite://", "")).resolve()
        conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(max_rows)
            columns = [c[0] for c in cursor.description] if cursor.description else []
            return [dict(zip(columns, r)) for r in rows], columns
        finally:
            conn.close()

    from sqlalchemy import text
    from app.db.session import business_engine
    with business_engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = result.fetchmany(max_rows)
        return [dict(zip(columns, r)) for r in rows], columns


def run_export(export_id: str, db: Session = None) -> None:
    """Run one export synchronously (callable inline or from Celery)."""
    owns_db = db is None
    if owns_db:
        from app.db.session import SessionLocal
        db = SessionLocal()
    try:
        export = db.query(ReportExport).filter(ReportExport.id == export_id).first()
        if not export:
            logger.error(f"Export {export_id} not found")
            return
        export.status = "running"
        db.commit()

        try:
            max_rows = _config_int("export_max_rows", DEFAULT_MAX_ROWS)
            retention_days = _config_int("export_retention_days", DEFAULT_RETENTION_DAYS)

            rows, columns = _run_export_sql(export.sql_text, max_rows + 1)
            truncated = len(rows) > max_rows
            if truncated:
                rows = rows[:max_rows]

            import pandas as pd
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            final_path = EXPORT_DIR / f"{export.id}.xlsx"

            info = pd.DataFrame([
                {"field": "question", "value": export.question},
                {"field": "sql", "value": export.sql_text},
                {"field": "generated_at", "value": (utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M (เวลาไทย)")},
                {"field": "row_count", "value": len(rows)},
                {"field": "truncated", "value": str(truncated)},
                {"field": "requested_by_user_id", "value": export.user_id},
            ])

            # Write to temp then rename — never leave a half-written file.
            # Temp lives in .tmp/ subdir so the cleanup job's EXPORT_DIR/*.xlsx
            # orphan sweep can never delete a file that is still being written
            # (pandas requires the .xlsx extension, so a .tmp suffix won't work)
            tmp_dir = EXPORT_DIR / ".tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", dir=tmp_dir)
            os.close(fd)
            try:
                with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
                    pd.DataFrame(rows, columns=columns or None).to_excel(writer, sheet_name="Data", index=False)
                    info.to_excel(writer, sheet_name="Info", index=False)
                os.replace(tmp_path, final_path)
            except BaseException:
                Path(tmp_path).unlink(missing_ok=True)
                raise

            export.status = "done"
            export.file_path = str(final_path)
            export.row_count = len(rows)
            export.truncated = truncated
            export.completed_at = utcnow()
            export.expires_at = utcnow() + timedelta(days=retention_days)
            db.commit()
            logger.info(f"Export {export.id} done: {len(rows)} rows, truncated={truncated}")

        except Exception as e:
            logger.error(f"Export {export_id} failed: {e}")
            export.status = "failed"
            export.error = str(e)[:500]
            db.commit()
    finally:
        if owns_db:
            db.close()


def cleanup_expired(db: Session) -> int:
    """Delete expired export records + files, and orphan files. Returns count removed."""
    removed = 0
    now = utcnow()
    expired = db.query(ReportExport).filter(
        ReportExport.expires_at.isnot(None), ReportExport.expires_at < now
    ).all()
    for export in expired:
        if export.file_path:
            Path(export.file_path).unlink(missing_ok=True)
        db.delete(export)
        removed += 1
    db.commit()

    # Orphan files (record gone but file remains)
    if EXPORT_DIR.exists():
        known = {Path(e.file_path).name for e in db.query(ReportExport).filter(ReportExport.file_path.isnot(None)).all()}
        for f in EXPORT_DIR.glob("*.xlsx"):
            if f.name not in known:
                f.unlink(missing_ok=True)
                removed += 1
    return removed
