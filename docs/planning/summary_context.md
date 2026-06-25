# AI Assistant - Implementation Summary

## Overview

AI Revenue Query Assistant สำหรับ องค์กร ที่ใช้ AI แปลงคำถามภาษาไทยเป็น SQL

---

## Phase 1: Schema Metadata System

### 1.1 Migration File
**File:** `database/migrations/003_schema_metadata.sql`

| Table | Description |
|-------|-------------|
| `schema_metadata` | เก็บข้อมูล columns สำหรับ AI context |
| `schema_semantic_mapping` | map คำย่อ/business terms → SQL conditions |
| `schema_business_rules` | กฎการสร้าง SQL สำหรับ AI |
| Views | สำหรับ AI prompt building |

### 1.2 SQLAlchemy Models
**File:** `app/models/schema_models.py`

- `SchemaMetadata` - column metadata พร้อมชื่อไทย/อังกฤษ, data types, notes
- `SchemaSemanticMapping` - keyword → SQL condition mapping
- `SchemaBusinessRule` - กฎการสร้าง SQL

### 1.3 Populate Script
**File:** `scripts/populate_schema_metadata.py`

- 22 schema metadata records
- 47 semantic mappings (คำย่อหน่วยงาน + business terms + province/department mappings)
- 16 business rules

---

## Phase 2: Admin API for Context Management

**Files:** `app/api/v1/admin.py`, `app/schemas/admin_schemas.py`

| Endpoint | Description |
|----------|-------------|
| `GET/POST/PUT/DELETE /api/v1/admin/schema/columns` | จัดการ column metadata |
| `GET/POST/PUT/DELETE /api/v1/admin/mappings` | จัดการ semantic mappings |
| `GET/POST/PUT/DELETE /api/v1/admin/rules` | จัดการ business rules |
| `GET/POST/PUT/DELETE /api/v1/admin/golden-examples` | จัดการ few-shot examples |
| `POST /api/v1/admin/refresh-cache` | Refresh schema cache |

---

## Phase 3: Enhanced Schema Service

**File:** `app/services/schema_service.py`

| Method | Description |
|--------|-------------|
| `get_semantic_mappings()` | อ่าน mappings จาก database |
| `get_abbreviation_mappings()` | กรองเฉพาะคำย่อ |
| `get_term_mappings()` | กรองเฉพาะ business terms |
| `build_semantic_mapping_text()` | สร้าง prompt section สำหรับ AI |
| `get_schema_context()` | รวม semantic mappings ใน context |

---

## Phase 4: Database Abstraction Layer

**File:** `app/services/database_adapter.py`

| Class | Description |
|-------|-------------|
| `DatabaseAdapter` | Abstract base class |
| `SQLiteAdapter` | SQLite implementation |
| `PostgreSQLAdapter` | PostgreSQL implementation |
| `MSSQLAdapter` | SQL Server implementation |
| `create_adapter()` | Factory function |

**Config:** เพิ่ม `DB_ENGINE` setting ใน `app/config.py`

---

## Phase 5: Golden Examples Enhancement

**File:** `app/services/prompt_manager.py`

| Method | Description |
|--------|-------------|
| `detect_categories()` | ตรวจจับ category จาก keywords |
| `auto_categorize()` | จัดหมวดหมู่ examples อัตโนมัติ |
| `get_relevant_examples()` | เลือก examples ตาม context |
| `get_category_counts()` | สถิติจำนวน examples ต่อ category |
| `compose_system_prompt()` | เลือก examples ตามคำถาม |

---

## Phase 6: Self-Correction Retry Mechanism (NEW)

**File:** `app/services/ai_service.py`

### 6.1 New Classes & Methods

```python
@dataclass
class RetryStatus:
    """Status update during retry process"""
    attempt: int
    max_attempts: int
    status: str  # "generating", "executing", "error", "retrying", "success", "failed"
    message: str
    sql_query: Optional[str] = None
    error: Optional[str] = None
```

