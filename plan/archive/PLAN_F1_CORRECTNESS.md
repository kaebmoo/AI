# PLAN F1 — Correctness Bugs (ผลลัพธ์ต่อ user ผิด/ไม่ครบโดยเงียบ)

> **ตรวจ source ซ้ำ 2026-09-21:** แผนนี้มี implementation แล้ว ไม่ต้อง execute ซ้ำ; สถานะรายข้อ หลักฐาน และ acceptance ที่ยังค้างดู [รายงาน F1–F8](../REVIEW_F1_F8_2026-09-21.md) ข้อความและ checklist ด้านล่างคงไว้เป็นแผนในอดีต

**Prerequisite:** PLAN_F3 Phase A (CI) เขียวก่อน
**ประมาณเวลา:** 1 วัน
**หลักการ:** accuracy สำคัญสุด — ทุกข้อในแผนนี้คือกรณีที่ user ได้คำตอบผิดหรือไม่ครบโดยไม่รู้ตัว

## READ FIRST (อ่านทั้งไฟล์ก่อนแก้)

- `app/services/query_engine.py`
- `app/services/ai/hybrid_flow.py`
- `app/services/ai/service.py` (เฉพาะ `_pending_limit_warning` accessors)
- `app/schemas/chat.py`
- `app/api/v1/query.py` ← **ยังไม่เคย review** อ่านทั้งไฟล์ เช็คว่า request schema มี default provider แบบเดียวกับ B3 หรือไม่
- `app/services/schema/prompt_builder.py` (ฟังก์ชัน `build_system_prompt`, `get_schema_context`)
- tests ที่เกี่ยวข้องใน `tests/unit/` — grep หา `cache`, `dedup`, `limit_warning`, `provider` ก่อน เพื่อรู้ว่า test เดิม assert พฤติกรรมไหนไว้

---

## F1.1 — Query result cache ต้องไม่ทำงานเมื่อมี conversation history

**ปัญหา:** `_cache_key(question, provider, context)` ไม่มี history ในสมการ แต่ SQL ขึ้นกับ history (intent prompt สั่ง inherit filter จากคำถามก่อนหน้า) → คำถาม follow-up ข้อความเดียวกัน ("แล้วเดือนกุมภาล่ะ") จากคนละบทสนทนา ได้ผลลัพธ์ของกันและกัน
**ปัญหารอง:** ตอน cache HIT โค้ด mutate `cached.execution_time_ms` บน object ที่แชร์ใน cache

**การแก้ (ใน `QueryEngine.query`):**

```python
# cache ใช้ได้เฉพาะคำถาม first-turn เท่านั้น
use_cache = not history

qcache_key = _cache_key(question, selected_provider_name, context_name_for_cache)
if use_cache:
    cached = _cache_get(qcache_key)
    if cached is not None:
        from dataclasses import replace
        logger.info(f"QueryEngine: Cache HIT (key={qcache_key[:12]}…)")
        return replace(cached, execution_time_ms=(time.time() - start_time) * 1000)
```

และตอน store:

```python
if use_cache and result.data and not result.error:
    _cache_set(qcache_key, engine_result)
```

**หมายเหตุ:** `dataclasses.replace` เป็น shallow copy — `query_result` ข้างในยังแชร์ object เดิม ยอมรับได้เพราะไม่มีที่ไหน mutate `query_result` หลังคืนค่า (ตรวจยืนยันใน `chat.py` ด้วย) ถ้าพบว่ามีการ mutate ให้เปลี่ยนเป็น `copy.deepcopy` เฉพาะจุด

**Test ใหม่:** `tests/unit/test_query_cache.py`
- คำถามเดียวกัน ไม่มี history สองครั้ง → ครั้งสอง HIT (mock AIService นับจำนวนเรียก)
- คำถามเดียวกัน แต่ครั้งสองส่ง history → MISS (AIService ถูกเรียก)
- cache HIT สองครั้ง → `execution_time_ms` ของผลลัพธ์ครั้งแรกใน cache ไม่ถูกแก้ (assert entry เดิมใน `_query_cache` ไม่เปลี่ยน)

---

## F1.2 — คำเตือน "ข้อมูลถูกตัดที่ 1,000 แถว" ต้องถึง user ใน hybrid mode

**ปัญหา 2 ชั้น:**
1. `execute_sql_attempt` ตั้ง `service.set_pending_limit_warning(...)` แต่ `query_hybrid` **ไม่เคยอ่านออกมา** — ตัวอ่านมีเฉพาะ `retry_loop.py` (mcp mode) → user ใน hybrid (default) ได้ข้อมูล truncate โดยไม่รู้
2. เงื่อนไข trigger เช็ค `isinstance(exec_data, list) and len(exec_data) >= 1000` — แต่ `nt_query_mcp.execute_query` คืน **dict** (`{"success":..., "data":..., "truncated":...}`) เงื่อนไขนี้จึงแทบไม่เคยจริง ต้องใช้ flag `truncated` จาก payload

**การแก้:**

ใน `execute_sql_attempt` (hybrid_flow.py) หลัง parse:

```python
if isinstance(exec_data, dict) and exec_data.get("truncated"):
    logger.warning("Query result truncated by row limit.")
    service.set_pending_limit_warning(LIMIT_WARNING_MESSAGE)
elif isinstance(exec_data, list) and len(exec_data) >= 1000:
    service.set_pending_limit_warning(LIMIT_WARNING_MESSAGE)  # เผื่อ payload แบบ list เดิม
```

