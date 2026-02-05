#!/usr/bin/env node
/**
 * Test: Smart Unit Formatting for Tooltips
 *
 * Demonstrates how tooltip displays change based on data magnitude
 */

// Simulate formatNumberWithUnit function
function formatNumberWithUnit(value, maxValue) {
    if (maxValue >= 1_000_000_000) {
        // พันล้านบาท (Billions)
        return {
            text: (value / 1_000_000_000).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
            unit: 'พันล้านบาท'
        };
    } else if (maxValue >= 1_000_000) {
        // ล้านบาท (Millions)
        return {
            text: (value / 1_000_000).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
            unit: 'ล้านบาท'
        };
    } else if (maxValue >= 1_000) {
        // พันบาท (Thousands)
        return {
            text: (value / 1_000).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
            unit: 'พันบาท'
        };
    } else {
        // บาท (Baht)
        return {
            text: value.toLocaleString('th-TH', { minimumFractionDigits: 0, maximumFractionDigits: 0 }),
            unit: 'บาท'
        };
    }
}

console.log("=".repeat(80));
console.log("TEST: Smart Unit Formatting for Tooltips");
console.log("=".repeat(80));

// Test Case 1: Small values (บาท)
console.log("\n1. Small Dataset (หลักร้อยบาท):");
const smallData = [150, 250, 320, 180, 290];
const smallMax = Math.max(...smallData);
console.log(`   Data: ${smallData.join(", ")}`);
console.log(`   Max Value: ${smallMax.toLocaleString()} บาท`);
console.log("\n   Tooltip Display:");
smallData.forEach((val, idx) => {
    const formatted = formatNumberWithUnit(val, smallMax);
    console.log(`     Value ${idx + 1}: ${formatted.text} ${formatted.unit}`);
});

// Test Case 2: Thousands (พันบาท)
console.log("\n\n2. Medium Dataset (หลักพันบาท):");
const mediumData = [15000, 25000, 32000, 18000, 29000];
const mediumMax = Math.max(...mediumData);
console.log(`   Data: ${mediumData.map(v => v.toLocaleString()).join(", ")} บาท`);
console.log(`   Max Value: ${mediumMax.toLocaleString()} บาท`);
console.log("\n   Tooltip Display:");
mediumData.forEach((val, idx) => {
    const formatted = formatNumberWithUnit(val, mediumMax);
    console.log(`     Value ${idx + 1}: ${formatted.text} ${formatted.unit}`);
});

// Test Case 3: Millions (ล้านบาท) - MOST COMMON FOR FINANCIAL DATA
console.log("\n\n3. Large Dataset (หลักล้านบาท) - User's Use Case:");
const largeData = [1500000, 2500000, 3200000, 1800000, 2900000];
const largeMax = Math.max(...largeData);
console.log(`   Data: ${largeData.map(v => v.toLocaleString()).join(", ")} บาท`);
console.log(`   Max Value: ${largeMax.toLocaleString()} บาท`);
console.log("\n   ❌ OLD Tooltip Display (hard to read):");
largeData.forEach((val, idx) => {
    console.log(`     Value ${idx + 1}: ${val.toLocaleString('th-TH')} บาท`);
});
console.log("\n   ✅ NEW Tooltip Display (easier to read):");
largeData.forEach((val, idx) => {
    const formatted = formatNumberWithUnit(val, largeMax);
    console.log(`     Value ${idx + 1}: ${formatted.text} ${formatted.unit}`);
});

// Test Case 4: Billions (พันล้านบาท)
console.log("\n\n4. Very Large Dataset (หลักพันล้านบาท):");
const veryLargeData = [1500000000, 2500000000, 3200000000, 1800000000, 2900000000];
const veryLargeMax = Math.max(...veryLargeData);
console.log(`   Data: ${veryLargeData.map(v => v.toLocaleString()).join(", ")} บาท`);
console.log(`   Max Value: ${veryLargeMax.toLocaleString()} บาท`);
console.log("\n   ❌ OLD Tooltip Display (too long):");
console.log(`     Value 1: ${veryLargeData[0].toLocaleString('th-TH')} บาท`);
console.log("\n   ✅ NEW Tooltip Display:");
veryLargeData.forEach((val, idx) => {
    const formatted = formatNumberWithUnit(val, veryLargeMax);
    console.log(`     Value ${idx + 1}: ${formatted.text} ${formatted.unit}`);
});

// Test Case 5: Real-world example - ค่าใช้จ่ายรายหมวดบัญชี
console.log("\n\n5. Real Example: ค่าใช้จ่ายรายหมวดบัญชี รายเดือน");
const expenses = {
    "ค่าใช้จ่ายบุคลากร": [
        { month: 1, amount: 1500000 },
        { month: 2, amount: 1600000 },
        { month: 8, amount: 1200000 },
    ],
    "ค่าใช้จ่ายดำเนินงาน": [
        { month: 1, amount: 500000 },
        { month: 2, amount: 650000 },
        { month: 8, amount: 550000 },
    ]
};

const allValues = Object.values(expenses).flatMap(items => items.map(i => i.amount));
const expenseMax = Math.max(...allValues);

console.log(`   Max Value: ${expenseMax.toLocaleString()} บาท`);
console.log("\n   Grouped Bar Chart Tooltip:");
console.log("   ┌─────────────────────────────┐");
console.log("   │     เดือน 1                │");
console.log("   ├─────────────────────────────┤");

Object.entries(expenses).forEach(([category, items]) => {
    const jan = items.find(i => i.month === 1);
    if (jan) {
        const formatted = formatNumberWithUnit(jan.amount, expenseMax);
        console.log(`   │ ⬛ ${category}`);
        console.log(`   │    ${formatted.text} ${formatted.unit.padEnd(15)}│`);
    }
});

console.log("   └─────────────────────────────┘");

console.log("\n" + "=".repeat(80));
console.log("BENEFITS");
console.log("=".repeat(80));
console.log(`
✅ Improved Readability:
   - OLD: "1,500,000 บาท" (7 digits, hard to scan)
   - NEW: "1.50 ล้านบาท" (4 characters, easy to read)

✅ Consistent Precision:
   - Always shows 2 decimal places for millions/billions
   - Makes comparing values easier

✅ Automatic Detection:
   - Analyzes maxValue in dataset
   - Chooses appropriate unit automatically
   - No manual configuration needed

✅ Scales to All Magnitudes:
   - < 1K: บาท (no decimals)
   - 1K-1M: พันบาท (2 decimals)
   - 1M-1B: ล้านบาท (2 decimals)
   - > 1B: พันล้านบาท (2 decimals)
`);

console.log("=".repeat(80));
console.log("Test Complete ✅");
console.log("=".repeat(80));
