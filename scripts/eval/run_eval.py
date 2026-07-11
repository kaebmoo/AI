"""
NL→SQL Eval Harness — execution-match accuracy (PLAN F3 Phase B)
=================================================================
Compares EXECUTION RESULTS (not SQL strings) of QueryEngine-generated SQL
against golden examples. Costs real LLM calls — run manually only.

Usage:
    python -m scripts.eval.run_eval --limit 5
    python -m scripts.eval.run_eval --provider matcha
    python -m scripts.eval.run_eval --compare eval_results/BASELINE.json
"""

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "eval_results"
FLOAT_TOL = 1e-6


# ── Row comparison ─────────────────────────────────────────


def _norm_value(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, int):
        return float(v)
    return v


def _rows_to_multiset(rows):
    """Rows → sorted list of value-tuples (column order = sorted column names)."""
    if not rows:
        return []
    cols = sorted(rows[0].keys())
    tuples = [tuple(_norm_value(r.get(c)) for c in cols) for r in rows]
    return sorted(tuples, key=lambda t: tuple(str(x) for x in t))


def rows_match(expected, actual):
    """Multiset compare of value-tuples; column count must match."""
    if not expected and not actual:
        return True
    exp_cols = len(expected[0]) if expected else 0
    act_cols = len(actual[0]) if actual else 0
    if expected and actual and len(expected[0].keys()) != len(actual[0].keys()):
        return False
    exp_t, act_t = _rows_to_multiset(expected), _rows_to_multiset(actual)
    if len(exp_t) != len(act_t):
        return False
    for a, b in zip(exp_t, act_t):
        if len(a) != len(b):
            return False
        for x, y in zip(a, b):
            if isinstance(x, float) and isinstance(y, float):
                if abs(x - y) > FLOAT_TOL * max(1.0, abs(x), abs(y)):
                    return False
            elif x != y:
                return False
    return True


# ── Golden examples + expected execution ──────────────────


def load_golden_examples(limit=None, context_filter=None):
    from app.config import settings
    conn = sqlite3.connect(settings.CONFIG_DB_URL.replace("sqlite:///", ""))
    conn.row_factory = sqlite3.Row
    sql = "SELECT id, question_pattern, expected_sql, category FROM golden_examples WHERE is_active=1"
    params = []
    if context_filter:
        sql += " AND category = ?"
        params.append(context_filter)
    sql += " ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def run_expected_sql(sql):
    """Execute golden SQL against the business DB (read-only)."""
    from app.config import settings
    path = Path(settings.BUSINESS_DB_PATH).resolve()
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(sql).fetchmany(2000)]
        return rows, None
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()


def known_contexts():
    from app.config import settings
    conn = sqlite3.connect(settings.CONFIG_DB_URL.replace("sqlite:///", ""))
    try:
        return {r[0] for r in conn.execute("SELECT name FROM schema_contexts WHERE is_active=1")}
    except Exception:
        return set()
    finally:
        conn.close()


# ── Eval loop ──────────────────────────────────────────────


async def run_eval(provider=None, context_filter=None, limit=None):
    from app.services.mcp_client import MCPClientService
    from app.services.query_engine import QueryEngine, clear_query_cache

    examples = load_golden_examples(limit=limit, context_filter=context_filter)
    contexts = known_contexts()
    print(f"Loaded {len(examples)} golden examples (contexts in DB: {sorted(contexts)})")

    records = []
    mcp_client = MCPClientService()
    async with mcp_client.connected():
        engine = QueryEngine(mcp_client=mcp_client)
        try:
            for i, ex in enumerate(examples, 1):
                q = ex["question_pattern"]
                print(f"[{i}/{len(examples)}] {q[:60]}…", flush=True)
                record = {
                    "id": ex["id"], "question": q, "category": ex["category"],
                    "expected_sql": ex["expected_sql"], "generated_sql": None,
                    "status": None, "latency_s": None, "tokens": None, "detail": None,
                }

                expected_rows, exp_err = run_expected_sql(ex["expected_sql"])
                if exp_err:
                    record["status"] = "golden_broken"  # data drift — admin must fix the golden, not the model
                    record["detail"] = exp_err
                    records.append(record)
                    continue

                clear_query_cache()  # never serve a cached answer during eval
                ctx = ex["category"] if ex["category"] in contexts else None
                t0 = time.time()
                try:
                    result = await engine.query(q, provider=provider, context=ctx, user_id=None)
                    qr = result.query_result
                    record["latency_s"] = round(time.time() - t0, 2)
                    record["generated_sql"] = qr.sql_query
                    record["tokens"] = qr.tokens_used
                    if qr.error or not qr.sql_query:
                        record["status"] = "generation_failed"
                        record["detail"] = qr.error
                    else:
                        actual_rows = qr.data or []
                        record["status"] = "exact_match" if rows_match(expected_rows, actual_rows) else "mismatch"
                        if record["status"] == "mismatch":
                            record["detail"] = f"expected {len(expected_rows)} rows, got {len(actual_rows)}"
                except Exception as e:
                    record["latency_s"] = round(time.time() - t0, 2)
                    record["status"] = "execution_failed"
                    record["detail"] = str(e)
                records.append(record)
        finally:
            engine.close()

    return records


