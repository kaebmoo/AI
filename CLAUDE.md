# Instructions for AI Coding Assistants

## Project: NT AI Assistant

AI Query Assistant สำหรับ NT (National Telecom)
ใช้ Claude API หรือ Google AI (Gemini) ในการแปลงคำถามภาษาไทยเป็น SQL

---

## Quick Reference

### Database

- **Type**: SQLite
- **File**: `revenue.sqlite`
- **Main Table**: `revenue`

### AI Providers Supported

- **Claude API (Anthropic)** - claude-sonnet-4-5, claude-opus-4, claude-haiku-3-5
- **Google AI / Gemini API** - gemini-3-flash, gemini-2.0-flash-exp
- **Matcha (NT Gateway)** - gpt-4.1, gpt-4o, gpt-4-turbo (OpenAI-compatible)

**Configuration:** Admin can enable/disable providers and select models via Admin Settings UI

---

## Critical Data Handling Rules

### 1. DATE Column ⚠️

DATE เก็บเป็น **Unix Timestamp (Milliseconds)** ไม่ใช่ Text

```sql
-- ❌ WRONG
SELECT DATE FROM revenue
-- Result: 1735689600000

-- ✅ CORRECT
SELECT date(DATE / 1000, 'unixepoch') as readable_date FROM revenue
-- Result: 2025-01-01

-- ✅ RECOMMENDED: ใช้ YEAR, MONTH แทน
SELECT * FROM revenue WHERE YEAR = 2025 AND MONTH = 1
```

### 2. Thai Column Names ⚠️

Column ที่มีชื่อภาษาไทยต้อง **double quotes**

```sql
-- ❌ WRONG
SELECT กลุ่มธุรกิจ, หมวดบัญชี FROM revenue

-- ✅ CORRECT
SELECT "กลุ่มธุรกิจ", "หมวดบัญชี" FROM revenue
```

### 3. Revenue Unit ⚠️

REVENUE_VALUE มีหน่วยเป็น **บาท** (ไม่ใช่ล้านบาท)

```sql
-- รายได้ 162.24 บาท (ไม่ใช่ 162.24 ล้านบาท)
SELECT SUM(REVENUE_VALUE) as total_baht FROM revenue

-- ถ้าต้องการแสดงเป็นล้านบาท
SELECT SUM(REVENUE_VALUE) / 1000000 as total_million FROM revenue
```

### 4. Thai Year Conversion

```sql
-- ปี พ.ศ. = ปี ค.ศ. + 543
SELECT YEAR, YEAR + 543 as year_th FROM revenue

-- 2025 → 2568
```

---

## Table Schema: revenue

### Time Columns

| Column | Type    | Example       | Notes                               |
| ------ | ------- | ------------- | ----------------------------------- |
| YEAR   | INTEGER | 2025          | ปี ค.ศ.                         |
| MONTH  | INTEGER | 1             | เดือน (1-12)                   |
| DATE   | INTEGER | 1735689600000 | Unix ms -**ต้องแปลง** |

### Organization Hierarchy

```
DIVISION (สายงาน)
  └── GROUP (กลุ่ม)
       └── DEPARTMENT (ฝ่าย)
            └── SECTION (ส่วน)
                 └── COST_CENTER (ศูนย์ต้นทุน)
```

| Column                 | Example                                                        |
| ---------------------- | -------------------------------------------------------------- |
| DIVISION               | "สายงานบริหารองค์กร"                         |
| GROUP                  | "กลุ่มเลขานุการและบริหารงานกลาง" |
| DEPARTMENT             | "ฝ่ายเลขานุการผู้บริหาร"                 |
| SECTION                | "ส่วนการประชุมผู้บริหาร"                 |
| COST_CENTER            | "1C00104"                                                      |
| กลุ่มธุรกิจ | "กลุ่มสนับสนุน"                                   |

### Product Columns

| Column        | Example                          |
| ------------- | -------------------------------- |
| PRODUCT_KEY   | "192020001"                      |
| PRODUCT_NAME  | "รายได้อื่น"           |
| PRODUCT       | "192020001 รายได้อื่น" |
| SERVICE_GROUP | "รายได้อื่น"           |
| BUSINESS      | "8 รายได้อื่น"         |

### Accounting Columns

| Column             | Example                                                                     |
| ------------------ | --------------------------------------------------------------------------- |
| REPORT_CODE        | "R10"                                                                       |
| GL_CODE            | "49901101"                                                                  |
| GL_NAME            | "ดอกเบี้ยเงินให้กู้ยืม-กองทุนสวัสดิการ" |
| GL_GROUP           | "ผลตอบแทนทางการเงินและรายได้อื่น"            |
| หมวดบัญชี | "R10 ผลตอบแทนทางการเงินและรายได้อื่น"        |

### Value Columns

| Column        | Type | Can SUM? |
| ------------- | ---- | -------- |
| REVENUE_VALUE | REAL | ✅ Yes   |
| AMOUNT        | REAL | ✅ Yes   |

---

## Common SQL Patterns

### รายได้รวมแยกตามเดือน

```sql
SELECT YEAR, MONTH, SUM(REVENUE_VALUE) as total
FROM revenue
GROUP BY YEAR, MONTH
ORDER BY YEAR, MONTH
```

### รายได้แยกตามกลุ่มธุรกิจ

