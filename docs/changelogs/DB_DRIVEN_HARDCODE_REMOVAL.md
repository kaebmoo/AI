# DB-Driven Hardcode Removal (2026-03-08)

## Overview

ลบ hardcode ทั้งหมดออกจาก Python code — ย้ายเข้า DB ให้ admin จัดการผ่าน UI ได้เลย ไม่ต้อง deploy

**Plan:** `.claude/plans/merry-imagining-yeti.md`

## 6 Phases Completed

---

### Phase 1: Context Instructions → DB-driven

**Problem:** `schema_service.py` มี if/elif block ยาว 20 บรรทัดที่เลือก context-specific instructions (revenue/expense/transfer_price/pl_costtype) — เพิ่ม context ใหม่ต้องแก้ code

**Solution:**
- ลบ if/elif blocks ใน `_build_thai_prompt()` และ `_build_english_prompt()`
- ใช้ `context_info.get('instruction_th')` ตรงจาก `schema_contexts` table
- ตรวจสอบแล้วว่า DB มี instruction_th ครบทุก context (revenue: 526 chars, expense: 703 chars, transfer_price: 160 chars, pl_costtype: 3511 chars)
- เพิ่ม Visualization Rule ใน expense's instruction_th ที่ขาดหาย

**Files Changed:**
- `app/services/schema_service.py` — ลบ if/elif, ใช้ DB value ตรง

**Result:** เพิ่ม context ใหม่ = INSERT row ใน `schema_contexts` → จบ

---

### Phase 2: Prompt Sections → `schema_business_rules`

**Problem:** `_build_thai_prompt()` มี hardcoded strings ยาว 100+ บรรทัด (hierarchy rule, context retention REPLACE/MERGE/RESET, unit conversion, response format)

**Solution:**
- เพิ่ม 2 columns ใน `schema_business_rules`: `rule_category`, `inject_mode`
- INSERT 5 instruction rules: CONTEXT_RETENTION_REPLACE/MERGE/RESET, UNIT_CONVERSION, RESPONSE_FORMAT
- สร้าง `build_hierarchy_rule_text(context_name)` — generate hierarchy rule จาก `master_hierarchy` table อัตโนมัติ
- สร้าง `build_instruction_rules_text(main_view)` — fetch rules จาก DB
- แก้ `_build_thai_prompt()` ให้ใช้ dynamic sections
- แก้ `build_business_rules_text()` ให้ filter `inject_mode='schema_context'` ป้องกัน double injection

**Files Changed:**
- `app/services/schema_service.py` — dynamic prompt generation
- `database/migrations/` — ALTER + INSERT rules

**Result:** Admin แก้ rules ผ่าน UI ได้ + hierarchy rule เปลี่ยนตาม master_hierarchy อัตโนมัติ

---

### Phase 3: Visualization Prompt → Dynamic + schema_metadata

**Problem:**
1. explain_result prompt ซ้ำกัน 3 providers (70+ lines each) — copy-paste
2. chart_postprocessor hardcode TIME_KEYS, measure_patterns, dimension_patterns
3. Column ชื่อใหม่ (เช่น `budget_allocated`) ไม่ถูก detect

**Solution:**

**3.0) Pre-requisite:** UPDATE `dimension_group = 'time_period'` สำหรับ UPPERCASE time columns (YEAR, MONTH, DATE) ทุก view

**3.1) Shared function:** สร้าง `build_explain_prompt()` ใน `chart_postprocessor.py`
- รับ `schema_metadata` + `hierarchy_info` เป็น parameter
- สร้าง prompt dynamically: column hints จาก `is_summable`/`dimension_group`, hierarchy examples จาก `master_hierarchy`

**3.2) 3 Providers:** ลบ 70+ lines hardcoded prompt แต่ละ provider → ใช้ shared function
- ทุก provider ส่ง `hierarchy_info` + `schema_metadata` ไปยัง `build_explain_prompt()`
- `enforce_time_series_rule()` รับ `time_columns` parameter (จาก schema_metadata)
- `auto_detect_chart_config()` รับ `schema_metadata` parameter (ใช้ `is_summable`)

**3.3) ai_service.py:** Load `_schema_metadata` + `_hierarchy_info` ก่อน explain_result call

**Files Changed:**
- `app/providers/chart_postprocessor.py` — shared `build_explain_prompt()`, updated auto_detect
- `app/providers/claude_provider.py` — ใช้ shared function
- `app/providers/gemini_provider.py` — ใช้ shared function
- `app/providers/matcha_provider.py` — ใช้ shared function
- `app/providers/base.py` — updated explain_result ABC signature
- `app/services/ai_service.py` — load metadata + pass to providers

**Result:**
- Column ชื่อใหม่ที่ `is_summable=1` → chart detect ว่าเป็น measure ได้
- Column ชื่อใหม่ที่ `dimension_group='time_period'` → detect ว่าเป็น time ได้
- เพิ่ม chart type ใหม่ = แก้ 1 ที่ (shared function) แทน 3 ที่

---

### Phase 4: Data Warnings → DB

**Problem:** `DATA_WARNINGS` list hardcoded ใน `warning_detector.py` — เพิ่ม warning ต้องแก้ code

