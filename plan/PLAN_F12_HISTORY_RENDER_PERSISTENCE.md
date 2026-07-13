# PLAN F12 — Persist Chart/Table/Pivot ในประวัติการสนทนา

**วันที่:** 2026-07-13
**Prerequisite:** ไม่มี (F1–F11 executed ครบแล้ว — ดู `PLAN_FIX_MASTER.md`)
**ประมาณเวลา:** 1–1.5 วัน
**หลักการ:** reproducibility — เปิดประวัติแล้วต้องเห็น "สิ่งเดียวกับที่เคยเห็น" (accuracy over performance ตามหลักโปรเจกต์)

---

## ปัญหา (ยืนยันจากการอ่าน source จริง 2026-07-13)

เปิดประวัติการสนทนาแล้วเห็นเฉพาะข้อความ — กราฟ ตาราง และ pivot หายทั้งหมด สาเหตุ 4 ชั้น:

1. **`chat_history` ไม่มีคอลัมน์เก็บ visualization payload** (`app/models/chat.py`) — มีแค่ `question`, `generated_sql`, `sql_result_summary`, `ai_response`
2. **`_save_history` ทิ้งข้อมูล** (`app/api/v1/chat.py`) — `result.data` ถูก `str(...)[:1000]` เก็บเป็น summary ให้ LLM เท่านั้น ส่วน `chart_config` / `visualization` / `display_hint` / `hierarchy_columns` ไม่ถูก save เลย
3. **`GET /conversations/{id}` คืนแค่ text** (`app/api/v1/conversations.py`) — `ConversationMessageItem` ไม่มี field พวกนี้
4. **`ChatSessionData` ช่วยไม่ได้** — upsert เก็บเฉพาะ query ล่าสุด 1 แถวต่อ conversation (มีไว้สำหรับ chart-only re-render) ไม่ใช่ per-message

ฝั่ง frontend `ChatBubble` (`Message` interface) **รองรับ field ครบอยู่แล้ว** (`data`, `visualization`, `chartConfig`, `displayHint`, `hierarchyColumns`, `warnings`, `confidence`) — ตอน live ใช้งานได้ปกติ ขาดแค่ตอน `loadConversation` ที่ API ไม่มีข้อมูลให้ map

## Decision (บันทึกไว้เพื่ออนาคต)

| ทางเลือก | ข้อดี | ข้อเสีย | ตัดสิน |
|----------|-------|---------|--------|
| **1. เก็บ payload ลง DB** | เปิดประวัติเห็นเหมือนเดิมเป๊ะ (reproducible), ไม่เพิ่ม load ตอนเปิดประวัติ | DB โต — ต้องมี row cap | ✅ **เลือก** |
| 2. Re-execute `generated_sql` ตอนเปิดประวัติ | DB เบา | ข้อมูล business DB เปลี่ยนได้ → สิ่งที่เห็นไม่ตรงกับที่เคยเห็น (ขัดหลัก accuracy), เพิ่ม load | ❌ |

ข้อจำกัดขนาดยอมรับได้เพราะ query layer ตัดผลลัพธ์ที่ 1,000 แถวอยู่แล้ว (ดู F1.2/B2) — payload ต่อ message มีเพดานตามธรรมชาติ และแผนนี้แยก `result_data` เป็นคอลัมน์ต่างหากเพื่อให้ retention job ในอนาคตลบเฉพาะ data ได้โดยไม่แตะ metadata

**จุดที่ต้องระวังที่สุด (พบจากการอ่าน chat.py):** `_format_response` **mutate** `chart_config` หลัง `_save_history` ถูกเรียกไปแล้ว (Wave-4 max_series override + recompute warning) — ดังนั้น**ห้าม persist ใน `_save_history`** ต้อง persist จาก response dict ที่ `_format_response` คืนมา เพื่อเก็บสิ่งที่ client เห็นจริง

---

## หลักการทำงาน (ตาม PLAN_FIX_MASTER — บังคับ)

1. อ่านไฟล์ใน READ FIRST ให้ครบก่อนเขียนโค้ด
2. หลังจบแต่ละ phase: รัน `pytest tests/unit tests/integration` ต้องผ่านทั้งหมด
3. เจอบั๊กนอกขอบเขต → จดใน `plan/FIX_NOTES.md` ห้ามแก้ทันที
4. commit แยกตาม phase (อย่างน้อย 1 commit ต่อ phase)

