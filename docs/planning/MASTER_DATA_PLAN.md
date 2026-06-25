# Master Data & Hierarchy — Implementation Plan

**Created:** 2026-03-07
**Owner:** Finance (บชง.)
**Prerequisite:** Phase 1 (Foundation) — DONE

---

## Architecture Overview

```
                    ┌──────────────────────┐
                    │   Master Data Files   │
                    │ (OneDrive CSV/Excel)  │
                    └──────────┬───────────┘
                               │ import_master_data.py
                               ▼
┌──────────────┐     ┌──────────────────────┐     ┌──────────────┐
│  Actual Data │────▶│   master_hierarchy    │◀────│   Admin UI   │
│ (auto-extract)│     │ master_hierarchy_vals │     │  (CRUD API)  │
└──────────────┘     └──────────┬───────────┘     └──────────────┘
                               │ get_column_hierarchies()
                               ▼
                    ┌──────────────────────┐
                    │     AI Service       │
                    │ (detect level, value │
                    │  lookup, drill-down) │
                    └──────────────────────┘
```

---

## Phase 2: Admin API & Value Lookup Integration

**Goal:** ให้ AI ค้นหา hierarchy values ได้ + Admin เรียก API จัดการ master data

### 2.1 Admin API Endpoints

**File:** `app/api/v1/admin.py` (เพิ่มใน existing file)

```
# Public (no auth) — used by AI pipeline
GET /api/v1/admin/hierarchy/{context}
    → returns hierarchy levels for context
GET /api/v1/admin/hierarchy/{context}/search?q=fixed+line
    → search hierarchy_values by alias match, return with parent chain

# Admin only
GET  /api/v1/admin/hierarchy
    → list all contexts + summary counts
POST /api/v1/admin/hierarchy/{context}/levels
    → create/update hierarchy level (level_columns, detection_keywords)
PUT  /api/v1/admin/hierarchy/{context}/levels/{level}
    → edit level definition
DELETE /api/v1/admin/hierarchy/{context}/levels/{level}
    → soft-delete (is_active=0)

GET  /api/v1/admin/hierarchy/{context}/values?level=1&parent=Fixed+Line+%26+Broadband
    → list values with pagination, filter by level/parent
POST /api/v1/admin/hierarchy/{context}/values
    → create value (source='manual')
PUT  /api/v1/admin/hierarchy/{context}/values/{id}
    → edit value/aliases/parent
DELETE /api/v1/admin/hierarchy/{context}/values/{id}
    → soft-delete

POST /api/v1/admin/hierarchy/extract
    → trigger auto-extract from data (runs extract_hierarchy.py logic)
POST /api/v1/admin/hierarchy/import
    → upload CSV file, import as manual entries
```

**Pydantic Schemas:**
```python
# app/schemas/hierarchy_schemas.py

class HierarchyLevel(BaseModel):
    context_name: str
    level: int
    level_label_th: str
    level_label_en: str
    level_columns: List[str]
    detection_keywords: List[str]
    source: str  # 'auto' or 'manual'

class HierarchyValue(BaseModel):
    id: int
    context_name: str
    level: int
    value: str
    parent_value: Optional[str]
    aliases: List[str]
    source: str
    children_count: int = 0  # populated by query

class HierarchySearchResult(BaseModel):
    value: str
    level: int
    level_label_th: str
    parent_chain: List[str]  # ["Fixed Line & Broadband", "บริการโทรศัพท์ประจำที่ (Fixed Line)"]
    matched_alias: str
```

### 2.2 Value Lookup via Hierarchy

**File:** `app/services/ai_service.py` — enhance `_lookup_values_from_question()`

Currently `keyword_value_index` does flat text search. Enhance:

