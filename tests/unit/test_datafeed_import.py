"""F10 Phase A: DataFeed importer — integrity gates and dtype preservation."""

import hashlib
import json
import sqlite3

import pytest
import yaml

from scripts.datafeed import import_datafeed as imp


CONTRACT = {
    "schema_version": "1.0.0",
    "domain": "rev",
    "control_totals": {
        "source": "fact_bu",
        "grand_total": {"source": "fact_total", "tolerance_rel": 0.0001, "tolerance_abs": 1.0},
        "period_key": "year_month",
        "bg_key": "bu",
        "measures": [{"name": "revenue", "agg": "sum"}],
    },
    "datasets": [
        {
            "name": "fact_bu",
            "kind": "fact",
            "grain": "bu x month",
            "keys": ["year_month", "bu"],
            "columns": [
                {"name": "year_month", "dtype": "integer", "null_ok": False, "description": "งวด"},
                {"name": "bu", "dtype": "string", "null_ok": False, "description": "BG"},
                {"name": "bu_code", "dtype": "string", "null_ok": False, "description": "รหัส"},
                {"name": "revenue", "dtype": "double", "null_ok": False, "description": "รายได้"},
            ],
        },
        {
            "name": "fact_total",
            "kind": "fact",
            "grain": "month",
            "keys": ["year_month"],
            "columns": [
                {"name": "year_month", "dtype": "integer", "null_ok": False},
                {"name": "revenue", "dtype": "double", "null_ok": False},
            ],
        },
    ],
}


def _write_bundle(tmp_path, *, tamper_sha=False, wrong_rowcount=False, bad_control=False):
    latest = tmp_path / "dist" / "rev" / "latest"
    latest.mkdir(parents=True)
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "rev.yaml").write_text(yaml.safe_dump(CONTRACT, allow_unicode=True))

    fact_bu = "year_month,bu,bu_code,revenue\n202401,A,007,100.5\n202401,B,010,200.0\n202402,A,007,50.0\n"
    fact_total = "year_month,revenue\n202401,300.5\n202402,50.0\n"
    control_value = "999999" if bad_control else "300.5"
    controls = (
        "bu_seq,bu,year_month,measure,value\n"
        f"1,A,202401,revenue,100.5\n2,B,202401,revenue,200.0\n1,A,202402,revenue,50.0\n"
        f"0,__ALL__,202401,revenue,{control_value}\n0,__ALL__,202402,revenue,50.0\n"
    )
    (latest / "fact_bu.csv").write_text(fact_bu)
    (latest / "fact_total.csv").write_text(fact_total)
    (latest / "control_totals.csv").write_text(controls)

    def sha(name):
        return hashlib.sha256((latest / name).read_bytes()).hexdigest()

    manifest = {
        "domain": "rev", "schema_version": "1.0.0", "period": "202402", "built_at": "x",
        "reconcile": {"ok": True},
        "files": {
            "fact_bu.csv": {"sha256": "0" * 64 if tamper_sha else sha("fact_bu.csv")},
            "fact_total.csv": {"sha256": sha("fact_total.csv")},
            "control_totals.csv": {"sha256": sha("control_totals.csv")},
        },
        "row_counts": {"fact_bu": 99 if wrong_rowcount else 3, "fact_total": 2},
    }
    (latest / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path / "dist"


def _run_import(source, db_path, allow_schema_change=False):
    latest, manifest, contract = imp.load_bundle(source, "rev")
    imp.check_integrity_pre(latest, manifest, contract["datasets"])
    conn = sqlite3.connect(db_path)
    try:
        imp.check_schema_version(conn, "rev", str(manifest["schema_version"]), allow_schema_change)
        conn.execute("BEGIN")
        total = imp.import_datasets(conn, latest, "rev", contract, manifest)
        imp.check_control_totals(conn, latest, "rev", contract)
        conn.execute(
            "INSERT INTO feed_import_log (domain, schema_version, period, built_at, row_total, status) "
            "VALUES (?, ?, ?, ?, ?, 'ok')",
            ("rev", str(manifest["schema_version"]), str(manifest["period"]), "x", total),
        )
        conn.commit()
        return total
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


class TestDataFeedImport:
    def test_happy_path(self, tmp_path):
        source = _write_bundle(tmp_path)
        db = tmp_path / "biz.sqlite"
        total = _run_import(source, db)
        assert total == 5

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT COUNT(*) FROM feed_rev_fact_bu").fetchone()[0] == 3
        # string dtype preserved: leading zero intact
        assert conn.execute("SELECT bu_code FROM feed_rev_fact_bu WHERE bu='A' LIMIT 1").fetchone()[0] == "007"
        assert conn.execute("SELECT status FROM feed_import_log").fetchone()[0] == "ok"

    def test_sha_mismatch_aborts(self, tmp_path):
        source = _write_bundle(tmp_path, tamper_sha=True)
        with pytest.raises(SystemExit, match="sha256 mismatch"):
            _run_import(source, tmp_path / "biz.sqlite")

    def test_wrong_rowcount_rolls_back(self, tmp_path):
        source = _write_bundle(tmp_path, wrong_rowcount=True)
        db = tmp_path / "biz.sqlite"
        # Pre-existing table must survive the rollback
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE feed_rev_fact_bu (old_col TEXT)")
        conn.execute("INSERT INTO feed_rev_fact_bu VALUES ('keep')")
        conn.commit()
        conn.close()

        with pytest.raises(SystemExit, match="row count mismatch"):
            _run_import(source, db)

        conn = sqlite3.connect(db)
        assert conn.execute("SELECT old_col FROM feed_rev_fact_bu").fetchone()[0] == "keep"

    def test_missing_rowcount_entry_rolls_back(self, tmp_path):
        """A dataset absent from manifest.row_counts must fail the gate, not skip it."""
        source = _write_bundle(tmp_path)
        manifest_path = source / "rev" / "latest" / "manifest.json"
        m = json.loads(manifest_path.read_text())
        del m["row_counts"]["fact_bu"]
        manifest_path.write_text(json.dumps(m))

        with pytest.raises(SystemExit, match="missing entry"):
            _run_import(source, tmp_path / "biz.sqlite")

    def test_bad_control_total_rolls_back(self, tmp_path):
        source = _write_bundle(tmp_path, bad_control=True)
        db = tmp_path / "biz.sqlite"
        with pytest.raises(SystemExit, match="control totals failed"):
            _run_import(source, db)
        conn = sqlite3.connect(db)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'feed_rev_%'")]
        assert "feed_rev_fact_bu" not in tables  # rollback removed it

    def test_schema_change_requires_flag(self, tmp_path):
        source = _write_bundle(tmp_path)
        db = tmp_path / "biz.sqlite"
        _run_import(source, db)

        # Bump schema version in manifest
        manifest_path = source / "rev" / "latest" / "manifest.json"
        m = json.loads(manifest_path.read_text())
        m["schema_version"] = "2.0.0"
        manifest_path.write_text(json.dumps(m))

        with pytest.raises(SystemExit, match="schema_version"):
            _run_import(source, db)
        _run_import(source, db, allow_schema_change=True)  # flag allows it
