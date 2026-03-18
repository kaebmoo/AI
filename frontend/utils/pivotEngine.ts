/**
 * Pivot Engine — Pure TypeScript, no DOM dependencies.
 * Takes raw SQL result rows + config → produces pivoted data.
 * Works on Expo Web + Mobile.
 */

// ============================================================
// Types
// ============================================================

export interface PivotField {
    name: string;        // Column name from SQL result
    type: 'dimension' | 'measure';  // Auto-detected or user-set
}

export interface PivotConfig {
    rowFields: string[];     // Columns to use as row headers
    colFields: string[];     // Columns to use as column headers (pivot)
    valueField: string;      // Column to aggregate
    aggregation: 'sum' | 'avg' | 'count' | 'min' | 'max';
}

export interface PivotResult {
    // For table display
    rowHeaders: string[];        // Unique combined row labels
    colHeaders: string[];        // Unique combined column labels
    matrix: (number | null)[][]; // [rowIdx][colIdx] = aggregated value
    rowTotals: number[];         // Sum per row
    colTotals: number[];         // Sum per column
    grandTotal: number;

    // For flat display (when no colFields)
    flatRows: Record<string, any>[];
    flatColumns: string[];
}

// ============================================================
// Field Detection
// ============================================================

const TIME_KEYWORDS = ['month', 'year', 'date', 'quarter', 'week',
    'เดือน', 'ปี', 'วันที่', 'ไตรมาส', 'สัปดาห์'];
const MEASURE_KEYWORDS = ['total', 'revenue', 'amount', 'value', 'price', 'cost',
    'profit', 'sum', 'avg', 'count', 'baht', 'บาท', 'รายได้',
    'ค่าใช้จ่าย', 'กำไร', 'ยอด', 'มูลค่า', 'ต้นทุน', 'ขาดทุน'];

/**
 * Check if a value is truly numeric (the ENTIRE string must be a valid number).
 *
 * Uses Number() instead of parseFloat() because:
 * - parseFloat("01.รายได้") → 1  ← WRONG! It parses leading digits only
 * - Number("01.รายได้")     → NaN ← CORRECT! Entire string must be numeric
 *
 * Also handles comma-formatted numbers like "1,234.56"
 */
function isStrictlyNumeric(v: any): boolean {
    if (typeof v === 'number' && !isNaN(v)) return true;
    if (v === null || v === undefined || v === '') return false;
    const s = String(v).replace(/,/g, '').trim();
    if (s === '') return false;
    return !isNaN(Number(s));
}

/**
 * Auto-detect field types from data.
 * Returns fields in original order (same as data columns).
 */
export function detectFields(data: Record<string, any>[]): PivotField[] {
    if (!data || data.length === 0) return [];

    const keys = Object.keys(data[0]);
    const fields: PivotField[] = [];

    for (const key of keys) {
        const lower = key.toLowerCase();
        const sampleValues = data.slice(0, 20).map(r => r[key]);
        const nonEmpty = sampleValues.filter(v => v !== null && v !== undefined && v !== '');
        const numericCount = nonEmpty.filter(v => isStrictlyNumeric(v)).length;
        // Need >80% of non-empty values to be numeric
        const isNumeric = nonEmpty.length > 0 && numericCount > nonEmpty.length * 0.8;
        const isMeasureKeyword = MEASURE_KEYWORDS.some(k => lower.includes(k));
        const isTimeDim = TIME_KEYWORDS.some(t => lower.includes(t));

        // Classification priority:
        // 1. Numeric + has measure keyword (e.g. "รวมทั้งปี (ล้านบาท)") → MEASURE
        //    (measure keyword wins over time keyword when data is actually numeric)
        // 2. Numeric + no time keyword → MEASURE
        // 3. Has measure keyword + no time keyword → MEASURE
        // 4. Everything else → DIMENSION
        const isMeasure = (isNumeric && isMeasureKeyword)       // "รวมทั้งปี (ล้านบาท)" = numeric + "บาท" → measure even though "ปี"
            || (isNumeric && !isTimeDim)                         // pure numeric, not a time field
            || (isMeasureKeyword && !isTimeDim);                 // has measure keyword, not time
        fields.push({
            name: key,
            type: isMeasure ? 'measure' : 'dimension',
        });
    }

    return fields;
}