## READ FIRST (อ่านทั้งไฟล์ก่อนแก้)

- `app/api/v1/chat.py` — โดยเฉพาะ `_save_history`, `_format_response`, `_save_session_data`, `_handle_chart_only`, endpoint `/` และ `/stream`
- `app/api/v1/conversations.py` — `ConversationMessageItem`, `get_conversation`
- `app/models/chat.py`, `app/models/chat_session.py`
- `app/schemas/chat.py` — `ChatResponse`, `ChartConfig`
- `app/config.py` — pattern การเพิ่ม settings
- `scripts/migrate_conversations.py` — pattern migration script ของ app DB (idempotent Python, ไม่ใช่ SQL file ใน `database/migrations/` ซึ่งเป็นของ config DB)
- `frontend/services/conversation.ts`, `frontend/app/(app)/index.tsx` (ฟังก์ชัน `loadConversation`), `frontend/components/Chat/ChatBubble.tsx` (เฉพาะ `Message` interface — ไม่ต้องแก้)
- `tests/unit/test_chart_feedback_events.py` หรือ test ใกล้เคียง — ดู pattern การ mock DB session ใน test เดิม

---

## Phase A — Backend: เก็บและส่งคืน render payload

### A.1 Model: เพิ่ม 2 คอลัมน์ใน `chat_history`

`app/models/chat.py` — เพิ่มใน `ChatHistory`:

```python
# F12: render payload สำหรับ restore กราฟ/ตาราง/pivot ตอนเปิดประวัติ
# แยก 2 คอลัมน์เพื่อให้ retention job อนาคตลบ result_data ได้โดยไม่เสีย metadata
render_meta = Column(Text, nullable=True)   # JSON: visualization, chart_config, display_hint, hierarchy_columns, warnings, confidence, data_truncated, total_rows
result_data = Column(Text, nullable=True)   # JSON: list of row dicts (capped ที่ HISTORY_RENDER_MAX_ROWS)
```

ทั้งคู่ nullable → แถวเก่าและ path อื่นที่เขียน `ChatHistory` (เช่น Telegram) ไม่กระทบ

### A.2 Config: row cap

`app/config.py` — เพิ่มใน settings:

```python
HISTORY_RENDER_MAX_ROWS: int = 1000  # เพดานแถวที่เก็บลง chat_history.result_data (query layer ตัดที่ 1,000 อยู่แล้ว)
```

(ตั้งใจใช้ settings ไม่ใช่ admin_config 3-tier — ค่านี้เป็น storage policy ไม่ใช่ AI behavior; ถ้าภายหลังต้องการปรับผ่าน UI ค่อยย้าย)

### A.3 Persist หลัง `_format_response` (จุดสำคัญที่สุด)

`app/api/v1/chat.py` — เพิ่ม helper:

```python
def _persist_render_payload(db: Session, chat_entry: ChatHistory, response_data: dict) -> None:
    """
    F12: เก็บ payload ที่ client เห็นจริงลง chat_history (เรียกหลัง _format_response เสมอ
    เพราะ _format_response mutate chart_config — max_series override + warning recompute)
    Non-fatal: ล้มเหลวแค่ log warning ห้ามทำให้ response พัง
    """
    try:
        data = response_data.get("data") or []
        max_rows = settings.HISTORY_RENDER_MAX_ROWS
        truncated = len(data) > max_rows

        meta = {
            "visualization": response_data.get("visualization"),
            "chart_config": response_data.get("chart_config"),
            "display_hint": response_data.get("display_hint"),
            "hierarchy_columns": response_data.get("hierarchy_columns"),
            "warnings": response_data.get("warnings"),
            "confidence": response_data.get("confidence"),
            "data_truncated": truncated,
            "total_rows": len(data),
        }
        chat_entry.render_meta = json.dumps(meta, ensure_ascii=False, default=str)
        chat_entry.result_data = (
            json.dumps(data[:max_rows], ensure_ascii=False, default=str) if data else None
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to persist render payload (non-fatal): {e}")
```

จุดเรียก **2 ที่** (ทั้งสอง endpoint สร้าง response ผ่าน `_format_response` เหมือนกัน):

