"""
NT AI Assistant - Dimension Family Auto-Detection
=====================================================
Pure-function engine that groups related columns into dimension families
based on naming conventions. Zero DB/AI cost.

Algorithm:
1. Strip known suffixes to find column stems
2. Group columns sharing the same stem
3. Map stems to category prefixes via lookup
4. Handle special cases (Thai columns, time columns)
5. Return only groups with 2+ members
"""

import re
from typing import Dict, List, Tuple

# Suffixes to strip, longest first so _DEPARTMENT matches before _NAME
_SUFFIXES = [
    "_DEPARTMENT", "_GROUP", "_ABBR", "_NAME", "_CODE", "_KEY", "_TYPE",
    "_VALUE", "_DESC", "_DESCRIPTION", "_ID", "_NO", "_NUMBER",
]

# Stem → category prefix mapping
_STEM_TO_CATEGORY: Dict[str, str] = {
    "DIVISION": "org_division",
    "GROUP": "org_group",
    "DEPARTMENT": "org_department",
    "SECTION": "org_section",
    "COST_CENTER": "org_cost_center",
    "GL": "acct_gl",
    "REPORT": "acct_report",
    "PRODUCT": "product",
    "SERVICE": "product_service",
    "BUSINESS": "biz",
    "REVENUE": "value_revenue",
}

# Thai column → family mapping
_THAI_FAMILIES: Dict[str, str] = {
    "กลุ่มธุรกิจ": "biz_item",
    "หมวดบัญชี": "acct_category",
}

# Time-related columns
_TIME_COLUMNS = {"YEAR", "MONTH", "DATE"}


def _strip_suffix(col: str) -> str:
    """Strip known suffix from a column name (case-insensitive, longest first)."""
    upper = col.upper()
    for suffix in _SUFFIXES:
        if upper.endswith(suffix) and len(upper) > len(suffix):
            return col[: len(col) - len(suffix)]
    return col


def _categorize_stem(stem: str) -> str:
    """Map a stem to a category name via lookup table."""
    upper = stem.upper()
    if upper in _STEM_TO_CATEGORY:
        return _STEM_TO_CATEGORY[upper]
    # Default: use lowercase stem as category
    return upper.lower()


def detect_families(column_names: List[str]) -> Dict[str, List[str]]:
    """Detect dimension families from column naming conventions.

    Args:
        column_names: List of column names (case preserved).

    Returns:
        Dict mapping family name to list of column names.
        Only includes families with 2+ members.

    Example:
        >>> detect_families(["SECTION", "SECTION_ABBR", "GL_CODE", "GL_NAME", "YEAR"])
        {'org_section': ['SECTION', 'SECTION_ABBR'], 'acct_gl': ['GL_CODE', 'GL_NAME']}
    """
    if not column_names:
        return {}

    # Track: stem → list of original column names
    stem_groups: Dict[str, List[str]] = {}
    # Track: stem → representative (upper) for category lookup
    stem_upper: Dict[str, str] = {}

    # Phase 1: Handle Thai special columns separately
    thai_families: Dict[str, List[str]] = {}
    remaining: List[str] = []

    for col in column_names:
        if col in _THAI_FAMILIES:
            family = _THAI_FAMILIES[col]
            thai_families.setdefault(family, []).append(col)
        else:
            remaining.append(col)

    # Phase 2: Handle time columns
    time_cols: List[str] = []
    non_time: List[str] = []

    for col in remaining:
        if col.upper() in _TIME_COLUMNS:
            time_cols.append(col)
        else:
            non_time.append(col)

    # Phase 3: Stem-based grouping for remaining columns
    for col in non_time:
        stem = _strip_suffix(col)
        stem_key = stem.upper()  # case-insensitive grouping

        stem_groups.setdefault(stem_key, []).append(col)
        if stem_key not in stem_upper:
            stem_upper[stem_key] = stem_key

    # Phase 4: Build result
    result: Dict[str, List[str]] = {}

    # Add time family
    if len(time_cols) >= 2:
        result["time"] = sorted(time_cols, key=lambda c: c.upper())

    # Add Thai families
    for family, cols in thai_families.items():
        if len(cols) >= 2:
            result[family] = cols

    # Add stem-based families (only 2+ members)
    for stem_key, cols in stem_groups.items():
        if len(cols) >= 2:
            category = _categorize_stem(stem_key)
            result[category] = sorted(cols, key=lambda c: c.upper())

    return result