```sql
SELECT "กลุ่มธุรกิจ", SUM(REVENUE_VALUE) as total
FROM revenue
WHERE YEAR = 2025 AND MONTH = 1
GROUP BY "กลุ่มธุรกิจ"
ORDER BY total DESC
```

### รายได้แยกตามสายงาน

```sql
SELECT DIVISION, SUM(REVENUE_VALUE) as total
FROM revenue
WHERE YEAR = 2025
GROUP BY DIVISION
ORDER BY total DESC
```

### Drill-down หน่วยงาน

```sql
SELECT 
    DIVISION,
    "GROUP",
    DEPARTMENT,
    SUM(REVENUE_VALUE) as total
FROM revenue
WHERE YEAR = 2025 AND MONTH = 1
GROUP BY DIVISION, "GROUP", DEPARTMENT
ORDER BY total DESC
```

---

## File Locations

```
nt-revenue-assistant/
├── docs/
│   └── DATA_DICTIONARY.md      # Schema documentation
├── database/
│   └── schema_metadata.sql     # Metadata table setup
├── app/
│   ├── services/
│   │   ├── schema_service.py   # Schema management
│   │   └── ai_service.py       # AI integration (Claude + Gemini)
│   └── core/
└── CLAUDE.md                   # This file
```

---

## API Integration

### Claude API (Anthropic)

```python
from app.services.ai_service import create_claude_service

service = create_claude_service(
    api_key="sk-ant-...",
    db_path="revenue.sqlite"
)

result = service.query("รายได้รวมเดือนมกราคม 2568")
print(result.sql_query)
print(result.explanation)
```

### Google AI (Gemini)

```python
from app.services.ai_service import create_gemini_service

service = create_gemini_service(
    api_key="AIza...",
    db_path="revenue.sqlite"
)

result = service.query("รายได้รวมเดือนมกราคม 2568")
print(result.sql_query)
print(result.explanation)
```

### Matcha (NT Gateway)

```python
from app.services.ai_service import create_matcha_service

service = create_matcha_service(
    api_key="sk-...",
    api_url="https://aigateway.ntictsolution.com/v1/chat/completions",
    model="gpt-4.1",
    db_path="revenue.sqlite"
)

result = service.query("รายได้รวมเดือนมกราคม 2568")
print(result.sql_query)
print(result.explanation)
```

**Note:** Matcha is the default provider. Configuration is stored in `admin_config` table with fallback to `.env`

---

## Testing

### Mock AI for Tests

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_ai_response():
    return {
        "sql": "SELECT SUM(REVENUE_VALUE) FROM revenue WHERE YEAR = 2025",
        "explanation": "รายได้รวมปี 2568",
        "tokens_used": 100
    }
```

---

## When Adding New Data Sources

1. **Update** `docs/DATA_DICTIONARY.md`
2. **Run** `database/schema_metadata.sql` to update metadata
3. **Call** `schema_service.refresh_cache()` to reload
4. **Test** with sample queries

---

## Important Notes

1. **SELECT only** - No INSERT, UPDATE, DELETE
2. **Thai response** - Always explain in Thai
3. **Unit = Baht** - Not millions
4. **Use YEAR/MONTH** - Instead of DATE conversion
5. **Quote Thai columns** - "กลุ่มธุรกิจ", "หมวดบัญชี"

---

## Dependencies

```
# requirements.txt
anthropic>=0.18.0      # Claude API
google-genai           # Gemini API
openai                 # For Matcha (OpenAI-compatible)
```

---

## Admin Configuration System

### Dynamic Provider Management

The system uses a **3-tier fallback** configuration:

1. **Database (admin_config table)** - Admin changes via Web UI
2. **.env file** - Developer/deployment config
3. **Hardcoded defaults** - Safety net

### Configuration Tables

**admin_config:**
- `default_ai_provider` - Which provider to use (claude/gemini/matcha)
- `claude_enabled`, `gemini_enabled`, `matcha_enabled` - Enable/disable providers
- `claude_model`, `gemini_model`, `matcha_model` - Model selection
- Feature flags: `rag_enabled`, `auto_context_detection`, `debug_mode`, etc.

**schema_contexts:**
- Multiple data contexts with routing keywords
- Custom AI instructions per context
- Example: "รายได้" → revenue, "ค่าใช้จ่าย" → expense

### Admin Settings UI

**Access:** `http://localhost:5173/settings` (Admin only)

**Features:**
- Enable/disable AI providers
- Select default provider and models
- Configure Matcha API gateway URL
- Toggle feature flags
- Manage data contexts

### User Experience

**Dynamic Model Selector:**
- Frontend automatically loads enabled providers from backend
- Users only see providers that admin has enabled
- If admin disables Claude → Claude button disappears from UI

**API Endpoints:**
```python
# Public - no auth required
GET /api/v1/admin/config/ai/providers  # Get active providers

# Admin only
GET /api/v1/admin/config/ai            # Get full AI config
PUT /api/v1/admin/config/ai            # Update AI config
```

### Configuration Priority Example

```python
# How system determines default provider:

# 1. Try database first
default_provider = db.query(admin_config).filter(
    config_key='default_ai_provider'
).first()

# 2. Fallback to .env
if not default_provider:
    default_provider = os.getenv('AI_PROVIDER')

# 3. Fallback to hardcoded
if not default_provider:
    default_provider = 'matcha'
```

---

## Contact

- **Department**: Finance (บชง.)
- **Project**: NT AI Assistant
- **Classification**: Internal Use Only
