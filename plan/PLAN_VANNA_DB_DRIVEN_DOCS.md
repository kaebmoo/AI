# Plan: Vanna Documentation — Static File to DB-Driven

**Project root:** `/Users/seal/Documents/GitHub/AI/`
**Date:** 2026-03-23 (rev 5)

**Status update:** core DB-driven Vanna docs flow, admin CRUD, sync-status tracking, and admin UI are already in place. The next round should shift from architecture delivery to retrieval-quality verification, business-view documentation refresh, and operational hardening.

---

## Problem

`vanna_service._sync_documentation()` อ่าน `docs/DATABASE_TABLES_GUIDE.md` เป็น static file แล้ว chunk ใส่ ChromaDB เป็น RAG training data

ปัญหาเชิงสถาปัตยกรรม 4 ข้อ:

1. **Static file coupling** — Vanna ผูกกับไฟล์ที่ path fix ตาย ไฟล์หาย = knowledge หายเงียบ (แค่ print warning)
2. **Duplication** — เนื้อหาส่วนใหญ่ใน guide ซ้ำกับข้อมูลที่ `_sync_documentation()` ดึงจาก config DB อยู่แล้ว (business rules, semantic mappings) และ `_sync_ddl()` ดึง DDL อยู่แล้ว
3. **Onboarding gap** — admin onboard context ใหม่ผ่าน pipeline แล้ว guide ไม่รู้จัก context นั้น Vanna brain ไม่มี summary ให้ context ใหม่
4. **Single source of truth ไม่มี** — human doc (markdown) กับ runtime doc (DB tables) ใช้ source คนละตัว ทำให้ drift กันตลอด

## Solution

1. สร้างตาราง `vanna_documentation` สำหรับ **manual-only** knowledge docs
2. เพิ่ม `_sync_context_summaries()` ที่ auto-generate summary ต่อ context แล้ว train เข้า Vanna ตรง (ไม่ persist ลงตาราง — regenerate ทุก sync จาก live DB)
3. เพิ่ม CRUD API + admin UI สำหรับจัดการ manual docs
4. เพิ่ม brain sync status ที่ track **ทุก brain-relevant change** (docs, contexts, mappings, rules, golden examples, schema metadata, hierarchy, onboarding) ไม่ใช่แค่ vanna_docs
5. ลบ static file dependency ออกจาก Vanna code path
6. เก็บ `docs/DATABASE_TABLES_GUIDE.md` เป็น human-only reference doc

---

## Design decisions

### `vanna_documentation` = manual-only table

- `_sync_context_summaries()` generate จาก live DB data ทุก sync — ไม่ persist เพราะ source of truth คือ DB tables ที่มีอยู่แล้ว
- ไม่มีคอลัมน์ `auto_generated` — ตารางเก็บเฉพาะ manual knowledge
- Flow ชัด: manual docs อ่านจากตาราง, context summaries generate on-the-fly

### Brain sync status = single key `last_brain_relevant_change_at`

- Track ด้วย key เดียว ไม่ใช่แยกต่อ source
- Update จากทุกจุดที่กระทบ brain: vanna_docs CRUD, context CRUD, mappings CRUD, rules CRUD, golden examples CRUD, schema metadata CRUD, hierarchy CRUD, onboarding apply
- เทียบกับ `last_brain_sync_at` เพื่อบอก admin ว่า `needs_sync` หรือไม่
- ทำผ่าน shared helper `mark_brain_dirty()` ใน `_shared.py` — แต่ละ route file เรียก 1 บรรทัดหลัง mutation

### `updated_at` policy

- ใช้ DB trigger (pattern เดียวกับ `admin_config` ใน migration 004) — ไม่พึ่ง application code

### AdminConfigService session management

- `mark_brain_dirty()` และ analytics.py sync timestamp สร้าง `AdminConfigService()` โดยไม่ส่ง session → `_owns_session = True` → ต้อง `.close()` ใน `finally` block เสมอเพื่อป้องกัน session leak

---

## Risk assessment

การเปลี่ยน training corpus ของ Vanna มี **behavioral risk ที่ retrieval quality จะเปลี่ยน**:

