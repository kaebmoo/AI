# แผนการพัฒนา Admin Web UI และ Schema Analyzer

## ภาพรวมโครงการ

พัฒนาระบบ Admin Web UI สำหรับบริหารจัดการ Context ของ AI และระบบวิเคราะห์โครงสร้างข้อมูลอัตโนมัติ

### วัตถุประสงค์

1. **Admin Web UI** - ให้ Admin สามารถจัดการ Business Rules, Semantic Mappings, Golden Examples ผ่าน Web ได้ง่าย
2. **Schema Analyzer** - ระบบวิเคราะห์โครงสร้างข้อมูลใหม่ด้วย AI และนำเข้าระบบโดยอัตโนมัติ
3. **Data Quality Assistant** - ช่วย Admin ตรวจสอบและปรับปรุงคุณภาพข้อมูล

---

## สถานะปัจจุบัน

### Backend API (พร้อมใช้งาน ✅)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/admin/schema/columns` | CRUD | จัดการ Column Metadata |
| `/api/v1/admin/mappings` | CRUD | จัดการ Semantic Mappings |
| `/api/v1/admin/rules` | CRUD | จัดการ Business Rules |
| `/api/v1/admin/golden-examples` | CRUD | จัดการ Few-shot Examples |
| `/api/v1/admin/refresh-cache` | POST | Refresh Schema Cache |

### Database Tables (พร้อมใช้งาน ✅)

| Table | Records | Description |
|-------|---------|-------------|
| `schema_metadata` | 22 | Column definitions |
| `schema_semantic_mapping` | 53 | Keyword → SQL mappings |
| `schema_business_rules` | 17 | SQL generation rules |
| `golden_examples` | 2 | Few-shot examples |

### Frontend (ต้องพัฒนาใหม่ 🔨)

ปัจจุบันเป็น React Native (Expo) สำหรับ Chat UI เท่านั้น ยังไม่มี Admin UI

---

## Phase 1: Admin Web UI (Frontend)

### 1.1 เลือก Technology Stack

**ทางเลือก A: React Web App แยก (แนะนำ)**
```
frontend-admin/
├── src/
│   ├── components/
│   ├── pages/
│   ├── services/
│   └── App.tsx
├── package.json
└── vite.config.ts
```

**ข้อดี:**
- แยก codebase ชัดเจน
- ใช้ UI Library ที่เหมาะกับ Admin (Ant Design, MUI)
- Build และ Deploy แยกได้

**ทางเลือก B: เพิ่มใน Expo Web**
- ใช้ codebase เดียวกับ Chat UI
- ต้องปรับ navigation และ routing

**แนะนำ: ทางเลือก A** - React + Vite + Ant Design

### 1.2 โครงสร้างหน้า Admin UI

```
/admin
├── /login                    # Admin Login
├── /dashboard                # Overview Dashboard
├── /mappings                 # Semantic Mappings Management
│   ├── /list                 # List all mappings
│   ├── /create               # Create new mapping
│   └── /edit/:id             # Edit mapping
├── /rules                    # Business Rules Management
│   ├── /list                 # List all rules
│   ├── /create               # Create new rule
│   └── /edit/:id             # Edit rule
├── /examples                 # Golden Examples Management
│   ├── /list                 # List examples
│   ├── /create               # Create example
│   └── /edit/:id             # Edit example
├── /schema                   # Schema Metadata
│   ├── /columns              # Column definitions
│   └── /analyze              # Schema Analyzer (Phase 2)
└── /settings                 # System Settings
```

### 1.3 UI Components