| Method | Description |
|--------|-------------|
| `query_with_retry()` | Query พร้อม auto-retry เมื่อ SQL ผิด |
| `_build_retry_prompt()` | สร้าง prompt สำหรับ retry พร้อม error context |
| `_find_similar_values()` | หาค่าใกล้เคียงใน DB สำหรับ zero results |
| `_check_zero_results_reason()` | วิเคราะห์สาเหตุที่ได้ 0 rows |

### 6.2 Retry Types

| Error Type | Trigger | Action |
|------------|---------|--------|
| `no_sql` | AI ไม่สร้าง SQL | ขอให้ AI สร้างใหม่ |
| `validation_error` | SQL ไม่ผ่าน validation | ส่ง error กลับให้แก้ |
| `execution_error` | SQL error (no such column/table) | ส่ง error + hints |
| `zero_results` | ได้ 0 rows | ส่ง hints ค่าจริงใน DB |

### 6.3 Zero Results Handling

เมื่อ query ได้ 0 rows:
1. วิเคราะห์ WHERE clause หาค่าที่ใช้
2. ค้นหาค่าจริงใน database
3. ส่ง hints กลับให้ AI:
   ```
   Column 'PRODUCT_NAME': ค่าที่มีในระบบ เช่น 'บริการ Broadband'...
   Column 'organization_group_abbr': ค่าที่มีในระบบ เช่น 'อป.', 'ขบ.'...
   ```
4. AI ปรับ SQL ใหม่ (เช่น ใช้ LIKE แทน =)

### 6.4 Flow Diagram

```
User Question
     ↓
[1] Generate SQL
     ↓
[2] Validate SQL
     ↓
[3] Execute SQL
     ↓
    ┌─── Error? ──────→ Retry with error hints
    │
    ├─── 0 rows? ─────→ Retry with value hints
    │
    └─── Success ─────→ Return result
```

---

## Phase 7: Chat API with Retry Support (NEW)

**Files:** `app/api/v1/chat.py`, `app/schemas/chat.py`

### 7.1 Updated Request Schema

```python
class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    provider: Optional[str] = "gemini"
    max_retries: int = Field(default=3, ge=0, le=5)  # NEW
```

### 7.2 Updated Response Schema

```python
class ChatResponse(BaseModel):
    id: int
    conversation_id: Optional[str] = None
    question: str
    answer: str
    sql_query: Optional[str]
    data: Optional[List[Dict[str, Any]]] = None
    execution_time_ms: float
    retry_count: int = 0  # NEW
    retry_history: Optional[List[RetryAttempt]] = None  # NEW
```

### 7.3 API Usage

```bash
POST /api/v1/chat/
{
    "question": "รายได้ nt broadband แยกจังหวัด",
    "provider": "matcha",
    "max_retries": 3
}
```

Response:
```json
{
    "answer": "...",
    "sql_query": "SELECT section, SUM(revenue)...",
    "retry_count": 1,
    "retry_history": [
        {
            "attempt": 1,
            "error_type": "execution_error",
            "error": "no such column: province"
        }
    ]
}
```

---

## Phase 8: Province/Location Semantic Mapping (NEW)

### 8.1 New Semantic Mappings

| Keyword | Target Column | Description |
|---------|---------------|-------------|
| `จังหวัด` | `section` | จังหวัดอยู่ในชื่อ section |
| `รายจังหวัด` | `section` | แยกรายจังหวัด |
| `แยกจังหวัด` | `section` | แยกตามจังหวัด |
| `province` | `section` | Province data |
| `พื้นที่` | `section` | พื้นที่/จังหวัด |

### 8.2 New Business Rules

| Rule Code | Description |
|-----------|-------------|
| `PROVINCE_USE_SECTION` | เมื่อถามเรื่องจังหวัด ให้ใช้ `section` ไม่ใช่ `cost_center` |
| `NO_PROVINCE_COLUMN` | ไม่มี column `province` หรือ `จังหวัด` ในตาราง |

