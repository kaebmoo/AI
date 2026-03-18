
import React, { useMemo, useState, useEffect } from 'react';
import { View, Text, Dimensions, ScrollView, Modal, TouchableOpacity, Pressable } from 'react-native';
import { BarChart, LineChart, PieChart } from 'react-native-gifted-charts';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { Ionicons } from '@expo/vector-icons';
import type { ChartConfig } from '../../types/chart';
import { resolveChartType } from '../../types/chart';
import { EChartsWrapper, isEChartsAvailable } from '../Chart/EChartsWrapper';
import { buildEChartsOption } from '../../utils/chartDataTransform';

interface DataChartProps {
    data: Record<string, any>[];
    visualization?: string;
    chartConfig?: ChartConfig;  // AI-recommended column configuration
}

// ============================================================
// Chart Type Detection
// ============================================================

// Helper to safely parse numbers (remove commas, %, currency symbols)
const safelyParseNumber = (val: any): number => {
    if (typeof val === 'number') return val;
    if (val === null || val === undefined || val === '') return 0;

    let strVal = String(val).trim();
    // Check for accounting negative format: (123.45) -> -123.45
    const isAccountingNegative = strVal.startsWith('(') && strVal.endsWith(')');

    // Whitelist strategy: Keep only digits, dots, and minus sign.
    strVal = strVal.replace(/[^0-9.-]/g, '');

    const parsed = parseFloat(strVal);
    if (isNaN(parsed)) return 0;

    return isAccountingNegative ? -Math.abs(parsed) : parsed;
};

// Helper: Detect unit from column name
const detectUnitFromColumnName = (columnName?: string): 'baht' | 'thousand' | 'million' | 'billion' | 'auto' => {
    if (!columnName) return 'auto';

    const lower = columnName.toLowerCase();

    // Check for billion indicators
    if (lower.includes('billion') || lower.includes('พันล้าน') || lower.includes('_b_baht') || lower.includes('_billion')) {
        return 'billion';
    }

    // Check for million indicators
    if (lower.includes('million') || lower.includes('ล้าน') ||
        lower.includes('_m_baht') || lower.includes('_million') ||
        lower.endsWith('_m') || lower.includes('_mb')) {
        return 'million';
    }

    // Check for thousand indicators
    if (lower.includes('thousand') || lower.includes('พัน') ||
        lower.includes('_k_baht') || lower.includes('_thousand') ||
        lower.endsWith('_k')) {
        return 'thousand';
    }

    // Auto-detect based on maxValue
    return 'auto';
};

// Helper: Smart number formatting with appropriate unit (บาท, ล้านบาท, พันล้านบาท)
const formatNumberWithUnit = (
    value: number,
    maxValue: number,
    columnName?: string
): { text: string; unit: string } => {
    // Detect unit from column name first
    const detectedUnit = detectUnitFromColumnName(columnName);

    // If unit is pre-determined by column name (value already converted)
    if (detectedUnit === 'billion') {
        return {
            text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'พันล้านบาท'
        };
    }

    if (detectedUnit === 'million') {
        return {
            text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'ล้านบาท'
        };
    }

    if (detectedUnit === 'thousand') {
        return {
            text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'พันบาท'
        };
    }

    // Auto-detect based on max value in dataset (for raw baht values)
    const absMax = Math.abs(maxValue);
    if (absMax >= 1_000_000) {
        // As requested, anything >= 1M is represented in millions
        return {
            text: (value / 1_000_000).toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'ล้านบาท'
        };
    } else {
        // บาท (Baht)
        return {
            text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'บาท'
        };
    }
};

// Helper: Smart Month Sorting (handles Thai names, "เดือน X", numeric)
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

        // 2. Extract number from "เดือน X" or similar patterns
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

        // 4. Fallback: return large number to push to end
        return 999;
    };

    return [...values].sort((a, b) => {
        const numA = extractMonthNum(a);
        const numB = extractMonthNum(b);
        return numA - numB;
    });
};

type ChartMode =
    | 'grouped_bar'      // Comparison: Same categories across different periods (e.g., dept revenue month 8 vs 9)
    | 'stacked_bar'      // Composition: Parts of a whole
    | 'horizontal_bar'   // Ranking: Many categories
    | 'vertical_bar'     // Few categories comparison
    | 'line'             // Time series trend
    | 'multi_line'       // Multiple series over time
    | 'pie_chart'        // Proportional (Pie)
    | 'donut_chart';     // Proportional (Donut)

interface ChartAnalysis {
    mode: ChartMode;
    categoryKey: string;      // X-axis grouping (e.g., department)
    seriesKey: string;        // Color grouping (e.g., month)
    measureKey: string;       // Y-axis value (e.g., revenue)
    seriesValues: string[];   // Unique series (e.g., ['8', '9'])
    categories: string[];     // Unique categories
    hasDifferenceColumn: boolean;
    differenceKey?: string;
    percentDiffKey?: string;
}

