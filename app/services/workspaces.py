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
import re
from typing import Any, FrozenSet, Optional

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE = "default"


# A context created after the migration (new registration, admin UI) has workspace_id NULL:
# everywhere below NULL means 'default' — no creator has to know about workspaces.


class ContextNotAllowed(PermissionError):
    """The caller's key may not use this context → HTTP 403."""


def norm(name: str) -> str:
    # same spellings context_store.get_context_info accepts: 'transfer_price' = 'transfer price'
    return str(name).strip().lower().replace("_", " ")


def _config_engine():
    from app.db.session import config_engine
    return config_engine


def allowed_contexts(api_key: Any, config_engine=None) -> Optional[FrozenSet[str]]:
    """The contexts the key may use, as their exact stored names; None = unrestricted."""
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
            listed = list(parsed)
        except ValueError as exc:
            logger.error(f"API key {getattr(api_key, 'key_prefix', '?')}: unreadable allowed_contexts ({exc}) — denying all")
            return frozenset()
    try:
        with (config_engine or _config_engine()).connect() as conn:
            if workspace_id is None:
                reachable = {row[0] for row in conn.execute(text("SELECT name FROM schema_contexts WHERE is_active = 1 AND status = 'active'"))}
            else:
                reachable = {row[0] for row in conn.execute(text(
                    "SELECT sc.name FROM schema_contexts sc JOIN workspaces w ON w.id = COALESCE(sc.workspace_id, (SELECT id FROM workspaces WHERE name = 'default')) "
                    "WHERE w.id = :ws AND sc.is_active = 1 AND sc.status = 'active' AND w.is_active = 1"), {"ws": workspace_id})}
    except Exception as exc:
        logger.error(f"API key contexts unreadable ({exc}) — denying all")
        return frozenset()
    if listed is None:
        return frozenset(reachable)
    # a listed name stands for the stored context it spells (exactly, else loosely) — inside what is reachable
    return frozenset(name for entry in listed for name in [_match(entry, reachable)] if name)


def _match(name: str, stored) -> Optional[str]:
    """The stored context name a caller's spelling refers to: exact first, else '_'/space/case-insensitive."""
    if name in stored:
        return name
    loose = sorted(s for s in stored if norm(s) == norm(name))
    return loose[0] if loose else None


def is_restricted(api_key: Any) -> bool:
    return api_key is not None and (getattr(api_key, "workspace_id", None) is not None
                                    or bool(getattr(api_key, "allowed_contexts", None)))


def canonical_context(context_name: str, allowed: Optional[FrozenSet[str]]) -> str:
    """The stored name of the context a restricted caller named — or ContextNotAllowed.

    Only this return value may travel on: downstream resolution is exact, and a name that matches
    nothing there falls back to the legacy DB with an empty system prompt (i.e. outside every
    allowlist). Unrestricted callers get their string back untouched, as before."""
    if allowed is None:
        return context_name
    stored = _match(context_name, allowed) if isinstance(context_name, str) else None
    if stored is None:
        raise ContextNotAllowed(f"API key นี้ไม่มีสิทธิ์ใช้ context '{context_name}'")
    return stored


def check_context(context_name: str, allowed: Optional[FrozenSet[str]]) -> None:
    """A context the system itself picked (router, cache) must be one of the allowed stored names."""
    if allowed is not None and context_name not in allowed:
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
            "SELECT sc.name, COALESCE(sc.workspace_id, (SELECT id FROM workspaces WHERE name = 'default')) FROM schema_contexts sc "
            "WHERE sc.is_active = 1 AND sc.status = 'active'"))}
    for name in contexts or []:
        if norm(name) not in known:
            raise ValueError(f"ไม่พบ context '{name}'")
        if workspace_id is not None and known[norm(name)] != workspace_id:
            raise ValueError(f"context '{name}' ไม่อยู่ใน workspace '{workspace}'")
    return workspace_id, (json.dumps(list(contexts), ensure_ascii=False) if contexts is not None else None)



# ── Vanna brain per workspace (Phase 4b) ───────────────────────────────────────────────────

def brain_path(base: str, workspace: Optional[str]) -> str:
    """Chroma directory of a workspace's brain; 'default' keeps the path it always had."""
    if workspace in (None, DEFAULT_WORKSPACE):
        return base
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", workspace):  # it becomes part of a path
        raise ValueError(f"workspace name is not a slug: {workspace!r}")
    return f"{base.rstrip('/')}__{workspace}"


def workspace_of_context(context_name: Optional[str], config_engine=None) -> str:
    """Name of the workspace a context belongs to — the brain a question about it retrieves from."""
    try:
        with (config_engine or _config_engine()).connect() as conn:
            for name, workspace in conn.execute(text(
                    "SELECT sc.name, w.name FROM schema_contexts sc JOIN workspaces w ON w.id = COALESCE(sc.workspace_id, (SELECT id FROM workspaces WHERE name = 'default'))")):
                if norm(name) == norm(context_name or ""):
                    return workspace
    except Exception as exc:  # registry not migrated: one brain, as before
        logger.debug(f"workspace_of_context({context_name}): {exc}")
    return DEFAULT_WORKSPACE


class BrainFilter:
    """What is trained into a workspace's brain. A named workspace holds its own contexts and their
    tables only; 'default' holds everything not owned by another workspace — including knowledge
    no context owns (global rules, free-text golden categories). With no other workspace defined
    that is everything: the brain the deployment always had."""

    def __init__(self, workspace: Optional[str], config_engine=None):
        self.workspace = workspace or DEFAULT_WORKSPACE
        self._own_contexts, self._own_views, self._foreign_contexts, self._foreign_views = set(), set(), set(), set()
        with (config_engine or _config_engine()).connect() as conn:
            rows = list(conn.execute(text(
                "SELECT sc.name, sc.main_view, w.name, sc.id FROM schema_contexts sc "
                "LEFT JOIN workspaces w ON w.id = sc.workspace_id")))
            tables = {}
            try:
                for context_id, table in conn.execute(text(
                        "SELECT sc.id, st.table_name FROM schema_contexts sc JOIN source_tables st ON st.source_id = sc.source_id")):
                    tables.setdefault(context_id, set()).add(table)
            except Exception:
                pass  # no file-source registry
        for name, main_view, workspace_name, context_id in rows:
            own = (workspace_name or DEFAULT_WORKSPACE) == self.workspace
            views = {v.lower() for v in ({main_view} | tables.get(context_id, set())) if v}
            (self._own_contexts if own else self._foreign_contexts).add(norm(name))
            (self._own_views if own else self._foreign_views).update(views)

    def _keep(self, value: Optional[str], own: set, foreign: set) -> bool:
        if self.workspace == DEFAULT_WORKSPACE:
            return value is None or value not in foreign
        return value is not None and value in own

    def context(self, name: Optional[str]) -> bool:
        return self._keep(norm(name) if name else None, self._own_contexts, self._foreign_contexts)

    def view(self, name: Optional[str]) -> bool:
        return self._keep(name.lower() if name else None, self._own_views, self._foreign_views)


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
