# Context Onboarding — Backend Fixes + Web Admin UI Plan

**Date:** 2026-03-18  
**Target:** Claude Code Execution  
**Project Root:** `/Users/seal/Documents/GitHub/AI/`

---

## Part 1: สิ่งที่ตรวจพบจาก Code จริง

### 1.1 Backend — สิ่งที่ทำเสร็จแล้ว

| Component | Status | หมายเหตุ |
|-----------|--------|----------|
| `app/services/context_onboarding.py` (~600 lines) | Done | 5 classes: DataInspector, LLMAnalyzer, ConfigGenerator, ConfigApplicator, ConfigValidator + ContextOnboardingService orchestrator |
| `scripts/onboard_context.py` (~150 lines) | Done | CLI wrapper ครบทุก option |
| `.claude/skills/onboard-context.md` | Done | Claude Code interactive skill |
| 3 Admin API endpoints ใน `admin.py` | Done | `/contexts/onboard`, `/contexts/onboard/inspect`, `/contexts/onboard/validate` |
| P&L Quick Fix (5 DB changes) | Done | business rule, golden examples, instruction, metadata |

### 1.2 Backend — ปัญหาที่พบ (ต้องแก้)

**BUG-1: `_last_view_name` fragile pattern**
- `ContextOnboardingService.generate_config()` ใช้ `self._last_view_name` ที่ set จากข้างนอก
- ถ้าเรียก `generate_config()` โดยไม่เรียก `run_full_pipeline()` ก่อนจะ crash (AttributeError)
- แก้: ให้ `generate_config()` รับ `view_name` เป็น required parameter แทน

**BUG-2: Hardcoded DB path ใน admin endpoints**
- `onboard_context()` endpoint คำนวณ path เอง: `os.path.dirname(...)` 4 ชั้น
- `inspect_context()` และ `validate_context()` ก็ hardcode `"nt_fi_report.sqlite"`
- แก้: ใช้ `settings.BUSINESS_DB_PATH` หรือ config ที่มีอยู่แล้ว (ต้องอ่าน `app/config.py` ก่อน)

**BUG-3: Dual DB connection**
- `context_onboarding.py` ใช้ raw `sqlite3.connect()` ตลอด
- Admin endpoints ใช้ SQLAlchemy session
- เรื่องนี้ตั้งใจ เพราะ business DB (nt_fi_report.sqlite) แยกจาก app DB (app.db)
- **ไม่ต้องแก้** — แค่ให้ DB path มาจาก config ไม่ hardcode

**BUG-4: ไม่มี Pydantic schemas สำหรับ onboarding**
- Admin endpoints รับ/คืน raw `dict` — ไม่มี type safety, ไม่มี API docs
- แก้: สร้าง request/response schemas ใน `admin_schemas.py`

**BUG-5: Config ที่ generate มีปัญหา SQL Injection potential**
- `ConfigGenerator._esc()` แค่ escape single quote — ไม่ใช้ parameterized queries
- ความเสี่ยงต่ำ (admin-only, input มาจาก LLM ไม่ใช่ user) แต่ควร note ไว้
- **ไม่ต้องแก้ตอนนี้** — flag เป็น tech debt

### 1.3 Frontend Admin — โครงสร้างปัจจุบัน

**Stack:** React + TypeScript + Ant Design + Vite + react-router-dom  
**Path:** `frontend-admin/src/`

**Menu Groups ปัจจุบัน (6 กลุ่ม, 20 pages):**
1. **Dashboard** — Dashboard
2. **Discovery & Analysis** — Schema Analyzer (AI), Schema Explorer
3. **Data Management** — Data Contexts, View Builder, View Manager, Dimension Families, Master Data
4. **Knowledge Base** — Business Rules, Semantic Mappings, Golden Examples
5. **AI Configuration** — AI Providers, AI Models
6. **Monitoring** — Feedback, Query Logs, Data Warnings, Query Patterns
7. **System** — Settings, User Management

**ข้อสังเกต:** Menu มี 20 items แล้ว sidebar ค่อนข้างยาว แต่ยังจัดกลุ่มดีอยู่

### 1.4 สิ่งที่ยังไม่ได้ทำ (จาก Planning doc)

- [ ] **Admin UI page** สำหรับ onboarding workflow ← เป้าหมายหลักของแผนนี้
- [ ] Batch onboard multiple views
- [ ] Auto-detect new views/tables and suggest onboarding
- [ ] Compare generated config vs existing (diff mode)
- [ ] Use cheap model for inspection summary, expensive for full analysis

