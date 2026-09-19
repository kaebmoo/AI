"""
Register a DataFeed bundle as a DuckDB file source (Plan 7 Phase 1 — zero-import)
==================================================================================
Points context feed_<domain> at <source>/<domain>/latest/ where the files already
are. Nothing is copied: the assistant reads the CSVs in place through DuckDB views
named exactly like the F10 tables (feed_<domain>_<dataset>), so the F10
knowledge/golden keep working.

Same gates as import_datafeed.py, but against the files in place — the registry
is only written after all of them pass:
1. manifest reconcile.ok, 2. sha256 of every file used (allowlist = manifest files),
3. row counts through the views, 4. control totals through the views (if the contract has them).

Registry, context knowledge (from the contract — app/services/datafeed_knowledge.py) and
the contract pointer are written in one transaction; afterwards the knowledge re-syncs
itself whenever the contract or the build's schema_version changes (Phase 2).

Rollback to the imported copy (import_datafeed.py stays the fallback): --legacy

Usage:
    python -m scripts.datafeed.register_file_source --domain revenue \
        --source /path/to/DataFeed/dist
    python -m scripts.datafeed.register_file_source --domain revenue --legacy
"""

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.source_registration import (  # noqa: E402,F401 — re-exported for callers of this module
    DTYPE_DUCKDB, GateError, build_tables, register, register_domain, source_name, verify_in_place,
)


def bind_legacy(config_engine, domain: str) -> None:
    from sqlalchemy import text

    with config_engine.begin() as conn:
        bound = conn.execute(text(
            "UPDATE schema_contexts SET source_id = (SELECT id FROM data_sources WHERE name = 'legacy') "
            "WHERE name = :ctx"
        ), {"ctx": f"feed_{domain}"}).rowcount
    print(f"feed_{domain} → legacy (business DB เดิม) — {bound} context(s)")


def main():
    parser = argparse.ArgumentParser(description="Register a DataFeed bundle as a DuckDB file source")
    parser.add_argument("--domain", required=True, choices=["revenue", "expense", "sales", "ebt"])
    parser.add_argument("--source", help="Path to DataFeed/dist (required unless --legacy)")
    parser.add_argument("--legacy", action="store_true", help="Point feed_<domain> back at the imported copy")
    args = parser.parse_args()

    from app.db.session import config_engine
    from scripts.migrate_data_sources import migrate

    migrate(config_engine)
    if args.legacy:
        bind_legacy(config_engine, args.domain)
        return
    if not args.source:
        parser.error("--source is required")

    t0 = time.time()
    try:  # gates + registry + knowledge: app/services/source_registration.py (shared with POST /admin/sources/register)
        done = register_domain(config_engine, args.domain, Path(args.source))
    except GateError as exc:
        raise SystemExit(f"ABORT: {exc}") from exc
    print(f"Domain {args.domain}: schema {done['schema_version']}, period {done['period']}, root {done['root']}")
    print(f"Knowledge: {done['context']} ({done['metadata_rows']} metadata rows, {done['docs']} docs) — brain marked dirty")
    print(f"Registered source '{done['source']}' ({done['views']} views) → {done['context']} "
          f"in {time.time() - t0:.1f}s — no rows imported")

if __name__ == "__main__":
    main()