1. `chat()` (POST `/`) — ปัจจุบัน step 9 คือ `return _format_response(...)` → เปลี่ยนเป็น:
   ```python
   response_data = _format_response(chat_entry, conversation_id, engine_result, admin_config)
   _persist_render_payload(db, chat_entry, response_data)
   return response_data
   ```
2. `chat_stream()` (POST `/stream`) ใน `generate_events()` — หลังบรรทัด `response_data = _format_response(...)` ก่อน `yield _sse_format("answer", response_data)` (persist ก่อน yield เพื่อให้ข้อมูลลง DB แม้ client หลุดระหว่างส่ง answer)

**ห้าม**แตะ `_save_history` — `sql_result_summary` ยังจำเป็นสำหรับ LLM context เหมือนเดิม

### A.4 API: คืน payload ใน conversation detail

`app/api/v1/conversations.py`:

1. เพิ่ม fields ใน `ConversationMessageItem`:
   ```python
   data: Optional[List[Dict[str, Any]]] = None
   visualization: Optional[str] = None
   chart_config: Optional[Dict[str, Any]] = None
   display_hint: Optional[str] = None
   hierarchy_columns: Optional[List[str]] = None
   warnings: Optional[List[Dict[str, Any]]] = None
   confidence: Optional[Dict[str, Any]] = None
   data_truncated: bool = False
   ```
   (ใช้ `Dict[str, Any]` ตรง ๆ ไม่ import `ChartConfig` schema — payload ถูก serialize มาแล้วจาก response จริง ไม่ต้อง validate ซ้ำ)

2. ใน `get_conversation` เพิ่ม helper parse แบบกันพัง (แถวเก่า = NULL, JSON เสีย = ข้าม):
   ```python
   def _safe_json(text_val, default=None):
       if not text_val:
           return default
       try:
           return json.loads(text_val)
       except (ValueError, TypeError):
           logger.warning("Corrupted render payload JSON in chat_history — returning None")
           return default
   ```
   แล้ว map ต่อ message:
   ```python
   meta = _safe_json(m.render_meta, {}) or {}
   ConversationMessageItem(
       ...เดิม...,
       data=_safe_json(m.result_data),
       visualization=meta.get("visualization"),
       chart_config=meta.get("chart_config"),
       display_hint=meta.get("display_hint"),
       hierarchy_columns=meta.get("hierarchy_columns"),
       warnings=meta.get("warnings"),
       confidence=meta.get("confidence"),
       data_truncated=bool(meta.get("data_truncated", False)),
   )
   ```
   (ต้อง `import json` — เช็คก่อนว่าไฟล์นี้ยังไม่มี)

**ข้อจำกัดที่รับรู้แล้ว (ไม่แก้ในแผนนี้):** conversation ยาว ๆ ที่มี data ทุก message จะทำ response ใหญ่ขึ้น — ถ้าเจอปัญหาจริงค่อยเพิ่ม `?include_data=false` + lazy endpoint ภายหลัง จดไว้ใน `FIX_NOTES.md` ถ้าพบ

### A.5 Migration script

สร้าง `scripts/migrate_chat_render_payload.py` ตาม pattern ของ `scripts/migrate_conversations.py` (idempotent, ใช้ `app.db.session.engine`):

```python
from sqlalchemy import text, inspect
from app.db.session import engine

def migrate():
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("chat_history")}
    with engine.begin() as conn:
        if "render_meta" not in existing:
            conn.execute(text("ALTER TABLE chat_history ADD COLUMN render_meta TEXT"))
            print("Added chat_history.render_meta")
        if "result_data" not in existing:
            conn.execute(text("ALTER TABLE chat_history ADD COLUMN result_data TEXT"))
            print("Added chat_history.result_data")
    print("Migration complete (idempotent).")
```

`ALTER TABLE ... ADD COLUMN` ใช้ได้ทั้ง SQLite และ PostgreSQL (`DATABASE_URL` รองรับทั้งคู่ — ดู `_create_engine`) แถวเก่าได้ NULL อัตโนมัติ ไม่ต้อง backfill (ประวัติเก่าแสดง text-only เหมือนพฤติกรรมปัจจุบัน — ยอมรับ)

### Phase A — Tests

`tests/unit/test_history_render_persistence.py` (ใหม่):

