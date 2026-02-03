
import React from 'react';
import { View, Text, ScrollView, useColorScheme } from 'react-native';

interface DataTableProps {
    data: Record<string, any>[];
}

export const DataTable = ({ data }: DataTableProps) => {
    const isDark = useColorScheme() === 'dark';

    if (!data || data.length === 0) return null;

    const keys = Object.keys(data[0]);

    // 1. Hierarchy & Dimension Detection
    // Strict exclusion of measure terms from dimensions
    const isMeasure = (k: string) => ['total', 'revenue', 'amount', 'count', 'value', 'price', 'cost', 'profit', 'รายได้', 'ยอดรวม', 'จำนวน', 'expense', 'baht', 'บาท'].some(term => k.toLowerCase().includes(term));

    const monthKey = keys.find(k => !isMeasure(k) && ['month', 'เดือน'].some(term => k.toLowerCase().includes(term)));
    const yearKey = keys.find(k => !isMeasure(k) && ['year', 'ปี', 'พ.ศ.', 'ค.ศ.'].some(term => k.toLowerCase().includes(term)));
    const labelKey = monthKey || keys.find(k => !isMeasure(k) && ['date', 'label', 'name', 'time'].some(term => k.toLowerCase().includes(term)));

    // Measure Key
    const valueKey = keys.find(k => isMeasure(k)) || keys.find(k => typeof data[0][k] === 'number' && !k.toLowerCase().includes('id'));

    const dimensionKeys = keys.filter(k => {
        const lowerK = k.toLowerCase();
        const val = data[0][k];
        return (typeof val === 'string' || ['year', 'id', 'code', 'date'].some(t => lowerK.includes(t))) && k !== valueKey && !isMeasure(k);
    });

    const categoryKeys = dimensionKeys.filter(k =>
        !['year', 'month', 'date', 'time', 'quarter'].some(t => k.toLowerCase().includes(t))
    );

    // Determines if we should Pivot (Crosstab)
    // Rule: We have Time dimensions AND Category dimensions AND duplicate time entries (implying multiple series)
    let isCrosstab = false;
    let rowKey = ''; // e.g. Province
    let periodLabels: string[] = [];
    let pivotedRows: any[] = [];

    if (yearKey || monthKey) {
        // Check for duplicate time entries
        const timeLabels = data.map(item => {
            if (monthKey && yearKey) return `${item[monthKey]}/${item[yearKey]}`;
            if (labelKey) return String(item[labelKey]);
            return '';
        });
        const uniqueTimes = new Set(timeLabels);

        // Only pivot if we have duplicates (meaning multiple categories per time slot)
        if (timeLabels.length > uniqueTimes.size && categoryKeys.length > 0) {
            isCrosstab = true;
            rowKey = categoryKeys[0]; // Primary category (Province, Group)

            // --- Month Filling Logic ---
            // Sort periods naturally first
            let periods = Array.from(uniqueTimes);

            // Smart Sort: Try to parse as dates or integers
            periods.sort((a, b) => {
                // Try numeric month sort (e.g. 01/2568)
                const aParts = a.split('/');
                const bParts = b.split('/');
                if (aParts.length > 1 && bParts.length > 1) {
                    const aYear = parseInt(aParts[1]);
                    const bYear = parseInt(bParts[1]);
                    const aMonth = parseInt(aParts[0]);
                    const bMonth = parseInt(bParts[0]);
                    if (aYear !== bYear) return aYear - bYear;
                    return aMonth - bMonth;
                }
                return a.localeCompare(b);
            });

            // Force Fill 12 Months if looks like monthly data
            // Check if labels constitute months (01...12)
            const hasMonthLike = periods.some(p => {
                const m = parseInt(p.split('/')[0]);
                return !isNaN(m) && m >= 1 && m <= 12;
            });

            if (hasMonthLike && periods.length < 12) {
                // Detect Year from existing data
                const sampleparts = periods[0].split('/');
                const yearSuffix = sampleparts.length > 1 ? `/${sampleparts[1]}` : '';

                const allMonths = Array.from({ length: 12 }, (_, i) => {
                    const m = String(i + 1).padStart(2, '0');
                    return `${m}${yearSuffix}`;
                });

                // Merge (keep sorted existing, insert missing)
                // Simplest: Use allMonths as the base if yearSuffix implies a single year
                // If multiple years exists, this logic is tricky. 
                // Let's safe-guard: Only force fill if ALL periods belong to SAME year.
                const uniqueYears = new Set(periods.map(p => p.split('/')[1]));
                if (uniqueYears.size === 1) {
                    periodLabels = allMonths;
                } else {
                    periodLabels = periods;
                }
            } else {
                periodLabels = periods;
            }

            // Pivot Logic
            const rowMap: Record<string, any> = {};

            data.forEach(item => {
                const rVal = String(item[rowKey]);
                let tLabel = '';
                if (monthKey && yearKey) tLabel = `${item[monthKey]}/${item[yearKey]}`;
                else if (labelKey) tLabel = String(item[labelKey]);

                if (!rowMap[rVal]) {
                    rowMap[rVal] = { _rowLabel: rVal };
                }

                // FORMATTING: If user asked for % diff (Case 2), valueKey might be auto-detected wrong?
                // But Case 2 is NOT crosstab anymore due to stricter check. 
                // Case 1 is the Crosstab.
                rowMap[rVal][tLabel] = item[valueKey || keys[keys.length - 1]];
            });

            pivotedRows = Object.values(rowMap);
        }
    }

    // Fallback Parent Detection (Grouped List)
    let parentKey = '';
    if (!isCrosstab && dimensionKeys.length >= 2) {
        const uniqueCounts = dimensionKeys.map(k => ({
            key: k,
            count: new Set(data.map(d => d[k])).size
        }));
        uniqueCounts.sort((a, b) => a.count - b.count);
        if (uniqueCounts[0].count < data.length) {
            parentKey = uniqueCounts[0].key;
        }
    }

    // 2. Formatting Logic
    const renderCell = (key: string, value: any) => {
        if (typeof value === 'number') {
            const lowerKey = key.toLowerCase();
            // Don't format Year, ID, Code, keys, No.
            if (['year', 'id', 'code', 'key', 'no.', 'ปี', 'รหัส', 'quarter'].some(t => lowerKey.includes(t)) && key !== '_rowLabel') {
                return String(value);
            }
            return value.toLocaleString('th-TH', { maximumFractionDigits: 2 });
        }
        return String(value || '-');
    };

    // 3. Render Logic

    // RENDER: CROSSTAB (Pivot)
    const renderCrosstabTable = () => {
        return (
            <View>
                {/* Header Row */}
                <View className="flex-row bg-blue-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                    {/* Frozen First Column Header */}
                    <View className="px-4 py-3 bg-blue-100/50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700" style={{ width: 180 }}>
                        <Text className="text-xs font-bold text-gray-700 dark:text-gray-200 uppercase">{rowKey}</Text>
                    </View>
                    {/* Period Columns Header */}
                    {periodLabels.map((period, idx) => (
                        <View key={period} className="px-4 py-3" style={{ width: 120 }}>
                            <Text className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase text-center">{period}</Text>
                        </View>
                    ))}
                </View>

                {/* Data Rows */}
                {pivotedRows.map((row, rIdx) => (
                    <View key={rIdx} className={`flex-row border-b border-gray-100 dark:border-gray-800 ${rIdx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50/50 dark:bg-gray-800/30'}`}>
                        {/* Frozen First Column Data */}
                        <View className="px-4 py-3 bg-gray-50/80 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700" style={{ width: 180 }}>
                            <Text className="text-xs font-semibold text-gray-800 dark:text-gray-200" numberOfLines={2}>{row._rowLabel}</Text>
                        </View>
                        {/* Period Data Cells */}
                        {periodLabels.map((period) => (
                            <View key={period} className="px-4 py-3" style={{ width: 120 }}>
                                <Text className="text-xs text-gray-700 dark:text-gray-300 text-right font-variant-numeric">
                                    {renderCell(period, row[period])}
                                </Text>
                            </View>
                        ))}
                    </View>
                ))}
            </View>
        );
    };

    // RENDER: GROUPED LIST
    const renderGroupedTable = () => {
        const grouped: Record<string, typeof data> = {};
        data.forEach(item => {
            const pVal = String(item[parentKey]);
            if (!grouped[pVal]) grouped[pVal] = [];
            grouped[pVal].push(item);
        });
        const displayKeys = keys.filter(k => k !== parentKey);

        return (
            <View>
                {Object.entries(grouped).map(([groupName, groupItems], gIdx) => (
                    <View key={groupName} className="mb-4">
                        <View className="bg-blue-50 dark:bg-blue-900/40 px-4 py-2 border-l-4 border-blue-500 mb-1">
                            <Text className="font-bold text-gray-800 dark:text-gray-200">{groupName}</Text>
                        </View>
                        <View className="flex-row bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                            {displayKeys.map((key, idx) => (
                                <View key={key} className="px-4 py-2" style={{ width: idx === 0 ? 200 : 160 }}>
                                    <Text className="text-[10px] font-bold text-gray-500 uppercase">{key}</Text>
                                </View>
                            ))}
                        </View>
                        {groupItems.map((row, rIdx) => (
                            <View key={rIdx} className={`flex-row border-b border-gray-100 dark:border-gray-800 ${rIdx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-800/50'}`}>
                                {displayKeys.map((key, cIdx) => (
                                    <View key={key} className="px-4 py-2" style={{ width: cIdx === 0 ? 200 : 160 }}>
                                        <Text className={`text-xs text-gray-700 dark:text-gray-300 ${typeof row[key] === 'number' ? 'text-right' : ''}`}>
                                            {renderCell(key, row[key])}
                                        </Text>
                                    </View>
                                ))}
                            </View>
                        ))}
                    </View>
                ))}
            </View>
        );
    };

    // RENDER: FLAT LIST
    const renderFlatTable = () => {
        return (
            <View>
                <View className="flex-row bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                    {keys.map((key, idx) => (
                        <View key={key} className="px-4 py-3" style={{ width: idx === 0 ? 150 : 160 }}>
                            <Text className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wide">{key}</Text>
                        </View>
                    ))}
                </View>
                {data.map((row, idx) => (
                    <View key={idx} className={`flex-row border-b border-gray-100 dark:border-gray-700/50 ${idx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50/50 dark:bg-gray-800/30'}`}>
                        {keys.map((key, colIndex) => (
                            <View key={`${idx}-${key}`} className="px-4 py-3" style={{ width: colIndex === 0 ? 150 : 160 }}>
                                <Text className={`text-sm text-gray-700 dark:text-gray-300 ${typeof row[key] === 'number' ? 'text-right font-variant-numeric' : 'text-left'}`}>
                                    {renderCell(key, row[key])}
                                </Text>
                            </View>
                        ))}
                    </View>
                ))}
            </View>
        );
    };

    return (
        <View className="mt-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
            <View className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/50 flex-row justify-between items-center">
                <View className="flex-row items-center space-x-2">
                    <Text className="text-base">🔢</Text>
                    <Text className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                        {isCrosstab ? `สรุปตาม ${rowKey} (Crosstab)` : parentKey ? `ตารางแยกตาม ${parentKey}` : 'ตารางข้อมูล'}
                    </Text>
                </View>
                <Text className="text-xs text-gray-500 dark:text-gray-400 font-medium bg-white dark:bg-gray-800 px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700">
                    {data.length} รายการ
                </Text>
            </View>

            <ScrollView horizontal showsHorizontalScrollIndicator={true} className="w-full">
                {isCrosstab ? renderCrosstabTable() : (parentKey ? renderGroupedTable() : renderFlatTable())}
            </ScrollView>
        </View>
    );
};
