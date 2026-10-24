"""Offline scoring, selection, audit, and CLI checks for generated metric evals.

Usage: python -m pytest tests/unit/test_run_metric_eval.py -q
"""

import json
import sqlite3
import sys

import pytest

from scripts.eval.metric_eval_lib import path_category, report, score_case
from scripts.eval import run_metric_eval as runner


def question(qid="M0001", values=(100,), *, shape="total", metric="ebt", mode="month", dimension=None, unit="baht"):
    return {
        "id": qid, "question": f"คำถาม {qid}", "class": f"{shape}:{metric}:{mode}" + (f":{dimension}" if dimension else ""),
        "shape": shape, "metric_id": metric, "mode": mode, "dimension": dimension, "unit": unit,
        "ordered": shape.startswith("top"), "expected_rows": [{"value": v} for v in values],
    }


@pytest.mark.parametrize("value,cell,unit,ok", [
    (100, 100, "baht", True),
    (100, 100.4, "baht", True),
    (100, 100.5, "baht", True),
    (100, 101, "baht", False),
    (12345678, 12.345678, "baht", True),
    (12345678, 12.350678, "baht", True),
    (12345678, 12.351678, "baht", False),
    (12.5, 12.505, "percent", True),
    (12.5, 0.125, " Percent ", True),
    (12.5, 0.12505, " % ", True),
    (12.5, 12.52, "percent", False),
    (12.5, 0.1252, "%", False),
    (1, True, "baht", False),
    (100, "100", "baht", False),
    (None, "anything", "baht", True),
])
def test_score_case_numeric_rules(value, cell, unit, ok):
    result = score_case(question(values=(value,), unit=unit), {"data": [{"amount": cell}]})
    assert result["ok"] is ok
    assert bool(result["note"]) is not ok


def test_score_case_top_n_positions_and_ties():
    q = question(values=(300, 200, 200), shape="top5_desc")
    assert score_case(q, {"data": [{"v": 300}, {"v": 200}, {"v": 200}]}) == {"ok": True, "note": ""}
    assert score_case(q, {"data": [{"v": 200}, {"v": 300}, {"v": 200}]}) == {
        "ok": False, "note": "positions differ: [1, 2]",
    }


def test_score_case_by_rows_any_order_and_any_numeric_column():
    q = question(values=(100, 200), shape="by", dimension="unit")
    q["expected_rows"] = [{"unit": "ก", "value": 100}, {"unit": "ข", "value": 200}]
    assert score_case(q, {"data": [{"unit": "ข", "amount": 200}, {"unit": "ก", "other": 0, "amount": 100}]})["ok"]


@pytest.mark.parametrize("data,n", [([], 0), (None, 0), ([{"v": 100}], 1), ([{"v": 100}] * 3, 3)])
def test_score_case_row_count(data, n):
    assert score_case(question(values=(100, 200)), {"data": data}) == {
        "ok": False, "note": f"rows: got {n} / want 2",
    }


def test_score_case_error_and_empty_oracle():
    assert score_case(question(), {"error": "query_failed", "data": [{"v": 100}]}) == {
        "ok": False, "note": "error query_failed",
    }
    assert score_case(question(values=()), {}) == {"ok": True, "note": ""}


def test_score_case_distinct_rows_sorted_greedy_and_missing_limit():
    assert score_case(question(values=(100, 99.5)), {"data": [{"v": 99.6}, {"v": 100.4}]})["ok"]
    assert score_case(question(values=(100, 100)), {"data": [{"v": 100}, {"v": 500}]}) == {
        "ok": False, "note": "unmatched expected values: [100]",
    }
    assert score_case(question(values=(10, 10.5)), {"data": [{"v": 10.3}, {"v": 9.8}]}) == {
        "ok": False, "note": "unmatched expected values: [10.5]",
    }
    assert score_case(question(values=(40, 30, 20, 10)), {"data": [{"v": 900}] * 4}) == {
        "ok": False, "note": "unmatched expected values: [10, 20, 30]",
    }


