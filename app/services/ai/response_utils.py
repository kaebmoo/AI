import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional


logger = logging.getLogger(__name__)

EXPLANATION_MAX_ROWS = 200
_TEMPORAL_FALLBACK_KEYS = (
    "year", "month", "quarter", "date", "day", "week", "period",
    "ปี", "เดือน", "ไตรมาส", "วันที่", "งวด",
)


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return value is True or value == 1 or str(value).lower() in {"true", "1", "yes"}


def _metadata_columns(
    schema_metadata: Optional[List[Dict]],
    keys: Iterable[str],
    predicate,
) -> List[str]:
    key_by_lower = {str(key).lower(): key for key in keys}
    return [
        key_by_lower[str(meta.get("column_name", "")).lower()]
        for meta in schema_metadata or []
        if meta.get("column_name")
        and str(meta.get("column_name")).lower() in key_by_lower
        and predicate(meta)
    ]


def _temporal_columns(
    data: List[Dict],
    schema_metadata: Optional[List[Dict]],
) -> List[str]:
    keys = list(data[0].keys())
    metadata_time = _metadata_columns(
        schema_metadata,
        keys,
        lambda meta: meta.get("dimension_group") == "time_period",
    )
    metadata_names = {column.lower() for column in metadata_time}
    fallback_time = [
        column for column in keys
        if column.lower() not in metadata_names
        and any(keyword in column.lower() for keyword in _TEMPORAL_FALLBACK_KEYS)
    ]
    return metadata_time + fallback_time


def _numeric_columns(data: List[Dict]) -> List[str]:
    columns = list(data[0].keys())
    return [
        column for column in columns
        if any(_as_number(row.get(column)) is not None for row in data)
        and all(
            row.get(column) is None or _as_number(row.get(column)) is not None
            for row in data
        )
    ]


def _sum_measures(rows: List[Dict], measure_cols: List[str]) -> Dict[str, float]:
    return {
        column: sum(
            _as_number(row.get(column)) or 0.0
            for row in rows
        )
        for column in measure_cols
    }


def _aggregate_rows(
    data: List[Dict],
    group_cols: List[str],
    measure_cols: List[str],
) -> List[Dict]:
    groups: Dict[tuple, List[Dict]] = defaultdict(list)
    for row in data:
        groups[tuple(row.get(column) for column in group_cols)].append(row)

    result = []
    for key, rows in groups.items():
        output = dict(zip(group_cols, key))
        output.update(_sum_measures(rows, measure_cols))
        result.append(output)
    return result


def _top_n_by_temporal_grain(
    data: List[Dict],
    temporal_cols: List[str],
    category_col: Optional[str],
    measure_cols: List[str],
    max_rows: int,
) -> List[Dict]:
    """Keep each temporal grain and bucket categories independently.

    The row budget is distributed across temporal grains so a monthly result
    remains monthly. Values are ranked by absolute aggregate magnitude, which
    keeps large negative expenses visible instead of silently discarding them.
    """
    if not temporal_cols:
        return []

    time_groups: Dict[tuple, List[Dict]] = {}
    for row in data:
        time_key = tuple(row.get(column) for column in temporal_cols)
        time_groups.setdefault(time_key, []).append(row)

    # Preserve the query's order (usually ORDER BY time), while guaranteeing a
    # hard payload cap if a result contains more temporal grains than rows.
    time_items = list(time_groups.items())[:max_rows]
    if not time_items:
        return []

    base_slots, remainder = divmod(max_rows, len(time_items))
    result: List[Dict] = []
    for index, (time_key, time_rows) in enumerate(time_items):
        slots = base_slots + (1 if index < remainder else 0)
        category_groups: Dict[Any, List[Dict]] = defaultdict(list)
        if category_col:
            for row in time_rows:
                category_groups[row.get(category_col)].append(row)
        else:
            category_groups[None] = time_rows

        ranked = sorted(
            category_groups.items(),
            key=lambda item: (
                -sum(abs(value) for value in _sum_measures(item[1], measure_cols).values()),
                str(item[0]),
            ),
        )
        top_n = max(1, slots - 1) if category_col else 1
        keep = ranked[:top_n]
        remainder_rows = [row for _, rows in ranked[top_n:] for row in rows]

        for category, rows in keep:
            output = dict(zip(temporal_cols, time_key))
            if category_col:
                output[category_col] = category
            output.update(_sum_measures(rows, measure_cols))
            result.append(output)

        if category_col and remainder_rows:
            output = dict(zip(temporal_cols, time_key))
            output[category_col] = "อื่นๆ"
            output.update(_sum_measures(remainder_rows, measure_cols))
            result.append(output)

    return result[:max_rows]


