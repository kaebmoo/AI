
import React from 'react';
import { View, Text, ScrollView, useColorScheme } from 'react-native';

interface DataTableProps {
    data: Record<string, any>[];
}

// Helper: Smart Month Sorting (same as DataChart)
const smartMonthSort = (values: string[]): string[] => {
    const monthNameToNum: Record<string, number> = {
        'มกราคม': 1, 'january': 1, 'jan': 1, 'ม.ค.': 1,
        'กุมภาพันธ์': 2, 'february': 2, 'feb': 2, 'ก.พ.': 2,
        'มีนาคม': 3, 'march': 3, 'mar': 3, 'มี.ค.': 3,
        'เมษายน': 4, 'april': 4, 'apr': 4, 'เม.ย.': 4,
        'พฤษภาคม': 5, 'may': 5, 'พ.ค.': 5,
        'มิถุนายน': 6, 'june': 6, 'jun': 6, 'มิ.ย.': 6,
        'กรกฎาคม': 7, 'july': 7, 'jul': 7, 'ก.ค.': 7,
        'สิงหาคม': 8, 'august': 8, 'aug': 8, 'ส.ค.': 8,
        'กันยายน': 9, 'september': 9, 'sep': 9, 'ก.ย.': 9,
        'ตุลาคม': 10, 'october': 10, 'oct': 10, 'ต.ค.': 10,
        'พฤศจิกายน': 11, 'november': 11, 'nov': 11, 'พ.ย.': 11,
        'ธันวาคม': 12, 'december': 12, 'dec': 12, 'ธ.ค.': 12,
    };

    const extractMonthNum = (val: string): number => {
        const lower = val.toLowerCase().trim();

        // 1. Check Thai/English month name
        if (monthNameToNum[lower] !== undefined) {
            return monthNameToNum[lower];
        }

        // 2. Extract number from "เดือน X", "M/Y" format
        const parts = val.split('/');
        if (parts.length > 1) {
            // Format: "1/2025" - extract first part as month
            const monthNum = parseInt(parts[0]);
            if (!isNaN(monthNum) && monthNum >= 1 && monthNum <= 12) {
                return monthNum;
            }
        }

        const match = val.match(/\d+/);
        if (match) {
            const num = parseInt(match[0]);
            if (num >= 1 && num <= 12) return num;
        }

        // 3. Pure numeric string
        const asNum = parseInt(val);
        if (!isNaN(asNum) && asNum >= 1 && asNum <= 12) {
            return asNum;
        }

        // 4. Fallback
        return 999;
    };

    return [...values].sort((a, b) => {
        const aNum = extractMonthNum(a);
        const bNum = extractMonthNum(b);

        // If both are valid months, sort by month number
        if (aNum !== 999 && bNum !== 999) {
            return aNum - bNum;
        }

        // Fallback to string comparison
        return a.localeCompare(b);
    });
};