@pytest.mark.parametrize("shape", ["by", "top5_desc"])
def test_score_case_none_matches_row_without_numbers(shape):
    q = question(values=(100, None), shape=shape)
    assert score_case(q, {"data": [{"v": 100}, {"v": None}]})["ok"]
    if not q["ordered"]:
        q["expected_rows"].reverse()
        assert score_case(q, {"data": [{"v": 100}, {"v": None}]})["ok"]


@pytest.mark.parametrize("path,audited,category", [
    ("compiled:ebt", True, "compiled"),
    ("declined:shape:dimension_set", True, "free-SQL"),
    (None, True, "free-SQL"),
    ("legacy", True, "free-SQL"),
    (None, False, "unknown"),
    ("compiled:ebt", False, "unknown"),
])
def test_path_category(path, audited, category):
    assert path_category(path, audited) == category


def test_report_exact_layers_and_audited_coverage():
    spec = {"questions": [
        question("M0001", mode="cumulative"), question("M0002"),
        question("M0003", shape="by", dimension="unit"),
        question("M0004", shape="by", dimension="division"),
        question("M0005", shape="by", dimension="division"),
        question("M0006", shape="filter", metric="margin", mode="cumulative"),
        question("M0007"),
    ]}
    answers = {q["id"]: {"data": [{"v": 100}]} for q in spec["questions"][:6]}
    answers["M0002"] = {"error": "query_failed"}
    answers["M0004"] = {"data": []}
    paths = {"M0001": "compiled:ebt", "M0002": "compiled:ebt", "M0003": "compiled:ebt",
             "M0004": "declined:zeta", "M0006": None, "M0007": "declined:unasked"}
    assert report(spec, answers, paths) == "\n".join([
        "by:ebt:month:division  1/2  [free-SQL 0/1 · unknown 1/1]",
        "by:ebt:month:unit  1/1  [compiled 1/1]",
        "filter:margin:cumulative  1/1  [free-SQL 1/1]",
        "total:ebt:cumulative  1/1  [compiled 1/1]",
        "total:ebt:month  0/1  [compiled 0/1]",
        "Layers (shape metric mode)",
        "by ebt month  2/3  [compiled 1/1 · free-SQL 0/1 · unknown 1/1]",
        "filter margin cumulative  1/1  [free-SQL 1/1]",
        "total ebt cumulative  1/1  [compiled 1/1]",
        "total ebt month  0/1  [compiled 0/1]",
        "Shapes", "total  1/2", "by  2/3", "filter  1/1",
        "Decline reasons (top 5)", "zeta  1",
        "overall 4/6 · compiled 2/3 (60.0% of audited answered by the compiler)",
    ])


def test_report_decline_top_five_sorted_and_shape_order():
    reasons = ["z", "beta", "alpha", "d", "c", "b", "z", "alpha"]
    shape_order = ["total", "by", "filter", "top5_desc", "top5_asc", "top10_desc", "top10_asc"]
    questions = [question(f"M{i:04d}", shape=shape_order[i % 7]) for i in range(len(reasons))]
    answers = {q["id"]: {"data": [{"v": 100}]} for q in questions}
    paths = {q["id"]: f"declined:{reason}" for q, reason in zip(questions, reasons)}
    text = report({"questions": list(reversed(questions))}, answers, paths)
    lines = text.splitlines()
    start = lines.index("Decline reasons (top 5)")
    assert lines[start + 1:-1] == ["alpha  2", "z  2", "b  1", "beta  1", "c  1"]
    assert [line.split()[0] for line in lines[lines.index("Shapes") + 1:start]] == shape_order


def test_report_without_answers_or_audit():
    spec = {"questions": [question()]}
    assert report(spec, {}, {}).endswith("overall 0/0 · compiled 0/0 (0.0% of audited answered by the compiler)")
    text = report(spec, {"M0001": {"data": [{"v": 100}]}}, {})
    assert text.startswith("total:ebt:month  1/1  [unknown 1/1]\n")
    assert text.endswith("overall 1/1 · compiled 0/0 (0.0% of audited answered by the compiler)")


