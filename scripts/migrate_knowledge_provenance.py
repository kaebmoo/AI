"""
Migration script (Plan 8 Phase 8.1): where each row of knowledge came from, how sure it is, and whether it is in use.

config DB — the nine knowledge tables get `source` / `status` / `confidence` (PLAN_8 §3.2), and a queue table
`knowledge_proposals` holds a version that waits for a person because it collides with a row in use: every one of
those tables but golden_examples has a UNIQUE key of its own, so a proposed row cannot sit beside the active row
with the same key (RESULT_P8_PHASE1 §7.6 — owner's ruling 2026-09-21).

    source      declared (contract / data owner) · manual (a person) · inferred (data / profile / LLM) · learned (real use)
    status      active (read by prompt and RAG) · proposed (waits for a person) · rejected (a person said no)
    confidence  0–1 from the machine that wrote the row; NULL = not recorded

Rows that exist before this migration (RESULT_P8_PHASE1 §7.5): what a contract wrote = declared, a hierarchy value
extracted from the data = inferred, everything else = manual (every hierarchy level here was written or accepted by
a person); status = active and is_active untouched, so every request builds the prompt it built before.

Safe to run multiple times: columns are added when missing and only provenance that is still unknown is filled —
run it again after the restart to label rows the old code wrote in between (they arrive with status 'active').

Usage:
    python scripts/migrate_knowledge_provenance.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app.services.provenance import KNOWLEDGE_TABLES as TABLES  # noqa: E402 — the one list the app checks at startup

COLUMNS = (("source", "TEXT"), ("status", "TEXT NOT NULL DEFAULT 'active'"), ("confidence", "REAL"))

# What a contract source wrote, read from the registry — never a context name typed here
_CONTRACT_CONTEXTS = ("SELECT name FROM schema_contexts WHERE source_id IN "
                      "(SELECT id FROM data_sources WHERE contract_file IS NOT NULL)")
_CONTRACT_TABLES = ("SELECT st.table_name FROM source_tables st JOIN data_sources ds ON ds.id = st.source_id "
                    "WHERE ds.contract_file IS NOT NULL")
UNKNOWN = "(source IS NULL OR source = 'auto')"  # 'auto' = the hierarchy tables' old label and column default

BACKFILL = (
    f"UPDATE schema_contexts SET source = CASE WHEN name IN ({_CONTRACT_CONTEXTS}) THEN 'declared' ELSE 'manual' END "
    f"WHERE {UNKNOWN}",
    f"UPDATE schema_metadata SET source = CASE WHEN table_name IN ({_CONTRACT_TABLES}) THEN 'declared' ELSE 'manual' END "
    f"WHERE {UNKNOWN}",
    # datafeed_knowledge.sync_documentation writes category 'datafeed' for the context of its own contract
    f"UPDATE vanna_documentation SET source = CASE WHEN category = 'datafeed' AND context_name IN ({_CONTRACT_CONTEXTS}) "
    f"THEN 'declared' ELSE 'manual' END WHERE {UNKNOWN}",
    # gen_golden_from_controls writes category = the context, with no added_by; a person's example has one
    f"UPDATE golden_examples SET source = CASE WHEN added_by IS NULL AND category IN ({_CONTRACT_CONTEXTS}) "
    f"THEN 'declared' ELSE 'manual' END WHERE {UNKNOWN}",
    f"UPDATE master_hierarchy SET source = 'manual' WHERE {UNKNOWN}",
    f"UPDATE master_hierarchy_values SET source = 'inferred' WHERE {UNKNOWN}",
    f"UPDATE schema_business_rules SET source = 'manual' WHERE {UNKNOWN}",
    f"UPDATE schema_semantic_mapping SET source = 'manual' WHERE {UNKNOWN}",
    f"UPDATE data_warnings SET source = 'manual' WHERE {UNKNOWN}",
)

PROPOSALS_DDL = (
    """CREATE TABLE IF NOT EXISTS knowledge_proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT NOT NULL,              -- the knowledge table the version belongs to
        row_key TEXT NOT NULL,                 -- JSON of that table's key, e.g. {"name": "feed_revenue"}
        proposed TEXT NOT NULL,                -- JSON of the column values proposed
        source TEXT NOT NULL,                  -- who proposes: declared / inferred / learned
        confidence REAL,
        reason TEXT,                           -- why it waits instead of being written
        status TEXT NOT NULL DEFAULT 'proposed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    # one open proposal per key and proposer: a newer version is merged into the one still waiting (provenance.propose)
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_knowledge_proposals_open "
    "ON knowledge_proposals (table_name, row_key, source) WHERE status = 'proposed'",
)


def _label_and_queue(engine) -> int:
    """Label unknown provenance and create the queue in ONE SQLite transaction, begun by hand. pysqlite issues BEGIN
    only before DML, so a DROP TRIGGER ahead of the backfill committed on its own, and a backfill that failed rolled
    back without the trigger (Codex review 2026-09-22). With isolation_level None the BEGIN below covers DDL too."""
    raw = engine.raw_connection()
    dbapi = raw.driver_connection
    saved, dbapi.isolation_level = dbapi.isolation_level, None
    cur = dbapi.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        try:
            labelled = 0
            if any(cur.execute(f'SELECT 1 FROM "{t}" WHERE {UNKNOWN} LIMIT 1').fetchone() for t in TABLES):
                # Labelling provenance is not an edit of the content: a trigger that stamps updated_at on every
                # UPDATE (vanna_documentation has one) is lifted for the backfill and put back as it was
                names = ", ".join(f"'{t}'" for t in TABLES)
                triggers = cur.execute(
                    f"SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name IN ({names})").fetchall()
                for name, _ in triggers:
                    cur.execute(f'DROP TRIGGER "{name}"')
                for sql in BACKFILL:
                    labelled += cur.execute(sql).rowcount
                for _, sql in triggers:
                    cur.execute(sql)
            for ddl in PROPOSALS_DDL:
                cur.execute(ddl)
            cur.execute("COMMIT")
            return labelled
        except BaseException:
            cur.execute("ROLLBACK")
            raise
    finally:
        dbapi.isolation_level = saved
        raw.close()


def migrate(config_engine=None) -> dict:
    if config_engine is None:
        from app.db.session import config_engine
    for table in TABLES:
        existing = {c["name"] for c in inspect(config_engine).get_columns(table)}
        for column, ddl in COLUMNS:
            if column not in existing:
                with config_engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {column} {ddl}'))
                print(f"Added {table}.{column}")
    labelled = _label_and_queue(config_engine)
    with config_engine.connect() as conn:
        summary = {t: conn.execute(text(f'SELECT source, status, COUNT(*) FROM "{t}" GROUP BY 1, 2 ORDER BY 1, 2')).all()
                   for t in TABLES}
    print(f"Labelled {labelled} row(s) whose source was unknown")
    for table, rows in summary.items():
        print(f"  {table}: " + ", ".join(f"{s}/{st} {n}" for s, st, n in rows))
    print("Migration complete (idempotent).")
    return summary


if __name__ == "__main__":
    migrate()
