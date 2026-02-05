#!/usr/bin/env python3
"""
Test Program to Verify Visualization Issues
- Chart: Month ordering and Legend/Label display
- Table: Row/Column mapping

User Complaint:
1. Graph แกน x คือเดือน แต่เรียงลำดับไม่ถูก
2. Legend แสดงสีแต่ข้อความเป็นเดือนแทนที่จะเป็นหมวดบัญชี
3. ตาราง column เป็นเดือน แต่ row เป็นลำดับเดือนแทนที่จะเป็นหมวดบัญชี
"""

import json

# ==================== Test Case 1: Month Ordering ====================
print("=" * 80)
print("TEST 1: Month Ordering Issue")
print("=" * 80)

# Simulate data with Thai month names or numeric months
test_months_numeric = ["8", "9", "10", "11", "12", "1", "2", "3"]
test_months_thai = ["สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม", "มกราคม", "กุมภาพันธ์", "มีนาคม"]
test_months_mixed = ["เดือน 8", "เดือน 9", "เดือน 10", "เดือน 11", "เดือน 12", "เดือน 1", "เดือน 2"]

print("\n1.1 Numeric Months (as strings):")
print(f"Original: {test_months_numeric}")
sorted_numeric = sorted(test_months_numeric, key=lambda x: int(x))
print(f"Sorted (correct): {sorted_numeric}")
wrong_sorted = sorted(test_months_numeric)
print(f"String sort (wrong): {wrong_sorted}")

print("\n1.2 Thai Month Names:")
print(f"Original: {test_months_thai}")
# Frontend uses: Array.from(new Set(...)).sort((a, b) => Number(a) - Number(b))
# This will fail for Thai names since Number("สิงหาคม") = NaN
try:
    sorted_thai = sorted(test_months_thai, key=lambda x: float(x))
except ValueError:
    print(f"❌ PROBLEM: Cannot sort Thai month names numerically!")
    print(f"String sort result: {sorted(test_months_thai)}")

print("\n1.3 Mixed Format 'เดือน X':")
print(f"Original: {test_months_mixed}")
# Frontend tries Number(a) - Number(b) which will be NaN for "เดือน 8"
def extract_month_number(s):
    """Extract month number from 'เดือน X' format"""
    import re
    match = re.search(r'\d+', s)
    return int(match.group()) if match else 0

sorted_mixed = sorted(test_months_mixed, key=extract_month_number)
print(f"Sorted (needs custom logic): {sorted_mixed}")


# ==================== Test Case 2: AI Config Issue ====================
print("\n" + "=" * 80)
print("TEST 2: Chart Config - Category vs Series Confusion")
print("=" * 80)

# Simulate a query: "ค่าใช้จ่ายรายหมวดบัญชี รายเดือน"
# Expected: X-axis = เดือน (time), Legend = หมวดบัญชี (categories)
# But AI might return: X-axis = หมวดบัญชี, Series = เดือน (WRONG!)

sample_data_long = [
    {"เดือน": "1", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1000000},
    {"เดือน": "2", "หมวดบัญชี": "ค่าใช้จ่ายบุคลากร", "ยอดค่าใช้จ่าย": 1200000},
    {"เดือน": "1", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 500000},
    {"เดือน": "2", "หมวดบัญชี": "ค่าใช้จ่ายดำเนินงาน", "ยอดค่าใช้จ่าย": 550000},
]

print("\n2.1 Sample Data (Long Format):")
print(json.dumps(sample_data_long[:2], ensure_ascii=False, indent=2))

print("\n2.2 Correct AI Config:")
correct_config = {
    "visualization": "grouped_bar",
    "chart_config": {
        "category_column": "เดือน",  # X-axis = Time
        "measure_column": "ยอดค่าใช้จ่าย",
        "series_column": "หมวดบัญชี"  # Legend = Categories
    }
}
print(json.dumps(correct_config, ensure_ascii=False, indent=2))
print("✅ Result: X-axis shows months, Legend shows account categories")

print("\n2.3 WRONG AI Config (Swapped):")
wrong_config = {
    "visualization": "grouped_bar",
    "chart_config": {
        "category_column": "หมวดบัญชี",  # WRONG: Category as X-axis
        "measure_column": "ยอดค่าใช้จ่าย",
        "series_column": "เดือน"  # WRONG: Time as Legend
    }
}
print(json.dumps(wrong_config, ensure_ascii=False, indent=2))
print("❌ PROBLEM: X-axis shows categories, Legend shows months (user complaint!)")

# Check if backend swap logic would catch this
cat_col = wrong_config["chart_config"]["category_column"].lower()
series_col = wrong_config["chart_config"]["series_column"].lower()
time_keys = ['month', 'year', 'date', 'เดือน', 'ปี', 'วันที่']

