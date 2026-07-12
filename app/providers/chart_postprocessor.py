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

logger = logging.getLogger(__name__)

# Time-related column name keywords (English + Thai)
TIME_KEYS = [
    'month', 'year', 'date', 'day', 'time', 'quarter', 'week',
    'hour', 'minute', 'second',
    'เดือน', 'ปี', 'วันที่', 'ไตรมาส', 'งวด', 'เวลา',
]

# visualization types that require a time-dimension category axis (C1)
TEMPORAL_TYPES = {"line_chart", "multi_line", "area", "stacked_area"}

# Wave 4 — hardcoded fallback tier only. The real 3-tier value (admin_config DB
# -> .env CHART_MAX_SERIES -> this) is resolved in AdminConfigService.get_chart_max_series()
# and applied in app/api/v1/chat.py — this module has no DB access by design (pure,
# wrapped in try/except everywhere), so it can only ever see this hardcoded default
# unless a caller explicitly passes max_series=.
DEFAULT_MAX_SERIES = 5


def _is_time_column(col: str, time_columns: Optional[List[str]] = None) -> bool:
    """True if `col` is a time-axis column.

    Checks schema_metadata-derived `time_columns` (dimension_group == 'time_period')
    AND the TIME_KEYS keyword heuristic — union, not either/or. A SQL alias
    (e.g. `month AS "เดือน"`) won't exact-match schema_metadata's raw column
    name, so the heuristic must still get a chance to catch it. A false
    positive here only means "don't downgrade" (trust the LLM's chart type);
    a false negative would visibly corrupt a legitimately time-based chart.
    """
    col_lower = str(col).lower()
    if time_columns and col_lower in [c.lower() for c in time_columns]:
        return True
    return any(t in col_lower for t in TIME_KEYS)


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
        return parsed_result
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Try to extract JSON from markdown code blocks
    try:
        match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            parsed_result = json.loads(match.group(1))
            return parsed_result
    except (json.JSONDecodeError, TypeError):
        pass

    # 3. Try to find first { and last }
    try:
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            parsed_result = json.loads(match.group(1))
            return parsed_result
    except (json.JSONDecodeError, TypeError):
        pass

    return parsed_result


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
4. If data has multiple months, summarize each month individually or say "เดือน 1-12" — do NOT add month numbers together.