---

## Part 2: แผน Backend Fixes

### Phase B1: Fix `generate_config()` signature

**ไฟล์:** `app/services/context_onboarding.py`

**แก้ method `generate_config()`:**
```python
# Before (BUG):
def generate_config(self, analysis: Dict, view_name: Optional[str] = None) -> ConfigBundle:
    vn = view_name or analysis.get("context", {}).get("name", "unknown")
    generator = ConfigGenerator(view_name or self._last_view_name)  # ← crash ถ้าไม่มี _last_view_name

# After (FIX):
def generate_config(self, analysis: Dict, view_name: str) -> ConfigBundle:
    generator = ConfigGenerator(view_name)
```

**แก้ method `run_full_pipeline()`:**
```python
# ลบ self._last_view_name = view_name
# แก้เป็น:
config = self.generate_config(analysis, view_name=view_name)
```

**แก้ admin endpoint `onboard_context()`:**
```python
# ลบ service._last_view_name = view_name
# แก้เป็น:
config = service.generate_config(analysis, view_name=view_name)
```

### Phase B2: Fix DB path

**ไฟล์แก้:** `app/api/v1/admin.py` (3 endpoints)

**ขั้นตอน:**
1. อ่าน `app/config.py` ก่อนเพื่อดูว่า business DB path อยู่ตรงไหน
2. ถ้ามี `settings.BUSINESS_DB_PATH` หรือ `settings.SQLITE_DB_PATH` → ใช้เลย
3. ถ้าไม่มี → เพิ่ม config key ใน `config.py`:
   ```python
   BUSINESS_DB_PATH: str = os.path.join(BASE_DIR, "nt_fi_report.sqlite")
   ```
4. แก้ 3 endpoints ให้ใช้ config แทน hardcode

### Phase B3: Add Pydantic schemas

**ไฟล์:** `app/schemas/admin_schemas.py`

**เพิ่ม schemas:**
```python
class OnboardingRequest(BaseModel):
    view_name: str
    dry_run: bool = True
    provider: Optional[str] = None  # claude, gemini, matcha
    model: Optional[str] = None
    api_url: Optional[str] = None
    inspect_only: bool = False

class InspectionSummary(BaseModel):
    row_count: int
    columns: int
    detected_structure: str  # long_table, semi_crosstab, wide_table
    quality_issues: int
    value_columns: List[str] = []
    category_columns: List[str] = []
    time_columns: List[str] = []
    cross_column_analyses: List[dict] = []

class AnalysisSummary(BaseModel):
    data_structure: dict = {}
    context: dict = {}
    rules_count: int = 0
    examples_count: int = 0
    mappings_count: int = 0

class ConfigSummary(BaseModel):
    summary: str
    sql_count: int
    sql_statements: Optional[List[str]] = None  # only in dry_run

class ValidationSummary(BaseModel):
    passed: bool
    results: List[dict] = []
    issues: List[str] = []

class OnboardingResponse(BaseModel):
    status: str  # inspect_only, preview, applied
    inspection: InspectionSummary
    analysis: Optional[AnalysisSummary] = None
    config: Optional[ConfigSummary] = None
    apply: Optional[dict] = None
    validation: Optional[ValidationSummary] = None
```

**แก้ 3 endpoints ใน `admin.py`:**
- `onboard_context()`: รับ `OnboardingRequest`, คืน `OnboardingResponse`
- `inspect_context()`: รับ `{"view_name": str}`, คืน inspection dict
- `validate_context()`: รับ `{"view_name": str}`, คืน `ValidationSummary`

### Phase B4: เพิ่ม API endpoint สำหรับ list views ที่ onboard ได้

**ไฟล์:** `app/api/v1/admin.py`

**เพิ่ม endpoint:**
```python
@router.get("/contexts/onboard/available-views")
def list_onboardable_views(
    current_user: User = Depends(deps.require_admin),
):
    """List views/tables ที่ยังไม่มี config (หรือมีไม่ครบ) + views ที่มีอยู่แล้ว"""
    # 1. ดึง views/tables ทั้งหมดจาก business DB
    # 2. ดึง contexts ที่มี config แล้ว
    # 3. แยกเป็น: unconfigured (แนะนำ onboard) vs configured (แนะนำ re-onboard/validate)
```

