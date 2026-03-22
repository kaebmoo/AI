# NT AI Assistant - Data Dictionary

## Document Information

| Item         | Value               |
| ------------ | ------------------- |
| Version      | 2.0                 |
| Last Updated | 2026-03-22          |
| Database     | nt_fi_report.sqlite |

> This dictionary documents the business data views that AI queries against.
> The system uses **views** (not raw tables) as defined in `schema_contexts.main_view`.

---

## Multi-Context Overview

| Context | main_view | Description |
|---|---|---|
| revenue | `revenue_search` | รายได้ NT แยกตามหน่วยงาน, ผลิตภัณฑ์, บัญชี |
| expense | `v_expense_mart` | ค่าใช้จ่าย NT แยกตามหน่วยงาน, บัญชี |
| pl_costtype | `v_pl_costtype_nt_mth_clean` | กำไรขาดทุนแยกตาม cost type รายเดือน |
| transfer price | `v_transfer_price` | ราคาโอนภายในระหว่างหน่วยงาน |

---

## View: revenue_search

### Overview

View รายได้ NT — ใช้เป็น main_view สำหรับ revenue context
Source table: `revenue` (column names เป็น lowercase ใน view, UPPERCASE ใน raw table)

### Time Columns

| Column | Type    | Format  | Example       | Description                     |
| ------ | ------- | ------- | ------------- | ------------------------------- |
| year   | INTEGER | YYYY    | 2025          | ปี ค.ศ. (พ.ศ. = year + 543)    |
| month  | INTEGER | M       | 1             | เดือน (1-12)                    |

### Organization Columns

**Hierarchy: division > organization_group > department > section > cost_center**

| Column                  | Type | Example                                          | Description         |
| ----------------------- | ---- | ------------------------------------------------ | ------------------- |
| division                | TEXT | "สายงานบริหารองค์กร"                             | สายงาน              |
| organization_group      | TEXT | "กลุ่มเลขานุการและบริหารงานกลาง"                 | กลุ่ม               |
| department              | TEXT | "ฝ่ายเลขานุการผู้บริหาร"                         | ฝ่าย                |
| section                 | TEXT | "ส่วนการประชุมผู้บริหาร"                         | ส่วน                |
| cost_center             | TEXT | "1C00104"                                        | รหัสศูนย์ต้นทุน     |
| division_abbr           | TEXT | "บ."                                             | ชื่อย่อสายงาน       |
| organization_group_abbr | TEXT | "ขบ."                                            | ชื่อย่อกลุ่ม        |
| department_abbr         | TEXT | "ลขบ."                                           | ชื่อย่อฝ่าย         |
| section_abbr            | TEXT | "ปลขบ."                                          | ชื่อย่อส่วน         |
| business_unit           | TEXT | "กลุ่มสนับสนุน"                                  | กลุ่มธุรกิจหลัก     |
| account_category        | TEXT | "R10 ผลตอบแทนทางการเงินและรายได้อื่น"            | หมวดบัญชี           |

### Product & Business Columns

**Product Hierarchy: BUSINESS_GROUP > SERVICE_GROUP > PRODUCT_NAME**

| Column         | Type | Example                        | Description           |
| -------------- | ---- | ------------------------------ | --------------------- |
| BUSINESS_GROUP | TEXT | "Fixed Line & Broadband"       | กลุ่มธุรกิจ          |
| SERVICE_GROUP  | TEXT | "กลุ่มบริการ Cloud"            | กลุ่มบริการ           |
| PRODUCT_NAME   | TEXT | "Trunk Radio"                  | ชื่อผลิตภัณฑ์        |
| PRODUCT_KEY    | TEXT | "192020001"                    | รหัสผลิตภัณฑ์        |
| PRODUCT        | TEXT | "192020001 รายได้อื่น"         | รหัส+ชื่อ            |
| ITEM           | TEXT | "8"                            | รหัสหมวดธุรกิจ       |
| SUB_ITEM       | TEXT | "8.2"                          | รหัสหมวดย่อย         |

**Product Hierarchy Warning:**

```
BUSINESS_GROUP > SERVICE_GROUP > PRODUCT_NAME

ห้ามใช้ OR ข้าม level:
WHERE BUSINESS_GROUP = 'Fixed Line' OR PRODUCT_NAME = 'Trunk Radio'
→ ตัวเลขจะพอง! (นับ Fixed Line ทั้งหมด + Trunk Radio ซ้ำ)

ให้ใช้ AND:
WHERE BUSINESS_GROUP = 'Fixed Line' AND PRODUCT_NAME = 'Trunk Radio'
```

Hierarchy levels ถูกกำหนดใน `master_hierarchy` table — ดู [DATABASE_TABLES_GUIDE.md](DATABASE_TABLES_GUIDE.md) section 7

### Accounting Columns