is_cat_time = any(t in cat_col for t in time_keys)
is_series_time = any(t in series_col for t in time_keys)

print(f"\nBackend Swap Logic Check:")
print(f"  Category='{cat_col}' -> is_time={is_cat_time}")
print(f"  Series='{series_col}' -> is_time={is_series_time}")

if is_series_time and not is_cat_time:
    print("  ✅ Backend SHOULD swap these columns!")
else:
    print("  ❌ Backend would NOT swap (logic gap?)")


# ==================== Test Case 3: Table Row Detection ====================
print("\n" + "=" * 80)
print("TEST 3: Table Crosstab - Row Detection Issue")
print("=" * 80)

# Frontend DataTable.tsx logic:
# - Detects monthKey, yearKey
# - Filters categoryKeys = dimensions WITHOUT time keywords
# - Sets rowKey = categoryKeys[0]

print("\n3.1 Column Detection Logic:")
columns = ["เดือน", "หมวดบัญชี", "ยอดค่าใช้จ่าย"]
print(f"Columns: {columns}")

# Simulate frontend logic
measure_patterns = ['total', 'revenue', 'amount', 'value', 'ยอดรวม', 'ยอด']
def is_measure(k):
    return any(term in k.lower() for term in measure_patterns)

def is_time(k):
    return any(term in k.lower() for term in ['year', 'month', 'date', 'เดือน', 'ปี'])

month_key = next((k for k in columns if is_time(k) and not is_measure(k)), None)
dimension_keys = [k for k in columns if not is_measure(k)]
category_keys = [k for k in dimension_keys if not is_time(k)]

print(f"\nDetected:")
print(f"  monthKey = {month_key}")
print(f"  dimensionKeys = {dimension_keys}")
print(f"  categoryKeys = {category_keys}")

if category_keys:
    row_key = category_keys[0]
    print(f"\n✅ Crosstab rowKey = '{row_key}'")
    print(f"✅ Expected Table: Rows = {row_key}, Columns = Month periods")
else:
    print(f"\n❌ PROBLEM: No category key detected! Rows would default to something else")


# ==================== Test Case 4: Edge Cases ====================
print("\n" + "=" * 80)
print("TEST 4: Edge Cases That Could Break")
print("=" * 80)

print("\n4.1 Column Names Without Keywords:")
edge_columns = ["M", "ACC", "VAL"]  # Abbreviated, no keywords
print(f"Columns: {edge_columns}")
month_key = next((k for k in edge_columns if is_time(k)), None)
category_keys = [k for k in edge_columns if not is_measure(k) and not is_time(k)]
print(f"  monthKey = {month_key}")
print(f"  categoryKeys = {category_keys}")
if not month_key:
    print("  ❌ PROBLEM: Month column not detected!")

print("\n4.2 English Column Names:")
english_columns = ["Month", "Account", "Amount"]
print(f"Columns: {english_columns}")
month_key = next((k for k in english_columns if is_time(k)), None)
category_keys = [k for k in english_columns if not is_measure(k) and not is_time(k)]
print(f"  monthKey = {month_key}")
print(f"  categoryKeys = {category_keys}")
print(f"  ✅ Should work: Rows = {category_keys[0] if category_keys else 'N/A'}")


# ==================== Summary ====================
print("\n" + "=" * 80)
print("SUMMARY OF ISSUES")
print("=" * 80)
print("""
1. ❌ Month Ordering Issue:
   - Frontend sorts seriesValues with Number(a) - Number(b)
   - Fails for Thai names or "เดือน X" format
   - Only works for pure numeric strings "1", "2", etc.

2. ❌ Chart Config Swap Issue:
   - Backend has swap logic (ai_service.py:273-280)
   - Logic checks if 'เดือน' keyword exists in column names
   - BUT if AI uses different column names (M, month_id, etc.), swap won't trigger
   - Frontend trusts AI config blindly

3. ⚠️  Table Row Detection Issue:
   - Depends on keyword matching in column names
   - Works for "หมวดบัญชี", "Account"
   - Fails if columns use abbreviations or unexpected names

4. 🔍 Root Cause:
   - Heavy reliance on keyword matching (fragile)
   - No validation that AI config matches actual data structure
   - Month sorting assumes numeric strings, not formatted text

RECOMMENDED FIXES:
A. Add month name mapping for sorting (Thai ↔ Number)
B. Validate AI chart_config against actual data columns
C. Add fallback detection logic beyond keyword matching
D. Implement smarter month sorting that handles all formats
""")

print("\n" + "=" * 80)
print("Running Test Complete ✅")
print("=" * 80)
