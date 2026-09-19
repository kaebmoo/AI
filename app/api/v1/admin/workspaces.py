"""Workspace admin endpoints (Plan 7 Phase 4a): partitions of contexts that API keys are bound to."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.services.query_engine import clear_query_cache
from app.services.workspaces import DEFAULT_WORKSPACE

router = APIRouter()


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: Optional[str] = None
    description: Optional[str] = None


class WorkspaceContexts(BaseModel):
    contexts: List[str] = Field(..., description="Context names to move into this workspace")


def _workspace(db: Session, workspace_id: int):
    row = db.execute(text("SELECT id, name, is_active FROM workspaces WHERE id = :id"), {"id": workspace_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="ไม่พบ workspace")
    return row


@router.get("/workspaces", response_model=list)
def list_workspaces(_current_user: User = Depends(deps.require_admin), db: Session = Depends(deps.get_config_db)):
    """Workspaces with the contexts each one holds."""
    contexts = {}
    for name, workspace_id in db.execute(text(  # NULL (created after the migration) = 'default'
            "SELECT name, COALESCE(workspace_id, (SELECT id FROM workspaces WHERE name = 'default')) "
            "FROM schema_contexts WHERE is_active = 1 ORDER BY name")):
        contexts.setdefault(workspace_id, []).append(name)
    return [{**dict(row), "is_active": bool(row["is_active"]), "contexts": contexts.get(row["id"], [])}
            for row in db.execute(text("SELECT id, name, display_name, description, is_active FROM workspaces ORDER BY id")).mappings()]


@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
def create_workspace(data: WorkspaceCreate, _current_user: User = Depends(deps.require_admin),
                     db: Session = Depends(deps.get_config_db)):
    try:
        db.execute(text("INSERT INTO workspaces (name, display_name, description) VALUES (:n, :d, :desc)"),
                   {"n": data.name, "d": data.display_name or data.name, "desc": data.description})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"workspace '{data.name}' มีอยู่แล้ว")
    return dict(db.execute(text("SELECT id, name, display_name, description, is_active FROM workspaces WHERE name = :n"),
                           {"n": data.name}).mappings().one())


@router.put("/workspaces/{workspace_id}/contexts")
def move_contexts(workspace_id: int, data: WorkspaceContexts, _current_user: User = Depends(deps.require_admin),
                  db: Session = Depends(deps.get_config_db)):
    """Move contexts into the workspace — a context belongs to exactly one, so keys of its
    previous workspace lose it with this call. All or nothing."""
    workspace = _workspace(db, workspace_id)
    known = {name for (name,) in db.execute(text("SELECT name FROM schema_contexts"))}
    missing = [name for name in data.contexts if name not in known]
    if missing:
        raise HTTPException(status_code=400, detail=f"ไม่พบ context: {missing}")
    for name in data.contexts:
        db.execute(text("UPDATE schema_contexts SET workspace_id = :ws WHERE name = :n"), {"ws": workspace_id, "n": name})
    db.commit()
    clear_query_cache()  # allowlists are part of the cache key, cached routes are not re-checked per workspace
    return {"workspace": workspace["name"], "moved": data.contexts}


@router.delete("/workspaces/{workspace_id}")
def deactivate_workspace(workspace_id: int, _current_user: User = Depends(deps.require_admin),
                         db: Session = Depends(deps.get_config_db)):
    """Soft delete: keys bound to it reach nothing until it is re-activated; its contexts stay put."""
    workspace = _workspace(db, workspace_id)
    if workspace["name"] == DEFAULT_WORKSPACE:
        raise HTTPException(status_code=400, detail="ปิด workspace 'default' ไม่ได้")
    db.execute(text("UPDATE workspaces SET is_active = 0 WHERE id = :id"), {"id": workspace_id})
    db.commit()
    clear_query_cache()
    return {"workspace": workspace["name"], "is_active": False}