Ensure the "explanation" value is formatted as **beautiful Markdown**:
- Use `###` for main summaries and `####` for subsections.
- Use **bold text** (`**value**`) to highlight key metrics and numbers.
- Use bullet points (`-`) when listing multiple items (e.g., breakdown by group).
- Use blockquotes (`>`) to emphasize key insights or the most important finding.
- Keep the language natural and strictly in **Thai**.
- **Number formatting**: Display numbers with comma separators (e.g., 233,764,256 บาท). Do NOT wrap positive numbers in parentheses — in accounting, parentheses mean negative values. For negative numbers, use a minus sign (e.g., -152,297 บาท).
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
- **CRITICAL**: If a Time column exists (Month, Year, Date), YOU MUST USE IT AS 'category_column' (X-axis).
- **Comparison**: Use the other dimension (Department, Account, Section) as 'series_column' (Legend).
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
- Do NOT use heatmap when one dimension is time-based — use line_chart or grouped_bar instead.
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

    keys = list(data[0].keys())

    # Build metadata-driven lookups if available
    meta_measure_cols = set()
    meta_time_cols = set()
    meta_dimension_cols = set()
    if schema_metadata:
        for m in schema_metadata:
            col = m.get('column_name', '')
            if m.get('is_summable'):
                meta_measure_cols.add(col.lower())
            dg = m.get('dimension_group', '')
            if dg == 'time_period':
                meta_time_cols.add(col.lower())
            if m.get('is_groupable'):
                meta_dimension_cols.add(col.lower())

    # Fallback patterns (used when schema_metadata not available)
    _measure_patterns = [
        'revenue', 'value', 'amount', 'total', 'sum', 'count', 'baht',
        'รายได้', 'จำนวน', 'ยอด',
    ]
    _dimension_patterns = [
        'year', 'month', 'date', 'day', 'week', 'quarter',
        'ปี', 'เดือน', 'วันที่', 'id',
    ]
    _time_patterns = ['month', 'year', 'date', 'เดือน', 'ปี', 'วันที่']

    # Find measure column
    measure_col = None
    numeric_cols = []

    for key in keys:
        sample_val = data[0][key]
        is_numeric = isinstance(sample_val, (int, float)) or (
            isinstance(sample_val, str)
            and sample_val.replace(',', '').replace('.', '').replace('-', '').isdigit()
        )
        if is_numeric:
            numeric_cols.append(key)

    # Priority 0 (metadata): Column marked is_summable
    if meta_measure_cols:
        for col in numeric_cols:
            if col.lower() in meta_measure_cols:
                measure_col = col
                break

    # Priority 1: Column with measure-like name
    if not measure_col:
        for col in numeric_cols:
            if any(p in col.lower() for p in _measure_patterns):
                measure_col = col
                break

    # Priority 2: Numeric column that's NOT a dimension
    if not measure_col:
        for col in reversed(numeric_cols):
            if not any(p in col.lower() for p in _dimension_patterns):
                measure_col = col
                break

    # Priority 3: Last numeric column
    if not measure_col and numeric_cols:
        measure_col = numeric_cols[-1]

    # Find category column
    category_col = None
    series_col = None
    potential_cats = [k for k in keys if k != measure_col]

    # Use metadata time columns if available
    if meta_time_cols:
        time_cats = [k for k in potential_cats if k.lower() in meta_time_cols]
        # Prefer month over year
        month_cols = [k for k in time_cats if 'month' in k.lower()]
        if month_cols:
            category_col = month_cols[0]
        elif time_cats:
            category_col = time_cats[0]
    else:
        has_month = any('month' in k.lower() for k in potential_cats)
        has_year = any('year' in k.lower() for k in potential_cats)
        if has_month:
            category_col = next((k for k in potential_cats if 'month' in k.lower()), potential_cats[0] if potential_cats else None)
        elif has_year:
            category_col = next((k for k in potential_cats if 'year' in k.lower()), potential_cats[0] if potential_cats else None)

    if not category_col and potential_cats:
        category_col = potential_cats[0]

    # Infer Series Column
    if len(potential_cats) >= 2:
        remaining_cols = [k for k in potential_cats if k != category_col]
        string_cols = []
        for col in remaining_cols:
            sample_val = data[0].get(col)
            if isinstance(sample_val, str):
                unique_vals = set(str(row.get(col, '')) for row in data[:50])
                if 2 <= len(unique_vals) <= 30:
                    string_cols.append(col)

        if string_cols:
            series_col = string_cols[0]
        else:
            non_year_cols = [k for k in remaining_cols if 'year' not in k.lower()]
            series_col = non_year_cols[0] if non_year_cols else (remaining_cols[0] if remaining_cols else None)

    # Determine visualization type
    if meta_time_cols:
        is_time_category = category_col and category_col.lower() in meta_time_cols
    else:
        is_time_category = category_col and any(
            pattern in category_col.lower() for pattern in _time_patterns
        )

    # Check for time on series side too
    if meta_time_cols:
        is_time_series = series_col and series_col.lower() in meta_time_cols
    else:
        is_time_series = series_col and any(
            pattern in series_col.lower() for pattern in _time_patterns
        )

    # Matrix/heatmap detection: 2 non-time categorical dims + 1 measure, many-to-many
    is_matrix = False
    if (series_col and category_col and measure_col
            and not is_time_category and not is_time_series):
        unique_cat = len(set(str(row.get(category_col, '')) for row in data[:100]))
        unique_ser = len(set(str(row.get(series_col, '')) for row in data[:100]))
        if unique_cat >= 3 and unique_ser >= 3:
            expected = unique_cat * unique_ser
            if len(data) >= expected * 0.4:
                is_matrix = True

    viz_type = "bar_chart"
    if is_matrix:
        viz_type = "heatmap"
    elif series_col and is_time_category:
        viz_type = "line_chart"
    elif series_col:
        viz_type = "stacked_bar"
    elif is_time_category and len(data) > 10:
        viz_type = "line_chart"

    logger.info(f"Auto-detected: viz={viz_type}, cat={category_col}, measure={measure_col}, series={series_col}")

    parsed_result["visualization"] = viz_type
    parsed_result["chart_config"] = {
        "category_column": category_col,
        "measure_column": measure_col,
        "series_column": series_col or "",
    }

    return parsed_result


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


def _suggest_available_types(
    n_categories: int,
    has_series: bool,
    has_time_category: bool,
    is_matrix: bool = False,
) -> list:
    """Rule-based available_types suggestion."""
    if is_matrix:
        return ['heatmap', 'grouped_bar', 'stacked_bar', 'table']
    if not has_series:
        if n_categories <= 8:
            types = ['bar_chart', 'horizontal_bar', 'line_chart', 'pie_chart', 'donut_chart']
        else:
            types = ['bar_chart', 'horizontal_bar', 'line_chart']
    else:
        if has_time_category:
            types = ['line_chart', 'multi_line', 'grouped_bar', 'stacked_bar', 'area']
        else:
            types = ['grouped_bar', 'stacked_bar', 'stacked_bar_100', 'bar_chart']

    # C2: category axis isn't time — line/area family isn't valid, drop it
    if not has_time_category:
        types = [t for t in types if t not in TEMPORAL_TYPES]
    return types


