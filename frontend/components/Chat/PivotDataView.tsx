/**
 * PivotDataView — Mobile fallback (read-only table).
 *
 * On web, Metro resolves PivotDataView.web.tsx (WebDataRocks).
 * On mobile (iOS/Android), this simplified version is used instead.
 *
 * Features:
 * - Auto-detect fields and suggest config
 * - Render simple ScrollView table with the pivoted/multi-measure result
 * - Row spanning for multi-dimension rows
 * - No interactive pivot UI (that's the web version's job)
 */

import React, { useMemo } from 'react';
import {
    View, Text, ScrollView, useColorScheme, StyleSheet,
} from 'react-native';
import {
    detectFields, suggestConfig, executePivot, executeMultiMeasure,
    type PivotConfig,
} from '../../utils/pivotEngine';

// ============================================================
// Types
// ============================================================

interface PivotDataViewProps {
    data: Record<string, any>[];
    title?: string;
}

// ============================================================
// Number Formatting
// ============================================================

function formatNumber(val: number | null): string {
    if (val === null || val === undefined) return '-';
    const abs = Math.abs(val);
    if (abs >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(2)} พลบ.`;
    if (abs >= 1_000_000) return `${(val / 1_000_000).toFixed(2)} ลบ.`;
    if (abs >= 1_000) return val.toLocaleString('th-TH', { maximumFractionDigits: 2 });
    if (abs === 0) return '-';
    return val.toFixed(2);
}

// ============================================================
// Component
// ============================================================

export const PivotDataView: React.FC<PivotDataViewProps> = ({ data, title }) => {
    const isDark = useColorScheme() === 'dark';

    // Auto-detect and compute
    const displayData = useMemo(() => {
        if (!data || data.length === 0) return null;

        const fields = detectFields(data);
        const suggested = suggestConfig(fields);
        const dims = fields.filter(f => f.type === 'dimension');
        const measures = fields.filter(f => f.type === 'measure');

        // Wide format (already pivoted) → multi-measure mode
        if (measures.length >= 3) {
            const rowFields = dims.map(d => d.name);
            const result = executeMultiMeasure(data, rowFields, measures.map(m => m.name), 'sum');
            return {
                rowHeaders: result.rowHeaders,
                colHeaders: result.measureNames,
                matrix: result.matrix,
                rowTotals: result.rowTotals,
                colTotals: result.colTotals,
                grandTotal: result.grandTotal,
                rowFields,
            };
        }

        // Long format → standard pivot
        const config: PivotConfig = {
            rowFields: suggested.rowFields,
            colFields: suggested.colFields,
            valueField: suggested.valueField,
            aggregation: 'sum',
        };
        const result = executePivot(data, config);
        return {
            rowHeaders: result.rowHeaders,
            colHeaders: result.colHeaders.length > 0 ? result.colHeaders : [suggested.valueField],
            matrix: result.matrix,
            rowTotals: result.rowTotals,
            colTotals: result.colTotals,
            grandTotal: result.grandTotal,
            rowFields: suggested.rowFields,
        };
    }, [data]);

    if (!displayData) return null;

    const { rowHeaders, colHeaders, matrix, rowTotals, rowFields } = displayData;
    const textColor = isDark ? '#E5E7EB' : '#1F2937';
    const headerBg = isDark ? '#1E3A5F' : '#EFF6FF';
    const borderColor = isDark ? '#374151' : '#E5E7EB';
    const negColor = '#EF4444';
    const cellWidth = 100;
    const rowHeaderWidth = 130;

    return (
        <View style={[s.container, { borderColor, backgroundColor: isDark ? '#111827' : '#fff' }]}>
            {title ? (
                <Text style={[s.title, { color: textColor, borderBottomColor: borderColor }]}>{title}</Text>
            ) : null}

            <ScrollView horizontal showsHorizontalScrollIndicator>
                <View>
                    {/* Header */}
                    <View style={[s.row, { backgroundColor: headerBg }]}>
                        {rowFields.map((rf, i) => (
                            <View key={i} style={[s.cell, { width: rowHeaderWidth, borderColor }]}>
                                <Text style={[s.headerText, { color: textColor }]} numberOfLines={1}>{rf}</Text>
                            </View>
                        ))}
                        {colHeaders.map((col, ci) => (
                            <View key={ci} style={[s.cell, { width: cellWidth, borderColor }]}>
                                <Text style={[s.headerText, { color: textColor }]} numberOfLines={2}>{col}</Text>
                            </View>
                        ))}
                        <View style={[s.cell, { width: cellWidth, borderColor, backgroundColor: isDark ? '#1a237e' : '#e8eaf6' }]}>
                            <Text style={[s.headerText, { color: textColor, fontWeight: '700' }]}>รวม</Text>
                        </View>
                    </View>

                    {/* Data */}
                    <ScrollView style={{ maxHeight: 400 }} nestedScrollEnabled>
                        {rowHeaders.map((rh, ri) => {
                            const parts = rh.split(' | ');
                            return (
                                <View key={ri} style={[s.row, {
                                    backgroundColor: ri % 2 === 0 ? 'transparent' : (isDark ? '#1F293744' : '#F9FAFB'),
                                }]}>
                                    {parts.map((part, pi) => (
                                        <View key={pi} style={[s.cell, { width: rowHeaderWidth, borderColor }]}>
                                            <Text style={[s.cellText, { color: textColor, fontWeight: pi === 0 ? '600' : '400' }]}
                                                numberOfLines={2}>{part}</Text>
                                        </View>
                                    ))}
                                    {matrix[ri].map((val, ci) => (
                                        <View key={`v${ci}`} style={[s.cell, { width: cellWidth, borderColor }]}>
                                            <Text style={[s.numText, { color: val !== null && val < 0 ? negColor : textColor }]}>
                                                {formatNumber(val)}
                                            </Text>
                                        </View>
                                    ))}
                                    <View style={[s.cell, { width: cellWidth, borderColor }]}>
                                        <Text style={[s.numText, { color: rowTotals[ri] < 0 ? negColor : textColor, fontWeight: '600' }]}>
                                            {formatNumber(rowTotals[ri])}
                                        </Text>
                                    </View>
                                </View>
                            );
                        })}
                    </ScrollView>
                </View>
            </ScrollView>

            <Text style={[s.footer, { color: isDark ? '#6B7280' : '#9CA3AF' }]}>
                {rowHeaders.length} แถว × {colHeaders.length} คอลัมน์ | {data.length} รายการดิบ
            </Text>
        </View>
    );
};

const s = StyleSheet.create({
    container: { borderWidth: 1, borderRadius: 8, overflow: 'hidden', marginVertical: 8 },
    title: { fontSize: 13, fontWeight: '700', padding: 10, borderBottomWidth: 1 },
    row: { flexDirection: 'row' },
    cell: { paddingHorizontal: 6, paddingVertical: 6, borderWidth: 0.5, justifyContent: 'center' },
    headerText: { fontSize: 11, fontWeight: '600', textAlign: 'center' },
    cellText: { fontSize: 11 },
    numText: { fontSize: 11, textAlign: 'right', fontVariant: ['tabular-nums'] },
    footer: { fontSize: 10, textAlign: 'right', padding: 6 },
});

export default PivotDataView;
