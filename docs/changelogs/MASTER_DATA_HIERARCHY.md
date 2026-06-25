# AI Assistant — Master Data & DB-Driven Hierarchy

**Date:** 2026-03-07
**Status:** Phase 1 (Foundation) complete. Phase 2-4 planned.

---

## Overview

เปลี่ยน hierarchy system จาก hardcoded dict → DB-driven master data:
1. สร้างตาราง `master_hierarchy` + `master_hierarchy_values`
2. Auto-extract hierarchy จาก data
3. Import master data จาก CSV files
4. `COLUMN_HIERARCHIES` อ่านจาก DB (fallback to hardcoded)

---

## Phase 1: Foundation (DONE)

### New Tables

**`master_hierarchy`** — hierarchy level definitions
```sql
context_name    TEXT     -- 'revenue', 'revenue_org', 'revenue_gl', etc.
level           INTEGER  -- 0=broadest, N=most specific
level_label_th  TEXT     -- 'กลุ่มธุรกิจ'
level_label_en  TEXT     -- 'Business Group'
level_columns   TEXT     -- JSON: ["BUSINESS_GROUP", "BUSINESS"]
detection_keywords TEXT  -- JSON: ["กลุ่มธุรกิจ", "ธุรกิจ"]
source          TEXT     -- 'auto' or 'manual'
```

**`master_hierarchy_values`** — parent-child values with aliases
```sql
context_name    TEXT     -- 'revenue'
level           INTEGER  -- 1
value           TEXT     -- 'บริการโทรศัพท์ประจำที่ (Fixed Line)'
parent_value    TEXT     -- 'Fixed Line & Broadband'
aliases         TEXT     -- JSON: ["fixed line", "บริการโทรศัพท์ประจำที่"]
source          TEXT     -- 'auto' or 'manual'
```

### Key Design: source='manual' Preserved

- `extract_hierarchy.py` (auto) → uses `ON CONFLICT DO UPDATE ... CASE WHEN source='manual' THEN keep ELSE update`
- `import_master_data.py` (manual) → always overwrites
- ลำดับ: import master first → extract auto after → manual entries ไม่ถูกทับ

### Scripts

| Script | Purpose | Command |
|--------|---------|---------|
| `scripts/extract_hierarchy.py` | Auto-extract from data | `python scripts/extract_hierarchy.py` |
| `scripts/import_master_data.py` | Import from CSV files | `python scripts/import_master_data.py --source /path/to/master/source` |

### Master Data Imported

| Type | Source File | Data |
|------|------------|------|
| Product | `MASTER_PRODUCT_NT.csv` | 9 groups, 35 service groups, 270 products |
| Organization | `MASTER_ORGANIZATION_NT_BU.csv` | 12 divisions, 36 groups, 118 depts, 654 sections |
| Revenue GL | `MASTER_REVENUE_GL_CODE_NT1_NT.csv` | 10 GL groups, 175 GL codes |

### DB-Driven Hierarchy Loading

**File:** `app/services/ai_service.py`

```python
# Before: hardcoded
COLUMN_HIERARCHIES = { "revenue": [...], "pl_costtype": [...] }

# After: DB-first with fallback
def get_column_hierarchies() -> Dict:
    return _load_hierarchies_from_db()  # reads master_hierarchy table
    # Falls back to _HARDCODED_HIERARCHIES if DB error
```

- Loaded contexts: `revenue`, `revenue_org`, `revenue_gl`, `pl_costtype`, `transfer price`
- Cache: 1 hour TTL (`_HIERARCHY_CACHE_TTL`)
- All `COLUMN_HIERARCHIES.get()` calls replaced with `get_column_hierarchies().get()`

### Files Changed

| File | Change |
|------|--------|
| `database/migrations/009_master_hierarchy.sql` | New tables |
| `scripts/extract_hierarchy.py` | New: auto-extract from data |
| `scripts/import_master_data.py` | New: import from CSV master files |
| `app/services/ai_service.py` | DB-driven hierarchy loading with fallback |

---

---

## Phase 2: Admin API + Value Lookup (DONE)

### New Files

| File | Purpose |
|------|---------|
| `app/services/hierarchy_service.py` | Business logic: CRUD, search, diff, extract, unmatched keywords |
| `app/schemas/hierarchy_schemas.py` | Pydantic models for API |

### API Endpoints Added to `app/api/v1/admin.py`

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/hierarchy/{ctx}/search?q=` | Public | Alias search (used by AI pipeline) |
| GET | `/hierarchy` | Admin | List contexts with counts |
| GET | `/hierarchy/{ctx}/levels` | Admin | Get levels |
| POST | `/hierarchy/{ctx}/levels` | Admin | Create/update level |
| PUT | `/hierarchy/{ctx}/levels/{n}` | Admin | Edit level |
| DELETE | `/hierarchy/{ctx}/levels/{n}` | Admin | Soft-delete level |
| GET | `/hierarchy/{ctx}/values` | Admin | List values (paginated, filterable) |
| POST | `/hierarchy/{ctx}/values` | Admin | Create value |
| PUT | `/hierarchy/values/{id}` | Admin | Edit value |
| DELETE | `/hierarchy/values/{id}` | Admin | Soft-delete value |
| POST | `/hierarchy/extract` | Admin | Trigger auto-extract |
| GET | `/hierarchy/{ctx}/diff` | Admin | Compare DB vs data |
| GET | `/hierarchy/unmatched` | Admin | Get unmatched keywords |
| POST | `/hierarchy/unmatched/{kw}/resolve` | Admin | Mark resolved |

### AI Pipeline Integration

- `_lookup_values_from_question()` now searches `master_hierarchy_values` aliases before DB
- After SQL generation, LIKE patterns without alias match are logged to `unmatched_keywords` table

---

## Phase 3: Admin UI (DONE)

### New Files

| File | Purpose |
|------|---------|
| `frontend-admin/src/pages/HierarchyManager.tsx` | Main admin page |
| `frontend-admin/src/services/hierarchy.ts` | API client |

### Features

- **Context selector** — switch between revenue, revenue_org, revenue_gl, etc.
- **Levels tab** — view/edit hierarchy level definitions (columns, keywords)
- **Values tab** — paginated table with search, level filter, parent drill-down
- **Unmatched Keywords tab** — view keywords AI used LIKE for but had no alias, add as alias or resolve
- **Extract from Data** button — triggers auto-extract
- **Show Diff** button — compare DB hierarchy vs actual data
- **Add/Edit/Delete** modals for levels and values

### Route

- Path: `/hierarchy`
- Menu: Under "Schema" group as "Master Data"

---

## Phase 4: Automation (DONE)

### Unmatched Keyword Learning

- New table: `unmatched_keywords` (auto-created on first use)
- After SQL generation in `query_hybrid()`, LIKE patterns are checked against hierarchy aliases
- Unmatched patterns are logged with occurrence count + last question
- Admin reviews in UI → "Add as Alias" or "Resolve"

### Change Detection

- `hierarchy_service.detect_changes(context)` compares DB vs data
- Shows new values (in data but not in master) and missing values (in master but not in data)
- Admin can trigger via "Show Diff" button

### Auto-Extract

- `hierarchy_service.auto_extract(context)` delegates to `extract_hierarchy.py`
- Callable from Admin UI or API
- Preserves `source='manual'` entries