def resolve_max_series_warning(
    data: List[Dict],
    cat_col: str,
    ser_col: str,
    viz: str,
    max_series: int,
) -> Optional[str]:
    """Top-N + 'อื่นๆ' threshold warning (Wave 4) — shared between
    enrich_chart_config (hardcoded-default tier) and app/api/v1/chat.py's
    response formatting (real 3-tier-resolved value), so the two never drift
    out of sync on wording or the count they check.

    pie/donut bucket by distinct category_column values (each slice = one
    category); other multi-series chart types bucket by distinct
    series_column values. Single-series bar/line charts have nothing to
    bucket — always None for those.
    """
    if viz in ('pie_chart', 'donut_chart'):
        bucket_count = len(set(str(row.get(cat_col, '')) for row in data[:200])) if cat_col and data else 0
    elif ser_col:
        bucket_count = len(set(str(row.get(ser_col, '')) for row in data[:200])) if data else 0
    else:
        return None

    if bucket_count <= max_series:
        return None
    top_n = max_series - 1
    return f"แสดง Top-{top_n} จาก {bucket_count} กลุ่ม — กลุ่มที่เหลือรวมเป็น 'อื่นๆ' (ดูข้อมูลเต็มในตาราง)"


def enrich_chart_config(
    parsed_result: Dict,
    data: List[Dict],
    schema_metadata: Optional[List[Dict]] = None,
    chart_title: str = "",
    max_series: Optional[int] = None,
) -> Dict:
    """
    Step 4 in post-processing pipeline — AFTER enforce_dimension_family_rule().

    Adds: suggested_type (ECharts-ready), available_types, column_roles,
          title, sort_by, show_data_labels, warning, max_series (Wave 4).

    Does NOT change: category_column, measure_column, series_column,
                     visualization (backend string), or any existing rules output.

    max_series: caller-resolved 3-tier value (admin_config -> .env -> default).
        Falls back to DEFAULT_MAX_SERIES when the caller doesn't have DB access
        (this module deliberately doesn't) — callers that DO (app/api/v1/chat.py)
        should pass the real resolved value.
    """
    try:
        from app.models.chart import VISUALIZATION_TO_ECHARTS

        if not isinstance(parsed_result, dict):
            return parsed_result

        config = parsed_result.get("chart_config")
        if not config:
            return parsed_result

        viz = parsed_result.get("visualization", "")
        cat_col = config.get("category_column") or ""
        msr_col = config.get("measure_column") or ""
        ser_col = config.get("series_column") or ""

        # --- ECharts-ready type ---
        echarts_type = VISUALIZATION_TO_ECHARTS.get(viz)
        if echarts_type == "line" and ser_col:
            echarts_type = "multi_line"

        # --- Time axis detection: schema_metadata (dimension_group == 'time_period') first, else TIME_KEYS ---
        time_columns = [m['column_name'] for m in schema_metadata
                         if m.get('dimension_group') == 'time_period'] if schema_metadata else None
        has_time_cat = bool(cat_col) and _is_time_column(cat_col, time_columns)

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

        # --- Stats for suggestions ---
        n_categories = len(set(str(row.get(cat_col, '')) for row in data[:100])) if cat_col and data else 1
        has_series = bool(ser_col)

        # --- Warnings ---
        resolved_max_series = max_series if max_series is not None else DEFAULT_MAX_SERIES
        warning = None
        if viz in ('pie_chart', 'donut_chart') and has_series:
            warning = "Pie/Donut chart ไม่รองรับ series column — พิจารณาใช้ bar_chart แทน"
        else:
            warning = resolve_max_series_warning(data, cat_col, ser_col, viz, resolved_max_series)

        # --- Sort hint ---
        sort_by = 'category_asc' if has_time_cat else 'original'

        # --- Merge into chart_config (extend, don't replace) ---
        config["suggested_type"] = echarts_type
        is_matrix = viz == 'heatmap'
        config["available_types"] = _suggest_available_types(n_categories, has_series, has_time_cat, is_matrix=is_matrix)
        config["column_roles"] = roles
        config["title"] = chart_title or ""
        config["sort_by"] = sort_by
        config["show_data_labels"] = len(data) <= 20 if data else False
        config["is_time_axis"] = has_time_cat
        config["max_series"] = resolved_max_series
        if warning:
            config["warning"] = warning

        return parsed_result

    except Exception as e:
        logger.error(f"Error in enrich_chart_config: {e}")
        return parsed_result