### 8.3 Result

```sql
-- ก่อน (ผิด)
SELECT cost_center, SUM(revenue) FROM revenue_search GROUP BY cost_center
-- Result: "2R30102" (รหัสอ่านไม่รู้เรื่อง)

-- หลัง (ถูก)
SELECT section, SUM(revenue) FROM revenue_search GROUP BY section
-- Result: "ส่วนขายและบริการลูกค้า จันทบุรี" ✅
```

---

## Phase 9: Data Warning System (NEW)

**ระบบแจ้งเตือนผู้ใช้เมื่อข้อมูลต้องการการตีความพิเศษ**

### 9.1 Backend - Warning Detection

**File:** `app/api/v1/chat.py`

```python
DATA_WARNINGS = [
    {
        "code": "OTHER_REVENUE_NOT_NET",
        "keywords": ["รายได้อื่น"],
        "exclude_keywords": ["ผลตอบแทนทางการเงิน"],
        "message": "หมายเหตุ: 'รายได้อื่น' เป็นรายได้ที่ยังไม่สุทธิ",
        "severity": "warning"
    },
]
```

| Function | Description |
|----------|-------------|
| `detect_data_warnings()` | ตรวจสอบ data และ return warnings ที่เกี่ยวข้อง |

### 9.2 Schema Updates

**File:** `app/schemas/chat.py`

```python
class DataWarning(BaseModel):
    code: str
    message: str
    severity: str  # info, warning, important

class ChatResponse(BaseModel):
    # ... existing fields ...
    warnings: Optional[List[DataWarning]] = None  # NEW
```

### 9.3 Frontend - Warning Display

**File:** `frontend/components/Chat/ChatBubble.tsx`

- เพิ่ม `DataWarning` interface
- แสดงกล่อง warning ใต้ AI response
- สีตาม severity:
  - `info` → ฟ้า + ℹ️
  - `warning` → เหลือง + 📝
  - `important` → แดง + ⚠️

**File:** `frontend/app/(app)/index.tsx`

- เพิ่ม Disclaimer ถาวรด้านล่างหน้า Chat
- แถบสีเหลืองแสดงข้อความหมายเหตุ

### 9.4 API Response with Warnings

```json
{
    "answer": "รายได้รวมแยกตามกลุ่มธุรกิจ...",
    "data": [
        {"BUSINESS_GROUP": "Mobile", "total_revenue": 5000000000},
        {"BUSINESS_GROUP": "รายได้อื่น", "total_revenue": 1200000000}
    ],
    "warnings": [
        {
            "code": "OTHER_REVENUE_NOT_NET",
            "message": "หมายเหตุ: 'รายได้อื่น' เป็นรายได้ที่ยังไม่สุทธิ",
            "severity": "warning"
        }
    ]
}
```

### 9.5 Warning Trigger Logic

| Condition | Warning Triggered? |
|-----------|-------------------|
| Data contains "รายได้อื่น" | ✅ Yes |
| Data contains only "ผลตอบแทนทางการเงิน" | ❌ No |
| Data contains "Mobile", "Fixed Line" | ❌ No |

### 9.6 UI Preview

```
┌─────────────────────────────────────┐
│  [AI Response with data]            │
│                                     │
│  ┌─────────────────────────────────┐│
│  │ 📝 หมายเหตุ: 'รายได้อื่น'...    ││  ← Context-aware warning
│  └─────────────────────────────────┘│
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ หมายเหตุ: ข้อมูล "รายได้อื่น"...    │  ← Permanent disclaimer
└─────────────────────────────────────┘
┌─────────────────────────────────────┐
│ [Input Area]                   [📤]│
└─────────────────────────────────────┘
```

---

## Files Summary

### New Files

