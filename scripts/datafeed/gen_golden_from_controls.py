"""
control_totals → golden examples (PLAN F10 Phase C)
====================================================
Generates ~15-25 Thai golden examples from the feed's control totals so the
eval harness (F3-B) can measure the feed_<domain> context. Deterministic
period selection (latest + 3 evenly spaced back) — reproducible regen.

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


def build_examples(controls: pd.DataFrame, domain: str) -> list:
    total_table = f"feed_{domain}_fact_total_monthly"
    bu_table = f"feed_{domain}_fact_bu_monthly"
    examples = []

    periods = pick_periods(controls["year_month"].tolist())
    monthly = controls[controls["measure"] == "revenue"]

    for ym in periods:
        thai = thai_period(ym)
        # (ก) grand total per period
        examples.append((
            f"รายได้รวมทั้งบริษัทเดือน{thai} เท่าไร",
            f'SELECT revenue FROM {total_table} WHERE year_month = {ym}',
        ))
        # (ข) per-BG — first, middle, and a Thai-named BG for string matching
        bgs = monthly[(monthly["year_month"] == ym) & (monthly["bu"] != "__ALL__")]["bu"].tolist()
        chosen = []
        if bgs:
            chosen.append(bgs[0])
            thai_named = [b for b in bgs if any("฀" <= ch <= "๿" for ch in b)]
            if thai_named:
                chosen.append(thai_named[0])
        for bu in chosen[:2]:
            examples.append((
                f"รายได้ของกลุ่มธุรกิจ {bu} เดือน{thai} เท่าไร",
                f"SELECT revenue FROM {bu_table} WHERE bu = '{bu}' AND year_month = {ym}",
            ))

    # (ค) YTD questions — must use revenue_ytd (tests the bg8 business rule directly)
    latest = periods[-1]
    thai = thai_period(latest)
    ytd_bgs = controls[(controls["measure"] == "revenue_ytd") & (controls["year_month"] == latest)
                       & (controls["bu"] != "__ALL__")]["bu"].tolist()
    bg8 = next((b for b in ytd_bgs if b.startswith("8")), ytd_bgs[0] if ytd_bgs else None)
    if bg8:
        examples.append((
            f"รายได้สะสม (YTD) ของกลุ่มธุรกิจ {bg8} ณ เดือน{thai} เท่าไร",
            f"SELECT revenue_ytd FROM {bu_table} WHERE bu = '{bg8}' AND year_month = {latest}",
        ))
    examples.append((
        f"รายได้สะสมทั้งบริษัทตั้งแต่ต้นปีถึงเดือน{thai} เท่าไร",
        f"SELECT revenue_ytd FROM {total_table} WHERE year_month = {latest}",
    ))

    return examples


def main():
    parser = argparse.ArgumentParser(description="Generate golden examples from control totals")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--source", required=True, help="Path to DataFeed/dist")
    args = parser.parse_args()

    controls = pd.read_csv(
        Path(args.source) / args.domain / "latest" / "control_totals.csv", dtype={"bu": str}
    )
    examples = build_examples(controls, args.domain)

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
