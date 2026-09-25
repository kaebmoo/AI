"""
NT AI Assistant - Chart Post-Processor
========================================
Shared logic for parsing AI chart/visualization responses
and enforcing the Time-Series Rule and Dimension Family Rule
across all providers.
"""

import json
import re
import logging
from typing import Dict, List, Any, Optional

from app.services.chart.engine import (
    TEMPORAL_TYPES,
    decide_chart_structure,
)
from app.services.chart.engine import _suggest_available_types  # noqa: F401 — compatibility re-export
from app.services.chart.engine import resolve_max_series_warning  # noqa: F401 — compatibility re-export
from app.services.chart.profiler import DEFAULT_MAX_SERIES, _is_time_column
from app.services.chart.profiler import profile_chart_data  # noqa: F401 — compatibility re-export

logger = logging.getLogger(__name__)

_BAHT_RANGE_RE = re.compile(
    r"(?P<start>-?\d[\d,]*(?:\.\d+)?)\s*(?P<sep>-|–|—|ถึง)\s*"
    r"(?P<end>-?\d[\d,]*(?:\.\d+)?)\s*บาท"
)
_BAHT_VALUE_RE = re.compile(r"(?P<value>-?\d[\d,]*(?:\.\d+)?)\s*บาท")

def _format_million_baht(raw_value: str) -> Optional[str]:
    """Compact raw-baht literals in narrative text; leave sub-million values alone."""
    try:
        value = float(raw_value.replace(',', ''))
    except (TypeError, ValueError):
        return None
    if abs(value) < 1_000_000:
        return None
    compact = f"{value / 1_000_000:,.2f}".rstrip('0').rstrip('.')
    return f"{compact} ล้านบาท"


def compact_explanation_currency(text: str) -> str:
    """Convert large raw-baht amounts in AI prose to consistent million-baht text."""
    def replace_range(match: re.Match) -> str:
        start = _format_million_baht(match.group('start'))
        end = _format_million_baht(match.group('end'))
        if not start or not end:
            return match.group(0)
        return f"{start.removesuffix(' ล้านบาท')}{match.group('sep')}{end}"

    def replace_value(match: re.Match) -> str:
        return _format_million_baht(match.group('value')) or match.group(0)

    return _BAHT_VALUE_RE.sub(replace_value, _BAHT_RANGE_RE.sub(replace_range, text))


def _compact_parsed_explanation(parsed_result: Dict) -> Dict:
    if not isinstance(parsed_result, dict):
        return {"explanation": str(parsed_result)}
    explanation = parsed_result.get("explanation")
    if isinstance(explanation, str):
        parsed_result["explanation"] = compact_explanation_currency(explanation)
    return parsed_result


def parse_explanation_response(text: str) -> Dict:
    """
    Parse JSON from AI response text.
    Handles: pure JSON, markdown code blocks, and embedded JSON objects.

    Returns dict with at least {"explanation": ...}
    """
    parsed_result = {"explanation": text}

    # 1. Try pure JSON
    try:
        parsed_result = json.loads(text)
        return _compact_parsed_explanation(parsed_result)
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Try to extract JSON from markdown code blocks
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            parsed_result = json.loads(match.group(1))
            return _compact_parsed_explanation(parsed_result)
    except (json.JSONDecodeError, TypeError):
        pass

    # 3. Try to find first { and last }
    try:
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            parsed_result = json.loads(match.group(1))
            return _compact_parsed_explanation(parsed_result)
    except (json.JSONDecodeError, TypeError):
        pass

    return _compact_parsed_explanation(parsed_result)


