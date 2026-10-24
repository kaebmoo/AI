"""Synthetic parquet checks for the metric question generator and CLI.

Usage: python -m pytest tests/unit/test_gen_metric_questions.py -q
"""

from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import duckdb
import pytest
import yaml

from app.services.ai import metric_compiler
from scripts.eval.metric_eval_lib import contract_metrics, generate, open_dist


ROOT = Path(__file__).resolve().parents[2]
S1 = "สายงานขายและปฏิบัติการลูกค้า 1"
S2 = "สายงานขายและปฏิบัติการลูกค้า 2"
NAN = "ส่วนขายและบริการลูกค้า น่าน"
DIMS = ("division", "unit", "sub_unit", "cost_center")


@pytest.fixture
def contract():
    fixture = yaml.safe_load((ROOT / "tests/fixtures/ebt_metrics_1_6_0.yaml").read_text(encoding="utf-8"))
    return {"domain": "ebt", "schema_version": fixture["schema_version"], "metrics": fixture["metrics"],
            "datasets": [{"name": "fact_ebt", "columns": [
                {"name": "division", "description": "สายงาน — ระดับ 1; รายละเอียด"},
                {"name": "unit", "description": "ฝ่าย; ระดับ 3"},
                {"name": "sub_unit", "description": "ส่วน — ระดับ 4"},
                {"name": "cost_center", "description": "ศูนย์ต้นทุน"},
            ]}]}


