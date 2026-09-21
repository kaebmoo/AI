"""The Buddhist-era years an explanation names must be the years of its answer.

The explanation step converts ค.ศ. → พ.ศ. by itself and gets it wrong with a constant slip: the SQL
chose 2026 (right) and the text said 2566 or 2568 — 7 of 12 real portal questions, including one
whose rows carried `year: 2026` in plain sight (plan/archive/RESULT_F11.md §9). Asking the model
harder is not a fix; this checks the text against the years the answer is actually about.

Years of the answer = what the rows carry + the literals the SQL filtered on + what the question
typed. A text whose years already fall inside that set is returned untouched (a user who typed the
year gets the answer they got before). Otherwise the one shift that puts most of the named years on
years of the answer is applied to all of them — the slip is constant, so the relative years of a
comparison (2566 vs 2565 → 2569 vs 2568) survive. No shift that beats leaving it = left as is.
"""

import re
from typing import Any, Iterable, Optional, Set

BE_OFFSET = 543
# a year standing alone — not a digit run of an amount ("12,568.3") or a period key ("202608")
_BE_IN_TEXT = re.compile(r"(?<![\d,.])(25\d\d)(?![\d,.])")
# ค.ศ. year or YYYYMM period, พ.ศ. year — as a literal in SQL / a question / a cell
_LITERAL = re.compile(r"(?<!\d)(20\d\d|25\d\d)(0[1-9]|1[0-2])?(?!\d)")
_SHORT_BE = re.compile(r"(?:ปี|พ\.ศ\.)\s*(\d\d)(?!\d)")  # "ปี 69"


def _years_in(text: str) -> Set[int]:
    """พ.ศ. years named by literals in text: 2026 / 202608 → 2569, 2569 stays 2569."""
    years = set()
    for year, _month in _LITERAL.findall(text or ""):
        year = int(year)
        years.add(year + BE_OFFSET if year < 2500 else year)
    return years


def answer_years(question: str, sql: str, rows: Optional[Iterable[dict]]) -> Set[int]:
    years = _years_in(sql) | _years_in(question)
    years |= {2500 + int(short) for short in _SHORT_BE.findall(question or "")}
    for row in rows or []:
        for value in row.values():
            if isinstance(value, bool):
                continue
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            if isinstance(value, (int, str)):
                years |= _years_in(str(value))
    return years


def fix_text(text: str, years: Set[int]) -> str:
    said = [int(y) for y in _BE_IN_TEXT.findall(text or "")]
    if not said or not years or set(said) <= years:
        return text

    def hits(shift: int) -> int:
        return sum(1 for y in said if y + shift in years)

    # most years landed; then no change; then the smallest slip (the model's slip runs low: +k first)
    best = max({y - s for y in years for s in said} | {0}, key=lambda k: (hits(k), k == 0, -abs(k), k))
    if best == 0 or hits(best) <= hits(0):
        return text
    return _BE_IN_TEXT.sub(lambda m: str(int(m.group(1)) + best), text)


def fix_explanation(explanation: Any, question: str, sql: str, rows) -> Any:
    """The explanation (text, or dict with text + chart title) with its พ.ศ. years set right."""
    years = answer_years(question, sql, rows)
    if isinstance(explanation, dict):
        for key in ("explanation", "chart_title"):
            if isinstance(explanation.get(key), str):
                explanation[key] = fix_text(explanation[key], years)
        return explanation
    return fix_text(explanation, years) if isinstance(explanation, str) else explanation