def prepare_data_for_explanation(
    data: List[Dict],
    schema_metadata: Optional[List[Dict]] = None,
    max_rows: int = EXPLANATION_MAX_ROWS,
) -> List[Dict]:
    """Reduce an explanation payload without changing its analytical grain."""
    if not data:
        return data

    if len(data) <= max_rows:
        return data

    keys = list(data[0].keys())
    temporal_cols = _temporal_columns(data, schema_metadata)
    numeric_cols = _numeric_columns(data)
    metadata_measures = set(
        column.lower()
        for column in _metadata_columns(
            schema_metadata,
            keys,
            lambda meta: _truthy(meta.get("is_summable")),
        )
    )
    metadata_summability = {
        column.lower()
        for column in _metadata_columns(
            schema_metadata,
            keys,
            lambda meta: meta.get("is_summable") is not None,
        )
    }
    measure_cols = [
        column for column in numeric_cols
        if column.lower() in metadata_measures
        or (
            column.lower() not in metadata_summability
            and column not in temporal_cols
            and len({row.get(column) for row in data}) > min(20, len(data) * 0.1)
        )
    ]
    if not measure_cols:
        return data[:max_rows]

    dimension_cols = [column for column in keys if column not in measure_cols]
    category_cols = [column for column in dimension_cols if column not in temporal_cols]
    full_grouped = _aggregate_rows(data, dimension_cols, measure_cols)
    if len(full_grouped) <= max_rows:
        return full_grouped

    # Keep the first result dimension as the primary categorical dimension. It
    # follows SELECT/GROUP BY order and avoids inventing a business hierarchy.
    primary_category = category_cols[0] if category_cols else None
    reduced = _top_n_by_temporal_grain(
        data,
        temporal_cols,
        primary_category,
        measure_cols,
        max_rows,
    )
    if not reduced:
        # No temporal dimension means there is no safe grain to preserve. Keep
        # one aggregate per primary category and cap the payload deterministically.
        grouped = _aggregate_rows(
            data,
            [primary_category] if primary_category else [],
            measure_cols,
        )
        if primary_category and len(grouped) > max_rows:
            ranked = sorted(
                grouped,
                key=lambda row: (
                    -sum(abs(_as_number(row.get(column)) or 0.0) for column in measure_cols),
                    str(row.get(primary_category)),
                ),
            )
            reduced = ranked[:max(1, max_rows - 1)]
            other = {primary_category: "อื่นๆ"}
            other.update({
                column: sum(_as_number(row.get(column)) or 0.0 for row in ranked[max(1, max_rows - 1):])
                for column in measure_cols
            })
            reduced.append(other)
        else:
            reduced = grouped[:max_rows]

    logger.info(
        "explain data: %s → %s rows (temporal=%s, primary_category=%s, measures=%s)",
        len(data), len(reduced), temporal_cols, primary_category, measure_cols,
    )
    return reduced


def extract_sql(text: str) -> Optional[str]:
    sql_match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip()

    code_match = re.search(r"```\s*((?:WITH|SELECT).*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if code_match:
        return code_match.group(1).strip()

    select_match = re.search(r"((?:WITH|SELECT)\s+.*?(?:;|$))", text, re.DOTALL | re.IGNORECASE)
    if select_match:
        sql = select_match.group(1).strip()
        if "\n\n" in sql:
            sql = sql.split("\n\n")[0]
        return sql.rstrip(";") + "" if not sql.endswith(";") else sql

    return None


def extract_explanation(text: str) -> str:
    text_without_sql = re.sub(r"```sql.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)
    text_without_sql = re.sub(r"```.*?```", "", text_without_sql, flags=re.DOTALL)

    explanation_match = re.search(r"\*\*คำอธิบาย:?\*\*\s*(.*)", text_without_sql, re.DOTALL)
    if explanation_match:
        return explanation_match.group(1).strip()

    cleaned = text_without_sql.strip()
    if cleaned:
        return cleaned

    return "ดำเนินการสำเร็จ"


def parse_intent_json(text: str) -> Optional[Dict]:
    if not text:
        return None

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None