#### Dashboard
```
┌─────────────────────────────────────────────────────────┐
│  AI Assistant Asisstant Admin                              [Admin ▼]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │   53    │  │   17    │  │    2    │  │   22    │   │
│  │Mappings │  │ Rules   │  │Examples │  │ Columns │   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │
│                                                         │
│  ┌─ Recent Activity ────────────────────────────────┐  │
│  │ • Added rule: EXCLUDE_OTHER_REVENUE              │  │
│  │ • Updated mapping: สัดส่วนรายได้                 │  │
│  │ • Created example: Top 5 departments             │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─ Quick Actions ──────────────────────────────────┐  │
│  │ [+ Add Mapping] [+ Add Rule] [🔄 Refresh Cache]  │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

#### Semantic Mappings List
```
┌─────────────────────────────────────────────────────────┐
│  Semantic Mappings                        [+ Add New]   │
├─────────────────────────────────────────────────────────┤
│  Filter: [All Types ▼] [Active ▼]    Search: [______]  │
├─────────────────────────────────────────────────────────┤
│  ┌─ Type: abbreviation ─────────────────────────────┐  │
│  │ Keyword     │ Column              │ Condition    │  │
│  ├─────────────┼─────────────────────┼──────────────┤  │
│  │ นป.        │ organization_group  │ = 'นป.'     │  │
│  │ บชง.       │ department_abbr     │ = 'บชง.'    │  │
│  │ สญ.        │ division_abbr       │ = 'สญ.'     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─ Type: term ─────────────────────────────────────┐  │
│  │ Keyword         │ Column        │ Condition      │  │
│  ├─────────────────┼───────────────┼────────────────┤  │
│  │ สัดส่วนรายได้  │ BUSINESS_GROUP│ != 'รายได้อื่น'│  │
│  │ มือถือ         │ BUSINESS_GROUP│ = 'Mobile'    │  │
│  │ อสังหาริมทรัพย์│ SERVICE_GROUP │ = 'กลุ่ม...'  │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

#### Business Rules Editor
```
┌─────────────────────────────────────────────────────────┐
│  Edit Business Rule                          [Save]     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Rule Code: [EXCLUDE_OTHER_REVENUE_____________]        │
│                                                         │
│  Rule Name: [ไม่นับรายได้อื่นในการคำนวณ___________]    │
│                                                         │
│  Description:                                           │
│  ┌──────────────────────────────────────────────────┐  │
│  │ เมื่อคำนวณรายได้รวม หรือสัดส่วนรายได้           │  │
│  │ ต้องไม่นับ "รายได้อื่น" (BUSINESS_GROUP =       │  │
│  │ 'รายได้อื่น')...                                 │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  Severity: [⚠️ Warning ▼]                               │
│                                                         │
│  Applies To: [สัดส่วน, เปรียบเทียบ, รายได้รวม]         │
│                                                         │
│  ┌─ Example SQL ────────────────────────────────────┐  │
│  │ ✅ Correct:                                       │  │
│  │ SELECT SUM(revenue) FROM revenue_search          │  │
│  │ WHERE BUSINESS_GROUP != 'รายได้อื่น'             │  │
│  │                                                   │  │
│  │ ❌ Wrong:                                         │  │
│  │ SELECT SUM(revenue) FROM revenue_search          │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  [Toggle Active] [Delete]                    [Save]    │
└─────────────────────────────────────────────────────────┘
```

### 1.4 งานที่ต้องทำ Phase 1

| Task | Priority | Effort |
|------|----------|--------|
| สร้าง React project ใหม่ (Vite + TypeScript) | High | 2h |
| Setup Ant Design และ Layout | High | 2h |
| สร้าง API Service Layer | High | 3h |
| หน้า Login/Authentication | High | 3h |
| หน้า Dashboard | Medium | 2h |
| หน้า Semantic Mappings (CRUD) | High | 4h |
| หน้า Business Rules (CRUD) | High | 4h |
| หน้า Golden Examples (CRUD) | Medium | 3h |
| หน้า Schema Columns (View/Edit) | Medium | 3h |
| Testing และ Bug fixes | High | 4h |

**รวม: ~30 ชั่วโมง**

---

## Phase 2: Schema Analyzer (AI-Assisted)

### 2.1 Workflow Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Schema Analysis Workflow                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Upload/Connect                                           │
│     ┌──────────┐                                             │
│     │ CSV/SQL  │ ──→ Parse Structure ──→ Detect Columns     │
│     │ Database │                                             │
│     └──────────┘                                             │
│          ↓                                                   │
│  2. AI Analysis                                              │
│     ┌──────────────────────────────────────────────────┐    │
│     │ AI analyzes:                                      │    │
│     │ • Column types (date, currency, category, etc.)  │    │
│     │ • Thai/English names mapping                      │    │
│     │ • Suggested business rules                        │    │
│     │ • Potential semantic mappings                     │    │
│     └──────────────────────────────────────────────────┘    │
│          ↓                                                   │
│  3. Admin Review                                             │
│     ┌──────────────────────────────────────────────────┐    │
│     │ Admin reviews AI suggestions:                     │    │
│     │ ☑ Column "REVENUE_VALUE" → รายได้ (SUM=Yes)      │    │
│     │ ☑ Column "dept_code" → รหัสฝ่าย (Abbr mapping)   │    │
│     │ ☐ Column "xyz" → ??? (Need manual input)         │    │
│     └──────────────────────────────────────────────────┘    │
│          ↓                                                   │
│  4. Import to System                                         │
│     ┌──────────────────────────────────────────────────┐    │
│     │ Generate:                                         │    │
│     │ • schema_metadata records                         │    │
│     │ • semantic_mapping records                        │    │
│     │ • business_rules records                          │    │
│     │ • UPDATE system prompt                            │    │
│     └──────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Backend API ใหม่

