# Web Visualization — WebDataRocks + ECharts Integration

**Date:** 2026-03-18
**Status:** In Progress (functional, needs polish)

---

## Summary

Integrated WebDataRocks pivot table and ECharts charting library into the Expo Web frontend. Both libraries required special handling due to React 19 incompatibility and Expo/Metro bundler constraints.

---

## Problems Solved

### 1. WebDataRocks React 19 Crash
- **Problem:** WebDataRocks React wrapper bundles old React internally → "older version of React" error
- **Fix:** Use vanilla JS API directly (`new WebDataRocks({container})`) instead of React wrapper
- **File:** `frontend/components/Chat/PivotDataView.web.tsx`

### 2. SSR "window is not defined" Crash
- **Problem:** Both WebDataRocks and ECharts access `window` at import time → crashes on SSR/initial load
- **Fix:** Dynamic `import()` inside `useEffect` — only loads after component mounts on client
- **Files:** `PivotDataView.web.tsx`, `EChartsWrapper.tsx`

### 3. findHostInstance Crash (Page Refresh)
- **Problem:** React rendering children inside WebDataRocks container div caused DOM conflict
- **Fix:** Keep WebDataRocks container div **empty** (no React children). Loading indicator is a sibling element.
- **File:** `PivotDataView.web.tsx`

### 4. tslib ESM/CJS Incompatibility
- **Problem:** Metro bundles `tslib` CJS module which lacks `default` export. ECharts/zrender expects ESM → `Cannot destructure property '__extends' of 'tslib.default'`
- **Fix:** Metro `resolveRequest` interceptor redirects `tslib` → `tslib.es6.mjs` on web platform
- **File:** `frontend/metro.config.js`

### 5. Field Detection — Mixed Thai/Numeric Columns
- **Problem:** "รวมทั้งปี (ล้านบาท)" classified as time dimension because "ปี" matched time keywords, even though column is numeric with "บาท" measure keyword
- **Fix:** Adjusted `detectFields()` priority: numeric + measure keyword wins over time keyword
- **File:** `frontend/utils/pivotEngine.ts`

### 6. Pre-aggregated Total Column Double-Counting
- **Problem:** WebDataRocks summed pre-aggregated "รวมทั้งปี" column alongside monthly columns → inflated Grand Total
- **Fix:** `buildReport()` filters columns matching TOTAL_KEYWORDS from measures
- **File:** `PivotDataView.web.tsx`

### 7. P&L Charts Not Rendering (visualization='table')
- **Problem:** AI backend sets `visualization='table'` for P&L data. In DataChart.tsx, `analysis` useMemo returns null for `visualization='table'` → early return before ECharts render path, even though `echartsOption` was valid
- **Fix:** Moved ECharts render block **before** `if (!analysis) return null` guard. ECharts uses `echartsOption` (computed independently), not `analysis`.
- **File:** `frontend/components/Chat/DataChart.tsx`

### 8. P&L Chart Type Wrong (vertical_bar instead of grouped_bar)
- **Problem:** `resolveChartType()` returned null for `suggested_type=null` + `visualization='table'` → fell back to `'vertical_bar'` → no series grouping → each row = separate bar, repeated category labels, "series0" names
- **Fix:** Added `available_types[0]` fallback in `resolveChartType()`. P&L data with `available_types=['grouped_bar',...]` now correctly uses `grouped_bar` → `buildMultiSeries()` with proper series grouping.
- **File:** `frontend/types/chart.ts`

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/components/Chat/PivotDataView.web.tsx` | **New** — WebDataRocks vanilla JS wrapper |
| `frontend/components/Chat/PivotDataView.tsx` | **New** — Mobile fallback (read-only table) |
| `frontend/components/Chart/EChartsWrapper.tsx` | **Rewritten** — Dynamic import, module-level cache |
| `frontend/components/Chat/DataChart.tsx` | **Modified** — ECharts path moved before analysis null-guard |
| `frontend/types/chart.ts` | **Modified** — `resolveChartType()` added `available_types[0]` fallback |
| `frontend/utils/pivotEngine.ts` | **Modified** — Field detection priority fix |
| `frontend/utils/chartDataTransform.ts` | No changes (existing builders work correctly) |
| `frontend/metro.config.js` | **Modified** — tslib ESM override + .mjs source ext |
| `frontend/components/Chat/ChatBubble.tsx` | **Modified** — PivotDataView toggle button integration |

---

## Architecture Decisions

### 1. Vanilla JS over React Wrappers
Both WebDataRocks and ECharts have React wrappers, but neither is compatible with React 19 (Expo SDK 52). Using vanilla JS API directly with `useRef` for DOM containers avoids the incompatibility entirely and gives more control.

### 2. Platform-Specific Files (.web.tsx)
Metro resolves `.web.tsx` on web and `.tsx` on native automatically. PivotDataView has two implementations:
- `.web.tsx` — full WebDataRocks with vanilla JS
- `.tsx` — lightweight read-only table for mobile

### 3. ECharts Render Before Analysis Guard
`echartsOption` and `analysis` are independent computations:
- `echartsOption` = `buildEChartsOption(data, viz, chartConfig)` — works for any data
- `analysis` = pattern detection for gifted-charts fallback — returns null for `viz='table'`

The ECharts path must come first to ensure charts render when `echartsOption` is valid, regardless of `analysis` state.

### 4. Chart Type Resolution Priority
```
suggested_type > available_types[0] > VISUALIZATION_TO_ECHARTS[visualization] > 'vertical_bar'
```
This ensures AI-recommended chart types are respected even when `suggested_type` is null but `available_types` are provided.

---

## Render Flow (DataChart.tsx)

```
Component Mount
  ├── echartsOption = buildEChartsOption(data, viz, chartConfig)  [useMemo]
  ├── analysis = analyzeData(data, viz, chartConfig)              [useMemo]
  │     └── returns null when viz='table' or 'single_value'
  │
  ├── if (isEChartsAvailable() && echartsOption)                  [FIRST CHECK]
  │     └── return <EChartsWrapper option={echartsOption} />
  │
  ├── if (!analysis) return null                                   [SECOND CHECK]
  │     └── only blocks gifted-charts fallback path
  │
  └── return <GiftedCharts ... />                                  [NATIVE FALLBACK]
```

---

## Known Issues / TODO

- [ ] P&L chart series grouping functional but may need layout polish
- [ ] Chart tooltip formatting could be improved for P&L financial data
- [ ] WebDataRocks theme doesn't auto-switch with dark mode
- [ ] ECharts fullscreen modal needs testing on various screen sizes
- [ ] Remove any remaining debug console.log if found
