"""Vanna documentation CRUD + brain sync status endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api import deps
from app.models.schema_models import VannaDocumentation
from app.models.user import User
from app.schemas.admin_schemas import (
    VannaDocCreate,
    VannaDocListResponse,
    VannaDocResponse,
    VannaDocUpdate,
)
from ._shared import mark_brain_dirty
from app.services.provenance import ACTIVE, MANUAL, apply_human_edit

router = APIRouter()


def _raise_if_vanna_docs_table_missing(exc: OperationalError) -> None:
    error_text = str(getattr(exc, "orig", exc)).lower()
    if "no such table" in error_text and "vanna_documentation" in error_text:
        raise HTTPException(
            status_code=503,
            detail=(
                "Vanna documentation is not initialized. "
                "Apply migration 031_vanna_documentation.sql or run scripts/init_db.py first."
            ),
        ) from exc
    raise exc


# ── CRUD ──────────────────────────────────────────────────────

@router.get("/vanna-docs", response_model=VannaDocListResponse)
def list_vanna_docs(
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all Vanna knowledge docs with optional filters."""
    try:
        q = db.query(VannaDocumentation)
        if category is not None:
            q = q.filter(VannaDocumentation.category == category)
        if is_active is not None:
            q = q.filter(VannaDocumentation.is_active == is_active)
        q = q.order_by(VannaDocumentation.category, VannaDocumentation.doc_key)
        docs = q.all()
        return VannaDocListResponse(docs=docs, total=len(docs))
    except OperationalError as exc:
        _raise_if_vanna_docs_table_missing(exc)


@router.get("/vanna-docs/{doc_id}", response_model=VannaDocResponse)
def get_vanna_doc(
    doc_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get a single Vanna doc by ID."""
    try:
        doc = db.query(VannaDocumentation).filter(VannaDocumentation.id == doc_id).first()
    except OperationalError as exc:
        _raise_if_vanna_docs_table_missing(exc)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/vanna-docs", response_model=VannaDocResponse, status_code=201)
def create_vanna_doc(
    data: VannaDocCreate,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Create a new Vanna knowledge doc."""
    try:
        existing = db.query(VannaDocumentation).filter(
            VannaDocumentation.doc_key == data.doc_key
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"doc_key '{data.doc_key}' already exists")

        doc = VannaDocumentation(**data.model_dump(), source=MANUAL, status=ACTIVE)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        mark_brain_dirty()
        return doc
    except OperationalError as exc:
        db.rollback()
        _raise_if_vanna_docs_table_missing(exc)


@router.put("/vanna-docs/{doc_id}", response_model=VannaDocResponse)
def update_vanna_doc(
    doc_id: int,
    data: VannaDocUpdate,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Update an existing Vanna doc."""
    try:
        doc = db.query(VannaDocumentation).filter(VannaDocumentation.id == doc_id).first()
    except OperationalError as exc:
        _raise_if_vanna_docs_table_missing(exc)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        update_data = data.model_dump(exclude_unset=True)
        apply_human_edit(doc, "vanna_documentation", update_data)

        db.commit()
        db.refresh(doc)
        mark_brain_dirty()
        return doc
    except OperationalError as exc:
        db.rollback()
        _raise_if_vanna_docs_table_missing(exc)


@router.delete("/vanna-docs/{doc_id}", status_code=204)
def delete_vanna_doc(
    doc_id: int,
    _current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Delete a Vanna doc."""
    try:
        doc = db.query(VannaDocumentation).filter(VannaDocumentation.id == doc_id).first()
    except OperationalError as exc:
        _raise_if_vanna_docs_table_missing(exc)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        db.delete(doc)
        db.commit()
        mark_brain_dirty()
    except OperationalError as exc:
        db.rollback()
        _raise_if_vanna_docs_table_missing(exc)


# ── Brain Sync Status ─────────────────────────────────────────

@router.get("/brain-sync-status")
def get_brain_sync_status(
    _current_user: User = Depends(deps.require_admin),
):
    """Check if Vanna brain needs re-sync after recent changes."""
    from app.services.admin_config_service import AdminConfigService
    config_svc = AdminConfigService()
    try:
        last_sync = config_svc.get_config('last_brain_sync_at')
        last_change = config_svc.get_config('last_brain_relevant_change_at')
        return {
            "last_brain_sync_at": last_sync,
            "last_brain_relevant_change_at": last_change,
            "needs_sync": bool(last_change and (not last_sync or last_change > last_sync)),
        }
    finally:
        config_svc.close()
