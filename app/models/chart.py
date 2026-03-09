"""
Extended chart config models.

ChartConfigV2 extends the existing ChartConfig in schemas/chat.py
by adding available_types, column_roles, title, sort_by, warning.
"""
from typing import Literal, Optional, List
from pydantic import BaseModel


# Visualization types — superset of backend prompt values
# Backend prompt: bar_chart, horizontal_bar, line_chart, pie_chart,
#                 donut_chart, table, single_value, grouped_bar, stacked_bar
# Extended:       multi_line, area, stacked_area, stacked_bar_100,
#                 waterfall, mixed_bar_line, scatter
VisualizationType = Literal[
    'bar_chart',
    'horizontal_bar',
    'line_chart',
    'multi_line',
    'pie_chart',
    'donut_chart',
    'grouped_bar',
    'stacked_bar',
    'stacked_bar_100',
    'area',
    'stacked_area',
    'waterfall',
    'mixed_bar_line',
    'scatter',
    'heatmap',
]

# Map backend visualization string → ECharts-ready type
VISUALIZATION_TO_ECHARTS: dict[str, Optional[str]] = {
    'bar_chart':        'vertical_bar',
    'horizontal_bar':   'horizontal_bar',
    'line_chart':       'line',
    'multi_line':       'multi_line',
    'pie_chart':        'pie_chart',
    'donut_chart':      'donut_chart',
    'grouped_bar':      'grouped_bar',
    'stacked_bar':      'stacked_bar',
    'stacked_bar_100':  'stacked_bar_100',
    'area':             'area',
    'stacked_area':     'stacked_area',
    'waterfall':        'waterfall',
    'mixed_bar_line':   'mixed_bar_line',
    'scatter':          'scatter',
    'heatmap':          'heatmap',
    # Non-chart types
    'table':            None,
    'single_value':     None,
}


class ColumnRole(BaseModel):
    column: str
    role: Literal['category', 'measure', 'series', 'secondary_measure']
    label: Optional[str] = None
    format: Optional[Literal['number', 'currency_thb', 'percent', 'date']] = None
    axis: Optional[Literal['left', 'right']] = None


class ChartConfigV2(BaseModel):
    """
    Extended chart config — backward compatible with ChartConfig.
    All original fields are kept. New fields are additive.
    """
    # Original fields (MUST keep for backward compat)
    category_column: Optional[str] = None
    measure_column: Optional[str] = None
    series_column: Optional[str] = None

    # New fields
    suggested_type: Optional[str] = None
    available_types: List[str] = []
    column_roles: List[ColumnRole] = []
    title: Optional[str] = None
    sort_by: Optional[str] = 'original'
    show_data_labels: bool = False
    color_palette: Optional[List[str]] = None
    warning: Optional[str] = None