**File:** `app/api/v1/schema_analyzer.py`

```python
# Endpoints ที่ต้องเพิ่ม

@router.post("/analyze/upload")
def upload_and_analyze(file: UploadFile):
    """
    Upload CSV/SQL file และวิเคราะห์โครงสร้าง
    Returns: parsed columns, sample data
    """
    pass

@router.post("/analyze/database")
def analyze_database_table(table_name: str, connection_string: str):
    """
    เชื่อมต่อ database และวิเคราะห์ table
    Returns: column definitions, foreign keys, sample data
    """
    pass

@router.post("/analyze/ai-suggest")
def get_ai_suggestions(columns: List[ColumnInfo], sample_data: List[Dict]):
    """
    ส่งข้อมูล columns ให้ AI วิเคราะห์และแนะนำ
    Returns: suggested metadata, mappings, rules
    """
    pass

@router.post("/analyze/import")
def import_suggestions(suggestions: AnalysisSuggestions):
    """
    นำเข้า suggestions ที่ admin approve แล้ว
    Creates: metadata, mappings, rules records
    """
    pass
```

### 2.3 AI Analysis Prompt

```python
SCHEMA_ANALYSIS_PROMPT = """คุณเป็น Data Analyst ผู้เชี่ยวชาญในการวิเคราะห์โครงสร้างข้อมูล

## ข้อมูลที่ได้รับ
- รายชื่อ columns และ data types
- ตัวอย่างข้อมูล 10-20 rows

## สิ่งที่ต้องวิเคราะห์

### 1. Column Metadata
สำหรับแต่ละ column ให้ระบุ:
- display_name_th: ชื่อภาษาไทยที่เหมาะสม
- display_name_en: ชื่อภาษาอังกฤษ
- description: คำอธิบายความหมาย
- is_summable: true/false (เป็นตัวเลขที่ SUM ได้หรือไม่)
- is_groupable: true/false (เหมาะสำหรับ GROUP BY หรือไม่)
- special_notes: หมายเหตุพิเศษ (เช่น "หน่วยเป็นบาท", "ต้องแปลง Unix timestamp")

### 2. Semantic Mappings
หาคำย่อหรือ business terms ที่ควรมี mapping:
- keyword: คำที่ผู้ใช้อาจค้นหา
- keyword_type: abbreviation / term / synonym
- target_column: column ที่ควรใช้
- target_condition: เงื่อนไข SQL
- description: คำอธิบาย

### 3. Business Rules
กฎที่ควรใช้ในการสร้าง SQL:
- rule_code: รหัสกฎ (เช่น EXCLUDE_NULL, USE_CORRECT_TABLE)
- rule_name: ชื่อกฎ
- rule_description: รายละเอียด
- example_correct: ตัวอย่าง SQL ที่ถูก
- example_wrong: ตัวอย่าง SQL ที่ผิด

## Output Format
ตอบเป็น JSON ตามโครงสร้างนี้:
```json
{
  "metadata": [...],
  "mappings": [...],
  "rules": [...]
}
```
"""
```

### 2.4 UI: Schema Analyzer