- Chunk shape เปลี่ยน (จาก markdown sections เป็น DB rows + generated summaries)
- อาจเกิด duplication ระหว่าง business rules, semantic mappings, context summaries, manual docs
- Context summary ที่เขียนกว้างเกินอาจกลบ rule ที่เฉพาะกว่าใน retrieval ranking

**Acceptance criteria เชิง RAG quality (Phase 7):**
- หลัง sync ใหม่ ต้องทดสอบ 5-10 คำถามตัวอย่าง แล้วเทียบ retrieved docs กับ expected docs
- จำนวน chunks ต่อ context summary ต้อง <= 1 (ห้ามยาวเกิน 800 words)
- Manual doc content ห้ามซ้ำกับ rule text ที่ sync จาก `schema_business_rules` แล้ว
- Context summary ห้ามมี business rule details — แค่ structural info (columns, hierarchy, summable/groupable)

---

## Next round follow-up

### Phase 7A: Retrieval QA pack

- สร้างชุดคำถามตัวอย่างต่อ context หลัก และบันทึก expected retrieved docs
- ตรวจ false positive/false negative หลังเปลี่ยนเป็น DB-driven docs
- สรุป threshold tuning ที่เหมาะกับ production data จริง

### Phase 7B: Business DB docs refresh

- อัปเดตเอกสารอ้างอิงของ business views ให้ตรงกับ `schema_contexts.main_view`
- เก็บตัวอย่าง query ที่ hierarchy-safe และใช้ lowercase/view columns ตามของจริง
- เชื่อม process นี้กับ onboarding context ใหม่

### Phase 7C: Operations and recovery

- เขียน runbook สำหรับ migration 031, seeding, admin CRUD, sync, และ rollback/recovery
- เก็บ monitoring note เรื่อง sync duration, reset/retrain failures, และ missing-table handling

---

## Known issue: `_sync_ddl` engine mismatch (out of scope)

`get_all_tables()` ใช้ `service.business_engine` แต่ `_sync_ddl()` อ่าน `sqlite_master` ผ่าน `service.engine` ซึ่งคือ config DB ไม่ใช่ business DB แผนนี้ไม่แก้จุดนี้ แต่ Claude Code ควร verify ก่อนประกาศว่า DDL path ถูกต้อง ถ้าพบว่าผิดให้ note ไว้เป็น follow-up แยก

---

## Source of truth — read these files BEFORE writing any code

**Vanna service (the file being changed):**
- `app/services/vanna_service.py` — read entire file; focus on `_sync_documentation()`, `sync_brain()`, `_sync_ddl()`, `_sync_golden_examples()`

**Schema/context data access:**
- `app/services/schema/service.py` — `SchemaService` facade; methods: `get_all_contexts()`, `get_schema_metadata()`, `get_all_tables()`
- `app/services/schema/context_store.py` — `get_context_info()`, `get_all_contexts()` implementation
- `app/services/ai/hierarchy_context.py` — `get_column_hierarchies()`

**Hierarchy service:**
- `app/services/hierarchy_service.py` — `HierarchyService.get_levels()` returns hierarchy levels per context

**Existing models (pattern reference):**
- `app/models/schema_models.py` — all config DB models use `ConfigBase`

**Admin config service (for sync status) — CRITICAL for session management:**
- `app/services/admin_config_service.py` — `AdminConfigService()` without db param creates its own session (`_owns_session = True`) — MUST call `.close()` after use to prevent session leak. `set_config()` defaults to `config_type='general', category='ai'` — always pass `config_type='system', category='system'` for sync tracking keys

**Admin shared helpers:**
- `app/api/v1/admin/_shared.py` — existing helpers: `ensure_metadata_rows()`, `get_business_db_path()`

**Admin endpoint patterns (CRITICAL — read for style consistency):**
- `app/api/v1/admin/rules.py` — CRUD pattern (note: has `refresh_cache` + `clear_query_cache` side effects — vanna_docs must NOT copy these, but MUST add `mark_brain_dirty()`)
- `app/api/v1/admin/schema.py` — schema metadata CRUD + view builder + dimension families (mutations here affect DDL/prompt — must add `mark_brain_dirty()`)
- `app/api/v1/admin/hierarchy.py` — hierarchy levels/values CRUD (mutations here affect hierarchy info in context summaries — must add `mark_brain_dirty()`)
- `app/api/v1/admin/__init__.py` — router wiring: each domain = separate file + `include_router`
- `app/schemas/admin_schemas.py` — Pydantic schemas use `class Config: from_attributes = True` (NOT `model_config = ConfigDict`)

