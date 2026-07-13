"""Single deterministic chart decision engine."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.chart.profiler import (
    DEFAULT_MAX_SERIES,
    ChartDataProfile,
    profile_chart_data,
)


TEMPORAL_TYPES = {"line_chart", "multi_line", "area", "stacked_area"}

_MONEY_KEYS = (
    'revenue', 'income', 'expense', 'cost', 'profit', 'amount',
    'total', 'sum', 'budget', 'value', 'baht',
    'รายได้', 'ค่าใช้จ่าย', 'กำไร', 'ยอด', 'งบ', 'มูลค่า',
)
_CHART_LABELS = {
    'bar_chart': 'กราฟแท่ง',
    'horizontal_bar': 'กราฟแท่งแนวนอน',
    'line_chart': 'กราฟเส้น',
    'multi_line': 'กราฟเส้นหลายชุด',
    'grouped_bar': 'กราฟแท่งแบบกลุ่ม',
    'stacked_bar': 'กราฟแท่งสะสม',
    'heatmap': 'heatmap',
    'pie_chart': 'กราฟวงกลม',
    'donut_chart': 'กราฟโดนัท',
    'waterfall': 'กราฟน้ำตก',
}

MAX_VERTICAL_CATEGORIES = 12
MAX_AXIS_LABEL_LENGTH = 24


@dataclass(frozen=True)
class ChartDecision:
    profile: ChartDataProfile
    matrix: Optional[Dict[str, Any]]
    category_column: Optional[str]
    series_column: Optional[str]
    measure_column: Optional[str]
    visualization: str
    has_time_category: bool
    series_count: int
    has_negative: bool
    is_dense_time_series: bool
    requested_type: Optional[str] = None
    requested_type_accepted: bool = False
    requested_type_vetoed: bool = False
    requested_type_effective: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    chart_spec: Optional[Dict[str, Any]] = None
    available_types: List[str] = field(default_factory=list)

    @property
    def warning(self) -> Optional[str]:
        return self.warnings[0] if self.warnings else None

    def __getitem__(self, key: str) -> Any:
        """Keep dict-style access for callers written before ChartDecision."""
        return getattr(self, key)


def _field_kind(profile: ChartDataProfile, field: Optional[str]) -> str:
    role = profile.column_roles.get(field or '', 'nominal')
    return 'nominal' if role == 'categorical' else role


def _measure_unit(field: str) -> str:
    return 'THB' if any(key in field.lower() for key in _MONEY_KEYS) else 'number'


def _build_chart_spec(
    profile: ChartDataProfile,
    visualization: str,
    category_column: Optional[str],
    series_column: Optional[str],
    measure_column: Optional[str],
    max_series: int,
    has_negative: bool,
    title: str = '',
) -> Optional[Dict[str, Any]]:
    if not category_column or not measure_column:
        return None

    def dimension(field: str, sort: Optional[str] = None) -> Dict[str, Any]:
        result = {
            'field': field,
            'kind': _field_kind(profile, field),
        }
        if sort:
            result['sort'] = sort
        return result

    value = {
        'field': measure_column,
        'kind': 'quantitative',
        'unit': _measure_unit(measure_column),
        'scale': 'diverging_zero' if has_negative else 'auto',
    }
    if visualization == 'heatmap':
        if not series_column:
            return None
        return {
            'version': 1,
            'chart_type': visualization,
            'title': title or None,
            'x': dimension(
                series_column,
                'chronological' if _field_kind(profile, series_column) == 'temporal' else 'original',
            ),
            'y': dimension(category_column, 'value_desc'),
            'color': value,
            'missing': 'blank',
        }

    return {
        'version': 1,
        'chart_type': visualization,
        'title': title or None,
        'x': dimension(
            category_column,
            'chronological' if _field_kind(profile, category_column) == 'temporal' else 'value_desc',
        ),
        'y': value,
        'series': (
            {
                'field': series_column,
                'top_n': max(1, max_series - 1),
                'other_label': 'อื่นๆ',
            }
            if series_column else None
        ),
        'missing': 'omit',
    }


def _suggest_available_types(
    n_categories: int,
    has_series: bool,
    has_time_category: bool,
    is_matrix: bool = False,
) -> List[str]:
    if is_matrix:
        return ['heatmap', 'grouped_bar', 'stacked_bar', 'table']
    if not has_series:
        if n_categories <= 8:
            types = ['bar_chart', 'horizontal_bar', 'line_chart', 'pie_chart', 'donut_chart']
        else:
            types = ['bar_chart', 'horizontal_bar', 'line_chart']
    elif has_time_category:
        types = ['line_chart', 'multi_line', 'grouped_bar', 'stacked_bar', 'area']
    else:
        types = ['grouped_bar', 'stacked_bar', 'stacked_bar_100', 'bar_chart']
    if not has_time_category:
        types = [chart_type for chart_type in types if chart_type not in TEMPORAL_TYPES]
    return types


def resolve_max_series_warning(
    data: List[Dict],
    cat_col: Optional[str],
    ser_col: Optional[str],
    viz: str,
    max_series: int,
) -> Optional[str]:
    if viz == 'heatmap':
        return None
    if viz in ('pie_chart', 'donut_chart'):
        bucket_count = len({str(row.get(cat_col, '')) for row in data}) if cat_col and data else 0
    elif ser_col:
        bucket_count = len({str(row.get(ser_col, '')) for row in data}) if data else 0
    else:
        return None
    if bucket_count <= max_series:
        return None
    return (
        f"แสดง Top-{max_series - 1} จาก {bucket_count} กลุ่ม — "
        "กลุ่มที่เหลือรวมเป็น 'อื่นๆ' (ดูข้อมูลเต็มในตาราง)"
    )


def _matrix_request(
    requested_type: str,
    matrix: Dict[str, Any],
) -> Optional[str]:
    """Map a safe explicit request to a matrix-preserving chart family."""
    if requested_type == 'heatmap':
        return 'heatmap'
    if requested_type in {'bar_chart', 'grouped_bar'}:
        return 'grouped_bar'
    if requested_type == 'stacked_bar' and not matrix.get('has_negative'):
        return 'stacked_bar'
    if requested_type in {'line_chart', 'multi_line'} and matrix.get('dimension_count', 0) <= 5:
        return 'multi_line'
    return None


def _veto_warning(requested_type: str, matrix: Dict[str, Any], replacement: str) -> str:
    requested_label = _CHART_LABELS.get(requested_type, requested_type)
    replacement_label = _CHART_LABELS.get(replacement, replacement)
    if matrix.get('kind') != 'time_matrix':
        return (
            f"ไม่สามารถใช้{requested_label}กับข้อมูลเมทริกซ์ "
            f"{matrix.get('row_count', 0)} × {matrix.get('column_count', 0)} "
            f"เพราะอาจทำให้ความสัมพันธ์ระหว่างสองมิติอ่านผิด จึงใช้{replacement_label}แทน"
        )
    return (
        f"ไม่สามารถใช้{requested_label}กับข้อมูล "
        f"{matrix.get('dimension_count', 0)} หมวด × {matrix.get('time_count', 0)} ช่วงเวลา "
        f"เพราะจะทำให้มิติช่วงเวลาถูกรวม จึงใช้{replacement_label}แทน"
    )


def _infer_default_axes(
    profile: ChartDataProfile,
    measure_column: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Infer generic axes when a provider omitted chart column mappings."""
    dimensions = [column for column in profile.columns if column != measure_column]
    if not dimensions:
        return None, None

    temporal = [column for column in dimensions if column in profile.temporal_columns]
    month_like = [
        column for column in temporal
        if any(token in column.lower() for token in ('month', 'เดือน'))
    ]
    category = (month_like or temporal or dimensions)[0]

    series_candidates = [
        column for column in dimensions
        if column != category
        and column in profile.categorical_columns
        and 2 <= profile.cardinality.get(column, 0) <= 30
    ]
    return category, (series_candidates[0] if series_candidates else None)


