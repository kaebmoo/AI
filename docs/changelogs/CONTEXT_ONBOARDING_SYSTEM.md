# Changelog: Context Onboarding System + P&L Quick Fix

**Date:** 2026-03-18
**Author:** Claude Code
**Impact:** New system + DB config fix

---

## Summary

สร้างระบบ **Context Onboarding** สำหรับวิเคราะห์ view/table ใหม่แล้ว auto-generate config ทั้งหมดที่จำเป็นสำหรับ NL-to-SQL system + แก้ปัญหา P&L SQL generation ที่ผิด

## Background

เมื่อ AI ได้รับคำถาม "ผลดำเนินงานปี 69 กลุ่มธุรกิจ รายเดือน" ระบบสร้าง SQL ที่ผิด:
```sql
SELECT business_unit, report_month, SUM(amount_value) AS amount
FROM v_pl_costtype_nt_mth_clean WHERE report_year = 2026
GROUP BY business_unit, report_month
```

ปัญหาคือ `v_pl_costtype_nt_mth_clean` เป็น **semi-crosstab** — `amount_value` มีความหมายต่างกันตาม `main_group` (01=รายได้, 02=ต้นทุน, 03=กำไรขั้นต้น, etc.) การ SUM โดยไม่แยก main_group จึงรวมทุกอย่างเข้าด้วยกัน

---

## Part 1: P&L Quick Fix (DB Config Changes)

### 1A. New Business Rule: `PL_MUST_FILTER_MAINGROUP`
- **Table:** `schema_business_rules`
- **Severity:** critical
- **Rule:** ห้าม SUM(amount_value) โดยไม่ระบุ main_group — ต้อง GROUP BY, WHERE filter, หรือ CASE WHEN pivot

### 1B. New Golden Example: "ผลดำเนินงาน กลุ่มธุรกิจ รายเดือน"
- Pattern ที่ fail → correct SQL with CASE WHEN pivot (revenue_mb, cost_mb, gross_profit_mb, operating_profit_mb, net_profit_mb)

### 1C. Updated Golden Example #15
- จาก: แสดงแค่ `main_group = '01.รายได้'`
- เป็น: แสดง P&L breakdown (revenue + gross_profit) พร้อม monthly pivot

### 1D. Updated `instruction_th`
- เพิ่ม critical rule ด้านบนสุด: "⛔ ห้าม SUM(amount_value) โดยไม่มี main_group"

### 1E. Updated `schema_metadata` for `amount_value`
- `special_notes`: "ห้าม SUM โดยไม่มี main_group context — view เป็น semi-crosstab P&L"

---

## Part 2: Context Onboarding System

### Architecture: 5-Phase Pipeline

```
Phase 1 (Inspect) → Phase 2 (LLM Analyze) → Phase 3 (Generate) → Phase 4 (Apply) → Phase 5 (Validate)
    SQL only         Multi-provider LLM        Config bundle        DB insert          Check config
```

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `app/services/context_onboarding.py` | ~600 | Core pipeline service (5 phases) |
| `scripts/onboard_context.py` | ~150 | CLI wrapper |
| `.claude/skills/onboard-context.md` | ~100 | Claude Code interactive skill |

### Modified Files

| File | Change |
|------|--------|
| `app/api/v1/admin.py` | +3 endpoints: `/contexts/onboard`, `/contexts/onboard/inspect`, `/contexts/onboard/validate` |

### Key Classes

```python
# Phase 1: SQL-based profiling (no LLM)
DataInspector.inspect(view_name) → InspectionResult

# Phase 2: LLM analysis (multi-provider)
LLMAnalyzer.analyze(inspection, provider, model) → Dict

# Phase 3: Convert analysis → SQL INSERT statements
ConfigGenerator.generate(analysis) → ConfigBundle

# Phase 4: Apply to DB
ConfigApplicator.apply(bundle, dry_run) → Dict

# Phase 5: Validate config exists
ConfigValidator.validate(view_name) → ValidationResult

# Orchestrator
ContextOnboardingService.run_full_pipeline(view_name, provider, model, dry_run) → Dict
```

### Phase 1: Data Inspection (Key Innovation)

**Semi-crosstab detection:** ตรวจจับว่า view เป็น semi-crosstab โดย:
1. วิเคราะห์ SUM(value_col) GROUP BY category_col
2. ถ้ามี mixed +/- signs across categories → likely semi-crosstab
3. ถ้า categories >= 3 → confirm semi-crosstab

**ทดสอบแล้ว:** `v_pl_costtype_nt_mth_clean` ถูก detect เป็น semi_crosstab:
```
amount_value by main_group: mixed +/- → ⚠️ SEMI-CROSSTAB
  01.รายได้: sum=141,840,452,690
  02.ต้นทุนบริการ: sum=121,300,618,177
  03.กำไรขั้นต้น: sum=20,539,834,513
```

### Phase 2: Multi-Provider LLM Support

```bash
# Default (from admin_config)
python scripts/onboard_context.py --view-name v_new_view --dry-run

# Gemini
python scripts/onboard_context.py --view-name v_new_view --provider gemini --model gemini-2.5-flash

# Claude
python scripts/onboard_context.py --view-name v_new_view --provider claude

# Matcha / OpenAI-compatible
python scripts/onboard_context.py --view-name v_new_view --provider matcha --model gpt-4.1
```

