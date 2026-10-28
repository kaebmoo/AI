"""Amounts an explanation states, checked against the result in code (plan/PLAN_ANOMALY_AVG_FIX.md §6).

The model turns baht cells into ล้านบาท by itself and slips: "หลายหมื่นล้านบาท" for differences of 50–101 million
(audit 518), "993.7 ล้านบาท" for −99.37 million in 3 of 5 practice answers (2026-10-28). Like thai_year, the text
is read in code rather than the model asked to be careful."""

import bisect
import re
from typing import Any, Iterable, List

# D-2 = ก (owner 2026-10-28): the change an explanation may call ผิดปกติ / มีนัยสำคัญ
# ponytail: constants; an admin_config key when the owner wants to tune them per context
CHANGE_MIN_BAHT = 5_000_000
CHANGE_MIN_PCT = 30
CHANGE_MIN_SD = 2

_SCALE = {"ล้านล้าน": 1e12, "แสนล้าน": 1e11, "หมื่นล้าน": 1e10, "พันล้าน": 1e9, "ล้าน": 1e6, "แสน": 1e5, "หมื่น": 1e4,
          "พัน": 1e3}
# a figure with a money unit after it: "99.37 ล้านบาท", "**2,993** ล้าน", "612 บาท" — a year ("ปี 2569") or a
# percent has none, so neither is read; "2,568 ล้านบาท" is money
_AMOUNT = re.compile(r"(?<![\d.,])(\d[\d,]*(?:\.(\d+))?)[\s*]*(" + "|".join(_SCALE) + r")?[\s*]*(บาท)?")
# "หลายหมื่นล้านบาท" = at least two of that size
_SEVERAL = re.compile(r"หลาย\s*(สิบ|ร้อย|พัน|หมื่น|แสน)\s*ล้าน")
_SEVERAL_SIZE = {"สิบ": 1e7, "ร้อย": 1e8, "พัน": 1e9, "หมื่น": 1e10, "แสน": 1e11}
# a heading that suggests how to display the data (prompt forbids it; the model writes it anyway)
_DISPLAY_ADVICE = re.compile(r"^\s*(?:#{1,6}\s*|\*\*)[^\n]*ข้อเสนอแนะ[^\n]*(?:แสดงผล|กราฟ|แผนภูมิ|นำเสนอ)", re.M)
_HEADING = re.compile(r"^\s*(?:#{1,6}\s|\*\*[^\n]*\*\*\s*$)", re.M)


def stated(text: str) -> List[tuple]:
    """(baht, tolerance, as written) of each amount the text states; tolerance = one unit of the last digit it
    shows ("99.37" ±0.01 ล้าน, "500" ±100 ล้าน — the model truncates as often as it rounds), None for
    "หลาย…ล้าน" (a least value, checked against the top only)."""
    out = []
    for m in _AMOUNT.finditer(text or ""):
        number, decimals, scale, baht = m.groups()
        if not baht and not (scale or "").endswith("ล้าน"):
            continue
        size = _SCALE.get(scale, 1.0)
        digits = number.replace(",", "")
        zeros = len(digits) - len(digits.rstrip("0")) if digits.strip("0") else 0
        unit = 10.0 ** -len(decimals) if decimals else 10.0 ** zeros
        out.append((float(digits) * size, unit * size, m.group(0).strip(" *")))
    return out + [(2 * _SEVERAL_SIZE[m.group(1)], None, m.group(0)) for m in _SEVERAL.finditer(text or "")]


def supported(rows) -> List[float]:
    """|values| a result holds: every numeric cell, the difference of two cells of a row — or of one column, one
    period beside another (up to 200 rows) — and each column's sum and mean."""
    values, columns = [], {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cells = [(k, v) for k, v in row.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v]
        values += [abs(v) for _, v in cells]
        values += [abs(a - b) for i, (_, a) in enumerate(cells) for _, b in cells[i + 1:]]
        for k, v in cells:
            columns.setdefault(k, []).append(v)
    for column in columns.values():
        values += [abs(sum(column)), abs(sum(column) / len(column))]
        if len(column) <= 200:  # ponytail: O(n²) per column; past 200 rows the model saw an aggregate anyway
            values += [abs(a - b) for i, a in enumerate(column) for b in column[i + 1:]]
    return values


def unsupported(text: str, rows, extra: Iterable[float] = ()) -> List[str]:
    """The amounts text states that the result does not hold: above all it supports (+1%), or none of the values
    `supported` lists within the text's last digit. `extra` = amounts it may quote from elsewhere."""
    support = sorted(supported(rows) + [abs(v) for v in extra])
    if not support:
        return []

    def held(value, tol):
        i = bisect.bisect_left(support, value - tol)
        return i < len(support) and support[i] <= value + tol

    return [written for value, tol, written in stated(text)
            if value > support[-1] * 1.01 or (tol is not None and not held(value, tol))]


def quoted(question: str) -> List[float]:
    """Amounts an explanation may repeat that are not in the result: the question's own and the rule's threshold."""
    return [value for value, _, _ in stated(question)] + [CHANGE_MIN_BAHT]


def retry_note(bad: List[str]) -> str:
    return (f"\n(คำบรรยายรอบก่อนเขียนจำนวนเงินที่ผลลัพธ์ไม่มี: {', '.join(bad)} — ใช้เฉพาะตัวเลขจากผลลัพธ์: "
            f"แปลงบาทเป็นล้านบาทด้วยการหาร 1,000,000 และนับหลักก่อนเขียน เช่น 99,369,948 บาท = 99.37 ล้านบาท)")


def text_of(explanation: Any) -> str:
    if isinstance(explanation, dict):
        return explanation.get("explanation") or ""
    return explanation if isinstance(explanation, str) else ""


def with_text(explanation: Any, text: str) -> Any:
    if isinstance(explanation, dict):
        return {**explanation, "explanation": text}
    return text


def from_rows(explanation: Any, rows: List[dict], limit: int = 5) -> Any:
    """D-4 = ก: the explanation written from the rows in code (no number passes through the model); the chart
    fields of the model's answer stay."""
    from app.services.ai.template_answer import _fmt_number

    lines = [f"- {', '.join(f'{k} = {_fmt_number(v)}' for k, v in row.items())}" for row in rows[:limit]]
    head = f"ผลลัพธ์ {len(rows)} รายการ" + (f" — {limit} รายการแรก" if len(rows) > limit else "")
    return with_text(explanation, f"{head}\n" + "\n".join(lines)
                     + "\n\n_(คำบรรยายสร้างจากผลลัพธ์โดยตรง — ตัวเลขในคำบรรยายของโมเดลไม่ตรงกับผลลัพธ์)_")


def drop_display_advice(text: str) -> str:
    """Cut a "ข้อเสนอแนะการแสดงผล / กราฟ" section: from its heading to the next heading or the end."""
    match = _DISPLAY_ADVICE.search(text or "")
    if match is None:
        return text
    following = _HEADING.search(text, match.end())
    rest = text[following.start():] if following else ""
    return drop_display_advice((text[:match.start()].rstrip() + "\n\n" + rest.lstrip()).strip())