def enforce_time_series_rule(parsed_result: Dict, time_columns: Optional[List[str]] = None) -> Dict:
    """
    Post-process chart config to ensure Time columns are on X-axis (category),
    not on legend (series). Swaps if necessary.

    Time-Series Rule:
    - If series_column is a time column BUT category_column is NOT → SWAP them
    - If swap happens on grouped_bar → force stacked_bar

    Args:
        parsed_result: Parsed AI response dict
        time_columns: Optional list of known time columns from schema_metadata.
                      If provided, uses exact match instead of keyword heuristic.
    """
    try:
        # Ensure we have a dict
        if isinstance(parsed_result, str):
            parsed_result = {"explanation": parsed_result}

        if "chart_config" not in parsed_result:
            return parsed_result

        config = parsed_result["chart_config"]
        cat = str(config.get("category_column", "")).lower()
        series = str(config.get("series_column", "")).lower()

        # Use schema_metadata time_columns if available, else fallback to keyword heuristic
        is_series_time = _is_time_column(series, time_columns)
        is_cat_time = _is_time_column(cat, time_columns)

        logger.debug(f"Chart Config: Cat='{cat}', Series='{series}', IsSeriesTime={is_series_time}, IsCatTime={is_cat_time}")

        # If Series is Time BUT Category is NOT Time -> SWAP
        if is_series_time and not is_cat_time:
            logger.info(f"Time-Series Rule violated. Swapping '{cat}' <-> '{series}'")
            config["category_column"] = config["series_column"]
            config["series_column"] = cat
            # Force Stacked Bar if swapping happened on grouped_bar
            if parsed_result.get("visualization") == "grouped_bar":
                parsed_result["visualization"] = "stacked_bar"

        return parsed_result
    except Exception as e:
        logger.error(f"Error in enforce_time_series_rule: {e}")
        return parsed_result


def enforce_categorical_axis_rule(
    parsed_result: Dict,
    time_columns: Optional[List[str]] = None,
    data: Optional[List[Dict]] = None,
) -> Dict:
    """
    Post-process chart config to ensure line/area-family charts only appear
    when category_column is a time dimension. If the LLM proposes a temporal
    chart type over a non-time category, downgrade to the bar-family
    equivalent (deterministic — does not trust the LLM's choice).

    Run AFTER enforce_time_series_rule (which may have already swapped
    category/series so the final category_column reflects the real axis).
    """
    try:
        if isinstance(parsed_result, str):
            parsed_result = {"explanation": parsed_result}

        viz = parsed_result.get("visualization")
        if viz not in TEMPORAL_TYPES:
            return parsed_result

        cat = (parsed_result.get("chart_config") or {}).get("category_column")
        if cat and _is_time_column(cat, time_columns):
            return parsed_result

        downgrade = {
            "line_chart": "bar_chart",
            "area": "bar_chart",
            "multi_line": "grouped_bar",
            "stacked_area": "stacked_bar",
        }
        logger.info(f"Categorical Axis Rule violated. Downgrading '{viz}' -> '{downgrade[viz]}' (category='{cat}')")
        parsed_result["visualization"] = downgrade[viz]
        cfg = parsed_result.setdefault("chart_config", {})
        cfg["warning"] = "ปรับจากกราฟเส้นเป็นกราฟแท่ง เนื่องจากแกน X ไม่ใช่คาบเวลา"
        return parsed_result
    except Exception as e:
        logger.error(f"Error in enforce_categorical_axis_rule: {e}")
        return parsed_result


def enforce_dimension_family_rule(
    parsed_result: Dict,
    families: Optional[Dict[str, List[str]]] = None,
) -> Dict:
    """
    Post-process chart config to ensure columns from the same dimension family
    are never split across category_column and series_column.

    If category_column and series_column belong to the same family:
    - Clear series_column (keep category only)
    - Downgrade grouped_bar/stacked_bar → bar_chart

    Args:
        parsed_result: Parsed AI response dict (may contain chart_config)
        families: Dimension families dict, e.g. {'org_section': ['SECTION', 'SECTION_ABBR']}
    """
    try:
        if not families or not isinstance(parsed_result, dict):
            return parsed_result

        if "chart_config" not in parsed_result:
            return parsed_result

        config = parsed_result["chart_config"]
        cat = str(config.get("category_column", "")).upper()
        series = str(config.get("series_column", "")).upper()

        if not cat or not series:
            return parsed_result

        # Build reverse lookup: column_upper → group
        col_to_group: Dict[str, str] = {}
        for group, cols in families.items():
            for col in cols:
                col_to_group[col.upper()] = group

        cat_group = col_to_group.get(cat)
        series_group = col_to_group.get(series)

        if cat_group and series_group and cat_group == series_group:
            logger.info(
                f"Dimension Family Rule violated: '{config.get('category_column')}' and "
                f"'{config.get('series_column')}' both belong to family '{cat_group}'. "
                f"Clearing series_column."
            )
            config["series_column"] = ""
            viz = parsed_result.get("visualization", "")
            if viz in ("grouped_bar", "stacked_bar"):
                parsed_result["visualization"] = "bar_chart"

        return parsed_result
    except Exception as e:
        logger.error(f"Error in enforce_dimension_family_rule: {e}")
        return parsed_result