@pytest.mark.parametrize("only_class,per_class,limit,ids", [
    (None, 2, None, ["M0001", "M0003", "M0006", "M0008"]),
    (None, 3, None, ["M0001", "M0003", "M0004", "M0006", "M0007", "M0009"]),
    (None, 10, None, [f"M{i:04d}" for i in range(1, 10)]),
    ("^by:.*:month", None, None, ["M0006", "M0007", "M0008", "M0009"]),
    ("by", 2, 1, ["M0006"]),
    (None, 2, 3, ["M0001", "M0003", "M0006"]),
    (None, None, 2, ["M0001", "M0002"]),
    ("missing", None, None, []),
    (None, 0, None, []),
    (None, None, 0, []),
])
def test_selection(only_class, per_class, limit, ids):
    spec = {"questions": [question(f"M{i:04d}", shape="total" if i <= 5 else "by") for i in range(9, 0, -1)]}
    selected = runner.select_questions(spec, only_class, per_class, limit)
    assert [q["id"] for q in selected] == ids


def make_audit(path, columns="id INTEGER PRIMARY KEY, channel TEXT, question TEXT, metric_path TEXT"):
    with sqlite3.connect(path) as conn:
        conn.execute(f"CREATE TABLE query_audit ({columns})")


def test_audit_start_and_channel_last_row_wins_read_only(tmp_path, monkeypatch):
    path = tmp_path / "practice ?# app.db"
    make_audit(path)
    assert runner.audit_start_id(path) == 0
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO query_audit VALUES (1, 'eval', 'old', 'compiled:old')")
    start = runner.audit_start_id(path)
    assert start == 1
    with sqlite3.connect(path) as conn:
        conn.executemany("INSERT INTO query_audit VALUES (?, ?, ?, ?)", [
            (2, "other", "wrong channel", "compiled:other"),
            (3, "eval", "same", "declined:first"),
            (4, "eval", "same", "compiled:last"),
            (5, "eval", "null", None),
        ])
    connect = sqlite3.connect
    opened = []

    def read_only_connect(database, **kwargs):
        assert database.endswith("?mode=ro") and kwargs == {"uri": True}
        opened.append(database)
        return connect(database, **kwargs)

    monkeypatch.setattr(runner.sqlite3, "connect", read_only_connect)
    assert runner.audit_paths(path, start, "eval") == {"same": "compiled:last", "null": None}
    assert len(opened) == 1


@pytest.mark.parametrize("schema,missing", [(None, "table"), ("id INTEGER, channel TEXT, question TEXT", "column")])
def test_audit_bad_schema_clean_exit(tmp_path, schema, missing):
    path = tmp_path / "copy.db"
    with sqlite3.connect(path) as conn:
        if schema:
            conn.execute(f"CREATE TABLE query_audit ({schema})")
    with pytest.raises(SystemExit) as exc:
        runner.audit_start_id(path)
    message = str(exc.value)
    assert "query_audit" in message and f"no such {missing}" in message
    assert len(message.splitlines()) == 1


def test_audit_missing_file_not_created(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(SystemExit, match="cannot read query_audit"):
        runner.audit_start_id(path)
    assert not path.exists()


@pytest.fixture
def cli(tmp_path, monkeypatch):
    spec = {"context": "feed_ebt", "scope": None,
            "request": {"include_data": True, "include_sql": True, "max_rows": 50, "source": "eval"},
            "oracle_build": {"period": 202609}, "questions": [question(), question("M0002")]}
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    results = tmp_path / "results"
    monkeypatch.setattr(runner, "RESULTS_DIR", results)
    monkeypatch.delenv("PORTAL_EVAL_API_KEY", raising=False)

    def no_http(*args, **kwargs):
        raise AssertionError("HTTP must be monkeypatched before a run")

    monkeypatch.setattr(runner, "ask", no_http)

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["run_metric_eval", "--questions", str(path), *map(str, args)])
        runner.main()

    return spec, path, results, run


def test_cli_score_uses_audited_ids_without_http_key_or_db(cli, tmp_path, monkeypatch, capsys):
    spec, _, results, run = cli
    saved = tmp_path / "saved.json"
    saved.write_text(json.dumps({"answers": {"M0001": {"data": [{"v": 100}]}, "M0002": {"error": "failed"}},
                                 "paths": {"M0002": "compiled:ignore_unaudited"}, "audited": ["M0001"]}), encoding="utf-8")

    def no_audit(*args):
        raise AssertionError("rescore must not read an audit DB")

    monkeypatch.setattr(runner, "audit_start_id", no_audit)
    run("--score", saved, "--audit-db", tmp_path / "unused.db")
    assert capsys.readouterr().out == report(spec, json.loads(saved.read_text())["answers"], {"M0001": None}) + "\n"
    assert not results.exists()


