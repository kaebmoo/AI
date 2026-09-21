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


def _label_drops(expected, actual):
    """Sets of extra TEXT columns of `actual` that may be ignored so the column counts agree.

    The model often answers "EBT of division X" with SELECT division, ebt — the value is right and
    the row carries its label. Only columns that hold nothing but text/NULL and whose name is not an
    expected column can be dropped: an extra number is a different answer, not a label.
    """
    from itertools import combinations

    if not expected or not actual:
        return
    extra = len(actual[0]) - len(expected[0])
    if extra <= 0:
        return
    wanted = {c.lower() for c in expected[0]}
    labels = [c for c in actual[0] if c.lower() not in wanted
              and all(r.get(c) is None or isinstance(r.get(c), str) for r in actual)]
    yield from combinations(labels, extra)


def _values_match(expected, actual) -> bool:
    """Values match, column for column — or once extra label columns of `actual` are set aside."""
    if _values_match_strict(expected, actual):
        return True
    return any(_values_match_strict(expected, [{k: v for k, v in r.items() if k not in drop} for r in actual])
               for drop in _label_drops(expected, actual))


def _values_match_strict(expected, actual) -> bool:
    """Multiset compare of value-tuples; column count must match."""
    if not expected and not actual:
        return True
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


def _columns_match(expected, actual) -> bool:
    """Case-insensitive comparison of sorted column names."""
    if not expected or not actual:
        return True  # empty-vs-empty already handled; nothing to compare
    exp = sorted(c.lower() for c in expected[0].keys())
    act = sorted(c.lower() for c in actual[0].keys())
    return exp == act


def match_status(expected, actual) -> str:
    """exact_match = values AND column names match; value_match = values only
    (other column names, or extra text label columns next to the expected values).

    value_match is reported separately — a same-values result under different
    column names may still be a wrong projection (e.g. SUM(x) aliased as the
    wrong measure), so it must not silently inflate the headline accuracy.
    """
    if not _values_match(expected, actual):
        return "mismatch"
    return "exact_match" if _columns_match(expected, actual) else "value_match"


# ── Golden examples + expected execution ──────────────────


def load_golden_examples(limit=None, context_filter=None, legacy=False):
    from app.config import settings
    conn = sqlite3.connect(settings.CONFIG_DB_URL.replace("sqlite:///", ""))
    conn.row_factory = sqlite3.Row
    sql = "SELECT id, question_pattern, expected_sql, category FROM golden_examples WHERE is_active=1"
    params = []
    if context_filter:
        sql += " AND category = ?"
        params.append(context_filter)
    if legacy:  # the contexts that were there before the file sources: what a change to a shared path must not lower
        sql += " AND category NOT LIKE 'feed\\_%' ESCAPE '\\'"
    sql += " ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def run_expected_sql(sql, context=None):
    """Execute golden SQL against the context's source (read-only).

    Plan 7: a file-source context compares against its files, not the imported copy.
    """
    from app.config import settings
    from app.services.data_sources import source_resolver

    source = source_resolver.for_context(context)
    if source.adapter is not None:
        try:
            return source.adapter.execute_query(sql, max_rows=2000), None
        except Exception as e:
            return None, str(e)
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


async def run_eval(provider=None, context_filter=None, limit=None, legacy=False):
    from app.services.mcp_client import MCPClientService
    from app.services.query_engine import QueryEngine, clear_query_cache

    examples = load_golden_examples(limit=limit, context_filter=context_filter, legacy=legacy)
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

                ctx = ex["category"] if ex["category"] in contexts else None
                expected_rows, exp_err = run_expected_sql(ex["expected_sql"], ctx)
                if exp_err:
                    record["status"] = "golden_broken"  # data drift — admin must fix the golden, not the model
                    record["detail"] = exp_err
                    records.append(record)
                    continue

                clear_query_cache()  # never serve a cached answer during eval
                t0 = time.time()
                try:
                    # Hard per-example timeout — a hung gateway call must not stall the whole run
                    result = await asyncio.wait_for(
                        engine.query(q, provider=provider, context=ctx, user_id=None),
                        timeout=180,
                    )
                    qr = result.query_result
                    record["latency_s"] = round(time.time() - t0, 2)
                    record["generated_sql"] = qr.sql_query
                    record["tokens"] = qr.tokens_used
                    if qr.error or not qr.sql_query:
                        record["status"] = "generation_failed"
                        record["detail"] = qr.error
                    else:
                        actual_rows = qr.data or []
                        record["status"] = match_status(expected_rows, actual_rows)
                        if record["status"] == "mismatch":
                            record["detail"] = f"expected {len(expected_rows)} rows, got {len(actual_rows)}"
                        elif record["status"] == "value_match":
                            record["detail"] = "values match; column names differ or label columns were added"
                except Exception as e:
                    record["latency_s"] = round(time.time() - t0, 2)
                    record["status"] = "execution_failed"
                    record["detail"] = str(e)
                records.append(record)
        finally:
            engine.close()

    return records