def build_dimension_family_prompt(families: Dict[str, List[str]]) -> str:
    """
    Generate a prompt snippet listing dimension families for LLM awareness.

    Args:
        families: Dict mapping group name to list of column names

    Returns:
        Prompt text to append to the explain_result system prompt,
        or empty string if no families.
    """
    if not families:
        return ""

    lines = [
        "\n\nDIMENSION FAMILY RULE (CRITICAL):",
        "Columns in the same family represent the SAME entity (code/abbreviation/name).",
        "They MUST be on the SAME axis. NEVER put one as category_column and another as series_column.",
        "Families:"
    ]
    for group, cols in sorted(families.items()):
        lines.append(f"  - {group}: {', '.join(cols)}")

    return "\n".join(lines)


def build_explain_prompt(
    question: str,
    sql: str,
    data: List[Dict],
    dimension_families: Optional[Dict[str, List[str]]] = None,
    hierarchy_info: Optional[List[Dict]] = None,
    schema_metadata: Optional[List[Dict]] = None,
) -> str:
    """
    Build the explain_result prompt dynamically — shared across all providers.

    Args:
        question: User's original question
        sql: Generated SQL query
        data: Query result data rows
        dimension_families: Column family groups (for family rule prompt)
        hierarchy_info: Hierarchy levels from master_hierarchy [{level_label_th, level_columns}]
        schema_metadata: Column metadata [{column_name, is_summable, dimension_group, ...}]
    """
    data_preview = json.dumps(data, ensure_ascii=False, default=str)
    family_prompt = build_dimension_family_prompt(dimension_families) if dimension_families else ""

    # Build column hints from schema_metadata
    column_hints = ""
    if schema_metadata:
        measure_cols = [m['column_name'] for m in schema_metadata if m.get('is_summable')]
        time_cols = [m['column_name'] for m in schema_metadata
                     if m.get('dimension_group') == 'time_period']
        groupable_cols = [m['column_name'] for m in schema_metadata
                          if m.get('is_groupable') and m.get('dimension_group') != 'time_period'
                          and not m.get('is_summable')]

        if measure_cols or time_cols or groupable_cols:
            column_hints = "\n\nCOLUMN HINTS (from schema metadata):"
            if measure_cols:
                column_hints += f"\n  Measure columns (summable): {', '.join(measure_cols)}"
            if time_cols:
                column_hints += f"\n  Time columns: {', '.join(time_cols)}"
            if groupable_cols:
                column_hints += f"\n  Groupable dimensions: {', '.join(groupable_cols[:10])}"
                if len(groupable_cols) > 10:
                    column_hints += f" (and {len(groupable_cols) - 10} more)"

    # Build hierarchy examples from master_hierarchy
    hierarchy_example = ""
    if hierarchy_info and len(hierarchy_info) >= 2:
        hierarchy_chain = " > ".join(h.get('level_label_th', '') for h in hierarchy_info)
        # Get column names for example
        example_cols = []
        for h in hierarchy_info:
            try:
                cols = json.loads(h.get('level_columns', '[]'))
                if cols:
                    example_cols.append(cols[0])
            except (ValueError, IndexError):
                pass
        hierarchy_example = f"""
Example for hierarchical data (hierarchy: {hierarchy_chain}):
{{{{
  "display_hint": "hierarchical",
  "hierarchy_columns": {json.dumps(example_cols, ensure_ascii=False)}
}}}}"""

    # The model converted 2026 into "2566" by itself (RESULT_F11 §9): it is handed the converted years instead,
    # and thai_year.fix_explanation still checks what it writes. Imported here: app.services.ai imports providers.
    from app.services.ai.thai_year import BE_OFFSET, answer_years
    years = sorted(answer_years(question, sql, data, schema_metadata))
    year_rule = ("\n5. **ปี พ.ศ. ของข้อมูลนี้แปลงไว้แล้ว:** "
                 + ", ".join(f"ค.ศ. {y - BE_OFFSET} = พ.ศ. {y}" for y in years)
                 + " — เขียนปีตามนี้ ห้ามแปลงปีเอง") if years else ""

    return f"""Question: {question}
SQL: {sql}
Results ({len(data)} rows):
{data_preview}
{column_hints}
{family_prompt}

Explain in Thai.
CRITICAL RULES:
1. **SQL is the ground truth** — describe ONLY what the SQL actually queries. If the SQL has no WHERE filter for a province/department, do NOT mention any specific province/department. Look at the SQL's WHERE clause and GROUP BY to understand the scope.
2. **Dimension columns** (Year/ปี, Month/เดือน, Quarter/ไตรมาส) — NEVER SUM or aggregate them. Report as-is (e.g., "เดือนมกราคม 2568" NOT "เดือนที่ 78").
3. Only SUM/aggregate **MEASURE columns** (revenue, amount, cost, etc.).
4. If data has multiple months, summarize each month individually or say "เดือน 1-12" — do NOT add month numbers together.{year_rule}

Ensure the "explanation" value is formatted as **beautiful Markdown**:
- Use `###` for main summaries and `####` for subsections.
- Use **bold text** (`**value**`) to highlight key metrics and numbers.
- Use bullet points (`-`) when listing multiple items (e.g., breakdown by group).
- Use blockquotes (`>`) to emphasize key insights or the most important finding.
- Keep the language natural and strictly in **Thai**.
- **Number formatting**: Source values are in baht. In the narrative, convert absolute values >= 1,000,000 baht to **ล้านบาท** by dividing by 1,000,000 (e.g., 7,400,000,000 บาท → 7,400 ล้านบาท; -3,686,967,403 บาท → -3,686.97 ล้านบาท). Keep smaller values in baht with comma separators. Do NOT wrap positive numbers in parentheses; use a minus sign for negative values.
- **DO NOT** mention or explain your choice of visualization (e.g. "We chose a Grouped Bar Chart because...") or table formats (like crosstab) in the `explanation`. The explanation must ONLY focus on answering the question and data insights.

CRITICAL: You must analyze the data and recommend the best visualization type.
Return the result as a JSON object with these keys:
1. "explanation": The beautifully formatted Thai markdown explanation.
2. "visualization": One of ['bar_chart', 'horizontal_bar', 'line_chart', 'pie_chart', 'donut_chart', 'table', 'single_value', 'grouped_bar', 'stacked_bar', 'waterfall', 'heatmap']
2b. "chart_title": (optional) Short Thai title for the chart, e.g. "รายได้ตามกลุ่มธุรกิจ Q1/2567"
3. "chart_config": Object with column mappings for the chart:
   - "category_column": The column name for X-axis labels (the PRIMARY grouping)
   - "measure_column": The column name for Y-axis values (e.g., total, sum, amount)
   - "series_column": (optional) The column for SECONDARY grouping/comparison
4. "display_hint": How to display the TABLE (separate from chart). Choose ONE:
   - 'hierarchical': ONLY when columns are STRICT parent-child. Each child belongs to EXACTLY ONE parent.
     DO NOT use hierarchical when columns are INDEPENDENT dimensions (cross-dimensions).
   - 'crosstab': When comparing values across a time dimension (month, quarter, year) OR across any two independent dimensions.
     USE THIS when data has: category × time × measure.
   - 'flat': For single-dimension data, already aggregated, when unsure,
     OR when SQL already has pre-pivoted columns (e.g., month names as columns like "ม.ค.", "ก.พ.", "มี.ค.").
     USE 'flat' when the SQL output is already in the desired display format and should NOT be re-pivoted.
5. "hierarchy_columns": (REQUIRED if display_hint='hierarchical') Array of actual column names ordered HIGHEST (parent) to LOWEST (child).

IMPORTANT for chart type selection:
- 'line_chart', 'area': ONLY when category_column is a time dimension (Month/Year/Date).
  For categorical breakdowns (account, department, product) with no time axis,
  use 'bar_chart' (<=6 categories) or 'horizontal_bar' (>6 or long Thai labels).

IMPORTANT for time-based comparisons:
- For a normal trend/comparison chart, use the Time column (Month, Year, Date) as 'category_column' (X-axis).
- Use the other dimension (Department, Account, Section) as 'series_column' (Legend).
     - **Legend Rule**: Prefer DESCRIPTIVE columns (e.g., 'department_name', 'account_name') over ID/Code columns for better readability.
     - If < 5 series: Suggest 'grouped_bar' or 'line_chart'
     - If > 5 series: Suggest 'stacked_bar' (to avoid clutter)
- **Exception**: Only use Time as Series if explicitly asked to "Compare Years" (Year-over-Year).

IMPORTANT for matrix/cross-dimension data:
- When data has TWO categorical dimensions and ONE numeric measure forming a matrix
  (e.g., owner × user, source × destination, sender × receiver, division × division),
  use **'heatmap'** for visualization. Set:
  - "category_column" = row dimension (e.g., owner_division)
  - "series_column" = column dimension (e.g., user_division)
  - "measure_column" = the numeric value
- For the table: use display_hint='crosstab' to show the matrix as a cross-tabulation.
- A time dimension may be the series/column dimension for a heatmap. When the
  result is a dense matrix (at least 6 periods × 8 categories), prefer:
  `category_column` = the descriptive category (heatmap rows),
  `series_column` = the time period (heatmap columns),
  `visualization` = 'heatmap'.
- When there are 6+ periods but no more than 5 categories, prefer 'multi_line'
  with time on the category axis. The post-processor validates this choice
  against the actual result shape.
{hierarchy_example}
"""