export const DataTable = ({ data }: DataTableProps) => {
    const isDark = useColorScheme() === 'dark';

    if (!data || data.length === 0) return null;

    const keys = Object.keys(data[0]);

    // 1. Hierarchy & Dimension Detection
    // Strict exclusion of measure terms from dimensions
    // IMPORTANT: Use word-boundary for 'count' to avoid matching 'account'
    const measurePatterns = ['total', 'revenue', 'amount', 'value', 'price', 'cost', 'profit', 'รายได้', 'ยอดรวม', 'จำนวน', 'expense', 'baht', 'บาท'];
    const wordBoundaryMeasures = ['count']; // These need word-boundary to avoid false positives

    const isMeasure = (k: string) => {
        const lower = k.toLowerCase();
        // Check regular patterns (substring match is fine)
        if (measurePatterns.some(term => lower.includes(term))) {
            return true;
        }
        // Check word-boundary patterns (must be whole word or with underscore)
        return wordBoundaryMeasures.some(term => {
            const regex = new RegExp(`(^|_)${term}($|_)`, 'i');
            return regex.test(lower);
        });
    };

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

    const categoryKeys = dimensionKeys.filter(k => {
        const lower = k.toLowerCase();
        // Exclude time-related columns (both English and Thai)
        const timeKeywords = ['year', 'month', 'date', 'time', 'quarter', 'week', 'day',
            'ปี', 'เดือน', 'วันที่', 'ไตรมาส', 'สัปดาห์', 'วัน', 'เวลา', 'พ.ศ.', 'ค.ศ.'];
        return !timeKeywords.some(t => lower.includes(t));
    });

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
        // OR simply if we have Time + Category (Force Crosstab for cleaner view)
        if (categoryKeys.length > 0 && (timeLabels.length > uniqueTimes.size || (monthKey && yearKey))) {
            isCrosstab = true;
            rowKey = categoryKeys[0]; // Primary category (Province, Group)

            // --- Month Filling Logic ---
            let periods = Array.from(uniqueTimes);

            // 1. Sort periods using smart month sorting
            periods = smartMonthSort(periods);

            // 2. Force Fill 1-12 Months
            // Detect if data looks like "Month" or "Month/Year"
            const sample = periods[0] || '';
            const isMonthYear = sample.includes('/');
            const isNumericMonth = !isNaN(parseInt(sample)) && parseInt(sample) >= 1 && parseInt(sample) <= 12;

            if (data.length > 1 && (isMonthYear || isNumericMonth)) {
                // Determine Year Suffix
                let yearSuffix = '';
                if (isMonthYear) {
                    const parts = sample.split('/');
                    if (parts.length > 1) yearSuffix = `/${parts[1]}`;
                }

                // Create Full Month List
                const allMonths = Array.from({ length: 12 }, (_, i) => {
                    // If original data has leading zero (01), keep it. If (1), keep it.
                    // Simple heuristic: check length of first part
                    const firstPart = isMonthYear ? sample.split('/')[0] : sample;
                    const shouldPad = firstPart.length === 2;
                    const m = shouldPad ? String(i + 1).padStart(2, '0') : String(i + 1);
                    return `${m}${yearSuffix}`;
                });

                // Check if our current data falls within a single year scope (safe to fill)
                // or if we just want to ensure 1-12 are present
                // Simple logic: Merge existing periods with allMonths, keep unique, then sort again
                const merged = new Set([...periods, ...allMonths]);
                periods = smartMonthSort(Array.from(merged));
            }

            periodLabels = periods;

            // 3. Pivot Data
            const rowMap: Record<string, any> = {};

            data.forEach(item => {
                const rVal = String(item[rowKey] || 'Unknown');
                let tLabel = '';

                if (monthKey && yearKey) {
                    const m = String(item[monthKey]);
                    const y = String(item[yearKey]);
                    // Auto-pad month if needed to match labels logic? 
                    // Let's assume data comes clean, but we might need to match format
                    tLabel = `${m}/${y}`;

                    // Try to match period format precisely if mismatch
                    if (!periodLabels.includes(tLabel)) {
                        // Maybe it needs padding? 1 -> 01
                        const padM = m.padStart(2, '0');
                        if (periodLabels.includes(`${padM}/${y}`)) tLabel = `${padM}/${y}`;
                        // Or unpadding? 01 -> 1
                        else if (periodLabels.includes(`${parseInt(m)}/${y}`)) tLabel = `${parseInt(m)}/${y}`;
                    }

                } else if (labelKey) {
                    tLabel = String(item[labelKey]);
                } else if (monthKey) {
                    tLabel = String(item[monthKey]);
                }

                if (!rowMap[rVal]) {
                    rowMap[rVal] = { _rowLabel: rVal };
                }

                if (tLabel && periodLabels.includes(tLabel)) {
                    // Sum up if duplicate (shouldn't happen often in SQL mart but safe to sum)
                    const val = item[valueKey || keys[keys.length - 1]];
                    const numVal = typeof val === 'number' ? val : parseFloat(String(val).replace(/,/g, '')) || 0;

                    rowMap[rVal][tLabel] = (rowMap[rVal][tLabel] || 0) + numVal;
                }
            });

            pivotedRows = Object.values(rowMap);
            // Sort rows by name
            pivotedRows.sort((a, b) => a._rowLabel.localeCompare(b._rowLabel));
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