# ── Questions across contexts (Plan 7 Phase 5) ─────────────


def _numbers(rows):
    return [float(v) for row in rows or [] if isinstance(row, dict) for v in row.values()
            if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _has(value, numbers) -> bool:
    return any(abs(value - n) <= max(0.01, abs(value) * 1e-9) for n in numbers)


def score_cross_domain(example, expected, answer_parts, computed, warnings):
    """(ok, detail). expected: [(accepted contexts, number)]; answer_parts: [(context, rows, error)].

    An expected number counts only when it is in a ONE-row result of an accepted context — a breakdown that
    happens to contain the number in one of its cells is not an answer to "how much in total"."""
    rows_with_numbers = [c for c, rows, err in answer_parts if not err and _numbers(rows)]
    if example.get("unanswerable"):
        return (not rows_with_numbers, "answered with a number" if rows_with_numbers else "no number given")
    missing = [f"{value:,.2f} ({'/'.join(accept)})" for accept, value in expected
               if not _has(value, [n for c, rows, err in answer_parts if c in accept and not err and len(rows or []) == 1
                                   for n in _numbers(rows)])]
    if missing:
        return False, "missing: " + "; ".join(missing)
    if example.get("computed"):
        a, b = expected[0][1], expected[1][1]
        want = a / b if example["computed"] == "ratio" else a - b
        if not computed or computed.get("operation") != example["computed"] or abs(computed["value"] - want) > max(1e-6, abs(want) * 1e-9):
            return False, f"computed {example['computed']} expected {want:,.6f}, got {computed}"
    if example.get("period_warning") and example.get("_periods_differ") and not any("งวด" in w for w in warnings):
        return False, "sources stand at different periods and the answer doesn't say so"
    return True, "all expected numbers present"


async def run_cross_domain(path, provider=None):
    from app.services import multi_context
    from app.services.data_sources import source_resolver
    from app.services.mcp_client import MCPClientService
    from app.services.query_engine import QueryEngine, clear_query_cache

    golden = json.loads(Path(path).read_text())
    allowed = frozenset(golden["allowed_contexts"]) if golden.get("allowed_contexts") else None
    records = []
    mcp_client = MCPClientService()
    async with mcp_client.connected():
        engine = QueryEngine(mcp_client=mcp_client)
        print(f"multi-context workspaces enabled: {sorted(multi_context.enabled_workspaces(engine.admin_config)) or 'none (baseline)'}")
        try:
            for i, ex in enumerate(golden["examples"], 1):
                print(f"[{i}/{len(golden['examples'])}] {ex['question'][:60]}…", flush=True)
                record = {"id": ex["id"], "question": ex["question"], "category": "cross_domain",
                          "expected_sql": "\n".join(f"-- {p['context']}\n{p['sql']}" for p in ex["parts"]),
                          "generated_sql": None, "status": None, "latency_s": None, "tokens": None, "detail": None}
                expected, broken = [], None
                for part in ex["parts"]:
                    rows, err = run_expected_sql(part["sql"], part["context"])
                    numbers = _numbers(rows)
                    if err or len(numbers) != 1:
                        broken = err or f"expected SQL of {part['context']} must return one number, got {rows}"
                        break
                    expected.append((part.get("accept") or [part["context"]], numbers[0]))
                if broken:
                    record.update(status="golden_broken", detail=broken)
                    records.append(record)
                    continue
                periods = {(source_resolver.for_context(p["context"]).data_as_of or {}).get("period") for p in ex["parts"]}
                ex["_periods_differ"] = len(periods) > 1

                clear_query_cache()
                t0 = time.time()
                try:
                    result = await asyncio.wait_for(multi_context.ask(
                        engine, ex["question"], provider=provider, allowed_contexts=allowed, user_id=None), timeout=300)
                    record["latency_s"] = round(time.time() - t0, 2)
                    if isinstance(result, multi_context.MultiResult):
                        parts = [(p.context, p.result.query_result.data if p.result is not None else [], p.error)
                                 for p in result.parts]
                        record["generated_sql"] = "\n".join(
                            f"-- {p.context}: {p.question}\n{p.result.query_result.sql_query if p.result is not None else ''}"
                            for p in result.parts)
                        computed, warnings = result.computed, result.warnings
                    else:
                        qr = result.query_result
                        parts = [(result.context_name, qr.data or [], qr.error)]
                        record["generated_sql"] = f"-- {result.context_name}\n{qr.sql_query}"
                        computed, warnings = None, []
                    ok, record["detail"] = score_cross_domain(ex, expected, parts, computed, warnings)
                    record["status"] = "value_match" if ok else "mismatch"
                except Exception as e:
                    record["latency_s"] = round(time.time() - t0, 2)
                    record.update(status="execution_failed", detail=f"{type(e).__name__}: {e}")
                print(f"    → {record['status']} ({record['latency_s']} s) {record['detail']}", flush=True)
                records.append(record)
        finally:
            engine.close()
    return records


# ── Reporting ──────────────────────────────────────────────


def summarize(records, provider):
    scored = [r for r in records if r["status"] != "golden_broken"]
    matched = [r for r in scored if r["status"] == "exact_match"]
    value_matched = [r for r in scored if r["status"] == "value_match"]
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
        "value_match": len(value_matched),
        "accuracy": round(len(matched) / len(scored), 4) if scored else None,
        "accuracy_incl_value_match": (
            round((len(matched) + len(value_matched)) / len(scored), 4) if scored else None
        ),
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
        f"**Accuracy (strict): {summary['exact_match']}/{summary['scored']}"
        f" = {summary['accuracy'] if summary['accuracy'] is not None else 'n/a'}**"
        f" | incl. value_match: {summary['accuracy_incl_value_match']}"
        f" (value_match: {summary['value_match']}, golden_broken: {summary['golden_broken']} — excluded)", "",
        "## Per-context", "",
        "| Context | Match | Total |", "|---|---|---|",
    ]
    for c, s in summary["per_context"].items():
        lines.append(f"| {c} | {s['match']} | {s['total']} |")
    value_matches = [r for r in records if r["status"] == "value_match"]
    if value_matches:
        lines += ["", "## Value match (ค่าตรงแต่ชื่อคอลัมน์ต่าง — ตรวจ projection ด้วยตา)", ""]
        lines += [f"- [{r['id']}] {r['question'][:70]}" for r in value_matches]
    fails = [r for r in records if r["status"] not in ("exact_match", "value_match", "golden_broken")]
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
    # Strip trailing whitespace per physical line (embedded SQL carries its own)
    md = "\n".join(ln.rstrip() for ln in "\n".join(lines).split("\n"))
    (base.with_suffix(".md")).write_text(md)
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
    parser.add_argument("--legacy", action="store_true", help="Only golden examples outside feed_* (the legacy contexts)")
    parser.add_argument("--compare", default=None, help="Path to BASELINE.json to diff against")
    parser.add_argument("--cross-domain", default=None, metavar="JSON",
                        help="Questions across contexts (e.g. scripts/eval/cross_domain_golden.json) instead of golden_examples")
    args = parser.parse_args()

    if args.cross_domain:
        records = asyncio.run(run_cross_domain(args.cross_domain, provider=args.provider))
    else:
        records = asyncio.run(run_eval(provider=args.provider, context_filter=args.context, limit=args.limit,
                                         legacy=args.legacy))
    summary = summarize(records, args.provider)
    latencies = sorted(r["latency_s"] for r in records if r.get("latency_s") is not None)
    if latencies:  # nearest-rank percentiles
        summary["latency_p50_s"] = latencies[(len(latencies) - 1) // 2]
        summary["latency_p95_s"] = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    write_reports(records, summary, args.provider)

    if args.compare:
        regressions = compare_with_baseline(records, args.compare)
        if regressions:
            sys.exit(1)


if __name__ == "__main__":
    main()