**Frontend patterns:**
- `frontend-admin/src/services/rules.ts` — API service pattern
- `frontend-admin/src/pages/Rules.tsx` — Ant Design Table + Modal + Form with react-query
- `frontend-admin/src/App.tsx` — route registration
- `frontend-admin/src/components/Layout/AdminLayout.tsx` — sidebar menu items

**Brain sync trigger:**
- `app/api/v1/admin/analytics.py` — `POST /sync-brain` endpoint

**Onboarding pipeline:**
- `app/api/v1/admin/onboarding.py` — does NOT call `sync_brain()` after apply; calls `schema_service.refresh_cache()` only

**Migration numbering:**
- `database/migrations/` — latest is `030`; next = `031`

**Current guide:**
- `docs/DATABASE_TABLES_GUIDE.md` — read entire file to identify unique knowledge

---

## Execution phases

### Phase 1: Create `vanna_documentation` table + sync tracking

**1a. Migration file**

Create `database/migrations/031_vanna_documentation.sql`:

```sql
-- ============================================================
-- Vanna Documentation — manual knowledge docs for RAG
-- ============================================================
CREATE TABLE IF NOT EXISTS vanna_documentation (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_key         TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    category        TEXT DEFAULT 'guide',
    context_name    TEXT,
    is_active       INTEGER DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vanna_doc_active ON vanna_documentation(is_active);
CREATE INDEX IF NOT EXISTS idx_vanna_doc_category ON vanna_documentation(category);
CREATE INDEX IF NOT EXISTS idx_vanna_doc_context ON vanna_documentation(context_name);

CREATE TRIGGER IF NOT EXISTS update_vanna_doc_timestamp
AFTER UPDATE ON vanna_documentation
FOR EACH ROW
BEGIN
    UPDATE vanna_documentation SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- Brain sync tracking keys (both seeded as system/system)
-- ============================================================
INSERT OR IGNORE INTO admin_config (config_key, config_value, config_type, category, display_name, description, is_active, is_sensitive)
VALUES
    ('last_brain_sync_at', NULL, 'system', 'system', 'Last Brain Sync', 'Timestamp of last successful Vanna brain sync', 1, 0),
    ('last_brain_relevant_change_at', NULL, 'system', 'system', 'Last Brain-Relevant Change', 'Timestamp of last change affecting Vanna brain content', 1, 0);
```

No `auto_generated` column. Both sync tracking keys seeded with identical `config_type='system'`, `category='system'` metadata.

**1b. SQLAlchemy model**

Add to `app/models/schema_models.py` at end of file:

```python
class VannaDocumentation(ConfigBase):
    """
    Manually authored knowledge documents for Vanna RAG.
    Replaces static file dependency on docs/DATABASE_TABLES_GUIDE.md.
    Auto-generated context summaries are NOT stored here — they are
    generated on-the-fly by _sync_context_summaries() during brain sync.
    """
    __tablename__ = "vanna_documentation"

    id = Column(Integer, primary_key=True, index=True)
    doc_key = Column(String(100), nullable=False, unique=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), default='guide')
    context_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_vanna_doc_active', 'is_active'),
        Index('ix_vanna_doc_category', 'category'),
    )
```

`onupdate=datetime.utcnow` is backup — DB trigger is primary mechanism.

**1c. Seed data**

INSERT after CREATE TABLE in migration. Each seed doc must be:
- Self-contained (makes sense when ChromaDB retrieves it alone)
- 200-600 words
- NOT duplicating content from `schema_business_rules` or `schema_semantic_mapping`

Seed these 3-5 docs (read `docs/DATABASE_TABLES_GUIDE.md` to extract):