def auto_detect_chart_config(data: List[Dict], parsed_result: Dict = None,
                             schema_metadata: Optional[List[Dict]] = None) -> Dict:
    """
    Fallback: infer chart config from data shape when AI doesn't provide one.

    Args:
        data: Query result data rows
        parsed_result: Existing parsed result to augment (or None for new dict)
        schema_metadata: Optional list of column metadata dicts with is_summable,
                         dimension_group, etc. from schema_metadata table.
    """
    if parsed_result is None:
        parsed_result = {}

    if not data or len(data) == 0:
        return parsed_result

    viz_type = parsed_result.get("visualization") or "bar_chart"
    decision = decide_chart_structure(
        data=data,
        measure_column=None,
        visualization=viz_type,
        schema_metadata=schema_metadata,
    )
    category_col = decision.category_column
    series_col = decision.series_column
    measure_col = decision.measure_column
    viz_type = decision.visualization

    logger.info(f"Auto-detected: viz={viz_type}, cat={category_col}, measure={measure_col}, series={series_col}")

    parsed_result["visualization"] = viz_type
    parsed_result["chart_config"] = {
        "category_column": category_col,
        "measure_column": measure_col,
        "series_column": series_col or "",
    }

    return parsed_result


def _can_infer_chart(data: List[Dict]) -> bool:
    """Return true when the result has at least one dimension and measure."""
    if not data:
        return False
    keys = list(data[0].keys())
    if len(keys) < 2:
        return False
    numeric = 0
    for key in keys:
        values = [row.get(key) for row in data if row.get(key) is not None]
        if values and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in values
        ):
            numeric += 1
    return numeric > 0 and numeric < len(keys)


