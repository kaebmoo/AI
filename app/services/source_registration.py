"""
Registering a DataFeed bundle as a file source (Plan 7 Phase 1–2; moved here from scripts/ in Phase 4c)
========================================================================================================
One implementation for the CLI (scripts/datafeed/register_file_source.py, import_datafeed.py) and
the admin API (POST /admin/sources/register). The registry is written only after every gate passed:

1. manifest reconcile.ok   2. sha256 of every file used (allowlist = contract datasets in the manifest)
3. row counts through the views   4. control totals through the views (contract spec: filter, bg_key, grand_total)

A failed gate raises GateError and leaves the registry untouched. The functions print their progress:
the CLI shows it, and the importer's tests read it.
"""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional

import pandas as pd
import yaml

from app.services.database_adapter import DuckDBFileAdapter


class GateError(Exception):
    """A bundle failed an integrity gate, or the request can't be registered — nothing was written."""


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
        raise GateError("ABORT: manifest reconcile.ok != true — feed ไม่ผ่าน gate ของตัวเอง")
    # a contract without control_totals (e.g. ebt) ships no control_totals.csv
    files_to_check = [f"{d['name']}.csv" for d in datasets] + (["control_totals.csv"] if with_controls else [])
    for fname in files_to_check:
        expected = manifest["files"].get(fname, {}).get("sha256")
        if not expected:
            raise GateError(f"ABORT: {fname} ไม่อยู่ใน manifest")
        actual = sha256_file(latest / fname)
        if actual != expected:
            raise GateError(f"ABORT: sha256 mismatch: {fname}")
    print(f"Integrity pre-check OK ({len(files_to_check)} files)")


def check_control_totals(conn, latest: Path, domain: str, contract: dict) -> None:
    """Gate 4: re-verify every control_totals.csv row against the actual rows (tables or views).

    One GROUP BY per measure (not one scan per row — fact_expense is ~150 MB of CSV).
    ``__ALL__`` rows: the grand-total dataset when the contract has one, else the source summed.
    ``filter`` ({column: value}, sales metric='actual') narrows the source before aggregating.
    No ``bg_key`` (ebt) = a total-only source: every control row is that period's total.
    """
    spec = contract.get("control_totals")
    if not spec:
        print("Control totals: none in contract — gate skipped")
        return
    grand = spec.get("grand_total") or {}
    source_table = f"feed_{domain}_{spec['source']}"
    grand_table = f"feed_{domain}_{grand['source']}" if grand else source_table
    period_key = spec.get("period_key", "year_month")
    bg_key = spec.get("bg_key")
    tol_rel = grand.get("tolerance_rel", spec.get("tolerance_rel", 1e-4))
    tol_abs = grand.get("tolerance_abs", spec.get("tolerance_abs", 1.0))
    filters = spec.get("filter") or {}
    where = " WHERE " + " AND ".join(f'"{c}" = ?' for c in filters) if filters else ""
    params = list(filters.values())

    controls = pd.read_csv(latest / "control_totals.csv", dtype={bg_key: str} if bg_key else None)
    actual = {}
    for measure in controls["measure"].unique():
        if bg_key:
            for bu, period, value in conn.execute(
                f'SELECT "{bg_key}", "{period_key}", SUM("{measure}") FROM "{source_table}"{where} GROUP BY 1, 2',
                params,
            ).fetchall():
                if period is not None:
                    actual[(measure, str(bu), int(period))] = value
        # the filter names columns of the source — a separate grand-total dataset is already the total
        grand_where, grand_params = (where, params) if grand_table == source_table else ("", [])
        for period, value in conn.execute(
            f'SELECT "{period_key}", SUM("{measure}") FROM "{grand_table}"{grand_where} GROUP BY 1', grand_params
        ).fetchall():
            if period is not None:
                actual[(measure, "__ALL__", int(period))] = value

    failures = []
    for _, row in controls.iterrows():
        measure, expected, period = row["measure"], float(row["value"]), row[period_key]
        bu = row[bg_key] if bg_key else "__ALL__"
        got = actual.get((measure, str(bu), int(period))) or 0.0
        if abs(got - expected) > max(tol_abs, tol_rel * abs(expected)):
            failures.append(f"{bu} {period} {measure}: db={got} expected={expected}")

    if failures:
        for f in failures[:10]:
            print(f"  CONTROL FAIL: {f}")
        raise GateError(f"ROLLBACK: control totals failed {len(failures)}/{len(controls)} rows")
    print(f"Control totals OK ({len(controls)} rows within tolerance)")


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
            raise GateError(f"ABORT: {file_name} ไม่อยู่ใน manifest")
        tables.append({
            "table_name": f"feed_{domain}_{dataset['name']}",
            "file_name": file_name,
            "columns": [{"name": c["name"], "type": DTYPE_DUCKDB[c["dtype"]]} for c in dataset["columns"]],
            "sha256": manifest["files"][file_name]["sha256"],
        })
    return tables