**เพิ่ม method ใน `context_onboarding.py`:**
```python
def list_available_views(self) -> Dict:
    """List all views/tables with their onboarding status."""
    conn = sqlite3.connect(self.db_path)
    # Get all views/tables
    # Get configured contexts
    # Return { unconfigured: [...], configured: [...] }
```

---

## Part 3: แผน Frontend — Context Onboarding Page

### 3.1 ตำแหน่งใน Menu

เพิ่มใน group **"Data Management"** หลัง "Data Contexts":

```
Data Management
  ├── Data Contexts          (จัดการ contexts ที่มีอยู่)
  ├── Context Onboarding ← NEW (wizard สร้าง context ใหม่)
  ├── View Builder
  ├── View Manager
  ├── Dimension Families
  └── Master Data
```

**เหตุผล:** Context Onboarding สร้าง Data Context ใหม่ ดังนั้นอยู่ถัดจาก Data Contexts เป็นลำดับธรรมชาติ

### 3.2 ไฟล์ที่ต้องสร้าง/แก้

| ไฟล์ | Action | หน้าที่ |
|------|--------|---------|
| `src/pages/ContextOnboarding.tsx` | **NEW** | หน้า wizard 4 steps |
| `src/services/onboardingService.ts` | **NEW** | API calls สำหรับ onboarding |
| `src/App.tsx` | **EDIT** | เพิ่ม route `/context-onboarding` |
| `src/components/Layout/AdminLayout.tsx` | **EDIT** | เพิ่ม menu item |

### 3.3 UX Design — Wizard 4 Steps

ใช้ Ant Design `Steps` component:

```
Step 1: Select View → Step 2: Inspect → Step 3: AI Analysis → Step 4: Review & Apply
```

#### Step 1: Select View

- Dropdown/Select ดึงจาก `GET /contexts/onboard/available-views`
- แยกแสดง:
  - "ยังไม่มี Config" (unconfigured) — badge สีเขียว "แนะนำ"
  - "มี Config แล้ว" (configured) — badge สีเหลือง "Re-onboard"
- หรือพิมพ์ชื่อ view เองได้
- ปุ่ม "Inspect" →

#### Step 2: Inspection Results

- แสดงผล Phase 1 (ไม่ใช้ AI, เร็วมาก):
  - ข้อมูลพื้นฐาน: row count, column count, date range
  - Detected Structure: badge สี (long_table=green, semi_crosstab=orange, wide_table=blue)
  - Column list: table แสดง name, type, distinct count, flags (NUMERIC, TIME, PREFIX, CASE_ISSUE)
  - Cross-Column Analysis: ถ้ามี semi_crosstab → แสดง warning box สีแดง
  - Quality Issues: list ปัญหาที่พบ
- Select AI Provider: dropdown (gemini, claude, matcha) — default จาก config
- ปุ่ม "Analyze with AI" →

#### Step 3: AI Analysis & Preview

- Loading state: "Analyzing with [Provider]..." (อาจใช้เวลา 10-30 วินาที)
- แสดงผล Phase 2+3:
  - **Context Info:** ชื่อ, keywords, detection instructions (collapsible)
  - **Business Rules:** table แสดง rule_code, severity (badge สี), description — editable
  - **Golden Examples:** table แสดง question, SQL preview — editable
  - **Semantic Mappings:** table แสดง keyword → condition — editable
  - **Hierarchy:** tree view
  - **Data Warnings:** list
- **SQL Preview:** collapsible panel แสดง SQL statements ทั้งหมด (dry-run output)
- Toggle: "Dry Run" (default) vs "Apply"
- ปุ่ม "Apply Config" →

#### Step 4: Results

- ถ้า dry-run: แสดง "Preview complete" + จำนวน SQL + ปุ่ม "Apply for real"
- ถ้า apply:
  - แสดง success/error count
  - Validation results (Phase 5)
  - ปุ่ม "Go to Data Contexts" (navigate ไปดู context ที่สร้าง)
  - ปุ่ม "Sync Vanna Brain" (optional — sync golden examples ไป vector DB)
  - ปุ่ม "Onboard Another View"

### 3.4 Service File

**`src/services/onboardingService.ts`:**

