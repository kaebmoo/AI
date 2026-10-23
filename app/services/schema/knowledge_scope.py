"""Which knowledge that no context owns applies to a context — decided by the columns it names.

A business rule with no table (``table_name`` NULL / '' / 'ALL') or a semantic mapping with no context
(``context_name`` NULL) was written for one data set and reached every context's prompt. The feed_ebt system
prompt (37,906 chars) carried ``department_abbr`` 103 times and the rule "จังหวัดให้ใช้ section" — columns no
feed_ebt table has — and "ebt ของ น่าน" was filtered at the wrong level (2026-10-22).

The rule holds for any data set, today's or one registered later: an item applies to a context unless it
names a column that some context has and this one does not. Nothing here names a context, a table or a
column; both sides are read from the registry (schema_contexts / source_tables / the legacy view itself).
An item that names no known column at all ("สร้าง SQL เพียง query เดียว") applies everywhere, as before.

Read-time only: no row is changed, so a person's knowledge (provenance `manual` / `declared`) is never
rewritten — it is just not shown where its columns do not exist.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Set

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

GLOBAL_RULE_TABLES = (None, "", "ALL")

# a quoted identifier (a Thai column is always quoted), or a bare word with an underscore in it
_IDENT = re.compile(r'"([^"]+)"|`([^`]+)`|\b([A-Za-z0-9]*_[A-Za-z0-9_]*)\b')


def named(*texts: Optional[str]) -> Set[str]:
    """The tokens of the texts that can only be identifiers, lowercase: quoted names and words with an
    underscore (department_abbr, time_key). A plain word is not counted even when some context has a column
    of that name — "GROUP BY", "division by zero", and the placeholders the rules are written with (AMOUNT,
    YEAR, table) are words first; counting them dropped 24 of 50 global rules from the revenue context
    itself. Only names that are some context's column count (ColumnScope.applies)."""
    found: Set[str] = set()
    for value in texts:
        for quoted, ticked, bare in _IDENT.findall(value or ""):
            token = (quoted or ticked or bare).strip().strip("_").lower()
            if token:
                found.add(token)
    return found


@dataclass(frozen=True)
class ColumnScope:
    own: FrozenSet[str]    # columns of this context's tables, lowercase
    known: FrozenSet[str]  # columns of every active context's tables, lowercase

    def applies(self, *texts: Optional[str], column: Optional[str] = None) -> bool:
        """False when the item names a known column this context lacks.

        ponytail: identifier-shaped tokens only (see `named`) — a rule that names another context's column as a
        plain word ("ใช้ section สำหรับจังหวัด") still reaches every context, as before. Upgrade: parse the
        rule's example SQL (database_adapter.check_select's json_serialize_sql) for its column references."""
        names = named(*texts) & self.known
        if column and column.strip():
            names.add(column.strip().lower())  # a mapping's target column counts even if no context has it
        return names <= self.own


def _columns_of(conn, business_engine, context: Dict) -> Set[str]:
    """Columns of every table a context reads: its file source's tables, else its legacy main view."""
    columns: Set[str] = set()
    if context.get("source_type") == "duckdb_file" and context.get("source_id") is not None:
        for (raw,) in conn.execute(text("SELECT columns FROM source_tables WHERE source_id = :s AND is_active = 1"),
                                   {"s": context["source_id"]}):
            try:
                columns.update(c["name"].lower() for c in json.loads(raw or "[]") if c.get("name"))
            except (TypeError, ValueError, AttributeError):
                continue
        return columns
    view = context.get("main_view")
    if view:
        try:
            columns.update(c["name"].lower() for c in inspect(business_engine).get_columns(view))
        except Exception:  # the view is missing: metadata still says what it had
            pass
        columns.update(row[0].lower() for row in conn.execute(text(
            "SELECT column_name FROM schema_metadata WHERE table_name = :t AND status = 'active'"), {"t": view}) if row[0])
    return columns


def scope_for(service, context_name: Optional[str]) -> Optional[ColumnScope]:
    """The context's ColumnScope; None — keep every item, the behaviour before this existed — when the
    context or the registry can't be read, or no column of the context is known."""
    if not context_name:
        return None
    from app.db.session import business_engine  # the legacy views; a file source's columns come from the registry

    try:
        with service.get_config_engine().connect() as conn:
            try:
                rows = conn.execute(text(
                    "SELECT sc.name, sc.main_view, sc.source_id, ds.source_type FROM schema_contexts sc "
                    "LEFT JOIN data_sources ds ON ds.id = sc.source_id "
                    "WHERE sc.is_active = 1 AND sc.status = 'active'")).mappings().all()
            except Exception:  # a config DB without the file-source registry: legacy views only
                rows = conn.execute(text(
                    "SELECT name, main_view FROM schema_contexts WHERE is_active = 1")).mappings().all()
            columns = {row["name"]: _columns_of(conn, business_engine, dict(row)) for row in rows}
    except Exception as exc:
        logger.warning("knowledge scope unavailable for %s (every item kept): %s", context_name, exc)
        return None
    own = next((cols for name, cols in columns.items()
                if name.replace("_", " ").lower() == context_name.replace("_", " ").lower()), None)
    if not own:
        return None
    return ColumnScope(own=frozenset(own), known=frozenset().union(*columns.values()))
