/**
 * ECharts option builders — transforms backend data into ECharts option objects.
 */
import { resolveChartType, type ChartConfig } from '../types/chart';
import { NT_CHART_PALETTE, FINANCIAL_COLORS, CHART_THEME, HEATMAP_COLORS } from '../constants/chartColors';
import { safelyParseNumber, formatNumberWithUnit, truncateLabel } from './chartUtils';

/** Thai tooltip number formatter */
const formatTooltipValue = (value: number, columnName?: string): string => {
    const result = formatNumberWithUnit(value, value, columnName);
    return `${result.text} ${result.unit}`;
};

/** Format number with commas and max 2 decimals */
function fmtNum(value: number, decimals: number = 2): string {
    // Use toFixed then add comma separators
    const parts = value.toFixed(decimals).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return parts.join('.');
}

/** Smart Y-axis formatter — abbreviates large numbers (max 2 decimals) */
function yAxisFormatter(value: number): string {
    const abs = Math.abs(value);
    if (abs >= 1_000_000_000) return `${fmtNum(value / 1_000_000_000)} พลบ.`;
    if (abs >= 1_000_000) return `${fmtNum(value / 1_000_000)} ลบ.`;
    if (abs >= 1_000) return `${fmtNum(value / 1_000, 0)}k`;
    return fmtNum(value, 0);
}

/** Smart label formatter for bar/line data labels (max 2 decimals) */
function dataLabelFormatter(params: any): string {
    const v = typeof params === 'object' ? params.value : params;
    if (v == null) return '';
    const abs = Math.abs(v);
    if (abs >= 1_000_000_000) return `${fmtNum(v / 1_000_000_000)} พลบ.`;
    if (abs >= 1_000_000) return `${fmtNum(v / 1_000_000)} ลบ.`;
    if (abs >= 1_000) return `${fmtNum(v / 1_000, 0)}k`;
    return fmtNum(v);
}

/** Tooltip formatter with Thai number formatting (max 2 decimals) */
function tooltipFormatter(params: any): string {
    if (!params) return '';
    const items = Array.isArray(params) ? params : [params];
    const lines = items.map((item: any) => {
        const marker = item.marker || '';
        const name = item.seriesName || item.name || '';
        const val = item.value ?? 0;
        const abs = Math.abs(val);
        let text: string;
        let unit: string;
        if (abs >= 1_000_000_000) { text = fmtNum(val / 1_000_000_000); unit = 'พันล้านบาท'; }
        else if (abs >= 1_000_000) { text = fmtNum(val / 1_000_000); unit = 'ล้านบาท'; }
        else if (abs >= 1_000) { text = fmtNum(val / 1_000); unit = 'พันบาท'; }
        else { text = fmtNum(val); unit = 'บาท'; }
        return `${marker} ${name}: <b>${text} ${unit}</b>`;
    });
    const header = items[0]?.axisValueLabel || items[0]?.name || '';
    return `<b>${header}</b><br/>` + lines.join('<br/>');
}

/** Apply dark/light mode text & line colors to any ECharts option */
function applyThemeColors(option: any, isDark: boolean): any {
    const t = isDark ? CHART_THEME.dark : CHART_THEME.light;

    // Global default text color
    option.textStyle = { ...(option.textStyle || {}), color: t.text };

    // Background transparent — container handles bg color
    option.backgroundColor = 'transparent';

    // Title
    if (option.title) {
        option.title.textStyle = { ...(option.title.textStyle || {}), color: t.text };
    }

    // Axes (handles single axis or array of axes)
    const patchAxis = (axis: any) => {
        if (!axis) return;
        const axes = Array.isArray(axis) ? axis : [axis];
        for (const a of axes) {
            a.axisLabel = { ...(a.axisLabel || {}), color: t.subText };
            a.axisLine = {
                ...(a.axisLine || {}),
                lineStyle: { ...(a.axisLine?.lineStyle || {}), color: t.axisLine },
            };
            a.splitLine = {
                ...(a.splitLine || {}),
                lineStyle: { ...(a.splitLine?.lineStyle || {}), color: t.splitLine },
            };
        }
    };
    patchAxis(option.xAxis);
    patchAxis(option.yAxis);

    // Legend
    if (option.legend) {
        option.legend.textStyle = { ...(option.legend.textStyle || {}), color: t.subText };
    }

    // Series labels (data labels on bars/lines/pie)
    if (option.series) {
        for (const s of option.series) {
            if (s.label?.show) {
                s.label = { ...s.label, color: t.text };
            }
        }
    }

    return option;
}