1. **`hierarchy_concept`** (category=guide) — why OR across hierarchy levels is dangerous, how levels relate, drill-down pattern
2. **`multi_context_workflow`** (category=workflow) — how `schema_contexts` routes questions to views, what "context" means
3. **`tables_collaboration_workflow`** (category=workflow) — the step-by-step: semantic_mapping matches terms -> golden_examples provide patterns -> schema_metadata validates columns -> business_rules enforce constraints
4. **`value_lookup_system`** (category=guide) — how keyword_value_index + hierarchy_values enable smart matching
5. **`sqlite_syntax_pitfalls`** (category=best_practice) — ONLY rules NOT already in `schema_business_rules` (check migration 003: `SQLITE_CONCAT`, `SQLITE_NO_LPAD`, `UNION_NO_PARENS` already exist — skip those)

---

### Phase 2: Add `_sync_context_summaries()` to VannaService

Add to `app/services/vanna_service.py`. Generates summaries on-the-fly, trains directly into Vanna, does NOT persist to `vanna_documentation`.

```python
def _sync_context_summaries(self, service: SchemaService):
    """Auto-generate and train one documentation chunk per active context."""
    contexts = service.get_all_contexts()
    if not contexts:
        print("   - No active contexts found for summary generation")
        return

    trained = 0
    for ctx in contexts:
        try:
            main_view = ctx.get('main_view', '')
            display_name = ctx.get('display_name', ctx.get('name', ''))
            description = ctx.get('description', '')
            instruction = ctx.get('instruction_th', '')

            metadata = service.get_schema_metadata(main_view)
            summable = [m['column_name'] for m in metadata if m.get('is_summable')]
            groupable = [m['column_name'] for m in metadata if m.get('is_groupable')]

            summary = f"## Context: {display_name} ({ctx['name']})\n"
            summary += f"Main View: {main_view}\n"
            if description:
                summary += f"Description: {description}\n"
            summary += f"\nSummable columns (ใช้ SUM ได้): {', '.join(summable) or 'none'}\n"
            summary += f"Groupable columns (ใช้ GROUP BY ได้): {', '.join(groupable[:15]) or 'none'}\n"

            try:
                from app.services.hierarchy_service import hierarchy_service
                levels = hierarchy_service.get_levels(ctx['name'])
                if levels:
                    chain = ' > '.join(lv['level_label_th'] for lv in levels)
                    summary += f"\nHierarchy: {chain}\n"
                    summary += "CRITICAL: ห้าม OR ข้ามระดับ hierarchy — ทำให้ตัวเลขผิดเพี้ยนหลายสิบเท่า\n"
            except Exception:
                pass

            if instruction:
                summary += f"\nSpecial instructions: {instruction[:300]}\n"

            self.train(documentation=summary)
            trained += 1
        except Exception as e:
            print(f"   ! Could not generate summary for context '{ctx.get('name')}': {e}")

    print(f"   - Generated {trained} context summaries")
```

Constraints:
- Each summary <= 800 words, structural info only, NO business rule details
- `try/except` around hierarchy, function-local import for `hierarchy_service`

---

### Phase 3: CRUD API endpoints

**3a. Pydantic schemas**

Add to `app/schemas/admin_schemas.py` using the repo's existing style (`class Config` not `ConfigDict`):

```python
class VannaDocCreate(BaseModel):
    doc_key: str
    title: str
    content: str
    category: str = "guide"
    context_name: Optional[str] = None

class VannaDocUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    context_name: Optional[str] = None
    is_active: Optional[bool] = None

class VannaDocResponse(BaseModel):
    id: int
    doc_key: str
    title: str
    content: str
    category: str
    context_name: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class VannaDocListResponse(BaseModel):
    docs: List[VannaDocResponse]
    total: int
```

**3b. Create `app/api/v1/admin/vanna_docs.py`**

Separate route file (follows admin package pattern).

Do NOT put endpoints in `analytics.py`. Do NOT copy `refresh_cache()` / `clear_query_cache()` side effects from rules.py.

| Method | Path | Function |
|---|---|---|
| GET | `/vanna-docs` | List all (filter by category, is_active) |
| GET | `/vanna-docs/{doc_id}` | Get single doc |
| POST | `/vanna-docs` | Create (check doc_key unique) |
| PUT | `/vanna-docs/{doc_id}` | Update |
| DELETE | `/vanna-docs/{doc_id}` | Delete |