| Column   | Type | Example                                          | Description     |
| -------- | ---- | ------------------------------------------------ | --------------- |
| GL_CODE  | TEXT | "49901101"                                       | รหัสบัญชี GL   |
| GL_NAME  | TEXT | "ดอกเบี้ยเงินให้กู้ยืม-กองทุนสวัสดิการ"        | ชื่อบัญชี      |
| GL_GROUP | TEXT | "ผลตอบแทนทางการเงินและรายได้อื่น"               | กลุ่มบัญชี     |
| TYPE     | TEXT | "รายได้"                                         | ประเภทรายการ   |

### Value Columns

| Column  | Type | Example | Can SUM? | Description                  |
| ------- | ---- | ------- | -------- | ---------------------------- |
| revenue | REAL | 162.24  | Yes      | มูลค่ารายได้ (**หน่วยบาท**) |

**หน่วยเป็นบาท** ไม่ใช่ล้านบาท

---

## View: v_expense_mart

### Overview

View ค่าใช้จ่าย NT — ใช้เป็น main_view สำหรับ expense context
Source table: `expense` (column names เป็น lowercase ใน view)

### Columns

| Column                  | Type    | Description                    | Source Column   |
| ----------------------- | ------- | ------------------------------ | --------------- |
| year                    | INTEGER | ปี ค.ศ.                        | YEAR            |
| month                   | INTEGER | เดือน (1-12)                   | MONTH           |
| date                    | INTEGER | Unix timestamp ms              | DATE            |
| division                | TEXT    | สายงาน                         | DIVISION        |
| organization_group      | TEXT    | กลุ่ม                          | GROUP           |
| department              | TEXT    | ฝ่าย                           | DEPARTMENT      |
| section                 | TEXT    | ส่วน                           | SECTION         |
| cost_center             | TEXT    | รหัสศูนย์ต้นทุน                | COST_CENTER     |
| division_abbr           | TEXT    | ชื่อย่อสายงาน                  | DIVISION_ABBR   |
| organization_group_abbr | TEXT    | ชื่อย่อกลุ่ม                   | GROUP_ABBR      |
| department_abbr         | TEXT    | ชื่อย่อฝ่าย                    | DEPARTMENT_ABBR |
| section_abbr            | TEXT    | ชื่อย่อส่วน                    | SECTION_ABBR    |
| business_group          | TEXT    | กลุ่มธุรกิจ                    | กลุ่มธุรกิจ     |
| gl_code                 | TEXT    | รหัสบัญชี GL                   | GL_CODE         |
| account_name            | TEXT    | ชื่อบัญชี                      | GL_NAME_NT1     |
| account_group_name      | TEXT    | กลุ่มบัญชี                     | GROUP_NAME      |
| account_group_code      | TEXT    | รหัสกลุ่มบัญชี                 | CODE_GROUP      |
| nt                      | TEXT    | บริษัท                         | NT              |
| type                    | TEXT    | ประเภทรายการ                   | TYPE            |
| expense                 | REAL    | ยอดค่าใช้จ่าย (**หน่วยบาท**)   | EXPENSE_VALUE   |

**Visualization Rule:** ห้ามใช้ `gl_code` เป็น Label/Legend ในกราฟ — ให้ใช้ `account_name` เสมอ

---

## View: v_pl_costtype_nt_mth_clean

### Overview

View กำไรขาดทุน (P&L) แยกตาม cost type รายเดือน — ใช้เป็น main_view สำหรับ pl_costtype context
Source table chain: `TRN_PL_COSTTYPE_NT_MTH` → `v_pl_costtype_nt_mth` → `v_pl_costtype_nt_mth_clean`

### Columns

| Column        | Type    | Description           | Source Column  |
| ------------- | ------- | --------------------- | -------------- |
| report_date   | INTEGER | วันที่ (Unix ms)      | DATE           |
| report_year   | INTEGER | ปี ค.ศ.               | YEAR           |
| report_month  | INTEGER | เดือน (1-12)          | MONTH          |
| main_group    | TEXT    | กลุ่มหลัก             | GROUP          |
| sub_group     | TEXT    | กลุ่มย่อย (cleaned)   | SUB_GROUP      |
| business_unit | TEXT    | หน่วยธุรกิจ           | BU             |
| service_group | TEXT    | กลุ่มบริการ           | SERVICE_GROUP  |
| product_id    | TEXT    | รหัสผลิตภัณฑ์         | PRODUCT_KEY    |
| product_name  | TEXT    | ชื่อผลิตภัณฑ์         | PRODUCT_NAME   |
| alliance_flag | TEXT    | สถานะ Alliance (Y/N)  | ALLIE          |
| amount_value  | REAL    | มูลค่า (**หน่วยบาท**) | VALUE          |

---

## View: v_transfer_price

### Overview

View ราคาโอนภายในระหว่างหน่วยงาน — ใช้เป็น main_view สำหรับ transfer price context
Source table: `transfer_price`

**Transfer Price Convention:**
- "ขาย" (selling side) → `owner_*` columns
- "ซื้อ/ใช้" (buying side) → `user_*` columns

### Columns

