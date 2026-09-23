# AI Assistant - MCP Servers

> ⚠️ **Server ทั้งสี่ตัวใน directory นี้เป็นของ "ภายใน" (INTERNAL)** — รันแบบ stdio subprocess ให้ pipeline ของแอปใช้ (`app/services/mcp_client.py`)
> **ห้ามต่อ client ภายนอก / desktop LLM (Claude Desktop, Claude Code, Gemini CLI, Codex ฯลฯ) เข้ากับ server เหล่านี้ตรง ๆ กับข้อมูลจริง** และห้ามเปิดออกด้วยการเปลี่ยน transport (`--transport sse`):
> มี tool ที่รับ **SQL ดิบ** (`execute_query` — ผู้เรียกปิด validator ได้ด้วย `validate_first=False`), คืน**ค่าจริงจากข้อมูล** (`get_sample_values`, `get_table_stats`, `get_column_info`), และ **admin tools ที่เขียน config DB / อ่านคำถามของผู้ใช้อื่น** —
> โดย**ไม่มี** API key, workspace / allowlist, `scope`, audit (`query_audit`) หรือ `llm_data_policy` คุมเลย (`mode=ro` กันการเขียน business DB เท่านั้น ไม่ได้จำกัดสิทธิ์อ่าน)
>
> **ผู้เรียกภายนอกใช้ `/api/v1/mcp` ทางเดียว** (facade 3 tools: `ask`, `list_contexts`, `source_status` — Plan 7 Phase 6) — ดู [`docs/manuals/manual_mcp_external.md`](../docs/manuals/manual_mcp_external.md) และ [`docs/DEPLOYMENT_SECURITY.md`](../docs/DEPLOYMENT_SECURITY.md)

## Overview

MCP (Model Context Protocol) Servers สำหรับ AI Assistant ช่วยให้ AI สามารถ:
- รู้จัก schema และ metadata ของ database
- แปลงคำย่อและคำพ้องความหมาย
- ตรวจสอบและรัน SQL อย่างปลอดภัย
- อธิบาย SQL เป็นภาษาไทย

---

## Servers ที่มี

| Server | Tools | Description |
|--------|-------|-------------|
| `nt_metadata_mcp.py` | 13 | Metadata, schema, mappings, business rules |
| `nt_query_mcp.py` | 5 | SQL validation, execution, explanation |
| `nt_validation_mcp.py` | 4 | Business-rule check, confidence score, result validation |
| `nt_admin_mcp.py` | 13 | Admin: search/add mappings-rules-examples, cache, hierarchy, inspect view, query logs / feedback (เขียน config DB — ไม่อยู่ในรายการ startup อัตโนมัติของ `MCPClientService`) |

รวม **35 tools** (13 + 5 + 4 + 13) — ทั้งหมดเป็น tool ภายใน ไม่มีตัวใดเป็น external API

**รองรับ Database:** SQLite, PostgreSQL, MSSQL

---

## Quick Start

### 1. ติดตั้ง Dependencies

```bash
cd mcp_servers
pip install -r requirements.txt
```

### 2. รัน MCP Server

```bash
# Metadata Server
python -m mcp_servers.nt_metadata_mcp

# Query Server
python -m mcp_servers.nt_query_mcp

# กำหนด Database URL
METADATA_DB_URL="sqlite:///nt_fi_report.sqlite" python -m mcp_servers.nt_metadata_mcp
```

### 3. รัน Tests

```bash
python mcp_servers/test_metadata_mcp.py  # 7/7 tests
python mcp_servers/test_query_mcp.py     # 5/5 tests
```

---

## Metadata MCP (13 Tools)

### Context Management

| Tool | Description | Example |
|------|-------------|---------|
| `get_available_contexts()` | ดึงรายการ contexts ทั้งหมด | `[{name: "revenue"}, {name: "expense"}]` |
| `route_question_to_context(question)` | ระบุ context จากคำถามอัตโนมัติ | "ค่าใช้จ่าย..." → expense (confidence: 0.95) |
| `get_context_info(context_name)` | ข้อมูลรายละเอียด context | main_view, keywords, description |

### Schema Information

| Tool | Description | Example |
|------|-------------|---------|
| `get_schema_for_context(context_name)` | ดึง schema ทั้งหมดของ context | columns, types, thai_names |
| `get_column_info(column_name, table_name)` | ข้อมูล column เฉพาะ | type, sample_values, is_summable |

### Semantic Mappings

