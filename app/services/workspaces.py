"""
Workspace + scoped API key (Plan 7 Phase 4a)
=============================================
A workspace is a partition inside ONE deployment (D8 Tier 1: units of one organisation) —
contexts belong to a workspace, an API key may be bound to one. What a key can reach:

    no workspace, no allowlist  → unrestricted (every key issued before Phase 4; session users)
    workspace                   → the active contexts of that workspace
    workspace + allowlist       → their intersection — an allowlist narrows, never widens
    allowlist only              → the listed contexts

Anything unreadable (broken JSON, config DB down) = the empty set: fail closed, never open.
A context outside the set is refused with ContextNotAllowed (HTTP 403) — never dropped silently.
"""

import json
import logging
from typing import Any, FrozenSet, Optional

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = "default"


class ContextNotAllowed(PermissionError):
    """The caller's key may not use this context → HTTP 403."""


def norm(name: str) -> str:
    # same spellings context_store.get_context_info accepts: 'transfer_price' = 'transfer price'
    return str(name).strip().lower().replace("_", " ")


def _config_engine():
    from app.db.session import config_engine
    return config_engine


def allowed_contexts(api_key: Any, config_engine=None) -> Optional[FrozenSet[str]]:
    """Normalised context names the key may use; None = unrestricted."""
    workspace_id = getattr(api_key, "workspace_id", None)
    raw = getattr(api_key, "allowed_contexts", None)
    if workspace_id is None and not raw:
        return None
    listed = None
    if raw:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, list) or not all(isinstance(n, str) for n in parsed):
                raise ValueError("allowed_contexts must be a JSON list of names")
            listed = {norm(n) for n in parsed}
        except ValueError as exc:
            logger.error(f"API key {getattr(api_key, 'key_prefix', '?')}: unreadable allowed_contexts ({exc}) — denying all")
            return frozenset()
    if workspace_id is None:
        return frozenset(listed)
    try:
        with (config_engine or _config_engine()).connect() as conn:
            in_workspace = {norm(row[0]) for row in conn.execute(text(
                "SELECT sc.name FROM schema_contexts sc JOIN workspaces w ON w.id = sc.workspace_id "
                "WHERE sc.workspace_id = :ws AND sc.is_active = 1 AND w.is_active = 1"), {"ws": workspace_id})}
    except Exception as exc:
        logger.error(f"Workspace {workspace_id}: contexts unreadable ({exc}) — denying all")
        return frozenset()
    return frozenset(in_workspace if listed is None else in_workspace & listed)


def is_restricted(api_key: Any) -> bool:
    return api_key is not None and (getattr(api_key, "workspace_id", None) is not None
                                    or bool(getattr(api_key, "allowed_contexts", None)))


def check_context(context_name: str, allowed: Optional[FrozenSet[str]]) -> None:
    if allowed is not None and norm(context_name) not in allowed:
        raise ContextNotAllowed(f"API key นี้ไม่มีสิทธิ์ใช้ context '{context_name}'")



def resolve_key_binding(workspace: Optional[str], contexts: Optional[list], config_engine=None):
    """(workspace_id, allowed_contexts JSON) for a new key — ValueError when the binding could
    never work (unknown/inactive workspace, unknown context, context of another workspace, empty list)."""
    if workspace is None and contexts is None:
        return None, None
    if contexts is not None and not contexts:
        raise ValueError("allowed_contexts ว่าง — key นี้จะใช้ context ใดไม่ได้เลย")
    with (config_engine or _config_engine()).connect() as conn:
        workspace_id = None
        if workspace is not None:
            workspace_id = conn.execute(text("SELECT id FROM workspaces WHERE name = :n AND is_active = 1"),
                                        {"n": workspace}).scalar()
            if workspace_id is None:
                raise ValueError(f"ไม่พบ workspace '{workspace}'")
        known = {norm(name): ws for name, ws in conn.execute(text(
            "SELECT name, workspace_id FROM schema_contexts WHERE is_active = 1"))}
    for name in contexts or []:
        if norm(name) not in known:
            raise ValueError(f"ไม่พบ context '{name}'")
        if workspace_id is not None and known[norm(name)] != workspace_id:
            raise ValueError(f"context '{name}' ไม่อยู่ใน workspace '{workspace}'")
    return workspace_id, (json.dumps(list(contexts), ensure_ascii=False) if contexts is not None else None)


_key_columns_checked: set = set()  # engine URLs whose api_keys table this process has checked


def ensure_api_key_columns(bind) -> None:
    """api_keys.workspace_id / allowed_contexts on an app DB created before Phase 4 (idempotent).

    The APIKey model selects both columns, so without them every key lookup fails — i.e. a
    deploy that forgot scripts/migrate_workspaces.py would lock every API caller out. Checked
    once per process per database.
    """
    url = str(bind.engine.url)
    if url in _key_columns_checked:
        return
    inspector = inspect(bind.engine)
    if inspector.has_table("api_keys"):
        existing = {c["name"] for c in inspector.get_columns("api_keys")}
        for column, ddl in (("workspace_id", "INTEGER"), ("allowed_contexts", "TEXT")):
            if column not in existing:
                with bind.engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE api_keys ADD COLUMN {column} {ddl}"))
                logger.info(f"Added api_keys.{column}")
    _key_columns_checked.add(url)
