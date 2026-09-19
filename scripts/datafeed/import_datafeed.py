"""
DataFeed → business DB importer (PLAN F10 Phase A)
===================================================
Sole writer of feed_* tables. Runs manually / monthly after the feed build.
The assistant only ever READS these tables (read-only connection, F4).

Integrity gates (any failure = rollback, nothing changes):
1. manifest reconcile.ok must be true
2. sha256 of every file used must match the manifest
3. row counts per table must match manifest.row_counts
4. control totals re-checked against the actual imported DB rows

Usage:
    python -m scripts.datafeed.import_datafeed --domain revenue \
        --source /path/to/DataFeed/dist [--db nt_fi_report.sqlite] [--allow-schema-change]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services import source_registration as _registration  # noqa: E402

CHUNK = 50_000
DTYPE_SQL = {"integer": "INTEGER", "Int64": "INTEGER", "double": "REAL", "string": "TEXT", "boolean": "INTEGER"}


def _cli(fn):
    """The gates live in app/services/source_registration.py (shared with the admin API) and raise
    GateError; on the command line a failed gate ends the run, as it always did."""
    import functools

    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _registration.GateError as exc:
            raise SystemExit(str(exc)) from exc
    return run


sha256_file = _registration.sha256_file
contract_file = _registration.contract_file
load_bundle = _registration.load_bundle
check_integrity_pre = _cli(_registration.check_integrity_pre)
check_control_totals = _cli(_registration.check_control_totals)


def csv_dtypes(dataset: dict) -> dict:
    """dtype map from contract — code columns MUST stay strings (leading zeros)."""
    return {c["name"]: str for c in dataset["columns"] if c["dtype"] == "string"}


def create_table_sql(table: str, dataset: dict) -> str:
    cols = ", ".join(
        f'"{c["name"]}" {DTYPE_SQL.get(c["dtype"], "TEXT")}' for c in dataset["columns"]
    )
    return f'CREATE TABLE "{table}" ({cols})'


def check_schema_version(conn, domain: str, version: str, allow_change: bool) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS feed_import_log ("
        "id INTEGER PRIMARY KEY, domain TEXT, schema_version TEXT, period TEXT, "
        "built_at TEXT, imported_at TEXT DEFAULT CURRENT_TIMESTAMP, row_total INTEGER, status TEXT)"
    )
    row = conn.execute(
        "SELECT schema_version FROM feed_import_log WHERE domain=? AND status='ok' "
        "ORDER BY id DESC LIMIT 1", (domain,)
    ).fetchone()
    if row and row[0] != version and not allow_change:
        raise SystemExit(
            f"ABORT: schema_version เปลี่ยน ({row[0]} → {version}) — "
            f"ต้องใส่ --allow-schema-change และรัน gen_docs_from_contract ใหม่ด้วย"
        )


def import_datasets(conn, latest: Path, domain: str, contract: dict, manifest: dict) -> int:
    total = 0
    for dataset in contract["datasets"]:
        name = dataset["name"]
        table = f"feed_{domain}_{name}"
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute(create_table_sql(table, dataset))

        cols = [c["name"] for c in dataset["columns"]]
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(f'"{c}"' for c in cols)
        inserted = 0
        for chunk in pd.read_csv(latest / f"{name}.csv", dtype=csv_dtypes(dataset), chunksize=CHUNK):
            chunk = chunk[cols]  # column order per contract
            rows = [tuple(None if pd.isna(v) else v for v in r) for r in chunk.itertuples(index=False)]
            conn.executemany(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})', rows)
            inserted += len(rows)

        expected = manifest["row_counts"].get(name)
        if expected is None:
            # Every table must pass the gate — a missing manifest entry is a failure, not a skip
            raise SystemExit(f"ROLLBACK: manifest.row_counts missing entry for '{name}'")
        if inserted != expected:
            raise SystemExit(f"ROLLBACK: row count mismatch {table}: {inserted} != {expected}")

        for key in dataset.get("keys", []):
            conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_{key}" ON "{table}" ("{key}")')

        total += inserted
        print(f"  {table}: {inserted} rows")
    return total


def main():
    parser = argparse.ArgumentParser(description="Import DataFeed bundle into business DB")
    parser.add_argument("--source", required=True, help="Path to DataFeed/dist (or extracted handoff)")
    parser.add_argument("--domain", required=True, choices=["revenue", "expense", "sales", "ebt"])
    parser.add_argument("--db", default=None, help="Business DB path (default: settings.BUSINESS_DB_PATH)")
    parser.add_argument("--allow-schema-change", action="store_true")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        from app.config import settings
        db_path = settings.BUSINESS_DB_PATH

    import time
    t0 = time.time()
    latest, manifest, contract = load_bundle(Path(args.source), args.domain)
    print(f"Domain {args.domain}: schema {manifest['schema_version']}, period {manifest['period']}")

    check_integrity_pre(latest, manifest, contract["datasets"], bool(contract.get("control_totals")))

    conn = sqlite3.connect(db_path, timeout=60)
    try:
        check_schema_version(conn, args.domain, str(manifest["schema_version"]), args.allow_schema_change)
        conn.execute("BEGIN")
        total = import_datasets(conn, latest, args.domain, contract, manifest)
        check_control_totals(conn, latest, args.domain, contract)
        conn.execute(
            "INSERT INTO feed_import_log (domain, schema_version, period, built_at, row_total, status) "
            "VALUES (?, ?, ?, ?, ?, 'ok')",
            (args.domain, str(manifest["schema_version"]), str(manifest["period"]),
             manifest.get("built_at", ""), total),
        )
        conn.commit()
        print(f"COMMIT: {total} rows in {time.time() - t0:.1f}s")
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