/**
 * Main dispatcher — builds ECharts option from data + visualization + chartConfig.
 */
export function buildEChartsOption(
    data: Record<string, any>[],
    visualization?: string,
    chartConfig?: ChartConfig,
    isDark: boolean = false,
): object | null {
    if (!data || data.length === 0) return null;

    // Default to vertical_bar when no chart type resolved (prevents fallback to gifted-charts)
    const chartType = resolveChartType(visualization, chartConfig) || 'vertical_bar';

    const dataKeys = Object.keys(data[0]);
    // Validate chartConfig columns against actual data keys (handles aliased SQL columns)
    const catCol = resolveColumn(chartConfig?.category_column, dataKeys) || dataKeys[0];
    const measureCol = resolveColumn(chartConfig?.measure_column, dataKeys) || findMeasureColumn(data[0], catCol);
    // Auto-detect series column when chart type is multi-series but series_column is missing/invalid
    const seriesCol = resolveColumn(chartConfig?.series_column, dataKeys)
        || (['grouped_bar', 'stacked_bar', 'stacked_bar_100', 'multi_line', 'stacked_area', 'heatmap'].includes(chartType)
            ? autoDetectSeriesColumn(data, catCol, measureCol || '')
            : undefined);



    if (!catCol || !measureCol) return null;

    let result: object | null;
    switch (chartType) {
        case 'vertical_bar':
            result = buildVerticalBar(data, catCol, measureCol, chartConfig);
            break;
        case 'horizontal_bar':
            result = buildHorizontalBar(data, catCol, measureCol, chartConfig);
            break;
        case 'line':
            result = buildLine(data, catCol, measureCol, chartConfig);
            break;
        case 'multi_line':
        case 'grouped_bar':
        case 'stacked_bar':
        case 'stacked_bar_100':
            result = buildMultiSeries(data, catCol, measureCol, seriesCol, chartType, chartConfig);
            break;
        case 'pie_chart':
            result = buildPie(data, catCol, measureCol, chartConfig, false);
            break;
        case 'donut_chart':
            result = buildPie(data, catCol, measureCol, chartConfig, true);
            break;
        case 'area':
        case 'stacked_area':
            result = buildArea(data, catCol, measureCol, seriesCol, chartType, chartConfig);
            break;
        case 'waterfall':
            result = buildWaterfall(data, catCol, measureCol, chartConfig);
            break;
        case 'heatmap':
            result = buildHeatmap(data, catCol, measureCol, seriesCol, chartConfig);
            break;
        default:
            result = buildVerticalBar(data, catCol, measureCol, chartConfig);
    }

    // Apply dark/light mode theme colors as final step
    if (result) {
        result = applyThemeColors(result, isDark);
    }
    return result;
}

/** Find the first numeric column that isn't the category */
function findMeasureColumn(row: Record<string, any>, catCol: string): string | undefined {
    for (const [key, val] of Object.entries(row)) {
        if (key !== catCol && typeof val === 'number') return key;
    }
    // Check string values that look numeric
    for (const [key, val] of Object.entries(row)) {
        if (key !== catCol && !isNaN(safelyParseNumber(val)) && val !== '' && val !== null) return key;
    }
    return undefined;
}

/**
 * Auto-detect a series column from data when chart type is multi-series
 * but no series_column was provided.
 * Heuristic: find a non-numeric column (other than catCol/measureCol)
 * with few unique values (2-20) — likely a grouping dimension.
 */
function autoDetectSeriesColumn(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
): string | undefined {
    const keys = Object.keys(data[0] || {});
    let bestCol: string | undefined;
    let bestCount = Infinity;

    for (const key of keys) {
        if (key === catCol || key === measureCol) continue;

        // Check if column is non-numeric (text-based series)
        const firstVal = data[0][key];
        if (typeof firstVal === 'number') continue;

        const unique = new Set(data.map(d => String(d[key] ?? '')));
        const count = unique.size;
        // Good series column: 2-20 unique values, fewer is better
        if (count >= 2 && count <= 20 && count < bestCount) {
            bestCol = key;
            bestCount = count;
        }
    }
    return bestCol;
}

