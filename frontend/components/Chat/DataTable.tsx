
import React from 'react';
import { View, Text, ScrollView, useColorScheme, TouchableOpacity, Alert, Share, Platform } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';
import { THAI_FONT_FAMILY } from '@/constants/theme';

interface DataTableProps {
    data: Record<string, any>[];
    displayHint?: 'hierarchical' | 'crosstab' | 'flat';
    hierarchyColumns?: string[]; // Ordered from parent→child (provided by LLM)
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

export const DataTable = ({ data, displayHint, hierarchyColumns }: DataTableProps) => {
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

    // Render Sort Arrow — NT amber accent (not generic blue)
    const renderSortIcon = (key: string) => {
        if (sortConfig.key !== key) return null;
        return (
            <Text className="text-[10px] ml-1" style={{ color: '#CA8A04' }}>
                {sortConfig.direction === 'asc' ? '▲' : '▼'}
            </Text>
        );
    };

    const keys = Object.keys(data[0]);
    console.log('[DataTable DEBUG] Keys:', keys);
    console.log('[DataTable DEBUG] Data Sample:', data[0]);

    // 1. Hierarchy & Dimension Detection
    // Dynamic Column Width Calculation
    const getColumnWidth = (key: string, isFirst: boolean = false) => {
        const baseWidth = isFirst ? 160 : 140;
        const charWidth = 9;
        const padding = 32;

        // Calculate based on Header Length
        const headerLength = key.length;
        const headerWidth = (headerLength * charWidth) + padding;

        // Also check actual data values (formatted numbers can be wider than headers)
        let dataWidth = 0;
        const sampleSize = Math.min(data.length, 10);
        for (let i = 0; i < sampleSize; i++) {
            const val = data[i]?.[key];
            let formattedLen = 0;
            if (typeof val === 'number') {
                formattedLen = val.toLocaleString('th-TH', { maximumFractionDigits: 2 }).length;
            } else if (typeof val === 'string') {
                formattedLen = Math.min(val.length, 30);
            }
            dataWidth = Math.max(dataWidth, (formattedLen * charWidth) + padding);
        }

        const requiredWidth = Math.max(headerWidth, dataWidth);

        // Clamp: Min 140/160, Max 350
        return Math.min(350, Math.max(baseWidth, requiredWidth));
    };

    // Strict exclusion of measure terms from dimensions
    // IMPORTANT: Use word-boundary for 'count' to avoid matching 'account'
    const measurePatterns = ['total', 'revenue', 'amount', 'value', 'price', 'cost', 'profit', 'รายได้', 'ยอดรวม', 'จำนวน', 'expense', 'baht', 'บาท', 'ค่าใช้จ่าย', 'กำไร', 'ขาดทุน'];
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

    // Measure Key — exclude already-identified time columns from fallback
    const timeColumnSet = new Set([monthKey, quarterKey, yearKey].filter(Boolean));
    const valueKey = keys.find(k => isMeasure(k)) || keys.find(k => typeof data[0][k] === 'number' && !k.toLowerCase().includes('id') && !timeColumnSet.has(k));

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

    // === MASTER RULE: If AI explicitly says 'flat', skip ALL auto-detection ===
    const skipAutoDetect = displayHint === 'flat';

    if (!skipAutoDetect && (yearKey || periodKey)) {
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
            // Pick category with highest cardinality as rowKey (not just first)
            // e.g., product_name(25) > department(1) → use product_name as rows
            rowKey = categoryKeys.reduce((best, k) => {
                const bestCard = new Set(data.map(d => String(d[best] || ''))).size;
                const kCard = new Set(data.map(d => String(d[k] || ''))).size;
                return kCard > bestCard ? k : best;
            }, categoryKeys[0]);
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

                // Normalize tLabel to match periodLabels format
                // Handles: "1" vs "01", "1/2025" vs "01/2025"
                if (tLabel) {
                    const normalizePeriod = (s: string): string => {
                        const parts = s.split('/');
                        const m = parseInt(parts[0]);
                        if (!isNaN(m) && m >= 1 && m <= 12) {
                            const padded = String(m).padStart(2, '0');
                            return parts.length > 1 ? `${padded}/${parts[1]}` : padded;
                        }
                        return s;
                    };
                    const normalizedLabel = normalizePeriod(tLabel);
                    const matchedLabel = periodLabels.find(p => normalizePeriod(p) === normalizedLabel);

                    if (matchedLabel) {
                        const val = item[valueKey || keys[keys.length - 1]];
                        const numVal = typeof val === 'number' ? val : parseFloat(String(val).replace(/,/g, '')) || 0;
                        rowMap[rVal][matchedLabel] = (rowMap[rVal][matchedLabel] || 0) + numVal;
                    }
                }
            });