```python
def _lookup_values_from_question(self, question, context_name, table_name):
    # Step 1: existing keyword_value_index search (fast)
    matches = self._keyword_index_search(question, context_name, table_name)

    # Step 2: NEW — search master_hierarchy_values aliases
    hierarchy_matches = self._hierarchy_alias_search(question, context_name)

    # Step 3: merge, prefer hierarchy matches (they have parent info)
    return self._merge_matches(matches, hierarchy_matches)

def _hierarchy_alias_search(self, question, context_name):
    """Search hierarchy values by alias matching."""
    # SELECT * FROM master_hierarchy_values
    # WHERE context_name = ? AND aliases LIKE '%keyword%'
    # Returns: value, level, parent_value, level_columns
    ...
```

**Benefit:** "fixed line" จะ match alias ของ `บริการโทรศัพท์ประจำที่ (Fixed Line)` (level 1) โดยตรง — AI ไม่ต้องเดาว่าเป็น column ไหน

### 2.3 Implementation Steps

1. Create `app/schemas/hierarchy_schemas.py` — Pydantic models
2. Add API routes in `app/api/v1/admin.py` — CRUD endpoints
3. Add `_hierarchy_alias_search()` in `ai_service.py`
4. Add tests: `tests/test_hierarchy_api.py`
5. Verify: existing queries still work, new alias matching works

### 2.4 Dependencies

- Phase 1 tables must exist
- No frontend changes required (API-only)

---

## Phase 3: Admin UI for Hierarchy Management

**Goal:** Admin จัดการ hierarchy ผ่าน Web UI ได้

### 3.1 New Page: `/settings/hierarchy`

**File:** `frontend-admin/src/pages/HierarchyManager.tsx`

```
┌─────────────────────────────────────────────────────────┐
│  Master Data Management                                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Context: [revenue ▼]   [Extract from Data] [Import CSV] │
│                                                          │
│  ┌─ Hierarchy Levels ──────────────────────────────────┐│
│  │ L0: กลุ่มธุรกิจ (BUSINESS_GROUP)         [Edit]    ││
│  │ L1: กลุ่มบริการ (SERVICE_GROUP)           [Edit]    ││
│  │ L2: บริการ/ผลิตภัณฑ์ (PRODUCT_NAME)      [Edit]    ││
│  │                                           [+ Add]   ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌─ Hierarchy Values (Tree View) ──────────────────────┐│
│  │ ▼ Fixed Line & Broadband                [auto]      ││
│  │   ▼ กลุ่มบริการ Internet Retail          [manual]   ││
│  │     • บริการ Broadband                [manual]   ││
│  │     • บริการ WiFi                     [manual]   ││
│  │   ▼ บริการโทรศัพท์ประจำที่ (Fixed Line) [manual]   ││
│  │     •  Home Phone                      [manual]   ││
│  │     •  Business Trunk Line             [manual]   ││
│  │ ▼ Digital                                [auto]      ││
│  │   ...                                                ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  ┌─ Edit Value ────────────────────────────────────────┐│
│  │ Value: [บริการโทรศัพท์ประจำที่ (Fixed Line)]       ││
│  │ Parent: [Fixed Line & Broadband ▼]                  ││
│  │ Aliases: [fixed line] [โทรศัพท์ประจำที่] [+ Add]   ││
│  │ Source: manual                    [Save] [Cancel]   ││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

### 3.2 Components

| Component | File | Description |
|-----------|------|-------------|
| HierarchyManager | `pages/HierarchyManager.tsx` | Main page with context selector |
| HierarchyLevelList | `components/HierarchyLevelList.tsx` | Level definitions CRUD |
| HierarchyTree | `components/HierarchyTree.tsx` | Tree view of values (Ant Design Tree) |
| HierarchyValueEditor | `components/HierarchyValueEditor.tsx` | Edit value/aliases modal |
| HierarchyImport | `components/HierarchyImport.tsx` | CSV upload + preview |

### 3.3 Key Features

1. **Tree View** — Ant Design `<Tree>` with lazy loading (load children on expand)
2. **Search** — ค้นหาด้วย keyword, highlight matched alias
3. **Inline Edit** — click value → edit modal with aliases tag input
4. **Import CSV** — upload → preview → confirm → import
5. **Extract from Data** — button → calls API → shows diff (new/updated/unchanged)
6. **Source Badge** — `[auto]` / `[manual]` badge แสดงที่มา

### 3.4 Implementation Steps

1. Add route in `frontend-admin/src/App.tsx`
2. Add API service: `frontend-admin/src/services/hierarchy.ts`
3. Build components (above)
4. Add menu item in sidebar

### 3.5 Dependencies

- Phase 2 API endpoints must be ready
- Ant Design Tree component (already in deps)

---

## Phase 4: Automation & AI-Assisted Management

**Goal:** ระบบจัดการตัวเองได้ + AI ช่วยแนะนำ

### 4.1 Auto-Extract on Data Change

**Trigger:** เมื่อมีการ upload data ใหม่ หรือ ETL pipeline ทำงาน

```python
# app/services/hierarchy_service.py

