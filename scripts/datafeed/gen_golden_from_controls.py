"""
control_totals → golden examples (PLAN F10 Phase C)
====================================================
Generates ~15-25 Thai golden examples from the feed's control totals so the
eval harness (F3-B) can measure the feed_<domain> context. Deterministic
period selection (latest + 3 evenly spaced back) — reproducible regen.

Everything about the data comes from the contract's control_totals (Plan 7 Phase 2):
source / grand_total datasets, period_key, bg_key, group_keys and measures
(agg 'sum' → monthly questions, 'point_in_time' → YTD questions), plus `filter`
({column: value} → AND column = value in every SQL). A source without bg_key (ebt's
fact_ebt_total_monthly) is total-only: one question per measure per period, worded as
monthly or YTD per measure (MEASURE_WORDS, else the measure's agg).
A contract without control_totals gets no golden — there is nothing to check against.

Marker: category = 'feed_<domain>' — delete-and-regen is clean.

Usage:
    python -m scripts.datafeed.gen_golden_from_controls --domain revenue \
        --source /path/to/DataFeed/dist
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

THAI_MONTHS = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

# Wording of the generated questions: (what is measured, what a bg_key value is called).
# Default only — an unknown domain falls back to its contract title.
QUESTION_WORDS = {
    "revenue": ("รายได้", "กลุ่มธุรกิจ"),
    "expense": ("ค่าใช้จ่าย", "กลุ่ม"),
    "sales": ("ยอดขาย", "กลุ่มธุรกิจ"),
}
# Total-only sources ask once per measure: measure name → (what the question calls it, is it YTD).
# Default only — an unknown measure is asked by its contract note, YTD when agg is point_in_time.
# The question must say which one it wants: a YTD value asked as "เดือน" scores a wrong-meaning answer right.
MEASURE_WORDS = {
    "sales_base_revenue": ("รายได้ (ฐานยอดขาย) ตามรายงาน EBT", True),
    "expense": ("ค่าใช้จ่ายตามรายงาน EBT", True),
    "ebt": ("กำไร (ขาดทุน) EBT ตามรายงาน EBT", True),
    "sales_base_revenue_month": ("รายได้ (ฐานยอดขาย) ตามรายงาน EBT", False),
    "expense_month": ("ค่าใช้จ่ายตามรายงาน EBT", False),
    "ebt_month": ("กำไร (ขาดทุน) EBT ตามรายงาน EBT", False),
}


def total_question(measure: dict, year_month: int) -> str:
    default = ((measure.get("note") or measure["name"]).split(",")[0], measure.get("agg") == "point_in_time")
    noun, ytd = MEASURE_WORDS.get(measure["name"], default)
    when = f"สะสมตั้งแต่ต้นปีถึงเดือน{thai_period(year_month)}" if ytd else f"ของเดือน{thai_period(year_month)}"
    return f"{noun} {when} เท่าไร"


def thai_period(year_month: int) -> str:
    year, month = divmod(int(year_month), 100)
    return f"{THAI_MONTHS[month]} {year + 543}"  # Thai month + พ.ศ. — exercises year conversion


def pick_periods(periods: list) -> list:
    """Latest + 3 evenly spaced earlier periods (deterministic)."""
    periods = sorted(set(periods))
    if len(periods) <= 4:
        return periods
    step = max(1, (len(periods) - 1) // 4)
    picked = [periods[-1]] + [periods[i] for i in range(0, len(periods) - 1, step)][:3]
    return sorted(set(picked))


def _is_thai(s: str) -> bool:
    return any("฀" <= ch <= "๿" for ch in s)


def build_examples(controls: pd.DataFrame, domain: str, contract: dict) -> list:
    spec = contract.get("control_totals")
    if not spec:
        return []
    period_key, bg_key = spec.get("period_key", "year_month"), spec.get("bg_key")
    group_keys = spec.get("group_keys", [bg_key, period_key])
    and_filter = "".join(f" AND {c} = " + (str(v) if isinstance(v, (int, float)) and not isinstance(v, bool)
                                           else "'" + str(v).replace("'", "''") + "'")
                         for c, v in (spec.get("filter") or {}).items())
    source = f"feed_{domain}_{spec['source']}"
    grand = spec.get("grand_total") or {}
    total_table = f"feed_{domain}_{grand['source']}" if grand else None
    # a source already at (bg × period) grain answers with its row; a finer one needs SUM
    source_keys = next(d.get("keys", []) for d in contract["datasets"] if d["name"] == spec["source"])
    one_row = set(source_keys) <= set(group_keys)
    # how a group is named in the question: its *_name key when there is one (expense_group_code
    # → expense_group_name), else the bg_key value itself (revenue bu, sales business_group)
    label_key = next((k for k in group_keys if k.endswith("_name") and k in controls.columns), bg_key)
    noun, group_noun = QUESTION_WORDS.get(domain, (contract.get("title", domain), "กลุ่ม"))
    measures = spec.get("measures", [])
    monthly = next((m["name"] for m in measures if m.get("agg", "sum") == "sum"), None)
    ytd = next((m["name"] for m in measures if m.get("agg") == "point_in_time"), None)

    def total_sql(measure, ym):
        if total_table:
            return f"SELECT {measure} FROM {total_table} WHERE {period_key} = {ym}"
        return f"SELECT SUM({measure}) FROM {source} WHERE {period_key} = {ym}{and_filter}"

    def group_sql(measure, bg, ym):
        value = measure if one_row else f"SUM({measure})"
        bg_lit = "'" + str(bg).replace("'", "''") + "'"
        return f"SELECT {value} FROM {source} WHERE {bg_key} = {bg_lit} AND {period_key} = {ym}{and_filter}"

    examples = []
    periods = pick_periods(controls[period_key].tolist())
    if not bg_key:  # total-only source: every measure, per period (one row per period — never summed)
        return [(total_question(m, ym), total_sql(m["name"], ym)) for ym in periods for m in measures]
    rows = controls[(controls["measure"] == monthly) & (controls[bg_key] != "__ALL__")] if monthly else controls[:0]

    for ym in periods if monthly else []:
        thai = thai_period(ym)
        # (ก) grand total per period
        examples.append((f"{noun}รวมทั้งบริษัทเดือน{thai} เท่าไร", total_sql(monthly, ym)))
        # (ข) per group — the first, and another Thai-named one for string matching
        groups = rows[rows[period_key] == ym][[bg_key, label_key]].values.tolist()
        chosen = groups[:1] + [g for g in groups[1:] if _is_thai(str(g[1]))][:1]
        for bg, label in chosen:
            examples.append((f"{noun}ของ{group_noun} {label} เดือน{thai} เท่าไร", group_sql(monthly, bg, ym)))

    # (ค) YTD questions — must use the point-in-time measure (tests the ytd rule directly)
    if ytd:
        latest = periods[-1]
        thai = thai_period(latest)
        ytd_groups = controls[(controls["measure"] == ytd) & (controls[period_key] == latest)
                              & (controls[bg_key] != "__ALL__")][bg_key].tolist()
        bg8 = next((b for b in ytd_groups if b.startswith("8")), ytd_groups[0] if ytd_groups else None)
        if bg8:
            examples.append((f"{noun}สะสม (YTD) ของ{group_noun} {bg8} ณ เดือน{thai} เท่าไร",
                             group_sql(ytd, bg8, latest)))
        examples.append((f"{noun}สะสมทั้งบริษัทตั้งแต่ต้นปีถึงเดือน{thai} เท่าไร", total_sql(ytd, latest)))

    return examples


def main():
    parser = argparse.ArgumentParser(description="Generate golden examples from control totals")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--source", required=True, help="Path to DataFeed/dist")
    args = parser.parse_args()

    from scripts.datafeed.import_datafeed import load_bundle

    latest, _, contract = load_bundle(Path(args.source), args.domain)
    if not contract.get("control_totals"):
        print(f"{args.domain}: contract has no control_totals — no golden generated (existing ones kept)")
        return
    bg_key = contract["control_totals"].get("bg_key")
    controls = pd.read_csv(latest / "control_totals.csv", dtype={bg_key: str} if bg_key else None)
    examples = build_examples(controls, args.domain, contract)

    from app.config import settings
    conn = sqlite3.connect(settings.CONFIG_DB_URL.replace("sqlite:///", ""), timeout=60)
    category = f"feed_{args.domain}"
    try:
        deleted = conn.execute("DELETE FROM golden_examples WHERE category = ?", (category,)).rowcount
        for question, sql in examples:
            conn.execute(
                "INSERT INTO golden_examples (question_pattern, expected_sql, category, is_active) "
                "VALUES (?, ?, ?, 1)",
                (question, sql, category),
            )
        conn.commit()
        print(f"Replaced {deleted} → inserted {len(examples)} golden examples (category={category})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
