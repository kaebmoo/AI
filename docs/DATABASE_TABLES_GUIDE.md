# Database Tables Guide

## สารบัญ

1. [schema_metadata](#1-schema_metadata)
2. [schema_business_rules](#2-schema_business_rules)
3. [schema_semantic_mapping](#3-schema_semantic_mapping)
4. [schema_context_tables](#4-schema_context_tables)
5. [golden_examples](#5-golden_examples)

---

## 1. schema_metadata

### หน้าที่

เก็บ **metadata ของคอลัมน์** ในฐานข้อมูลเพื่อให้ AI เข้าใจโครงสร้างข้อมูลและการใช้งานแต่ละคอลัมน์

### โครงสร้างตาราง

```sql
CREATE TABLE schema_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,           -- ชื่อตาราง (เช่น "revenue")
    column_name TEXT NOT NULL,          -- ชื่อคอลัมน์ (เช่น "YEAR", "REVENUE_VALUE")
    data_type TEXT,                     -- ชนิดข้อมูล (INTEGER, TEXT, REAL)
    display_name_th TEXT,               -- ชื่อแสดงภาษาไทย (เช่น "ปี")
    display_name_en TEXT,               -- ชื่อแสดงภาษาอังกฤษ (เช่น "Year")
    description TEXT,                   -- คำอธิบายคอลัมน์
    format_hint TEXT,                   -- คำแนะนำรูปแบบ (เช่น "YYYY", "Code")
    example_value TEXT,                 -- ค่าตัวอย่าง (เช่น "2025")
    is_summable INTEGER DEFAULT 1,     -- สามารถใช้ SUM() ได้หรือไม่ (1=ได้, 0=ไม่ได้)
    is_groupable INTEGER DEFAULT 1,    -- สามารถใช้ GROUP BY ได้หรือไม่
    hierarchy_level INTEGER,            -- ระดับลำดับชั้น (สำหรับ org hierarchy)
    special_notes TEXT,                 -- หมายเหตุพิเศษ
    conversion_sql TEXT,                -- SQL สำหรับแปลงค่า (ถ้ามี)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_name, column_name)
);
```

### การใช้งาน

#### 1. ใช้ในการสร้าง System Prompt

```python
from app.services.schema_service import SchemaService

service = SchemaService(db_path="revenue.sqlite")
metadata = service.get_schema_metadata(table_name="revenue")

# สร้าง schema text สำหรับ AI
schema_text = service.build_schema_text(table_name="revenue")
```

#### 2. ใช้ในการตรวจสอบความถูกต้องของ SQL

- ตรวจสอบว่าคอลัมน์สามารถใช้ `SUM()` ได้หรือไม่
- ตรวจสอบว่าคอลัมน์สามารถใช้ `GROUP BY` ได้หรือไม่
- ดูว่าต้องมีการแปลงค่าหรือไม่ (เช่น DATE ต้องแปลงจาก Unix timestamp)

#### 3. ตัวอย่างข้อมูล

```sql
-- Column: YEAR
table_name: revenue
column_name: YEAR
data_type: INTEGER
display_name_th: ปี
display_name_en: Year
is_summable: 0  -- ไม่สามารถ SUM ได้
is_groupable: 1 -- สามารถ GROUP BY ได้
special_notes: ปี พ.ศ. = YEAR + 543

-- Column: REVENUE_VALUE
table_name: revenue
column_name: REVENUE_VALUE
data_type: REAL
display_name_th: มูลค่ารายได้
is_summable: 1  -- สามารถ SUM ได้
is_groupable: 0 -- ไม่ควร GROUP BY
special_notes: หน่วยเป็นบาท
```

### ประโยชน์

✅ AI รู้ว่าคอลัมน์ไหนคืออะไร (ชื่อไทย/อังกฤษ)
✅ AI รู้ว่าคอลัมน์ไหนใช้ SUM ได้ ไหนใช้ไม่ได้
✅ AI รู้ว่าต้องแปลงค่าอย่างไร (เช่น DATE, ปี พ.ศ.)
✅ ลด error จากการใช้คอลัมน์ผิดประเภท

---

## 2. schema_business_rules

### หน้าที่

เก็บ **กฎทางธุรกิจและกฎการสร้าง SQL** เพื่อให้ AI สร้าง SQL ที่ถูกต้องตามข้อกำหนด

### โครงสร้างตาราง

```sql
CREATE TABLE schema_business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL UNIQUE,     -- รหัสกฎ (เช่น "DATE_CONVERT")
    rule_name TEXT NOT NULL,            -- ชื่อกฎ (เช่น "แปลง DATE ก่อนใช้")
    rule_description TEXT NOT NULL,     -- คำอธิบายกฎ
    applies_to TEXT,                    -- ใช้กับคอลัมน์ไหนบ้าง (comma-separated)
    example_correct TEXT,               -- ตัวอย่าง SQL ที่ถูกต้อง
    example_wrong TEXT,                 -- ตัวอย่าง SQL ที่ผิด
    severity TEXT DEFAULT 'warning',    -- ระดับความสำคัญ (error, warning, info)
    is_active INTEGER DEFAULT 1
);
```

### การใช้งาน

#### 1. ใช้ในการสร้าง System Prompt

```python
service = SchemaService(db_path="revenue.sqlite")
rules = service.get_business_rules(table_name="revenue")

# สร้าง business rules text สำหรับ AI
rules_text = service.build_business_rules_text()
```

#### 2. ตัวอย่างกฎสำคัญ

##### กฎ 1: DATE_CONVERT

```yaml
rule_code: DATE_CONVERT
rule_name: แปลง DATE ก่อนใช้
severity: warning
applies_to: DATE

✅ ถูกต้อง:
SELECT date(DATE / 1000, 'unixepoch') FROM revenue

❌ ผิด:
SELECT DATE FROM revenue  -- จะได้ตัวเลข Unix timestamp
```

##### กฎ 2: THAI_COLUMN

```yaml
rule_code: THAI_COLUMN
rule_name: Column ภาษาไทยต้อง quote
severity: error
applies_to: กลุ่มธุรกิจ, หมวดบัญชี

✅ ถูกต้อง:
SELECT "กลุ่มธุรกิจ" FROM revenue

❌ ผิด:
SELECT กลุ่มธุรกิจ FROM revenue  -- syntax error
```

##### กฎ 3: REVENUE_UNIT

```yaml
rule_code: REVENUE_UNIT
rule_name: หน่วยรายได้เป็นบาท
severity: warning
applies_to: REVENUE_VALUE, AMOUNT

คำเตือน: REVENUE_VALUE และ AMOUNT มีหน่วยเป็น บาท (ไม่ใช่ล้านบาท)

✅ ถูกต้อง:
SELECT SUM(REVENUE_VALUE) as revenue_baht FROM revenue

❌ ผิด:
SELECT SUM(REVENUE_VALUE) as revenue_million FROM revenue  -- ผิดหน่วย
```

##### กฎ 4: USE_YEAR_MONTH

```yaml
rule_code: USE_YEAR_MONTH
rule_name: ใช้ YEAR, MONTH แทน DATE
severity: info

✅ แนะนำ:
SELECT * FROM revenue WHERE YEAR = 2025 AND MONTH = 1

❌ ไม่แนะนำ:
SELECT * FROM revenue WHERE date(DATE/1000,'unixepoch') = '2025-01-01'
```

#### 3. การใช้งานใน Code

```python
# ดึงกฎทั้งหมด
rules = service.get_business_rules(table_name="revenue")

# Filter ตาม severity
error_rules = [r for r in rules if r['severity'] == 'error']
warning_rules = [r for r in rules if r['severity'] == 'warning']

# แสดงกฎให้ AI เห็น
for rule in rules:
    print(f"{rule['rule_name']}: {rule['rule_description']}")
```

### ประโยชน์

✅ AI สร้าง SQL ที่ถูกต้องตามกฎธุรกิจ
✅ ป้องกัน common mistakes (เช่น ลืม quote column ภาษาไทย)
✅ มี example ที่ชัดเจนว่าอันไหนถูก อันไหนผิด
✅ จัดการกฎแบบ centralized ไม่กระจัดกระจายในโค้ด

---

## 3. schema_semantic_mapping

### หน้าที่

แปลง **คำย่อ, คำศัพท์ธุรกิจ, และคำพ้องความหมาย** ให้เป็น SQL conditions ที่ถูกต้อง

### โครงสร้างตาราง

```sql
CREATE TABLE schema_semantic_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,       -- คำค้นหา (เช่น "นป.", "อสังหาริมทรัพย์")
    keyword_type TEXT DEFAULT 'term',  -- ประเภท (abbreviation, term, synonym)
    target_column TEXT NOT NULL,        -- คอลัมน์ที่ต้องใช้
    target_condition TEXT NOT NULL,     -- เงื่อนไข SQL (เช่น "= 'value'")
    full_condition TEXT,                -- SQL condition เต็ม (สำหรับกรณีซับซ้อน)
    description TEXT,                   -- คำอธิบาย
    priority INTEGER DEFAULT 0,         -- ลำดับความสำคัญ (สูง = ใช้ก่อน)
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### การใช้งาน

#### 1. ประเภทของ Semantic Mapping

##### A. Abbreviation (คำย่อหน่วยงาน)

```sql
-- คำย่อ "นป."
keyword: นป.
keyword_type: abbreviation
target_column: organization_group_abbr
target_condition: = 'นป.'
description: กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ

-- คำย่อ "บชง."
keyword: บชง.
keyword_type: abbreviation
target_column: department_abbr
target_condition: = 'บชง.'
description: ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ
```

**ตัวอย่างการใช้งาน:**

```
คำถาม: "รายได้ นป. ปี 2568"
AI แปลเป็น: WHERE organization_group_abbr = 'นป.' AND year = 2025
```

##### B. Business Term (คำศัพท์ธุรกิจ)

```sql
-- คำว่า "อสังหาริมทรัพย์"
keyword: อสังหาริมทรัพย์
keyword_type: term
target_column: SERVICE_GROUP
target_condition: = 'กลุ่มบริการพัฒนาสินทรัพย์'
description: บริการด้านสินทรัพย์และอสังหาริมทรัพย์

-- คำว่า "มือถือ"
keyword: มือถือ
keyword_type: term
target_column: BUSINESS_GROUP
target_condition: = 'Mobile'
description: กลุ่มผลิตภัณฑ์โทรศัพท์มือถือ
```

**ตัวอย่างการใช้งาน:**

```
คำถาม: "รายได้อสังหาริมทรัพย์"
AI แปลเป็น: WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'

คำถาม: "รายได้มือถือ"
AI แปลเป็น: WHERE BUSINESS_GROUP = 'Mobile'
```

##### C. Synonym (คำพ้องความหมาย)

```sql
-- "ทรัพย์สิน" = "อสังหาริมทรัพย์"
keyword: ทรัพย์สิน
keyword_type: synonym
target_column: SERVICE_GROUP
target_condition: = 'กลุ่มบริการพัฒนาสินทรัพย์'
description: คำพ้องความหมายกับ อสังหาริมทรัพย์
```

#### 2. การใช้งานใน Code

```python
from app.services.schema_service import SchemaService

service = SchemaService(db_path="revenue.sqlite")

# ดึง semantic mappings ทั้งหมด
mappings = service.get_semantic_mappings()

# ดึงเฉพาะคำย่อ
abbr_mappings = service.get_abbreviation_mappings()
# ผลลัพธ์: [{'keyword': 'นป.', 'target_column': 'organization_group_abbr', ...}, ...]

# ดึงเฉพาะคำศัพท์ธุรกิจ
term_mappings = service.get_term_mappings()
# ผลลัพธ์: [{'keyword': 'อสังหาริมทรัพย์', 'target_column': 'SERVICE_GROUP', ...}, ...]

# แสดงใน System Prompt
semantic_text = service.build_semantic_mapping_text()
```

#### 3. ตัวอย่างการทำงานใน System Prompt

```python
# System Prompt จะมีข้อมูลแบบนี้:

"""
### คำย่อหน่วยงาน (Abbreviations)
| คำย่อ | Column | Condition | ความหมาย |
|-------|--------|-----------|----------|
| นป.   | organization_group_abbr | = 'นป.' | กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ |
| บชง.  | department_abbr | = 'บชง.' | ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ |

### คำศัพท์ธุรกิจ (Business Terms)
| คำค้น | Column | Condition | ความหมาย |
|-------|--------|-----------|----------|
| อสังหาริมทรัพย์ | SERVICE_GROUP | = 'กลุ่มบริการพัฒนาสินทรัพย์' | บริการด้านสินทรัพย์ |
| มือถือ | BUSINESS_GROUP | = 'Mobile' | กลุ่มผลิตภัณฑ์มือถือ |

### วิธีใช้:
เมื่อพบคำใน query ให้ใช้ condition ที่กำหนด เช่น:
- "รายได้ นป." → WHERE organization_group_abbr = 'นป.'
- "รายได้อสังหาริมทรัพย์" → WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'
"""
```

### ประโยชน์

✅ ผู้ใช้ใช้คำย่อได้ (เช่น "นป.", "บชง.")
✅ ผู้ใช้ใช้ภาษาธรรมดาได้ (เช่น "อสังหาริมทรัพย์" แทน "กลุ่มบริการพัฒนาสินทรัพย์")
✅ รองรับหลายคำที่หมายถึงสิ่งเดียวกัน (synonyms)
✅ จัดการแบบ centralized - เพิ่ม/แก้ไขคำได้ที่เดียว

---

## 4. schema_context_tables

### หน้าที่

เก็บข้อมูล **ความสัมพันธ์ระหว่าง Context และ Table** เพื่อรองรับการทำงานแบบ **Multi-Table Context**
ช่วยให้ AI รู้ว่าในหนึ่งเรื่อง (Context) ควรไปดึงข้อมูลจากตารางไหนได้บ้าง และแต่ละตารางทำหน้าที่อะไร

### โครงสร้างตาราง

```sql
CREATE TABLE schema_context_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context_id INTEGER,                 -- อ้างอิง ID จาก schema_contexts
    table_name TEXT,                    -- ชื่อตารางที่เกี่ยวข้อง
    role TEXT DEFAULT 'main',           -- หน้าที่ ('main'='Fact', 'dimension', 'reference')
    FOREIGN KEY (context_id) REFERENCES schema_contexts(id)
);
```

### การใช้งาน

#### 1. ประเภทของ Role (บทบาทของตาราง)

*   **main**: ตารางหลักที่เก็บข้อมูลสำคัญ (Fact Table) เช่น ยอดขาย, ค่าใช้จ่าย
*   **dimension**:ตารางมิติข้อมูล เช่น ตารางลูกค้า, ตารางสินค้า, ตารางแผนก
*   **reference**: ตารางอ้างอิงอื่นๆ

#### 2. ตัวอย่างข้อมูล

สมมติ Context: **Revenue** (รายได้) นอกจากตารางหลัก `revenue_search` แล้ว ต้องการให้ AI รู้จักตารางสินค้าและลูกค้าด้วย

```sql
-- 1. Main Table
context_id: 1 (Revenue)
table_name: 'revenue_search'
role: 'main'

-- 2. Product Dimension
context_id: 1 (Revenue)
table_name: 'product_master'
role: 'dimension'

-- 3. Customer Dimension
context_id: 1 (Revenue)
table_name: 'customer_dim'
role: 'dimension'
```

### ประโยชน์

✅ AI สามารถทำ **Cross-Table Query** (JOIN) ได้แม่นยำขึ้น
✅ รองรับโครงสร้างข้อมูลที่ซับซ้อน (Star Schema)
✅ ไม่จำเป็นต้องยัดทุกอย่างลง View ใหญ่ตัวเดียว (Modular Design)

---

## 5. golden_examples

### หน้าที่

เก็บ **ตัวอย่างคำถาม-SQL ที่ดี** สำหรับ Few-Shot Learning เพื่อให้ AI เรียนรู้และสร้าง SQL ที่ถูกต้องขึ้น

### โครงสร้างตาราง

```sql
CREATE TABLE golden_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,                    -- อ้างอิงจาก chat_history (ถ้ามา จาก feedback)
    question_pattern TEXT NOT NULL,     -- รูปแบบคำถาม (เช่น "รายได้รวมเดือน X ปี Y")
    expected_sql TEXT NOT NULL,         -- SQL ที่ถูกต้อง
    category TEXT,                      -- หมวดหมู่ (เช่น "revenue_total", "abbreviation")
    is_active INTEGER DEFAULT 1,
    added_by INTEGER,                   -- ผู้เพิ่ม (user id)
    usage_count INTEGER DEFAULT 0,      -- จำนวนครั้งที่ถูกใช้
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### การใช้งาน

#### 1. Few-Shot Learning

AI จะได้รับตัวอย่างเหล่านี้ใน System Prompt เพื่อเรียนรู้ว่าควรสร้าง SQL อย่างไร:

```python
from app.services.matcha_examples import MatchaExamplesService

service = MatchaExamplesService(db_path="revenue.sqlite")

# ดึง golden examples
golden = service.get_golden_examples()

# ดึงแบบมีหมวดหมู่
golden_revenue = service.get_golden_examples(category="revenue_total")
golden_abbr = service.get_golden_examples(category="abbreviation")
```

#### 2. ตัวอย่าง Golden Examples

##### Example 1: รายได้รวม (ต้อง exclude รายได้อื่น)

```json
{
  "question_pattern": "รายได้รวมเดือนมกราคม 2568",
  "expected_sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE year = 2025 AND month = 1 AND BUSINESS_GROUP != 'รายได้อื่น'",
  "category": "revenue_total",
  "explanation": "รายได้รวมทั้งหมดในเดือนมกราคม 2568 (ค.ศ. 2025) ไม่รวมรายได้อื่น"
}
```

##### Example 2: การใช้คำย่อ

```json
{
  "question_pattern": "รายได้ นป. ปี 2568",
  "expected_sql": "SELECT SUM(revenue) as total_revenue FROM revenue_search WHERE organization_group_abbr = 'นป.' AND year = 2025",
  "category": "abbreviation",
  "explanation": "รายได้ของกลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ (นป.) ในปี 2568"
}
```

##### Example 3: การใช้ Business Term

```json
{
  "question_pattern": "รายได้อสังหาริมทรัพย์แยกตามฝ่าย",
  "expected_sql": "SELECT department, SUM(revenue) as total_revenue FROM revenue_search WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์' GROUP BY department ORDER BY total_revenue DESC",
  "category": "business_term",
  "explanation": "รายได้จากอสังหาริมทรัพย์/สินทรัพย์ แยกตามฝ่าย"
}
```

##### Example 4: Top N และ Bottom N

```json
{
  "question_pattern": "หน่วยงานไหนมีรายได้มากที่สุด 5 อันดับแรก และน้อยที่สุด 5 อันดับแรก",
  "expected_sql": "SELECT 'มากสุด' as category, department, total FROM (\n    SELECT department, SUM(revenue) as total\n    FROM revenue_search\n    GROUP BY department\n    ORDER BY total DESC\n    LIMIT 5\n)\nUNION ALL\nSELECT 'น้อยสุด' as category, department, total FROM (\n    SELECT department, SUM(revenue) as total\n    FROM revenue_search\n    GROUP BY department\n    ORDER BY total ASC\n    LIMIT 5\n)",
  "category": "ranking",
  "explanation": "Top 5 และ Bottom 5 หน่วยงานตามรายได้"
}
```

##### Example 5: การคำนวณสัดส่วน

```json
{
  "question_pattern": "สัดส่วนรายได้ของกลุ่มธุรกิจ Fixed Line & Broadband",
  "expected_sql": "SELECT\n    'Fixed Line & Broadband' as BUSINESS_GROUP,\n    SUM(revenue) as group_revenue,\n    (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น') as total_revenue,\n    ROUND(SUM(revenue) * 100.0 / (SELECT SUM(revenue) FROM revenue_search WHERE BUSINESS_GROUP != 'รายได้อื่น'), 2) as percentage\nFROM revenue_search\nWHERE BUSINESS_GROUP = 'Fixed Line & Broadband'",
  "category": "percentage",
  "explanation": "สัดส่วนรายได้ Fixed Line & Broadband เทียบกับรายได้รวม (ไม่นับรายได้อื่น)"
}
```

#### 3. การใช้ Golden Examples ใน AI Prompt

```python
# สร้าง Few-Shot Examples
few_shot_text = ""
for example in golden_examples:
    few_shot_text += f"""
### ตัวอย่างที่ {i+1}
**คำถาม:** {example['question_pattern']}

**SQL:**
```sql
{example['expected_sql']}
```

**คำอธิบาย:** {example.get('explanation', '')}

---

"""

# ใส่ใน System Prompt

system_prompt = f"""
{base_instruction}

## Few-Shot Examples (ตัวอย่างที่ดี)

{few_shot_text}

{schema_context}
"""

```

#### 4. การเพิ่ม Golden Example จาก User Feedback

```python
from app.api.v1.admin import create_golden_example

# เมื่อผู้ใช้ให้ feedback ว่า query นี้ดี
# Admin สามารถเพิ่มเข้า golden_examples ได้

create_golden_example(
    question="รายได้ บชง. เดือน 1 ถึง 11",
    expected_sql="SELECT month, SUM(revenue) as total FROM revenue_search WHERE department_abbr = 'บชง.' AND year = 2025 AND CAST(month AS INTEGER) BETWEEN 1 AND 11 GROUP BY month ORDER BY CAST(month AS INTEGER)",
    category="date_range",
    db=db
)
```

### ประโยชน์

✅ AI เรียนรู้จากตัวอย่างที่ดี (Few-Shot Learning)
✅ ลด hallucination - มีตัวอย่างชัดเจนให้ follow
✅ รวบรวม best practices ไว้ที่เดียว
✅ เพิ่มความแม่นยำของ SQL ที่ถูกสร้าง
✅ สามารถเพิ่ม/แก้ไข examples ได้ตามเวลา

---

## สรุปการทำงานร่วมกันของทั้ง 4 ตาราง

```
User Question: "รายได้ นป. เดือนมกราคม 2568"
      ↓
┌─────────────────────────────────────────────────────────┐
│ 1. schema_semantic_mapping                              │
│    "นป." → organization_group_abbr = 'นป.'              │
└─────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────┐
│ 2. golden_examples (Few-Shot Learning)                  │
│    ตัวอย่าง: "รายได้ นป. ปี X"                         │
│    SQL: SELECT ... WHERE organization_group_abbr = ...  │
└─────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────┐
│ 3. schema_metadata                                      │
│    - revenue column: is_summable = 1 (ใช้ SUM ได้)     │
│    - year column: data_type = INTEGER                   │
│    - month column: data_type = INTEGER                  │
└─────────────────────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────────────────────┐
│ 4. schema_business_rules                                │
│    - ต้อง CAST(month AS INTEGER) เมื่อเปรียบเทียบ      │
│    - หน่วยรายได้เป็นบาท                                │
└─────────────────────────────────────────────────────────┘
      ↓
AI Generated SQL:
SELECT SUM(revenue) as total_revenue
FROM revenue_search
WHERE organization_group_abbr = 'นป.'
  AND year = 2025
  AND month = 1
```

---

## สรุปหน้าที่ของ 4 ตารางหลัก (LLM Schema Logic)

โครงสร้างตารางเหล่านี้ออกแบบมาเพื่อให้ AI สามารถแปลงภาษาธรรมชาติ (Natural Language) เป็น SQL ได้อย่างแม่นยำ

### 1. `schema_metadata`

**หน้าที่:** เก็บรายละเอียดเชิงเทคนิคของแต่ละ Column เพื่อให้ AI เข้าใจบริบทของข้อมูล

* **Description:** อธิบายความหมายของ Column (ทั้งภาษาไทยและอังกฤษ)
* **Aggregation Rules:** ระบุว่า Column นั้นสามารถใช้ `SUM()` ได้หรือไม่ (`is_summable`)
* **Grouping Rules:** ระบุว่าสามารถใช้ `GROUP BY` ได้หรือไม่ (`is_groupable`)
* **Transformation:** วิธีการแปลงค่าพื้นฐานผ่าน `conversion_sql`

### 2. `schema_business_rules`

**หน้าที่:** เก็บ "กฎเหล็ก" ของธุรกิจในการสร้าง Query

* **Date Handling:** การแปลง Unix timestamp ให้เป็นรูปแบบวันที่ที่อ่านออก
* **Syntax Rules:** การใส่ Quote สำหรับ Column ภาษาไทย
* **Unit Logic:** การจัดการหน่วยนับ (เช่น รายได้ต้องเป็น "บาท" เสมอ ไม่ใช่ "ล้านบาท")
* **Time Granularity:** เน้นการใช้ `YEAR` หรือ `MONTH` แทนการใช้ `DATE` เต็มรูปแบบตามความเหมาะสม

### 3. `schema_semantic_mapping`

**หน้าที่:** ตัวแปลภาษา (Translator) จากคำพูดติดปากหรือคำย่อไปเป็นค่าในฐานข้อมูล

* **Abbreviation:** "นป."  `organization_group_abbr = 'นป.'`
* **Industry Terms:** "อสังหาริมทรัพย์"  `SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'`
* **Common Names:** "มือถือ"  `BUSINESS_GROUP = 'Mobile'`

### 4. `golden_examples`

**หน้าที่:** คลังตัวอย่าง SQL ที่ถูกต้องที่สุด (Few-Shot Learning)

* **Pattern Recognition:** AI เรียนรู้จากตัวอย่างจริงที่เคยตอบถูก
* **Best Practices:** กำหนดมาตรฐานการเขียน Code ที่ทีมยอมรับ
* **Efficiency:** ช่วยลดความผิดพลาดในคำถามที่มีความซับซ้อนสูง (Common Patterns)

---

## Workflow การทำงานร่วมกัน (Execution Flow)

เมื่อ User ส่งคำถามเข้ามา ระบบจะทำงานตามลำดับดังนี้:

> **User Query:** *"รายได้ นป. เดือนมกราคม 2568"*

| ขั้นตอน                          | แหล่งข้อมูลที่ใช้ | ผลลัพธ์ที่ได้                                                                        |
| --------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| **1. แปลงศัพท์**         | `semantic_mapping`               | แปลง "นป." เป็นเงื่อนไข `organization_group_abbr = 'นป.'`                   |
| **2. หาตัวอย่าง**       | `golden_examples`                | ค้นหารูปแบบ SQL ที่ใกล้เคียงกับคำถามนี้มาเป็นแนวทาง |
| **3. เช็คโครงสร้าง** | `schema_metadata`                | ตรวจสอบว่า `revenue` สามารถใช้ `SUM()` ได้                              |
| **4. บังคับใช้กฎ**     | `business_rules`                 | ตรวจสอบการ CAST ค่าเดือน และการจัดการหน่วยเงิน             |

### 🏁 Generated SQL:

```sql
SELECT SUM(revenue) 
FROM revenue_search 
WHERE organization_group_abbr = 'นป.' 
  AND report_month = 1 
  AND report_year = 2025;

```

---

## Best Practices

### 1. การเพิ่มข้อมูล

#### เพิ่ม Schema Metadata

```sql
INSERT INTO schema_metadata (
    table_name, column_name, data_type,
    display_name_th, is_summable, is_groupable
) VALUES (
    'revenue', 'NEW_COLUMN', 'TEXT',
    'คอลัมน์ใหม่', 0, 1
);
```

#### เพิ่ม Business Rule

```sql
INSERT INTO schema_business_rules (
    rule_code, rule_name, rule_description,
    example_correct, severity
) VALUES (
    'NEW_RULE', 'กฎใหม่', 'คำอธิบายกฎ',
    'SELECT ... ถูกต้อง', 'warning'
);
```

#### เพิ่ม Semantic Mapping

```sql
INSERT INTO schema_semantic_mapping (
    keyword, keyword_type, target_column,
    target_condition, description
) VALUES (
    'คำย่อใหม่', 'abbreviation', 'column_name',
    "= 'value'", 'คำอธิบาย'
);
```

#### เพิ่ม Golden Example

```sql
INSERT INTO golden_examples (
    question_pattern, expected_sql, category
) VALUES (
    'รูปแบบคำถาม', 'SELECT ...', 'category_name'
);
```

### 2. การ Refresh Cache

หลังจากเพิ่ม/แก้ไขข้อมูลในตารางเหล่านี้ ต้อง refresh cache:

```python
from app.services.schema_service import SchemaService

service = SchemaService(db_path="revenue.sqlite")
service.refresh_cache()

# System prompt จะถูกสร้างใหม่ครั้งถัดไป
```

### 3. การตรวจสอบความถูกต้อง

```python
# ตรวจสอบว่ามี metadata ครบหรือไม่
metadata = service.get_schema_metadata("revenue")
print(f"Total columns: {len(metadata)}")

# ตรวจสอบ business rules ที่ active
rules = service.get_business_rules()
active_rules = [r for r in rules if r['is_active'] == 1]
print(f"Active rules: {len(active_rules)}")

# ตรวจสอบ semantic mappings
mappings = service.get_semantic_mappings()
print(f"Total mappings: {len(mappings)}")

# ตรวจสอบ golden examples
from app.services.matcha_examples import MatchaExamplesService
matcha_service = MatchaExamplesService(db_path="revenue.sqlite")
golden = matcha_service.get_golden_examples()
print(f"Total golden examples: {len(golden)}")
```

---

## ไฟล์ที่เกี่ยวข้อง

### Database Schema

- [`database/schema_metadata.sql`](../database/schema_metadata.sql) - สคริปต์สร้างตาราง
- [`database/migrations/003_schema_metadata.sql`](../database/migrations/003_schema_metadata.sql) - Migration

### Models

- [`app/models/schema_models.py`](../app/models/schema_models.py) - SQLAlchemy models สำหรับ schema_metadata, schema_business_rules, schema_semantic_mapping
- [`app/models/feedback_models.py`](../app/models/feedback_models.py) - SQLAlchemy model สำหรับ golden_examples

### Services

- [`app/services/schema_service.py`](../app/services/schema_service.py) - Service หลักสำหรับจัดการ schema metadata
- [`app/services/matcha_examples.py`](../app/services/matcha_examples.py) - Service สำหรับจัดการ golden examples

### API Endpoints

- [`app/api/v1/admin.py`](../app/api/v1/admin.py) - Admin API สำหรับจัดการทั้ง 4 ตาราง

### Scripts

- [`scripts/populate_schema_metadata.py`](../scripts/populate_schema_metadata.py) - สคริปต์เติมข้อมูล metadata

---

## อ่านเพิ่มเติม

- [DATA_DICTIONARY.md](DATA_DICTIONARY.md) - พจนานุกรมข้อมูลฉบับเต็ม
- [CLAUDE.md](../CLAUDE.md) - คำแนะนำสำหรับ AI Coding Assistants
- [Admin-UI-and-Schema-Analyzer-Plan.md](Admin-UI-and-Schema-Analyzer-Plan.md) - แผน Admin UI และ Schema Analyzer