def _needs_horizontal_bar(data: List[Dict], category_column: Optional[str]) -> bool:
    if not category_column or not data:
        return False
    labels = [str(row.get(category_column, '')) for row in data]
    unique_labels = set(labels)
    return (
        len(unique_labels) > MAX_VERTICAL_CATEGORIES
        or max((len(label) for label in unique_labels), default=0) > MAX_AXIS_LABEL_LENGTH
    )


def decide_chart_structure(
    data: List[Dict],
    category_column: Optional[str] = None,
    series_column: Optional[str] = None,
    measure_column: Optional[str] = None,
    visualization: Optional[str] = None,
    schema_metadata: Optional[List[Dict]] = None,
    max_series: int = DEFAULT_MAX_SERIES,
    requested_type: Optional[str] = None,
    llm_hint: Optional[str] = None,
    title: str = '',
) -> ChartDecision:
    """Apply profile > explicit request > provider hint, with safe vetoes."""
    profile = profile_chart_data(
        data,
        measure_column=measure_column,
        schema_metadata=schema_metadata,
    )
    columns = set(profile.columns)
    measure = measure_column if measure_column in columns else profile.measure_column
    inferred_category, inferred_series = _infer_default_axes(profile, measure)
    category = category_column or inferred_category
    series = series_column or inferred_series
    hint = llm_hint or visualization or 'bar_chart'
    viz = hint
    matrix = profile.matrix_shape
    warnings: List[str] = []
    requested_accepted = False
    requested_vetoed = False
    requested_effective = None

    def add_warning(message: str) -> None:
        if message and message not in warnings:
            warnings.append(message)

    if matrix:
        recommendation = matrix['recommendation']

        def apply_recommendation() -> None:
            nonlocal category, series, viz
            if matrix['kind'] == 'time_matrix':
                time_column = matrix['time_column']
                dimension_column = matrix['dimension_column']
                if recommendation == 'heatmap':
                    category, series, viz = dimension_column, time_column, 'heatmap'
                else:
                    category, series, viz = time_column, dimension_column, recommendation
            else:
                category = matrix['row_column']
                series = matrix['column_column']
                viz = 'heatmap'

        if requested_type:
            requested_effective = _matrix_request(requested_type, matrix)
            if (
                requested_effective
                and matrix['kind'] == 'matrix'
                and requested_effective != 'heatmap'
            ):
                apply_recommendation()
                requested_effective = None
                requested_vetoed = True
                add_warning(_veto_warning(requested_type, matrix, viz))
            elif requested_effective:
                requested_accepted = True
                if matrix['kind'] == 'time_matrix':
                    category = matrix['time_column']
                    series = matrix['dimension_column']
                    viz = requested_effective
                    if requested_effective == 'heatmap':
                        category, series = matrix['dimension_column'], matrix['time_column']
                else:
                    category = matrix['row_column']
                    series = matrix['column_column']
                    viz = 'heatmap'
            else:
                apply_recommendation()
                requested_vetoed = True
                add_warning(_veto_warning(requested_type, matrix, viz))
        else:
            apply_recommendation()

    has_time_category = category in profile.temporal_columns
    if not matrix and has_time_category and not series and measure:
        other_dimensions = []
        for column in profile.columns:
            if column in (category, measure) or column in profile.temporal_columns:
                continue
            values = {str(row.get(column, '')) for row in data if row.get(column) is not None}
            sample = next((row.get(column) for row in data if row.get(column) is not None), None)
            if isinstance(sample, str) and 2 <= len(values) <= 30:
                other_dimensions.append((column, len(values)))
        if len(other_dimensions) == 1:
            series, series_count = other_dimensions[0]
            viz = 'stacked_bar' if series_count > max_series else 'grouped_bar'
        elif (
            len(data) > 10
            and not visualization
            and not llm_hint
            and viz == 'bar_chart'
        ):
            viz = 'line_chart'

    if requested_type and not matrix and not requested_accepted:
        candidate = requested_type
        if candidate == 'bar_chart' and has_time_category and series:
            candidate = 'grouped_bar'
        invalid_temporal = candidate in TEMPORAL_TYPES and not has_time_category
        invalid_negative = (
            profile.negative_columns.get(measure, False)
            and candidate in {'stacked_bar', 'stacked_area', 'pie_chart', 'donut_chart'}
        )
        if invalid_temporal or invalid_negative:
            requested_vetoed = True
            if invalid_negative:
                viz = 'grouped_bar' if series else 'horizontal_bar'
                add_warning('พบค่าติดลบ จึงไม่ใช้กราฟที่สื่อสัดส่วนหรือการสะสม')
            else:
                viz = 'bar_chart'
                add_warning('ปรับชนิดกราฟเนื่องจากแกน X ไม่ใช่คาบเวลา')
        else:
            viz = candidate
            requested_accepted = True
            requested_effective = candidate

    series_count = profile.cardinality.get(series, 0) if series else 0
    has_negative = profile.negative_columns.get(measure, False) if measure else False
    if has_time_category and series_count > max_series and viz in TEMPORAL_TYPES:
        viz = 'stacked_bar'

    if has_negative and viz in {'stacked_bar', 'stacked_area'}:
        viz = 'grouped_bar' if series else 'horizontal_bar'
        add_warning('พบค่าติดลบ จึงปรับจากกราฟสะสมเป็นกราฟเปรียบเทียบ')
        if requested_type:
            requested_vetoed = True
            requested_accepted = False
    elif matrix and has_negative and viz == 'grouped_bar':
        add_warning('พบค่าติดลบ จึงเลือกกราฟเปรียบเทียบแทนกราฟสะสม')
    elif has_negative and viz in {'pie_chart', 'donut_chart'}:
        viz = 'horizontal_bar'
        add_warning('พบค่าติดลบ จึงปรับจากกราฟวงกลมเป็นกราฟแท่งแนวนอน')
        if requested_type:
            requested_vetoed = True
            requested_accepted = False

    if viz in TEMPORAL_TYPES and not has_time_category:
        viz = 'bar_chart'
        add_warning('ปรับจากกราฟเส้นเนื่องจากแกน X ไม่ใช่คาบเวลา')

    if (
        not matrix
        and category
        and not has_time_category
        and not series
        and not requested_accepted
        and viz in {'bar_chart', 'pie_chart', 'donut_chart'}
        and (
            profile.cardinality.get(category, 0) > 12
            or (
                profile.cardinality.get(category, 0) > 6
                and _needs_horizontal_bar(data, category)
            )
        )
    ):
        previous_viz = viz
        viz = 'horizontal_bar'
        add_warning(
            f"ปรับเป็นกราฟแท่งแนวนอนเนื่องจากมีหมวดหมู่จำนวนมากหรือชื่อยาว "
            f"(เกิน {MAX_VERTICAL_CATEGORIES} หมวด หรือยาวกว่า {MAX_AXIS_LABEL_LENGTH} ตัวอักษร)"
        )
        if requested_type == previous_viz:
            requested_accepted = False
            requested_vetoed = True
            requested_effective = None

    is_dense = has_time_category and series_count > max_series
    n_categories = profile.cardinality.get(category, 1) if category else 1
    is_matrix = matrix is not None
    available_types = (
        ['stacked_bar', 'grouped_bar']
        if is_dense and viz != 'heatmap'
        else _suggest_available_types(
            n_categories,
            bool(series),
            has_time_category,
            is_matrix=is_matrix,
        )
    )
    if has_negative:
        available_types = [
            chart_type for chart_type in available_types
            if chart_type not in {
                'stacked_bar', 'stacked_area', 'stacked_bar_100',
                'pie_chart', 'donut_chart',
            }
        ]
    if viz in ('pie_chart', 'donut_chart') and series:
        add_warning('Pie/Donut chart ไม่รองรับ series column — พิจารณาใช้ bar_chart แทน')
    max_warning = resolve_max_series_warning(data, category, series, viz, max_series)
    if max_warning:
        add_warning(max_warning)

    return ChartDecision(
        profile=profile,
        matrix=matrix,
        category_column=category,
        series_column=series,
        measure_column=measure,
        visualization=viz,
        has_time_category=has_time_category,
        series_count=series_count,
        has_negative=has_negative,
        is_dense_time_series=is_dense,
        requested_type=requested_type,
        requested_type_accepted=requested_accepted,
        requested_type_vetoed=requested_vetoed,
        requested_type_effective=requested_effective,
        warnings=warnings,
        chart_spec=_build_chart_spec(
            profile, viz, category, series, measure,
            max_series, has_negative, title,
        ),
        available_types=available_types,
    )