| Tool | Description | Example |
|------|-------------|---------|
| `get_semantic_mappings(limit)` | ดึง mappings ทั้งหมด | คำย่อ, synonyms |
| `search_mapping_for_term(term)` | ค้นหา mapping เฉพาะ | "อป.1" → department_abbr = 'อป.1' |

### Business Rules

| Tool | Description | Example |
|------|-------------|---------|
| `get_business_rules(context_name)` | ดึงกฎธุรกิจทั้งหมด | GROUP_BY_REQUIRED, QUOTE_THAI_COLUMNS |
| `check_rule_violation(sql, question, table)` | ตรวจสอบ SQL ว่าละเมิดกฎไหม | violations: [], warnings: [] |

### Golden Examples

| Tool | Description | Example |
|------|-------------|---------|
| `get_golden_examples(limit, category)` | ดึงตัวอย่าง SQL | question, expected_sql |
| `find_similar_example(question)` | ค้นหาตัวอย่างที่คล้ายกัน | similarity score, matched example |

### Database Info

| Tool | Description | Example |
|------|-------------|---------|
| `get_database_info()` | ข้อมูล database | engine: sqlite, status: connected |
| `get_syntax_rules()` | กฎ SQL syntax ตาม engine | string_concat: `\|\|` for SQLite |

---

## Query MCP (5 Tools)

| Tool | Description | Example |
|------|-------------|---------|
| `validate_sql(sql)` | ตรวจสอบ SQL ว่าปลอดภัย | valid: true/false, issues, warnings |
| `execute_query(sql, limit)` | รัน SQL และดูผลลัพธ์ | data: [...], row_count: 100 |
| `get_sample_values(column, table, limit)` | ดูค่าตัวอย่างใน column | values: ["ฝ่ายการเงิน", ...] |
| `explain_sql_thai(sql)` | อธิบาย SQL เป็นภาษาไทย | "รวมยอด → จากตารางรายได้ → กรองปี 2568" |
| `get_table_stats(table_name)` | ดูสถิติตาราง | row_count: 315,984, columns: [...] |

---

## Use Cases

### 1. AI Generate SQL ที่แม่นยำ

```
User: "รายได้ฝ่าย อป.1 เดือนมกราคม 2568"

AI ใช้ MCP:
1. route_question_to_context("รายได้...")
   → context: "revenue"

2. get_schema_for_context("revenue")
   → columns: [year, month, department, revenue...]

3. search_mapping_for_term("อป.1")
   → department_abbr = 'อป.1'

4. get_business_rules("revenue")
   → ต้อง GROUP BY เมื่อใช้ SUM

5. AI สร้าง SQL:
   SELECT department, SUM(revenue)
   FROM revenue_search
   WHERE year = 2025 AND month = 1 AND department_abbr = 'อป.1'
   GROUP BY department
```

### 2. AI Validate & Execute SQL

```
AI สร้าง SQL แล้วตรวจสอบ:

1. validate_sql(sql)
   → valid: true
   → warnings: ["Consider adding LIMIT"]

2. execute_query(sql, limit=100)
   → success: true
   → data: [{department: "ฝ่ายบริการ", revenue: 1500000}, ...]

3. explain_sql_thai(sql)
   → "รวมยอดรายได้ จากตารางรายได้ กรองปี 2568 เดือนมกราคม
      หน่วยงาน อป.1 จัดกลุ่มตามฝ่าย"
```

### 3. AI Self-Correct (ป้องกัน SQL อันตราย)

```
AI สร้าง SQL ผิด:
SELECT * FROM revenue; DROP TABLE users

1. validate_sql(sql)
   → valid: false
   → issues: [
       "Dangerous operation: DROP",
       "Multiple statements not allowed"
     ]

2. AI แก้ไขและสร้างใหม่
```

### 4. AI เข้าใจคำย่อภาษาไทย

```
User: "รายได้ Mobile ปี 68"

1. search_mapping_for_term("Mobile")
   → BUSINESS_GROUP = 'Mobile'

2. search_mapping_for_term("ปี 68")
   → year = 2025 (พ.ศ. 2568 → ค.ศ. 2025)

3. AI สร้าง SQL ที่ถูกต้อง
```

---

## Integration

### Claude Desktop / MCP client อื่น — ต่อที่ `/api/v1/mcp` เท่านั้น