def postprocess_chart_result(
    result: Any,
    data: List[Dict],
    dimension_families: Optional[Dict[str, List[str]]] = None,
    hierarchy_info: Optional[list] = None,
    schema_metadata: Optional[List[Dict]] = None,
) -> Any:
    """Parse and make one deterministic chart decision from the supplied data.

    Providers may use a reduced payload to control LLM tokens. Callers that
    have the query's full result should call this function again with that full
    result; the narrative/title are retained while chart structure is rebuilt.
    """
    del hierarchy_info  # kept in the shared signature for provider compatibility
    was_plain_text = isinstance(result, str)
    parsed_result = parse_explanation_response(result) if was_plain_text else result
    if not isinstance(parsed_result, dict):
        return result

    if not parsed_result.get("chart_config") and _can_infer_chart(data):
        parsed_result = auto_detect_chart_config(
            data, parsed_result, schema_metadata=schema_metadata
        )

    time_columns = [
        meta["column_name"] for meta in schema_metadata or []
        if meta.get("dimension_group") == "time_period" and meta.get("column_name")
    ] or None
    parsed_result = enforce_time_series_rule(parsed_result, time_columns=time_columns)
    parsed_result = enforce_dimension_family_rule(parsed_result, dimension_families)
    parsed_result = enforce_categorical_axis_rule(parsed_result, time_columns=time_columns)

    if not parsed_result.get("chart_config"):
        return result if was_plain_text else parsed_result

    config = parsed_result.get("chart_config") or {}
    chart_title = parsed_result.get("chart_title") or config.get("title", "")
    return enrich_chart_config(
        parsed_result=parsed_result,
        data=data,
        schema_metadata=schema_metadata,
        chart_title=chart_title,
    )