/**
 * Suggest a default PivotConfig based on detected fields.
 *
 * Smart heuristics:
 * - If data looks already-pivoted (many measures like ม.ค./ก.พ./มี.ค.), use ALL dims as rows, no column pivot
 * - If data has time-like dimension, put it in columns
 * - Otherwise: first dim = row, second dim = column
 */
export function suggestConfig(fields: PivotField[]): PivotConfig {
    const dims = fields.filter(f => f.type === 'dimension');
    const measures = fields.filter(f => f.type === 'measure');

    // Heuristic: if 3+ measures → data is likely already pivoted (e.g. months as columns)
    // → put ALL dimensions as rows, no column pivot, first measure as value
    if (measures.length >= 3) {
        return {
            rowFields: dims.map(d => d.name),
            colFields: [],
            valueField: measures[0]?.name || '',
            aggregation: 'sum',
        };
    }

    // Heuristic: check if any dimension looks like time → put it as column
    const timeDim = dims.find(d =>
        TIME_KEYWORDS.some(t => d.name.toLowerCase().includes(t))
    );

    if (timeDim && dims.length >= 2) {
        const otherDims = dims.filter(d => d.name !== timeDim.name);
        return {
            rowFields: otherDims.map(d => d.name),
            colFields: [timeDim.name],
            valueField: measures[0]?.name || (fields[fields.length - 1]?.name || ''),
            aggregation: 'sum',
        };
    }

    // Default: first dim = row, second dim = column
    return {
        rowFields: dims.length > 0 ? [dims[0].name] : [],
        colFields: dims.length > 1 ? [dims[1].name] : [],
        valueField: measures.length > 0 ? measures[0].name : (fields[fields.length - 1]?.name || ''),
        aggregation: 'sum',
    };
}

// ============================================================
// Pivot Execution
// ============================================================

function aggregateValues(values: number[], agg: PivotConfig['aggregation']): number {
    if (values.length === 0) return 0;
    switch (agg) {
        case 'sum': return values.reduce((a, b) => a + b, 0);
        case 'avg': return values.reduce((a, b) => a + b, 0) / values.length;
        case 'count': return values.length;
        case 'min': return Math.min(...values);
        case 'max': return Math.max(...values);
    }
}

function buildKey(row: Record<string, any>, fields: string[]): string {
    return fields.map(f => String(row[f] ?? '')).join(' | ');
}

/**
 * Execute pivot on raw data.
 */
export function executePivot(
    data: Record<string, any>[],
    config: PivotConfig,
): PivotResult {
    const { rowFields, colFields, valueField, aggregation } = config;

    // Collect unique row/col keys preserving order from data
    const rowKeySet = new Map<string, true>();
    const colKeySet = new Map<string, true>();
    // Accumulator: rowKey → colKey → values[]
    const acc: Record<string, Record<string, number[]>> = {};

    for (const row of data) {
        const rKey = rowFields.length > 0 ? buildKey(row, rowFields) : '_all';
        const cKey = colFields.length > 0 ? buildKey(row, colFields) : '_all';
        const val = typeof row[valueField] === 'number'
            ? row[valueField]
            : parseFloat(String(row[valueField] || '0').replace(/,/g, '')) || 0;

        rowKeySet.set(rKey, true);
        colKeySet.set(cKey, true);

        if (!acc[rKey]) acc[rKey] = {};
        if (!acc[rKey][cKey]) acc[rKey][cKey] = [];
        acc[rKey][cKey].push(val);
    }

    const rowHeaders = Array.from(rowKeySet.keys());
    const colHeaders = Array.from(colKeySet.keys());

    // Build matrix
    const matrix: (number | null)[][] = [];
    const rowTotals: number[] = [];
    const colTotals: number[] = new Array(colHeaders.length).fill(0);
    let grandTotal = 0;

    for (let ri = 0; ri < rowHeaders.length; ri++) {
        const rowData: (number | null)[] = [];
        let rowSum = 0;
        for (let ci = 0; ci < colHeaders.length; ci++) {
            const vals = acc[rowHeaders[ri]]?.[colHeaders[ci]];
            if (vals && vals.length > 0) {
                const agg = aggregateValues(vals, aggregation);
                rowData.push(agg);
                rowSum += agg;
                colTotals[ci] += agg;
            } else {
                rowData.push(null);
            }
        }
        matrix.push(rowData);
        rowTotals.push(rowSum);
        grandTotal += rowSum;
    }

    // Build flat rows (for when colFields is empty or for export)
    const flatColumns = [...rowFields, ...colHeaders.filter(c => c !== '_all')];
    if (colHeaders.length === 1 && colHeaders[0] === '_all') {
        flatColumns.push(valueField);
    }

    const flatRows = rowHeaders.map((rh, ri) => {
        const row: Record<string, any> = {};
        // Split row header back to fields
        const parts = rh.split(' | ');
        rowFields.forEach((f, i) => { row[f] = parts[i] || ''; });

        if (colHeaders.length === 1 && colHeaders[0] === '_all') {
            row[valueField] = matrix[ri][0];
        } else {
            colHeaders.forEach((ch, ci) => {
                row[ch] = matrix[ri][ci];
            });
        }
        return row;
    });

    return {
        rowHeaders,
        colHeaders: colHeaders.filter(c => c !== '_all'),
        matrix,
        rowTotals,
        colTotals,
        grandTotal,
        flatRows,
        flatColumns,
    };
}

