/**
 * Centralized chart types — single source of truth.
 * Imported by: chat.ts, ChatBubble.tsx, DataChart.tsx
 */

export interface ColumnRole {
    column: string;
    role: 'category' | 'measure' | 'series' | 'secondary_measure';
    label?: string;
    display_label?: string;  // e.g., "รายได้ (ล้านบาท)" — for axis labels
    format?: 'number' | 'currency_thb' | 'percent' | 'date';
    axis?: 'left' | 'right';
}

export interface ChartConfig {
    // Original 3 fields (backward compatible)
    category_column?: string;
    measure_column?: string;
    series_column?: string;
    // Extended fields from enrich_chart_config
    suggested_type?: string;
    available_types?: string[];
    column_roles?: ColumnRole[];
    title?: string;
    sort_by?: string;
    show_data_labels?: boolean;
    warning?: string;
    is_time_axis?: boolean;
    max_series?: number;  // Wave 4 — max series/pie-slices before bucketing into "อื่นๆ"
}

/** Backend visualization strings
 * mixed_bar_line / scatter removed (Wave 2 L8) — no ChartConfig shape
 * supports either, and buildEChartsOption had no case for them, so picking
 * one silently rendered vertical_bar. */
export type BackendVisualizationType =
    | 'bar_chart' | 'horizontal_bar' | 'line_chart' | 'multi_line'
    | 'pie_chart' | 'donut_chart' | 'grouped_bar' | 'stacked_bar'
    | 'stacked_bar_100' | 'area' | 'stacked_area' | 'waterfall'
    | 'heatmap' | 'table' | 'single_value';

/** ECharts-ready chart type strings */
export type EChartsType =
    | 'vertical_bar' | 'horizontal_bar' | 'line' | 'multi_line'
    | 'pie_chart' | 'donut_chart' | 'grouped_bar' | 'stacked_bar'
    | 'stacked_bar_100' | 'area' | 'stacked_area' | 'waterfall'
    | 'heatmap';

/** Maps backend visualization → ECharts-ready type */
const VISUALIZATION_TO_ECHARTS: Record<string, string | null> = {
    bar_chart: 'vertical_bar',
    horizontal_bar: 'horizontal_bar',
    line_chart: 'line',
    multi_line: 'multi_line',
    pie_chart: 'pie_chart',
    donut_chart: 'donut_chart',
    grouped_bar: 'grouped_bar',
    stacked_bar: 'stacked_bar',
    stacked_bar_100: 'stacked_bar_100',
    area: 'area',
    stacked_area: 'stacked_area',
    waterfall: 'waterfall',
    heatmap: 'heatmap',
    table: null,
    single_value: null,
};

/**
 * Resolve the ECharts-ready type from backend visualization + chartConfig.
 * Priority: chartConfig.suggested_type > VISUALIZATION_TO_ECHARTS[visualization]
 * Always maps through VISUALIZATION_TO_ECHARTS to convert backend types to ECharts types.
 */
export function resolveChartType(
    visualization?: string,
    chartConfig?: ChartConfig,
): string | null {
    if (chartConfig?.suggested_type) {
        const st = chartConfig.suggested_type;
        // Map backend type → ECharts type if needed (e.g. 'line_chart' → 'line')
        // If already an ECharts type (not in map), return as-is
        return VISUALIZATION_TO_ECHARTS[st] !== undefined ? VISUALIZATION_TO_ECHARTS[st] : st;
    }

    // Fallback: use first available_type from chartConfig when suggested_type is null
    // This handles cases where AI sets visualization='table' but provides chart options
    if (chartConfig?.available_types?.length) {
        const first = chartConfig.available_types[0];
        const mapped = VISUALIZATION_TO_ECHARTS[first];
        if (mapped !== undefined) return mapped;  // mapped (could be null for 'table')
        return first;  // ECharts type not in map → return as-is
    }

    if (!visualization) return null;
    return VISUALIZATION_TO_ECHARTS[visualization] ?? null;
}