**Solution:**
- สร้าง `data_warnings` table (migration `021_data_warnings.sql`)
- Seed: `OTHER_REVENUE_NOT_NET` warning ย้ายจาก hardcoded
- `WarningDetector` อ่านจาก DB ด้วย in-memory cache (1hr TTL)
- Fallback to hardcoded ถ้า DB ไม่พร้อม
- Admin CRUD API: `GET/POST/PUT/DELETE /api/v1/admin/warnings`
- `clear_warnings_cache()` เรียกทุก mutation

**Files Changed:**
- `database/migrations/021_data_warnings.sql`
- `app/services/warning_detector.py` — DB-driven with cache
- `app/models/schema_models.py` — DataWarningModel
- `app/schemas/admin_schemas.py` — DataWarning CRUD schemas
- `app/api/v1/admin.py` — CRUD endpoints

**Result:** เพิ่ม/แก้ warning ผ่าน Admin UI ได้เลย

---

### Phase 5: Model Tier → `ai_models` table

**Problem:** `get_model(tier="cheap")` hardcode model name ใน 3 providers

**Solution:**
- เพิ่ม `tier` column ใน `ai_models` (migration `022_ai_models_tier.sql`)
- UPDATE: haiku → cheap, gemini-flash → cheap, gpt-3.5-turbo → cheap
- สร้าง `lookup_model_by_tier()` ใน `base.py` (shared, 1hr cache)
- 3 providers: `get_model()` → DB lookup first → hardcoded fallback

**Files Changed:**
- `database/migrations/022_ai_models_tier.sql`
- `app/providers/base.py` — `lookup_model_by_tier()`, `clear_model_tier_cache()`
- `app/providers/claude_provider.py` — DB-first get_model()
- `app/providers/gemini_provider.py` — DB-first get_model()
- `app/providers/matcha_provider.py` — DB-first get_model()

**Result:** เปลี่ยน cheap model ใน DB → providers ใช้ model ใหม่ทันที

---

### Phase 6: Query Classifier Patterns → DB

**Problem:** `COMPLEX_PATTERNS` + `SIMPLE_PATTERNS` hardcoded ใน `query_classifier.py` (34 patterns)

**Solution:**
- สร้าง `query_complexity_patterns` table (migration `023_query_complexity_patterns.sql`)
- Seed: 23 complex + 11 simple patterns
- `QueryComplexityClassifier` อ่านจาก DB ด้วย in-memory cache (1hr TTL)
- Fallback to hardcoded ถ้า DB ไม่พร้อม
- Admin CRUD API: `GET/POST/PUT/DELETE /api/v1/admin/query-patterns`
- `clear_patterns_cache()` เรียกทุก mutation

**Files Changed:**
- `database/migrations/023_query_complexity_patterns.sql`
- `app/services/query_classifier.py` — DB-driven with cache
- `app/models/schema_models.py` — QueryComplexityPattern
- `app/schemas/admin_schemas.py` — QueryPattern CRUD schemas
- `app/api/v1/admin.py` — CRUD endpoints

**Result:** เพิ่ม/แก้ pattern ผ่าน Admin UI ได้เลย

---

## New DB Tables

| Table | Rows | Purpose |
|-------|------|---------|
| `data_warnings` | 1 | Data quality warning definitions |
| `query_complexity_patterns` | 34 | Query tier classification patterns |

## Modified DB Tables

| Table | Change | Purpose |
|-------|--------|---------|
| `schema_business_rules` | +`rule_category`, +`inject_mode` columns | Categorize rules for injection control |
| `ai_models` | +`tier` column | Model tier mapping (default/cheap) |
| `schema_metadata` | Updated `dimension_group` for UPPERCASE time columns | Time column detection |

## New Admin API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/admin/warnings` | GET | List data warnings |
| `/api/v1/admin/warnings/{id}` | GET | Get single warning |
| `/api/v1/admin/warnings` | POST | Create warning |
| `/api/v1/admin/warnings/{id}` | PUT | Update warning |
| `/api/v1/admin/warnings/{id}` | DELETE | Delete warning |
| `/api/v1/admin/query-patterns` | GET | List query patterns |
| `/api/v1/admin/query-patterns/{id}` | GET | Get single pattern |
| `/api/v1/admin/query-patterns` | POST | Create pattern |
| `/api/v1/admin/query-patterns/{id}` | PUT | Update pattern |
| `/api/v1/admin/query-patterns/{id}` | DELETE | Delete pattern |

## New Cache Layers

| Cache | Location | TTL | Clear Function |
|-------|----------|-----|----------------|
| Warning definitions | `warning_detector.py` | 1hr | `clear_warnings_cache()` |
| Model tier mapping | `base.py` | 1hr | `clear_model_tier_cache()` |
| Query patterns | `query_classifier.py` | 1hr | `clear_patterns_cache()` |

## Cross-Cutting Pattern

ทุก Phase ใช้ pattern เดียวกัน:
1. **DB-first with cache** — load from DB, cache 1hr, fallback to hardcoded
2. **Idempotent migrations** — `CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE`, `UNIQUE` constraints
3. **Admin API** — CRUD endpoints, ทุก mutation เรียก cache clear
4. **Backward compatible** — hardcoded values เก็บไว้เป็น fallback

## Test Status

- **101 passed, 15 failed** (all pre-existing: PromptVersion missing, validate_sql removed)
- No regressions introduced
