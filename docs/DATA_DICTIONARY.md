# NT Revenue Assistant - Data Dictionary

## Document Information

| Item | Value |
|------|-------|
| Version | 1.0 |
| Last Updated | 2025-01-26 |
| Database | SQLite |
| Table | revenue |

---

## Table: revenue

### Overview
ข้อมูลรายได้ NT แยกตามหน่วยงาน, ผลิตภัณฑ์, และรหัสบัญชี รายเดือน

---

## Column Definitions

### 📅 Time Columns

| Column | Type | Format | Example | Description |
|--------|------|--------|---------|-------------|
| YEAR | INTEGER | YYYY | 2025 | ปี ค.ศ. (พ.ศ. = YEAR + 543) |
| MONTH | INTEGER | M | 1 | เดือน (1-12) |
| DATE | INTEGER | Unix ms | 1735689600000 | วันที่ (**ต้องแปลง**) |

**Date Conversion:**
```sql
-- แปลง Unix timestamp (ms) เป็นวันที่
SELECT date(DATE / 1000, 'unixepoch') FROM revenue
```

---

### 🏢 Organization Columns

**Hierarchy: DIVISION → GROUP → DEPARTMENT → SECTION → COST_CENTER**

| Column | Type | Example | Description | Level |
|--------|------|---------|-------------|-------|
| DIVISION | TEXT | "สายงานบริหารองค์กร" | สายงาน | 1 |
| GROUP | TEXT | "กลุ่มเลขานุการและบริหารงานกลาง" | กลุ่ม | 2 |
| DEPARTMENT | TEXT | "ฝ่ายเลขานุการผู้บริหาร" | ฝ่าย | 3 |
| SECTION | TEXT | "ส่วนการประชุมผู้บริหาร" | ส่วน | 4 |
| COST_CENTER | TEXT | "1C00104" | รหัสศูนย์ต้นทุน | 5 |
| COST_CENTER_DEPARTMENT | TEXT | "1C00100" | รหัสฝ่าย | |
| DIVISION_ABBR | TEXT | "บ." | ชื่อย่อสายงาน | |
| GROUP_ABBR | TEXT | "ขบ." | ชื่อย่อกลุ่ม | |
| DEPARTMENT_ABBR | TEXT | "ลขบ." | ชื่อย่อฝ่าย | |
| SECTION_ABBR | TEXT | "ปลขบ." | ชื่อย่อส่วน | |
| กลุ่มธุรกิจ | TEXT | "กลุ่มสนับสนุน" | กลุ่มธุรกิจหลัก | Top |

---

### 📦 Product & Business Columns

| Column | Type | Example | Description |
|--------|------|---------|-------------|
| PRODUCT_KEY | TEXT | "192020001" | รหัสผลิตภัณฑ์ |
| SUB_PRODUCT_KEY | TEXT | "1" | รหัสผลิตภัณฑ์ย่อย |
| PRODUCT_NAME | TEXT | "รายได้อื่น" | ชื่อผลิตภัณฑ์ |
| SUB_PRODUCT_NAME | TEXT | "รายได้อื่น" | ชื่อผลิตภัณฑ์ย่อย |
| PRODUCT | TEXT | "192020001 รายได้อื่น" | รหัส+ชื่อ |
| SUB_PRODUCT | TEXT | "1 รายได้อื่น" | รหัส+ชื่อย่อย |
| ITEM | TEXT | "8" | รหัสหมวดธุรกิจ |
| SUB_ITEM | TEXT | "8.2" | รหัสหมวดย่อย |
| BUSINESS_GROUP | TEXT | "รายได้อื่น" | กลุ่มธุรกิจ |
| BUSINESS | TEXT | "8 รายได้อื่น" | รหัส+ชื่อธุรกิจ |
| SERVICE | TEXT | "8.2 รายได้อื่น" | รหัส+ชื่อบริการ |
| SERVICE_GROUP | TEXT | "รายได้อื่น" | กลุ่มบริการ |
| REVENUE_GROUP_TYPE | TEXT | "รายได้อื่น" | ประเภทกลุ่มรายได้ |

---

### 📊 Accounting Columns

| Column | Type | Example | Description |
|--------|------|---------|-------------|
| REPORT_CODE | TEXT | "R10" | รหัสรายงาน |
| GL_CODE | TEXT | "49901101" | รหัสบัญชี GL |
| GL_NAME | TEXT | "ดอกเบี้ยเงินให้กู้ยืม-กองทุนสวัสดิการ" | ชื่อบัญชี |
| GL_GROUP | TEXT | "ผลตอบแทนทางการเงินและรายได้อื่น" | กลุ่มบัญชี |
| หมวดบัญชี | TEXT | "R10 ผลตอบแทนทางการเงินและรายได้อื่น" | หมวด (รหัส+ชื่อ) |
| NT | TEXT | "NT" | บริษัท |
| TYPE | TEXT | "รายได้" | ประเภทรายการ |

---

### 💰 Value Columns

| Column | Type | Example | Can SUM? | Description |
|--------|------|---------|----------|-------------|
| REVENUE_VALUE | REAL | 162.24 | ✅ Yes | มูลค่ารายได้ (**บาท**) |
| AMOUNT | REAL | 162.24 | ✅ Yes | จำนวนเงิน (**บาท**) |

⚠️ **หน่วยเป็นบาท** ไม่ใช่ล้านบาท

---

## Common Queries

```sql
-- รายได้รวมแยกตามเดือน
SELECT YEAR, MONTH, SUM(REVENUE_VALUE) as total
FROM revenue GROUP BY YEAR, MONTH ORDER BY YEAR, MONTH;

-- รายได้แยกตามกลุ่มธุรกิจ
SELECT "กลุ่มธุรกิจ", SUM(REVENUE_VALUE) as total
FROM revenue WHERE YEAR = 2025 AND MONTH = 1
GROUP BY "กลุ่มธุรกิจ" ORDER BY total DESC;

-- รายได้แยกตามสายงาน
SELECT DIVISION, SUM(REVENUE_VALUE) as total
FROM revenue WHERE YEAR = 2025
GROUP BY DIVISION ORDER BY total DESC;

-- รายได้แยกตามหมวดบัญชี
SELECT REPORT_CODE, "หมวดบัญชี", SUM(REVENUE_VALUE) as total
FROM revenue GROUP BY REPORT_CODE, "หมวดบัญชี" ORDER BY total DESC;
```

---

## Business Rules

1. **Date**: ใช้ `YEAR`, `MONTH` โดยตรง หรือแปลง `DATE` ด้วย `date(DATE/1000, 'unixepoch')`
2. **ปี พ.ศ.**: `YEAR + 543` (เช่น 2025 → 2568)
3. **หน่วยเงิน**: บาท (ไม่ใช่ล้านบาท)
4. **Thai Columns**: ใช้ double quotes `"กลุ่มธุรกิจ"`, `"หมวดบัญชี"`
5. **REVENUE_VALUE ≈ AMOUNT**: ปกติมีค่าเท่ากัน

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2025-01-26 | 1.0 | Initial |