- `_persist_render_payload`: response ที่มี data + chart_config → `render_meta`/`result_data` ถูกเขียนเป็น JSON ที่ parse กลับได้ครบทุก field
- Row cap: data 1,500 แถว, `HISTORY_RENDER_MAX_ROWS=1000` (monkeypatch settings) → เก็บ 1,000 แถว, `data_truncated=True`, `total_rows=1500`
- ไม่มี data (คำตอบ text-only) → `result_data` เป็น NULL, `render_meta` ยังถูกเขียน (visualization=None)
- Persist ล้มเหลว (mock `db.commit` โยน exception) → ไม่ raise, มี rollback
- `get_conversation`: แถวเก่า (NULL ทั้งคู่) → fields ใหม่เป็น None/False ไม่มี error
- `get_conversation`: `render_meta` เป็น JSON เสีย (`"{broken"`) → คืน None ไม่ 500

Integration (เพิ่มในไฟล์เดียวกันหรือ `tests/integration/`): ยิง `/chat` (mock QueryEngine ให้คืนผลมี data + explanation dict ที่มี chart_config) → ตามด้วย `GET /conversations/{id}` → `chart_config` ที่ได้ต้อง**เท่ากับ**ใน chat response (พิสูจน์ว่าเก็บค่า post-enrichment รวม `max_series`)

### Phase A — Checklist

- [x] `app/models/chat.py` เพิ่ม 2 คอลัมน์
- [x] `app/config.py` เพิ่ม `HISTORY_RENDER_MAX_ROWS`
- [x] `_persist_render_payload` + จุดเรียก 2 ที่ (`/` และ `/stream`)
- [x] `conversations.py` — schema fields ใหม่ + `_safe_json` + mapping
- [x] `scripts/migrate_chat_render_payload.py` + รันกับ `app.db` จริงสำเร็จ (รันตอนจบทั้งแผน — ดู Definition of Done)
- [x] Tests ใหม่ผ่าน + `pytest tests/unit tests/integration` เขียวทั้งชุด (629 passed, 3 skipped — baseline ที่วัดจริงตอนเริ่มงานคือ 617 passed/3 skipped ไม่ใช่ 363 ตามที่ระบุในแผน; ต้องแก้ raw-SQL DDL ใน `tests/unit/test_auto_analyzer.py` และ `tests/unit/test_feedback_enhanced.py` เพิ่ม `render_meta`/`result_data` ให้ตรง ORM model — บันทึกใน FIX_NOTES.md)

---

## Phase B — Frontend: restore ตอน `loadConversation`

### B.1 `frontend/services/conversation.ts`

เพิ่มใน `ConversationMessage` interface (ให้ตรงกับ A.4):

```typescript
data?: Record<string, any>[] | null;
visualization?: string | null;
chart_config?: ChartConfig | null;   // import type { ChartConfig } from '../types/chart'
display_hint?: 'hierarchical' | 'crosstab' | 'flat' | null;
hierarchy_columns?: string[] | null;
warnings?: DataWarning[] | null;     // reuse type จาก services/chat.ts หรือประกาศซ้ำแบบ minimal
confidence?: any | null;
data_truncated?: boolean;
```

### B.2 `frontend/app/(app)/index.tsx` — `loadConversation`

ตอน map assistant message เพิ่ม fields (ชื่อฝั่ง `Message` เป็น camelCase — ดู `ChatBubble.tsx`):

```typescript
restored.push({
    id: m.id,
    chatId: m.id,
    role: 'assistant',
    content: m.ai_response,
    sql: m.generated_sql || undefined,
    question: m.question,
    executionTime: m.execution_time_ms,
    // F12: restore chart/table/pivot
    data: m.data || undefined,
    visualization: m.visualization || undefined,
    chartConfig: (m.chart_config as any) || undefined,
    displayHint: m.display_hint || undefined,
    hierarchyColumns: m.hierarchy_columns || undefined,
    warnings: m.warnings || undefined,
    confidence: m.confidence || undefined,
});
```

`ChatBubble` มี per-message `ErrorBoundary` ครอบอยู่แล้วใน `index.tsx` — payload เสียตัวเดียวไม่ทำแอปพัง **ไม่ต้องแก้ `ChatBubble.tsx`**

