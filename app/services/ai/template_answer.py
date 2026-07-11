"""
Template answers (PLAN F9 Phase A) — deterministic Thai explanations for
trivially small results, skipping the LLM explanation call entirely.

Numbers NEVER pass through an LLM on this path — no hallucinated digits.
Flag: admin_config `template_answers_enabled` (default OFF).
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_SINGLE_ROW_COLS = 3
MAX_TABLE_ROWS = 5


def is_template_eligible(data: List[Dict]) -> bool:
    """Narrow entry conditions — start small, widen later."""
    if not data:
        return False
    cols = len(data[0])
    if len(data) == 1 and cols <= MAX_SINGLE_ROW_COLS:
        return True
    if 2 <= len(data) <= MAX_TABLE_ROWS and cols == 2:
        return True
    return False


def _fmt_number(v) -> str:
    if isinstance(v, float):
        text = f"{v:,.2f}"
    elif isinstance(v, int):
        text = f"{v:,}"
    else:
        return str(v)
    if isinstance(v, (int, float)) and abs(v) >= 1_000_000:
        text += f" ({v / 1_000_000:,.1f} ล้าน)"
    return text


def _describe_conditions(sql_query: str) -> str:
    """Short provenance from the WHERE clause (best effort, deterministic)."""
    import re
    match = re.search(r"WHERE\s+(.*?)(?:GROUP BY|ORDER BY|LIMIT|$)", sql_query or "", re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    cond = " ".join(match.group(1).split())
    if len(cond) > 120:
        cond = cond[:120] + "…"
    return f" (เงื่อนไข: {cond})"


def build_template_answer(question: str, sql_query: str, data: List[Dict]) -> Optional[Dict]:
    """Build an explanation dict matching the LLM explanation contract, or None."""
    if not is_template_eligible(data):
        return None

    provenance = _describe_conditions(sql_query)

    if len(data) == 1:
        row = data[0]
        parts = [f"{k} = {_fmt_number(v)}" for k, v in row.items()]
        text = f"ผลลัพธ์: {', '.join(parts)}{provenance}"
        return {"explanation": text}  # single value — no chart

    # Small 2-column table: one dimension + one measure
    dim_col, val_col = list(data[0].keys())
    lines = [f"- {row[dim_col]}: {_fmt_number(row[val_col])}" for row in data]
    text = f"ผลลัพธ์ {len(data)} รายการ{provenance}\n" + "\n".join(lines)

    result = {
        "explanation": text,
        "visualization": "bar_chart",
        "chart_config": {"category_column": dim_col, "measure_column": val_col},
    }
    try:
        from app.providers.chart_postprocessor import enrich_chart_config
        result = enrich_chart_config(parsed_result=result, data=data, chart_title="")
    except Exception as e:
        logger.debug(f"Template answer: chart enrich skipped: {e}")
    return result
