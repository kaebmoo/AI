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


def enforce_time_series_rule(parsed_result: Dict) -> Dict:
    """
    Post-process chart config to ensure Time columns are on X-axis (category),
    not on legend (series). Swaps if necessary.

    Time-Series Rule:
    - If series_column is a time column BUT category_column is NOT → SWAP them
    - If swap happens on grouped_bar → force stacked_bar
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

        is_series_time = any(t in series for t in TIME_KEYS)
        is_cat_time = any(t in cat for t in TIME_KEYS)

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


def auto_detect_chart_config(data: List[Dict], parsed_result: Dict = None) -> Dict:
    """
    Fallback: infer chart config from data shape when AI doesn't provide one.
    Used primarily by Matcha provider.

    Args:
        data: Query result data rows
        parsed_result: Existing parsed result to augment (or None for new dict)

    Returns:
        Dict with visualization and chart_config added
    """
    if parsed_result is None:
        parsed_result = {}

    if not data or len(data) == 0:
        return parsed_result

    keys = list(data[0].keys())

    # Patterns for identifying column types
    measure_patterns = [
        'revenue', 'value', 'amount', 'total', 'sum', 'count', 'baht',
        'รายได้', 'จำนวน', 'ยอด',
    ]
    dimension_patterns = [
        'year', 'month', 'date', 'day', 'week', 'quarter',
        'ปี', 'เดือน', 'วันที่', 'id',
    ]
    time_patterns = ['month', 'year', 'date', 'เดือน', 'ปี', 'วันที่']

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

    # Priority 1: Column with measure-like name
    for col in numeric_cols:
        if any(p in col.lower() for p in measure_patterns):
            measure_col = col
            break

    # Priority 2: Numeric column that's NOT a dimension
    if not measure_col:
        for col in reversed(numeric_cols):
            if not any(p in col.lower() for p in dimension_patterns):
                measure_col = col
                break

    # Priority 3: Last numeric column
    if not measure_col and numeric_cols:
        measure_col = numeric_cols[-1]

    # Find category column
    category_col = None
    series_col = None
    potential_cats = [k for k in keys if k != measure_col]

    has_month = any('month' in k.lower() for k in potential_cats)
    has_year = any('year' in k.lower() for k in potential_cats)

    if has_month:
        category_col = next((k for k in potential_cats if 'month' in k.lower()), potential_cats[0] if potential_cats else None)
    elif has_year:
        category_col = next((k for k in potential_cats if 'year' in k.lower()), potential_cats[0] if potential_cats else None)
    elif potential_cats:
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
    is_time_category = category_col and any(
        pattern in category_col.lower() for pattern in time_patterns
    )

    viz_type = "bar_chart"
    if series_col and is_time_category:
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
