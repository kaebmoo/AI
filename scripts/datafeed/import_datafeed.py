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
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

CHUNK = 50_000
DTYPE_SQL = {"integer": "INTEGER", "Int64": "INTEGER", "double": "REAL", "string": "TEXT", "boolean": "INTEGER"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def contract_file(source: Path, domain: str) -> Path:
    path = source.parent / "contracts" / f"{domain}.yaml"
    if not path.exists():
        # allow --source pointing at an extracted handoff with contract alongside
        path = source / domain / "latest" / f"{domain}.yaml"
    return path


def load_bundle(source: Path, domain: str):
    latest = source / domain / "latest"
    manifest = json.loads((latest / "manifest.json").read_text())
    contract = yaml.safe_load(contract_file(source, domain).read_text())
    return latest, manifest, contract


def check_integrity_pre(latest: Path, manifest: dict, datasets: list, with_controls: bool = True) -> None:
    if not manifest.get("reconcile", {}).get("ok"):
        raise SystemExit("ABORT: manifest reconcile.ok != true — feed ไม่ผ่าน gate ของตัวเอง")
    # a contract without control_totals (e.g. ebt) ships no control_totals.csv
    files_to_check = [f"{d['name']}.csv" for d in datasets] + (["control_totals.csv"] if with_controls else [])
    for fname in files_to_check:
        expected = manifest["files"].get(fname, {}).get("sha256")
        if not expected:
            raise SystemExit(f"ABORT: {fname} ไม่อยู่ใน manifest")
        actual = sha256_file(latest / fname)
        if actual != expected:
            raise SystemExit(f"ABORT: sha256 mismatch: {fname}")
    print(f"Integrity pre-check OK ({len(files_to_check)} files)")


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


def check_control_totals(conn, latest: Path, domain: str, contract: dict) -> None:
    """Gate 4: re-verify every control_totals.csv row against the actual rows (tables or views).

    One GROUP BY per measure (not one scan per row — fact_expense is ~150 MB of CSV).
    ``__ALL__`` rows: the grand-total dataset when the contract has one, else the source summed.
    """
    spec = contract.get("control_totals")
    if not spec:
        print("Control totals: none in contract — gate skipped")
        return
    grand = spec.get("grand_total") or {}
    source_table = f"feed_{domain}_{spec['source']}"
    grand_table = f"feed_{domain}_{grand['source']}" if grand else source_table
    period_key = spec.get("period_key", "year_month")
    bg_key = spec.get("bg_key", "bu")
    tol_rel = grand.get("tolerance_rel", spec.get("tolerance_rel", 1e-4))
    tol_abs = grand.get("tolerance_abs", spec.get("tolerance_abs", 1.0))

    controls = pd.read_csv(latest / "control_totals.csv", dtype={bg_key: str})
    actual = {}
    for measure in controls["measure"].unique():
        for bu, period, value in conn.execute(
            f'SELECT "{bg_key}", "{period_key}", SUM("{measure}") FROM "{source_table}" GROUP BY 1, 2'
        ).fetchall():
            if period is not None:
                actual[(measure, str(bu), int(period))] = value
        for period, value in conn.execute(
            f'SELECT "{period_key}", SUM("{measure}") FROM "{grand_table}" GROUP BY 1'
        ).fetchall():
            if period is not None:
                actual[(measure, "__ALL__", int(period))] = value

    failures = []
    for _, row in controls.iterrows():
        measure, expected, period, bu = row["measure"], float(row["value"]), row[period_key], row[bg_key]
        got = actual.get((measure, str(bu), int(period))) or 0.0
        if abs(got - expected) > max(tol_abs, tol_rel * abs(expected)):
            failures.append(f"{bu} {period} {measure}: db={got} expected={expected}")

    if failures:
        for f in failures[:10]:
            print(f"  CONTROL FAIL: {f}")
        raise SystemExit(f"ROLLBACK: control totals failed {len(failures)}/{len(controls)} rows")
    print(f"Control totals OK ({len(controls)} rows within tolerance)")


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
