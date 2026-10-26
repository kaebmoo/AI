"""Synthetic revenue grains share the compiler's table choice for questions and oracles."""

from copy import deepcopy
import json
from pathlib import Path

import duckdb
import pytest
import yaml

from app.services.ai import metric_compiler
from scripts.eval.metric_eval_lib import contract_metrics, generate, open_dist


ROOT = Path(__file__).resolve().parents[2]
BG1 = "1.Hard Infrastructure"
BG4 = "4.Fixed Line & Broadband"
BG8 = "8.รายได้อื่น"
DIMS = ("bu", "division_name", "unit_name", "cost_center")


@pytest.fixture
def contract():
    fixture = yaml.safe_load((ROOT / "tests/fixtures/revenue_metrics_draft.yaml").read_text(encoding="utf-8"))
    fixture["metrics"][0]["excluded_words"] = ["เป้า"]
    fixture["datasets"] = [
        {"name": "fact_total_monthly", "columns": []},
        {"name": "fact_bu_monthly", "columns": [
            {"name": "bu", "description": "กลุ่มธุรกิจ — ระดับ BG"},
        ]},
        {"name": "fact_org_monthly", "columns": [
            {"name": "unit_name", "description": "ฝ่าย — ระดับหน่วยงาน"},
        ]},
    ]
    return fixture