| Column           | Type    | Description               | Source Column               |
| ---------------- | ------- | ------------------------- | --------------------------- |
| year             | INTEGER | ปี ค.ศ.                   | YEAR                        |
| month            | INTEGER | เดือน (1-12)              | MONTH                       |
| tp_product_id    | TEXT    | รหัสผลิตภัณฑ์ TP          | TRANSFER_PRICE_PRODUCT_ID   |
| product_name     | TEXT    | ชื่อผลิตภัณฑ์             | Product                     |
| sub_product_name | TEXT    | ชื่อผลิตภัณฑ์ย่อย         | Sub_Product                 |
| unit             | TEXT    | หน่วยนับ                  | Unit                        |
| unit_price       | REAL    | ราคาต่อหน่วย              | Unit_Price                  |
| total_price_value| REAL    | มูลค่ารวม (**หน่วยบาท**)  | PRICE_VALUE                 |
| quantity         | REAL    | จำนวน                     | QUANTITY                    |
| owner_cc_unit    | TEXT    | หน่วยศูนย์ต้นทุนผู้ขาย   | UNIT_COST_CENTER_OWNER      |
| owner_cost_center| TEXT    | ศูนย์ต้นทุนผู้ขาย         | COST_CENTER_Owner           |
| owner_division   | TEXT    | สายงานผู้ขาย              | DIVISION_Owner              |
| owner_department | TEXT    | ฝ่ายผู้ขาย                | DEPARTMENT_Owner            |
| user_cc_unit     | TEXT    | หน่วยศูนย์ต้นทุนผู้ซื้อ  | UNIT_COST_CENTER_USER       |
| user_cost_center | TEXT    | ศูนย์ต้นทุนผู้ซื้อ        | COST_CENTER_User            |
| user_division    | TEXT    | สายงานผู้ซื้อ             | DIVISION_User               |
| user_department  | TEXT    | ฝ่ายผู้ซื้อ               | DEPARTMENT_User             |

---

## Common Queries

### Revenue — รายได้รวมแยกตามเดือน

```sql
SELECT year, month, SUM(revenue) as total
FROM revenue_search
WHERE year = 2025
GROUP BY year, month
ORDER BY year, month;
```

### Revenue — รายได้แยกตามกลุ่มธุรกิจ (hierarchy-aware)

```sql
-- Level 0: Business Group
SELECT BUSINESS_GROUP, SUM(revenue) as total
FROM revenue_search
WHERE year = 2025 AND month = 1
GROUP BY BUSINESS_GROUP
ORDER BY total DESC;

-- Level 1: Drill down to Service Group within a Business Group
SELECT SERVICE_GROUP, SUM(revenue) as total
FROM revenue_search
WHERE year = 2025 AND BUSINESS_GROUP = 'Fixed Line & Broadband'
GROUP BY SERVICE_GROUP
ORDER BY total DESC;

-- Level 2: Drill down to Product within a Service Group
SELECT PRODUCT_NAME, SUM(revenue) as total
FROM revenue_search
WHERE year = 2025 AND SERVICE_GROUP = 'กลุ่มบริการ Cloud'
GROUP BY PRODUCT_NAME
ORDER BY total DESC;
```

### Revenue — รายได้แยกตามสายงาน

```sql
SELECT division, SUM(revenue) as total
FROM revenue_search
WHERE year = 2025
GROUP BY division
ORDER BY total DESC;
```

### Expense — ค่าใช้จ่ายแยกตามกลุ่มบัญชี

```sql
SELECT account_group_name, SUM(expense) as total
FROM v_expense_mart
WHERE year = 2025 AND month = 1
GROUP BY account_group_name
ORDER BY total DESC;
```

### P&L — กำไรขาดทุนแยกตาม main_group

```sql
SELECT main_group, SUM(amount_value) as total
FROM v_pl_costtype_nt_mth_clean
WHERE report_year = 2025
GROUP BY main_group
ORDER BY total DESC;
```

---

## Business Rules

1. **Date**: ใช้ `year`, `month` โดยตรง — ไม่ต้องแปลง DATE
2. **ปี พ.ศ.**: `year + 543` (เช่น 2025 → 2568)
3. **หน่วยเงิน**: บาท (ไม่ใช่ล้านบาท) — ทุก view
4. **Thai Columns ใน raw table**: ต้องใช้ double quotes `"กลุ่มธุรกิจ"`, `"หมวดบัญชี"` (view columns เป็น lowercase ไม่ต้อง quote)
5. **Hierarchy**: ห้าม OR ข้าม level — ใช้ AND เสมอ
6. **Transfer Price**: "ขาย" → `owner_*`, "ซื้อ" → `user_*`

---

## Version History

| Date       | Version | Changes                                                      |
| ---------- | ------- | ------------------------------------------------------------ |
| 2025-01-26 | 1.0     | Initial — revenue table only                                 |
| 2026-03-22 | 2.0     | Update to views, add expense/P&L/transfer_price, hierarchy   |
