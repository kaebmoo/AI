"""Data source admin endpoints (Plan 7 Phase 4c): what is registered, is it readable and how
fresh, and (re-)registration through the same gates as the CLI."""

import asyncio
import json
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import deps
from app.config import settings
from app.core.llm_policy import FULL, normalize, parse_allowlist
from app.models.user import User
from app.services.query_engine import clear_query_cache

router = APIRouter()


class SourceRegisterRequest(BaseModel):
    domain: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$", description="DataFeed domain → context feed_<domain>")
    source_dir: Optional[str] = Field(
        None, description="Path to <dist>. Omit to re-register a domain from where it already is; "
                          "a new path must lie under DATA_SOURCE_ALLOWED_ROOTS (.env)")


class SourcePolicyRequest(BaseModel):
    llm_data_policy: Literal["full", "aggregated_only", "schema_only"]
    llm_provider_allowlist: Optional[List[str]] = Field(
        None, description="Providers this source's questions may go to; null = any enabled provider")


@router.get("/sources", response_model=list)
def list_sources(_current_user: User = Depends(deps.require_admin), db: Session = Depends(deps.get_config_db)):
    """Registered sources with the contexts bound to them. No file is touched — see /sources/{name}/status."""
    contexts = {}
    for row in db.execute(text(
            "SELECT sc.source_id, sc.name, sc.is_active, sc.main_view, w.name AS workspace FROM schema_contexts sc "
            "LEFT JOIN workspaces w ON w.id = COALESCE(sc.workspace_id, (SELECT id FROM workspaces WHERE name = 'default')) "
            "ORDER BY sc.name")).mappings():
        contexts.setdefault(row["source_id"], []).append(
            {"name": row["name"], "is_active": bool(row["is_active"]), "main_view": row["main_view"], "workspace": row["workspace"]})
    tables = dict(db.execute(text("SELECT source_id, COUNT(*) FROM source_tables WHERE is_active = 1 GROUP BY source_id")).all())
    return [{"name": s["name"], "source_type": s["source_type"], "root_path": s["root_path"],
             "contract_file": s["contract_file"], "knowledge": s["knowledge_sha"], "is_active": bool(s["is_active"]),
             "llm_data_policy": normalize(s["llm_data_policy"]) if "llm_data_policy" in s else FULL,
             "llm_provider_allowlist": (sorted(parse_allowlist(s["llm_provider_allowlist"]))
                                        if s.get("llm_provider_allowlist") else None),
             "tables": tables.get(s["id"], 0), "contexts": contexts.get(s["id"], []), "updated_at": str(s["updated_at"] or "")}
            for s in db.execute(text("SELECT * FROM data_sources ORDER BY id")).mappings()]


@router.get("/sources/{name}/status")
def source_status(name: str, _current_user: User = Depends(deps.require_admin), db: Session = Depends(deps.get_config_db)):
    """Connection test + freshness: resolves the source exactly as a question would (manifest
    reconcile + sha256 of the build), so `ok` means the assistant can answer from it right now."""
    from app.services.data_sources import source_resolver

    context = db.execute(text(
        "SELECT sc.name FROM schema_contexts sc JOIN data_sources ds ON ds.id = sc.source_id "
        "WHERE ds.name = :n AND sc.is_active = 1 ORDER BY sc.id"), {"n": name}).scalar()
    if context is None:
        if db.execute(text("SELECT 1 FROM data_sources WHERE name = :n"), {"n": name}).scalar() is None:
            raise HTTPException(status_code=404, detail="ไม่พบ source")
        return {"source": name, "ok": False, "error": "ไม่มี context ที่ active ผูกกับ source นี้"}
    try:
        resolved = source_resolver.for_context(context)
        if resolved.adapter is None:  # legacy business DB
            from app.db.session import business_engine
            with business_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"source": name, "ok": True, "context": context, "data_as_of": None}
        manifest = resolved.adapter.manifest or {}
        return {"source": name, "ok": bool(resolved.adapter.test_connection()), "context": context,
                "data_as_of": resolved.data_as_of, "schema_version": manifest.get("schema_version"),
                "views": len(resolved.adapter.view_columns)}
    except Exception as exc:  # SourceUnavailable (publishing / failed verification), missing files, …
        return {"source": name, "ok": False, "context": context, "error": str(exc)}


@router.put("/sources/{name}/policy")
def set_source_policy(name: str, request: SourcePolicyRequest, _current_user: User = Depends(deps.require_admin),
                      db: Session = Depends(deps.get_config_db)):
    """Phase 4.5: what of this source's data may reach an LLM provider, and which providers.
    Takes effect on the next question (the policy is read per request; cached answers are dropped)."""
    from app.providers.registry import provider_registry

    unknown = sorted(set(request.llm_provider_allowlist or []) - set(provider_registry.get_available()))
    if unknown:  # a misspelt name would lock every question out of the source
        raise HTTPException(status_code=400, detail=f"ไม่รู้จัก provider {unknown} — มี {provider_registry.get_available()}")
    allowlist = json.dumps(sorted(set(request.llm_provider_allowlist))) if request.llm_provider_allowlist is not None else None
    try:
        updated = db.execute(text(
            "UPDATE data_sources SET llm_data_policy = :p, llm_provider_allowlist = :a, updated_at = CURRENT_TIMESTAMP "
            "WHERE name = :n"), {"p": request.llm_data_policy, "a": allowlist, "n": name}).rowcount
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"config DB ยังไม่รองรับ — รัน scripts/migrate_data_sources.py ({exc})")
    if not updated:
        raise HTTPException(status_code=404, detail="ไม่พบ source")
    db.commit()
    clear_query_cache()
    return {"source": name, "llm_data_policy": request.llm_data_policy, "llm_provider_allowlist": request.llm_provider_allowlist}


@router.post("/sources/register")
async def register_source(request: SourceRegisterRequest, _current_user: User = Depends(deps.require_admin)):
    """Register / re-register a DataFeed domain as a file source. Same gates as
    scripts/datafeed/register_file_source.py; a failed gate = 400 and the registry is unchanged."""
    from app.db.session import config_engine
    from app.services import source_registration as registration

    try:
        if request.source_dir:
            roots = [r.strip() for r in (settings.DATA_SOURCE_ALLOWED_ROOTS or "").split(",") if r.strip()]
            dist = registration.allowed_dist(request.source_dir, roots)
        else:
            dist = registration.dist_of_registered(config_engine, request.domain)
            if dist is None:
                raise registration.GateError(f"'{request.domain}' ยังไม่เคยลงทะเบียน — ต้องระบุ source_dir")
        done = await asyncio.to_thread(registration.register_domain, config_engine, request.domain, dist)  # hashes every file
    except registration.GateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    clear_query_cache()
    return {"status": "success", **done}