```
┌─────────────────────────────────────────────────────────┐
│  Schema Analyzer                              [Step 1/3]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─ Upload Data ────────────────────────────────────┐  │
│  │                                                   │  │
│  │  [📁 Drop CSV/SQL file here or click to upload]  │  │
│  │                                                   │  │
│  │  ─── or ───                                      │  │
│  │                                                   │  │
│  │  Database: [PostgreSQL ▼]                        │  │
│  │  Host: [_____________]  Port: [5432]             │  │
│  │  Database: [_____________]                        │  │
│  │  Table: [_____________]                           │  │
│  │                              [Connect & Analyze]  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  AI Analysis Results                          [Step 2/3]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🤖 AI analyzed 15 columns, found:                     │
│  • 15 column metadata suggestions                       │
│  • 8 semantic mappings                                  │
│  • 3 business rules                                     │
│                                                         │
│  ┌─ Column Metadata ────────────────────────────────┐  │
│  │ Column         │ Thai Name    │ SUM? │ GROUP? │✓ │  │
│  ├────────────────┼──────────────┼──────┼────────┼──┤  │
│  │ REVENUE_VALUE  │ รายได้      │ ✅   │ ❌     │☑│  │
│  │ DEPARTMENT     │ ฝ่าย        │ ❌   │ ✅     │☑│  │
│  │ YEAR           │ ปี          │ ❌   │ ✅     │☑│  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─ Suggested Mappings ─────────────────────────────┐  │
│  │ Keyword    │ Type    │ Maps To           │ ✓     │  │
│  ├────────────┼─────────┼───────────────────┼───────┤  │
│  │ รายได้รวม │ term    │ SUM(REVENUE_VALUE)│ ☑     │  │
│  │ ฝ่าย      │ term    │ DEPARTMENT        │ ☑     │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  [◀ Back]                              [Import Selected]│
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Import Complete                              [Step 3/3]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ✅ Successfully imported:                              │
│  • 15 column metadata records                           │
│  • 6 semantic mappings                                  │
│  • 2 business rules                                     │
│                                                         │
│  Schema cache has been refreshed.                       │
│                                                         │
│  [View Imported Data]              [Analyze Another]    │
└─────────────────────────────────────────────────────────┘
```

### 2.5 งานที่ต้องทำ Phase 2

| Task | Priority | Effort |
|------|----------|--------|
| สร้าง Schema Analyzer API endpoints | High | 4h |
| CSV Parser และ Database Connector | High | 4h |
| AI Analysis Integration | High | 6h |
| สร้าง Analysis Prompt Template | High | 3h |
| UI: Upload/Connect step | Medium | 3h |
| UI: Review Suggestions step | High | 5h |
| UI: Import/Confirm step | Medium | 2h |
| Bulk import logic | Medium | 3h |
| Testing | High | 4h |

**รวม: ~34 ชั่วโมง**

---

## Phase 3: Data Quality Assistant

### 3.1 Features

1. **Duplicate Detection** - หา mappings/rules ที่ซ้ำกัน
2. **Conflict Detection** - หา rules ที่ขัดแย้งกัน
3. **Coverage Analysis** - วิเคราะห์ว่า columns ไหนยังไม่มี metadata
4. **Usage Statistics** - แสดงว่า mappings/rules ไหนถูกใช้บ่อย
5. **AI Suggestions** - แนะนำ mappings/rules ใหม่จาก query patterns

### 3.2 UI: Data Quality Dashboard

```
┌─────────────────────────────────────────────────────────┐
│  Data Quality Dashboard                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─ Health Score ───────────────────────────────────┐  │
│  │                                                   │  │
│  │    ████████████████░░░░  85%                     │  │
│  │                                                   │  │
│  │  ✅ 22/22 columns have metadata                  │  │
│  │  ⚠️ 3 mappings may be duplicates                 │  │
│  │  ❌ 2 rules have conflicts                        │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─ Issues to Review ───────────────────────────────┐  │
│  │                                                   │  │
│  │ ⚠️ Potential Duplicates:                         │  │
│  │   • "มือถือ" and "mobile" → same target         │  │
│  │   • "จังหวัด" appears in 3 different mappings   │  │
│  │                                                   │  │
│  │ ❌ Conflicts:                                     │  │
│  │   • RULE_A says use column X                     │  │
│  │   • RULE_B says don't use column X               │  │
│  │                                              [Fix]│  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─ AI Suggestions ─────────────────────────────────┐  │
│  │                                                   │  │
│  │ Based on recent queries, consider adding:        │  │
│  │   • Mapping: "ผลิตภัณฑ์" → PRODUCT_NAME         │  │
│  │   • Rule: Always use LEFT JOIN for...           │  │
│  │                                         [Review] │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.3 งานที่ต้องทำ Phase 3

| Task | Priority | Effort |
|------|----------|--------|
| Duplicate detection API | Medium | 3h |
| Conflict detection API | Medium | 4h |
| Coverage analysis API | Low | 2h |
| Usage statistics tracking | Low | 4h |
| AI suggestion from query logs | Medium | 6h |
| Data Quality Dashboard UI | Medium | 5h |

**รวม: ~24 ชั่วโมง**

---

## Timeline โดยรวม

```
Week 1-2: Phase 1 - Admin Web UI
├── Day 1-2: Project setup, Auth
├── Day 3-4: Mappings CRUD
├── Day 5-6: Rules CRUD
├── Day 7-8: Examples, Schema view
└── Day 9-10: Testing, Bug fixes

