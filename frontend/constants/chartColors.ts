/**
 * Shared chart color palettes.
 */

/** Primary NT chart palette — 10 colors */
export const NT_CHART_PALETTE = [
    '#3B82F6', // Blue 500
    '#10B981', // Emerald 500
    '#F59E0B', // Amber 500
    '#EF4444', // Red 500
    '#8B5CF6', // Violet 500
    '#EC4899', // Pink 500
    '#06B6D4', // Cyan 500
    '#F97316', // Orange 500
    '#14B8A6', // Teal 500
    '#6366F1', // Indigo 500
];

/** Financial chart colors */
export const FINANCIAL_COLORS = {
    positive: '#10B981',
    negative: '#EF4444',
    neutral: '#6B7280',
};

/** Backward-compat alias used by DataChart.tsx */
export const SERIES_COLORS = NT_CHART_PALETTE;