class HierarchyService:
    async def auto_extract_if_stale(self, context_name: str):
        """Check if hierarchy values are stale and re-extract."""
        # Compare data DISTINCT values vs master_hierarchy_values
        # If new values found → auto-insert as 'auto' source
        # If values missing from data → mark is_active=0 (don't delete)

    async def detect_changes(self, context_name: str) -> dict:
        """Compare DB hierarchy vs actual data, return diff."""
        return {
            "new_values": [...],      # in data but not in master
            "missing_values": [...],  # in master but not in data
            "unchanged": count
        }
```

**Schedule Options:**
- **Option A:** FastAPI startup event — run extract on app start
- **Option B:** Admin button "Sync with Data"
- **Option C:** Cron/scheduler (like openminicrew's daily cleanup)

Recommended: **Option B** (manual trigger via Admin UI) + **Option A** (light check on startup)

### 4.2 AI-Assisted Alias Suggestion

**เมื่อ admin เพิ่ม value ใหม่ หรือ AI ไม่พบ match → แนะนำ aliases**

```python
async def suggest_aliases(self, value: str, context_name: str) -> List[str]:
    """Use AI to suggest search aliases for a hierarchy value."""
    prompt = f"""
    ข้อมูลนี้คือ: "{value}" ในบริบท {context_name}
    ช่วยแนะนำ search aliases ที่คนอาจใช้ค้นหา เช่น:
    - ชื่อย่อ (abbreviation)
    - ชื่อภาษาอังกฤษ/ไทย
    - คำที่ใช้เรียกทั่วไป
    Return JSON array of strings only.
    """
    # Use cheap model (haiku/flash) for cost efficiency
    ...
```

### 4.3 Unmatched Query Learning

**เมื่อ AI สร้าง SQL ที่ใช้ LIKE '%keyword%' แต่ไม่มี hierarchy match → log ไว้**

```python
# ใน query_hybrid, after SQL generation:
if "LIKE" in sql_query:
    # Extract LIKE patterns
    patterns = re.findall(r"LIKE\s+'%(.+?)%'", sql_query)
    for pattern in patterns:
        if not hierarchy_alias_exists(pattern, context_name):
            log_unmatched_keyword(pattern, context_name, question)
            # Admin can later review and add as alias
