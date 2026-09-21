"""The Buddhist-era years an explanation names must be the years of its answer.

The explanation step converts ค.ศ. → พ.ศ. by itself and gets it wrong with a constant slip: the SQL
chose 2026 (right) and the text said 2566 or 2568 — 7 of 12 real portal questions, including one
whose rows carried `year: 2026` in plain sight (plan/archive/RESULT_F11.md §9). Asking the model
harder is not a fix; this checks the text against the years the answer is actually about.

Years of the answer = the period cells of the rows + the literals of the SQL's period conditions + what
the question typed. A period column is one whose name says so and that the context's metadata does not
call a measure (`is_time_column` — the rule of the prompt's date section): 2,568 baht names no year,
whichever column it sits in. A text whose years already fall inside that set is returned untouched (a
user who typed the year gets the answer they got before). Otherwise the one shift that puts most of the
named years on years of the answer is applied to all of them — the slip is constant, so the relative
years of a comparison (2566 vs 2565 → 2569 vs 2568) survive. No shift that beats leaving it = left as is.

Only a number the text marks as a year is read or rewritten: one after ปี / พ.ศ. / งวด / เดือน / ไตรมาส /
a month name / "8/", and the years a range or a list carries on with ("ปี 2568-2569", "ระหว่างปี 2566
กับ 2565"). "รายได้รวม 2500 ล้านบาท" is an amount — rewriting every 25xx put 2569 in its place.
"""

import re
from typing import Any, Iterable, Optional, Set

from app.services.schema.prompt_builder import is_time_column

BE_OFFSET = 543
_MONTHS = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
           "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")
_MONTHS_SHORT = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
# what says the number after it is a year — a month abbreviation with or without its dots
_MARK = "|".join([r"ปี(?:งบประมาณ|งบ)?", r"พ\.\s*ศ\.?", "งวด", "เดือน", "ไตรมาส", *_MONTHS,
                  *(re.escape(m).replace(r"\.", r"\.?") for m in _MONTHS_SHORT), r"(?<!\d)\d{1,2}\s*/"])
# a พ.ศ. year standing alone: not a digit run of an amount ("12,568.3") or a period key ("202608"), and
# not a number its unit follows ("ต่อปี 2500 บาท") — a year may end a sentence ("ปี 2569.")
_YEAR = r"(?<!\d)(?<!\d[.,])25\d\d(?!\d)(?![.,]\d)(?![\s*]*(?:ล้าน|บาท|แสน|หมื่น|พัน|%))"
_BE_YEAR = re.compile(_YEAR)
_YEAR_SPAN = re.compile(rf"(?:{_MARK})\s*{_YEAR}(?:\s*(?:เทียบกับ|เทียบ|กับ|และ|ถึง|หรือ|vs\.?|[-–—,])\s*{_YEAR})*")
# ค.ศ. year or YYYYMM period, พ.ศ. year — as a literal in SQL / a question / a cell
_LITERAL = re.compile(r"(?<!\d)(20\d\d|25\d\d)(0[1-9]|1[0-2])?(?!\d)")
_SHORT_BE = re.compile(r"(?:ปี|พ\.ศ\.)\s*(\d\d)(?!\d)")  # "ปี 69"
# the pieces of a statement a literal belongs to: a condition, a CASE branch, a select list — the AND of
# BETWEEN is not a boundary ("year_month BETWEEN 202601 AND 202608" is one condition)
_SQL_BREAK = re.compile(r"\b(?:AND|OR|SELECT|FROM|WHERE|HAVING|ON|WHEN|THEN|ELSE|END|JOIN|GROUP\s+BY|ORDER\s+BY|LIMIT)\b",
                        re.I)
_BETWEEN_AND = re.compile(r"(\bBETWEEN\s+\S+\s+)AND\b", re.I)
_IDENT = re.compile(r'"([^"]+)"|\b([A-Za-z_]\w*)')  # a Thai column name is always quoted


def _years_in(text: str) -> Set[int]:
    """พ.ศ. years named by literals in text: 2026 / 202608 → 2569, 2569 stays 2569."""
    years = set()
    for year, _month in _LITERAL.findall(text or ""):
        year = int(year)
        years.add(year + BE_OFFSET if year < 2500 else year)
    return years


def answer_years(question: str, sql: str, rows: Optional[Iterable[dict]], schema_metadata=None) -> Set[int]:
    # ponytail: a period column whose name says nothing (declared only in scope_columns, e.g. `fiscal_key`)
    # is not seen here — pass the context's scope columns in when a context has one
    measures = {str(c.get("column_name") or "").lower() for c in schema_metadata or [] if c.get("is_summable")}

    def period(name: str) -> bool:
        return is_time_column(name, name.lower() in measures)

    years = _years_in(question) | {2500 + int(short) for short in _SHORT_BE.findall(question or "")}
    for piece in _SQL_BREAK.split(_BETWEEN_AND.sub(r"\1", sql or "")):
        if any(period(quoted or bare) for quoted, bare in _IDENT.findall(piece)):
            years |= _years_in(piece)
    for row in rows or []:
        for column, value in row.items():
            if isinstance(value, bool) or not period(str(column)):
                continue
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            if isinstance(value, (int, str)):
                years |= _years_in(str(value))
    return years


def fix_text(text: str, years: Set[int]) -> str:
    said = {int(y) for span in _YEAR_SPAN.finditer(text or "") for y in _BE_YEAR.findall(span.group(0))}
    if not said or not years or said <= years:
        return text

    def hits(shift: int) -> int:  # distinct years: a prior year named three times is still one year
        return sum(1 for y in said if y + shift in years)

    # most years landed; then no change; then the smallest slip (the model's slip runs low: +k first)
    best = max({y - s for y in years for s in said} | {0}, key=lambda k: (hits(k), k == 0, -abs(k), k))
    if best == 0 or hits(best) <= hits(0):
        return text
    return _YEAR_SPAN.sub(lambda span: _BE_YEAR.sub(lambda y: str(int(y.group(0)) + best), span.group(0)), text)


def fix_explanation(explanation: Any, question: str, sql: str, rows, schema_metadata=None) -> Any:
    """The explanation (text, or dict with text + chart title) with its พ.ศ. years set right."""
    years = answer_years(question, sql, rows, schema_metadata)
    if isinstance(explanation, dict):
        for key in ("explanation", "chart_title"):
            if isinstance(explanation.get(key), str):
                explanation[key] = fix_text(explanation[key], years)
        return explanation
    return fix_text(explanation, years) if isinstance(explanation, str) else explanation
