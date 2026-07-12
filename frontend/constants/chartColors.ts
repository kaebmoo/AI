/**
 * Shared chart color palettes.
 */

/** Primary NT chart palette — 5 official brand colors.
 * Order matters for colorblind separation (verified via CIELAB dE76 under
 * deuteranopia/protanopia simulation): Dark Grey buffers Brick Red from both
 * Teal (original risk) and Brown (red-family collision under protanopia) —
 * do not move Brick Red adjacent to Teal or Brown. */
export const NT_CHART_PALETTE = [
    '#FFD100', // NT Yellow (PANTONE 109C) — bar/area fill only, see B1 line-color rule
    '#40C1AC', // Teal 7465C
    '#924C2E', // Brown 7587C
    '#545859', // Dark Grey 425C
    '#E1523E', // Brick Red 7625C
];

/** Line-series palette — NT_CHART_PALETTE without Yellow (~1.4:1 contrast on
 * white, unreadable as a thin 2px stroke). Used for any 'line' series type,
 * single or multi. */
export const NT_LINE_PALETTE = NT_CHART_PALETTE.slice(1);

/** Financial chart colors — brand-aligned, still reads positive/negative by instinct */
export const FINANCIAL_COLORS = {
    positive: '#40C1AC',
    negative: '#E1523E',
    neutral: '#545859',
};

/** Dark/light mode text & line colors for ECharts */
export const CHART_THEME = {
    dark: {
        text: '#E5E7EB',        // gray-200 — titles, data labels
        subText: '#9CA3AF',     // gray-400 — axis labels, legend
        axisLine: '#4B5563',    // gray-600 — axis lines
        splitLine: '#374151',   // gray-700 — grid lines
    },
    light: {
        text: '#374151',        // gray-700 — titles, data labels
        subText: '#6B7280',     // gray-500 — axis labels, legend
        axisLine: '#D1D5DB',    // gray-300 — axis lines
        splitLine: '#E5E7EB',   // gray-200 — grid lines
    },
};

/** Heatmap gradient — blue (low) → yellow (mid) → red (high) */
export const HEATMAP_COLORS = {
    min: '#313695',
    mid: '#FFFFBF',
    max: '#A50026',
};

/** Backward-compat alias used by DataChart.tsx */
export const SERIES_COLORS = NT_CHART_PALETTE;
