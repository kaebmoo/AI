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
import json
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.datafeed.import_datafeed import (  # noqa: E402
    check_control_totals, check_integrity_pre, contract_file, load_bundle,
)

DTYPE_DUCKDB = {"integer": "BIGINT", "Int64": "BIGINT", "double": "DOUBLE", "string": "VARCHAR",
                "boolean": "BOOLEAN"}


def source_name(domain: str) -> str:
    return f"datafeed_{domain}"


def build_tables(domain: str, contract: dict, manifest: dict) -> list:
    """Allowlist = contract datasets whose CSV is in the manifest; types from the contract."""
    tables = []
    for dataset in contract["datasets"]:
        file_name = f"{dataset['name']}.csv"
        if file_name not in manifest["files"]:
            raise SystemExit(f"ABORT: {file_name} ไม่อยู่ใน manifest")
        tables.append({
            "table_name": f"feed_{domain}_{dataset['name']}",
            "file_name": file_name,
            "columns": [{"name": c["name"], "type": DTYPE_DUCKDB[c["dtype"]]} for c in dataset["columns"]],
            "sha256": manifest["files"][file_name]["sha256"],
        })
    return tables


def verify_in_place(latest: Path, domain: str, contract: dict, manifest: dict, tables: list) -> None:
    """Gates 3+4 through the same read-only adapter the assistant will use."""
    from app.services.database_adapter import DuckDBFileAdapter

    with tempfile.TemporaryDirectory() as tmp:
        # manifest already checked by check_integrity_pre — don't hash every file twice
        adapter = DuckDBFileAdapter(f"verify-{domain}", str(latest), tables, tmp)
        for t in tables:
            dataset = t["table_name"][len(f"feed_{domain}_"):]
            got = adapter.execute_query(f'SELECT COUNT(*) AS n FROM "{t["table_name"]}"')[0]["n"]
            expected = manifest["row_counts"].get(dataset)
            if got != expected:
                raise SystemExit(f"ABORT: row count mismatch {t['table_name']}: {got} != {expected}")
        print(f"Row counts OK ({len(tables)} views)")
        check_control_totals(adapter.cursor(), latest, domain, contract)


def register(config_engine, domain: str, root: Path, tables: list, contract_path: Path, schema_version) -> tuple:
    """Registry + knowledge in one transaction → (context, metadata rows, docs)."""
    from sqlalchemy import text
    from app.services.datafeed_knowledge import knowledge_key, load_contract, sync_knowledge

    # knowledge and its key from the same bytes — a contract edited mid-run can't be recorded as synced
    contract, raw = load_contract(str(contract_path))
    with config_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO data_sources (name, source_type, root_path, manifest_file, contract_file, knowledge_sha, "
            "description) VALUES (:name, 'duckdb_file', :root, 'manifest.json', :contract, :key, :desc) "
            "ON CONFLICT(name) DO UPDATE SET source_type='duckdb_file', root_path=excluded.root_path, "
            "manifest_file=excluded.manifest_file, contract_file=excluded.contract_file, "
            "knowledge_sha=excluded.knowledge_sha, description=excluded.description, is_active=1, "
            "updated_at=CURRENT_TIMESTAMP"
        ), {"name": source_name(domain), "root": str(root), "contract": str(contract_path),
            "key": knowledge_key(raw, schema_version), "desc": f"DataFeed {domain} (zero-import)"})
        source_id = conn.execute(
            text("SELECT id FROM data_sources WHERE name = :name"), {"name": source_name(domain)}
        ).scalar_one()
        conn.execute(text("DELETE FROM source_tables WHERE source_id = :sid"), {"sid": source_id})
        for t in tables:
            conn.execute(text(
                "INSERT INTO source_tables (source_id, table_name, file_name, columns, sha256) "
                "VALUES (:sid, :table_name, :file_name, :columns, :sha256)"
            ), {"sid": source_id, **t, "columns": json.dumps(t["columns"])})
        synced = sync_knowledge(conn, domain, contract)  # creates feed_<domain> when missing
        conn.execute(text(
            "UPDATE schema_contexts SET source_id = :sid WHERE name = :ctx"
        ), {"sid": source_id, "ctx": synced[0]})
    return synced


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
    latest, manifest, contract = load_bundle(Path(args.source), args.domain)
    root = latest.absolute()  # not resolve(): a symlinked latest/ must keep following re-points
    print(f"Domain {args.domain}: schema {manifest['schema_version']}, period {manifest['period']}, root {root}")

    check_integrity_pre(latest, manifest, contract["datasets"], bool(contract.get("control_totals")))
    tables = build_tables(args.domain, contract, manifest)
    verify_in_place(root, args.domain, contract, manifest, tables)
    context, n_meta, n_docs = register(config_engine, args.domain, root, tables,
                                       contract_file(Path(args.source), args.domain).absolute(),
                                       manifest.get("schema_version"))
    from app.services.datafeed_knowledge import mark_brain_dirty
    mark_brain_dirty()
    print(f"Knowledge: {context} ({n_meta} metadata rows, {n_docs} docs) — brain marked dirty")
    print(f"Registered source '{source_name(args.domain)}' ({len(tables)} views) → {context} "
          f"in {time.time() - t0:.1f}s — no rows imported")


if __name__ == "__main__":
    main()