ถ้า `data_truncated === true` → แสดงหมายเหตุเล็ก ๆ ใต้ตาราง (เช่นต่อท้าย content หรือ warning bubble) ว่า "แสดงข้อมูลบางส่วนจากประวัติ" — ทำแบบ minimal ห้าม redesign UI

### B.3 QA แบบ manual (web)

1. ถามคำถามที่ได้กราฟ + ตาราง → reload หน้า (URL `?c=` เดิม) → กราฟ/ตาราง/toggle pivot ต้องกลับมาครบ
2. เปิด conversation เก่า (ก่อน migration) → text-only เหมือนเดิม ไม่มี error ใน console
3. สลับ conversation ไปมาใน sidebar → payload ไม่ปนข้าม conversation

### Phase B — Checklist

- [x] `conversation.ts` interface อัปเดต
- [x] `loadConversation` map ครบทุก field
- [x] หมายเหตุ data_truncated (minimal — ต่อท้าย `content` ด้วย markdown italic แทนการเพิ่ม warning bubble แยก)
- [x] QA manual ตาม B.3 ผ่านทั้ง 3 ข้อ (ทดสอบจริงผ่าน backend :8000 + frontend :8081 ที่รันอยู่แล้ว, login ผ่าน dev-OTP; ลบ test data ที่สร้างออกจาก app.db หลังทดสอบเสร็จ)

---

## Phase C (optional — ทำเมื่อ A+B เสร็จและมีเวลา) — persist การสลับกราฟ (chart-only)

**ปัญหา:** `_handle_chart_only` ไม่เขียน `ChatHistory` (id=None) — user สั่ง "ขอเป็น pie" แล้ว reload จะได้กราฟ config เดิมก่อนสลับ

**การแก้ (เลือกวิธีบุกรุกน้อยสุด):** ใน `_handle_chart_only` หลัง `enrich_chart_config` สำเร็จและมี data — หา `ChatHistory` แถวล่าสุดของ conversation นั้น (`ORDER BY created_at DESC LIMIT 1`) ที่ `render_meta IS NOT NULL` แล้วอัปเดตเฉพาะ `visualization` + `chart_config` ใน `render_meta` (JSON load → update 2 key → dump กลับ) — non-fatal เช่นเดิม

**Test:** chart-only request → แถวล่าสุดใน chat_history มี `render_meta.visualization` เป็นค่าใหม่ / conversation ที่ไม่มีแถว render_meta → ไม่ crash

- [x] Phase C implemented + tests ผ่าน — `_persist_chart_only_switch` เพิ่มใน `app/api/v1/chat.py`, เรียกท้าย `_handle_chart_only` หลัง `_log_chart_feedback_event`; tests 3 เคสใน `tests/unit/test_history_render_persistence.py` (632 passed, 3 skipped ทั้งชุด)

---

## นอกขอบเขต (ห้ามทำในแผนนี้)

- **Retention job** ลบ `result_data` เก่า (ผูก `BackgroundScheduler`) — รอดูขนาด DB จริงก่อน จด baseline ขนาด `app.db` ก่อน/หลัง deploy ไว้ใน `FIX_NOTES.md`
- **Lazy loading data** (`include_data=false`) — ทำเมื่อ response ใหญ่เป็นปัญหาจริง
- **Telegram** — ไม่กระทบ (คอลัมน์ nullable) และ Telegram render กราฟเป็นรูปส่งในแชทอยู่แล้ว ไม่มีแนวคิด "เปิดประวัติ"
- **แก้ `ChatSessionData`** — ยังใช้กับ chart-only flow เหมือนเดิม ไม่แตะ

## Definition of Done

- [ ] Migration รันแล้วบน `app.db` (idempotent — รันซ้ำไม่พัง)
- [ ] ถาม → ได้กราฟ/ตาราง/pivot → reload → เห็นเหมือนเดิม (รวม max_series/warning ที่ enrich แล้ว)
- [ ] ประวัติเก่าก่อน migration เปิดได้ปกติแบบ text-only
- [ ] `pytest tests/unit tests/integration` เขียวทั้งชุด (baseline: 363 passed, 3 skipped)
- [ ] อัปเดต `plan/IMPLEMENTATION_STATUS.md` และ `plan/README.md` (เพิ่ม F12)
- [ ] จด baseline ขนาด `app.db` ใน `plan/FIX_NOTES.md` เพื่อประกอบการตัดสินใจ retention job