Server ในไดเรกทอรีนี้เป็น **stdio ภายใน** ของแอป: `nt-query` รับ SQL ดิบ และไม่มี key / workspace /
allowlist / scope / audit / `llm_data_policy` ต่อ client ภายนอกเข้ามาตรง ๆ ไม่ได้ ไม่ว่ากรณีใด
(ไฟล์ตัวอย่าง `claude_desktop_config.json` ที่เคยสอนวิธีนั้นถูกลบแล้ว)

ทางเดียวคือ facade `POST /api/v1/mcp` ซึ่งมี 3 tool (`ask` / `list_contexts` / `source_status`) และบังคับกติกาครบ
Claude Desktop เรียก HTTP เองไม่ได้ (มันรัน process ในเครื่องแล้วคุยทาง stdio) จึงต่อผ่านตัวแปลง
`scripts/mcp_stdio_bridge.py` — key อยู่ใน env ไม่ได้อยู่ในไฟล์ config

วิธีตั้งค่า + ตัวอย่าง config: [`docs/manuals/manual_mcp_external.md`](../docs/manuals/manual_mcp_external.md)

### Python Client

```python
from mcp_servers.nt_metadata_mcp import (
    get_available_contexts,
    route_question_to_context,
    get_schema_for_context
)

from mcp_servers.nt_query_mcp import (
    validate_sql,
    execute_query,
    explain_sql_thai
)

# ใช้งาน
contexts = get_available_contexts()
result = route_question_to_context("รายได้เดือนมกราคม")
schema = get_schema_for_context("revenue")

validation = validate_sql("SELECT * FROM revenue_search")
if validation["valid"]:
    data = execute_query("SELECT * FROM revenue_search", limit=10)
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `METADATA_DB_URL` | Database connection string | `sqlite:///nt_fi_report.sqlite` |

### Database URL Formats

```bash
# SQLite
METADATA_DB_URL="sqlite:///path/to/db.sqlite"

# PostgreSQL
METADATA_DB_URL="postgresql://user:pass@localhost:5432/dbname"

# MSSQL
METADATA_DB_URL="mssql://user:pass@localhost:1433/dbname"
```

---

## Security Features

### SQL Validation

- ป้องกัน dangerous operations: `DROP`, `DELETE`, `TRUNCATE`, `ALTER`, `INSERT`, `UPDATE`
- ป้องกัน SQL injection patterns
- อนุญาตเฉพาะ `SELECT` และ `WITH` (CTE)
- ตรวจสอบ multiple statements

### Warnings

- `SELECT *` - แนะนำให้เลือก columns เฉพาะ
- No `WHERE` clause - อาจได้ข้อมูลมาก
- No `LIMIT` - แนะนำให้จำกัดผลลัพธ์
- Thai columns without quotes - ต้องใส่ double quotes

---

## File Structure

```
mcp_servers/
├── __init__.py              # Package init
├── nt_metadata_mcp.py       # Metadata server (13 tools)
├── nt_query_mcp.py          # Query server (5 tools)
├── nt_validation_mcp.py     # Validation server (4 tools)
├── nt_admin_mcp.py          # Admin server (13 tools — เขียน config DB)
├── test_metadata_mcp.py     # Tests (7/7 passed)
├── test_query_mcp.py        # Tests (5/5 passed)
├── requirements.txt         # Dependencies
└── README.md                # This file
```

---

## Dependencies

```
mcp==1.26.0            # same pin as ../requirements.txt — 2.x renamed FastMCP
psycopg2-binary>=2.9.0  # PostgreSQL
pyodbc>=4.0.0           # MSSQL
python-dotenv>=1.0.0
```

---

## Test Results

```
Metadata MCP Server - Test Suite
====================================
[PASS] Contexts
[PASS] Routing
[PASS] Schema
[PASS] Mappings
[PASS] Rules
[PASS] Examples
[PASS] DB Info

Total: 7/7 tests passed

Query MCP Server - Test Suite
====================================
[PASS] Validate SQL (8/8 cases)
[PASS] Execute Query
[PASS] Sample Values
[PASS] Explain SQL Thai
[PASS] Table Stats

Total: 5/5 tests passed
```

---

## Roadmap

- [x] Phase 1: Core MCP Servers (nt_metadata_mcp, nt_query_mcp)
- [ ] Phase 2: Validation & Confidence (nt_validation_mcp)
- [ ] Phase 3: Reporting (nt_reporting_mcp)
- [ ] Phase 4: Backend Integration (mcp_client.py)
- [ ] Phase 5: Deployment (docker-compose)

---

## License

Source-available public reference