# ── enrich_chart_config: Step 4 in post-processing pipeline ──────────────────

# Money-related column keywords
_MONEY_KW = [
    'revenue', 'income', 'expense', 'cost', 'profit', 'amount',
    'total', 'sum', 'budget', 'value', 'baht',
    'รายได้', 'ค่าใช้จ่าย', 'กำไร', 'ยอด', 'งบ', 'มูลค่า',
]
_PCT_KW = ['percent', 'rate', 'ratio', 'pct', 'เปอร์เซ็น', 'อัตรา', '%']


def _detect_col_format(col: str) -> str:
    lower = col.lower()
    if any(k in lower for k in _PCT_KW):
        return 'percent'
    if any(k in lower for k in _MONEY_KW):
        return 'currency_thb'
    return 'number'


def _build_display_label(col: str, schema_metadata: Optional[List[Dict]] = None) -> str:
    """Build a human-readable display label for chart axis from column name + schema metadata."""
    # Try schema_metadata for Thai display name
    if schema_metadata:
        meta = next((m for m in schema_metadata if m.get('column_name') == col), None)
        if meta:
            display_name = meta.get('display_name_th') or meta.get('display_name_en') or col
            # Check for unit hint in special_notes or description
            desc = (meta.get('description') or '').lower()
            if 'ล้านบาท' in desc:
                return f"{display_name} (ล้านบาท)"
            elif 'บาท' in desc or 'baht' in desc:
                return f"{display_name} (บาท)"
            elif _detect_col_format(col) == 'currency_thb':
                return display_name
            return display_name

    # Fallback: detect from column name keywords
    lower = col.lower()
    if 'million' in lower or '_mb' in lower or col.endswith('_m'):
        return f"{col} (ล้านบาท)"
    if 'ล้านบาท' in col or 'ล้าน' in lower:
        return col
    if any(k in lower for k in _PCT_KW):
        return f"{col} (%)"
    return col