All require `deps.require_admin`, use `deps.get_config_db`.

After each mutation, call `mark_brain_dirty()` from `_shared.py`. No other side effects.

**3c. Wire into admin package**

Add to `app/api/v1/admin/__init__.py`:

```python
from .vanna_docs import router as vanna_docs_router
# ...
router.include_router(vanna_docs_router)
```

---

### Phase 4: Brain sync status + `mark_brain_dirty()`

**4a. `mark_brain_dirty()` helper**

Add to `app/api/v1/admin/_shared.py`:

```python
def mark_brain_dirty():
    """Record that brain-relevant config has changed.

    Called after mutations to contexts, mappings, rules, golden examples,
    schema metadata, hierarchy, vanna docs, or onboarding apply.
    Admin sees needs_sync indicator until they trigger Sync Brain.
    """
    try:
        from datetime import datetime
        from app.services.admin_config_service import AdminConfigService
        svc = AdminConfigService()
        try:
            svc.set_config(
                'last_brain_relevant_change_at',
                datetime.utcnow().isoformat(),
                config_type='system',
                category='system',
            )
        finally:
            svc.close()
    except Exception:
        pass
```

Key points:
- Always passes `config_type='system', category='system'` explicitly
- `finally: svc.close()` prevents session leak (`AdminConfigService()` without db param creates its own `ConfigSessionLocal()` with `_owns_session=True`)
- Outer `try/except` ensures failure to track dirty state never breaks the actual mutation

**4b. Add `mark_brain_dirty()` calls to existing route files**

Add `from ._shared import mark_brain_dirty` and call after successful mutations in these files:

| Route file | What it manages | Where to add |
|---|---|---|
| `vanna_docs.py` | Vanna knowledge docs | After create, update, delete |
| `contexts.py` | Schema contexts | After create, update, delete |
| `mappings.py` | Semantic mappings | After create, update, delete |
| `rules.py` | Business rules | After create, update, delete, toggle |
| `golden_examples.py` | Golden SQL examples | After create, update, delete |
| `schema.py` | Schema metadata + view builder + dimension families | After metadata create/update/delete, propagate, dimension batch update |
| `hierarchy.py` | Master hierarchy levels + values | After upsert level, delete level, create/update/delete value, bootstrap, auto-extract |
| `onboarding.py` | Context onboarding | After successful apply (both `onboard_context` and `apply_sql_statements`) |

Pattern — add ONE line after each mutation's success point:

```python
# After db.commit() or success return:
mark_brain_dirty()
```

Do NOT change any existing behavior — just append one call.

**4c. Record sync timestamp in analytics.py**

In `sync_brain_knowledge` endpoint in `app/api/v1/admin/analytics.py`, after successful sync:

```python
# After vanna.sync_brain(service) succeeds:
try:
    from app.services.admin_config_service import AdminConfigService
    from datetime import datetime
    config_svc = AdminConfigService()
    try:
        config_svc.set_config(
            'last_brain_sync_at',
            datetime.utcnow().isoformat(),
            config_type='system',
            category='system',
        )
    finally:
        config_svc.close()
except Exception:
    pass
```

Note: `finally: config_svc.close()` is mandatory — same session leak concern as `mark_brain_dirty()`.

**4d. Brain sync status endpoint**

Add to `vanna_docs.py`:

```python
@router.get("/brain-sync-status")
def get_brain_sync_status(
    _current_user: User = Depends(deps.require_admin),
):
    """Check if Vanna brain needs re-sync after recent changes."""
    from app.services.admin_config_service import AdminConfigService
    config_svc = AdminConfigService()
    try:
        last_sync = config_svc.get_config('last_brain_sync_at')
        last_change = config_svc.get_config('last_brain_relevant_change_at')
        return {
            "last_brain_sync_at": last_sync,
            "last_brain_relevant_change_at": last_change,
            "needs_sync": bool(last_change and (not last_sync or last_change > last_sync)),
        }
    finally:
        config_svc.close()
```

---

### Phase 5: Replace `_sync_documentation()` in VannaService

**Remove** the entire block #3 that reads `docs/DATABASE_TABLES_GUIDE.md`.