            pivotedRows = Object.values(rowMap);
            // Sort rows by total value (descending)
            pivotedRows.sort((a, b) => {
                const totalA = periodLabels.reduce((s, p) => s + (a[p] || 0), 0);
                const totalB = periodLabels.reduce((s, p) => s + (b[p] || 0), 0);
                return totalB - totalA;
            });

            // Time-based crosstab: always keep as crosstab
            // Users who ask "รายเดือน" or "รายไตรมาส" expect time as columns
            // Empty cells simply mean "not in result set" — still useful info
        }
    }

    // === NEW: Category × Category Crosstab Detection ===
    // If no time-based crosstab, try to detect Category × Category pattern
    // SKIP if LLM explicitly requested hierarchical display
    if (!skipAutoDetect && !isCrosstab && categoryKeys.length >= 2 && valueKey && displayHint !== 'hierarchical') {
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

        // IMPORTANT: Identifier and Name columns should NEVER be column candidates
        // They belong together in rows (business rule: CODE + NAME pairs)
        const isIdentifier = (key: string): boolean => {
            const lower = key.toLowerCase();

            // Exact patterns that should match anywhere (substring match)
            // These are always identifiers regardless of position
            if (lower.includes('code') ||
                lower.includes('รหัส') ||
                lower.includes('เลขที่') ||
                lower.includes('cost_center') ||
                lower.includes('abbr') ||          // Abbreviations are identifiers
                lower.includes('ย่อ')) {            // Thai abbreviation
                return true;
            }

            // Word-boundary patterns (must be whole word or with underscore/hyphen separator)
            // This handles cases like: gl_code, account_id, key_value, but NOT: building, division
            const boundaryPatterns = ['id', 'gl', 'key', 'no'];
            return boundaryPatterns.some(pattern => {
                const regex = new RegExp(`(^|_|-)${pattern}($|_|-)`, 'i');
                return regex.test(lower);
            });
        };

        // NAME columns should also never be column candidates
        // They pair with CODE columns and belong in rows
        const isNameColumn = (key: string): boolean => {
            const lower = key.toLowerCase();
            return lower.includes('name') ||
                lower.includes('ชื่อ') ||
                lower.includes('_desc') ||
                lower.includes('description');
        };

        const getSemanticScore = (key: string): number => {
            // Identifiers must be rows (highest priority)
            if (isIdentifier(key)) return 100;
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
        // IMPORTANT: Exclude identifiers from column candidates

        // DEBUG: Log identifier detection
        categoryStats.forEach(c => {
            console.log(`[DataTable] Column: ${c.key}, uniqueCount: ${c.uniqueCount}, isIdentifier: ${isIdentifier(c.key)}, isName: ${isNameColumn(c.key)}, semanticScore: ${getSemanticScore(c.key)}`);
        });

        const colCandidate = categoryStats.find(c =>
            c.uniqueCount >= 2 &&
            c.uniqueCount <= 20 &&
            getSemanticScore(c.key) <= 0 &&
            !isIdentifier(c.key) &&     // CRITICAL: No identifiers as columns
            !isNameColumn(c.key)        // CRITICAL: No name columns as columns (they pair with codes)
        ) || categoryStats.find(c =>
            c.uniqueCount >= 2 &&
            c.uniqueCount <= 20 &&
            !isIdentifier(c.key) &&
            !isNameColumn(c.key)
        );

        if (colCandidate) {
            console.log(`[DataTable] Selected column candidate: ${colCandidate.key}`);
        } else {
            console.log(`[DataTable] No suitable column candidate found - will use flat table`);
        }

        // Use ALL other keys as row keys to preserve dimensions (e.g. Dept + Account)
        const rowCandidates = categoryStats.filter(c => c.key !== colCandidate?.key);

        if (colCandidate && rowCandidates.length > 0) {
            const allRowKeys = rowCandidates.map(r => r.key);
            const primaryRowKey = allRowKeys[0];

            // ─── KEY CHECK: Distinguish 1:N hierarchy from true matrix ───────
            // In a hierarchy: each ROW value maps to exactly 1 COL value
            //   e.g. SERVICE_GROUP → exactly 1 BUSINESS_GROUP (hierarchy → show as rows)
            // In a true matrix crosstab: each ROW value can appear across MULTIPLE COL values
            //   e.g. department_name appears for multiple months (time comparison)
            const rowToColMap: Record<string, Set<string>> = {};
            data.forEach(row => {
                const rVal = String(row[primaryRowKey] || '');
                const cVal = String(row[colCandidate.key] || '');
                if (!rowToColMap[rVal]) rowToColMap[rVal] = new Set();
                rowToColMap[rVal].add(cVal);
            });
            const isOneToNHierarchy = Object.values(rowToColMap).every(s => s.size === 1);

            // Sparsity check: would the pivot create a mostly-empty matrix?
            // If each row only has 1 value across columns → sparse → flat is better
            const uniqueRowLabels = new Set(data.map(d =>
                allRowKeys.map(k => String(d[k] || '')).join('-')
            )).size;
            const possibleCells = uniqueRowLabels * colCandidate.uniqueCount;
            const fillRate = data.length / possibleCells;
            const isSparse = fillRate < 0.4; // less than 40% cells filled

            // Use crosstab ONLY if:
            // (a) LLM explicitly requested crosstab, OR
            // (b) Data is NOT a 1:N hierarchy AND NOT sparse
            const useCrosstab = (displayHint === 'crosstab') ||
                (!isOneToNHierarchy && !isSparse && colCandidate.uniqueCount <= 20);

            if (isOneToNHierarchy && displayHint !== 'crosstab') {
                console.log(`[DataTable] Detected 1:N hierarchy (${primaryRowKey} → ${colCandidate.key}) → using hierarchical mode instead of crosstab`);
            }
            if (isSparse && displayHint !== 'crosstab') {
                console.log(`[DataTable] Sparse pivot detected (fill rate ${(fillRate*100).toFixed(0)}%) → using flat table`);
            }

            if (useCrosstab) {
                isCrosstab = true;
                rowKey = allRowKeys.join(' / '); // Display Label
                colKey = colCandidate.key;

                // Enhanced sorting: If all values are numeric (like GL codes), sort numerically
                const allNumeric = colCandidate.values.every(v => !isNaN(parseFloat(v)) && isFinite(parseFloat(v)));
                periodLabels = colCandidate.values.sort((a, b) => {
                    if (allNumeric) {
                        return parseFloat(a) - parseFloat(b);
                    }
                    return a.localeCompare(b, 'th');
                });

                // Pivot the data - Use ALL row keys (including both code and name)
                const rowMap: Record<string, any> = {};
                data.forEach(item => {
                    // Create Composite Row Key using ALL row keys (code + name together)
                    const rVal = allRowKeys.map(k => String(item[k] || '')).filter(v => v).join(' - ');
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

                console.log(`[DataTable] Category×Category Crosstab: [${allRowKeys.join(', ')}] × ${colCandidate.key}`);
            }
        }
    }

    // ─── Multi-level Hierarchy Detection ───────────────────────────────────
    // Used when LLM sends display_hint='hierarchical' OR auto-detected from data.
    let hierarchyKeys: string[] = []; // Ordered parent→child column names
    let hierarchyValueKey: string = valueKey || '';

    const detectMultiLevelHierarchy = (): string[] => {
        // 1. LLM explicitly provided ordering → trust it
        if (hierarchyColumns && hierarchyColumns.length >= 2) {
            // Validate all columns exist in data
            const valid = hierarchyColumns.filter(c => keys.includes(c));
            if (valid.length >= 2) return valid;
        }

        // 2. Auto-detect: find dimension columns with strict 1:N parent-child relationships
        const nonMeasureDims = dimensionKeys.filter(k => {
            const lower = k.toLowerCase();
            const timeKeywords = ['year', 'month', 'date', 'time', 'quarter', 'week', 'day',
                'ปี', 'เดือน', 'วันที่', 'ไตรมาส', 'สัปดาห์', 'วัน', 'เวลา', 'พ.ศ.', 'ค.ศ.'];
            return !timeKeywords.some(t => lower.includes(t));
        });

        if (nonMeasureDims.length < 2) return [];

        // Get cardinality
        const cardinalityMap = nonMeasureDims.map(k => ({
            key: k,
            unique: new Set(data.map(d => String(d[k] || ''))).size,
        }));

        // Sort ascending (fewest unique = highest in hierarchy)
        cardinalityMap.sort((a, b) => a.unique - b.unique);

        // Verify strict 1:N between adjacent levels: for each child value, it maps to exactly 1 parent
        const candidate: string[] = [];
        for (let i = 0; i < cardinalityMap.length; i++) {
            if (candidate.length === 0) {
                candidate.push(cardinalityMap[i].key);
                continue;
            }
            const parentKey = candidate[candidate.length - 1];
            const childKey = cardinalityMap[i].key;

            // Check: child values mostly map to 1 parent (allow some shared names)
            // e.g., "ส่วนสนับสนุน" may exist in multiple departments — tree rendering handles this correctly.
            const childToParent: Record<string, Set<string>> = {};
            data.forEach(row => {
                const child = String(row[childKey] || '');
                const parent = String(row[parentKey] || '');
                if (!childToParent[child]) childToParent[child] = new Set();
                childToParent[child].add(parent);
            });

            const totalChildren = Object.keys(childToParent).length;
            const multiParentCount = Object.values(childToParent).filter(parents => parents.size > 1).length;
            // Allow up to 30% of children to have shared names across parents
            // True cross-dimensional data (product × region) typically has 80%+ overlap → won't pass
            const isHierarchical = totalChildren > 0 && (multiParentCount / totalChildren) <= 0.3;
            if (isHierarchical) {
                candidate.push(childKey);
            }
        }

        return candidate.length >= 2 ? candidate : [];
    };

    // Determine if we should use hierarchical mode
    // Priority: crosstab hint wins, otherwise always try hierarchy auto-detection
    // AI often defaults to 'flat' for multi-level data — the strict 1:N check in
    // detectMultiLevelHierarchy() prevents false positives, so it's safe to always run.
    const isHierarchicalHint = displayHint === 'hierarchical';
    const isCrosstabHint = displayHint === 'crosstab';
    const isFlatHint = displayHint === 'flat';

    if (!isCrosstab && !isCrosstabHint) {
        hierarchyKeys = detectMultiLevelHierarchy();
        if (hierarchyKeys.length >= 2) {
            hierarchyValueKey = valueKey || keys.find(k => typeof data[0][k] === 'number' && !k.toLowerCase().includes('id') && !timeColumnSet.has(k)) || keys[keys.length - 1];
        }
    }

    const isHierarchical = !isCrosstab && hierarchyKeys.length >= 2;

    // ─── Render: HIERARCHICAL GROUPED ROWS ────────────────────────────────
    const renderHierarchicalTable = () => {
        // Build nested tree: { parentVal: { childVal: { grandChildVal: rows[] } } ... }
        const levels = hierarchyKeys;
        const leafLevel = levels.length - 1;
        const measureKeys = keys.filter(k => k !== hierarchyValueKey && isMeasure(k));
        // Non-hierarchy, non-measure display columns
        const extraCols = keys.filter(k => !levels.includes(k) && k !== hierarchyValueKey && !measureKeys.includes(k));
        const valueCols = [hierarchyValueKey, ...measureKeys].filter(Boolean);

        // Recursively build grouped structure
        type TreeNode = { rows: Record<string, any>[]; children: Record<string, TreeNode> };
        const buildTree = (rows: Record<string, any>[], levelIdx: number): Record<string, TreeNode> => {
            if (levelIdx > leafLevel) return {};
            const grouped: Record<string, TreeNode> = {};
            rows.forEach(row => {
                const key = String(row[levels[levelIdx]] ?? '—');
                if (!grouped[key]) grouped[key] = { rows: [], children: {} };
                grouped[key].rows.push(row);
            });
            if (levelIdx < leafLevel) {
                Object.keys(grouped).forEach(k => {
                    grouped[k].children = buildTree(grouped[k].rows, levelIdx + 1);
                });
            }
            return grouped;
        };

        const sumRows = (rows: Record<string, any>[]): Record<string, number> => {
            const totals: Record<string, number> = {};
            valueCols.forEach(col => {
                totals[col] = rows.reduce((s, r) => s + (parseFloat(String(r[col]).replace(/,/g, '')) || 0), 0);
            });
            return totals;
        };

        // Wave 5: restrained neutral ramp (Claude-like) — depth shown by
        // indentation + a lightening background + text weight, not loud hues.
        const levelColors = [
            isDark ? '#374151' : '#EEF0F3', // Level 0 — deepest neutral
            isDark ? '#2C333D' : '#F3F5F7',
            isDark ? '#232A33' : '#F8F9FA',
            isDark ? '#1F2530' : '#FCFCFD',
        ];
        const levelTextColors = [
            isDark ? '#F3F4F6' : '#111827',
            isDark ? '#E5E7EB' : '#1F2937',
            isDark ? '#D1D5DB' : '#374151',
            isDark ? '#9CA3AF' : '#4B5563',
        ];

        const tree = buildTree(data, 0);

        const renderNode = (node: TreeNode, levelIdx: number, groupName: string): React.ReactElement => {
            const isLeaf = levelIdx === leafLevel;
            const bgColor = levelColors[Math.min(levelIdx, levelColors.length - 1)];
            const textColor = levelTextColors[Math.min(levelIdx, levelTextColors.length - 1)];
            const indent = levelIdx * 12;
            const subtotals = sumRows(node.rows);

            // Sort child groups by their subtotal if a sort is active
            const sortedChildEntries = (entries: [string, TreeNode][]) => {
                if (!sortConfig.key || !valueCols.includes(sortConfig.key)) {
                    return entries.sort(([a], [b]) => a.localeCompare(b, 'th'));
                }
                return entries.sort(([, nodeA], [, nodeB]) => {
                    const totA = sumRows(nodeA.rows)[sortConfig.key!] ?? 0;
                    const totB = sumRows(nodeB.rows)[sortConfig.key!] ?? 0;
                    return sortConfig.direction === 'asc' ? totA - totB : totB - totA;
                });
            };

            // Leaf rows: only show when there are extra columns beyond hierarchy+measure
            // If extraCols is empty, the subtotal in the header already shows all info
            const hasExtraInfo = extraCols.length > 0;
            // Also show leaf rows when a leaf group has multiple raw rows that differ (detail rows)
            const leafHasMultipleDistinctRows = isLeaf && node.rows.length > 1;
            const showLeafRows = isLeaf && (hasExtraInfo || leafHasMultipleDistinctRows);

            return (
                <View key={`${levelIdx}-${groupName}`}>
                    {/* Group header row */}
                    <View style={{ backgroundColor: bgColor, paddingLeft: 12 + indent, paddingRight: 12, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: isDark ? '#374151' : '#E5E7EB' }}>
                        <Text style={{ flex: 1, fontSize: levelIdx === 0 ? 13 : 12, fontWeight: '700', color: textColor }} numberOfLines={2}>
                            {levelIdx === 0 ? '▸ ' : '  ▸ '}{groupName}
                        </Text>
                        {/* Subtotals per value column */}
                        {valueCols.map(col => (
                            <Text key={col} style={{ width: getColumnWidth(col), fontSize: 12, fontWeight: '600', color: textColor, textAlign: 'right' }}>
                                {subtotals[col] !== undefined ? subtotals[col].toLocaleString('th-TH', { maximumFractionDigits: 2 }) : ''}
                            </Text>
                        ))}
                    </View>
                    {/* Children: either sub-groups or leaf rows (only when there are extra columns to show) */}
                    {showLeafRows
                        ? sortData(node.rows).map((row, rIdx) => (
                            <View key={rIdx} style={{ flexDirection: 'row', paddingLeft: 16 + indent + 12, paddingRight: 12, paddingVertical: 6, backgroundColor: rIdx % 2 === 0 ? (isDark ? '#111827' : '#FFFFFF') : (isDark ? 'rgba(55,65,81,0.3)' : '#F9FAFB'), borderBottomWidth: 1, borderBottomColor: isDark ? '#1F2937' : '#F3F4F6' }}>
                                {/* Extra non-hierarchy, non-measure cols */}
                                {extraCols.map(col => (
                                    <Text key={col} style={{ width: getColumnWidth(col, true), fontSize: 12, color: isDark ? '#D1D5DB' : '#374151' }} numberOfLines={2}>
                                        {renderCell(col, row[col])}
                                    </Text>
                                ))}
                                {/* Value cols (only if extra cols exist to differentiate rows) */}
                                {valueCols.map(col => (
                                    <Text key={col} style={{ width: getColumnWidth(col), fontSize: 12, color: isDark ? '#E5E7EB' : '#1F2937', textAlign: 'right', fontVariant: ['tabular-nums'] }}>
                                        {renderCell(col, row[col])}
                                    </Text>
                                ))}
                            </View>
                        ))
                        : !isLeaf
                            ? sortedChildEntries(Object.entries(node.children))
                                .map(([childName, childNode]) => renderNode(childNode, levelIdx + 1, childName))
                            : null
                    }
                </View>
            );
        };

        // Sort top-level groups by subtotal if sort is active on a value column
        const sortTopLevel = (entries: [string, TreeNode][]) => {
            if (!sortConfig.key || !valueCols.includes(sortConfig.key)) {
                return entries.sort(([a], [b]) => a.localeCompare(b, 'th'));
            }
            return entries.sort(([, nodeA], [, nodeB]) => {
                const totA = sumRows(nodeA.rows)[sortConfig.key!] ?? 0;
                const totB = sumRows(nodeB.rows)[sortConfig.key!] ?? 0;
                return sortConfig.direction === 'asc' ? totA - totB : totB - totA;
            });
        };

        // Column header
        return (
            <View>
                {/* Header */}
                <View style={{ flexDirection: 'row', backgroundColor: isDark ? '#1F2937' : '#F9FAFB', paddingHorizontal: 12, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: isDark ? '#374151' : '#E5E7EB' }}>
                    <Text style={{ flex: 1, fontSize: 11, fontWeight: '700', color: isDark ? '#9CA3AF' : '#6B7280', textTransform: 'uppercase', letterSpacing: 0.5, fontFamily: THAI_FONT_FAMILY }}>
                        {levels.join(' › ')}
                    </Text>
                    {valueCols.map(col => (
                        <TouchableOpacity key={col} onPress={() => handleSort(col)} style={{ width: getColumnWidth(col), flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end' }}>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: isDark ? '#9CA3AF' : '#6B7280', textTransform: 'uppercase', textAlign: 'right', fontFamily: THAI_FONT_FAMILY }}>{col}</Text>
                            {renderSortIcon(col)}
                        </TouchableOpacity>
                    ))}
                </View>
                {/* Tree rows — sorted by subtotal when sort is active */}
                {sortTopLevel(Object.entries(tree))
                    .map(([groupName, node]) => renderNode(node, 0, groupName))}
            </View>
        );
    };

    // ─── Fallback: Single-level Grouped List (parentKey) ─────────────────
    // Used when NOT crosstab AND NOT hierarchical — groups by one parent column
    let parentKey = '';
    if (!isCrosstab && !isHierarchical && dimensionKeys.length >= 2) {
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
                <View className="flex-row bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                    {/* Frozen First Column Header */}
                    <TouchableOpacity onPress={() => handleSort('_rowLabel')} className="px-4 py-3 bg-gray-100 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex-row items-center justify-between" style={{ width: getColumnWidth(rowKey, true) }}>
                        <Text className="text-xs font-bold text-gray-700 dark:text-gray-200 uppercase">{rowKey}</Text>
                        {renderSortIcon('_rowLabel')}
                    </TouchableOpacity>
                    {/* Period Columns Header */}
                    {periodLabels.map((period, idx) => (
                        <TouchableOpacity key={period} onPress={() => handleSort(period)} className="px-4 py-3 flex-row items-center justify-center" style={{ width: getColumnWidth(period) }}>
                            <Text className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase text-center">{period}</Text>
                            {renderSortIcon(period)}
                        </TouchableOpacity>
                    ))}
                </View>

                {/* Data Rows */}
                {sortData(pivotedRows).map((row, rIdx) => (
                    <View key={rIdx} className={`flex-row border-b border-gray-100 dark:border-gray-800 ${rIdx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50/50 dark:bg-gray-800/30'}`}>
                        {/* Frozen First Column Data */}
                        <View className="px-4 py-3 bg-gray-50/80 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700" style={{ width: getColumnWidth(rowKey, true) }}>
                            <Text className="text-xs font-semibold text-gray-800 dark:text-gray-200" numberOfLines={2}>{row._rowLabel}</Text>
                        </View>
                        {/* Period Data Cells */}
                        {periodLabels.map((period) => (
                            <View key={period} className="px-4 py-3" style={{ width: getColumnWidth(period) }}>
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
                        <View className="bg-gray-50 dark:bg-gray-800 px-4 py-2 border-l-4 mb-1" style={{ borderLeftColor: '#FFD100' }}>
                            <Text className="font-bold text-gray-800 dark:text-gray-200" style={{ fontFamily: THAI_FONT_FAMILY }}>{groupName}</Text>
                        </View>
                        <View className="flex-row bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                            {displayKeys.map((key, idx) => (
                                <TouchableOpacity key={key} onPress={() => handleSort(key)} className="px-4 py-2 flex-row items-center justify-between" style={{ width: getColumnWidth(key, idx === 0) }}>
                                    <Text className="text-[10px] font-bold text-gray-500 uppercase">{key}</Text>
                                    {renderSortIcon(key)}
                                </TouchableOpacity>
                            ))}
                        </View>
                        {sortData(groupItems).map((row, rIdx) => (
                            <View key={rIdx} className={`flex-row border-b border-gray-100 dark:border-gray-800 ${rIdx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-800/50'}`}>
                                {displayKeys.map((key, cIdx) => (
                                    <View key={key} className="px-4 py-2" style={{ width: getColumnWidth(key, cIdx === 0) }}>
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
                        <TouchableOpacity key={key} onPress={() => handleSort(key)} className="px-4 py-3 flex-row items-center justify-between" style={{ width: getColumnWidth(key, idx === 0) }}>
                            <Text className="text-xs font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wide">{key}</Text>
                            {renderSortIcon(key)}
                        </TouchableOpacity>
                    ))}
                </View>
                {sortData(data).map((row, idx) => (
                    <View key={idx} className={`flex-row border-b border-gray-100 dark:border-gray-700/50 ${idx % 2 === 0 ? 'bg-white dark:bg-gray-900' : 'bg-gray-50/50 dark:bg-gray-800/30'}`}>
                        {keys.map((key, colIndex) => (
                            <View key={`${idx}-${key}`} className="px-4 py-3" style={{ width: getColumnWidth(key, colIndex === 0) }}>
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
        // fontFamily on the container → all descendant text inherits Sarabun on web (RN-Web renders Text as inheriting DOM nodes)
        <View className="mt-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm" style={{ fontFamily: THAI_FONT_FAMILY } as any}>
            <View className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-900/50 flex-row justify-between items-center">
                <View className="flex-row items-center" style={{ flex: 1, flexShrink: 1 }}>
                    {/* NT-yellow accent tick instead of the emoji */}
                    <View style={{ width: 3, height: 14, borderRadius: 2, backgroundColor: '#FFD100', marginRight: 8 }} />
                    <Text className="text-sm font-semibold text-gray-800 dark:text-gray-200" style={{ fontFamily: THAI_FONT_FAMILY, flexShrink: 1 }} numberOfLines={1}>
                        {isCrosstab
                            ? `${rowKey} × ${colKey}`
                            : isHierarchical
                                ? `${hierarchyKeys.join(' › ')}`
                                : parentKey
                                    ? `ตารางแยกตาม ${parentKey}`
                                    : 'ตารางข้อมูล'}
                    </Text>
                </View>
                <View className="flex-row items-center gap-2" style={{ flexShrink: 0 }}>
                    <Text className="text-xs text-gray-500 dark:text-gray-400 font-medium bg-white dark:bg-gray-800 px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700" style={{ fontFamily: THAI_FONT_FAMILY }}>
                        {data.length} รายการ
                    </Text>
                    <TouchableOpacity
                        onPress={exportToCSV}
                        className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 active:bg-gray-200 dark:active:bg-gray-600"
                        accessibilityLabel="ดาวน์โหลด CSV"
                    >
                        <Ionicons name="download-outline" size={18} color={isDark ? '#D1D5DB' : '#6B7280'} />
                    </TouchableOpacity>
                </View>
            </View>

            <ScrollView
                horizontal
                showsHorizontalScrollIndicator={true}
                className="w-full"
            >
                <ScrollView
                    nestedScrollEnabled={true}
                    showsVerticalScrollIndicator={true}
                    style={{ maxHeight: 600 }}
                >
                    {isCrosstab
                        ? renderCrosstabTable()
                        : isHierarchical
                            ? renderHierarchicalTable()
                            : parentKey
                                ? renderGroupedTable()
                                : renderFlatTable()}
                </ScrollView>
            </ScrollView>
        </View>
    );
};
