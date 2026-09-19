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


class TestContractDrivenControls:
    """Plan 7 Phase 2: expense/sales have no grand-total dataset, ebt has no control totals."""

    NO_GRAND = {**CONTRACT, "control_totals": {**CONTRACT["control_totals"], "grand_total": None,
                                               "tolerance_rel": 0.0001, "tolerance_abs": 1.0}}

    def _db(self, tmp_path):
        source = _write_bundle(tmp_path)
        latest, manifest, _ = imp.load_bundle(source, "rev")
        conn = sqlite3.connect(":memory:")
        imp.import_datasets(conn, latest, "rev", CONTRACT, manifest)
        return conn, latest

    def test_all_row_sums_the_source_without_grand_total(self, tmp_path, capsys):
        conn, latest = self._db(tmp_path)
        imp.check_control_totals(conn, latest, "rev", self.NO_GRAND)  # __ALL__ 300.5 = A 100.5 + B 200
        assert "5 rows within tolerance" in capsys.readouterr().out
        conn.execute("UPDATE feed_rev_fact_bu SET revenue = 0 WHERE bu = 'B'")
        with pytest.raises(SystemExit):  # B and __ALL__ of 202401 now off
            imp.check_control_totals(conn, latest, "rev", self.NO_GRAND)

    def test_contract_without_control_totals(self, tmp_path, capsys):
        conn, latest = self._db(tmp_path)
        (latest / "control_totals.csv").unlink()  # ebt ships none
        no_controls = {k: v for k, v in CONTRACT.items() if k != "control_totals"}
        manifest = json.loads((latest / "manifest.json").read_text())
        del manifest["files"]["control_totals.csv"]
        imp.check_integrity_pre(latest, manifest, no_controls["datasets"], with_controls=False)
        imp.check_control_totals(conn, latest, "rev", no_controls)
        assert "gate skipped" in capsys.readouterr().out

    def test_golden_follows_the_contract(self):
        import pandas as pd
        from scripts.datafeed.gen_golden_from_controls import build_examples

        controls = pd.DataFrame({"bu": ["A", "__ALL__"], "year_month": [202401, 202401],
                                 "measure": ["revenue", "revenue"], "value": [100.5, 300.5]})
        with_grand = [sql for _, sql in build_examples(controls, "rev", CONTRACT)]
        assert with_grand == ["SELECT revenue FROM feed_rev_fact_total WHERE year_month = 202401",
                              "SELECT revenue FROM feed_rev_fact_bu WHERE bu = 'A' AND year_month = 202401"]
        finer = {**self.NO_GRAND, "datasets": [{**CONTRACT["datasets"][0], "keys": ["year_month", "bu", "bu_code"]}]}
        assert [sql for _, sql in build_examples(controls, "rev", finer)] == [
            "SELECT SUM(revenue) FROM feed_rev_fact_bu WHERE year_month = 202401",
            "SELECT SUM(revenue) FROM feed_rev_fact_bu WHERE bu = 'A' AND year_month = 202401"]
        assert build_examples(None, "ebt", {"datasets": []}) == []