**Replace with:**

```python
# 3. Auto-generated context summaries (replaces static guide file)
self._sync_context_summaries(service)

# 4. Manual documentation from vanna_documentation table
try:
    with service.engine.connect() as conn:
        docs = conn.execute(text(
            "SELECT title, content FROM vanna_documentation WHERE is_active = 1 ORDER BY category, doc_key"
        )).mappings().all()
        for doc in docs:
            self.train(documentation=f"## {doc['title']}\n{doc['content']}")
    print(f"   - Trained {len(docs)} documentation entries from DB")
except Exception as e:
    print(f"   ! Could not load vanna_documentation: {e}")
```

Final method structure:

```python
def _sync_documentation(self, service: SchemaService):
    """Train Documentation — DB-driven, no static files."""
    # 1. Business Rules (unchanged)
    # 2. Semantic Mappings (unchanged)
    # 3. Auto-generated context summaries (NEW)
    # 4. Manual documentation from vanna_documentation table (NEW)
```

---

### Phase 6: Tests

Create `tests/unit/test_vanna_documentation.py`:

**Sync/Vanna unit tests (6):**

1. `test_sync_documentation_has_no_file_dependency` — patch `builtins.open` to raise; verify `_sync_documentation` completes without calling it
2. `test_sync_context_summaries_generates_per_context` — mock `get_all_contexts()` returning 2 contexts + mock `get_schema_metadata()` -> verify `train(documentation=...)` called 2 times
3. `test_sync_context_summaries_handles_empty_contexts` — mock returning [] -> no crash, train not called for summaries
4. `test_sync_context_summaries_handles_missing_hierarchy` — mock hierarchy import to raise -> continues without crash, train still called for structural info
5. `test_sync_documentation_reads_vanna_documentation_table` — in-memory SQLite with 1 row -> verify `train(documentation=...)` called with that content
6. `test_migration_creates_table` — execute migration SQL on in-memory DB -> INSERT + query

**CRUD API tests (5):**

7. `test_list_vanna_docs` — create 2 docs, GET list, verify count
8. `test_create_vanna_doc` — POST, verify 201 + response fields
9. `test_create_duplicate_doc_key_fails` — POST same doc_key twice, verify 400
10. `test_update_vanna_doc` — PUT, verify fields changed
11. `test_delete_vanna_doc` — DELETE, verify 204 + GET returns 404

**Brain sync status tests (3):**

12. `test_sync_brain_records_timestamp` — call sync_brain endpoint (mock VannaService) -> verify `last_brain_sync_at` is set in admin_config
13. `test_crud_vanna_doc_marks_brain_dirty` — POST vanna-doc -> verify `last_brain_relevant_change_at` updated in admin_config
14. `test_brain_sync_status_needs_sync` — set `last_brain_relevant_change_at` > `last_brain_sync_at` -> GET brain-sync-status -> verify `needs_sync=true`; then set `last_brain_sync_at` > change -> verify `needs_sync=false`; then both NULL -> verify `needs_sync=false`

**RAG quality acceptance tests (2):**

15. `test_no_duplicate_content_in_corpus` — after sync, verify manual doc content does not duplicate any business rule `rule_description` text
16. `test_context_summary_is_structural_only` — verify generated summary contains column lists and hierarchy but NOT business rule text or semantic mapping details

---

### Phase 7: Frontend admin UI

**7a. `frontend-admin/src/services/vannaDocs.ts`**