```

**Admin UI:**
```
┌─ Unmatched Keywords ──────────────────────────┐
│ "fixed line"  × 15 queries  → [Add as alias]  │
│ "ค่า internet" × 8 queries  → [Add as alias]  │
│ "สญ."         × 5 queries  → [Add as alias]  │
└────────────────────────────────────────────────┘
```

### 4.4 Implementation Steps

1. Create `app/services/hierarchy_service.py`
2. Add startup extract check in `app/main.py`
3. Add "Sync" button in Admin UI (Phase 3)
4. Add unmatched keyword logging in `ai_service.py`
5. Add unmatched keyword review page in Admin UI
6. Add AI alias suggestion endpoint

### 4.5 Dependencies

- Phase 3 Admin UI
- Cheap AI model available (for alias suggestion)

---

## Design Principles Applied

> Full version: `CLAUDE.md` § Design Principles

### No Hardcoding

| What | Where it lives | NOT in code |
|------|---------------|-------------|
| Product hierarchy | `master_hierarchy` + `master_hierarchy_values` | ~~COLUMN_HIERARCHIES dict~~ |
| View/table names | `schema_contexts.main_view` + `master_hierarchy.source_view` | ~~hardcoded strings~~ |
| Column names | `master_hierarchy.level_columns` | ~~hardcoded lists~~ |
| Keywords | `master_hierarchy.detection_keywords` | ~~hardcoded regex/lists~~ |
| Business values | `master_hierarchy_values.value` + `.aliases` | ~~hardcoded examples~~ |

**Hardcode is acceptable ONLY for:**
- Fallback defaults when DB is unavailable (e.g. `_HARDCODED_HIERARCHIES`)
- Structural constants (e.g. `_HIERARCHY_CACHE_TTL = 3600`)
- Error messages and log strings

### Design for Change

**ถ้าค่าอาจเปลี่ยนในอนาคต → ห้าม hardcode → ใส่ DB**

| สิ่งที่เปลี่ยนได้ | ออกแบบรองรับอย่างไร |
|-------------------|-------------------|
| เพิ่ม context ใหม่ (expense, asset) | Admin UI → Add Level → Extract → ไม่ต้องแก้ code |
| เปลี่ยน view name | แก้ `source_view` ใน DB → extract อ่าน DB |
| เปลี่ยน column name | แก้ `level_columns` ใน DB → AI อ่าน DB |
| เพิ่ม keyword ใหม่ | แก้ `detection_keywords` ใน DB → AI อ่าน DB |
| เพิ่ม product/org ใหม่ | Auto-extract ดึงจาก data จริง หรือ import CSV |
| รูปแบบ master CSV เปลี่ยน | `import_master_data.py` ใช้ column names ไม่ใช่ positions |

### Automation & Maintenance

```
วงจรการดูแลระบบ:

1. Data ใหม่เข้าระบบ (ETL/import)
   ↓
2. Admin กดปุ่ม "Extract from Data" (หรือ cron schedule)
   ↓
3. ระบบ auto-extract → เจอ values ใหม่ → บันทึกเป็น source='auto'
   ↓
4. Admin ตรวจสอบ → แก้ aliases, parent → เปลี่ยนเป็น source='manual'
   ↓
5. AI ใช้ hierarchy ใหม่ทันที (หลัง cache expire 1hr หรือ invalidate)
   ↓
6. AI สร้าง SQL → LIKE patterns ที่ไม่มี alias → log unmatched
   ↓
7. Admin review unmatched → เพิ่มเป็น alias → ลดปัญหาครั้งต่อไป
```

**Idempotent operations:** extract/import ซ้ำกี่รอบก็ได้:
- `UNIQUE(context_name, level, value)` → ไม่สร้าง duplicate
- `ON CONFLICT DO UPDATE` → อัปเดต timestamp เท่านั้น
- `source='manual'` → auto-extract ไม่ทับ

---

## Adding New Context (NO CODE CHANGES needed)

### Via Admin UI (recommended)

1. ไปที่ `/hierarchy` → เลือกหรือพิมพ์ชื่อ context ใหม่
2. Add Level:
   - Level 0: ชื่อ, columns, keywords, `source_view`, `parent_column` = NULL
   - Level 1: ชื่อ, columns, keywords, `source_view`, `parent_column` = ชื่อ column ของ level 0
3. Click "Extract from Data" → ดึง values จาก view อัตโนมัติ
4. Done — AI ใช้ได้ทันที

### Via Command Line (for batch/initial setup)

```bash
# ถ้ามี master CSV
python scripts/import_master_data.py --source /path/to/master --type expense_gl

# ถ้าไม่มี master CSV → extract จาก data จริง
python scripts/extract_hierarchy.py --context expense
```

### Adding New Import Type (requires code — one-time)

เฉพาะเมื่อมี master CSV format ใหม่ที่ไม่เหมือนกับที่มี:

```python
# scripts/import_master_data.py
def import_new_type(conn, source_dir, dry_run=False):
    filepath = source_dir / "MASTER_NEW_TYPE.csv"
    rows = read_csv(filepath)
    for row in rows:
        upsert_level(conn, "new_context", ...)
        upsert_value(conn, "new_context", ...)