# ── Reporting ──────────────────────────────────────────────


def summarize(records, provider):
    scored = [r for r in records if r["status"] != "golden_broken"]
    matched = [r for r in scored if r["status"] == "exact_match"]
    per_context = {}
    for r in scored:
        c = r["category"] or "(auto)"
        per_context.setdefault(c, [0, 0])
        per_context[c][1] += 1
        if r["status"] == "exact_match":
            per_context[c][0] += 1
    return {
        "provider": provider,
        "total": len(records),
        "scored": len(scored),
        "exact_match": len(matched),
        "accuracy": round(len(matched) / len(scored), 4) if scored else None,
        "golden_broken": sum(1 for r in records if r["status"] == "golden_broken"),
        "per_context": {c: {"match": m, "total": t} for c, (m, t) in sorted(per_context.items())},
    }


def write_reports(records, summary, provider):
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    base = RESULTS_DIR / f"eval_{stamp}_{provider or 'default'}"
    payload = {"summary": summary, "records": records}
    (base.with_suffix(".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    lines = [
        f"# Eval Report — {stamp} (provider: {provider or 'default'})", "",
        f"**Accuracy: {summary['exact_match']}/{summary['scored']}"
        f" = {summary['accuracy'] if summary['accuracy'] is not None else 'n/a'}**"
        f" (golden_broken: {summary['golden_broken']} — excluded)", "",
        "## Per-context", "",
        "| Context | Match | Total |", "|---|---|---|",
    ]
    for c, s in summary["per_context"].items():
        lines.append(f"| {c} | {s['match']} | {s['total']} |")
    fails = [r for r in records if r["status"] not in ("exact_match", "golden_broken")]
    if fails:
        lines += ["", "## Failures", ""]
        for r in fails:
            lines += [
                f"### [{r['id']}] {r['question']} — `{r['status']}`",
                f"- detail: {r['detail']}",
                "```sql", f"-- expected\n{r['expected_sql']}", f"-- generated\n{r['generated_sql']}", "```", "",
            ]
    broken = [r for r in records if r["status"] == "golden_broken"]
    if broken:
        lines += ["", "## Golden broken (admin action needed)", ""]
        lines += [f"- [{r['id']}] {r['question']} — {r['detail']}" for r in broken]
    (base.with_suffix(".md")).write_text("\n".join(lines))
    print(f"\nWrote {base}.json / .md")
    return base.with_suffix(".json")


def compare_with_baseline(records, baseline_path):
    baseline = json.loads(Path(baseline_path).read_text())
    base_by_id = {r["id"]: r for r in baseline["records"]}
    regressions, improvements = [], []
    for r in records:
        b = base_by_id.get(r["id"])
        if not b:
            continue
        if b["status"] == "exact_match" and r["status"] != "exact_match":
            regressions.append(r)
        elif b["status"] != "exact_match" and r["status"] == "exact_match":
            improvements.append(r)
    print("\n=== Baseline comparison ===")
    print(f"Baseline accuracy: {baseline['summary']['accuracy']}")
    if regressions:
        print(f"\n*** {len(regressions)} REGRESSION(S) ***")
        for r in regressions:
            print(f"  - [{r['id']}] {r['question'][:60]} → {r['status']}")
    if improvements:
        print(f"\n{len(improvements)} improvement(s):")
        for r in improvements:
            print(f"  + [{r['id']}] {r['question'][:60]}")
    if not regressions and not improvements:
        print("No changes vs baseline.")
    return regressions


def main():
    parser = argparse.ArgumentParser(description="NL→SQL execution-match eval")
    parser.add_argument("--provider", default=None, help="Provider (default: admin default)")
    parser.add_argument("--context", default=None, help="Filter by golden category")
    parser.add_argument("--limit", type=int, default=None, help="Run only N examples")
    parser.add_argument("--compare", default=None, help="Path to BASELINE.json to diff against")
    args = parser.parse_args()

    records = asyncio.run(run_eval(provider=args.provider, context_filter=args.context, limit=args.limit))
    summary = summarize(records, args.provider)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    write_reports(records, summary, args.provider)

    if args.compare:
        regressions = compare_with_baseline(records, args.compare)
        if regressions:
            sys.exit(1)


if __name__ == "__main__":
    main()
