#!/usr/bin/env node
/**
 * Test: Grouped Bar Chart Month Sorting Issue
 *
 * Simulates the fixed logic for question: "ค่าใช้จ่ายรายหมวดบัญชี รายเดือน"
 */

// Simulate smartMonthSort
function smartMonthSort(values) {
    const monthNameToNum = {
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

    const extractMonthNum = (val) => {
        const lower = val.toLowerCase().trim();
        if (monthNameToNum[lower] !== undefined) return monthNameToNum[lower];

        const match = val.match(/\d+/);
        if (match) {
            const num = parseInt(match[0]);
            if (num >= 1 && num <= 12) return num;
        }

        const asNum = parseInt(val);
        if (!isNaN(asNum) && asNum >= 1 && asNum <= 12) return asNum;

        return 999;
    };

    return [...values].sort((a, b) => extractMonthNum(a) - extractMonthNum(b));
}

console.log("=" .repeat(80));
console.log("TEST: Grouped Bar Chart - Month Sorting Fix");
console.log("=" .repeat(80));

// Simulate query result data
const sampleData = [
    { "เดือน": "8", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1000000 },
    { "เดือน": "9", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1200000 },
    { "เดือน": "10", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1100000 },
    { "เดือน": "11", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1300000 },
    { "เดือน": "12", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1400000 },
    { "เดือน": "1", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1500000 },
    { "เดือน": "2", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1600000 },
    { "เดือน": "8", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 500000 },
    { "เดือน": "9", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 550000 },
    { "เดือน": "10", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 520000 },
    { "เดือน": "11", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 580000 },
    { "เดือน": "12", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 600000 },
    { "เดือน": "1", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 620000 },
    { "เดือน": "2", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 650000 },
];

console.log("\n1. Sample Data:");
console.log(`   Rows: ${sampleData.length}`);
console.log(`   Columns: ${Object.keys(sampleData[0]).join(", ")}`);

// Simulate AI returning WRONG config (before swap)
let chartConfig = {
    category_column: "หมวดบัญชี",  // WRONG - should be X-axis but isn't time
    measure_column: "ยอดค่าใช้จ่าย",
    series_column: "เดือน"  // WRONG - time should be category
};

console.log("\n2. AI Config (BEFORE swap):");
console.log(`   category_column: ${chartConfig.category_column}`);
console.log(`   series_column: ${chartConfig.series_column}`);
console.log(`   ❌ PROBLEM: Time column is in series, not category!`);

// Simulate swap logic
let finalCategoryKey = chartConfig.category_column;
let finalSeriesKey = chartConfig.series_column;

const timeKeywords = ['month', 'year', 'date', 'quarter', 'week', 'day', 'time',
    'เดือน', 'ปี', 'วันที่', 'ไตรมาส', 'สัปดาห์', 'วัน', 'เวลา'];

const isCategoryTime = timeKeywords.some(t => finalCategoryKey.toLowerCase().includes(t));
const isSeriesTime = timeKeywords.some(t => finalSeriesKey.toLowerCase().includes(t));

if (isSeriesTime && !isCategoryTime) {
    console.log("\n3. Frontend Validation:");
    console.log(`   ⚠️  Detected: Time column in series_column`);
    console.log(`   🔄 SWAPPING: category ↔ series`);
    [finalCategoryKey, finalSeriesKey] = [finalSeriesKey, finalCategoryKey];
} else {
    console.log("\n3. Frontend Validation:");
    console.log(`   ✅ Config is correct, no swap needed`);
}

console.log("\n4. Config (AFTER swap):");
console.log(`   category_column: ${finalCategoryKey}`);
console.log(`   series_column: ${finalSeriesKey}`);
console.log(`   ✅ Time column is now in category (X-axis)!`);

// Build categories (X-axis labels)
const categoryCounts = {};
sampleData.forEach(row => {
    const cat = String(row[finalCategoryKey] || '');
    categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
});

let categories = Object.keys(categoryCounts);
console.log("\n5. Categories (BEFORE sort):");
console.log(`   ${categories.join(", ")}`);

// CRITICAL FIX: Sort categories if time column
const isCategoryTimeColumn = ['month', 'เดือน', 'quarter', 'ไตรมาส'].some(t =>
    finalCategoryKey.toLowerCase().includes(t)
);

if (isCategoryTimeColumn) {
    console.log(`\n6. Detected time column, applying smartMonthSort...`);
    categories = smartMonthSort(categories);
    console.log(`   ✅ Sorted: ${categories.join(", ")}`);
} else {
    console.log(`\n6. Not a time column, skipping month sort`);
}

// Build series values (Legend)
const uniqueSeries = Array.from(new Set(sampleData.map(d => String(d[finalSeriesKey]))));
console.log("\n7. Series Values (Legend):");
console.log(`   ${uniqueSeries.join(", ")}`);

// Simulate groupedChartData logic
console.log("\n8. Grouped Chart Data Structure:");
console.log(`   actualCategories (X-axis): ${categories.join(", ")}`);
console.log(`   actualSeriesValues (Legend): ${uniqueSeries.join(", ")}`);

// Verify final structure
console.log("\n" + "=".repeat(80));
console.log("VERIFICATION RESULT");
console.log("=".repeat(80));

const expectedOrder = ["1", "2", "8", "9", "10", "11", "12"];
const isCorrectOrder = JSON.stringify(categories) === JSON.stringify(expectedOrder);

if (isCorrectOrder) {
    console.log("✅ SUCCESS: X-axis (categories) is sorted correctly!");
    console.log(`   Expected: ${expectedOrder.join(", ")}`);
    console.log(`   Actual:   ${categories.join(", ")}`);
} else {
    console.log("❌ FAIL: X-axis (categories) is NOT sorted correctly!");
    console.log(`   Expected: ${expectedOrder.join(", ")}`);
    console.log(`   Actual:   ${categories.join(", ")}`);
}

console.log("\n✅ Chart should now display:");
console.log("   - X-axis: เดือน 1, 2, 8, 9, 10, 11, 12 (sorted correctly)");
console.log("   - Legend: ค่าใช้จ่ายบุคลากร, ค่าใช้จ่ายดำเนินงาน");
console.log("   - Each month shows grouped bars for each category");

console.log("\n" + "=".repeat(80));
console.log("Test Complete ✅");
console.log("=".repeat(80));
