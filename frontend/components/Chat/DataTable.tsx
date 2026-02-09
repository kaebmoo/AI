
import React from 'react';
import { View, Text, ScrollView, useColorScheme, TouchableOpacity, Alert, Share, Platform } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';

interface DataTableProps {
    data: Record<string, any>[];
}

// Helper: Smart Month Sorting (Enhanced to handle Years)
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

    const parseDate = (val: string): { year: number, month: number } => {
        let year = 0;
        let month = 999;
        const lower = val.toLowerCase().trim();

        // 1. Try to extract Year (4 digits)
        const yearMatch = val.match(/\d{4}/);
        if (yearMatch) {
            year = parseInt(yearMatch[0]);
            // Convert Thai Year roughly if too high
            if (year > 2500) year -= 543;
        }

        // 2. Try to extract Month
        // Check Name
        for (const [name, num] of Object.entries(monthNameToNum)) {
            if (lower.includes(name)) {
                month = num;
                break;
            }
        }

        // Check M/Y format (1/2025)
        if (month === 999) {
            const parts = val.split(/[\/\-]/);
            if (parts.length > 1) {
                const m = parseInt(parts[0]);
                if (!isNaN(m) && m >= 1 && m <= 12) month = m;
            }
        }

        // Check pure number
        if (month === 999) {
            const m = parseInt(val);
            if (!isNaN(m) && m >= 1 && m <= 12) month = m;
        }

        return { year, month };
    };

    return [...values].sort((a, b) => {
        const da = parseDate(a);
        const db = parseDate(b);

        if (da.year !== db.year && da.year !== 0 && db.year !== 0) {
            return da.year - db.year;
        }
        if (da.month !== db.month) {
            return da.month - db.month;
        }
        return a.localeCompare(b);
    });
};