def verify_in_place(latest: Path, domain: str, contract: dict, manifest: dict, tables: list) -> None:
    """Gates 3+4 through the same read-only adapter the assistant will use."""
    with tempfile.TemporaryDirectory() as tmp:
        # manifest already checked by check_integrity_pre — don't hash every file twice
        adapter = DuckDBFileAdapter(f"verify-{domain}", str(latest), tables, tmp)
        for t in tables:
            dataset = t["table_name"][len(f"feed_{domain}_"):]
            got = adapter.execute_query(f'SELECT COUNT(*) AS n FROM "{t["table_name"]}"')[0]["n"]
            expected = manifest["row_counts"].get(dataset)
            if got != expected:
                raise GateError(f"ABORT: row count mismatch {t['table_name']}: {got} != {expected}")
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


def dist_of_registered(config_engine, domain: str) -> Optional[Path]:
    """<dist> of an already registered domain (root_path = <dist>/<domain>/latest)."""
    from sqlalchemy import text

    with config_engine.connect() as conn:
        root = conn.execute(text("SELECT root_path FROM data_sources WHERE name = :n AND source_type = 'duckdb_file'"),
                            {"n": source_name(domain)}).scalar()
    return Path(root).parents[1] if root else None


def allowed_dist(source_dir: str, allowed_roots: List[str]) -> Path:
    """The caller-supplied <dist> directory, only when it lies under a configured root (realpath):
    the server reads whatever this points at, so an admin API must not take arbitrary paths."""
    real = os.path.realpath(source_dir)
    for root in allowed_roots:
        root_real = os.path.realpath(root)
        if root and (real == root_real or real.startswith(root_real.rstrip(os.sep) + os.sep)):
            return Path(source_dir)
    raise GateError(f"path อยู่นอก DATA_SOURCE_ALLOWED_ROOTS: {source_dir}")


def register_domain(config_engine, domain: str, source: Path) -> dict:
    """All gates, then registry + knowledge in one transaction. → summary for the caller."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", domain or ""):  # becomes part of table names and paths
        raise GateError(f"domain ไม่ถูกต้อง: {domain!r}")
    try:
        latest, manifest, contract = load_bundle(source, domain)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise GateError(f"อ่าน bundle ของ '{domain}' ไม่ได้: {exc}") from exc
    if contract.get("domain") != domain:
        raise GateError(f"contract เป็นของ domain '{contract.get('domain')}' ไม่ใช่ '{domain}'")
    root = latest.absolute()  # not resolve(): a symlinked latest/ must keep following re-points
    check_integrity_pre(latest, manifest, contract["datasets"], bool(contract.get("control_totals")))
    tables = build_tables(domain, contract, manifest)
    verify_in_place(root, domain, contract, manifest, tables)
    try:
        context, n_meta, n_docs = register(config_engine, domain, root, tables,
                                           contract_file(source, domain).absolute(), manifest.get("schema_version"))
    except KeyError as exc:  # rolled back with the transaction
        raise GateError(f"contract ของ '{domain}' ขาด field {exc}") from exc
    from app.services.datafeed_knowledge import mark_brain_dirty
    mark_brain_dirty()
    return {"source": source_name(domain), "context": context, "root": str(root), "views": len(tables),
            "schema_version": manifest.get("schema_version"), "period": manifest.get("period"),
            "build_id": manifest.get("build_id"), "metadata_rows": n_meta, "docs": n_docs}