// ============================================================
// Multi-Measure Execution (for already-pivoted / wide-format data)
// ============================================================

/**
 * Result from multi-measure aggregation.
 * Used when data is already pivoted (e.g. months as separate columns).
 * Shape is intentionally compatible with PivotResult for reuse in rendering.
 */
export interface MultiMeasureResult {
    rowHeaders: string[];        // Unique combined row labels
    measureNames: string[];      // Column headers = measure field names
    matrix: (number | null)[][]; // [rowIdx][measureIdx] = aggregated value
    rowTotals: number[];
    colTotals: number[];
    grandTotal: number;
}

/**
 * Aggregate multiple measure columns grouped by row dimensions.
 * Unlike executePivot (which pivots ONE value across a column dimension),
 * this shows MULTIPLE value columns side-by-side (like Tableau "Measure Values").
 *
 * Example:
 *   data: [{กลุ่มธุรกิจ: "Fixed", ม.ค.: 100, ก.พ.: 200}, ...]
 *   rowFields: ["กลุ่มธุรกิจ"]
 *   measureFields: ["ม.ค.", "ก.พ."]
 *   → rowHeaders: ["Fixed"], measureNames: ["ม.ค.", "ก.พ."], matrix: [[100, 200]]
 */
export function executeMultiMeasure(
    data: Record<string, any>[],
    rowFields: string[],
    measureFields: string[],
    aggregation: PivotConfig['aggregation'],
): MultiMeasureResult {
    if (!data || data.length === 0 || measureFields.length === 0) {
        return { rowHeaders: [], measureNames: measureFields, matrix: [], rowTotals: [], colTotals: [], grandTotal: 0 };
    }

    const rowKeySet = new Map<string, true>();
    const acc: Record<string, Record<string, number[]>> = {};

    for (const row of data) {
        const rKey = rowFields.length > 0 ? buildKey(row, rowFields) : '_all';
        rowKeySet.set(rKey, true);
        if (!acc[rKey]) acc[rKey] = {};
        for (const m of measureFields) {
            if (!acc[rKey][m]) acc[rKey][m] = [];
            const val = typeof row[m] === 'number'
                ? row[m]
                : parseFloat(String(row[m] || '0').replace(/,/g, '')) || 0;
            acc[rKey][m].push(val);
        }
    }

    // Sort row headers by dimension parts (for proper row spanning & logical order)
    const rowHeaders = Array.from(rowKeySet.keys()).sort((a, b) => {
        const pa = a.split(' | ');
        const pb = b.split(' | ');
        for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
            const cmp = (pa[i] || '').localeCompare(pb[i] || '', 'th');
            if (cmp !== 0) return cmp;
        }
        return 0;
    });

    const matrix: (number | null)[][] = [];
    const rowTotals: number[] = [];
    const colTotals = new Array(measureFields.length).fill(0);
    let grandTotal = 0;

    for (const rh of rowHeaders) {
        const rowData: (number | null)[] = [];
        let rowSum = 0;
        for (let mi = 0; mi < measureFields.length; mi++) {
            const vals = acc[rh]?.[measureFields[mi]];
            if (vals && vals.length > 0) {
                const agg = aggregateValues(vals, aggregation);
                rowData.push(agg);
                rowSum += agg;
                colTotals[mi] += agg;
            } else {
                rowData.push(null);
            }
        }
        matrix.push(rowData);
        rowTotals.push(rowSum);
        grandTotal += rowSum;
    }

    return { rowHeaders, measureNames: measureFields, matrix, rowTotals, colTotals, grandTotal };
}

