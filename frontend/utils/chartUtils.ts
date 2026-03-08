/**
 * Chart utility functions — extracted from DataChart.tsx for reuse.
 */

/** Safely parse numbers (remove commas, %, currency symbols) */
export const safelyParseNumber = (val: any): number => {
    if (typeof val === 'number') return val;
    if (val === null || val === undefined || val === '') return 0;

    let strVal = String(val).trim();
    const isAccountingNegative = strVal.startsWith('(') && strVal.endsWith(')');

    strVal = strVal.replace(/[^0-9.-]/g, '');

    const parsed = parseFloat(strVal);
    if (isNaN(parsed)) return 0;

    return isAccountingNegative ? -Math.abs(parsed) : parsed;
};

/** Detect unit from column name */
export const detectUnitFromColumnName = (
    columnName?: string,
): 'baht' | 'thousand' | 'million' | 'billion' | 'auto' => {
    if (!columnName) return 'auto';
    const lower = columnName.toLowerCase();

    if (lower.includes('billion') || lower.includes('พันล้าน') || lower.includes('_b_baht') || lower.includes('_billion')) {
        return 'billion';
    }
    if (lower.includes('million') || lower.includes('ล้าน') ||
        lower.includes('_m_baht') || lower.includes('_million') ||
        lower.endsWith('_m') || lower.includes('_mb')) {
        return 'million';
    }
    if (lower.includes('thousand') || lower.includes('พัน') ||
        lower.includes('_k_baht') || lower.includes('_thousand') ||
        lower.endsWith('_k')) {
        return 'thousand';
    }
    return 'auto';
};

export const formatNumberWithUnit = (
    value: number,
    maxValue: number,
    columnName?: string,
): { text: string; unit: string } => {
    const detectedUnit = detectUnitFromColumnName(columnName);

    if (detectedUnit === 'billion') {
        return {
            text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'พันล้านบาท',
        };
    }
    if (detectedUnit === 'million') {
        return {
            text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'ล้านบาท',
        };
    }
    if (detectedUnit === 'thousand') {
        return {
            text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'พันบาท',
        };
    }

    // Auto-detect from maxValue
    const absMax = Math.abs(maxValue);
    if (absMax >= 1_000_000) {
        return {
            text: (value / 1_000_000).toLocaleString('th-TH', { maximumFractionDigits: 2 }),
            unit: 'ล้านบาท',
        };
    }
    return {
        text: value.toLocaleString('th-TH', { maximumFractionDigits: 2 }),
        unit: 'บาท',
    };
};

/** Thai month ordering for smart sort */
const THAI_MONTH_ORDER: Record<string, number> = {
    'ม.ค.': 1, 'ก.พ.': 2, 'มี.ค.': 3, 'เม.ย.': 4,
    'พ.ค.': 5, 'มิ.ย.': 6, 'ก.ค.': 7, 'ส.ค.': 8,
    'ก.ย.': 9, 'ต.ค.': 10, 'พ.ย.': 11, 'ธ.ค.': 12,
    'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4,
    'พฤษภาคม': 5, 'มิถุนายน': 6, 'กรกฎาคม': 7, 'สิงหาคม': 8,
    'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12,
};

const EN_MONTH_ORDER: Record<string, number> = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
};

/** Smart month sort — handles Thai, English, and numeric months */
export const smartMonthSort = (labels: string[]): string[] => {
    return [...labels].sort((a, b) => {
        const aOrder = THAI_MONTH_ORDER[a] ?? EN_MONTH_ORDER[a.toLowerCase()] ?? null;
        const bOrder = THAI_MONTH_ORDER[b] ?? EN_MONTH_ORDER[b.toLowerCase()] ?? null;
        if (aOrder !== null && bOrder !== null) return aOrder - bOrder;

        // Try numeric month extraction
        const aNum = parseInt(a, 10);
        const bNum = parseInt(b, 10);
        if (!isNaN(aNum) && !isNaN(bNum)) return aNum - bNum;

        return a.localeCompare(b, 'th');
    });
};

/** Truncate long labels */
export const truncateLabel = (label: string, maxLen: number = 12): string => {
    return label.length > maxLen ? label.slice(0, maxLen) + '...' : label;
};