def test_cli_refuses_port_8000(cli, monkeypatch):
    monkeypatch.setenv("PORTAL_EVAL_API_KEY", "practice")
    with pytest.raises(SystemExit, match="refusing port 8000"):
        cli[3]("--base-url", "http://localhost:8000/")


def test_cli_requires_practice_key(cli):
    with pytest.raises(SystemExit, match="set PORTAL_EVAL_API_KEY to a practice key"):
        cli[3]()


@pytest.mark.parametrize("scope,audited", [(None, False), ({"unit": "ฝ่าย ก"}, True)])
def test_cli_run_saves_body_timing_selection_paths_and_progress(cli, tmp_path, monkeypatch, capsys, scope, audited):
    spec, source, results, run = cli
    spec["scope"] = scope
    source.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    path = tmp_path / "practice.db"
    if audited:
        make_audit(path)
        with sqlite3.connect(path) as conn:
            conn.execute("INSERT INTO query_audit VALUES (1, 'eval', ?, 'declined:old')", (spec["questions"][1]["question"],))
    monkeypatch.setenv("PORTAL_EVAL_API_KEY", "practice-test")
    calls, sleeps = [], []

    def fake_ask(base_url, key, body):
        assert base_url == "http://localhost:8001" and key == "practice-test"
        expected = {"question": spec["questions"][len(calls)]["question"], "context": spec["context"], **spec["request"]}
        if scope is not None:
            expected["scope"] = scope
        assert body == expected
        calls.append(body)
        if audited and len(calls) == 1:
            with sqlite3.connect(path) as conn:
                conn.execute("INSERT INTO query_audit VALUES (2, 'eval', ?, 'compiled:ebt')", (body["question"],))
        return {"data": [{"v": 100}], "_seconds": 0.1} if len(calls) == 1 else {"error": "query_failed", "_seconds": 0.2}

    monkeypatch.setattr(runner, "ask", fake_ask)
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    args = ["--only-class", "^total:", "--per-class", "2", "--limit", "2", "--pause", "0.3"]
    run(*args, *(["--audit-db", path] if audited else []))
    assert len(calls) == 2 and sleeps == [0.3]
    files = list(results.glob("metric_eval_feed_ebt_202609_*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert set(saved) == {"base_url", "at", "questions", "oracle_build", "selection", "answers", "paths", "audited"}
    assert saved["base_url"] == "http://localhost:8001" and saved["questions"] == str(source)
    assert saved["oracle_build"] == spec["oracle_build"]
    assert saved["selection"] == {"only_class": "^total:", "per_class": 2, "limit": 2}
    assert saved["answers"] == {"M0001": {"data": [{"v": 100}], "_seconds": 0.1},
                                "M0002": {"error": "query_failed", "_seconds": 0.2}}
    assert saved["paths"] == ({"M0001": "compiled:ebt", "M0002": None} if audited else {})
    assert saved["audited"] == (["M0001", "M0002"] if audited else [])
    output = capsys.readouterr().out
    assert output.startswith("M0001 0.1s ✓\nM0002 0.2s ✗\n")
    assert f"saved {files[0]}" in output and report(spec, saved["answers"], saved["paths"]) in output
    run("--score", files[0])
    assert capsys.readouterr().out == report(spec, saved["answers"], saved["paths"]) + "\n"
    assert len(calls) == 2


@pytest.mark.parametrize("args", [("--per-class", "-1"), ("--limit", "-1"), ("--pause", "-1"), ("--only-class", "[")])
def test_cli_invalid_selection_fails_before_http(cli, monkeypatch, capsys, args):
    monkeypatch.setenv("PORTAL_EVAL_API_KEY", "practice")
    with pytest.raises(SystemExit) as exc:
        cli[3](*args)
    assert exc.value.code == 2
    assert args[0] in capsys.readouterr().err