ใน `query_hybrid` — บรรทัดแรกของฟังก์ชัน: `service.set_pending_limit_warning("")` (เคลียร์ state ค้างจาก instance reuse)

ใน `run_hybrid_attempt` — หลังได้ `explanation` และก่อนสร้าง `QueryResult`:

```python
pending = service.get_pending_limit_warning()
if pending:
    if isinstance(explanation, dict):
        explanation["explanation"] = (explanation.get("explanation") or "") + pending
    else:
        explanation = (explanation or "") + pending
    service.set_pending_limit_warning("")
```

**สำคัญ:** `explanation` เป็นได้ทั้ง `str` และ `dict` (จาก `explain_result` ที่ผ่าน chart postprocessor) — ต้อง handle ทั้งสองแบบตาม sketch ห้ามลืม

และเคลียร์ pending warning ตอนเริ่ม attempt ใหม่ใน loop (กัน warning จาก attempt ที่ fail ติดไป attempt ถัดไปซึ่งอาจไม่ truncate)

**Test ใหม่:** `tests/unit/test_hybrid_limit_warning.py`
- mock mcp_client.call_tool ให้ `execute_query` คืน dict ที่ `truncated: true` → explanation (ทั้งกรณี str และ dict) ต้องลงท้ายด้วยข้อความเตือน
- กรณี `truncated: false` → ไม่มีข้อความเตือน
- attempt 1 truncated+fail validation, attempt 2 สำเร็จไม่ truncate → ไม่มีข้อความเตือน

---

## F1.3 — เลิก override admin default provider ด้วย schema default

**ปัญหา:** `ChatRequest.provider: Optional[str] = "gemini"` — ทุก request ที่ไม่ระบุ provider จะบังคับ gemini เสมอ ทับค่า `default_ai_provider` ที่ admin ตั้งผ่าน UI (ขัดหลัก DB-driven config) และถ้า gemini ไม่มี key จะไหลเข้า fallback แบบคาดเดายาก

**การแก้:**
1. `app/schemas/chat.py`: `provider: Optional[str] = None` (อัปเดต comment ให้บอกว่า None = ใช้ admin default)
2. อ่าน `app/api/v1/query.py` — ถ้า request schema ของ stateless API มี pattern เดียวกัน แก้เป็น None เช่นกัน
3. **QA ฝั่ง frontend (ห้ามข้าม):** grep ใน `frontend/` และ `frontend-admin/` หาจุดที่เรียก `/chat` และ `/chat/stream` — ยืนยันว่า frontend ส่ง provider ชัดเจนเมื่อ user เลือก และ**ไม่ส่ง** เมื่อ user ไม่ได้เลือก ถ้า frontend hardcode ค่า ให้จดใน `plan/FIX_NOTES.md` (ไม่แก้ frontend ในแผนนี้)

**Test:** แก้/เพิ่มใน test ของ chat endpoint — request ที่ไม่ส่ง provider ต้องได้ `request.provider is None` และ QueryEngine ต้อง resolve จาก `ai_config["default_provider"]` (mock AdminConfigService)

---

## F1.4 — วันที่ปัจจุบันใน system prompt stale ได้สูงสุด 6 ชั่วโมง

**ปัญหา:** `get_schema_context` ฝัง `datetime.now()` ลง prompt แต่ `build_system_prompt` cache ผลลัพธ์ 6 ชม. — คำถามแนว "เดือนนี้/วันนี้" ช่วงหลังเที่ยงคืน/ต้นเดือน อาจได้ค่าอ้างอิงวันที่ผิด

**การแก้ (เลือกวิธีที่ 1 — ต่ำสุดเสี่ยง):** เพิ่มวันที่ลง cache key ใน `build_system_prompt`:

```python
today = datetime.now().strftime('%Y-%m-%d')
cache_key = f"prompt|{ai_provider}|{context_name}|{language}|{include_samples}|{rag_enabled}|{today}"
```

prompt จะถูก rebuild วันละครั้งต่อ context — entry เก่าค้างใน in-memory cache ของ SchemaService ซึ่งยอมรับได้ (ขนาดเล็ก) — ตรวจว่า `set_cached_value` ไม่มีปัญหาโตไม่จำกัด ถ้าไม่มี eviction ให้จดใน FIX_NOTES

**Test:** unit test mock datetime สองค่า → cache key ต่างกัน

---

## Acceptance Criteria (F1 ทั้งแผน)

- [ ] pytest ทั้ง suite ผ่าน + tests ใหม่ตาม 4 ข้อผ่าน
- [ ] Manual: ถามคำถามเดิมซ้ำใน conversation ใหม่หลังคุย follow-up → SQL ถูก generate ใหม่ (ดู log ไม่มี Cache HIT เมื่อมี history)
- [ ] Manual: query ที่คืน > 1,000 แถว (เช่น detail query ไม่ใส่เงื่อนไข) → คำตอบใน UI มีข้อความเตือน
- [ ] Manual: ตั้ง default provider = matcha ใน Admin UI → chat โดยไม่เลือก provider → log แสดง provider matcha
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md` (บันทึกว่า cache/limit-warning behavior เปลี่ยน)