/**
 * Validate that chartConfig column names exist in the actual data keys.
 * If a column doesn't match, return undefined so auto-detection kicks in.
 */
function resolveColumn(
    configCol: string | undefined,
    dataKeys: string[],
): string | undefined {
    if (!configCol) return undefined;
    if (dataKeys.includes(configCol)) return configCol;
    // Column name from chartConfig doesn't match data — ignore it
    return undefined;
}

/** Common tooltip config */
function baseTooltip(): object {
    return {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        confine: true,
    };
}

// ============================================================
// Y-axis label builder — detect metric name from column name
// ============================================================

/** Keywords that indicate financial/monetary columns */
const _MONEY_KEYWORDS = [
    'revenue', 'income', 'expense', 'cost', 'profit', 'amount', 'total', 'sum',
    'budget', 'value', 'baht', 'รายได้', 'ค่าใช้จ่าย', 'กำไร', 'ยอด', 'งบ', 'มูลค่า',
    'ต้นทุน', 'ขาดทุน', 'ebt',
];

/** Build a descriptive Y-axis label from column name and config */
function buildYAxisLabel(measureCol: string, config?: ChartConfig): string {
    if (!measureCol) return '';

    // Check column_roles from backend for display_label
    if (config?.column_roles) {
        const role = config.column_roles.find(
            (r: any) => r.role === 'measure' && r.column === measureCol
        );
        if (role?.display_label) return role.display_label;
    }

    // If column name already has Thai unit suffix, return as-is
    if (measureCol.includes('ล้านบาท') || measureCol.includes('พันบาท')) return measureCol;

    // Detect unit from column name
    const lower = measureCol.toLowerCase();
    const isMoney = _MONEY_KEYWORDS.some(k => lower.includes(k));

    // Check for unit hints in column name
    if (lower.includes('million') || lower.includes('_mb') || lower.endsWith('_m')) {
        return `${measureCol} (ล้านบาท)`;
    }
    if (lower.includes('_billion') || lower.includes('_b')) {
        return `${measureCol} (พันล้านบาท)`;
    }
    if (lower.includes('percent') || lower.includes('pct') || lower.includes('%') || lower.includes('อัตรา')) {
        return `${measureCol} (%)`;
    }

    // Generic money column — just show column name (unit shown in tooltip)
    if (isMoney) return measureCol;

    return measureCol;
}

// ============================================================
// Individual chart builders
// ============================================================

