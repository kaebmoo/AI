"""
One rule for every writer of the knowledge tables (Plan 8.1 — PLAN_8 §3.2–3.4, RESULT_P8_PHASE1 §7.6)

    source  declared (the data owner's contract) · manual (a person) · inferred (data / profile / LLM) · learned (real use)
    status  active (read by prompt and RAG) · proposed (waits for a person) · rejected (a person said no)

Who may change a row that is already there:
- a person (manual): always — the row becomes theirs
- the contract (declared): its own earlier declaration and what a machine wrote, never a person's row —
  contract against admin waits for a person every time (D-C, owner 2026-09-21)
- a machine (inferred / learned): only what a machine wrote
Only a person touches a rejected row. When the writer may not change the row, its version waits in
knowledge_proposals and the row in use stays as it is. Unknown provenance (NULL, the old 'auto') is a person's.
"""

import json
import sqlite3
from typing import Any, Dict, Iterable, Optional

DECLARED, MANUAL, INFERRED, LEARNED = "declared", "manual", "inferred", "learned"
ACTIVE, PROPOSED, REJECTED = "active", "proposed", "rejected"
MACHINE = frozenset({INFERRED, LEARNED})
KNOWLEDGE_TABLES = ("schema_contexts", "schema_metadata", "schema_business_rules", "golden_examples",
                    "schema_semantic_mapping", "master_hierarchy", "master_hierarchy_values", "data_warnings",
                    "vanna_documentation")

# What the contract writes, per table (datafeed_knowledge, gen_golden_from_controls). A person who edits one of
# these makes a declared row theirs; editing anything else — keywords, priority, workspace, on/off, display
# names, dimension family — leaves it declared, because the contract never writes those fields.
DECLARED_FIELDS = {
    "schema_contexts": frozenset({"main_view", "description", "instruction_th", "scope_columns"}),
    "schema_metadata": frozenset({"description", "data_type", "is_summable", "is_groupable"}),
    "vanna_documentation": frozenset({"title", "content", "category", "context_name"}),
    "golden_examples": frozenset({"question_pattern", "expected_sql", "category"}),
}


def may_replace(writer: str, source: Optional[str], status: Optional[str] = None) -> bool:
    """Whether `writer` may change, in place, a row whose provenance is (source, status)."""
    if writer == MANUAL:
        return True
    if status == REJECTED:
        return False
    if writer == DECLARED:
        return source == DECLARED or source in MACHINE
    return source in MACHINE


def after_human_edit(table: str, source: Optional[str], changed: Iterable[str]) -> str:
    """The source of a row after a person changed `changed` of its fields."""
    if source == DECLARED and not DECLARED_FIELDS.get(table, frozenset()) & set(changed):
        return DECLARED
    return MANUAL


def missing_status(engine) -> list:
    """Knowledge tables that exist without the Plan 8.1 `status` column — every prompt / RAG reader filters on it."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    return [t for t in KNOWLEDGE_TABLES
            if t in present and "status" not in {c["name"] for c in inspector.get_columns(t)}]


def mark_human_edit(row, table: str, changed: Iterable[str]) -> None:
    """An ORM row a person just changed: theirs (or still declared — after_human_edit), and in use."""
    row.source = after_human_edit(table, row.source, changed)
    row.status = ACTIVE


def _run(conn, sql: str, params: Dict[str, Any]):
    if isinstance(conn, sqlite3.Connection):
        return conn.execute(sql, params)
    from sqlalchemy import text
    return conn.execute(text(sql), params)


def as_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def propose(conn, table: str, key: Dict[str, Any], values: Dict[str, Any], source: str,
            confidence: Optional[float] = None, reason: Optional[str] = None) -> bool:
    """Queue `values` for the row of `table` at `key`, on the caller's transaction (sqlite3 or SQLAlchemy).

    One open proposal per key and proposer: a newer version is merged into the one still waiting, field by field
    (two machine writers may propose different fields of one row). A version a person already rejected, or one
    the waiting proposal already says, is not written again. True = something new waits now.
    """
    params = {"t": table, "k": as_json(key), "p": as_json(values), "s": source, "c": confidence, "r": reason}
    wanted = json.loads(params["p"])
    for status, proposed in _run(conn, "SELECT status, proposed FROM knowledge_proposals WHERE table_name = :t "
                                       "AND row_key = :k AND source = :s AND status IN ('rejected', 'proposed')", params):
        held = json.loads(proposed)
        if (status == REJECTED and held == wanted) or (status == PROPOSED and {**held, **wanted} == held):
            return False
    _run(conn, "INSERT INTO knowledge_proposals (table_name, row_key, proposed, source, confidence, reason) "
               "VALUES (:t, :k, :p, :s, :c, :r) ON CONFLICT (table_name, row_key, source) WHERE status = 'proposed' "
               "DO UPDATE SET proposed = json_patch(knowledge_proposals.proposed, excluded.proposed), "
               "confidence = excluded.confidence, reason = excluded.reason, created_at = CURRENT_TIMESTAMP", params)
    return True