```typescript
import api from './api';

export const onboardingService = {
  // List available views with onboarding status
  getAvailableViews: () =>
    api.get('/admin/contexts/onboard/available-views'),

  // Phase 1: Inspect only (fast, no AI)
  inspect: (viewName: string) =>
    api.post('/admin/contexts/onboard/inspect', { view_name: viewName }),

  // Full pipeline (inspect + analyze + generate + optional apply)
  onboard: (params: {
    view_name: string;
    dry_run?: boolean;
    provider?: string;
    model?: string;
    inspect_only?: boolean;
  }) =>
    api.post('/admin/contexts/onboard', params),

  // Validate existing config
  validate: (viewName: string) =>
    api.post('/admin/contexts/onboard/validate', { view_name: viewName }),
};
```

### 3.5 Component Architecture

```
ContextOnboarding.tsx
├── State: { currentStep, viewName, inspectionData, analysisData, configData, applyResult }
├── Step 1: ViewSelector
│   ├── Select (available views)
│   └── Button "Inspect"
├── Step 2: InspectionView
│   ├── BasicInfo (row count, structure badge)
│   ├── ColumnTable
│   ├── CrossColumnWarnings
│   ├── QualityIssues
│   ├── ProviderSelector
│   └── Button "Analyze with AI"
├── Step 3: AnalysisPreview
│   ├── ContextCard
│   ├── RulesTable (editable)
│   ├── ExamplesTable (editable)
│   ├── MappingsTable (editable)
│   ├── SQLPreview (collapsible)
│   └── Button "Apply" / "Dry Run"
└── Step 4: ResultsView
    ├── ApplyStats
    ├── ValidationResults
    └── ActionButtons
```

ทั้งหมดอยู่ใน **ไฟล์เดียว** `ContextOnboarding.tsx` (ประมาณ 600-800 lines) เพราะ state sharing ระหว่าง steps ง่ายกว่าแยกไฟล์ ตาม pattern เดียวกับ pages อื่นในโปรเจกต์ เช่น `HierarchyManager.tsx`, `ViewBuilder.tsx`

---

## Part 4: Execution Order

```
Phase 1 — Backend Fixes (ไม่กระทบ frontend)
  Step 1.1  อ่าน app/config.py เพื่อหา business DB path config
  Step 1.2  แก้ context_onboarding.py: fix generate_config() signature
  Step 1.3  แก้ admin.py: fix DB path ใน 3 onboarding endpoints
  Step 1.4  เพิ่ม Pydantic schemas ใน admin_schemas.py
  Step 1.5  แก้ 3 endpoints ให้ใช้ schemas
  Step 1.6  เพิ่ม GET /contexts/onboard/available-views endpoint
  Step 1.7  เพิ่ม list_available_views() ใน context_onboarding.py
  
Phase 2 — Frontend: Service + Types
  Step 2.1  สร้าง src/services/onboardingService.ts
  Step 2.2  เพิ่ม types ใน src/types/index.ts (ถ้าจำเป็น)

Phase 3 — Frontend: Page + Route + Menu
  Step 3.1  สร้าง src/pages/ContextOnboarding.tsx (wizard 4 steps)
  Step 3.2  แก้ src/App.tsx: เพิ่ม route + import
  Step 3.3  แก้ AdminLayout.tsx: เพิ่ม menu item ใน Data Management group

Phase 4 — Testing
  Step 4.1  ทดสอบ backend: inspect endpoint กับ view จริง
  Step 4.2  ทดสอบ frontend: wizard flow ครบ 4 steps
  Step 4.3  ทดสอบ end-to-end: onboard view ใหม่แล้วทดสอบถามคำถาม
```

---

## Part 5: กฎสำหรับ Claude Code

### 5.1 Codebase Conventions

- **Backend:** FastAPI + SQLAlchemy (app DB) + raw sqlite3 (business DB) — อย่าแก้ pattern นี้
- **Frontend Admin:** React + TypeScript + Ant Design — ใช้ `antd` components เท่านั้น
- **API Service pattern:** ดูตัวอย่างจาก `src/services/contextService.ts` หรือ `viewBuilder.ts`
- **Page pattern:** ดูตัวอย่างจาก `src/pages/ViewBuilder.tsx` หรือ `HierarchyManager.tsx`
- **Menu structure:** ดูจาก `AdminLayout.tsx` — เพิ่ม item ใน group `Data Management` children array

### 5.2 สิ่งที่ห้ามทำ

