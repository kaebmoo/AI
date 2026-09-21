"""
Real portal questions — ask them the way the portal hook does, then score what the USER sees
=============================================================================================
The questions are the ones portal users typed themselves (scripts/eval/portal_real_questions.json).
A score that reads only the numbers in `data` called these 10/12 while the text named the wrong
Buddhist-era year in 7 of them (plan/archive/RESULT_F11.md §9) — so a question passes only when:

  numbers  the rows in `data` carry the oracle's values (±0.01 million baht)
  said     the text states the figure it answers with, to the digits it writes — a text that said
           "1 ล้านบาท" over rows of 3,434.07 passed on `data` alone
  years    every year the answer text names is a year of the oracle's answer (พ.ศ. = ค.ศ. + 543) —
           never widened by the cells of the response (a count of 2025 is not the year 2568)
  base     a question that names no period gets an answer that says which period it used

Ask a server that runs on COPIES of config.db / app.db with a practice key made on that copy — never
the live server, never the portal's key (they would spend the portal's quota and write its audit).

Usage:
    PORTAL_EVAL_API_KEY=<practice key> python -m scripts.eval.run_portal_questions --base-url http://localhost:8001
    python -m scripts.eval.run_portal_questions --score eval_results/portal_real_<ts>.json   # rescore, no calls
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = Path(__file__).with_name("portal_real_questions.json")
RESULTS_DIR = PROJECT_ROOT / "eval_results"
LIVE_PORT = 8000  # the server the portal uses
TOL = 0.01 + 1e-9  # million baht, and percentage points
# a year standing alone — not a digit run of an amount ("12,568.3") or a period key ("202608"); it may end
# a sentence or a list ("ปี 2568, 2569.")
_BE = re.compile(r"(?<!\d)(?<!\d[.,])(25[67]\d)(?!\d)(?![.,]\d)")
_CE = re.compile(r"(?<!\d)(?<!\d[.,])(20[23]\d)(?!\d)(?![.,]\d)")
# a figure as the text writes it: "3,434.07 ล้านบาท", "**6,631** ล้านบาท", "2.7 หมื่นล้านบาท", "82.09%"
_FIGURE = re.compile(r"(?<![\d.,])(\d[\d,]*(?:\.(\d+))?)[\s*]*(ล้านล้าน|แสนล้าน|หมื่นล้าน|พันล้าน|ล้าน|แสน|หมื่น|พัน)?"
                     r"[\s*]*(บาท|%)?")
_SCALE = {"ล้านล้าน": 1e12, "แสนล้าน": 1e11, "หมื่นล้าน": 1e10, "พันล้าน": 1e9, "ล้าน": 1e6, "แสน": 1e5, "หมื่น": 1e4,
          "พัน": 1e3}


# ── what the user sees ─────────────────────────────────────


def _numbers(row: dict) -> list:
    return [v for v in row.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _cells(row: dict) -> set:
    out = set()
    for v in row.values():
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        out.add(str(v).strip())
    return out


def _has(row: dict, target: float, percent: bool = False) -> bool:
    """A cell holds target — in baht or million baht (a percentage: as percent or as a ratio)."""
    scale = 100 if percent else 1e-6
    return any(abs(c - target) <= TOL for n in _numbers(row) for c in (n, n * scale))


def _states(answer: str, target: float, percent: bool = False) -> bool:
    """The text writes target — million baht, or a percent — to the digits it shows (the oracle's own ±TOL on
    top): "6,631 ล้านบาท" states 6,630.81 and "1 ล้านบาท" states nothing near 3,434.07. A sign said in words
    ("ลดลง 3.81%") has no minus to read, so magnitudes are compared."""
    unit_size = 1 if percent else 1e6
    for number, decimals, scale, unit in _FIGURE.findall(answer):
        if percent != (unit == "%") or not (percent or scale or unit):
            continue
        size = _SCALE.get(scale, 1)
        slack = 0.5 * 10 ** -len(decimals) * size + TOL * unit_size
        if abs(float(number.replace(",", "")) * size - abs(target) * unit_size) <= slack:
            return True
    return False


def _key_in(row: dict, key: list) -> bool:
    cells = _cells(row)
    return any(all(part in cells for part in alt) for alt in key)


def check_numbers(alt: dict, data: list) -> tuple:
    """(ok, note) — the data against one accepted answer."""
    if alt.get("refusal"):
        amounts = [n for row in data for n in _numbers(row) if abs(n) >= 1]
        return (not amounts, f"ปฏิเสธแต่มีตัวเลข {amounts[:3]}" if amounts else "")
    if not data:
        return False, "ไม่มีแถว"
    if "values" in alt:
        missing = [v for v in alt["values"] if not any(_has(r, v) for r in data)]
        if alt.get("percent") is not None and not any(_has(r, alt["percent"], percent=True) for r in data):
            missing.append(f"{alt['percent']}%")
        return not missing, f"ไม่พบ {missing}" if missing else ""
    if "pairs" in alt:  # every row: a label the oracle knows + both of its values
        bad = []
        for row in data:
            label = next((c for c in _cells(row) if c in alt["pairs"]), None)
            if label is None or not all(_has(row, v) for v in alt["pairs"][label]):
                bad.append(label or "?")
        if len(data) < alt.get("min_rows", 1):
            bad.append(f"แถว {len(data)} < {alt['min_rows']}")
        return not bad, f"แถวที่ไม่ตรง {bad[:3]}" if bad else ""
    rows, need = alt["rows"], alt.get("min_rows", len(alt["rows"]))
    if len(data) < need:
        return False, f"แถว {len(data)} < {need}"
    if alt.get("ordered"):
        bad = [i + 1 for i, (want, row) in enumerate(zip(rows[:need], data))
               if not (_key_in(row, want["key"]) and _has(row, want["value"]))]
        return not bad, f"อันดับที่ไม่ตรง {bad}" if bad else ""
    bad = [want["key"][0][0] for want in rows
           if not any(_key_in(r, want["key"]) and _has(r, want["value"]) for r in data)]
    return not bad, f"ไม่พบ {bad[:4]}" if bad else ""


def check_said(alt: dict, answer: str) -> tuple:
    """(ok, note) — the text states the figure it answers with: every value (and the percent) of a
    single-figure answer, the top of a ranking. A list of months is read from `data` alone."""
    if "values" in alt:
        want = [(v, False) for v in alt["values"]] + ([(alt["percent"], True)] if alt.get("percent") is not None else [])
    elif alt.get("ordered"):
        want = [(alt["rows"][0]["value"], False)]
    else:
        return True, ""
    missing = [f"{v}%" if percent else v for v, percent in want if not _states(answer, v, percent)]
    return not missing, f"ข้อความไม่บอกยอด {missing}" if missing else ""


def check_text(alt: dict, answer: str, time_in_question: bool) -> tuple:
    """(years_ok, base_ok, note)"""
    if alt.get("refusal"):
        ok = all(word in answer for word in alt["refusal"])
        return True, ok, "" if ok else f"ข้อความไม่บอกว่า{''.join(alt['refusal'])}"
    allowed_be = set(alt["years_be"])
    said_be = {int(y) for y in _BE.findall(answer)}
    said_ce = {int(y) for y in _CE.findall(answer)}
    wrong = sorted((said_be - allowed_be) | {y + 543 for y in said_ce if y + 543 not in allowed_be})
    notes = [f"ปีในข้อความไม่ตรง {wrong} (ถูก: {sorted(allowed_be)})"] if wrong else []
    base_ok = True
    if not time_in_question:  # the answer must say which period it is about
        named_year = bool((said_be | {y + 543 for y in said_ce}) & set(alt["years_be"]))
        named_base = not alt.get("base_words") or any(w in answer for w in alt["base_words"])
        base_ok = named_year and named_base
        if not base_ok:
            notes.append(f"ไม่บอกฐาน ({alt['base']})")
    return not wrong, base_ok, "; ".join(notes)


def score(question: dict, response: dict) -> dict:
    answer, data = response.get("answer") or "", response.get("data") or []
    results = [(a, *check_numbers(a, data)) for a in question["accept"]]
    alt, num_ok, num_note = next((r for r in results if r[1]), results[0])
    if response.get("error"):
        num_ok, num_note = False, f"error {response['error']}"
    said_ok, said_note = check_said(alt, answer)
    years_ok, base_ok, text_note = check_text(alt, answer, question["time_in_question"])
    return {"ok": num_ok and said_ok and years_ok and base_ok, "numbers": num_ok, "said": said_ok, "years": years_ok,
            "base": base_ok, "matched": alt["base"] if num_ok else None,
            "note": "; ".join(n for n in (num_note, said_note, text_note) if n)}


# ── asking ─────────────────────────────────────────────────


def ask(base_url: str, key: str, body: dict) -> dict:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/v1/query/", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": key})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        out = {"error": f"http_{e.code}", "answer": e.read().decode(errors="replace")[:300]}
    out["_seconds"] = round(time.time() - t0, 1)
    return out


def report(spec: dict, answers: dict) -> str:
    lines, totals = [], {}
    for q in spec["questions"]:
        resp = answers.get(q["id"])
        if resp is None:
            continue
        s = score(q, resp)
        mark = lambda b: "✓" if b else "✗"  # noqa: E731
        lines.append(f"{q['id']} {mark(s['ok'])} num{mark(s['numbers'])} ยอด{mark(s['said'])} ปี{mark(s['years'])}"
                     f" ฐาน{mark(s['base'])}  {q['question'][:40]}{'  — ' + s['note'] if s['note'] else ''}")
        for subset in ("all", "P01-P12") if int(q["id"][1:]) <= 12 else ("all",):
            t = totals.setdefault(subset, {"n": 0, "ok": 0, "numbers": 0, "said": 0, "years": 0})
            t["n"] += 1
            t["ok"] += s["ok"]
            t["numbers"] += s["numbers"]
            t["said"] += s["said"]
            t["years"] += s["years"] and s["base"]
    for subset, t in totals.items():
        lines.append(f"[{subset}] ถูกครบ {t['ok']}/{t['n']} · ตัวเลข {t['numbers']}/{t['n']}"
                     f" · ยอดในข้อความ {t['said']}/{t['n']} · ปี+ฐานในข้อความ {t['years']}/{t['n']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Real portal questions — ask + score")
    parser.add_argument("--base-url", default="http://localhost:8001", help="server on COPIES of the DBs")
    parser.add_argument("--score", metavar="JSON", help="rescore a saved run (no calls)")
    parser.add_argument("--only", help="comma-separated ids, e.g. P01,P09")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds between questions")
    args = parser.parse_args()
    spec = json.loads(QUESTIONS.read_text())

    if args.score:
        print(report(spec, json.loads(Path(args.score).read_text())["answers"]))
        return
    if urlparse(args.base_url).port == LIVE_PORT:
        sys.exit(f"refusing port {LIVE_PORT}: that is the live server — run one on copies of the DBs")
    key = os.environ.get("PORTAL_EVAL_API_KEY")
    if not key:
        sys.exit("set PORTAL_EVAL_API_KEY to a practice key made on the copy")

    only = set(args.only.split(",")) if args.only else None
    answers = {}
    for q in spec["questions"]:
        if only and q["id"] not in only:
            continue
        body = {"question": q["question"], "context": spec["context"], "scope": spec["scope"], **spec["request"]}
        answers[q["id"]] = ask(args.base_url, key, body)
        print(f"{q['id']} {answers[q['id']]['_seconds']}s", flush=True)
        time.sleep(args.pause)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"portal_real_{datetime.now():%Y%m%d_%H%M}.json"
    out.write_text(json.dumps({"base_url": args.base_url, "at": datetime.now().isoformat(timespec="seconds"),
                               "answers": answers}, ensure_ascii=False, indent=1))
    print(report(spec, answers))
    print(f"saved {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
