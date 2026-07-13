"""Data-only chart profiling shared by every chart decision path."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


TIME_KEYS = [
    'month', 'year', 'date', 'day', 'time', 'quarter', 'week',
    'hour', 'minute', 'second',
    'เดือน', 'ปี', 'วันที่', 'ไตรมาส', 'งวด', 'เวลา',
]

DEFAULT_MAX_SERIES = 5

_MEASURE_COLUMN_KEYS = (
    'revenue', 'value', 'amount', 'total', 'sum', 'count', 'baht',
    'รายได้', 'จำนวน', 'ยอด',
)
_DIMENSION_COLUMN_KEYS = (
    'year', 'month', 'date', 'day', 'week', 'quarter', 'id',
    'ปี', 'เดือน', 'วันที่', 'ไตรมาส',
)


def _is_time_column(col: str, time_columns: Optional[List[str]] = None) -> bool:
    col_lower = str(col).lower()
    if time_columns and col_lower in [str(c).lower() for c in time_columns]:
        return True
    return any(token in col_lower for token in TIME_KEYS)


def _non_null_values(data: List[Dict], column: str) -> List[str]:
    return [str(row.get(column)) for row in data if row.get(column) is not None]


def _has_negative_measure(data: List[Dict], measure_col: str) -> bool:
    for row in data:
        value = row.get(measure_col)
        try:
            if float(str(value).replace(',', '')) < 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _is_numeric_value(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        float(str(value).replace(',', ''))
        return True
    except (TypeError, ValueError):
        return False


def _numeric_columns(data: List[Dict]) -> List[str]:
    if not data:
        return []
    return [
        column for column in data[0]
        if (values := [row.get(column) for row in data if row.get(column) is not None])
        and all(_is_numeric_value(value) for value in values)
    ]


def _select_measure_column(
    numeric_columns: List[str],
    schema_metadata: Optional[List[Dict]] = None,
) -> Optional[str]:
    """Select a measure using metadata first, then generic structural hints."""
    metadata_measures = {
        str(meta.get('column_name', '')).lower()
        for meta in schema_metadata or []
        if meta.get('is_summable') and meta.get('column_name')
    }
    for column in numeric_columns:
        if column.lower() in metadata_measures:
            return column
    for column in numeric_columns:
        if any(keyword in column.lower() for keyword in _MEASURE_COLUMN_KEYS):
            return column
    for column in reversed(numeric_columns):
        if not any(keyword in column.lower() for keyword in _DIMENSION_COLUMN_KEYS):
            return column
    return numeric_columns[-1] if numeric_columns else None


def _infer_matrix_shape(
    data: List[Dict],
    measure_col: Optional[str],
    time_columns: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Infer a dense two-dimensional result and its safe chart family."""
    if not data or not measure_col:
        return None

    keys = list(data[0].keys())
    time_candidates = [
        key for key in keys
        if key != measure_col and _is_time_column(key, time_columns)
    ]
    dimension_candidates = [
        key for key in keys
        if key != measure_col and key not in time_candidates
    ]

    def column_shape(column: str) -> tuple[int, bool]:
        values = _non_null_values(data, column)
        numeric = sum(1 for value in values if _is_numeric_value(value))
        return len(set(values)), bool(values) and numeric / len(values) < 0.8

    def pair_coverage(left: str, right: str) -> tuple[int, int, float]:
        left_values = set(_non_null_values(data, left))
        right_values = set(_non_null_values(data, right))
        pairs = {
            (str(row.get(left)), str(row.get(right)))
            for row in data
            if row.get(left) is not None and row.get(right) is not None
        }
        expected = len(left_values) * len(right_values)
        return len(left_values), len(right_values), len(pairs) / expected if expected else 0.0

    has_negative = _has_negative_measure(data, measure_col)
    for time_col in time_candidates:
        time_count, _ = column_shape(time_col)
        if time_count < 4:
            continue
        for dimension_col in dimension_candidates:
            dimension_count, is_categorical = column_shape(dimension_col)
            if not is_categorical or dimension_count < 3:
                continue
            _, _, coverage = pair_coverage(time_col, dimension_col)
            if len(data) < 12 or coverage < 0.5:
                continue
            if time_count >= 6 and dimension_count >= 8:
                recommendation = (
                    'heatmap'
                    if time_count <= 24 and dimension_count <= 40
                    else ('grouped_bar' if has_negative else 'stacked_bar')
                )
            elif time_count >= 6 and dimension_count <= 5:
                recommendation = 'multi_line'
            else:
                recommendation = (
                    'stacked_bar'
                    if dimension_count > DEFAULT_MAX_SERIES and not has_negative
                    else 'grouped_bar'
                )
            return {
                'kind': 'time_matrix',
                'time_column': time_col,
                'dimension_column': dimension_col,
                'time_count': time_count,
                'dimension_count': dimension_count,
                'coverage': coverage,
                'has_negative': has_negative,
                'recommendation': recommendation,
            }

    categorical = [
        (column, column_shape(column)[0])
        for column in dimension_candidates
        if column_shape(column)[1] and column_shape(column)[0] >= 3
    ]
    for index, (row_col, row_count) in enumerate(categorical):
        for col_col, col_count in categorical[index + 1:]:
            _, _, coverage = pair_coverage(row_col, col_col)
            if (
                row_count >= 3 and col_count >= 3
                and row_count <= 40 and col_count <= 40
                and len(data) >= 12 and coverage >= 0.4
            ):
                return {
                    'kind': 'matrix',
                    'row_column': row_col,
                    'column_column': col_col,
                    'row_count': row_count,
                    'column_count': col_count,
                    'coverage': coverage,
                    'recommendation': 'heatmap',
                }
    return None