function buildVerticalBar(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    config?: ChartConfig,
): object {
    const categories = data.map(d => truncateLabel(String(d[catCol] ?? ''), 15));
    const values = data.map(d => safelyParseNumber(d[measureCol]));

    return {
        title: config?.title ? { text: config.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
        tooltip: { ...baseTooltip(), trigger: 'axis', formatter: tooltipFormatter },
        grid: { left: '3%', right: '5%', bottom: '15%', top: config?.title ? '15%' : '10%', containLabel: true },
        xAxis: {
            type: 'category',
            data: categories,
            axisLabel: { rotate: categories.length > 6 ? 30 : 0, fontSize: 11 },
        },
        yAxis: { type: 'value', name: buildYAxisLabel(measureCol, config), nameLocation: 'middle', nameGap: 50, nameTextStyle: { fontSize: 12 }, axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
        series: [{
            type: 'bar',
            data: values.map((v, i) => ({
                value: v,
                itemStyle: { color: NT_CHART_PALETTE[i % NT_CHART_PALETTE.length] },
            })),
            barMaxWidth: 50,
            label: config?.show_data_labels ? { show: true, position: 'top', fontSize: 10, formatter: dataLabelFormatter } : undefined,
        }],
    };
}

function buildHorizontalBar(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    config?: ChartConfig,
): object {
    const categories = data.map(d => truncateLabel(String(d[catCol] ?? ''), 20));
    const values = data.map(d => safelyParseNumber(d[measureCol]));

    return {
        title: config?.title ? { text: config.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
        tooltip: { ...baseTooltip(), trigger: 'axis', formatter: tooltipFormatter },
        grid: { left: '25%', right: '5%', bottom: '10%', top: config?.title ? '15%' : '10%', containLabel: false },
        xAxis: { type: 'value', name: buildYAxisLabel(measureCol, config), nameLocation: 'middle', nameGap: 30, nameTextStyle: { fontSize: 12 }, axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
        yAxis: {
            type: 'category',
            data: categories,
            axisLabel: { fontSize: 11 },
            inverse: true,
        },
        series: [{
            type: 'bar',
            data: values.map((v, i) => ({
                value: v,
                itemStyle: { color: NT_CHART_PALETTE[i % NT_CHART_PALETTE.length] },
            })),
            barMaxWidth: 30,
            label: config?.show_data_labels ? { show: true, position: 'right', fontSize: 10, formatter: dataLabelFormatter } : undefined,
        }],
    };
}

function buildLine(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    config?: ChartConfig,
): object {
    const categories = data.map(d => truncateLabel(String(d[catCol] ?? ''), 15));
    const values = data.map(d => safelyParseNumber(d[measureCol]));

    return {
        title: config?.title ? { text: config.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
        tooltip: { ...baseTooltip(), trigger: 'axis', formatter: tooltipFormatter },
        grid: { left: '3%', right: '5%', bottom: '15%', top: config?.title ? '15%' : '10%', containLabel: true },
        xAxis: {
            type: 'category',
            data: categories,
            boundaryGap: false,
            axisLabel: { rotate: categories.length > 6 ? 30 : 0, fontSize: 11 },
        },
        yAxis: { type: 'value', name: buildYAxisLabel(measureCol, config), nameLocation: 'middle', nameGap: 50, nameTextStyle: { fontSize: 12 }, axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
        series: [{
            type: 'line',
            data: values,
            smooth: true,
            itemStyle: { color: NT_CHART_PALETTE[0] },
            areaStyle: undefined,
            label: config?.show_data_labels ? { show: true, position: 'top', fontSize: 10, formatter: dataLabelFormatter } : undefined,
        }],
    };
}

function buildMultiSeries(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    seriesCol: string | undefined,
    chartType: string,
    config?: ChartConfig,
): object {
    if (!seriesCol) {
        // Fallback to single series
        if (chartType === 'multi_line') return buildLine(data, catCol, measureCol, config);
        return buildVerticalBar(data, catCol, measureCol, config);
    }

    // Group data by series
    const seriesNames = [...new Set(data.map(d => String(d[seriesCol] ?? '')))];
    const categories = [...new Set(data.map(d => String(d[catCol] ?? '')))];

    const seriesData = seriesNames.map((name, idx) => {
        const seriesValues = categories.map(cat => {
            const row = data.find(d => String(d[catCol]) === cat && String(d[seriesCol]) === name);
            return row ? safelyParseNumber(row[measureCol]) : 0;
        });

        const isLine = chartType === 'multi_line';
        const isStacked = chartType === 'stacked_bar' || chartType === 'stacked_bar_100' || chartType === 'stacked_area';

        return {
            name,
            type: isLine ? 'line' : 'bar',
            data: seriesValues,
            stack: isStacked ? 'total' : undefined,
            smooth: isLine,
            itemStyle: { color: NT_CHART_PALETTE[idx % NT_CHART_PALETTE.length] },
            label: config?.show_data_labels ? { show: true, position: isStacked ? 'inside' : 'top', fontSize: 9, formatter: dataLabelFormatter } : undefined,
        };
    });

    return {
        title: config?.title ? { text: config.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
        tooltip: { ...baseTooltip(), trigger: 'axis', formatter: tooltipFormatter },
        legend: { data: seriesNames, bottom: 0, type: 'scroll', textStyle: { fontSize: 10 } },
        grid: { left: '3%', right: '5%', bottom: '20%', top: config?.title ? '15%' : '10%', containLabel: true },
        xAxis: {
            type: 'category',
            data: categories.map(c => truncateLabel(c, 12)),
            axisLabel: { rotate: categories.length > 6 ? 30 : 0, fontSize: 11 },
        },
        yAxis: { type: 'value', name: buildYAxisLabel(measureCol, config), nameLocation: 'middle', nameGap: 50, nameTextStyle: { fontSize: 12 }, axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
        series: seriesData,
    };
}

function buildPie(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    config?: ChartConfig,
    isDonut: boolean = false,
): object {
    const pieData = data.map((d, i) => ({
        name: truncateLabel(String(d[catCol] ?? ''), 20),
        value: safelyParseNumber(d[measureCol]),
        itemStyle: { color: NT_CHART_PALETTE[i % NT_CHART_PALETTE.length] },
    }));

    return {
        title: config?.title ? { text: config.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
        tooltip: {
            trigger: 'item',
            confine: true,
            formatter: (params: any) => {
                const val = params.value ?? 0;
                const abs = Math.abs(val);
                let text: string, unit: string;
                if (abs >= 1_000_000_000) { text = fmtNum(val / 1_000_000_000); unit = 'พันล้านบาท'; }
                else if (abs >= 1_000_000) { text = fmtNum(val / 1_000_000); unit = 'ล้านบาท'; }
                else if (abs >= 1_000) { text = fmtNum(val / 1_000); unit = 'พันบาท'; }
                else { text = fmtNum(val); unit = 'บาท'; }
                return `${params.marker} ${params.name}: <b>${text} ${unit}</b> (${params.percent}%)`;
            },
        },
        legend: { bottom: 0, type: 'scroll', textStyle: { fontSize: 10 } },
        series: [{
            type: 'pie',
            radius: isDonut ? ['40%', '70%'] : '70%',
            center: ['50%', '45%'],
            data: pieData,
            label: {
                show: true,
                fontSize: 10,
                formatter: '{b}: {d}%',
            },
            emphasis: {
                itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' },
            },
        }],
    };
}

function buildArea(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    seriesCol: string | undefined,
    chartType: string,
    config?: ChartConfig,
): object {
    // Reuse multi-series builder but add areaStyle
    const base = seriesCol
        ? buildMultiSeries(data, catCol, measureCol, seriesCol, chartType === 'stacked_area' ? 'stacked_bar' : 'multi_line', config) as any
        : buildLine(data, catCol, measureCol, config) as any;

    if (base?.series) {
        for (const s of base.series) {
            s.type = 'line';
            s.areaStyle = { opacity: 0.3 };
            s.smooth = true;
            if (chartType === 'stacked_area') s.stack = 'total';
        }
    }
    return base;
}

function buildWaterfall(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    config?: ChartConfig,
): object {
    const categories = data.map(d => truncateLabel(String(d[catCol] ?? ''), 15));
    const values = data.map(d => safelyParseNumber(d[measureCol]));

    // Calculate running total for waterfall
    let runningTotal = 0;
    const baseValues: number[] = [];
    const increaseValues: (number | '-')[] = [];
    const decreaseValues: (number | '-')[] = [];

    values.forEach(v => {
        if (v >= 0) {
            baseValues.push(runningTotal);
            increaseValues.push(v);
            decreaseValues.push('-');
        } else {
            baseValues.push(runningTotal + v);
            increaseValues.push('-');
            decreaseValues.push(-v);
        }
        runningTotal += v;
    });

    return {
        title: config?.title ? { text: config.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
        tooltip: { ...baseTooltip(), trigger: 'axis', formatter: tooltipFormatter },
        grid: { left: '3%', right: '5%', bottom: '15%', top: config?.title ? '15%' : '10%', containLabel: true },
        xAxis: {
            type: 'category',
            data: categories,
            axisLabel: { rotate: categories.length > 6 ? 30 : 0, fontSize: 11 },
        },
        yAxis: { type: 'value', name: buildYAxisLabel(measureCol, config), nameLocation: 'middle', nameGap: 50, nameTextStyle: { fontSize: 12 }, axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
        series: [
            {
                name: 'Base',
                type: 'bar',
                stack: 'waterfall',
                itemStyle: { color: 'transparent' },
                data: baseValues,
            },
            {
                name: 'Increase',
                type: 'bar',
                stack: 'waterfall',
                itemStyle: { color: FINANCIAL_COLORS.positive },
                data: increaseValues,
                label: config?.show_data_labels ? { show: true, position: 'top', fontSize: 10 } : undefined,
            },
            {
                name: 'Decrease',
                type: 'bar',
                stack: 'waterfall',
                itemStyle: { color: FINANCIAL_COLORS.negative },
                data: decreaseValues,
                label: config?.show_data_labels ? { show: true, position: 'bottom', fontSize: 10 } : undefined,
            },
        ],
    };
}

function buildHeatmap(
    data: Record<string, any>[],
    catCol: string,
    measureCol: string,
    seriesCol: string | undefined,
    config?: ChartConfig,
): object {
    // catCol = row dimension (Y-axis), seriesCol = column dimension (X-axis)
    const colDim = seriesCol || catCol;
    const rowDim = seriesCol ? catCol : (Object.keys(data[0] || {}).find(k => k !== catCol && k !== measureCol) || catCol);

    // Unique labels for each axis
    const xLabels = [...new Set(data.map(d => String(d[colDim] ?? '')))];
    const yLabels = [...new Set(data.map(d => String(d[rowDim] ?? '')))];

    // Build [xIndex, yIndex, value] tuples
    const heatmapData: [number, number, number][] = [];
    let minVal = Infinity;
    let maxVal = -Infinity;

    for (const row of data) {
        const xVal = String(row[colDim] ?? '');
        const yVal = String(row[rowDim] ?? '');
        const val = safelyParseNumber(row[measureCol]);

        const xi = xLabels.indexOf(xVal);
        const yi = yLabels.indexOf(yVal);
        if (xi >= 0 && yi >= 0) {
            heatmapData.push([xi, yi, val]);
            if (val < minVal) minVal = val;
            if (val > maxVal) maxVal = val;
        }
    }

    // Handle edge case
    if (minVal === Infinity) { minVal = 0; maxVal = 1; }

    return {
        title: config?.title ? { text: config.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
        tooltip: {
            position: 'top',
            confine: true,
            formatter: (params: any) => {
                const xi = params.value[0];
                const yi = params.value[1];
                const val = params.value[2];
                const xName = xLabels[xi] || '';
                const yName = yLabels[yi] || '';
                const abs = Math.abs(val);
                let text: string, unit: string;
                if (abs >= 1_000_000_000) { text = fmtNum(val / 1_000_000_000); unit = 'พลบ.'; }
                else if (abs >= 1_000_000) { text = fmtNum(val / 1_000_000); unit = 'ลบ.'; }
                else if (abs >= 1_000) { text = fmtNum(val / 1_000, 0); unit = 'k'; }
                else { text = fmtNum(val); unit = ''; }
                return `${yName} → ${xName}<br/><b>${text} ${unit}</b>`;
            },
        },
        grid: {
            left: '25%',
            right: '10%',
            bottom: '20%',
            top: config?.title ? '15%' : '10%',
            containLabel: false,
        },
        xAxis: {
            type: 'category',
            data: xLabels.map(l => truncateLabel(l, 10)),
            splitArea: { show: true },
            axisLabel: { rotate: xLabels.length > 6 ? 45 : 0, fontSize: 10 },
            position: 'bottom',
        },
        yAxis: {
            type: 'category',
            data: yLabels.map(l => truncateLabel(l, 15)),
            splitArea: { show: true },
            axisLabel: { fontSize: 10 },
        },
        visualMap: {
            min: minVal,
            max: maxVal,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: 0,
            inRange: {
                color: [HEATMAP_COLORS.min, HEATMAP_COLORS.mid, HEATMAP_COLORS.max],
            },
            textStyle: { fontSize: 10 },
            formatter: (value: number) => {
                const abs = Math.abs(value);
                if (abs >= 1_000_000) return `${fmtNum(value / 1_000_000)} ลบ.`;
                if (abs >= 1_000) return `${fmtNum(value / 1_000, 0)}k`;
                return fmtNum(value, 0);
            },
        },
        series: [{
            type: 'heatmap',
            data: heatmapData,
            label: {
                show: heatmapData.length <= 100,
                fontSize: 9,
                formatter: (params: any) => {
                    const val = params.value[2];
                    const abs = Math.abs(val);
                    if (abs >= 1_000_000) return `${fmtNum(val / 1_000_000)}`;
                    if (abs >= 1_000) return `${fmtNum(val / 1_000, 0)}k`;
                    return fmtNum(val, 0);
                },
            },
            emphasis: {
                itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' },
            },
        }],
    };
}