| File | Description |
|------|-------------|
| `database/migrations/003_schema_metadata.sql` | Migration สำหรับ metadata tables |
| `app/models/schema_models.py` | SQLAlchemy models |
| `app/api/v1/admin.py` | Admin API endpoints |
| `app/schemas/admin_schemas.py` | Pydantic schemas for admin API |
| `app/services/database_adapter.py` | Database abstraction layer |
| `scripts/populate_schema_metadata.py` | Populate initial data |
| `scripts/test_retry_mechanism.py` | Test script for retry mechanism |

### Modified Files

| File | Changes |
|------|---------|
| `app/services/schema_service.py` | Semantic mappings, DB integration |
| `app/services/prompt_manager.py` | Category-aware example selection |
| `app/services/ai_service.py` | Retry mechanism, zero results handling |
| `app/api/v1/chat.py` | Retry, warnings detection, `DATA_WARNINGS` config |
| `app/schemas/chat.py` | `max_retries`, `retry_count`, `retry_history`, `DataWarning`, `warnings` |
| `app/config.py` | `DB_ENGINE` setting |
| `app/main.py` | Include admin router |
| `app/db/base.py` | Import schema models |
| `frontend/components/Chat/ChatBubble.tsx` | Warning display component |
| `frontend/services/chat.ts` | `DataWarning`, `warnings` in response |
| `frontend/app/(app)/index.tsx` | Disclaimer bar, warnings mapping |

---

## Expected Improvements

| Query | Before | After |
|-------|--------|-------|
| "รายได้ นป." | AI ไม่เข้าใจ | `WHERE organization_group_abbr = 'นป.'` |
| "รายได้อสังหาริมทรัพย์" | หา column ไม่เจอ | `WHERE SERVICE_GROUP = 'กลุ่มบริการพัฒนาสินทรัพย์'` |
| "revenue by BU" | สับสนกับ BUSINESS_GROUP | AI เข้าใจ business_unit = organization |
| "แยกรายจังหวัด" | ใช้ `cost_center` (รหัส) | ใช้ `section` (ชื่อจังหวัด) |
| "รายได้ อป.1" | ใช้ผิด column | ใช้ `department_abbr = 'อป.1'` |
| "ผลิตภัณฑ์ Super Fiber" | 0 rows, ไม่มี retry | Retry พร้อม hints → ได้ข้อมูล |
| SQL error: no such column | Error ทันที | Retry 3 ครั้งพร้อมแก้ไข |
| ผลลัพธ์มี "รายได้อื่น" | ไม่มีคำเตือน | แสดง warning ให้ user ทราบ |

---

## AI Providers Supported

| Provider | Model | Status |
|----------|-------|--------|
| Claude | claude-sonnet-4-6 | ✅ Supported |
| Gemini | gemini-2.0-flash-exp | ✅ Supported |
| Matcha | gpt-4o (internal gateway) | ✅ Supported |

---

## Quick Test

```bash
# Test retry mechanism
python scripts/test_retry_mechanism.py

# Test specific query
python -c "
from app.config import settings
from app.services.ai_service import create_matcha_service

service = create_matcha_service(
    api_key=settings.MATCHA_AI_API_KEY,
    api_url=settings.MATCHA_API_URL,
    db_path='./nt_fi_report.sqlite',
    model=settings.MATCHA_MODEL
)
service.refresh_schema()

result = service.query_with_retry(
    question='รายได้ nt broadband ของ อป.1 แยกเป็นรายจังหวัด',
    max_retries=3
)
print(f'Rows: {len(result.data)}, Retries: {result.retry_count}')
print(f'SQL: {result.sql_query}')
"
```

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2025-01-27 | 1.0 | Phase 1-5: Schema metadata, Admin API, Database abstraction |
| 2025-01-28 | 2.0 | Phase 6-8: Self-correction retry, Zero results handling, Province mapping |
| 2025-01-29 | 2.1 | Phase 9: Data Warning System (Backend + Frontend) |