@pytest.fixture
def dist(tmp_path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE fact_bu_monthly (year_month INTEGER, bu_seq INTEGER, bu TEXT, "
                     "revenue DOUBLE, revenue_ytd DOUBLE)")
        conn.execute("CREATE TABLE fact_org_monthly (year_month INTEGER, division_name TEXT, unit_name TEXT, "
                     "cost_center TEXT, revenue DOUBLE, revenue_ytd DOUBLE)")
        conn.execute("CREATE TABLE fact_total_monthly (year_month INTEGER, revenue DOUBLE, revenue_ytd DOUBLE)")
        for period in (202508, 202509, 202608, 202609):
            month = period % 100
            scale = 0.5 if period < 202600 else 1
            conn.executemany("INSERT INTO fact_bu_monthly VALUES (?, ?, ?, ?, ?)", [
                (period, 1, BG1, 100 * scale, 100 * month * scale),
                (period, 4, BG4, 200 * scale, 200 * month * scale),
                (period, 8, BG8, 30 * scale, (210 if month == 9 else 30 * month) * scale),
            ])
            conn.executemany("INSERT INTO fact_org_monthly VALUES (?, ?, ?, ?, ?, ?)", [
                (period, "D1", "U1", "C1", 130 * scale, (1110 if month == 9 else 130 * month) * scale),
                (period, "D2", "U2", "C2", 200 * scale, 200 * month * scale),
            ])
            conn.execute("INSERT INTO fact_total_monthly VALUES (?, ?, ?)",
                         [period, 350 * scale, (4000 if month == 9 else 3200) * scale])
        for name in ("fact_bu_monthly", "fact_org_monthly", "fact_total_monthly"):
            path = str(dist_dir / f"{name}.parquet").replace("'", "''")
            conn.execute(f"COPY {name} TO '{path}' (FORMAT PARQUET)")
    return dist_dir


def test_contract_metrics_matches_synced_shapes(contract):
    original = deepcopy(contract)
    metric, = contract_metrics(contract)
    assert metric.dataset is None
    assert isinstance(metric.datasets, tuple)
    assert metric.datasets == tuple(
        {**item, "name": "feed_revenue_" + item["name"]} for item in contract["metrics"][0]["datasets"])
    assert all(isinstance(item, dict) for item in metric.datasets)
    assert metric.excluded_words == ("เป้า",)
    assert metric.dimensions == ("bu_seq", *DIMS)
    assert isinstance(metric.dimensions, tuple)
    assert metric.official_total["dataset"] == "feed_revenue_fact_total_monthly"
    assert contract == original
    del contract["metrics"][0]["excluded_words"]
    assert contract_metrics(contract)[0].excluded_words is None


@pytest.mark.parametrize("compare", [False, True])
def test_shapes_and_every_request_replay_the_compiler(contract, dist, compare):
    spec = generate(contract, dist, 202609, compare=compare)
    shapes = {"by", "filter", "top5_desc", "top5_asc", "top10_desc", "top10_asc"}
    if compare:
        shapes.add("compare_up")
        assert any(q["shape"] == "compare_total" for q in spec["questions"])
    for mode in ("month", "cumulative"):
        for dim in DIMS:
            assert {q["shape"] for q in spec["questions"] if q["dimension"] == dim and q["mode"] == mode} == shapes
    assert spec["skipped"] == [
        {"metric_id": "revenue", "mode": mode, "dimension": "bu_seq", "shape": None, "reason": "not_string"}
        for mode in ("month", "cumulative")
    ]
    resolved = metric_compiler.resolve(contract_metrics(contract))
    with open_dist(dist, "revenue") as conn:
        for q in spec["questions"]:
            request = dict(q["request"], dimensions=tuple(q["request"]["dimensions"]),
                           filters=tuple(q["request"]["filters"]))
            req = metric_compiler.CompileRequest(**request)
            compiled = metric_compiler.compile(req, resolved)
            table = "fact_total_monthly" if q["dimension"] is None else (
                "fact_bu_monthly" if q["dimension"] == "bu" else "fact_org_monthly")
            assert compiled.table == "feed_revenue_" + table
            rows = conn.execute(compiled.sql).fetchall()
            actual = [dict(zip(req.dimensions, row[:len(req.dimensions)]),
                           value=round(float(row[-1]), 2) if row[-1] is not None else None) for row in rows]
            if q["ordered"]:
                assert actual == q["expected_rows"]
            else:
                assert sorted(actual, key=str) == sorted(q["expected_rows"], key=str)


@pytest.mark.parametrize("dim,label,values", [
    ("bu", "กลุ่มธุรกิจ", {BG1, BG4, BG8}),
    ("unit_name", "ฝ่าย", {"U1", "U2"}),
])
def test_filter_values_and_labels_come_from_the_dimensions_table(contract, dist, dim, label, values):
    spec = generate(contract, dist, 202609)
    questions = [q for q in spec["questions"] if q["dimension"] == dim]
    filters = [q for q in questions if q["shape"] == "filter"]
    assert {q["request"]["filters"][0]["value"] for q in filters} == values
    assert all(label in q["question"] and dim not in q["question"] for q in questions)
    assert all(f"{label} {q['request']['filters'][0]['value']}" in q["question"] for q in filters)


def test_official_total_and_reclassified_ytd(contract, dist):
    spec = generate(contract, dist, 202609)
    totals = [q for q in spec["questions"] if q["shape"] == "total"]
    assert totals and all(q["request"]["official_total_ok"] is True for q in totals)
    for q in totals:
        assert q["expected_rows"] == [{"value": 4000.0 if q["mode"] == "cumulative" else 350.0}]
    by_bu = [q for q in spec["questions"] if q["class"] == "by:revenue:cumulative:bu"]
    assert by_bu
    with open_dist(dist, "revenue") as conn:
        summed = conn.execute("SELECT SUM(revenue) FROM feed_revenue_fact_bu_monthly "
                              "WHERE bu = ? AND year_month BETWEEN 202601 AND 202609", [BG8]).fetchone()[0]
    assert summed == 60.0
    assert all({row["bu"]: row["value"] for row in q["expected_rows"]}[BG8] == 210.0 != summed for q in by_bu)


@pytest.mark.parametrize("table", ["fact_total_monthly", "fact_bu_monthly", "fact_org_monthly"])
def test_every_declared_dataset_parquet_is_required(contract, dist, table):
    (dist / f"{table}.parquet").unlink()
    with pytest.raises(ValueError, match=rf"Missing metric dataset parquet: .*{table}\.parquet"):
        generate(contract, dist, 202609)


def test_dimension_without_a_dataset_is_skipped(contract, dist):
    contract["metrics"][0]["dimensions"] = ["bu", "unassigned"]
    spec = generate(contract, dist, 202609)
    assert spec["skipped"] == [
        {"metric_id": "revenue", "mode": mode, "dimension": "unassigned", "shape": None, "reason": "no_dataset"}
        for mode in ("month", "cumulative")
    ]
    assert {q["dimension"] for q in spec["questions"]} == {None, "bu"}


@pytest.mark.parametrize("dimensions,position", [(["bu"], 3), (["bu_seq", "bu"], 0)])
def test_compilers_smallest_table_and_declaration_order_drive_metadata(contract, dist, dimensions, position):
    alternate = {"name": "alternate_bu", "dimensions": dimensions}
    contract["metrics"][0]["datasets"].insert(position, alternate)
    contract["datasets"].append({"name": "alternate_bu", "columns": [
        {"name": "bu", "description": "ธุรกิจที่เลือก — ตารางทางเลือก"},
    ]})
    with duckdb.connect(":memory:") as conn:
        source = str(dist / "fact_bu_monthly.parquet").replace("'", "''")
        target = str(dist / "alternate_bu.parquet").replace("'", "''")
        conn.execute(f"COPY (SELECT * REPLACE ('chosen' AS bu, CAST(bu_seq AS TEXT) AS bu_seq) "
                     f"FROM read_parquet('{source}')) TO '{target}' (FORMAT PARQUET)")
    spec = generate(contract, dist, 202609)
    filters = [q for q in spec["questions"] if q["shape"] == "filter" and q["dimension"] == "bu"]
    assert filters and {q["request"]["filters"][0]["value"] for q in filters} == {"chosen"}
    assert all("ธุรกิจที่เลือก chosen" in q["question"] for q in filters)
    assert any(q["dimension"] == "bu_seq" for q in spec["questions"]) is (position == 0)


def test_datasets_generation_is_deterministic(contract, dist):
    first = generate(contract, dist, 202609, compare=True)
    second = generate(contract, dist, 202609, compare=True)
    assert json.dumps(first, ensure_ascii=False) == json.dumps(second, ensure_ascii=False)