export const DataChart = ({ data, visualization, chartConfig }: DataChartProps) => {
    const colorScheme = useColorScheme();
    const isDark = colorScheme === 'dark';
    const screenWidth = Dimensions.get('window').width;
    const chartWidth = Math.min(screenWidth - 64, 500);

    // Full screen modal state
    const [isFullScreen, setIsFullScreen] = useState(false);

    // ============================================================
    // ECharts hooks — MUST be called before any early returns (React rules of hooks)
    // These hooks are independent of `analysis` — they only use props.
    // ============================================================
    const resolvedType = resolveChartType(visualization, chartConfig);
    const [activeType, setActiveType] = useState<string | null>(resolvedType);

    useEffect(() => {
        const newType = resolveChartType(visualization, chartConfig);
        if (newType) setActiveType(newType);
    }, [visualization, chartConfig?.suggested_type]);

    const availableTypes = chartConfig?.available_types ?? [];
    const showToolbar = availableTypes.length > 1;

    const echartsOption = useMemo(() => {
        if (!isEChartsAvailable()) return null;
        const overrideConfig = activeType
            ? { ...chartConfig, suggested_type: activeType }
            : chartConfig;
        const opt = buildEChartsOption(data, visualization, overrideConfig, isDark);
        return opt;
    }, [data, visualization, chartConfig, activeType, isDark]);

    const echartsOptionFullscreen = useMemo(() => {
        if (!echartsOption) return null;
        const opt = { ...(echartsOption as any) };
        delete opt.title;
        if (opt.grid) opt.grid = { ...opt.grid, top: '8%' };
        return opt;
    }, [echartsOption]);

    // ============================================================
    // 1. Analyze Data Structure (AI-first, fallback to pattern detection)
    // ============================================================

    const analysis = useMemo((): ChartAnalysis | null => {
        if (!data || data.length < 1) return null;

        // ============================================================
        // Skip chart for non-chart visualizations
        // ============================================================
        if (visualization === 'table' || visualization === 'single_value') {
            return null;
        }

        const keys = Object.keys(data[0]);

        // ============================================================
        // Check if data has any numerical columns (required for charts)
        // ============================================================
        const hasNumericalData = keys.some(key => {
            const sampleValue = data[0][key];
            const cleanVal = String(sampleValue).replace(/[^0-9.-]/g, '');
            return typeof sampleValue === 'number' ||
                (typeof sampleValue === 'string' && cleanVal.length > 0 && !isNaN(parseFloat(cleanVal)));
        });

        if (!hasNumericalData) {
            return null;
        }

        // ============================================================
        // AI-RECOMMENDED CONFIG (Priority) - No more hardcoded patterns!
        // ============================================================
        if (chartConfig?.category_column && chartConfig?.measure_column) {
            const categoryKey = chartConfig.category_column;
            const measureKey = chartConfig.measure_column;
            const seriesKey = chartConfig.series_column || '';

            // Normalize keys for case-insensitive matching
            const lowerKeys = keys.map(k => k.toLowerCase());
            const findKeyCaseInsensitive = (target: string) => {
                if (!target) return undefined;
                const idx = lowerKeys.indexOf(target.toLowerCase());
                return idx !== -1 ? keys[idx] : undefined;
            };

            const matchedCategoryKey = findKeyCaseInsensitive(categoryKey);
            const matchedMeasureKey = findKeyCaseInsensitive(measureKey);

            // Verify columns exist in data (using matched keys)
            if (!matchedCategoryKey || !matchedMeasureKey) {
                console.warn(`AI columns not found: ${categoryKey}, ${measureKey}. keys: ${keys.join(', ')}`);
            } else {
                // Use the actual keys from data
                let finalCategoryKey = matchedCategoryKey;
                const finalMeasureKey = matchedMeasureKey;
                let finalSeriesKey = seriesKey ? findKeyCaseInsensitive(seriesKey) || '' : '';

                // ============================================================
                // CRITICAL FIX: Validate AI Config - Swap if Time is in Series instead of Category
                // ============================================================
                if (finalSeriesKey) {
                    const timeKeywords = ['month', 'year', 'date', 'quarter', 'week', 'day', 'time',
                        'เดือน', 'ปี', 'วันที่', 'ไตรมาส', 'สัปดาห์', 'วัน', 'เวลา'];

                    const isCategoryTime = timeKeywords.some(t => finalCategoryKey.toLowerCase().includes(t));
                    const isSeriesTime = timeKeywords.some(t => finalSeriesKey.toLowerCase().includes(t));

                    // If Series is Time but Category is NOT Time -> SWAP them
                    if (isSeriesTime && !isCategoryTime) {
                        [finalCategoryKey, finalSeriesKey] = [finalSeriesKey, finalCategoryKey];
                    }
                }

                // Build categories
                const categoryCounts: Record<string, number> = {};
                data.forEach(row => {
                    const cat = String(row[finalCategoryKey] || '');
                    categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
                });
                let categories = Object.keys(categoryCounts);

                // CRITICAL: Sort categories if it's a time column (after potential swap)
                // Enhanced detection: Check if values look like months (1-12), not just column names
                const looksLikeMonths = categories.length > 0 &&
                    categories.filter(c => !isNaN(parseInt(c))).length > 0 && // Has numeric values
                    categories.every(c => {
                        const num = parseInt(c);
                        return isNaN(num) || (num >= 1 && num <= 12); // All numeric values are 1-12
                    });

                const isCategoryTimeColumn = ['month', 'year', 'date', 'quarter', 'week', 'เดือน', 'ปี', 'วันที่', 'ไตรมาส'].some(t =>
                    finalCategoryKey.toLowerCase().includes(t)
                ) || looksLikeMonths; // Add value-based detection

                // Helper: Check if categories are numeric
                const isNumericCategories = categories.length > 0 && categories.every(c => !isNaN(parseFloat(c)) && isFinite(parseFloat(c)));

                if (isCategoryTimeColumn) {
                    categories = smartMonthSort(categories);
                } else if (isNumericCategories) {
                    categories.sort((a, b) => parseFloat(a) - parseFloat(b));
                }

                const hasRepeatedCategories = Object.values(categoryCounts).some(count => count > 1);

                // Build series values if series column provided
                let seriesValues: string[] = [];
                if (finalSeriesKey) {
                    const uniqueValues = Array.from(new Set(data.map(d => String(d[finalSeriesKey]))));

                    // Detect if this is a month/time column
                    const isMonthColumn = ['month', 'เดือน', 'quarter', 'ไตรมาส'].some(t =>
                        finalSeriesKey.toLowerCase().includes(t)
                    );

                    // Use smart month sorting for time columns, numeric for others
                    seriesValues = isMonthColumn
                        ? smartMonthSort(uniqueValues)
                        : uniqueValues.sort((a, b) => {
                            const aNum = parseFloat(a);
                            const bNum = parseFloat(b);
                            return !isNaN(aNum) && !isNaN(bNum) ? aNum - bNum : a.localeCompare(b);
                        });
                }

                // Detect difference columns
                const differenceKey = keys.find(k => {
                    const lower = k.toLowerCase();
                    return (lower.includes('diff') || lower.includes('ผลต่าง') || lower.includes('change')) &&
                        !lower.includes('percent') && !lower.includes('%');
                });
                const percentDiffKey = keys.find(k => {
                    const lower = k.toLowerCase();
                    return (lower.includes('%') || lower.includes('percent') || lower.includes('เปอร์เซ็นต์'));
                });

                // Determine mode from AI visualization recommendation
                // Determine mode from AI visualization recommendation
                let mode: ChartMode = 'vertical_bar';
                if ((visualization === 'grouped_bar' && finalSeriesKey) || (finalSeriesKey && seriesValues.length >= 2 && hasRepeatedCategories)) {
                    mode = 'grouped_bar';
                } else if (visualization === 'grouped_bar' && !finalSeriesKey) {
                    mode = 'vertical_bar';
                } else if (visualization === 'stacked_bar') {
                    mode = 'stacked_bar';
                } else if (visualization === 'line_chart') {
                    mode = categories.length > 1 ? 'multi_line' : 'line';
                } else if (visualization === 'pie_chart') {
                    mode = 'pie_chart';
                } else if (visualization === 'donut_chart') {
                    mode = 'donut_chart';
                } else if (visualization === 'horizontal_bar') {
                    mode = 'horizontal_bar';
                } else if (!visualization && categories.length > 5) {
                    // Only auto-switch to horizontal if NO explicit visualization is requested
                    mode = 'horizontal_bar';
                } else if (visualization === 'bar_chart') {
                    mode = 'vertical_bar';
                }

                return {
                    mode,
                    categoryKey: finalCategoryKey,
                    seriesKey: finalSeriesKey,
                    measureKey: finalMeasureKey,
                    seriesValues,
                    categories,
                    hasDifferenceColumn: !!(differenceKey || percentDiffKey),
                    differenceKey,
                    percentDiffKey
                };
            }
        }

        // ============================================================
        // FALLBACK: Pattern-based detection (legacy support)
        // ============================================================

        // ============================================================
        // Detect Wide Format (Pivoted) - Multiple measure columns for periods
        // e.g., revenue_august, revenue_september, revenue_8, revenue_9
        // ============================================================

        const monthNames: Record<string, string> = {
            'january': '1', 'jan': '1', 'ม.ค.': '1', 'มกราคม': '1',
            'february': '2', 'feb': '2', 'ก.พ.': '2', 'กุมภาพันธ์': '2',
            'march': '3', 'mar': '3', 'มี.ค.': '3', 'มีนาคม': '3',
            'april': '4', 'apr': '4', 'เม.ย.': '4', 'เมษายน': '4',
            'may': '5', 'พ.ค.': '5', 'พฤษภาคม': '5',
            'june': '6', 'jun': '6', 'มิ.ย.': '6', 'มิถุนายน': '6',
            'july': '7', 'jul': '7', 'ก.ค.': '7', 'กรกฎาคม': '7',
            'august': '8', 'aug': '8', 'ส.ค.': '8', 'สิงหาคม': '8',
            'september': '9', 'sep': '9', 'ก.ย.': '9', 'กันยายน': '9',
            'october': '10', 'oct': '10', 'ต.ค.': '10', 'ตุลาคม': '10',
            'november': '11', 'nov': '11', 'พ.ย.': '11', 'พฤศจิกายน': '11',
            'december': '12', 'dec': '12', 'ธ.ค.': '12', 'ธันวาคม': '12',
        };

        // Detect pivoted measure columns (revenue_august, revenue_september, etc.)
        const pivotedMeasureColumns: { key: string; period: string; periodNum: number }[] = [];

        keys.forEach(k => {
            const lower = k.toLowerCase();

            // Skip non-measure columns
            if (lower.includes('diff') || lower.includes('percent') || lower.includes('%') || lower.includes('change')) {
                return;
            }

            // Check for month name in column
            for (const [monthName, monthNum] of Object.entries(monthNames)) {
                if (lower.includes(monthName.toLowerCase())) {
                    pivotedMeasureColumns.push({
                        key: k,
                        period: monthName,
                        periodNum: parseInt(monthNum)
                    });
                    return;
                }
            }

            // Check for month number suffix: revenue_8, revenue_9, etc.
            const monthSuffixMatch = k.match(/_(\d{1,2})$/);
            if (monthSuffixMatch) {
                const monthNum = parseInt(monthSuffixMatch[1]);
                if (monthNum >= 1 && monthNum <= 12) {
                    pivotedMeasureColumns.push({
                        key: k,
                        period: `เดือน ${monthNum}`,
                        periodNum: monthNum
                    });
                }
            }
        });

        // Sort by period number
        pivotedMeasureColumns.sort((a, b) => a.periodNum - b.periodNum);

        // Detect difference and percent columns
        const differenceKey = keys.find(k => {
            const lower = k.toLowerCase();
            return (lower.includes('diff') || lower.includes('ผลต่าง') || lower.includes('change')) &&
                !lower.includes('percent') && !lower.includes('%');
        });

        const percentDiffKey = keys.find(k => {
            const lower = k.toLowerCase();
            return (lower.includes('%') || lower.includes('percent') || lower.includes('เปอร์เซ็นต์'));
        });

        // ============================================================
        // Wide Format Detected - Use Pivoted Mode
        // ============================================================

        if (pivotedMeasureColumns.length >= 2) {
            // Find category key (non-numeric, non-measure column)
            const categoryKey = keys.find(k => {
                const lower = k.toLowerCase();
                const isPivotCol = pivotedMeasureColumns.some(p => p.key === k);
                const isDiffCol = lower.includes('diff') || lower.includes('percent') || lower.includes('%');
                return !isPivotCol && !isDiffCol && typeof data[0][k] === 'string';
            }) || keys[0];

            const categories = data.map(row => String(row[categoryKey] || 'Unknown'));
            const seriesValues = pivotedMeasureColumns.map(p => p.period);

            return {
                mode: 'grouped_bar',
                categoryKey,
                seriesKey: '__pivoted__', // Special marker for wide format
                measureKey: pivotedMeasureColumns[0].key, // Primary measure
                seriesValues,
                categories,
                hasDifferenceColumn: !!(differenceKey || percentDiffKey),
                differenceKey,
                percentDiffKey,
                // Store pivoted columns info for rendering
                _pivotedColumns: pivotedMeasureColumns,
            } as ChartAnalysis & { _pivotedColumns: typeof pivotedMeasureColumns };
        }

        // ============================================================
        // Long Format Detection (Original Logic)
        // ============================================================

        const monthKey = keys.find(k =>
            ['month', 'เดือน'].some(term => k.toLowerCase().includes(term)) &&
            !k.toLowerCase().includes('diff')
        );
        const yearKey = keys.find(k =>
            ['year', 'ปี'].some(term => k.toLowerCase().includes(term))
        );

        // Category keys (for grouping)
        const categoryKeys = keys.filter(k => {
            const lower = k.toLowerCase();
            return ['department', 'ฝ่าย', 'division', 'สายงาน', 'group', 'กลุ่ม', 'province', 'จังหวัด', 'product', 'สินค้า', 'service', 'บริการ', 'name', 'category', 'account', 'หมวด', 'บัญชี', 'segment', 'type', 'ประเภท'].some(term => lower.includes(term)) &&
                !lower.includes('diff') && !lower.includes('percent');
        }).sort((a, b) => {
            // Prefer keys containing 'name' or 'desc' over 'id' or 'code'
            const aLower = a.toLowerCase();
            const bLower = b.toLowerCase();
            const aHasName = aLower.includes('name') || aLower.includes('create') || aLower.includes('desc');
            const bHasName = bLower.includes('name') || bLower.includes('create') || bLower.includes('desc');
            const aHasCode = aLower.includes('code') || aLower.includes('id');
            const bHasCode = bLower.includes('code') || bLower.includes('id');

            if (aHasName && !bHasName) return -1;
            if (!aHasName && bHasName) return 1;
            if (!aHasCode && bHasCode) return -1;
            if (aHasCode && !bHasCode) return 1;
            return 0;
        });

        // Value/Measure keys (use word boundary matching to avoid false positives like "account" matching "count")
        const measurePatterns = ['total', 'revenue', 'amount', 'sum', 'avg', 'value', 'price', 'cost', 'profit', 'รายได้', 'ยอดรวม', 'จำนวน', 'expense', 'ค่าใช้จ่าย', 'งบประมาณ', 'budget'];
        // Patterns that need word boundary (to avoid "account" matching "count")
        const wordBoundaryPatterns = ['count'];

        const measureKeys = keys.filter(k => {
            const lower = k.toLowerCase();
            // Skip diff/percent/change columns
            if (lower.includes('diff') || lower.includes('percent') || lower.includes('change')) {
                return false;
            }
            // Check regular patterns (substring match is fine)
            if (measurePatterns.some(term => lower.includes(term))) {
                return true;
            }
            // Check word-boundary patterns (must be whole word or with underscore)
            return wordBoundaryPatterns.some(term => {
                const regex = new RegExp(`(^|_)${term}($|_)`, 'i');
                return regex.test(lower);
            });
        });

        if (measureKeys.length === 0) return null;

        const measureKey = measureKeys[0];
        const categoryKey = categoryKeys[0] || keys.find(k => typeof data[0][k] === 'string' && !measureKeys.includes(k)) || keys[0];

        // Check if same category appears multiple times with different months
        const categoryCounts: Record<string, number> = {};
        data.forEach(row => {
            const cat = String(row[categoryKey] || '');
            categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
        });

        const hasRepeatedCategories = Object.values(categoryCounts).some(count => count > 1);
        let uniqueCategories = Object.keys(categoryCounts);

        // Sort categories if it's a time/month column
        const isCategoryTimeCol = ['month', 'year', 'date', 'quarter', 'week', 'เดือน', 'ปี', 'วันที่', 'ไตรมาส'].some(t =>
            categoryKey.toLowerCase().includes(t)
        );
        if (isCategoryTimeCol && uniqueCategories.length > 0) {
            uniqueCategories = smartMonthSort(uniqueCategories);
        }

        // Detect series key (what differentiates repeated categories)
        let seriesKey = '';
        let seriesValues: string[] = [];

        if (hasRepeatedCategories && monthKey) {
            seriesKey = monthKey;
            const uniqueMonths = Array.from(new Set(data.map(d => String(d[monthKey]))));
            seriesValues = smartMonthSort(uniqueMonths);
        } else if (hasRepeatedCategories && yearKey) {
            seriesKey = yearKey;
            seriesValues = Array.from(new Set(data.map(d => String(d[yearKey])))).sort();
        }

        const determineChartMode = (): ChartMode => {
            let mode: ChartMode = 'vertical_bar'; // Default

            if (seriesKey && seriesValues.length >= 2 && hasRepeatedCategories && uniqueCategories.length > 1) {
                // Comparison mode: Same departments across different months (Must have > 1 category to compare)
                mode = 'grouped_bar';
            } else if (monthKey || yearKey) {
                // Time series
                mode = uniqueCategories.length > 1 ? 'multi_line' : 'line';
            } else if (uniqueCategories.length > 5) {
                // Many categories - use horizontal for readability
                mode = 'horizontal_bar';
            }
            return mode;
        };

        // ============================================================
        // 4. Force AI Recommendation
        // ============================================================
        let forcedMode: ChartMode | undefined;
        if (visualization) {
            if (visualization === 'bar_chart') forcedMode = 'vertical_bar';
            else if (visualization === 'horizontal_bar') forcedMode = 'horizontal_bar';
            else if (visualization === 'line_chart') forcedMode = 'line';
            else if (visualization === 'line_chart') forcedMode = 'line';
            else if (visualization === 'pie_chart') forcedMode = 'pie_chart';
            else if (visualization === 'donut_chart') forcedMode = 'donut_chart';
        }

        // ============================================================
        // 5. Determine Chart Mode
        // ============================================================

        return {
            mode: forcedMode || determineChartMode(),
            categoryKey,
            seriesKey: seriesKey || '',
            measureKey,
            seriesValues,
            categories: uniqueCategories,
            hasDifferenceColumn: !!differenceKey,
            differenceKey,
            percentDiffKey
        };
    }, [data, visualization, chartConfig]);

    // ============================================================
    // ECharts Rendering Path (BEFORE analysis null-guard)
    // ECharts uses echartsOption which is computed independently of analysis.
    // When visualization='table', analysis is null but echartsOption may be valid.
    // ============================================================

    /** Thai labels for chart type toolbar */
    const CHART_LABELS: Record<string, string> = {
        vertical_bar: 'แท่ง',
        horizontal_bar: 'แท่งแนวนอน',
        bar_chart: 'แท่ง',
        line: 'เส้น',
        line_chart: 'เส้น',
        multi_line: 'หลายเส้น',
        pie_chart: 'วงกลม',
        donut_chart: 'โดนัท',
        grouped_bar: 'แท่งกลุ่ม',
        stacked_bar: 'แท่งสะสม',
        stacked_bar_100: '100% สะสม',
        area: 'พื้นที่',
        stacked_area: 'พื้นที่สะสม',
        waterfall: 'น้ำตก',
        scatter: 'กระจาย',
        mixed_bar_line: 'ผสม',
        treemap: 'แผนผัง',
    };

    // Toolbar renderer — shared between normal and fullscreen views (ECharts path)
    const renderEChartsToolbar = (containerStyle?: any) => (
        showToolbar ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={containerStyle}>
                <View style={{ flexDirection: 'row', gap: 6, paddingHorizontal: 2 }}>
                    {availableTypes.map((type) => {
                        const isActive = type === activeType;
                        return (
                            <TouchableOpacity
                                key={type}
                                onPress={() => setActiveType(type)}
                                style={{
                                    paddingHorizontal: 12,
                                    paddingVertical: 6,
                                    borderRadius: 16,
                                    backgroundColor: isActive ? '#3B82F6' : (isDark ? '#374151' : '#F3F4F6'),
                                    borderWidth: isActive ? 0 : 1,
                                    borderColor: isDark ? '#4B5563' : '#E5E7EB',
                                }}
                            >
                                <Text style={{
                                    fontSize: 12,
                                    fontWeight: isActive ? '600' : '400',
                                    color: isActive ? '#FFFFFF' : (isDark ? '#D1D5DB' : '#4B5563'),
                                }}>
                                    {CHART_LABELS[type] || type}
                                </Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>
            </ScrollView>
        ) : null
    );

    // If ECharts is available and we have a valid option, render chart
    // This runs BEFORE the analysis null-guard so charts show even for visualization='table'
    if (isEChartsAvailable() && echartsOption) {
        return (
            <View className="my-4 p-4 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm"
                style={{ width: '100%' }}>

                {/* Header: Title + Expand Button */}
                <View style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 8,
                }}>
                    <Text className="text-sm font-semibold text-gray-700 dark:text-gray-200"
                        style={{ flex: 1, flexShrink: 1 }} numberOfLines={2}>
                        {chartConfig?.title || ''}
                    </Text>
                    <TouchableOpacity
                        onPress={() => setIsFullScreen(true)}
                        style={{
                            padding: 6,
                            borderRadius: 6,
                            backgroundColor: isDark ? '#374151' : '#F3F4F6',
                            flexShrink: 0,
                            marginLeft: 8,
                        }}
                        activeOpacity={0.7}
                    >
                        <Ionicons name="expand-outline" size={18} color={isDark ? '#D1D5DB' : '#6B7280'} />
                    </TouchableOpacity>
                </View>

                {/* Chart Type Toolbar */}
                {renderEChartsToolbar({ marginBottom: 8 })}

                {/* ECharts Render */}
                <EChartsWrapper
                    option={echartsOption}
                    height={400}
                    width={Math.min(screenWidth - 48, 800)}
                />

                {/* Warning */}
                {chartConfig?.warning && (
                    <Text className="text-xs text-amber-600 dark:text-amber-400 text-center mt-2">
                        {chartConfig.warning}
                    </Text>
                )}

                {/* Full Screen Modal */}
                <Modal
                    visible={isFullScreen}
                    animationType="slide"
                    transparent={false}
                    onRequestClose={() => setIsFullScreen(false)}
                >
                    <View style={{ flex: 1, backgroundColor: isDark ? '#111827' : '#FFFFFF', paddingTop: 48 }}>
                        {/* Modal Header — compact */}
                        <View style={{
                            flexDirection: 'row',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            paddingHorizontal: 16,
                            paddingBottom: 8,
                            borderBottomWidth: 1,
                            borderBottomColor: isDark ? '#374151' : '#E5E7EB',
                        }}>
                            <Text style={{
                                flex: 1,
                                fontSize: 15,
                                fontWeight: '600',
                                color: isDark ? '#F3F4F6' : '#1F2937',
                            }} numberOfLines={2}>
                                {chartConfig?.title || ''}
                            </Text>
                            <TouchableOpacity
                                onPress={() => setIsFullScreen(false)}
                                style={{
                                    padding: 6,
                                    borderRadius: 6,
                                    backgroundColor: isDark ? '#374151' : '#F3F4F6',
                                    marginLeft: 8,
                                }}
                            >
                                <Ionicons name="close" size={20} color={isDark ? '#E5E7EB' : '#374151'} />
                            </TouchableOpacity>
                        </View>

                        {/* Toolbar in Modal — compact */}
                        <View style={{ paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4 }}>
                            {renderEChartsToolbar()}
                        </View>

                        {/* Full Screen ECharts — use option WITHOUT title */}
                        <View style={{ flex: 1, paddingHorizontal: 8, paddingTop: 4 }}>
                            <EChartsWrapper
                                option={echartsOptionFullscreen || echartsOption}
                                height={screenWidth > 768 ? 580 : 460}
                                width={screenWidth - 16}
                            />
                        </View>

                        {/* Warning in fullscreen */}
                        {chartConfig?.warning && (
                            <Text style={{
                                fontSize: 11,
                                color: '#D97706',
                                textAlign: 'center',
                                paddingBottom: 12,
                                paddingHorizontal: 16,
                            }}>
                                {chartConfig.warning}
                            </Text>
                        )}
                    </View>
                </Modal>
            </View>
        );
    }

    if (!analysis) {
        return null;
    }

    // ============================================================
    // 2. Color Utilities
    // ============================================================

    // Imported from constants/chartColors.ts — kept as local ref for gifted-charts path
    const SERIES_COLORS = require('../../constants/chartColors').SERIES_COLORS as string[];

    const stringToColor = (str: string, index?: number) => {
        if (typeof index === 'number' && index < SERIES_COLORS.length) {
            return SERIES_COLORS[index];
        }
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
        }
        const hue = Math.abs(hash % 360);
        return `hsl(${hue}, 70%, 50%)`;
    };

    const formatYLabel = (val: string) => {
        const num = safelyParseNumber(val);
        const abs = Math.abs(num);
        if (abs >= 1_000_000) return (num / 1_000_000).toLocaleString('th-TH', { maximumFractionDigits: 2 }) + ' ลบ.';
        if (abs >= 1_000) return (num / 1_000).toLocaleString('th-TH', { maximumFractionDigits: 2 }) + 'k';
        return num.toLocaleString('th-TH', { maximumFractionDigits: 2 });
    };

    const truncateLabel = (label: string, maxLen: number = 12) => {
        return label.length > maxLen ? label.slice(0, maxLen) + '...' : label;
    };

    // ============================================================
    // 3. Render Grouped Bar Chart (Comparison Mode)
    // ============================================================

    // Helper: Smart Tooltip Position
    // Defined here to be accessible by both Grouped and Single Chart logic
    const calculateTooltipStyle = (
        index: number,
        totalItems: number,
        isHorizontalChart: boolean,
        isHighValue: boolean
    ) => {
        const style: any = {
            position: 'absolute',
            zIndex: 1000,
            minWidth: 140,
            maxWidth: 200,
            padding: 8,
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 2 },
            shadowOpacity: 0.25,
            shadowRadius: 3.84,
            elevation: 5,
        };

        if (isHorizontalChart) {
            // Horizontal Bar Chart (Sideways Bars)
            // If high value (long bar), tooltip should be LEFT of the bar end to avoid right overflow
            if (isHighValue) {
                // Shift strictly LEFT for any bar longer than 30% of max
                style.left = -160;
            } else {
                style.left = 10; // Shift forward right
            }
            style.top = -20; // Center vertically relative to bar
        } else {
            // Vertical Bar Chart (Standard)
            const isFarRight = index > totalItems * 0.7;
            const isFarLeft = index < totalItems * 0.2;

            if (isFarRight) style.right = -20;
            else if (isFarLeft) style.left = -10;
            else style.left = -70; // Center

            // Vertical Flip
            if (isHighValue) style.top = 10; // Flip down
            else style.bottom = 10; // Flip up
        }
        return style;
    };

    // ============================================================
    // 3. Process Data for Chart
    // ============================================================

    const groupedChartData = useMemo(() => {
        if (!analysis || !data) return [];

        const groupedData: Record<string, Record<string, number>> = {};
        const diffData: Record<string, { diff?: number; pctDiff?: number }> = {};

        // Check if this is Wide Format (pivoted columns)
        const isPivotedFormat = analysis.seriesKey === '__pivoted__';
        const pivotedColumns = (analysis as any)._pivotedColumns as { key: string; period: string; periodNum: number }[] | undefined;

        if (isPivotedFormat && pivotedColumns) {
            // Wide Format: Read values from pivoted columns
            data.forEach(row => {
                const category = String(row[analysis.categoryKey] || 'Unknown');

                if (!groupedData[category]) {
                    groupedData[category] = {};
                }

                // Read value from each pivoted column
                pivotedColumns.forEach(col => {
                    groupedData[category][col.period] = safelyParseNumber(row[col.key]);
                });

                // Store difference data
                if (!diffData[category]) diffData[category] = {};
                if (analysis.differenceKey && row[analysis.differenceKey] !== undefined) {
                    diffData[category].diff = safelyParseNumber(row[analysis.differenceKey]);
                }
                if (analysis.percentDiffKey && row[analysis.percentDiffKey] !== undefined) {
                    diffData[category].pctDiff = safelyParseNumber(row[analysis.percentDiffKey]);
                }
            });
        } else {
            // Long Format: Original logic
            data.forEach(row => {
                const category = String(row[analysis.categoryKey] || 'Unknown');
                const series = String(row[analysis.seriesKey] || '');
                const value = safelyParseNumber(row[analysis.measureKey]);

                if (!groupedData[category]) {
                    groupedData[category] = {};
                }
                groupedData[category][series] = value;

                // Store difference data
                if (analysis.differenceKey || analysis.percentDiffKey) {
                    if (!diffData[category]) diffData[category] = {};
                    if (analysis.differenceKey && row[analysis.differenceKey] !== undefined) {
                        diffData[category].diff = safelyParseNumber(row[analysis.differenceKey]);
                    }
                    if (analysis.percentDiffKey && row[analysis.percentDiffKey] !== undefined) {
                        diffData[category].pctDiff = safelyParseNumber(row[analysis.percentDiffKey]);
                    }
                }
            });
        }

        // Get actual categories from grouped data (important for Wide Format)
        // CRITICAL FIX: Use analysis.categories (already sorted) instead of Object.keys
        let actualCategories = analysis.categories || Object.keys(groupedData);

        // If categories are months/time, ensure they're sorted
        // Enhanced detection: Check if values look like months (1-12), not just column names
        const looksLikeMonths = actualCategories.length > 0 &&
            actualCategories.filter(c => !isNaN(parseInt(c))).length > 0 && // Has numeric values
            actualCategories.every(c => {
                const num = parseInt(c);
                return isNaN(num) || (num >= 1 && num <= 12); // All numeric values are 1-12
            });

        const isCategoryTimeColumn = ['month', 'year', 'date', 'quarter', 'week', 'เดือน', 'ปี', 'วันที่', 'ไตรมาส'].some(t =>
            analysis.categoryKey.toLowerCase().includes(t)
        ) || looksLikeMonths; // Add value-based detection

        // Check numeric
        const isNumericCategories = actualCategories.length > 0 && actualCategories.every(c => !isNaN(parseFloat(c)) && isFinite(parseFloat(c)));

        if (isCategoryTimeColumn && actualCategories.length > 0) {
            actualCategories = smartMonthSort(actualCategories);
        } else if (isNumericCategories && actualCategories.length > 0) {
            actualCategories.sort((a, b) => parseFloat(a) - parseFloat(b));
        }

        // Get actual series values (periods)
        const actualSeriesValues = isPivotedFormat && pivotedColumns
            ? pivotedColumns.map(col => col.period)
            : analysis.seriesValues;

        // Build stacked data for grouped bars
        // react-native-gifted-charts uses stackData for grouped bars
        const stackData = actualCategories.map(category => {
            const stacks = actualSeriesValues.map((series, idx) => ({
                value: groupedData[category]?.[series] || 0,
                color: SERIES_COLORS[idx % SERIES_COLORS.length],
                marginBottom: 2,
            }));

            return {
                stacks,
                label: truncateLabel(category, 10),
                fullLabel: category,
                diffInfo: diffData[category],
            };
        });

        // Calculate max value for scaling
        const maxValue = Math.max(
            ...Object.values(groupedData).flatMap(g => Object.values(g))
        );

        // Tooltip renderer
        const renderGroupedTooltip = (item: any, index: number) => {
            if (!item) return null;

            const category = item.fullLabel || item.label || "";
            const values = groupedData[category] || {};
            const diff = diffData[category];

            const currentGroupMax = Math.max(...Object.values(values).map(v => safelyParseNumber(v)));
            const isHighValue = currentGroupMax > (maxValue * 0.7);

            // Smart Position Logic (Refactored)
            // Note: Grouped Bar charts also use the isHorizontal flag from outer scope,
            // but we need to pass it correctly.
            // Here 'actualCategories.length > 5' determines isHorizontal for Grouped Charts.
            const isGroupedHorizontal = actualCategories.length > 5;

            const tooltipStyle = calculateTooltipStyle(
                index,
                actualCategories.length,
                isGroupedHorizontal,
                isHighValue
            );

            // Smart unit detection - determine once for all values
            const formattedDiff = diff?.diff ? formatNumberWithUnit(Math.abs(diff.diff), maxValue, analysis.measureKey) : null;

            return (
                <View
                    className="bg-gray-900 dark:bg-white rounded-lg shadow-lg"
                    style={{
                        ...tooltipStyle,
                        minWidth: 200,
                        maxWidth: 340, // Increased from 220 for longer text
                        maxHeight: 280, // Prevent tooltip from getting too tall
                    }}
                >
                    <Text
                        className="text-white dark:text-gray-900 text-xs font-bold mb-2 text-center"
                        style={{ flexWrap: 'wrap', maxWidth: '100%' }}
                    >
                        {category}
                    </Text>

                    <ScrollView
                        style={{ maxHeight: 200 }}
                        nestedScrollEnabled={true}
                        showsVerticalScrollIndicator={actualSeriesValues.length > 5}
                    >
                        {actualSeriesValues.map((series, idx) => {
                            const formatted = formatNumberWithUnit(values[series] || 0, maxValue, analysis.measureKey);
                            const displayLabel = isPivotedFormat || isNaN(Number(series)) ? series : `เดือน ${series}`;

                            return (
                                <View key={series} className="mb-2">
                                    {/* Label row with color indicator */}
                                    <View className="flex-row items-center mb-1">
                                        <View
                                            style={{
                                                width: 10,
                                                height: 10,
                                                borderRadius: 2,
                                                backgroundColor: SERIES_COLORS[idx % SERIES_COLORS.length],
                                                marginRight: 6,
                                                flexShrink: 0
                                            }}
                                        />
                                        <Text
                                            className="text-gray-300 dark:text-gray-600 text-[11px] flex-1"
                                            style={{ flexWrap: 'wrap' }}
                                        >
                                            {displayLabel}
                                        </Text>
                                    </View>
                                    {/* Value row - indented to align with text */}
                                    <View style={{ marginLeft: 16 }}>
                                        <Text className="text-white dark:text-gray-900 text-[11px] font-semibold">
                                            {formatted.text} {formatted.unit}
                                        </Text>
                                    </View>
                                </View>
                            );
                        })}
                    </ScrollView>

                    {diff && (
                        <View className="border-t border-gray-700 dark:border-gray-300 mt-2 pt-2">
                            {diff.diff !== undefined && formattedDiff && (
                                <View className="flex-row justify-between">
                                    <Text className="text-gray-400 dark:text-gray-500 text-[10px]">ผลต่าง:</Text>
                                    <Text className={`text-[10px] font-semibold ${diff.diff >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {diff.diff >= 0 ? '+' : '-'}{formattedDiff.text} {formattedDiff.unit}
                                    </Text>
                                </View>
                            )}
                            {diff.pctDiff !== undefined && (
                                <View className="flex-row justify-between">
                                    <Text className="text-gray-400 dark:text-gray-500 text-[10px]">% ผลต่าง:</Text>
                                    <Text className={`text-[10px] font-semibold ${diff.pctDiff >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {diff.pctDiff >= 0 ? '+' : ''}{diff.pctDiff.toFixed(2)}%
                                    </Text>
                                </View>
                            )}
                        </View>
                    )}
                </View>
            );
        };

        const isHorizontal = analysis.mode === 'horizontal_bar';
        const chartHeight = isHorizontal
            ? Math.max(250, actualCategories.length * 60)
            : 220;

        return (
            <View className="my-4 p-4 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm">
                <View className="flex-row justify-between items-center mb-4">
                    <Text className="text-sm font-semibold text-gray-700 dark:text-gray-200" style={{ flex: 1 }}>
                        📊 เปรียบเทียบ: {analysis.measureKey}
                    </Text>
                    <TouchableOpacity
                        onPress={() => setIsFullScreen(true)}
                        style={{
                            padding: 8,
                            borderRadius: 8,
                            backgroundColor: '#3B82F6',
                            width: 36, // Smaller button
                            height: 36,
                            justifyContent: 'center',
                            alignItems: 'center',
                            marginLeft: 8
                        }}
                    >
                        <Text style={{ color: '#FFFFFF', fontSize: 16 }}>⤢</Text>
                    </TouchableOpacity>
                </View>

                {/* Legend */}
                <View className="flex-row flex-wrap mb-4 gap-x-4 gap-y-2">
                    {actualSeriesValues.map((series, idx) => (
                        <View key={series} className="flex-row items-center">
                            <View
                                style={{
                                    width: 12,
                                    height: 12,
                                    borderRadius: 3,
                                    backgroundColor: SERIES_COLORS[idx % SERIES_COLORS.length],
                                    marginRight: 6
                                }}
                            />
                            <Text className="text-xs text-gray-600 dark:text-gray-300">
                                {isPivotedFormat || isNaN(Number(series)) ? series : `เดือน ${series}`}
                            </Text>
                        </View>
                    ))}
                </View>

                <ScrollView
                    style={{ maxHeight: 400, width: '100%' }}
                    nestedScrollEnabled={true}
                    showsVerticalScrollIndicator={true}
                    showsHorizontalScrollIndicator={true}
                    contentContainerStyle={{ paddingRight: 20 }}
                >
                    {/* @ts-ignore */}
                    <BarChart
                        stackData={stackData}
                        barWidth={isHorizontal ? 16 : 20}
                        spacing={isHorizontal ? 30 : 40}
                        roundedTop
                        roundedBottom
                        hideRules
                        xAxisThickness={0}
                        yAxisThickness={0}
                        horizontal={isHorizontal}
                        yAxisTextStyle={{
                            color: isDark ? '#9CA3AF' : '#6B7280',
                            fontSize: 10,
                            width: isHorizontal ? 100 : undefined
                        }}
                        xAxisLabelTextStyle={{
                            color: isDark ? '#9CA3AF' : '#6B7280',
                            fontSize: 9,
                            width: 60,
                            textAlign: 'center'
                        }}
                        yAxisLabelWidth={isHorizontal ? 110 : 45}
                        formatYLabel={formatYLabel}
                        noOfSections={4}
                        maxValue={maxValue * 1.1}
                        height={chartHeight}
                        width={chartWidth - (isHorizontal ? 110 : 45)}
                        isAnimated
                        renderTooltip={renderGroupedTooltip}
                    />
                </ScrollView>

                <Text className="text-[10px] text-gray-400 dark:text-gray-500 text-center mt-3">
                    * แตะที่กราฟเพื่อดูรายละเอียดและผลต่าง
                </Text>

                {/* Full Screen Modal for Grouped Bars */}
                <Modal
                    visible={isFullScreen}
                    animationType="fade"
                    transparent={false}
                    onRequestClose={() => setIsFullScreen(false)}
                >
                    <View className="flex-1 bg-white dark:bg-gray-900 pt-12">
                        <View className="flex-row justify-between items-center px-6 pb-4 border-b border-gray-200 dark:border-gray-700">
                            <Text className="text-lg font-bold text-gray-800 dark:text-gray-100">
                                📊 เปรียบเทียบ: {analysis.measureKey}
                            </Text>
                            <TouchableOpacity
                                onPress={() => setIsFullScreen(false)}
                                className="p-2 rounded-lg bg-gray-100 dark:bg-gray-800 active:bg-gray-200 dark:active:bg-gray-700"
                            >
                                <Ionicons name="close-outline" size={24} color={isDark ? '#E5E7EB' : '#374151'} />
                            </TouchableOpacity>
                        </View>
                        <ScrollView className="flex-1 px-6 pt-6">
                            <View style={{ marginLeft: isHorizontal ? 0 : -10 }}>
                                {/* @ts-ignore */}
                                <BarChart
                                    stackData={stackData}
                                    barWidth={20}
                                    spacing={40}
                                    roundedTop
                                    roundedBottom
                                    hideRules
                                    xAxisThickness={0}
                                    yAxisThickness={0}
                                    horizontal={isHorizontal}
                                    yAxisTextStyle={{
                                        color: isDark ? '#9CA3AF' : '#6B7280',
                                        fontSize: 10,
                                        width: isHorizontal ? 100 : undefined
                                    }}
                                    xAxisLabelTextStyle={{
                                        color: isDark ? '#9CA3AF' : '#6B7280',
                                        fontSize: 9,
                                        width: 60,
                                        textAlign: 'center'
                                    }}
                                    yAxisLabelWidth={isHorizontal ? 110 : 45}
                                    formatYLabel={formatYLabel}
                                    noOfSections={4}
                                    maxValue={maxValue * 1.1}
                                    height={isHorizontal ? Math.max(400, actualCategories.length * 60) : 400} // Taller for fullscreen
                                    width={screenWidth - 80} // Explicit full width
                                    isAnimated
                                    renderTooltip={renderGroupedTooltip}
                                />
                            </View>
                            {/* Legend in Modal */}
                            <View className="flex-row flex-wrap mt-6 justify-center gap-x-4 gap-y-2">
                                {actualSeriesValues.map((series, idx) => (
                                    <View key={series} className="flex-row items-center">
                                        <View
                                            style={{
                                                width: 12,
                                                height: 12,
                                                borderRadius: 3,
                                                backgroundColor: SERIES_COLORS[idx % SERIES_COLORS.length],
                                                marginRight: 6
                                            }}
                                        />
                                        <Text className="text-xs text-gray-600 dark:text-gray-300">
                                            {isPivotedFormat || isNaN(Number(series)) ? series : `เดือน ${series}`}
                                        </Text>
                                    </View>
                                ))}
                            </View>
                        </ScrollView>
                    </View>
                </Modal>
            </View>
        );
    }, [data, analysis, isDark, chartWidth, isFullScreen]); // Added isFullScreen dependency

    // Grouped/stacked bar: only fall back to gifted-charts if ECharts is NOT available
    if ((analysis.mode === 'grouped_bar' || analysis.mode === 'stacked_bar' || analysis.seriesKey === '__pivoted__') && !(isEChartsAvailable() && echartsOption)) {
        return groupedChartData;
    }



    // ============================================================
    // 4. Original Chart Logic (Line, Horizontal Bar, Vertical Bar)
    // ============================================================

    const keys = Object.keys(data[0]);
    const monthKey = keys.find(k => ['month', 'เดือน'].some(term => k.toLowerCase().includes(term)));
    const yearKey = keys.find(k => ['year', 'ปี'].some(term => k.toLowerCase().includes(term)));
    const labelKey = keys.find(k =>
        ['date', 'label', 'name', 'product', 'department', 'province', 'group', 'category', 'segment', 'account', 'type', 'ฝ่าย', 'จังหวัด', 'สินค้า', 'หมวด', 'บัญชี', 'ประเภท']
            .some(term => k.toLowerCase().includes(term))
    );

    const isTimeSeries = !!(yearKey || monthKey);
    const isLineChart = isTimeSeries && data.length > 1;

    // Process data for non-grouped charts
    let processedData: any[] = [];
    let lineDataSets: any[] = [];
    let isMultiSeries = false;
    let seriesNames: string[] = [];
    const groupedData: Record<string, any[]> = {};

    if (isLineChart) {
        // Generate unique time labels
        const timeLabels = new Set<string>();

        data.forEach(item => {
            let label = '';
            if (monthKey && yearKey) {
                const yearStr = String(item[yearKey]);
                const shortYear = yearStr.length === 4 ? yearStr.slice(-2) : yearStr;
                label = `${item[monthKey]}/${shortYear}`;
            } else if (labelKey) {
                label = String(item[labelKey]);
            } else {
                label = String(item[keys[0]]);
            }

            if (!groupedData[label]) groupedData[label] = [];
            groupedData[label].push(item);
            timeLabels.add(label);
        });

        const sortedLabels = Array.from(timeLabels).sort((a, b) => {
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

        if (Object.values(groupedData).some(arr => arr.length > 1)) {
            isMultiSeries = true;
            seriesNames = Array.from(new Set(data.map(d => String(d[analysis.categoryKey]))));
        }

        if (isMultiSeries) {
            seriesNames.forEach((seriesName, idx) => {
                const points = sortedLabels.map(label => {
                    const items = groupedData[label] || [];
                    const match = items.find(i => String(i[analysis.categoryKey]) === seriesName);
                    const val = match ? safelyParseNumber(match[analysis.measureKey]) : 0;
                    return {
                        value: val,
                        label: label,
                        dataPointText: '',
                        formattedValue: val.toLocaleString('th-TH', { minimumFractionDigits: 2 }),
                        seriesName: seriesName,
                        dateLabel: label
                    };
                });

                lineDataSets.push({
                    data: points,
                    color: stringToColor(seriesName, idx),
                    label: seriesName,
                    dataPointsColor: stringToColor(seriesName, idx),
                });
            });
            processedData = lineDataSets[0]?.data || [];
        } else {
            processedData = sortedLabels.map(label => {
                const items = groupedData[label] || [];
                const val = items.reduce((sum, i) => sum + safelyParseNumber(i[analysis.measureKey]), 0);
                return {
                    value: val,
                    label: label,
                    parent: '',
                    frontColor: '#3B82F6',
                    labelTextStyle: { color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 },
                    formattedValue: val.toLocaleString('th-TH', { minimumFractionDigits: 2 }),
                    dataPointText: ''
                };
            });
        }
    } else {
        // Bar chart processing
        processedData = data.map(item => {
            const val = safelyParseNumber(item[analysis.measureKey]);
            let label = '';

            if (monthKey && yearKey && item[monthKey] && item[yearKey]) {
                const yearStr = String(item[yearKey]);
                const shortYear = yearStr.length === 4 ? yearStr.slice(-2) : yearStr;
                label = `${item[monthKey]}/${shortYear}`;
            } else if (labelKey && item[labelKey]) {
                label = String(item[labelKey]);
            } else if (analysis.categoryKey && item[analysis.categoryKey]) {
                label = String(item[analysis.categoryKey]);
            } else {
                label = String(Object.values(item)[0]);
            }

            const displayLabel = truncateLabel(label, 15);

            return {
                value: val,
                label: displayLabel,
                fullLabel: label,
                frontColor: stringToColor(label),
                labelTextStyle: { color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 },
                formattedValue: val.toLocaleString('th-TH', { minimumFractionDigits: 2 }),
                topLabelComponent: () => (
                    <Text style={{ color: isDark ? '#FFF' : '#000', fontSize: 10, marginBottom: 2 }}>
                        {val.toLocaleString('th-TH', { maximumFractionDigits: 0 })}
                    </Text>
                )
            };
        });
    }

    const isHorizontal = !isLineChart && data.length > 5;

    let maxValue = 0;
    if (isMultiSeries) {
        maxValue = Math.max(...lineDataSets.flatMap(ds => ds.data.map((d: any) => d.value)));
    } else {
        maxValue = Math.max(...processedData.map(d => d.value));
    }

    // ============================================================
    // Fix: Dimensions and Safe Areas
    // ============================================================
    // screenWidth is already defined at top of component
    const safeChartWidth = Math.min(screenWidth - 48, 600); // Max width 600px, otherwise screen - 48px padding



    // Render Smart Tooltip (Refactored)
    const renderTooltip = (item: any, index: number) => {
        if (!item) return null;

        // Check High Value relative to Max
        const isHorizontalChart = !isLineChart && data.length > 5;
        // Lower threshold to 0.3 (30%) for horizontal charts to force left-shift more often
        const threshold = isHorizontalChart ? 0.3 : 0.6;
        const isHigh = item.value > (maxValue * threshold);

        const total = processedData.length;

        const tooltipStyle = calculateTooltipStyle(index, total, isHorizontalChart, isHigh);

        // Smart unit formatting
        const formatted = formatNumberWithUnit(item.value || 0, maxValue, analysis.measureKey);

        return (
            <View
                className="bg-gray-900 dark:bg-white rounded-lg shadow-lg"
                style={{
                    ...tooltipStyle,
                    minWidth: 140,
                    maxWidth: 280, // Increased for longer labels
                    padding: 8
                }}
            >
                <Text
                    className="text-white dark:text-gray-900 text-xs font-bold mb-1 text-center"
                    style={{ flexWrap: 'wrap' }}
                >
                    {item.fullLabel || item.label}
                </Text>
                <Text className="text-white dark:text-gray-900 text-xs text-center">
                    {formatted.text} {formatted.unit}
                </Text>
            </View>
        );
    };

    // ============================================================
    // Gifted Charts Fallback (original code below)
    // ============================================================

    return (
        <View className="my-4 p-4 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm"
            style={{ width: '100%', overflow: 'visible' }}>

            {/* ... Header ... */}
            <View style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 24,
                width: '100%',
                gap: 8,
                padding: 4
            }}>
                <Text
                    className="text-sm font-semibold text-gray-700 dark:text-gray-200"
                    style={{ flex: 1, flexShrink: 1 }}
                    numberOfLines={2}
                >
                    {isLineChart ? '📈 Trends' : isHorizontal ? '📊 Comparative Rank' : '📊 Comparison'} : {analysis.measureKey}
                </Text>
                <TouchableOpacity
                    onPress={() => setIsFullScreen(true)}
                    style={{
                        padding: 8,
                        borderRadius: 8,
                        backgroundColor: '#3B82F6',
                        // borderWidth: 3,
                        // borderColor: '#FF0000',
                        width: 44,
                        height: 44,
                        justifyContent: 'center',
                        alignItems: 'center',
                        flexShrink: 0,
                        zIndex: 9999
                    }}
                    activeOpacity={0.7}
                >
                    <Text style={{ color: '#FFFFFF', fontSize: 20, fontWeight: 'bold' }}>⤢</Text>
                </TouchableOpacity>
            </View>

            {/* Chart Area */}
            <View style={{ marginLeft: isHorizontal ? 0 : -10, position: 'relative' }}>
                {/* Floating Expand Button */}


                {isLineChart ? (
                    // ... Line Chart ...
                    <LineChart
                        dataSet={isMultiSeries ? lineDataSets : undefined} // Usage for Multi-Line
                        data={isMultiSeries ? undefined : processedData}   // Usage for Single-Line
                        color={isMultiSeries ? undefined : "#3B82F6"}
                        thickness={2}
                        startFillColor="rgba(59, 130, 246, 0.3)"
                        endFillColor="rgba(59, 130, 246, 0.01)"
                        startOpacity={0.9}
                        endOpacity={0.2}
                        initialSpacing={20}
                        noOfSections={4}
                        yAxisTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 }}
                        xAxisLabelTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 }}
                        formatYLabel={formatYLabel}
                        hideDataPoints={false}
                        dataPointsColor="#3B82F6"
                        curved
                        areaChart={!isMultiSeries} // Only area for single series to avoid clutter
                        height={200}
                        width={safeChartWidth} // Use safe width
                        isAnimated
                        pointerConfig={{
                            pointerStripUptoDataPoint: true,
                            pointerStripColor: isDark ? '#4B5563' : '#D1D5DB',
                            pointerStripWidth: 2,
                            strokeDashArray: [2, 5],
                            pointerColor: isDark ? '#9CA3AF' : '#6B7280',
                            radius: 4,
                            pointerLabelWidth: 100,
                            pointerLabelHeight: 120,
                            autoAdjustPointerLabelPosition: true,
                            pointerComponent: (items: any) => {
                                if (!items || items.length === 0 || !items[0]) return null;
                                // Multi-series tooltip inside pointer
                                const item = items[0];

                                if (isMultiSeries) {
                                    const targetLabel = item.dateLabel || item.label;
                                    const groupItems = groupedData[targetLabel] || [];
                                    return (
                                        <View className="bg-gray-900 dark:bg-white rounded-lg shadow-lg p-2"
                                            style={{
                                                position: 'absolute',
                                                left: item.pointerX ? 10 : 0,
                                                top: -80,
                                                zIndex: 1000,
                                                minWidth: 180,
                                                maxWidth: 300,
                                                maxHeight: 240
                                            }}>
                                            <Text className="text-gray-300 dark:text-gray-500 text-[10px] mb-2 font-bold text-center">{targetLabel}</Text>
                                            <ScrollView
                                                style={{ maxHeight: 180 }}
                                                nestedScrollEnabled={true}
                                                showsVerticalScrollIndicator={groupItems.length > 5}
                                            >
                                                {groupItems.map((gItem: any, idx: number) => {
                                                    const sName = String(gItem[analysis.categoryKey]);
                                                    const val = safelyParseNumber(gItem[analysis.measureKey]);
                                                    const formatted = formatNumberWithUnit(val, maxValue, analysis.measureKey);
                                                    return (
                                                        <View key={idx} className="mb-2">
                                                            <View className="flex-row items-center mb-1">
                                                                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: stringToColor(sName, idx), marginRight: 4, flexShrink: 0 }} />
                                                                <Text className="text-white dark:text-gray-900 text-[10px] flex-1" style={{ flexWrap: 'wrap' }}>{sName}</Text>
                                                            </View>
                                                            <View style={{ marginLeft: 12 }}>
                                                                <Text className="text-white dark:text-gray-900 text-[10px] font-bold">{formatted.text} {formatted.unit}</Text>
                                                            </View>
                                                        </View>
                                                    );
                                                })}
                                            </ScrollView>
                                        </View>
                                    );
                                }

                                // Single series tooltip
                                const formatted = formatNumberWithUnit(item.value || 0, maxValue, analysis.measureKey);
                                return (
                                    <View
                                        className="bg-gray-900 dark:bg-white rounded-lg shadow-lg p-2"
                                        style={{
                                            position: 'absolute',
                                            left: -90,
                                            top: -60,
                                            zIndex: 1000,
                                            minWidth: 140,
                                            maxWidth: 240,
                                            padding: 8
                                        }}
                                    >
                                        <Text className="text-white dark:text-gray-900 text-xs font-bold mb-1 text-center" style={{ flexWrap: 'wrap' }}>{item.label}</Text>
                                        <Text className="text-white dark:text-gray-900 text-xs text-center">{formatted.text} {formatted.unit}</Text>
                                    </View>
                                );
                            },
                        }}
                    />
                ) : (
                    <ScrollView
                        style={{ maxHeight: 400, width: '100%' }}
                        nestedScrollEnabled={true}
                        showsVerticalScrollIndicator={true}
                        showsHorizontalScrollIndicator={true}
                        contentContainerStyle={{
                            paddingRight: 40, // More padding for right-side safety
                            minWidth: isHorizontal ? '100%' : undefined
                        }}
                    >
                        <BarChart
                            data={processedData}
                            barWidth={22}
                            spacing={24}
                            roundedTop
                            roundedBottom
                            hideRules
                            xAxisThickness={0}
                            yAxisThickness={0}
                            horizontal={isHorizontal}
                            yAxisTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10, width: isHorizontal ? 120 : undefined }}
                            yAxisLabelWidth={isHorizontal ? 130 : 40}
                            formatYLabel={formatYLabel}
                            noOfSections={4}
                            height={isHorizontal ? Math.max(200, processedData.length * 50) : 200}
                            width={safeChartWidth - (isHorizontal ? 130 : 40)} // Constrain width
                            isAnimated
                            frontColor={'#3B82F6'}
                            renderTooltip={renderTooltip}
                            shiftX={isHorizontal ? -10 : 0}
                        />
                    </ScrollView>
                )}
            </View>

            {/* Legend for multi-series */}
            {isMultiSeries && seriesNames.length > 0 && (
                <View className="flex-row flex-wrap mt-4 pt-4 border-t border-gray-100 dark:border-gray-700 justify-center gap-x-4 gap-y-2">
                    {seriesNames.map((name, idx) => (
                        <View key={name} className="flex-row items-center">
                            <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: stringToColor(name, idx), marginRight: 6 }} />
                            <Text className="text-xs text-gray-600 dark:text-gray-300">{name}</Text>
                        </View>
                    ))}
                </View>
            )}

            <Text className="text-[10px] text-gray-400 dark:text-gray-500 text-center mt-3">
                * แตะที่กราฟเพื่อดูรายละเอียด
            </Text>

            {/* Full Screen Modal */}
            <Modal
                visible={isFullScreen}
                animationType="fade"
                transparent={false}
                onRequestClose={() => setIsFullScreen(false)}
            >
                <View className="flex-1 bg-white dark:bg-gray-900 pt-12">
                    {/* Modal Header */}
                    <View className="flex-row justify-between items-center px-6 pb-4 border-b border-gray-200 dark:border-gray-700">
                        <Text className="text-lg font-bold text-gray-800 dark:text-gray-100">
                            {isLineChart ? '📈 Trends' : isHorizontal ? '📊 Comparative Rank' : '📊 Comparison'} : {analysis.measureKey}
                        </Text>
                        <TouchableOpacity
                            onPress={() => setIsFullScreen(false)}
                            className="p-2 rounded-lg bg-gray-100 dark:bg-gray-800 active:bg-gray-200 dark:active:bg-gray-700"
                        >
                            <Ionicons name="close-outline" size={24} color={isDark ? '#E5E7EB' : '#374151'} />
                        </TouchableOpacity>
                    </View>

                    {/* Full Screen Chart */}
                    <ScrollView className="flex-1 px-6 pt-6">
                        <View style={{ marginLeft: isHorizontal ? 0 : -10 }}>
                            {isLineChart ? (
                                <LineChart
                                    dataSet={isMultiSeries ? lineDataSets : undefined}
                                    data={isMultiSeries ? undefined : processedData}
                                    color={isMultiSeries ? undefined : "#3B82F6"}
                                    thickness={2}
                                    startFillColor="rgba(59, 130, 246, 0.3)"
                                    endFillColor="rgba(59, 130, 246, 0.01)"
                                    startOpacity={0.9}
                                    endOpacity={0.2}
                                    initialSpacing={20}
                                    noOfSections={4}
                                    yAxisTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 12 }}
                                    xAxisLabelTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 12 }}
                                    formatYLabel={formatYLabel}
                                    hideDataPoints={false}
                                    dataPointsColor="#3B82F6"
                                    curved
                                    areaChart={!isMultiSeries}
                                    height={300}
                                    width={screenWidth - 80}
                                    isAnimated
                                    pointerConfig={{
                                        pointerStripUptoDataPoint: true,
                                        pointerStripColor: isDark ? '#4B5563' : '#D1D5DB',
                                        pointerStripWidth: 2,
                                        strokeDashArray: [2, 5],
                                        pointerColor: isDark ? '#9CA3AF' : '#6B7280',
                                        radius: 4,
                                        pointerLabelWidth: 100,
                                        pointerLabelHeight: 120,
                                        autoAdjustPointerLabelPosition: true,
                                        pointerComponent: (items: any) => {
                                            if (!items || items.length === 0) return null;
                                            if (isMultiSeries && items[0]?.dataSet) {
                                                const pointsInDataSet = items[0].dataSet;
                                                const categoryValue = pointsInDataSet[0]?.label || '';
                                                return (
                                                    <View
                                                        className="absolute bg-gray-800 dark:bg-gray-100 rounded-lg shadow-lg p-3 border border-gray-600 dark:border-gray-300"
                                                        style={{ minWidth: 200, maxWidth: 300, maxHeight: 240 }}
                                                    >
                                                        <Text className="text-white dark:text-gray-900 font-semibold mb-2 text-sm" style={{ flexWrap: 'wrap' }}>
                                                            {categoryValue}
                                                        </Text>
                                                        <ScrollView style={{ maxHeight: 180 }} showsVerticalScrollIndicator={true} nestedScrollEnabled={true}>
                                                            {pointsInDataSet.map((point: any, i: number) => {
                                                                const seriesName = lineDataSets?.[i]?.dataSetName || '';
                                                                const value = point.value;
                                                                const formatted = formatNumberWithUnit(value, maxValue, analysis.measureKey);
                                                                const color = lineDataSets?.[i]?.color || '#3B82F6';
                                                                return (
                                                                    <View key={i} className="mb-2">
                                                                        <View className="flex-row items-center mb-1">
                                                                            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: color, marginRight: 8, flexShrink: 0 }} />
                                                                            <Text className="text-white dark:text-gray-900 text-xs flex-1" style={{ flexWrap: 'wrap' }}>
                                                                                {seriesName}
                                                                            </Text>
                                                                        </View>
                                                                        <View style={{ marginLeft: 16 }}>
                                                                            <Text className="text-white dark:text-gray-900 text-xs font-semibold">
                                                                                {formatted.text} {formatted.unit}
                                                                            </Text>
                                                                        </View>
                                                                    </View>
                                                                );
                                                            })}
                                                        </ScrollView>
                                                    </View>
                                                );
                                            } else {
                                                const item = items[0];
                                                if (!item) return null; // Added safety check
                                                const formatted = formatNumberWithUnit(item.value, maxValue, analysis.measureKey);
                                                return (
                                                    <View
                                                        className="absolute bg-gray-800 dark:bg-gray-100 rounded-lg shadow-lg p-3 border border-gray-600 dark:border-gray-300"
                                                        style={{ minWidth: 160, maxWidth: 240 }}
                                                    >
                                                        <Text className="text-white dark:text-gray-900 text-xs font-semibold mb-1" style={{ flexWrap: 'wrap' }}>
                                                            {item.label || ''}
                                                        </Text>
                                                        <Text className="text-white dark:text-gray-900 text-xs">
                                                            {formatted.text} {formatted.unit}
                                                        </Text>
                                                    </View>
                                                );
                                            }
                                        }
                                    }}
                                />
                            ) : (
                                <ScrollView
                                    horizontal={!isHorizontal}
                                    showsHorizontalScrollIndicator={!isHorizontal}
                                    showsVerticalScrollIndicator={isHorizontal}
                                    style={{
                                        maxWidth: isHorizontal ? undefined : '100%',
                                        maxHeight: isHorizontal ? 500 : undefined,
                                        minWidth: isHorizontal ? '100%' : undefined
                                    }}
                                >
                                    <BarChart
                                        data={processedData}
                                        barWidth={22}
                                        spacing={24}
                                        roundedTop
                                        roundedBottom
                                        hideRules
                                        xAxisThickness={0}
                                        yAxisThickness={0}
                                        horizontal={isHorizontal}
                                        yAxisTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 12, width: isHorizontal ? 120 : undefined }}
                                        yAxisLabelWidth={isHorizontal ? 130 : 40}
                                        formatYLabel={formatYLabel}
                                        noOfSections={4}
                                        height={isHorizontal ? Math.max(300, processedData.length * 50) : 300}
                                        width={screenWidth - 120}
                                        isAnimated
                                        frontColor={'#3B82F6'}
                                        renderTooltip={renderTooltip}
                                        shiftX={isHorizontal ? -10 : 0}
                                    />
                                </ScrollView>
                            )}
                        </View>

                        {/* Legend for multi-series */}
                        {isMultiSeries && seriesNames.length > 0 && (
                            <View className="flex-row flex-wrap mt-6 pt-4 border-t border-gray-100 dark:border-gray-700 justify-center gap-x-4 gap-y-2">
                                {seriesNames.map((name, idx) => (
                                    <View key={name} className="flex-row items-center">
                                        <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: stringToColor(name, idx), marginRight: 6 }} />
                                        <Text className="text-xs text-gray-600 dark:text-gray-300">{name}</Text>
                                    </View>
                                ))}
                            </View>
                        )}

                        <Text className="text-xs text-gray-400 dark:text-gray-500 text-center mt-6 mb-4">
                            * แตะที่กราฟเพื่อดูรายละเอียด
                        </Text>
                    </ScrollView>
                </View>
            </Modal>
        </View>
    );
};

export default DataChart;