// ============================================================
// Smart Month Sorting (reusable)
// ============================================================

const THAI_MONTH_ORDER: Record<string, number> = {
    'ม.ค.': 1, 'ก.พ.': 2, 'มี.ค.': 3, 'เม.ย.': 4, 'พ.ค.': 5, 'มิ.ย.': 6,
    'ก.ค.': 7, 'ส.ค.': 8, 'ก.ย.': 9, 'ต.ค.': 10, 'พ.ย.': 11, 'ธ.ค.': 12,
    'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4,
    'พฤษภาคม': 5, 'มิถุนายน': 6, 'กรกฎาคม': 7, 'สิงหาคม': 8,
    'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12,
};

export function smartSort(values: string[]): string[] {
    return [...values].sort((a, b) => {
        // Try Thai month
        const ma = THAI_MONTH_ORDER[a];
        const mb = THAI_MONTH_ORDER[b];
        if (ma && mb) return ma - mb;

        // Try numeric
        const na = parseFloat(a);
        const nb = parseFloat(b);
        if (!isNaN(na) && !isNaN(nb)) return na - nb;

        // Fallback: string compare
        return a.localeCompare(b);
    });
}

// ============================================================
// ECharts Dataset Builder
// ============================================================

/**
 * Build ECharts option using dataset + encode for dynamic axis mapping.
 * This is the key to Tableau-like flexibility.
 */
export function buildDynamicChartOption(
    data: Record<string, any>[],
    config: {
        categoryField: string;   // X-axis (dimension)
        valueFields: string[];   // Y-axis values (measures) — can be multiple series
        seriesField?: string;    // Optional: split into series by this dimension
        chartType?: 'bar' | 'line' | 'scatter';
        title?: string;
    },
): object {
    const { categoryField, valueFields, seriesField, chartType = 'bar', title } = config;

    // If seriesField is provided, we need to group data
    if (seriesField) {
        const seriesNames = [...new Set(data.map(d => String(d[seriesField] || '')))];
        const categories = [...new Set(data.map(d => String(d[categoryField] || '')))];
        const valueField = valueFields[0] || '';

        const series = seriesNames.map((name, idx) => {
            const seriesData = categories.map(cat => {
                const row = data.find(d =>
                    String(d[categoryField]) === cat && String(d[seriesField]) === name
                );
                return row ? (typeof row[valueField] === 'number' ? row[valueField] : parseFloat(row[valueField]) || 0) : 0;
            });
            return {
                name,
                type: chartType,
                data: seriesData,
            };
        });

        return {
            title: title ? { text: title, left: 'center' } : undefined,
            tooltip: { trigger: 'axis' },
            legend: { data: seriesNames, bottom: 0, type: 'scroll' },
            grid: { left: '3%', right: '5%', bottom: '15%', top: '15%', containLabel: true },
            xAxis: { type: 'category', data: categories },
            yAxis: { type: 'value', name: valueField },
            series,
        };
    }

    // Simple: use ECharts dataset + encode
    // Transform data to dataset source format
    const dimensions = [categoryField, ...valueFields];
    const source = data.map(row => dimensions.map(d => row[d]));

    const series = valueFields.map(vf => ({
        type: chartType,
        encode: { x: categoryField, y: vf },
        name: vf,
    }));

    return {
        title: title ? { text: title, left: 'center' } : undefined,
        tooltip: { trigger: 'axis' },
        legend: valueFields.length > 1 ? { data: valueFields, bottom: 0 } : undefined,
        grid: { left: '3%', right: '5%', bottom: '15%', top: '15%', containLabel: true },
        dataset: {
            dimensions,
            source,
        },
        xAxis: { type: 'category' },
        yAxis: { type: 'value', name: valueFields.length === 1 ? valueFields[0] : '' },
        series,
    };
}