export const DataTable = ({ data }: DataTableProps) => {
    const isDark = useColorScheme() === 'dark';
    const [sortConfig, setSortConfig] = React.useState<{ key: string | null; direction: 'asc' | 'desc' }>({ key: null, direction: 'asc' });

    if (!data || data.length === 0) return null;

    // Sorting Helper
    const handleSort = (key: string) => {
        let direction: 'asc' | 'desc' = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };

    const sortData = (dataToSort: any[]) => {
        if (!sortConfig.key) return dataToSort;

        return [...dataToSort].sort((a, b) => {
            let valA = a[sortConfig.key!];
            let valB = b[sortConfig.key!];

            // Handle undefined/null (push to bottom usually, or treat as empty)
            if (valA === undefined || valA === null) valA = '';
            if (valB === undefined || valB === null) valB = '';

            // 1. Numeric Sort (including strings with commas like "1,234.56")
            const cleanNumA = typeof valA === 'number' ? valA : parseFloat(String(valA).replace(/,/g, ''));
            const cleanNumB = typeof valB === 'number' ? valB : parseFloat(String(valB).replace(/,/g, ''));

            const isNumA = !isNaN(cleanNumA) && String(valA).trim() !== '';
            const isNumB = !isNaN(cleanNumB) && String(valB).trim() !== '';

            if (isNumA && isNumB) {
                return sortConfig.direction === 'asc' ? cleanNumA - cleanNumB : cleanNumB - cleanNumA;
            }

            // 2. String Sort
            const strA = String(valA).toLowerCase();
            const strB = String(valB).toLowerCase();

            if (strA < strB) {
                return sortConfig.direction === 'asc' ? -1 : 1;
            }
            if (strA > strB) {
                return sortConfig.direction === 'asc' ? 1 : -1;
            }
            return 0;
        });
    };

    // Render Sort Arrow
    const renderSortIcon = (key: string) => {
        if (sortConfig.key !== key) return null;
        return (
            <Text className="text-[10px] text-blue-500 ml-1">
                {sortConfig.direction === 'asc' ? '▲' : '▼'}
            </Text>
        );
    };

    const keys = Object.keys(data[0]);

    // 1. Hierarchy & Dimension Detection
    const FIRST_COL_WIDTH = 180;
    const COL_WIDTH = 160;

    // Strict exclusion of measure terms from dimensions
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
    const quarterKey = keys.find(k => !isMeasure(k) && ['quarter', 'ไตรมาส'].some(term => k.toLowerCase().includes(term)));
    const yearKey = keys.find(k => !isMeasure(k) && ['year', 'ปี', 'พ.ศ.', 'ค.ศ.'].some(term => k.toLowerCase().includes(term)));
    const periodKey = monthKey || quarterKey; // Generic period key (month or quarter)
    const labelKey = periodKey || keys.find(k => !isMeasure(k) && ['date', 'label', 'name', 'time'].some(term => k.toLowerCase().includes(term)));

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
    let colKey = ''; // Column dimension (for Category×Category crosstabs)
    let periodLabels: string[] = [];
    let pivotedRows: any[] = [];

    if (yearKey || periodKey) {
        // Check for duplicate time entries
        // Check for duplicate time entries
        const timeLabels = data.map(item => {
            if (periodKey && yearKey) {
                const p = item[periodKey]; // month or quarter
                const y = item[yearKey];
                if (p && y) return `${p}/${y}`;
                return '';
            }
            if (periodKey) return String(item[periodKey] || '');
            if (labelKey) return String(item[labelKey] || '');
            return '';
        }).filter(t => t && t.trim() !== '' && t !== '/' && !t.includes('undefined') && !t.includes('null'));

        const uniqueTimes = new Set(timeLabels);

        // Only pivot if we have duplicates (meaning multiple categories per time slot)
        // OR simply if we have Time + Category (Force Crosstab for cleaner view)
        if (categoryKeys.length > 0 && (timeLabels.length > uniqueTimes.size || (periodKey && yearKey))) {
            isCrosstab = true;
            rowKey = categoryKeys[0]; // Primary category (Province, Group)
            colKey = quarterKey ? 'ไตรมาส' : monthKey ? 'เดือน' : yearKey ? 'ปี' : 'ช่วงเวลา';

            // --- Month Filling Logic ---
            let periods = Array.from(uniqueTimes);

            // 0. Normalize periods to avoid duplicates (e.g., "1/2025" vs "01/2025")
            const normalizedPeriods = new Map<string, string>();
            periods.forEach(period => {
                const parts = period.split('/');
                if (parts.length === 2) {
                    // Month/Year format - ALWAYS normalize to MM/YYYY (0-padded)
                    const month = parseInt(parts[0]);
                    const year = parts[1];
                    if (!isNaN(month) && month >= 1 && month <= 12) {
                        const normalized = `${String(month).padStart(2, '0')}/${year}`;
                        normalizedPeriods.set(normalized, normalized);
                    } else {
                        normalizedPeriods.set(period, period);
                    }
                } else {
                    // Single value (just month) - ALWAYS normalize to MM (0-padded)
                    const month = parseInt(period);
                    if (!isNaN(month) && month >= 1 && month <= 12) {
                        const normalized = String(month).padStart(2, '0');
                        normalizedPeriods.set(normalized, normalized);
                    } else {
                        normalizedPeriods.set(period, period);
                    }
                }
            });
            periods = Array.from(normalizedPeriods.values());

            // 1. Sort periods using smart month sorting
            periods = smartMonthSort(periods);

            // 2. Detect period type and optionally fill missing periods
            const sample = periods[0] || '';
            const isQuarter = /^Q[1-4]/i.test(sample) || quarterKey;
            const isMonthYear = sample.includes('/') && !isQuarter;
            const isNumericMonth = !isNaN(parseInt(sample)) && parseInt(sample) >= 1 && parseInt(sample) <= 12;

            // For quarters: Sort Q1, Q2, Q3, Q4 properly
            if (isQuarter) {
                periods = periods.sort((a, b) => {
                    // Extract quarter number (Q1 -> 1, Q2/2025 -> 2)
                    const getQNum = (s: string) => {
                        const match = s.match(/Q?(\d)/i);
                        return match ? parseInt(match[1]) : 999;
                    };
                    // Extract year if present
                    const getYear = (s: string) => {
                        const match = s.match(/\/(\d{4})/);
                        return match ? parseInt(match[1]) : 0;
                    };
                    const yearA = getYear(a), yearB = getYear(b);
                    if (yearA !== yearB) return yearA - yearB;
                    return getQNum(a) - getQNum(b);
                });
            }
            // Only fill months if we have less than 12 periods (avoid duplicates)
            else if (data.length > 1 && periods.length < 12 && (isMonthYear || isNumericMonth)) {
                // Determine Year Suffix
                let yearSuffix = '';
                if (isMonthYear) {
                    const parts = sample.split('/');
                    if (parts.length > 1) yearSuffix = `/${parts[1]}`;
                }

                // Create Full Month List (Always Padded)
                const allMonths = Array.from({ length: 12 }, (_, i) => {
                    const m = String(i + 1).padStart(2, '0');
                    return `${m}${yearSuffix}`;
                });

                // Merge existing periods with allMonths, keep unique, then sort again
                const merged = new Set([...periods, ...allMonths]);
                periods = smartMonthSort(Array.from(merged));
            }

            periodLabels = periods;

            // 3. Pivot Data
            const rowMap: Record<string, any> = {};

            data.forEach(item => {
                const rVal = String(item[rowKey] || 'Unknown');
                let tLabel = '';

                if (periodKey && yearKey) {
                    const p = item[periodKey]; // could be month number, quarter (Q1), etc.
                    const y = String(item[yearKey]);

                    if (quarterKey) {
                        // Quarter format: Q1/2025 or just Q1
                        tLabel = `${p}/${y}`;
                    } else if (monthKey) {
                        const m = parseInt(String(p));
                        if (!isNaN(m)) {
                            // Always pad to match column headers
                            const padM = String(m).padStart(2, '0');
                            tLabel = `${padM}/${y}`;
                        } else {
                            tLabel = `${p}/${y}`;
                        }
                    } else {
                        tLabel = `${p}/${y}`;
                    }
                } else if (periodKey) {
                    tLabel = String(item[periodKey]);
                } else if (labelKey) {
                    tLabel = String(item[labelKey]);
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

    // === NEW: Category × Category Crosstab Detection ===
    // If no time-based crosstab, try to detect Category × Category pattern
    if (!isCrosstab && categoryKeys.length >= 2 && valueKey) {
        // Analyze each category's cardinality
        const categoryStats = categoryKeys.map(k => ({
            key: k,
            uniqueCount: new Set(data.map(d => d[k])).size,
            values: Array.from(new Set(data.map(d => String(d[k] || ''))))
        }));

        // Semantic hints for row vs column preference
        // "Owner/Provider/Source" columns should be ROWS (who gave)
        // "User/Recipient/Target" columns should be COLUMNS (who received)
        // Using word-boundary matching to avoid false positives (e.g., "user_id", "total")
        const rowPatterns = [
            /owner/i, /provider/i, /seller/i, /sender/i,
            /ผู้ให้/i, /ผู้ขาย/i, /ต้นทาง/i, /ผู้ส่ง/i
        ];
        const colPatterns = [
            /\buser\b/i, /recipient/i, /buyer/i, /receiver/i,  // \buser\b = whole word only
            /ผู้รับ/i, /ผู้ซื้อ/i, /ปลายทาง/i
        ];

        const getSemanticScore = (key: string): number => {
            // Check row patterns (positive score = prefer as row)
            if (rowPatterns.some(pattern => pattern.test(key))) return 1;
            // Check column patterns (negative score = prefer as column)
            if (colPatterns.some(pattern => pattern.test(key))) return -1;
            return 0;
        };

        // Sort by: 1) semantic preference (row keywords first), 2) unique count (fewer = column)
        categoryStats.sort((a, b) => {
            const semanticDiff = getSemanticScore(b.key) - getSemanticScore(a.key);
            if (semanticDiff !== 0) return semanticDiff;
            return a.uniqueCount - b.uniqueCount;
        });

        // After sorting: first item prefers rows, last prefers columns
        // But we still pick based on cardinality for columns
        const colCandidate = categoryStats.find(c => c.uniqueCount >= 2 && c.uniqueCount <= 20 && getSemanticScore(c.key) <= 0)
                          || categoryStats.find(c => c.uniqueCount >= 2 && c.uniqueCount <= 20);
        // Best row candidate: not the column candidate
        const rowCandidate = categoryStats.find(c => c !== colCandidate && c.uniqueCount >= 1);

        if (colCandidate && rowCandidate) {
            // Check if data has the expected pattern (row × col combinations)
            const expectedCombinations = rowCandidate.uniqueCount * colCandidate.uniqueCount;
            const actualRows = data.length;

            // If actual data is close to expected combinations, it's a good crosstab candidate
            // Allow some flexibility (50% to 150% of expected)
            const isSuitableForCrosstab = actualRows >= expectedCombinations * 0.3 &&
                                          actualRows <= expectedCombinations * 2 &&
                                          colCandidate.uniqueCount <= 20;

            if (isSuitableForCrosstab) {
                isCrosstab = true;
                rowKey = rowCandidate.key;
                colKey = colCandidate.key;
                periodLabels = colCandidate.values.sort((a, b) => a.localeCompare(b, 'th'));

                // Pivot the data
                const rowMap: Record<string, any> = {};
                data.forEach(item => {
                    const rVal = String(item[rowKey] || 'Unknown');
                    const cVal = String(item[colCandidate.key] || '');

                    if (!rowMap[rVal]) {
                        rowMap[rVal] = { _rowLabel: rVal };
                    }

                    if (cVal && periodLabels.includes(cVal)) {
                        const val = item[valueKey];
                        const numVal = typeof val === 'number' ? val : parseFloat(String(val).replace(/,/g, '')) || 0;
                        rowMap[rVal][cVal] = (rowMap[rVal][cVal] || 0) + numVal;
                    }
                });

                pivotedRows = Object.values(rowMap);
                pivotedRows.sort((a, b) => a._rowLabel.localeCompare(b._rowLabel, 'th'));

                console.log(`[DataTable] Category×Category Crosstab: ${rowKey} × ${colCandidate.key}`);
            }
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
        const lowerKey = key.toLowerCase();

        // Don't format IDs, Codes, Years, etc.
        if (['year', 'id', 'code', 'key', 'no.', 'ปี', 'รหัส', 'quarter'].some(t => lowerKey.includes(t)) && key !== '_rowLabel') {
            return String(value);
        }

        // Handle Actual Numbers
        if (typeof value === 'number') {
            return value.toLocaleString('th-TH', { maximumFractionDigits: 2 });
        }

        // Handle String Numbers (e.g. "104323.50")
        if (typeof value === 'string') {
            // Check if it's a pure number (no clean integers like 2024, but floats)
            // Or just try to parse
            const num = parseFloat(value);
            if (!isNaN(num) && /^-?\d+(\.\d+)?$/.test(value)) {
                // It's a valid number string.
                return num.toLocaleString('th-TH', { maximumFractionDigits: 2 });
            }
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
                    <TouchableOpacity onPress={() => handleSort('_rowLabel')} className="px-4 py-3 bg-blue-100/50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex-row items-center justify-between" style={{ width: FIRST_COL_WIDTH }}>
                        <Text className="text-xs font-bold text-gray-700 dark:text-gray-200 uppercase">{rowKey}</Text>
                        {renderSortIcon('_rowLabel')}
                    </TouchableOpacity>
                    {/* Period Columns Header */}
                    {periodLabels.map((period, idx) => (
                        <TouchableOpacity key={period} onPress={() => handleSort(period)} className="px-4 py-3 flex-row items-center justify-center" style={{ width: COL_WIDTH }}>
                            <Text className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase text-center">{period}</Text>
                            {renderSortIcon(period)}
                        </TouchableOpacity>
                    ))}
                </View>

                {/* Data Rows */}
                {sortData(pivotedRows).map((row, rIdx) => (
                    <View key={rIdx} className={`flex-row border-b border-gray-100 dark:border-gray-800 ${rIdx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50/50 dark:bg-gray-800/30'}`}>
                        {/* Frozen First Column Data */}
                        <View className="px-4 py-3 bg-gray-50/80 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700" style={{ width: FIRST_COL_WIDTH }}>
                            <Text className="text-xs font-semibold text-gray-800 dark:text-gray-200" numberOfLines={2}>{row._rowLabel}</Text>
                        </View>
                        {/* Period Data Cells */}
                        {periodLabels.map((period) => (
                            <View key={period} className="px-4 py-3" style={{ width: COL_WIDTH }}>
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
                                <TouchableOpacity key={key} onPress={() => handleSort(key)} className="px-4 py-2 flex-row items-center justify-between" style={{ width: idx === 0 ? FIRST_COL_WIDTH : COL_WIDTH }}>
                                    <Text className="text-[10px] font-bold text-gray-500 uppercase">{key}</Text>
                                    {renderSortIcon(key)}
                                </TouchableOpacity>
                            ))}
                        </View>
                        {sortData(groupItems).map((row, rIdx) => (
                            <View key={rIdx} className={`flex-row border-b border-gray-100 dark:border-gray-800 ${rIdx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-800/50'}`}>
                                {displayKeys.map((key, cIdx) => (
                                    <View key={key} className="px-4 py-2" style={{ width: cIdx === 0 ? FIRST_COL_WIDTH : COL_WIDTH }}>
                                        <Text className={`text-xs text-gray-700 dark:text-gray-300 ${isMeasure(key) || typeof row[key] === 'number' ? 'text-right' : ''}`}>
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
                        <TouchableOpacity key={key} onPress={() => handleSort(key)} className="px-4 py-3 flex-row items-center justify-between" style={{ width: idx === 0 ? FIRST_COL_WIDTH : COL_WIDTH }}>
                            <Text className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wide">{key}</Text>
                            {renderSortIcon(key)}
                        </TouchableOpacity>
                    ))}
                </View>
                {sortData(data).map((row, idx) => (
                    <View key={idx} className={`flex-row border-b border-gray-100 dark:border-gray-700/50 ${idx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50/50 dark:bg-gray-800/30'}`}>
                        {keys.map((key, colIndex) => (
                            <View key={`${idx}-${key}`} className="px-4 py-3" style={{ width: colIndex === 0 ? FIRST_COL_WIDTH : COL_WIDTH }}>
                                <Text className={`text-sm text-gray-700 dark:text-gray-300 ${isMeasure(key) || typeof row[key] === 'number' ? 'text-right font-variant-numeric' : 'text-left'}`}>
                                    {renderCell(key, row[key])}
                                </Text>
                            </View>
                        ))}
                    </View>
                ))}
            </View>
        );
    };

    // CSV Export Function
    const exportToCSV = async () => {
        try {
            let csvContent = '';

            if (isCrosstab) {
                // Crosstab CSV
                const headers = [rowKey, ...periodLabels];
                csvContent = headers.map(h => `"${h}"`).join(',') + '\n';

                pivotedRows.forEach(row => {
                    const rowValues = [row._rowLabel, ...periodLabels.map(period => {
                        const val = row[period];
                        return val !== undefined && val !== null ? val : '-';
                    })];
                    csvContent += rowValues.map(v => `"${v}"`).join(',') + '\n';
                });
            } else if (parentKey) {
                // Grouped Table CSV
                const childKeys = dimensionKeys.filter(k => k !== parentKey);
                const headers = [parentKey, ...childKeys, valueKey].filter((h): h is string => Boolean(h));
                csvContent = headers.map(h => `"${h}"`).join(',') + '\n';

                data.forEach(item => {
                    const rowValues = headers.map(key => {
                        const val = item[key as string];
                        return val !== undefined && val !== null ? val : '-';
                    });
                    csvContent += rowValues.map(v => `"${v}"`).join(',') + '\n';
                });
            } else {
                // Flat Table CSV
                const headers = keys;
                csvContent = headers.map(h => `"${h}"`).join(',') + '\n';

                data.forEach(item => {
                    const rowValues = headers.map(key => {
                        const val = item[key as string];
                        return val !== undefined && val !== null ? val : '-';
                    });
                    csvContent += rowValues.map(v => `"${v}"`).join(',') + '\n';
                });
            }

            const fileName = `data_export_${new Date().getTime()}.csv`;

            // Platform-specific export
            if (Platform.OS === 'web') {
                // Web: Create blob and download
                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement('a');
                const url = URL.createObjectURL(blob);
                link.href = url;
                link.download = fileName;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(url);

                Alert.alert('สำเร็จ', 'ดาวน์โหลดไฟล์ CSV เรียบร้อย');
            } else {
                // Mobile: Save file and share
                const fileUri = FileSystem.documentDirectory + fileName;
                await FileSystem.writeAsStringAsync(fileUri, csvContent, {
                    encoding: FileSystem.EncodingType.UTF8,
                });

                // Check if sharing is available
                const isAvailable = await Sharing.isAvailableAsync();
                if (isAvailable) {
                    await Sharing.shareAsync(fileUri, {
                        mimeType: 'text/csv',
                        dialogTitle: 'Export CSV',
                        UTI: 'public.comma-separated-values-text'
                    });
                    Alert.alert('สำเร็จ', 'ส่งออกข้อมูลเรียบร้อย');
                } else {
                    // Fallback: Copy to clipboard
                    await Clipboard.setStringAsync(csvContent);
                    Alert.alert('คัดลอกแล้ว', 'คัดลอกข้อมูล CSV ไปยังคลิปบอร์ดแล้ว');
                }
            }
        } catch (error: any) {
            console.error('Export error:', error);
            Alert.alert('ข้อผิดพลาด', `ไม่สามารถส่งออกข้อมูลได้: ${error.message}`);
        }
    };

    return (
        <View className="mt-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm">
            <View className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/50 flex-row justify-between items-center">
                <View className="flex-row items-center space-x-2">
                    <Text className="text-base">🔢</Text>
                    <Text className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                        {isCrosstab ? `${rowKey} × ${colKey}` : parentKey ? `ตารางแยกตาม ${parentKey}` : 'ตารางข้อมูล'}
                    </Text>
                </View>
                <View className="flex-row items-center gap-2">
                    <Text className="text-xs text-gray-500 dark:text-gray-400 font-medium bg-white dark:bg-gray-800 px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700">
                        {data.length} รายการ
                    </Text>
                    <TouchableOpacity
                        onPress={exportToCSV}
                        className="p-2 rounded-lg bg-green-50 dark:bg-green-900/30 active:bg-green-100 dark:active:bg-green-900/50"
                    >
                        <Ionicons name="download-outline" size={18} color={isDark ? '#86EFAC' : '#16A34A'} />
                    </TouchableOpacity>
                </View>
            </View>

            <ScrollView horizontal showsHorizontalScrollIndicator={true} className="w-full">
                {isCrosstab ? renderCrosstabTable() : (parentKey ? renderGroupedTable() : renderFlatTable())}
            </ScrollView>
        </View>
    );
};
