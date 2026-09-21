# Database Tables Guide

**Version:** 2.0
**Last Updated:** 2026-07-12
**Database:** config.db (SQLite)

> **Note:** This file is for human reference only. Vanna RAG documentation is now
> managed via the `vanna_documentation` table and auto-generated context summaries.
> Manage via Admin UI: Knowledge Base > Vanna Knowledge.
> See `app/services/vanna_service.py` for the DB-driven sync logic.
>
> This guide documents config DB tables that drive AI SQL generation.

---

## สารบัญ

1. [schema_metadata](#1-schema_metadata) — Column metadata
2. [schema_business_rules](#2-schema_business_rules) — SQL generation rules
3. [schema_semantic_mapping](#3-schema_semantic_mapping) — Keyword-to-SQL translation
4. [schema_contexts](#4-schema_contexts) — Multi-context routing
5. [golden_examples](#5-golden_examples) — Few-shot learning examples
6. [view_column_mappings](#6-view_column_mappings) — View-to-source column mapping
7. [master_hierarchy](#7-master_hierarchy) — Hierarchy level definitions
8. [master_hierarchy_values](#8-master_hierarchy_values) — Hierarchy values with parent chains
9. [keyword_value_index](#9-keyword_value_index) — Smart keyword-to-value lookup

---

## ที่มา + สถานะของความรู้ (Plan 8.1, 2026-09-21)

9 ตาราง — `schema_contexts`, `schema_metadata`, `schema_business_rules`, `golden_examples`, `schema_semantic_mapping`,
`master_hierarchy`, `master_hierarchy_values`, `data_warnings`, `vanna_documentation` — มี 3 คอลัมน์ (`scripts/migrate_knowledge_provenance.py`):

| คอลัมน์ | ค่า |
|---|---|
| `source` | `declared` (contract / เจ้าของข้อมูล) · `manual` (คน) · `inferred` (ข้อมูล / profile / LLM) · `learned` (จากการใช้งานจริง) — NULL / `auto` เดิม = ของคน |
| `status` | `active` (prompt / RAG / routing อ่าน) · `proposed` (รอคน) · `rejected` (คนปฏิเสธ) — `NOT NULL DEFAULT 'active'` |
| `confidence` | 0–1 จากเครื่องที่เขียน · NULL = ไม่ได้บันทึก |

- **กฎเดียวของตัวเขียน** (`app/services/provenance.py`): คนแก้ได้เสมอ · contract ทับได้เฉพาะแถว `declared` ของตัวเองหรือของเครื่อง ·
  เครื่องทับได้เฉพาะของเครื่อง · ที่ทับไม่ได้ = ข้อเสนอเข้าคิว · ไม่มีใครยกเว้นคนแตะแถว `rejected`
- **`knowledge_proposals`** — ข้อเสนอที่ชนแถวที่มีอยู่ (8 ใน 9 ตารางมีคีย์ UNIQUE จึงเก็บ `proposed` คู่กับ `active` คีย์เดียวกันไม่ได้):
  `table_name`, `row_key` (JSON ของคีย์), `proposed` (JSON ของช่องที่เสนอ), `source`, `confidence`, `reason`, `status`, `created_at` ·
  หนึ่งข้อเสนอที่รออยู่ต่อคีย์ต่อผู้เสนอ (partial unique index) — ฉบับใหม่รวมทีละช่อง · หน้า admin ของคิว = Plan 8.3
- `is_active` ยังเป็นสวิตช์เปิด/ปิดของ admin แยกจาก `status` (`schema_metadata` ไม่มี `is_active`)

---

## Multi-Context Architecture

The system supports multiple data contexts (revenue, expense, pl_costtype, etc.) via the `schema_contexts` table. Each context has:

- A `main_view` that AI queries against (e.g., `revenue_search`, `v_expense_mart`)
- Detection `keywords` (JSON array) for automatic context routing from user questions
- Custom AI instructions (`instruction_th`, `instruction_en`)
- Context-scoped semantic mappings and business rules

**Context routing flow:**

```
User: "รายได้ นป. เดือนมกราคม 2568"
      ↓
Step 0: Context Routing (schema_contexts)
  → keyword "รายได้" matches → context = "revenue", main_view = "revenue_search"
      ↓
Step 1: Semantic Mapping (schema_semantic_mapping)
  → "นป." → organization_group_abbr = 'นป.'
      ↓
Step 1.5: Hierarchy Level Detection (master_hierarchy)
  → validate that keywords don't mix hierarchy levels
      ↓
Step 2: Few-Shot Examples (golden_examples)
  → find similar question patterns for AI reference
      ↓
Step 2.5: Value Lookup (keyword_value_index)
  → match user keywords to actual DB values
      ↓
Step 3: Schema Metadata (schema_metadata)
  → revenue is_summable=1, year data_type=INTEGER
      ↓
Step 4: Business Rules (schema_business_rules)
  → enforce unit=baht, Thai column quoting, etc.
      ↓
Generated SQL:
SELECT SUM(revenue) FROM revenue_search
WHERE organization_group_abbr = 'นป.' AND year = 2025 AND month = 1
```

---

## 1. schema_metadata

### หน้าที่

เก็บ **metadata ของคอลัมน์** ในฐานข้อมูลเพื่อให้ AI เข้าใจโครงสร้างข้อมูลและการใช้งานแต่ละคอลัมน์

### โครงสร้างตาราง

```sql
CREATE TABLE schema_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,           -- ชื่อตาราง/view (เช่น "revenue", "revenue_search")
    column_name TEXT NOT NULL,          -- ชื่อคอลัมน์ (เช่น "year", "revenue", "BUSINESS_GROUP")
    data_type TEXT,                     -- ชนิดข้อมูล (INTEGER, TEXT, REAL)
    display_name_th TEXT,               -- ชื่อแสดงภาษาไทย (เช่น "ปี")
    display_name_en TEXT,               -- ชื่อแสดงภาษาอังกฤษ (เช่น "Year")
    description TEXT,                   -- คำอธิบายคอลัมน์
    format_hint TEXT,                   -- คำแนะนำรูปแบบ (เช่น "YYYY", "Code")
    example_value TEXT,                 -- ค่าตัวอย่าง (เช่น "2025")
    sample_values JSON,                 -- JSON array ของค่าตัวอย่างหลายค่า
    is_summable INTEGER DEFAULT 0,      -- สามารถใช้ SUM() ได้หรือไม่
    is_groupable INTEGER DEFAULT 1,     -- สามารถใช้ GROUP BY ได้หรือไม่
    hierarchy_level INTEGER,            -- ระดับลำดับชั้น (สำหรับ org hierarchy)
    dimension_group TEXT,               -- กลุ่มมิติข้อมูลที่เกี่ยวข้อง (family group)
    special_notes TEXT,                 -- หมายเหตุพิเศษ
    conversion_sql TEXT,                -- SQL สำหรับแปลงค่า (ถ้ามี)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_name, column_name)
);
```

### การใช้งาน

#### 1. ใช้ในการสร้าง System Prompt

```python
from app.services.schema_service import SchemaService
from app.db.session import config_engine, business_engine

service = SchemaService(db_engine=config_engine, business_engine=business_engine)
metadata = service.get_schema_metadata(table_name="revenue_search")

# สร้าง schema text สำหรับ AI
schema_text = service.build_schema_text(table_name="revenue_search")
```

#### 2. ใช้ในการตรวจสอบความถูกต้องของ SQL

- ตรวจสอบว่าคอลัมน์สามารถใช้ `SUM()` ได้หรือไม่ (`is_summable`)
- ตรวจสอบว่าคอลัมน์สามารถใช้ `GROUP BY` ได้หรือไม่ (`is_groupable`)
- ดูว่าต้องมีการแปลงค่าหรือไม่ (เช่น DATE ต้องแปลงจาก Unix timestamp)
- `dimension_group` ใช้จัดกลุ่มคอลัมน์ที่เกี่ยวข้องกัน (เช่น product columns, org columns)

#### 3. ตัวอย่างข้อมูล

```sql
-- Column: year (view revenue_search ใช้ชื่อคอลัมน์ lowercase)
table_name: revenue_search
column_name: year
data_type: INTEGER
display_name_th: ปี
is_summable: 0
is_groupable: 1
special_notes: ใช้สำหรับการกรองข้อมูลรายปี (ปี ค.ศ. — ปี พ.ศ. = year + 543)

-- Column: revenue
table_name: revenue_search
column_name: revenue
data_type: DOUBLE
display_name_th: มูลค่ารายได้
is_summable: 1
is_groupable: 1
special_notes: ใช้เป็นตัวเลขหลักในการคำนวณรายได้ (หน่วยเป็นบาท)
```

### ประโยชน์

- AI รู้ว่าคอลัมน์ไหนคืออะไร (ชื่อไทย/อังกฤษ)
- AI รู้ว่าคอลัมน์ไหนใช้ SUM ได้ ไหนใช้ไม่ได้
- AI รู้ว่าต้องแปลงค่าอย่างไร (เช่น DATE, ปี พ.ศ.)
- `dimension_group` ช่วย AI เข้าใจว่าคอลัมน์ไหนเกี่ยวข้องกัน
- ลด error จากการใช้คอลัมน์ผิดประเภท

---

## 2. schema_business_rules

### หน้าที่

เก็บ **กฎทางธุรกิจและกฎการสร้าง SQL** เพื่อให้ AI สร้าง SQL ที่ถูกต้องตามข้อกำหนด

### โครงสร้างตาราง

```sql
CREATE TABLE schema_business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL UNIQUE,     -- รหัสกฎ (เช่น "DATE_CONVERSION")
    rule_name TEXT NOT NULL,            -- ชื่อกฎ (เช่น "แปลง DATE ก่อนใช้")
    rule_description TEXT NOT NULL,     -- คำอธิบายกฎ
    table_name TEXT,                    -- ใช้กับ table/view ไหน (NULL = ทุกตาราง)
    applies_to TEXT,                    -- ใช้กับคอลัมน์ไหนบ้าง (comma-separated)
    example_correct TEXT,               -- ตัวอย่าง SQL ที่ถูกต้อง
    example_wrong TEXT,                 -- ตัวอย่าง SQL ที่ผิด
    severity TEXT DEFAULT 'warning',    -- ระดับความสำคัญ (critical, error, warning, info)
    inject_mode TEXT DEFAULT 'schema_context',  -- ตำแหน่งใน prompt: 'schema_context' หรือ 'instruction'
    rule_category TEXT DEFAULT 'sql_generation', -- หมวดหมู่กฎ (sql_generation, context_retention, sql_pattern, unit_conversion, response_format, display, data_structure)
    pattern TEXT,                       -- regex pattern สำหรับ validation (migration 030)
    check_type TEXT DEFAULT 'regex_warning',  -- ประเภทการตรวจ (regex_warning, regex_error, context_warning, aggregate_check)
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### inject_mode — ตำแหน่งของกฎใน AI Prompt

กฎแต่ละข้อจะถูกฉีดเข้าไปในตำแหน่งต่างกันของ system prompt:

| inject_mode | ตำแหน่ง | ใช้สำหรับ |
|---|---|---|
| `schema_context` (default) | ส่วน schema definition | กฎเกี่ยวกับโครงสร้างข้อมูล (DATE conversion, Thai quoting) |
| `instruction` | ส่วน instruction | กฎเชิงธุรกิจ (unit conversion, context retention, SQL patterns) |
| `NULL` | ทั้งสอง | กฎทั่วไป (ถูกรวมไม่ว่า filter ด้วย inject_mode ใด) |

### ตัวอย่างกฎสำคัญ

#### กฎ 1: DATE_CONVERSION

```
rule_code: DATE_CONVERSION
severity: warning
check_type: regex_warning
pattern: (?i)SELECT.*\bDATE\b(?!.*/\s*1000)

ถูกต้อง: SELECT date(DATE / 1000, 'unixepoch') FROM v_expense_mart
ผิด: SELECT DATE FROM v_expense_mart  -- จะได้ตัวเลข Unix timestamp (ms)
```

#### กฎ 2: THAI_COLUMN_QUOTES

```
rule_code: THAI_COLUMN_QUOTES
severity: error
check_type: regex_error
pattern: (?i)(กลุ่มธุรกิจ|หมวดบัญชี)(?!["'])

ถูกต้อง: SELECT "กลุ่มธุรกิจ" FROM revenue
ผิด: SELECT กลุ่มธุรกิจ FROM revenue  -- syntax error (คอลัมน์ภาษาไทยใน raw table)
```

#### กฎ 3: REVENUE_UNIT

```
rule_code: REVENUE_UNIT
severity: warning
table_name: revenue_search
applies_to: revenue
check_type: context_warning

คำเตือน: คอลัมน์ revenue มีหน่วยเป็น บาท (ไม่ใช่ล้านบาท)
```

### ประโยชน์

- AI สร้าง SQL ที่ถูกต้องตามกฎธุรกิจ
- `inject_mode` แยกกฎตามตำแหน่งใน prompt (schema vs instruction)
- `rule_category` จัดกลุ่มกฎ (เช่น context_retention, unit_conversion)
- `pattern` + `check_type` ใช้ validate SQL output อัตโนมัติ
- ป้องกัน common mistakes (เช่น ลืม quote column ภาษาไทย)

---

## 3. schema_semantic_mapping

### หน้าที่

แปลง **คำย่อ, คำศัพท์ธุรกิจ, และคำพ้องความหมาย** ให้เป็น SQL conditions ที่ถูกต้อง

### โครงสร้างตาราง

```sql
CREATE TABLE schema_semantic_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,       -- คำค้นหา (เช่น "นป.", "อสังหาริมทรัพย์")
    keyword_type TEXT DEFAULT 'term',   -- ประเภท (abbreviation, term, synonym)
    target_column TEXT NOT NULL,        -- คอลัมน์ที่ต้องใช้
    target_condition TEXT NOT NULL,     -- เงื่อนไข SQL (เช่น "= 'value'")
    full_condition TEXT,                -- SQL condition เต็ม (สำหรับกรณีซับซ้อน)
    description TEXT,                   -- คำอธิบาย
    priority INTEGER DEFAULT 0,        -- ลำดับความสำคัญ (สูง = ใช้ก่อน)
    is_active INTEGER DEFAULT 1,
    context_name TEXT,                  -- NULL = global (ทุก context), ค่า = เฉพาะ context นั้น
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### context_name — Context Scoping

Semantic mappings สามารถเป็น global หรือ scoped เฉพาะ context:

| context_name | ความหมาย |
|---|---|
| `NULL` | ใช้ได้กับทุก context (global mapping) |
| `'revenue'` | ใช้เฉพาะ revenue context |
| `'transfer price'` | ใช้เฉพาะ transfer price context |

### ประเภท Semantic Mapping

#### A. Abbreviation (คำย่อหน่วยงาน)

```
keyword: นป.
keyword_type: abbreviation
target_column: organization_group_abbr
target_condition: = 'นป.'
description: กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ
```

#### B. Business Term (คำศัพท์ธุรกิจ) — ใช้ full_condition สำหรับเงื่อนไขซับซ้อน

```
keyword: อสังหาริมทรัพย์
keyword_type: term
target_column: SERVICE_GROUP
full_condition: service_group LIKE '%กลุ่มบริการพัฒนาสินทรัพย์%'
description: รายได้จากอสังหาริมทรัพย์
```

#### C. Synonym (คำพ้องความหมาย)

```
keyword: ทรัพย์สิน
keyword_type: term
target_column: SERVICE_GROUP
full_condition: service_group LIKE '%กลุ่มบริการพัฒนาสินทรัพย์%'
description: รายได้จากทรัพย์สิน (คำพ้องความหมายกับ อสังหาริมทรัพย์)
```

> ถ้า `full_condition` มีค่า ระบบจะใช้ `full_condition` แทน `target_column + target_condition`
> (ดู `SchemaSemanticMapping.get_sql_condition()` ใน `app/models/schema_models.py`)

### ตัวอย่างการใช้งาน

```
คำถาม: "รายได้ นป. ปี 2568"
AI แปลเป็น: WHERE organization_group_abbr = 'นป.' AND year = 2025

คำถาม: "รายได้อสังหาริมทรัพย์"
AI แปลเป็น: WHERE SERVICE_GROUP LIKE '%กลุ่มบริการพัฒนาสินทรัพย์%'
```

### การใช้งานใน Code

```python
from app.services.schema_service import SchemaService
from app.db.session import config_engine, business_engine

service = SchemaService(db_engine=config_engine, business_engine=business_engine)

# ดึง semantic mappings ทั้งหมด
mappings = service.get_semantic_mappings()

# ดึงเฉพาะคำย่อ
abbr_mappings = service.get_semantic_mappings(keyword_type="abbreviation")

# ดึงเฉพาะคำศัพท์ธุรกิจ
term_mappings = service.get_semantic_mappings(keyword_type="term")
```

### ประโยชน์

- ผู้ใช้ใช้คำย่อได้ (เช่น "นป.", "บชง.")
- ผู้ใช้ใช้ภาษาธรรมดาได้ (เช่น "อสังหาริมทรัพย์")
- `context_name` scoping ป้องกัน mapping ชนกันข้าม context
- รองรับหลายคำที่หมายถึงสิ่งเดียวกัน (synonyms)

---

## 4. schema_contexts

### หน้าที่

เก็บ **การตั้งค่า context** สำหรับ multi-context routing — ระบบจะเลือก context จาก keywords ในคำถามของผู้ใช้แล้วเชื่อมไปยัง main_view ที่ถูกต้อง

### โครงสร้างตาราง

```sql
CREATE TABLE schema_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,          -- Context identifier (เช่น 'revenue', 'expense')
    display_name TEXT NOT NULL,         -- ชื่อแสดงใน UI
    description TEXT,                   -- คำอธิบาย context
    main_view TEXT NOT NULL,            -- ชื่อ view/table หลักที่ AI จะ query
    is_active BOOLEAN DEFAULT 1,
    priority INTEGER DEFAULT 0,         -- สูงกว่า = ถูกเลือกก่อนเมื่อ keyword ตรงหลาย context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    keywords TEXT,                      -- JSON array ของ keywords สำหรับ auto-detection
    instruction_th TEXT,                -- Custom AI instruction ภาษาไทยสำหรับ context นี้
    instruction_en TEXT,                -- Custom AI instruction ภาษาอังกฤษ
    updated_at TIMESTAMP,
    -- Plan 7 (scripts/migrate_data_sources.py, migrate_workspaces.py)
    source_id INTEGER REFERENCES data_sources(id),   -- แหล่งข้อมูลของ context ('legacy' = business DB เดิม)
    scope_columns TEXT,                 -- JSON {"scope key": "column"} ที่ผู้เรียกจำกัดขอบเขตได้; NULL = ไม่รับ scope
    workspace_id INTEGER REFERENCES workspaces(id)    -- NULL = 'default'
);
```

**ตารางของ Plan 7 (config DB)** — รายละเอียด: `docs/DATAFEED_INTEGRATION.md`, `docs/manuals/manual_api_keys.md`

| ตาราง | หน้าที่ | คอลัมน์หลัก |
|---|---|---|
| `data_sources` | ที่อยู่ของข้อมูลต่อ source | `name`, `source_type` (`legacy` / `duckdb_file`), `root_path`, `manifest_file`, `contract_file`, `knowledge_sha` (contract sha + schema_version ของ knowledge ล่าสุด), `is_active` |
| `source_tables` | allowlist ของ view ต่อ file source (เขียนตอนลงทะเบียน) | `source_id`, `table_name`, `file_name`, `columns` (JSON ชื่อ+ชนิด), `sha256`, `is_active` |
| `workspaces` | การแบ่ง context ภายใน deployment; API key ผูกกับ workspace ได้ | `name` (slug), `display_name`, `description`, `is_active` — `default` สร้างโดย migration |

> **หมายเหตุ:** migration 004 เดิมกำหนดคอลัมน์ `database_url`, `default_instruction`,
> `sample_queries`, `created_by`, `metadata` ไว้ด้วย แต่ตารางจริงใน config DB ปัจจุบัน
> ไม่มีคอลัมน์เหล่านั้นแล้ว — code (`app/services/schema/context_store.py`) ใช้เฉพาะ
> name, display_name, description, main_view, is_active, priority, keywords,
> instruction_th, instruction_en
>
> `keywords` เก็บเป็น **JSON array** (เช่น `["รายได้", "revenue", "sales"]`) —
> `context_store._normalize_context_row()` จะ parse ด้วย `json.loads`

### ตัวอย่าง Contexts (ข้อมูลจริงใน config DB)

| name | display_name | main_view | keywords (ตัวอย่าง) | priority |
|---|---|---|---|---|
| revenue | รายได้ | revenue_search | `["รายได้", "revenue", "sales", "ยอดขาย"]` | 10 |
| expense | ค่าใช้จ่าย | v_expense_mart | `["ค่าใช้จ่าย", "expense", "cost", "ต้นทุน"]` | 9 |
| transfer price | ราคาโอนระหว่างหน่วยงาน | v_transfer_price | `["ราคาโอน", "transfer price", "segment report"]` | 9 |
| pl_costtype | ผลดำเนินงาน | v_pl_costtype_nt_mth_clean | `["ผลดำเนินงาน", "profit & loss", "EBT"]` | 5 |
| feed_revenue | DataFeed revenue | feed_revenue_fact_bu_monthly | `["datafeed", "feed", "dashboard"]` | 0 |

### Context Routing Flow

1. User ถามคำถาม เช่น "รายได้รวมปี 2568"
2. ระบบ scan keywords จาก `schema_contexts` → พบ "รายได้" ใน revenue context
3. เลือก context "revenue" → main_view = "revenue_search"
4. โหลด metadata, rules, mappings ที่เกี่ยวข้องกับ revenue
5. AI generate SQL ที่ query จาก `revenue_search`

### ประโยชน์

- รองรับหลาย data source โดยไม่ต้องแก้ code
- Admin เพิ่ม context ใหม่ได้ผ่าน UI
- แต่ละ context มี instruction เฉพาะ (เช่น expense มีคำเตือนเรื่อง amount ที่อาจติดลบ)

---

## 5. golden_examples

### หน้าที่

เก็บ **ตัวอย่างคำถาม-SQL ที่ดี** สำหรับ Few-Shot Learning เพื่อให้ AI เรียนรู้และสร้าง SQL ที่ถูกต้องขึ้น

### โครงสร้างตาราง

```sql
CREATE TABLE golden_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,                    -- อ้างอิงจาก chat_history (cross-DB, ไม่มี FK)
    question_pattern TEXT NOT NULL,     -- รูปแบบคำถาม (เช่น "รายได้รวมเดือน X ปี Y")
    expected_sql TEXT NOT NULL,         -- SQL ที่ถูกต้อง
    category TEXT,                      -- หมวดหมู่ (เช่น "revenue_total", "abbreviation")
    is_active INTEGER DEFAULT 1,
    added_by INTEGER,                   -- ผู้เพิ่ม (user id, cross-DB)
    usage_count INTEGER DEFAULT 0,      -- จำนวนครั้งที่ถูกใช้
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### ตัวอย่าง Golden Examples

```json
{
  "question_pattern": "รายได้รวมเดือนมกราคม 2568",
  "expected_sql": "SELECT SUM(revenue) FROM revenue_search WHERE year = 2025 AND month = 1 AND BUSINESS_GROUP != 'รายได้อื่น'",
  "category": "revenue_total"
}
```

```json
{
  "question_pattern": "รายได้ นป. ปี 2568",
  "expected_sql": "SELECT SUM(revenue) FROM revenue_search WHERE organization_group_abbr = 'นป.' AND year = 2025",
  "category": "abbreviation"
}
```

### การใช้งาน

AI จะได้รับ golden examples ใน System Prompt เพื่อเรียนรู้ pattern ที่ถูกต้อง (Few-Shot Learning) ช่วยลด hallucination และเพิ่มความแม่นยำของ SQL

### ประโยชน์

- AI เรียนรู้จากตัวอย่างที่ดี (Few-Shot Learning)
- ลด hallucination — มีตัวอย่างชัดเจนให้ follow
- เพิ่มความแม่นยำของ SQL สำหรับ common patterns
- สามารถเพิ่ม/แก้ไข examples ได้ผ่าน Admin UI

---

## 6. view_column_mappings

### หน้าที่

Map คอลัมน์ของ **view** กลับไปยัง **source table** เพื่อให้ metadata propagation ทำงานได้ — เมื่อมี metadata ของ source table, ระบบสามารถ apply metadata ไปยัง view columns ที่ตรงกันโดยอัตโนมัติ

### โครงสร้างตาราง

```sql
CREATE TABLE view_column_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    view_name TEXT NOT NULL,            -- ชื่อ view (เช่น "revenue_search")
    view_column TEXT NOT NULL,          -- ชื่อคอลัมน์ใน view (เช่น "revenue")
    source_table TEXT NOT NULL,         -- ชื่อ source table (เช่น "revenue")
    source_column TEXT NOT NULL,        -- ชื่อคอลัมน์ใน source (เช่น "REVENUE_VALUE")
    mapping_type TEXT DEFAULT 'alias',  -- ประเภท: alias | expression | passthrough
    expression_sql TEXT,                -- SQL expression (สำหรับ mapping_type = 'expression')
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(view_name, view_column)
);
```

### mapping_type

| Type | ความหมาย | ตัวอย่างจริง (revenue_search ← revenue) |
|---|---|---|
| `alias` | คอลัมน์เปลี่ยนชื่อ | view `revenue` ← source `REVENUE_VALUE`, view `business_unit` ← source `"กลุ่มธุรกิจ"` |
| `expression` | คอลัมน์จาก SQL expression | คอลัมน์ที่คำนวณจาก expression เช่น `date(DATE/1000, 'unixepoch')` |
| `passthrough` | ชื่อเดียวกันทั้ง view และ source | `BUSINESS_GROUP` ← `BUSINESS_GROUP` |

### ประโยชน์

- Metadata ที่สร้างสำหรับ source table สามารถ propagate ไปยัง view ได้อัตโนมัติ
- ไม่ต้องสร้าง metadata ซ้ำสำหรับทุก view
- รองรับ view ที่มี column rename หรือ expression columns

---

## 7. master_hierarchy

### หน้าที่

กำหนด **ระดับลำดับชั้น** (hierarchy levels) ของข้อมูลในแต่ละ context — ป้องกัน AI จากการ OR ข้าม hierarchy levels ซึ่งจะทำให้ผลลัพธ์ผิดพลาดร้ายแรง (inflated numbers)

### โครงสร้างตาราง

```sql
CREATE TABLE master_hierarchy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context_name TEXT NOT NULL,         -- hierarchy family (เช่น 'revenue', 'revenue_org', 'revenue_gl')
    level INTEGER NOT NULL,             -- ลำดับชั้น (0 = top, 1, 2, ...)
    level_label_th TEXT NOT NULL,       -- ชื่อระดับภาษาไทย (เช่น "กลุ่มธุรกิจ")
    level_label_en TEXT NOT NULL,       -- ชื่อระดับภาษาอังกฤษ (เช่น "Business Group")
    level_columns TEXT NOT NULL,        -- JSON array: คอลัมน์ที่เกี่ยวข้อง ["BUSINESS_GROUP"]
    detection_keywords TEXT NOT NULL,   -- JSON array: keywords สำหรับ detect level
    is_active BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'auto',         -- 'manual' (admin) · 'inferred' · 'declared' · 'learned' — DEFAULT เดิม 'auto' = ที่มาไม่รู้ (Plan 8.1)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    parent_column TEXT,                 -- คอลัมน์ของ parent level (NULL สำหรับ top level)
    source_view TEXT,                   -- view/table ที่ hierarchy นี้อ้างอิง
    UNIQUE(context_name, level)
);
```

### Hierarchy Families

`context_name` ทำหน้าที่เป็นชื่อ **hierarchy family** — หนึ่ง business context อาจมีหลาย family:

| family (context_name) | source_view | โครงสร้าง |
|---|---|---|
| `revenue` | revenue_search | กลุ่มธุรกิจ > กลุ่มบริการ > บริการ/ผลิตภัณฑ์ |
| `revenue_org` | revenue_search | สายงาน > กลุ่มงาน > ฝ่าย > ส่วน |
| `revenue_gl` | revenue_search | หมวดบัญชี > รหัสบัญชี |
| `expense` | v_expense_mart | หมวดค่าใช้จ่าย > รายการค่าใช้จ่าย |
| `expense_org` | v_expense_mart | สายงาน > กลุ่มงาน > ฝ่าย |
| `pl_costtype` | TRN_PL_COSTTYPE_NT_MTH | กลุ่มธุรกิจ > กลุ่มบริการ > ผลิตภัณฑ์/บริการ |
| `transfer price` | v_transfer_price | สายงาน (ผู้ให้บริการ) > บริการ |

### ตัวอย่าง Revenue Product Hierarchy (ข้อมูลจริง)

| level | label_th | label_en | level_columns | parent_column |
|---|---|---|---|---|
| 0 | กลุ่มธุรกิจ | Business Group | `["BUSINESS_GROUP", "BUSINESS"]` | NULL |
| 1 | กลุ่มบริการ | Service Group | `["SERVICE_GROUP"]` | BUSINESS_GROUP |
| 2 | บริการ/ผลิตภัณฑ์ | Product/Service | `["PRODUCT_NAME", "PRODUCT"]` | SERVICE_GROUP |

### ทำไมต้องมี Hierarchy?

```
BUSINESS_GROUP > SERVICE_GROUP > PRODUCT_NAME

ถ้า AI ใช้ OR ข้าม level:
WHERE BUSINESS_GROUP = 'Digital' OR PRODUCT_NAME = 'บริการ NT CLOUD'
→ จะได้รายได้ Digital ทั้งหมด + บริการ NT CLOUD ซ้ำ → ตัวเลขพอง!

ที่ถูกต้อง:
WHERE BUSINESS_GROUP = 'Digital' AND PRODUCT_NAME = 'บริการ NT CLOUD'
```

### ประโยชน์

- ป้องกัน "OR across levels" ที่ทำให้ตัวเลขพอง
- DB-driven — admin เพิ่ม/แก้ hierarchy ได้โดยไม่ต้องแก้ code
- `source` / `status` แยกของคนกับที่เครื่องเดา — ระดับที่ bootstrap เสนอ = `proposed` จนกว่า admin รับ (Plan 8.1)
- `detection_keywords` ช่วย AI detect ว่า user ถามเกี่ยวกับ level ไหน

---

## 8. master_hierarchy_values

### หน้าที่

เก็บ **ค่าจริง** ในแต่ละ hierarchy level พร้อม parent-child chains และ aliases — ใช้สำหรับ validate ว่าค่าที่ user ถามมีอยู่จริงและอยู่ level ไหน

### โครงสร้างตาราง

```sql
CREATE TABLE master_hierarchy_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    context_name TEXT NOT NULL,         -- hierarchy family (เช่น 'revenue')
    level INTEGER NOT NULL,             -- hierarchy level (ตรงกับ master_hierarchy.level)
    value TEXT NOT NULL,                -- ค่าจริง (เช่น "Fixed Line & Broadband")
    parent_value TEXT,                  -- ค่า parent (NULL สำหรับ top level)
    aliases TEXT,                       -- JSON array: ชื่ออื่นๆ/keywords (เช่น ["digital"])
    source TEXT DEFAULT 'auto',         -- 'inferred' (extract จากข้อมูล) หรือ 'manual' — status ตามระดับของมัน (Plan 8.1)
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(context_name, level, value)
);
```

### ตัวอย่างข้อมูล (ข้อมูลจริงใน config DB)

| context | level | value | parent_value | aliases |
|---|---|---|---|---|
| revenue | 0 | Digital | NULL | `["digital"]` |
| revenue | 1 | กลุ่มบริการ Cloud & BigData | Digital | `["cloud & bigdata", "กลุ่มบริการ cloud & bigdata"]` |
| revenue | 2 | บริการ NT CLOUD | กลุ่มบริการ Cloud & BigData | `["nt cloud", "บริการ nt cloud"]` |

### ประโยชน์

- Validate ว่าค่าที่ user ถามมีอยู่จริงใน DB
- Parent chain ใช้ drill-down/roll-up (เช่น "บริการ NT CLOUD อยู่ใน กลุ่มบริการ Cloud & BigData อยู่ใน Digital")
- `aliases` ช่วย fuzzy matching (user พิมพ์ "nt cloud" ก็หา "บริการ NT CLOUD" เจอ)
- Auto-extracted จาก data จริง + admin override ได้

---

## 9. keyword_value_index

### หน้าที่

**Smart keyword lookup** — index ค่าจริงจากทุกคอลัมน์ที่ searchable เพื่อให้ระบบ match คำที่ user พิมพ์กับค่าจริงใน DB ได้เร็ว โดยไม่ต้อง scan data ทุกครั้ง

### โครงสร้างตาราง

```sql
CREATE TABLE keyword_value_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,              -- keyword (lowercase, stripped prefixes)
    column_name TEXT NOT NULL,          -- คอลัมน์ที่ค่านี้อยู่
    column_value TEXT NOT NULL,         -- ค่าจริงใน DB
    table_name TEXT NOT NULL DEFAULT 'revenue_search',  -- ตาราง/view ที่ค่านี้อยู่
    context_name TEXT NOT NULL DEFAULT 'revenue',       -- context ที่ค่านี้อยู่
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### วิธีสร้าง Index

`keyword_value_index` ถูกสร้างโดย `build_keyword_index()` ใน `app/services/schema/keyword_index.py`:

1. อ่าน searchable columns จาก `schema_metadata` (is_groupable = 1)
2. Scan DISTINCT values จากทุก searchable column ใน business DB
3. สร้าง keyword โดยตัด prefix ภาษาไทย (เช่น "กลุ่มบริการ", "บริการ", "สายงาน", "ฝ่าย", "รายได้") + แยกคำด้วย space/`-`/`&`/`/` แล้ว lowercase
4. เก็บลง `keyword_value_index` ใน config DB

### ตัวอย่างข้อมูล

| keyword | column_name | column_value | table_name | context_name |
|---|---|---|---|---|
| internet retail | SERVICE_GROUP | กลุ่มบริการ Internet Retail | revenue_search | revenue |
| รายได้อื่น | SERVICE_GROUP | รายได้อื่น | revenue_search | revenue |
| กลุ่มบริการ internet retail | SERVICE_GROUP | กลุ่มบริการ Internet Retail | revenue_search | revenue |

### ใช้ร่วมกับ `get_known_terms()`

Function `get_known_terms()` รวม keywords จาก:
1. `keyword_value_index` — ค่าจริงจาก data
2. `master_hierarchy_values` — ค่า + aliases จาก hierarchy

ใช้สำหรับ dictionary keyword extraction แบบ longest-match เพื่อหาคำที่ user พิมพ์ที่ตรงกับค่าจริงใน DB

### ประโยชน์

- Lookup เร็วโดยไม่ต้อง scan business data ทุกครั้ง
- Keyword stripping ช่วย fuzzy match (เช่น "internet retail" หา "กลุ่มบริการ Internet Retail" เจอ)
- รองรับหลาย context (revenue, expense, ฯลฯ)

---

## สรุปหน้าที่ของตารางทั้งหมด

| ตาราง | หน้าที่ | ใช้ตอนไหน |
|---|---|---|
| `schema_contexts` | เลือก context + main_view | Step 0: Context routing |
| `schema_semantic_mapping` | แปลคำย่อ/ศัพท์ → SQL condition | Step 1: Keyword translation |
| `master_hierarchy` | ตรวจ level ของ dimension | Step 1.5: Level validation |
| `keyword_value_index` | match keyword → actual DB value | Step 2.5: Value lookup |
| `golden_examples` | ตัวอย่าง SQL ที่ดี | Step 2: Few-shot learning |
| `schema_metadata` | ข้อมูล column (type, SUM, GROUP BY) | Step 3: Schema context |
| `schema_business_rules` | กฎการสร้าง SQL | Step 4: Rule enforcement |
| `view_column_mappings` | map view ↔ source columns | Background: metadata propagation |
| `master_hierarchy_values` | ค่าจริง + parent chains + aliases | Background: value validation |

---

## Best Practices

### การ Refresh Cache

หลังจากเพิ่ม/แก้ไขข้อมูลในตารางเหล่านี้ ต้อง refresh cache:

```python
from app.services.schema_service import SchemaService
from app.db.session import config_engine, business_engine

service = SchemaService(db_engine=config_engine, business_engine=business_engine)
service.refresh_cache()
```

### การเพิ่มข้อมูล

ใช้ Admin API endpoints หรือ Admin Agent tools:

- `/admin/schema/columns` — จัดการ schema_metadata
- `/admin/rules` — จัดการ business rules
- `/admin/mappings` — จัดการ semantic mappings
- `/admin/contexts` — จัดการ contexts
- `/admin/golden-examples` — จัดการ golden examples
- `/admin/hierarchy` — จัดการ hierarchy

---

## ไฟล์ที่เกี่ยวข้อง

### Models

- [`app/models/schema_models.py`](../app/models/schema_models.py) — SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule, ViewColumnMapping
- [`app/models/feedback_models.py`](../app/models/feedback_models.py) — GoldenExample

### Services

- [`app/services/schema/service.py`](../app/services/schema/service.py) — SchemaService facade
- [`app/services/schema/prompt_builder.py`](../app/services/schema/prompt_builder.py) — prompt construction
- [`app/services/schema/keyword_index.py`](../app/services/schema/keyword_index.py) — keyword_value_index builder
- [`app/services/schema/view_manager.py`](../app/services/schema/view_manager.py) — view_column_mappings
- [`app/services/schema/context_store.py`](../app/services/schema/context_store.py) — schema_contexts
- [`app/services/hierarchy_service.py`](../app/services/hierarchy_service.py) — master_hierarchy/values
- [`app/services/vanna_service.py`](../app/services/vanna_service.py) — Vanna RAG sync (DB-driven: `vanna_documentation`, rules, golden examples)

### API Endpoints

- [`app/api/v1/admin/`](../app/api/v1/admin/) — Admin CRUD package (schema.py, mappings.py, rules.py, etc.)

### Migrations

- [`database/migrations/003_schema_metadata.sql`](../database/migrations/003_schema_metadata.sql) — schema_metadata
- [`database/migrations/004_admin_config.sql`](../database/migrations/004_admin_config.sql) — schema_contexts
- [`database/migrations/009_master_hierarchy.sql`](../database/migrations/009_master_hierarchy.sql) — master_hierarchy/values
- [`database/migrations/020_update_schema_contexts.sql`](../database/migrations/020_update_schema_contexts.sql) — instruction_th/en
- [`database/migrations/030_add_rule_pattern_columns.sql`](../database/migrations/030_add_rule_pattern_columns.sql) — pattern/check_type

---

## อ่านเพิ่มเติม

- [DATA_DICTIONARY.md](DATA_DICTIONARY.md) — พจนานุกรมข้อมูลของ business tables/views
- [CLAUDE.md](../CLAUDE.md) — คำแนะนำสำหรับ AI Coding Assistants
