/**
 * PivotDataView — Web version using WebDataRocks (vanilla JS).
 *
 * WebDataRocks handles ALL pivot functionality:
 * - Drag-drop field configuration
 * - Aggregation (SUM, AVG, COUNT, MIN, MAX, etc.)
 * - Table rendering with totals
 * - Export to PDF, Excel, JSON
 * - Theming (dark/light)
 *
 * We only provide:
 * 1. Data (from SQL query result)
 * 2. Smart defaults (from suggestConfig in pivotEngine.ts)
 * 3. Theme CSS
 *
 * IMPORTANT: We use the vanilla JS API (`new WebDataRocks(...)`) instead of
 * the React wrapper to avoid React 19 incompatibility. The React wrapper
 * pre-bundles old React elements that crash with React 19.
 * This is the same pattern as EChartsWrapper.tsx (echarts.init on a div ref).
 *
 * Metro resolves this file on web; PivotDataView.tsx is used on mobile.
 */

import React, { useRef, useMemo, useEffect, useCallback, useState } from 'react';
import { detectFields, suggestConfig, type PivotField } from '../../utils/pivotEngine';

// ============================================================
// Types
// ============================================================

interface PivotDataViewProps {
    data: Record<string, any>[];
    title?: string;
}

// ============================================================
// Helper: Map suggestConfig → WebDataRocks report
// ============================================================

function buildReport(
    data: Record<string, any>[],
    title?: string,
): any {
    const fields = detectFields(data);
    const suggested = suggestConfig(fields);
    const measures = fields.filter(f => f.type === 'measure');

    // Filter out pre-aggregated "total" columns (e.g. "รวมทั้งปี (ล้านบาท)")
    // These are pre-calculated sums from the database — including them causes
    // double-counting because WebDataRocks also computes Grand Total via SUM.
    const TOTAL_KEYWORDS = ['รวม', 'total', 'sum', 'grand', 'ytd', 'ทั้งปี'];
    const activeMeasures = measures.filter(m => {
        const lower = m.name.toLowerCase();
        return !TOTAL_KEYWORDS.some(k => lower.includes(k));
    });
    // Fall back to all measures if filtering removed everything
    const finalMeasures = activeMeasures.length > 0 ? activeMeasures : measures;

    // Build slice: rows, columns, measures
    const rows = suggested.rowFields.map(f => ({ uniqueName: f }));
    const columns = suggested.colFields.map(f => ({ uniqueName: f }));

    // Use all measures if data is already pivoted (wide format), else use suggested single value
    const measureSlice = finalMeasures.length >= 3
        ? finalMeasures.map(m => ({ uniqueName: m.name, aggregation: 'sum' }))
        : finalMeasures.length > 0
            ? [{ uniqueName: suggested.valueField || finalMeasures[0].name, aggregation: 'sum' }]
            : [];

    return {
        dataSource: { data },
        slice: {
            rows,
            columns,
            measures: measureSlice,
        },
        options: {
            grid: {
                showTotals: 'on',
                showGrandTotals: 'on',
                title: title || '',
                showHeaders: true,
            },
            configuratorActive: false,
        },
        formats: [{
            name: '',
            thousandsSeparator: ',',
            decimalSeparator: '.',
            decimalPlaces: 2,
        }],
    };
}

// ============================================================
// Component — Vanilla JS WebDataRocks (no React wrapper)
// ============================================================

export const PivotDataView: React.FC<PivotDataViewProps> = ({ data, title }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const pivotRef = useRef<any>(null);
    const [ready, setReady] = useState(false);
    // The library is fetched on first open (a lazy chunk in dev) — when that fails, say so instead of loading forever
    const [failed, setFailed] = useState(false);

    // Detect dark mode
    const isDark = typeof window !== 'undefined' &&
        window.matchMedia?.('(prefers-color-scheme: dark)')?.matches;

    // Dark mode cell customizer
    const customizeCell = useCallback((cell: any, cellData: any) => {
        if (!isDark) return;
        const style = cell.style as Record<string, string>;
        if (style) {
            style['background-color'] = cellData.isGrandTotal || cellData.isTotalColumn || cellData.isTotalRow
                ? '#1E3A5F'
                : cellData.hierarchy
                    ? '#1F2937'
                    : '#111827';
            style['color'] = '#E5E7EB';
            style['border-color'] = '#374151';
        }
    }, [isDark]);

    // Load WebDataRocks vanilla JS + CSS, then create pivot instance
    useEffect(() => {
        if (!containerRef.current || !data || data.length === 0) return;

        let destroyed = false;

        const init = async () => {
            try {
                // Load CSS
                await import('@webdatarocks/webdatarocks/webdatarocks.min.css');
                // Load vanilla JS — sets window.WebDataRocks via IIFE
                // (NOT the React wrapper which pre-bundles old React!)
                await import('@webdatarocks/webdatarocks/webdatarocks.js');
                const WebDataRocks = (window as any).WebDataRocks;

                if (destroyed || !containerRef.current) return;
                if (!WebDataRocks) {
                    console.error('WebDataRocks not found on window after import');
                    setFailed(true);
                    return;
                }

                const report = buildReport(data, title);

                // Create pivot using vanilla JS constructor
                const pivot = new WebDataRocks({
                    container: containerRef.current,
                    toolbar: true,
                    width: '100%',
                    height: 500,
                    report,
                    customizeCell: isDark ? customizeCell : undefined,
                    ready: () => {
                        if (!destroyed) setReady(true);
                    },
                });

                pivotRef.current = pivot;
            } catch (err) {
                console.error('Failed to load WebDataRocks:', err);
                if (!destroyed) setFailed(true);
            }
        };

        init();

        return () => {
            destroyed = true;
            if (pivotRef.current) {
                try {
                    pivotRef.current.dispose?.();
                } catch {
                    // ignore disposal errors
                }
                pivotRef.current = null;
            }
            // Clear the container
            if (containerRef.current) {
                containerRef.current.innerHTML = '';
            }
            setReady(false);
        };
    }, []); // Mount once

    // When data/title changes, update the existing pivot
    useEffect(() => {
        if (pivotRef.current && ready) {
            try {
                const newReport = buildReport(data, title);
                pivotRef.current.setReport(newReport);
            } catch (err) {
                console.error('Failed to update WebDataRocks report:', err);
            }
        }
    }, [data, title, ready]);

    if (!data || data.length === 0) return null;

    return (
        <div
            className="nt-pivot-wrapper"
            style={{
                width: '100%',
                borderRadius: 8,
                overflow: 'hidden',
                border: `1px solid ${isDark ? '#374151' : '#E5E7EB'}`,
            }}
        >
            {/* Loading indicator — separate from WebDataRocks container */}
            {!ready && (
                <div style={{
                    padding: 24,
                    textAlign: 'center',
                    color: isDark ? '#9CA3AF' : '#6B7280',
                }}>
                    {failed ? 'โหลด Pivot ไม่สำเร็จ — รีเฟรชหน้าแล้วลองใหม่' : 'Loading Pivot Table...'}
                </div>
            )}
            {/*
              WebDataRocks container — React must NOT render children inside this div.
              WebDataRocks takes full ownership of this DOM node via `new WebDataRocks({ container })`.
              If React tries to reconcile children here, it will crash (findHostInstance error).
            */}
            <div
                ref={containerRef}
                style={{ width: '100%', display: ready ? 'block' : 'none' }}
            />
        </div>
    );
};

export default PivotDataView;
