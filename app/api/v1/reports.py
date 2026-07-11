"""
Reports / Export API (PLAN F6)
===============================
Exports re-run the saved SQL — full data, not the 1,000-row session snapshot.
Frontend polls GET /{id} for status (no SSE).
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import deps
from app.core.time_utils import utcnow
from app.models.report_export import ReportExport
from app.models.user import User
from app.services import report_service
from app.services.report_service import ExportError

logger = logging.getLogger(__name__)

router = APIRouter()

# Checked once at import — REDIS_URL present means Celery broker is available
_celery_available = False
try:
    from app.config import settings
    _celery_available = bool(settings.REDIS_URL)
except Exception:
    pass


class CreateExportRequest(BaseModel):
    chat_history_id: int


class ExportStatus(BaseModel):
    id: str
    status: str
    question: Optional[str] = None
    row_count: Optional[int] = None
    truncated: bool = False
    error: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None


def _to_status(e: ReportExport) -> ExportStatus:
    return ExportStatus(
        id=e.id, status=e.status, question=e.question,
        row_count=e.row_count, truncated=bool(e.truncated), error=e.error,
        created_at=str(e.created_at) if e.created_at else None,
        expires_at=str(e.expires_at) if e.expires_at else None,
    )


def _get_owned(export_id: str, user: User, db: Session) -> ReportExport:
    export = db.query(ReportExport).filter(ReportExport.id == export_id).first()
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    if export.user_id != user.id and getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return export


EXPORTS_PER_HOUR = 10


@router.post("/", response_model=ExportStatus)
async def create_export(
    request: Request,
    body: CreateExportRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    # Per-USER hourly limit via DB count — slowapi's limiter keys by remote IP,
    # which shares quota across NAT users and is trivially bypassed by IP rotation
    from datetime import timedelta
    hour_ago = utcnow() - timedelta(hours=1)

    def _hour_count() -> int:
        return db.query(ReportExport).filter(
            ReportExport.user_id == current_user.id,
            ReportExport.created_at >= hour_ago,
        ).count()

    quota_msg = f"เกินจำนวน export ที่กำหนด ({EXPORTS_PER_HOUR} ครั้ง/ชั่วโมง)"
    if _hour_count() >= EXPORTS_PER_HOUR:  # cheap fast-path reject
        raise HTTPException(status_code=429, detail=quota_msg)

    try:
        export = report_service.create_export(db, current_user, body.chat_history_id)
    except ExportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Insert-then-verify closes the check/insert race: concurrent requests that all
    # passed the fast path each re-count AFTER their own insert — any request that
    # sees the cap breached deletes its reservation. Slight over-rejection at the
    # boundary is possible; overrun is not.
    if _hour_count() > EXPORTS_PER_HOUR:
        db.delete(export)
        db.commit()
        raise HTTPException(status_code=429, detail=quota_msg)

    if _celery_available:
        try:
            from app.workers.report_worker import generate_report
            generate_report.delay(export.id)
            return _to_status(export)
        except Exception as e:
            logger.warning(f"Celery enqueue failed, running inline: {e}")

    # Inline fallback — blocks the request but always works
    report_service.run_export(export.id, db=db)
    db.refresh(export)
    return _to_status(export)


@router.get("/", response_model=List[ExportStatus])
def list_exports(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    exports = db.query(ReportExport).filter(
        ReportExport.user_id == current_user.id
    ).order_by(ReportExport.created_at.desc()).offset(skip).limit(min(limit, 100)).all()
    return [_to_status(e) for e in exports]


@router.get("/{export_id}", response_model=ExportStatus)
def get_export(
    export_id: str,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    return _to_status(_get_owned(export_id, current_user, db))


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db),
):
    export = _get_owned(export_id, current_user, db)
    if export.status != "done" or not export.file_path:
        raise HTTPException(status_code=400, detail=f"Export not ready (status: {export.status})")
    if export.expires_at and export.expires_at < utcnow():
        raise HTTPException(status_code=410, detail="Export expired")
    import os
    if not os.path.exists(export.file_path):
        raise HTTPException(status_code=410, detail="Export file no longer available")

    try:
        from app.services.audit_service import AuditService
        AuditService(db).log_change(
            action="SELECT", table_name="report_exports", record_id=None,
            new_value={"export_id": export.id, "event": "downloaded"},
            source="report_export", user_id=current_user.id,
        )
    except Exception:
        pass

    created = export.created_at.strftime("%Y%m%d") if export.created_at else "report"
    return FileResponse(
        export.file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"nt-report-{created}.xlsx",
    )
