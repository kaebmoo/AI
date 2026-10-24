"""Ask generated metric questions on a practice server and report layered scores.

Usage:
    PORTAL_EVAL_API_KEY=<practice key> python -m scripts.eval.run_metric_eval \
        --questions eval_results/metric_ebt_202609.json --audit-db <copy app.db>
    python -m scripts.eval.run_metric_eval --questions <questions.json> --score <saved.json>
"""

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import urlparse
import warnings

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality isn't compatible.*", category=UserWarning)
    from scripts.eval.metric_eval_lib import report, score_case
from scripts.eval.run_portal_questions import ask


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "eval_results"


def select_questions(spec: dict, only_class: str | None = None, per_class: int | None = None,
                     limit: int | None = None) -> list[dict]:
    """Filter classes, sample evenly within each class, then limit in id order."""
    questions = [q for q in sorted(spec["questions"], key=lambda q: q["id"])
                 if only_class is None or re.search(only_class, q["class"])]
    if per_class is not None:
        classes = defaultdict(list)
        for q in questions:
            classes[q["class"]].append(q)
        selected = set()
        for items in classes.values():
            n = len(items)
            indices = sorted({round(i * n / per_class) for i in range(per_class)}) if n > per_class else range(n)
            selected.update(items[i]["id"] for i in indices)
        questions = [q for q in questions if q["id"] in selected]
    return questions if limit is None else questions[:limit]


def _audit_rows(path: Path, sql: str, parameters: tuple = ()) -> list:
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.execute("SELECT id, channel, question, metric_path FROM query_audit LIMIT 0")
            return conn.execute(sql, parameters).fetchall()
    except sqlite3.Error as exc:
        sys.exit(f"cannot read query_audit from {path}: " + " ".join(str(exc).splitlines()))


def audit_start_id(path: Path) -> int:
    """Validate the audit schema and mark the start of this run, read-only."""
    return _audit_rows(path, "SELECT MAX(id) FROM query_audit")[0][0] or 0


def audit_paths(path: Path, start: int, channel: str) -> dict:
    """Read this channel's new rows; the last audit row for a question wins."""
    rows = _audit_rows(path, "SELECT question, metric_path FROM query_audit "
                       "WHERE id > ? AND channel = ? ORDER BY id", (start, channel))
    return dict(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:8001", help="server on COPIES of the DBs")
    parser.add_argument("--audit-db", type=Path, help="practice copy's app.db (read-only)")
    parser.add_argument("--score", type=Path, metavar="JSON", help="rescore a saved run (no calls)")
    parser.add_argument("--only-class", help="regular expression matched against class ids")
    parser.add_argument("--per-class", type=int, help="number sampled evenly from each class")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between questions")
    args = parser.parse_args()
    for name in ("per_class", "limit", "pause"):
        if getattr(args, name) is not None and getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} must be nonnegative")
    spec = json.loads(args.questions.read_text(encoding="utf-8"))
    if args.score:
        saved = json.loads(args.score.read_text(encoding="utf-8"))
        paths = {qid: saved.get("paths", {}).get(qid) for qid in saved.get("audited", [])}
        print(report(spec, saved["answers"], paths))
        return
    if urlparse(args.base_url).port == 8000:
        sys.exit("refusing port 8000: that is the live server — run one on copies of the DBs")
    key = os.environ.get("PORTAL_EVAL_API_KEY")
    if not key:
        sys.exit("set PORTAL_EVAL_API_KEY to a practice key made on the copy")
    try:
        questions = select_questions(spec, args.only_class, args.per_class, args.limit)
    except re.error as exc:
        parser.error(f"--only-class: {exc}")
    start = audit_start_id(args.audit_db) if args.audit_db else None
    answers = {}
    for i, q in enumerate(questions):
        if i and args.pause:
            time.sleep(args.pause)
        body = {"question": q["question"], "context": spec["context"], **spec["request"]}
        if spec["scope"] is not None:
            body["scope"] = spec["scope"]
        response = ask(args.base_url, key, body)
        answers[q["id"]] = response
        mark = "✓" if score_case(q, response)["ok"] else "✗"
        print(f"{q['id']} {response['_seconds']}s {mark}", flush=True)
    paths = {}
    if args.audit_db:
        by_question = audit_paths(args.audit_db, start, spec["request"]["source"])
        paths = {q["id"]: by_question.get(q["question"]) for q in questions}
    now = datetime.now()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULTS_DIR / f"metric_eval_{spec['context']}_{spec['oracle_build']['period']}_{now:%Y%m%d_%H%M}.json"
    output.write_text(json.dumps({
        "base_url": args.base_url, "at": now.isoformat(timespec="seconds"), "questions": str(args.questions),
        "oracle_build": spec["oracle_build"],
        "selection": {"only_class": args.only_class, "per_class": args.per_class, "limit": args.limit},
        "answers": answers, "paths": paths, "audited": list(paths),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report(spec, answers, paths))
    print(f"saved {output}")


if __name__ == "__main__":
    main()