### Config Tables Covered (ครบ 7 ตาราง)

| Table | Generated |
|-------|-----------|
| `schema_contexts` | 1 row (context definition + instructions) |
| `schema_metadata` | 10-15 rows (column metadata) |
| `schema_business_rules` | 5-10 rows (SQL correctness rules) |
| `golden_examples` | 5-8 rows (few-shot examples) |
| `schema_semantic_mapping` | 10-20 rows (keyword mappings) |
| `master_hierarchy` | 2-4 rows (dimension hierarchy) |
| `data_warnings` | 1-3 rows (quality alerts) |

### Admin API Endpoints

```
GET  /api/v1/admin/contexts/onboard/available-views  # List views with status
POST /api/v1/admin/contexts/onboard                   # Full pipeline
POST /api/v1/admin/contexts/onboard/inspect            # Phase 1 only (fast)
POST /api/v1/admin/contexts/onboard/validate           # Check config exists
```

All endpoints use **Pydantic schemas** (`OnboardingRequest`, `InspectRequest`, `ValidateRequest`) for type-safe request validation.

---

## Part 3: Admin Web UI (2026-03-18)

### Context Onboarding Wizard Page

4-step wizard UI ใน Admin Dashboard สำหรับ onboard view/table ใหม่แบบ visual

**Route:** `/context-onboarding`
**Menu:** Data Management → Context Onboarding (หลัง Data Contexts)

#### Step 1: Select View
- Dropdown แสดง views/tables ทั้งหมดจาก `GET /available-views`
- แยก: Unconfigured (badge เขียว) vs Configured (badge ส้ม = re-onboard)
- แสดง row count, type (view/table)

#### Step 2: Inspect
- แสดงผล Phase 1: row count, detected structure (long_table/semi_crosstab/wide_table)
- Column table: name, type, distinct count, flags (NUMERIC/TIME/PREFIX)
- Cross-column warnings (semi-crosstab alert)
- Quality issues list
- เลือก AI Provider (gemini/claude/matcha)

#### Step 3: AI Analysis & Preview
- Loading state (10-30 sec)
- Context configuration preview
- Generated config stats (rules/examples/mappings counts)
- SQL preview (collapsible, dry-run output)
- Config summary markdown

#### Step 4: Results
- Success/failure status
- Applied config stats
- Validation results (passed/issues)
- Navigation buttons: "Go to Data Contexts", "Onboard Another View"

### Files Created/Modified

| File | Action |
|------|--------|
| `frontend-admin/src/pages/ContextOnboarding.tsx` | NEW — wizard page |
| `frontend-admin/src/services/onboardingService.ts` | NEW — API service + types |
| `frontend-admin/src/App.tsx` | EDIT — route `/context-onboarding` |
| `frontend-admin/src/components/Layout/AdminLayout.tsx` | EDIT — menu item (RocketOutlined) |
| `app/schemas/admin_schemas.py` | EDIT — 9 onboarding schemas |
| `app/api/v1/admin/onboarding.py` | EDIT — typed endpoints + `_get_business_db_path()` compatibility shim + available-views endpoint |
| `app/services/context_onboarding.py` | EDIT — `list_available_views()` + fix `generate_config()` signature |

### Backend Bug Fixes (part of Admin UI work)

1. **BUG-1 Fixed:** `generate_config()` — `view_name` เป็น required parameter แล้ว, ลบ `_last_view_name` fragile pattern
2. **BUG-2 Fixed:** DB path — สร้าง `_get_business_db_path()` helper ใช้ร่วม 4 endpoints (ไม่ hardcode อีกต่อไป)
3. **BUG-4 Fixed:** Pydantic schemas — 9 schemas เพิ่มใน `admin_schemas.py`, endpoints ทั้งหมดใช้ typed request/response

---

## Design Principles Applied

1. **No Hardcoding** — ทุก config อยู่ใน DB, generate จาก LLM
2. **DB-Driven** — ใช้ existing config tables ทั้งหมด
3. **Admin Self-Service** — Admin API + Claude Code Skill
4. **Automation First** — auto-detect semi-crosstab, auto-generate rules
5. **Multi-Provider** — reuse existing provider registry
6. **Idempotent** — INSERT OR REPLACE / INSERT OR IGNORE

---

## Testing Results

### Phase 1 Inspection (v_pl_costtype_nt_mth_clean)
- ✅ Detected: semi_crosstab
- ✅ Cross-column: amount_value × main_group = mixed signs
- ✅ Quality issues: prefix_inconsistency in sub_group, business_unit
- ✅ Column classification: value/category/time/dimension correct
- ✅ CLI `--inspect-only` works

### Quick Fix Verification
- ✅ Business rule PL_MUST_FILTER_MAINGROUP inserted
- ✅ Golden example for monthly P&L by BU inserted
- ✅ Example #15 updated with P&L breakdown
- ✅ instruction_th updated with critical rule
- ✅ schema_metadata special_notes updated