- อย่าแก้ `context_onboarding.py` core logic (Phase 1-5 pipeline) — แก้แค่ signature/path bugs
- อย่าเปลี่ยน raw sqlite3 เป็น SQLAlchemy ใน onboarding service — business DB แยกจาก app DB ตั้งใจ
- อย่าเพิ่ม dependency ใหม่ทั้ง backend และ frontend (ใช้ของที่มีอยู่แล้ว)
- อย่าแก้ menu group structure ที่มีอยู่ — แค่เพิ่ม item

### 5.3 ไฟล์ที่ต้องอ่านก่อน implement

| ไฟล์ | ต้องอ่านเพื่อ |
|------|-------------|
| `app/config.py` | หา business DB path config |
| `app/services/context_onboarding.py` | เข้าใจ class structure ก่อนแก้ |
| `app/api/v1/admin.py` (ท้ายไฟล์) | ดู 3 onboarding endpoints ปัจจุบัน |
| `app/schemas/admin_schemas.py` | ดู pattern ของ schemas ที่มี |
| `frontend-admin/src/pages/ViewBuilder.tsx` | ดู pattern wizard page |
| `frontend-admin/src/services/viewBuilder.ts` | ดู pattern API service |
| `frontend-admin/src/pages/HierarchyManager.tsx` | ดู pattern complex page |
| `frontend-admin/src/components/Layout/AdminLayout.tsx` | ดู menu structure |

### 5.4 ข้อสำคัญเรื่อง Inspection Response

`DataInspector.inspect()` คืน `InspectionResult` dataclass — เรียก `.to_dict()` เพื่อได้ JSON serializable dict

Frontend ต้องรองรับ `inspection.to_dict()` structure:
```json
{
  "view_name": "v_xxx",
  "row_count": 12345,
  "detected_structure": "semi_crosstab",
  "columns": [
    {
      "name": "col1",
      "type": "TEXT",
      "distinct_count": 10,
      "null_count": 0,
      "is_numeric": false,
      "is_time_column": false,
      "has_numeric_prefix": true,
      "sample_values": ["01.xxx", "02.yyy"],
      "all_distinct": ["01.xxx", "02.yyy", "03.zzz"]
    }
  ],
  "cross_column_analyses": [
    {
      "value_column": "amount_value",
      "category_column": "main_group",
      "has_mixed_signs": true,
      "likely_semi_crosstab": true,
      "categories": { "01.รายได้": {"sum": 141840452690}, ... }
    }
  ],
  "quality_issues": [
    {"column": "sub_group", "type": "prefix_inconsistency", "description": "...", "examples": [...]}
  ]
}
```

### 5.5 ข้อสำคัญเรื่อง LLM Analysis Response

`onboard` endpoint คืน analysis ที่มี structure หลายชั้น — frontend ต้อง handle:
- `analysis.data_structure.type` — "long_table" / "semi_crosstab" / "wide_table"
- `analysis.context` — context definition dict
- `config.sql_statements` — array of SQL strings (เฉพาะ dry_run)
- `config.summary` — human-readable markdown text

Analysis อาจใช้เวลา 10-30 วินาที — frontend ต้องมี loading state ที่ชัดเจน

---

## Part 6: Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM analysis ช้า (30+ วินาที) | UX ไม่ดี | แสดง loading + progress message, ใช้ AbortController สำหรับ cancel |
| LLM return JSON ไม่ valid | Backend error 500 | `_parse_response()` มี fallback อยู่แล้ว — frontend แสดง error message ชัดเจน |
| View ไม่มีใน business DB | Inspect fail | Validate view_name ก่อน inspect (list available views) |
| SQL injection จาก LLM output | Config ผิด | Existing `_esc()` ป้องกัน basic case, admin review ก่อน apply |
| Config apply ทับของเดิม | Data loss | ใช้ `INSERT OR REPLACE` + dry_run default + แสดง warning ถ้า view มี config อยู่แล้ว |

---

## Appendix A: Menu Item เพิ่มใน AdminLayout.tsx

```typescript
// ใน menuItems array, ใน group "Data Management", children array:
{
    key: '/context-onboarding',
    icon: <RocketOutlined />,  // import { RocketOutlined } from '@ant-design/icons'
    label: 'Context Onboarding',
},
```

วางหลัง `Data Contexts` (`/contexts`) และก่อน `View Builder` (`/view-builder`)

## Appendix B: Route เพิ่มใน App.tsx

```typescript
import ContextOnboarding from './pages/ContextOnboarding'

// ใน Routes:
<Route path="/context-onboarding" element={<ContextOnboarding />} />
```
