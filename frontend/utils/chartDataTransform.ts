/**
 * ECharts option builders — transforms backend data into ECharts option objects.
 */
import { resolveChartType, type ChartConfig } from '../types/chart';
import { NT_CHART_PALETTE, FINANCIAL_COLORS } from '../constants/chartColors';
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

/**
 * Main dispatcher — builds ECharts option from data + visualization + chartConfig.
 */
export function buildEChartsOption(
    data: Record<string, any>[],
    visualization?: string,
    chartConfig?: ChartConfig,
): object | null {
    if (!data || data.length === 0) return null;

    const chartType = resolveChartType(visualization, chartConfig);
    if (!chartType) return null;

    const catCol = chartConfig?.category_column || Object.keys(data[0])[0];
    const measureCol = chartConfig?.measure_column || findMeasureColumn(data[0], catCol);
    const seriesCol = chartConfig?.series_column;

    if (!catCol || !measureCol) return null;

    switch (chartType) {
        case 'vertical_bar':
            return buildVerticalBar(data, catCol, measureCol, chartConfig);
        case 'horizontal_bar':
            return buildHorizontalBar(data, catCol, measureCol, chartConfig);
        case 'line':
            return buildLine(data, catCol, measureCol, chartConfig);
        case 'multi_line':
        case 'grouped_bar':
        case 'stacked_bar':
        case 'stacked_bar_100':
            return buildMultiSeries(data, catCol, measureCol, seriesCol, chartType, chartConfig);
        case 'pie_chart':
            return buildPie(data, catCol, measureCol, chartConfig, false);
        case 'donut_chart':
            return buildPie(data, catCol, measureCol, chartConfig, true);
        case 'area':
        case 'stacked_area':
            return buildArea(data, catCol, measureCol, seriesCol, chartType, chartConfig);
        case 'waterfall':
            return buildWaterfall(data, catCol, measureCol, chartConfig);
        default:
            return buildVerticalBar(data, catCol, measureCol, chartConfig);
    }
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

/** Common tooltip config */
function baseTooltip(): object {
    return {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        confine: true,
    };
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
        yAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
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
        xAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
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
        yAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
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
        yAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
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
        yAxis: { type: 'value', axisLabel: { fontSize: 11, formatter: yAxisFormatter } },
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