```typescript
import api from './api';

export interface VannaDoc {
    id: number;
    doc_key: string;
    title: string;
    content: string;
    category: string;
    context_name: string | null;
    is_active: boolean;
    created_at: string;
    updated_at?: string;
}

export interface VannaDocCreate {
    doc_key: string;
    title: string;
    content: string;
    category?: string;
    context_name?: string | null;
}

export interface VannaDocUpdate {
    title?: string;
    content?: string;
    category?: string;
    context_name?: string | null;
    is_active?: boolean;
}

export interface VannaDocListResponse {
    docs: VannaDoc[];
    total: number;
}

export interface BrainSyncStatus {
    last_brain_sync_at: string | null;
    last_brain_relevant_change_at: string | null;
    needs_sync: boolean;
}

export const getVannaDocs = async (params?: { category?: string; is_active?: boolean }) => {
    const response = await api.get<VannaDocListResponse>('/admin/vanna-docs', { params });
    return response.data;
};

export const getVannaDoc = async (id: number) => {
    const response = await api.get<VannaDoc>(`/admin/vanna-docs/${id}`);
    return response.data;
};

export const createVannaDoc = async (data: VannaDocCreate) => {
    const response = await api.post<VannaDoc>('/admin/vanna-docs', data);
    return response.data;
};

export const updateVannaDoc = async (id: number, data: VannaDocUpdate) => {
    const response = await api.put<VannaDoc>(`/admin/vanna-docs/${id}`, data);
    return response.data;
};

export const deleteVannaDoc = async (id: number) => {
    await api.delete(`/admin/vanna-docs/${id}`);
};

export const getBrainSyncStatus = async () => {
    const response = await api.get<BrainSyncStatus>('/admin/brain-sync-status');
    return response.data;
};
```

**7b. `frontend-admin/src/pages/VannaDocs.tsx`**

Copy pattern from `Rules.tsx`. Key differences:

Page header:
- Query `getBrainSyncStatus` via `useQuery`
- Show yellow Ant Design `Alert` banner when `needs_sync=true`:
  `"Knowledge has been updated since last Brain Sync. Click 'Sync Brain' in Settings to apply changes."`

Table columns: `doc_key`, `title`, `category` (Tag: guide=blue, best_practice=green, workflow=orange), `context_name` (or "All"), `is_active` (Tag), actions (Edit/Delete)

Form fields in Modal: `doc_key` (disabled when editing), `title`, `content` (TextArea rows=10), `category` (Select), `context_name` (Input, optional), `is_active` (Switch)

No `auto_generated` column. No `refresh_cache` / `clear_query_cache` calls.

react-query keys: `['vanna-docs']`, `['brain-sync-status']`
Invalidate `['brain-sync-status']` after any mutation succeeds.

**7c. `frontend-admin/src/App.tsx`**

```tsx
import VannaDocs from './pages/VannaDocs'
<Route path="/vanna-docs" element={<VannaDocs />} />
```

**7d. `frontend-admin/src/components/Layout/AdminLayout.tsx`**

Add under "Knowledge Base" group after Golden Examples:

```tsx
{
    key: '/vanna-docs',
    icon: <FileTextOutlined />,
    label: 'Vanna Knowledge',
},
```

`FileTextOutlined` is already imported.

---

### Phase 8: Update static guide file

Add header to `docs/DATABASE_TABLES_GUIDE.md`:

```markdown
> **Note:** This file is for human reference only. Vanna RAG documentation is now
> managed via the `vanna_documentation` table and auto-generated context summaries.
> Manage via Admin UI: Knowledge Base > Vanna Knowledge.
> See `app/services/vanna_service.py` for the DB-driven sync logic.
```

---

## What NOT to do

- Do NOT add CRUD endpoints to `analytics.py` — create `vanna_docs.py` as separate route file
- Do NOT copy `refresh_cache()` / `clear_query_cache()` from rules.py — vanna docs don't affect schema cache
- Do NOT use `model_config = ConfigDict(...)` — repo uses `class Config: from_attributes = True`
- Do NOT add `auto_generated` column — table is manual-only
- Do NOT persist auto-generated context summaries to `vanna_documentation` table
- Do NOT hook onboarding to auto-call `sync_brain()` — manual trigger is intentional
- Do NOT change `_sync_ddl()` or `_sync_golden_examples()` — out of scope
- Do NOT touch `get_rag_context()` or `_get_chroma_results()`
- Do NOT duplicate business rule text or semantic mapping lists in seed data
- Do NOT call `set_config()` without explicit `config_type='system', category='system'` for sync tracking keys
- Do NOT create `AdminConfigService()` without closing it — always use `try/finally: svc.close()` pattern

---

## File change summary