Week 3-4: Phase 2 - Schema Analyzer
├── Day 1-2: Backend APIs
├── Day 3-4: AI Integration
├── Day 5-6: Upload & Review UI
├── Day 7-8: Import logic
└── Day 9-10: Testing

Week 5: Phase 3 - Data Quality
├── Day 1-2: Detection APIs
├── Day 3-4: Dashboard UI
└── Day 5: Testing & Polish
```

---

## Technical Stack

### Frontend Admin
```json
{
  "framework": "React 18 + TypeScript",
  "build": "Vite",
  "ui": "Ant Design 5",
  "state": "React Query (TanStack)",
  "routing": "React Router v6",
  "forms": "Ant Design Form + Yup",
  "charts": "Ant Design Charts"
}
```

### Backend (Existing)
```json
{
  "framework": "FastAPI",
  "database": "SQLite / PostgreSQL",
  "orm": "SQLAlchemy",
  "auth": "JWT"
}
```

### New Backend Dependencies
```python
# requirements.txt เพิ่มเติม
pandas>=2.0.0        # CSV parsing
sqlalchemy>=2.0.0    # Database introspection
python-multipart     # File upload
openpyxl             # Excel support (optional)
```

---

## File Structure (Proposed)

```
frontend-admin/
├── src/
│   ├── components/
│   │   ├── Layout/
│   │   │   ├── AdminLayout.tsx
│   │   │   └── Sidebar.tsx
│   │   ├── Mappings/
│   │   │   ├── MappingList.tsx
│   │   │   ├── MappingForm.tsx
│   │   │   └── MappingTable.tsx
│   │   ├── Rules/
│   │   │   ├── RuleList.tsx
│   │   │   ├── RuleForm.tsx
│   │   │   └── RuleCard.tsx
│   │   ├── Examples/
│   │   │   └── ...
│   │   ├── Analyzer/
│   │   │   ├── UploadStep.tsx
│   │   │   ├── ReviewStep.tsx
│   │   │   └── ImportStep.tsx
│   │   └── DataQuality/
│   │       └── Dashboard.tsx
│   │
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Mappings.tsx
│   │   ├── Rules.tsx
│   │   ├── Examples.tsx
│   │   ├── Schema.tsx
│   │   └── Analyzer.tsx
│   │
│   ├── services/
│   │   ├── api.ts
│   │   ├── auth.ts
│   │   ├── mappings.ts
│   │   ├── rules.ts
│   │   └── analyzer.ts
│   │
│   ├── types/
│   │   └── index.ts
│   │
│   ├── App.tsx
│   └── main.tsx
│
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## API Endpoints Summary (New)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyzer/upload` | Upload file for analysis |
| POST | `/api/v1/analyzer/database` | Analyze database table |
| POST | `/api/v1/analyzer/ai-suggest` | Get AI suggestions |
| POST | `/api/v1/analyzer/import` | Import approved suggestions |
| GET | `/api/v1/quality/health` | Get data quality score |
| GET | `/api/v1/quality/duplicates` | Find duplicate mappings |
| GET | `/api/v1/quality/conflicts` | Find conflicting rules |
| GET | `/api/v1/quality/suggestions` | AI suggestions from logs |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Time to add new mapping | < 1 minute |
| Time to analyze new schema | < 5 minutes |
| Admin tasks via UI vs CLI | > 90% via UI |
| AI suggestion accuracy | > 80% accepted |
| Data quality score | > 90% |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI suggestions not accurate | Medium | Always require admin review |
| Large file upload fails | Medium | Chunk upload, size limits |
| Schema changes break existing rules | High | Validation before save |
| Duplicate mappings cause confusion | Medium | Auto-detection & warnings |

---

## Next Steps

1. **Immediate**: Create `frontend-admin/` project structure
2. **This week**: Implement Phase 1 core features
3. **Review**: Demo to stakeholders after Phase 1
4. **Iterate**: Adjust Phase 2-3 based on feedback

---

*Document created: 2025-01-29*
*Version: 1.0*