@pytest.fixture
def dist(tmp_path):
    rows = []

    def add(division, sub_unit, measure_type, group_1, amount, ytd, group_0=""):
        rows.append((202609, division, sub_unit, measure_type, group_0, group_1, amount, ytd))

    add(S1, NAN, "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 10, 100)
    add(S1, NAN, "ADDITIVE", "08.รายได้อื่น", 1, 5)
    add(S1, NAN, "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 6, 60)
    add(S1, NAN, "ADDITIVE", "01.ค่าใช้จ่ายตอบแทนแรงงาน", 2, 20, "02.ค่าใช้จ่าย")
    add(S1, NAN, "ADDITIVE", "02.ค่าสวัสดิการ", 0.3, 3, "02.ค่าใช้จ่าย")
    add(S1, NAN, "ADDITIVE", "03.ค่าใช้จ่ายพัฒนาและฝึกอบรมบุคลากร", 0.1, 1, "02.ค่าใช้จ่าย")
    add(S1, "ส่วน X", "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 20, 200)
    add(S1, "ส่วน X", "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 15, 150)
    add(S1, "ส่วน X", "ADDITIVE", "01.ค่าใช้จ่ายตอบแทนแรงงาน-ER", 1, 10, "02.ค่าใช้จ่าย")
    add(S1, "ส่วน X", "ADDITIVE", "01.ค่าใช้จ่ายตอบแทนแรงงาน", 3, 30, "02.ค่าใช้จ่าย")
    add(S1, "ส่วน X", "COMPUTED", "3.1 กำไร (ขาดทุน) ของส่วนงาน (1)-(2)", 99, 999)
    add(S2, "ส่วน Y", "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 30, 300)
    add(S2, "ส่วน Y", "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 10, 100)
    add(S2, "ส่วน Y", "ADDITIVE", "02.ค่าสวัสดิการ", 5, 50, "02.ค่าใช้จ่าย")
    add("สายงานอื่น", "ส่วน Z", "SUBTOTAL", "รวมรายได้ทั้งสิ้น", 100, 1000)
    add("สายงานอื่น", "ส่วน Z", "SUBTOTAL", "รวมค่าใช้จ่ายทั้งสิ้น", 10, 100)
    rows += [(202608, *r[1:6], 10000, 100000) for r in rows[:4]]
    dist_dir = tmp_path / "dist's parquet"
    dist_dir.mkdir()
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE fact (time_key INTEGER, division TEXT, sub_unit TEXT, "
                     "measure_type TEXT, group_0 TEXT, group_1 TEXT, amount DOUBLE, amount_ytd DOUBLE, "
                     "unit TEXT, unit_fname TEXT, unit_short_name TEXT, cost_center TEXT, is_hq INTEGER)")
        enriched = []
        for row in rows:
            unit = {S1: "ฝ่าย A", S2: "ฝ่าย B", "สายงานอื่น": "ฝ่าย O'Brien"}[row[1]]
            enriched.append((*row, unit, unit + " เต็ม", unit + " ย่อ", "CC " + row[2], 0))
        conn.executemany("INSERT INTO fact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", enriched)
        path = str(dist_dir / "fact_ebt.parquet").replace("'", "''")
        conn.execute(f"COPY (SELECT * FROM fact) TO '{path}' (FORMAT PARQUET)")
        path = str(dist_dir / "fact_ebt_total_monthly.parquet").replace("'", "''")
        conn.execute(f"COPY (SELECT 202609 AS time_key, 295.0 AS ebt, 29.5 AS ebt_month, "
                     f"399.0 AS ebt_ex_personnel, 39.9 AS ebt_ex_personnel_month) TO '{path}' (FORMAT PARQUET)")
    (dist_dir / "manifest.json").write_text('{"build_id": "synthetic"}', encoding="utf-8")
    return dist_dir


@pytest.fixture
def spec(contract, dist):
    return generate(contract, dist, 202609, contract_name="synthetic.yaml")


def test_product_counts_and_metadata(spec):
    metric_modes, dims, phrasings, filter_values = 3 * 2, len(DIMS), 3, 3
    classes = defaultdict(set)
    for question in spec["questions"]:
        classes[question["shape"]].add(question["class"])
    expected_classes = {"total": metric_modes, **{shape: metric_modes * dims for shape in
                        ("by", "filter", "top5_desc", "top5_asc", "top10_desc", "top10_asc")}}
    assert {shape: len(items) for shape, items in classes.items()} == expected_classes
    expected_questions = {shape: count * phrasings * (filter_values if shape == "filter" else 1)
                          for shape, count in expected_classes.items()}
    assert Counter(q["shape"] for q in spec["questions"]) == expected_questions
    assert len(spec["questions"]) == 594
    assert [q["id"] for q in spec["questions"]] == [f"M{i:04d}" for i in range(1, 595)]
    assert spec["context"] == "feed_ebt" and spec["scope"] is None
    assert spec["request"] == {"include_data": True, "include_sql": True, "max_rows": 50, "source": "eval"}
    assert spec["oracle_build"] == {"period": 202609, "contract": "synthetic.yaml", "schema_version": "1.6.0",
                                     "manifest": {"build_id": "synthetic"}}
    assert "scripts/eval/run_metric_eval.py" in spec["about"]
    assert Counter(s["reason"] for s in spec["skipped"]) == {
        "missing_column": 3 * metric_modes, "name_column": 2 * metric_modes, "not_string": metric_modes,
    }
    assert {q["dimension"] for q in spec["questions"]} == {None, *DIMS}


def test_every_request_replays_the_compiler(spec, contract, dist):
    resolved = metric_compiler.resolve(contract_metrics(contract))
    with open_dist(dist, "ebt") as conn:
        for q in spec["questions"]:
            request = dict(q["request"], dimensions=tuple(q["request"]["dimensions"]),
                           filters=tuple(q["request"]["filters"]))
            req = metric_compiler.CompileRequest(**request)
            compiled = metric_compiler.compile(req, resolved)
            rows = conn.execute(compiled.sql).fetchall()
            actual = [dict(zip(req.dimensions, row[:len(req.dimensions)]),
                           value=round(float(row[-1]), 2) if row[-1] is not None else None) for row in rows]
            if q["ordered"]:
                assert actual == q["expected_rows"]
                values = [row["value"] for row in actual]
                assert values == sorted(values, reverse=req.order_desc)
                assert req.limit in (5, 10)
            else:
                assert sorted(actual, key=str) == sorted(q["expected_rows"], key=str)
            assert q["ordered"] == q["shape"].startswith("top")
            assert q["unit"] == resolved[q["metric_id"]].unit
            assert all(set(row) == {*req.dimensions, "value"} for row in q["expected_rows"])


def test_official_totals_and_phrasings(spec):
    totals = {q["class"]: q["expected_rows"] for q in spec["questions"] if q["shape"] == "total"}
    for metric, cumulative, month in (("ebt", 295.0, 29.5), ("ebt_excluding_personnel", 399.0, 39.9)):
        assert totals[f"total:{metric}:cumulative"] == [{"value": cumulative}]
        assert totals[f"total:{metric}:month"] == [{"value": month}]
    cases = defaultdict(list)
    for q in spec["questions"]:
        cases[json.dumps(q["request"], sort_keys=True)].append(q["question"])
        assert q["time_in_question"] is True and "2569" in q["question"]
        if q["mode"] == "month":
            assert "เดือนกันยายน 2569" in q["question"]
        if q["dimension"]:
            assert {"division": "สายงาน", "unit": "ฝ่าย", "sub_unit": "ส่วน", "cost_center": "ศูนย์ต้นทุน"}[
                q["dimension"]] in q["question"]
        if q["shape"] == "filter":
            assert q["request"]["filters"][0]["value"] in q["question"]
    assert all(len(phrases) == len(set(phrases)) == 3 for phrases in cases.values())


def test_by_questions_use_description_labels(spec):
    questions = [q["question"] for q in spec["questions"] if q["shape"] == "by" and q["dimension"] == "unit"]
    assert questions
    assert all("ฝ่าย" in question and "unit" not in question for question in questions)


@pytest.mark.parametrize("dimension,label,prefixed", [
    ("division", "สายงาน", True),
    ("cost_center", "ศูนย์ต้นทุน", False),
])
def test_filter_questions_name_value_without_repeating_label(spec, dimension, label, prefixed):
    questions = [q for q in spec["questions"] if q["shape"] == "filter" and q["dimension"] == dimension]
    assert questions
    for q in questions:
        value = q["request"]["filters"][0]["value"]
        assert value.startswith(label) is prefixed
        subject = value if prefixed else f"{label} {value}"
        assert value in q["question"]
        assert any(f"{prefix}{subject} " in q["question"] for prefix in ("ของ", "เฉพาะ", "สำหรับ"))
        if prefixed:
            assert f"{label} {value}" not in q["question"]


def test_small_row_limit_skips_by_classes(contract, dist):
    spec = generate(contract, dist, 202609, max_rows=1)
    skipped = [s for s in spec["skipped"] if s["reason"] == "rows>max_rows"]
    assert len(skipped) == 3 * 2 * len(DIMS)
    assert all(s["shape"] == "by" and s["rows"] == (2 if s["dimension"] in ("division", "unit") else 3)
               for s in skipped)
    assert not any(q["shape"] == "by" for q in spec["questions"])
    assert len(spec["questions"]) == 594 - 72


def test_determinism_and_many_phrasings(contract, dist):
    first = generate(contract, dist, 202609, phrasings=25)
    second = generate(contract, dist, 202609, phrasings=25)
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)
    cases = defaultdict(set)
    counts = Counter()
    for q in first["questions"]:
        key = json.dumps(q["request"], sort_keys=True)
        cases[key].add(q["question"])
        counts[key] += 1
    assert all(len(phrases) == counts[key] == 25 for key, phrases in cases.items())


def test_missing_official_table_falls_back_and_manifest_optional(contract, dist):
    (dist / "fact_ebt_total_monthly.parquet").unlink()
    (dist / "manifest.json").unlink()
    spec = generate(contract, dist, 202609)
    assert spec["oracle_build"]["manifest"] is None
    totals = {q["class"]: q for q in spec["questions"] if q["shape"] == "total"}
    assert totals["total:ebt:cumulative"]["expected_rows"] == [{"value": 295.0}]
    assert totals["total:ebt:month"]["expected_rows"] == [{"value": 29.0}]
    assert all(q["request"]["official_total_ok"] is False for q in totals.values())


def test_fewer_filter_values_nulls_and_period_scope(contract, dist):
    simple = deepcopy(contract)
    simple["metrics"] = simple["metrics"][:1]
    simple["metrics"][0]["dimensions"] = ["unit"]
    with duckdb.connect(":memory:") as conn:
        path = str(dist / "fact_ebt.parquet").replace("'", "''")
        conn.execute(f"CREATE TABLE fact AS SELECT * FROM read_parquet('{path}')")
        conn.execute("UPDATE fact SET unit = CASE WHEN time_key = 202608 THEN 'old only' "
                     "WHEN sub_unit = 'ส่วน X' THEN NULL WHEN sub_unit = 'ส่วน Y' THEN '' "
                     "ELSE 'only value' END")
        conn.execute(f"COPY fact TO '{path}' (FORMAT PARQUET)")
    spec = generate(simple, dist, 202609)
    filters = [q for q in spec["questions"] if q["shape"] == "filter"]
    assert len(filters) == 2 * 3
    assert {q["request"]["filters"][0]["value"] for q in filters} == {"only value"}


def test_null_oracle_and_error_class(contract, dist):
    changed = deepcopy(contract)
    changed["metrics"][-1]["expr"] = "ebt / nullif(0, 0)"
    spec = generate(changed, dist, 202609)
    assert all(row["value"] is None for q in spec["questions"] if q["metric_id"] == "ebt_margin"
               for row in q["expected_rows"])
    changed["metrics"][0]["expr"] = "unknown_term"
    with pytest.raises(ValueError, match="total:ebt:month"):
        generate(changed, dist, 202609)


@pytest.mark.parametrize("period", [202613, 202600, "202609", 202609.0, True, None])
def test_invalid_period(contract, dist, period):
    with pytest.raises(ValueError, match="period"):
        generate(contract, dist, period)


def test_missing_dataset(contract, dist):
    (dist / "fact_ebt.parquet").unlink()
    with pytest.raises(ValueError, match="fact_ebt.parquet"):
        generate(contract, dist, 202609)


def test_cli(contract, dist, tmp_path):
    source = tmp_path / "contract.yaml"
    source.write_text(yaml.safe_dump(contract, allow_unicode=True), encoding="utf-8")
    output = tmp_path / "output" / "questions.json"
    args = [sys.executable, "-m", "scripts.eval.gen_metric_questions", "--contract", str(source),
            "--dist", str(dist), "--period", "202609", "--out", str(output)]
    success = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    assert success.returncode == 0, success.stderr
    assert "Classes: 150; questions: 594" in success.stdout
    assert "Questions per shape:" in success.stdout and "Skipped per reason:" in success.stdout
    assert str(output) in success.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == generate(
        contract, dist, 202609, contract_name=str(source))
    bad_period = args.copy()
    bad_period[bad_period.index("--period") + 1] = "202613"
    invalid = subprocess.run(bad_period, cwd=ROOT, text=True, capture_output=True)
    assert invalid.returncode != 0 and "period" in invalid.stderr
    (dist / "fact_ebt.parquet").unlink()
    missing = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    assert missing.returncode != 0 and "fact_ebt.parquet" in missing.stderr
    for result in (invalid, missing):
        assert "Traceback" not in result.stderr and len(result.stderr.splitlines()) == 1