IMPORTERS["new_type"] = import_new_type  # register
```

**Note:** นี่เป็น code change เพียงอย่างเดียวที่จำเป็น — เพราะ CSV format ต่างกัน ไม่มี standard

---

## Data Flow Summary

```
1. FIRST TIME SETUP
   CSV Files → import_master_data.py → master_hierarchy (source='manual')
   Data tables → extract_hierarchy.py → master_hierarchy (source='auto')

2. ONGOING (when data changes)
   Admin clicks "Sync" → detect_changes() → show diff → confirm → update
   OR: Auto-extract on app startup (light check)

3. ADMIN EDITS
   Admin UI → CRUD API → master_hierarchy (source='manual')
   Manual edits always preserved over auto-extract

4. AI QUERY PIPELINE
   Question → get_column_hierarchies() (cached 1hr)
           → _detect_hierarchy_level()
           → _hierarchy_alias_search() (Phase 2)
           → correct SQL generation
```

---

## Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| DB table missing on fresh deploy | Hardcoded fallback (`_HARDCODED_HIERARCHIES`) |
| Stale cache after admin edit | Cache TTL = 1 hour. Admin API calls `_invalidate_cache()` explicitly. |
| Master CSV format changes | `import_master_data.py` uses column names, not positions |
| Too many aliases → false matches | Aliases are exact substring match, ranked by length |
| Auto-extract misidentifies hierarchy | source='auto' never overwrites source='manual' |

## Performance — Capacity Planning

### Benchmark (2026-03-07, SQLite, 3,475 values)

| Operation | Latency | Used By |
|-----------|---------|---------|
| `aliases LIKE '%keyword%'` | 0.07–0.37 ms | AI pipeline (every query) |
| Load hierarchy levels (19 rows) | 0.04 ms | Cached 1hr |
| Load ALL 3,475 values | 5.32 ms | Admin UI only |

### Scaling Thresholds

| Total Values | Impact | Action Required |
|-------------|--------|-----------------|
| < 5,000 | None (current) | No action |
| 5,000–10,000 | Negligible | Monitor alias search latency |
| 10,000–50,000 | LIKE scan may reach 2-5ms | Add index: `CREATE INDEX idx_mhv_aliases ON master_hierarchy_values(aliases)` |
| > 50,000 | LIKE full-scan too slow | Migrate to SQLite FTS5 or separate alias lookup table |

### Why Current Design is Safe

1. **AI pipeline uses `LIKE` search with `LIMIT 10`** — returns 6-10 rows per keyword, never scans full table
2. **Hierarchy levels (19 rows) are cached in memory** — 0 DB queries during normal operation
3. **Admin UI paginates** — loads 100 rows at a time, not full table
4. **SQLite keeps DB in memory** on repeated access — cold start ~5ms, warm ~0.3ms

### When to Re-evaluate

- New context with > 2,000 values added (e.g. detailed cost center master)
- Alias search latency > 5ms in production logs
- Total values exceed 10,000
- Migration from SQLite to PostgreSQL (different LIKE performance characteristics — may need GIN index + pg_trgm)

### PostgreSQL Migration Notes (future)

If migrating to PostgreSQL:
```sql
-- Replace LIKE with trigram index for fast substring search
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_mhv_aliases_trgm ON master_hierarchy_values USING gin (aliases gin_trgm_ops);
-- LIKE '%keyword%' will use the gin index automatically
```

---

## Timeline Estimate

| Phase | Scope | Depends On |
|-------|-------|-----------|
| Phase 1 | Foundation (tables + scripts + DB-driven) | — |
| Phase 2 | Admin API + value lookup integration | Phase 1 |
| Phase 3 | Admin UI (hierarchy manager page) | Phase 2 |
| Phase 4 | Automation + AI-assisted management | Phase 3 |