| File | Action |
|---|---|
| `database/migrations/031_vanna_documentation.sql` | CREATE (table + trigger + seed + sync tracking keys) |
| `app/models/schema_models.py` | ADD `VannaDocumentation` model |
| `app/schemas/admin_schemas.py` | ADD 4 Pydantic schemas (`class Config` style) |
| `app/api/v1/admin/vanna_docs.py` | CREATE (5 CRUD + brain-sync-status endpoint) |
| `app/api/v1/admin/__init__.py` | ADD import + include `vanna_docs_router` |
| `app/api/v1/admin/_shared.py` | ADD `mark_brain_dirty()` helper (with `svc.close()`) |
| `app/api/v1/admin/analytics.py` | MODIFY sync_brain to record `last_brain_sync_at` (with `config_svc.close()`) |
| `app/api/v1/admin/contexts.py` | ADD `mark_brain_dirty()` after mutations |
| `app/api/v1/admin/mappings.py` | ADD `mark_brain_dirty()` after mutations |
| `app/api/v1/admin/rules.py` | ADD `mark_brain_dirty()` after mutations |
| `app/api/v1/admin/golden_examples.py` | ADD `mark_brain_dirty()` after mutations |
| `app/api/v1/admin/schema.py` | ADD `mark_brain_dirty()` after metadata/view/dimension mutations |
| `app/api/v1/admin/hierarchy.py` | ADD `mark_brain_dirty()` after level/value mutations |
| `app/api/v1/admin/onboarding.py` | ADD `mark_brain_dirty()` after apply |
| `app/services/vanna_service.py` | MODIFY `_sync_documentation()`, ADD `_sync_context_summaries()` |
| `tests/unit/test_vanna_documentation.py` | CREATE (16 tests) |
| `frontend-admin/src/services/vannaDocs.ts` | CREATE |
| `frontend-admin/src/pages/VannaDocs.tsx` | CREATE |
| `frontend-admin/src/App.tsx` | ADD route + import |
| `frontend-admin/src/components/Layout/AdminLayout.tsx` | ADD menu item |
| `docs/DATABASE_TABLES_GUIDE.md` | ADD human-only notice |

Total: 21 files (7 create, 14 modify)

---

## Execution order

1. Phase 1 (table + model + seed + sync keys) — everything depends on this
2. Phase 2 (`_sync_context_summaries`) — can test standalone
3. Phase 3 (CRUD API + router wiring) — depends on Phase 1
4. Phase 4 (brain sync status + `mark_brain_dirty` across all routes) — depends on Phase 3
5. Phase 5 (replace `_sync_documentation`) — depends on Phase 1 + 2
6. Phase 6 (tests) — depends on all above
7. Phase 7 (frontend) — depends on Phase 3 + 4
8. Phase 8 (guide notice) — independent, do last

---

## Verification checklist

**Code hygiene:**
1. `grep -r "DATABASE_TABLES_GUIDE" app/` returns zero hits
2. `grep -r "guide_path" app/` returns zero hits
3. `_sync_documentation()` does not call `open()` or `os.path.exists()`
4. No `auto_generated` field anywhere (schema, model, API, UI)
5. `vanna_docs.py` exists as separate route file, NOT inside `analytics.py`
6. Pydantic schemas use `class Config` not `ConfigDict`
7. CRUD endpoints have NO `refresh_cache` or `clear_query_cache` calls
8. All `set_config` calls for sync keys use `config_type='system', category='system'`
9. Both sync tracking keys seeded in migration with system/system
10. Every `AdminConfigService()` created without db param has matching `.close()` in `finally` block

**Functional:**
11. Migration `031` runs on fresh SQLite without errors
12. All 16 tests pass
13. All 5 CRUD endpoints work via `/docs`
14. `POST /sync-brain` records `last_brain_sync_at`
15. `GET /brain-sync-status` returns correct `needs_sync` in all 3 states: never synced, synced but outdated, up-to-date
16. After mutations in ALL 8 route files (vanna_docs, contexts, mappings, rules, golden_examples, schema, hierarchy, onboarding): `last_brain_relevant_change_at` is updated
17. Frontend table renders, create/edit/delete works, sync warning banner shows/hides correctly

**RAG quality:**
18. Seed data contains 3-5 docs, none duplicating business rule text
19. Context summaries are structural only (columns, hierarchy), no rule details
20. After sync, test 5 sample questions — verify relevant docs are retrieved