class TestControlTotalsFilterAndTotalOnly:
    """NT-Report sales 1.2.0 (control_totals.filter) and ebt 1.2.0 (total-only source, no bg_key)."""

    SALES = {"domain": "s", "control_totals": {
        "source": "fact_sales", "grand_total": None, "period_key": "year_month", "bg_key": "bg",
        "group_keys": ["bg", "year_month"], "filter": {"metric": "actual"},
        "measures": [{"name": "amount", "agg": "sum"}]},
        "datasets": [{"name": "fact_sales", "keys": ["year_month", "bg", "metric", "cost_center"], "columns": []}]}
    EBT = {"domain": "e", "control_totals": {
        "source": "fact_total", "grand_total": {"source": "fact_total"}, "period_key": "time_key",
        "group_keys": ["time_key"],
        "measures": [{"name": "sales_base_revenue", "agg": "sum"}, {"name": "expense", "agg": "sum"},
                     {"name": "ebt", "agg": "sum"}]},
        "datasets": [{"name": "fact_total", "keys": ["time_key"], "columns": []}]}

    def test_filter_applies_before_aggregate(self, tmp_path, capsys):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE feed_s_fact_sales (year_month INTEGER, bg TEXT, metric TEXT, amount REAL)")
        conn.executemany("INSERT INTO feed_s_fact_sales VALUES (?,?,?,?)", [
            (202607, "A", "actual", 100.0), (202607, "A", "target", 900.0), (202607, "B", "actual", 50.0)])
        (tmp_path / "control_totals.csv").write_text(
            "bg,year_month,measure,value\nA,202607,amount,100.0\nB,202607,amount,50.0\n__ALL__,202607,amount,150.0\n")
        imp.check_control_totals(conn, tmp_path, "s", self.SALES)  # target rows must not count
        assert "3 rows within tolerance" in capsys.readouterr().out
        conn.execute("UPDATE feed_s_fact_sales SET amount = 0 WHERE bg = 'B'")
        with pytest.raises(SystemExit):
            imp.check_control_totals(conn, tmp_path, "s", self.SALES)

    def test_total_only_source_without_bg_key(self, tmp_path, capsys):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE feed_e_fact_total (time_key INTEGER, sales_base_revenue REAL, expense REAL, ebt REAL)")
        conn.execute("INSERT INTO feed_e_fact_total VALUES (202607, 300.0, 400.0, -100.0)")
        (tmp_path / "control_totals.csv").write_text(
            "time_key,measure,value\n202607,ebt,-100.0\n202607,expense,400.0\n202607,sales_base_revenue,300.0\n")
        imp.check_control_totals(conn, tmp_path, "e", self.EBT)
        assert "3 rows within tolerance" in capsys.readouterr().out
        conn.execute("UPDATE feed_e_fact_total SET ebt = 100.0")  # a sign flip is the bug this guards
        with pytest.raises(SystemExit):
            imp.check_control_totals(conn, tmp_path, "e", self.EBT)

    def test_golden_carries_the_filter(self):
        import pandas as pd
        from scripts.datafeed.gen_golden_from_controls import build_examples

        controls = pd.DataFrame({"bg": ["A", "__ALL__"], "year_month": [202607, 202607],
                                 "measure": ["amount", "amount"], "value": [100.0, 150.0]})
        assert [sql for _, sql in build_examples(controls, "s", self.SALES)] == [
            "SELECT SUM(amount) FROM feed_s_fact_sales WHERE year_month = 202607 AND metric = 'actual'",
            "SELECT SUM(amount) FROM feed_s_fact_sales WHERE bg = 'A' AND year_month = 202607 AND metric = 'actual'"]

    def test_golden_of_total_only_source_asks_every_measure(self):
        import pandas as pd
        from scripts.datafeed.gen_golden_from_controls import build_examples

        controls = pd.DataFrame({"time_key": [202607] * 3, "measure": ["ebt", "expense", "sales_base_revenue"],
                                 "value": [-100.0, 400.0, 300.0]})
        examples = build_examples(controls, "e", self.EBT)
        assert [sql for _, sql in examples] == [
            f"SELECT {m} FROM feed_e_fact_total WHERE time_key = 202607"
            for m in ("sales_base_revenue", "expense", "ebt")]
        assert len({q for q, _ in examples}) == 3  # one distinct question per measure

    def test_golden_asks_monthly_and_ytd_measures_differently(self):
        """ebt 1.3.0: ebt = YTD, ebt_month = the month. A question that says 'เดือน' for a YTD
        value scores a wrong-meaning answer as right."""
        import pandas as pd
        from scripts.datafeed.gen_golden_from_controls import build_examples

        spec = {**self.EBT["control_totals"], "measures": [
            {"name": "ebt", "agg": "sum"}, {"name": "ebt_month", "agg": "sum"},
            {"name": "other_ytd", "agg": "point_in_time", "note": "ยอดอื่น, บาท"}]}
        controls = pd.DataFrame({"time_key": [202607] * 3, "measure": ["ebt", "ebt_month", "other_ytd"], "value": [1.0, 2.0, 3.0]})
        q = {sql.split()[1]: question for question, sql in build_examples(controls, "e", {**self.EBT, "control_totals": spec})}
        assert "สะสม" in q["ebt"] and "สะสม" not in q["ebt_month"] and "ของเดือนกรกฎาคม 2569" in q["ebt_month"]
        assert "สะสม" in q["other_ytd"] and q["other_ytd"].startswith("ยอดอื่น")  # unknown measure: note + agg


def test_golden_of_a_grouped_source_with_several_measures_asks_each_one():
    """ebt 1.4.0: control totals per division (bg_key) with six measures — YTD and monthly of three
    figures. Asking only the first of each kind (the revenue shape) left expense/ebt and every
    per-division figure unmeasured."""
    import pandas as pd
    from scripts.datafeed.gen_golden_from_controls import build_examples

    contract = {"domain": "ebt", "title": "EBT feed", "control_totals": {
        "source": "fact_div", "grand_total": {"source": "fact_total"}, "period_key": "time_key", "bg_key": "division",
        "group_keys": ["division", "time_key"],
        "measures": [{"name": "ebt", "agg": "point_in_time"}, {"name": "ebt_month", "agg": "sum"},
                     {"name": "expense_month", "agg": "sum"}]},
        "datasets": [{"name": "fact_div", "keys": ["division", "time_key"], "columns": []}]}
    rows = [(d, t, m, 1.0) for t in (202606, 202607) for m in ("ebt", "ebt_month", "expense_month")
            for d in ("สายงาน 1", "สายงาน 2", "__ALL__")]
    controls = pd.DataFrame(rows, columns=["division", "time_key", "measure", "value"])
    examples = dict(build_examples(controls, "ebt", contract))
    sqls = set(examples.values())
    for m in ("ebt", "ebt_month", "expense_month"):  # every measure: both periods in total, the latest per division
        assert {f"SELECT {m} FROM feed_ebt_fact_total WHERE time_key = {t}" for t in (202606, 202607)} <= sqls
        assert f"SELECT {m} FROM feed_ebt_fact_div WHERE division = 'สายงาน 1' AND time_key = 202607" in sqls
    assert len(examples) == 3 * 2 + 3 * 2
    by_sql = {sql: q for q, sql in examples.items()}
    assert "สะสม" in by_sql["SELECT ebt FROM feed_ebt_fact_div WHERE division = 'สายงาน 2' AND time_key = 202607"]
    assert "ของเดือนกรกฎาคม 2569" in by_sql["SELECT ebt_month FROM feed_ebt_fact_total WHERE time_key = 202607"]
    assert all("สายงาน สายงาน" in q for q, sql in examples.items() if "fact_div" in sql)  # group noun + label