def enrich_chart_config(
    parsed_result: Dict,
    data: List[Dict],
    schema_metadata: Optional[List[Dict]] = None,
    chart_title: str = "",
    max_series: Optional[int] = None,
    requested_type: Optional[str] = None,
) -> Dict:
    """
    Step 4 in post-processing pipeline — AFTER enforce_dimension_family_rule().

    Adds: suggested_type (ECharts-ready), available_types, column_roles,
          title, sort_by, show_data_labels, warning, max_series (Wave 4).

    Repairs a missing series_column when the data shape is unambiguously
    category × time × measure; otherwise preserves the AI mapping.

    max_series: caller-resolved 3-tier value (admin_config -> .env -> default).
        Falls back to DEFAULT_MAX_SERIES when the caller doesn't have DB access
        (this module deliberately doesn't) — callers that DO (app/api/v1/chat.py)
        should pass the real resolved value.
    """
    try:
        from app.models.chart import ChartSpec, VISUALIZATION_TO_ECHARTS

        if not isinstance(parsed_result, dict):
            return parsed_result

        config = parsed_result.get("chart_config")
        if not config:
            return parsed_result

        resolved_max_series = max_series if max_series is not None else DEFAULT_MAX_SERIES
        decision = decide_chart_structure(
            data=data,
            category_column=config.get("category_column") or None,
            series_column=config.get("series_column") or None,
            measure_column=config.get("measure_column") or None,
            visualization=parsed_result.get("visualization", ""),
            schema_metadata=schema_metadata,
            max_series=resolved_max_series,
            requested_type=requested_type,
            title=chart_title,
        )
        matrix = decision.matrix
        cat_col = decision.category_column or ""
        msr_col = decision.measure_column or ""
        ser_col = decision.series_column or ""
        viz = decision.visualization
        has_time_cat = decision.has_time_category

        if cat_col:
            config['category_column'] = cat_col
        if ser_col:
            config['series_column'] = ser_col
        if msr_col:
            config['measure_column'] = msr_col
        parsed_result['visualization'] = viz
        if decision.warning:
            config['warning'] = decision.warning
        if matrix:
            logger.info(
                "Data-shape chart decision: kind=%s, rows=%s, columns=%s, viz=%s, coverage=%.2f",
                matrix['kind'], cat_col, ser_col, viz, matrix['coverage'],
            )

        # --- Column roles ---
        roles = []
        if cat_col:
            roles.append({
                "column": cat_col, "role": "category",
                "label": cat_col,
                "format": "date" if has_time_cat else "number",
            })
        if ser_col:
            roles.append({"column": ser_col, "role": "series", "label": ser_col})
        if msr_col:
            display_label = _build_display_label(msr_col, schema_metadata)
            roles.append({
                "column": msr_col, "role": "measure", "label": msr_col,
                "display_label": display_label,
                "format": _detect_col_format(msr_col), "axis": "left",
            })

        has_series = bool(ser_col)

        # --- ECharts-ready type (after all config repairs) ---
        echarts_type = VISUALIZATION_TO_ECHARTS.get(viz)
        if echarts_type == "line" and ser_col:
            echarts_type = "multi_line"

        # --- Warnings ---
        warning = config.get("warning") or decision.warning
        if viz in ('pie_chart', 'donut_chart') and has_series:
            warning = "Pie/Donut chart ไม่รองรับ series column — พิจารณาใช้ bar_chart แทน"

        # --- Sort hint ---
        sort_by = 'category_asc' if has_time_cat else 'original'

        # --- Merge into chart_config (extend, don't replace) ---
        config["suggested_type"] = echarts_type
        config["available_types"] = decision.available_types
        config["column_roles"] = roles
        config["title"] = chart_title or ""
        config["sort_by"] = sort_by
        config["show_data_labels"] = len(data) <= 20 if data else False
        config["is_time_axis"] = has_time_cat
        config["max_series"] = resolved_max_series
        if decision.chart_spec:
            config["chart_spec"] = ChartSpec.model_validate(
                decision.chart_spec
            ).model_dump(exclude_none=True)
        if warning:
            config["warning"] = warning

        return parsed_result

    except Exception as e:
        logger.error(f"Error in enrich_chart_config: {e}")
        return parsed_result