@dataclass(frozen=True)
class ChartDataProfile:
    """Shared, renderer-neutral facts about a query result."""

    columns: List[str]
    column_roles: Dict[str, str]
    cardinality: Dict[str, int]
    temporal_columns: List[str]
    categorical_columns: List[str]
    quantitative_columns: List[str]
    negative_columns: Dict[str, bool]
    measure_column: Optional[str]
    matrix_shape: Optional[Dict[str, Any]]


def profile_chart_data(
    data: List[Dict],
    measure_column: Optional[str] = None,
    schema_metadata: Optional[List[Dict]] = None,
) -> ChartDataProfile:
    """Profile result shape once so every chart decision uses the same facts."""
    if not data:
        return ChartDataProfile([], {}, {}, [], [], [], {}, None, None)

    columns = list(data[0].keys())
    numeric_columns = _numeric_columns(data)
    metadata_time_columns = [
        meta['column_name'] for meta in schema_metadata or []
        if meta.get('dimension_group') == 'time_period' and meta.get('column_name')
    ]
    temporal_columns = [
        column for column in columns
        if _is_time_column(column, metadata_time_columns)
    ]
    selected_measure = (
        measure_column
        if measure_column in numeric_columns
        else _select_measure_column(numeric_columns, schema_metadata)
    )
    cardinality = {
        column: len({str(row.get(column)) for row in data})
        for column in columns
    }
    column_roles = {
        column: (
            'temporal' if column in temporal_columns
            else 'quantitative' if column in numeric_columns
            else 'categorical'
        )
        for column in columns
    }
    negative_columns = {
        column: _has_negative_measure(data, column)
        for column in numeric_columns
    }
    matrix_shape = _infer_matrix_shape(
        data,
        selected_measure,
        time_columns=temporal_columns,
    ) if selected_measure else None

    return ChartDataProfile(
        columns=columns,
        column_roles=column_roles,
        cardinality=cardinality,
        temporal_columns=temporal_columns,
        categorical_columns=[
            column for column in columns if column_roles[column] == 'categorical'
        ],
        quantitative_columns=numeric_columns,
        negative_columns=negative_columns,
        measure_column=selected_measure,
        matrix_shape=matrix_shape,
    )
