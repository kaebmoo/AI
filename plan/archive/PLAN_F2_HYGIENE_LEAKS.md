# PLAN F2 — Resource Leaks, SSE Robustness, Latent Bugs

**Prerequisite:** PLAN_F1 เสร็จ (แตะ `query_engine.py` ต่อจากกัน ห้ามทำขนาน)
**ประมาณเวลา:** 1 วัน

## READ FIRST

- `app/api/deps.py`
- `app/services/query_engine.py` (สภาพหลัง F1)
- `app/api/v1/chat.py` (endpoint `/`, `/stream`, `/train`)
- `app/api/v1/query.py` ← ยังไม่เคย review — อ่านทั้งไฟล์ หา pattern สร้าง `QueryEngine`/`AdminConfigService`
- `app/telegram/dispatcher.py` (`_handle_query`, `_cmd_context`)
- `app/services/mcp_client.py`
- `app/services/ai/retry_loop.py`
- `app/providers/claude_provider.py`
- `app/providers/registry.py`
- `app/config.py`
- `app/services/ai/hybrid_flow.py` (`resolve_context_info`, `query_hybrid`)
- grep ทั้ง repo: `datetime.utcnow`, `AdminConfigService()`, `SchemaService(`

---

## F2.1 — ปิด Config DB session leak (B4)

**ปัญหา:** สองจุดสร้าง `AdminConfigService()` แบบ own-session แล้วไม่ `close()`:
1. `deps.get_ai_service` — รั่วทุกครั้งที่ `/train` ถูกเรียก
2. `QueryEngine.__init__` (`self.admin_config = admin_config or AdminConfigService()`) — รั่วทุก chat/stream/telegram/query request

ขัดกฎเดิมของโปรเจกต์: "`AdminConfigService()` แบบไม่ส่ง db ต้อง close ใน finally เสมอ" (`_build_provider_kwargs` ทำถูกแล้ว ใช้เป็นแบบ)

**การแก้:**

1. เพิ่ม dependency ใน `deps.py`:

```python
def get_admin_config_service() -> Generator:
    svc = AdminConfigService()
    try:
        yield svc
    finally:
        svc.close()
```

2. `deps.get_ai_service`: รับ `config_service: AdminConfigService = Depends(get_admin_config_service)` แทนการสร้างเอง
3. `chat.py` ทั้ง `/` และ `/stream`: เพิ่ม `admin_config: AdminConfigService = Depends(deps.get_admin_config_service)` แล้วส่งเข้า `QueryEngine(mcp_client=..., db_session=db, admin_config=admin_config)`
4. `query.py`: apply pattern เดียวกัน (อ่านไฟล์ก่อน)
5. `QueryEngine.__init__`: ยังรับ fallback สร้างเองได้ (เพื่อ script/test เดิม) แต่ต้อง track ownership และมีทางปิด:

```python
def __init__(self, mcp_client, db_session=None, admin_config=None):
    ...
    self._owns_admin_config = admin_config is None
    self.admin_config = admin_config or AdminConfigService()

def close(self):
    if self._owns_admin_config and self.admin_config:
        self.admin_config.close()
```

6. `telegram/dispatcher.py::_handle_query`: สร้าง `AdminConfigService()` เอง ครอบด้วย `try/finally close` แล้ว inject เข้า engine (ทั้ง branch shared client และ fallback) — หรือเรียก `engine.close()` ใน finally ถ้าปล่อยให้ engine สร้างเอง
7. grep `QueryEngine(` ทั้ง repo — จุดอื่น (scripts, tests, admin tools) ให้เพิ่ม close ตามความเหมาะสม จดรายการที่แก้ลง commit message

**Test:** `tests/unit/test_admin_config_lifecycle.py` — patch `ConfigSessionLocal` ด้วย factory ที่นับ open/close; ยิง `get_admin_config_service` ผ่าน dependency แล้ว assert close ถูกเรียก; สร้าง `QueryEngine()` แบบ fallback + `close()` → session ปิด

---

## F2.2 — `mcp_client.call_tool`: bare except

เปลี่ยน `except:` (ใน fallback loop หา server) เป็น `except Exception:` — bare except กลืน `asyncio.CancelledError` ทำให้ cancel task ไม่ทำงาน (เกี่ยวโดยตรงกับ F2.4)

---

## F2.3 — Dedup ปล่อย key เมื่อ request จบแบบ error

**ปัญหา:** `_dedup_check` mark ตอนเริ่ม ไม่เคยลบ — request แรก error แล้ว user retry ทันที โดนบล็อก "คำถามซ้ำ" 5 วินาที

**การแก้ (query_engine.py):** refactor เป็น mark/release:

```python
def _dedup_mark(question, provider, user_id) -> Optional[str]:
    """คืน key ถ้า mark สำเร็จ, None ถ้าเป็น duplicate"""
    ...

def _dedup_release(key: str) -> None:
    _dedup_store.pop(key, None)
```

ใน `query()`:
- `dedup_key = _dedup_mark(...)`; ถ้า None → คืน duplicate result (พฤติกรรมเดิม)
- ครอบ pipeline ด้วย try/except: ถ้า exception หรือ `result.error` truthy → `_dedup_release(dedup_key)` แล้ว raise/คืนตามเดิม (สำเร็จ → ปล่อยให้ TTL หมดเอง ตามพฤติกรรมเดิม)

**Test:** duplicate ภายใน TTL ถูกบล็อก; request แรก error → request ที่สองทันทีไม่ถูกบล็อก

---

## F2.4 — SSE: drain queue + cancel query task เมื่อ client หลุด

**ปัญหา:** (1) event ที่ push เข้า queue เสี้ยววินาทีก่อน task done จะหาย (2) client ปิดแท็บ → generator ถูก close แต่ `query_task` วิ่งต่อ เผา LLM token ฟรี

**การแก้ (`chat.py::chat_stream::generate_events`):**

```python
query_task = None
try:
    ...
    query_task = asyncio.create_task(engine.query(...))
    while not query_task.done():
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
            yield _sse_format(event["event"], event["data"])
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
    # drain event ที่ค้าง
    while not event_queue.empty():
        event = event_queue.get_nowait()
        yield _sse_format(event["event"], event["data"])
    engine_result = query_task.result()
    ...
except Exception as e:
    logger.error(f"SSE stream error: {e}")
    yield _sse_format("error", {"message": str(e)})
finally:
    if query_task is not None and not query_task.done():
        query_task.cancel()
        logger.info("SSE client disconnected — query task cancelled")
```

**หมายเหตุ:** client disconnect ทำให้ Starlette โยน `GeneratorExit`/cancel เข้า generator — `finally` จะทำงาน นี่คือเหตุผลที่ F2.2 ต้องแก้ก่อน (bare except ใน call_tool จะกลืน CancelledError ระหว่าง cancel)

**Test:** integration test — สร้าง generator, iterate 1-2 events แล้ว `aclose()` → assert task ถูก cancel (mock engine.query เป็น coroutine ค้างนาน)

---

## F2.5 — Hoist `resolve_context_info` ออกจาก retry loop + reuse SchemaService

**ปัญหา:** `query_hybrid` เรียก `resolve_context_info` (สร้าง `SchemaService` ใหม่) **ทุก attempt** ทั้งที่ context ไม่เปลี่ยนระหว่าง retry — เปลือง init/cache ซ้ำ และ `QueryEngine` มี `self.schema_service` อยู่แล้วแต่ไม่ถูกใช้

**การแก้:**
1. `resolve_context_info(context_name, schema_service=None)` — ถ้าได้รับ instance ใช้เลย ไม่สร้างใหม่
2. `query_hybrid(...)` รับ kwarg `schema_service=None` แล้วเรียก `resolve_context_info` **ครั้งเดียวก่อน for-loop** (ย้าย error handling context-not-found ออกมาก่อน loop ด้วย)
3. `AIService.query_hybrid` รับและ forward kwarg
4. `QueryEngine.query`: ส่ง `schema_service=self.schema_service`
5. `dispatcher._cmd_context`: ใช้ instance เดียว module-level หรือสร้างครั้งเดียวต่อ dispatcher — อย่างน้อยย้าย import ออกนอกฟังก์ชันและ comment เหตุผล (ยอมรับได้ถ้าคง per-call แต่ต้องจดเหตุผล)

**Test:** mock SchemaService นับจำนวน instantiate — request เดียวที่ retry 3 ครั้งต้องสร้าง 0 ครั้ง (ใช้ instance ที่ inject)

---

## F2.6 — B8: mcp mode + Claude ใช้งานไม่ได้จริง

สอง sub-bug (โหมด `mode="mcp"` ไม่ใช่ default แต่เป็น API surface ที่เปิดอยู่):

**F2.6.1 — ลบ `top_p` ใน `claude_provider.generate_sql`:** โมเดล Claude 4.5+ ปฏิเสธ request ที่ส่ง `temperature` และ `top_p` พร้อมกัน — คงไว้เฉพาะ `temperature=0` (พฤติกรรม deterministic เท่าเดิม)

**F2.6.2 — message ordering ใน `retry_loop.py` สำหรับ Claude:**
- ปัจจุบันคำถามแรกไม่เคยถูกใส่ `current_history` → turn ที่ 2 message list เริ่มด้วย role `assistant` → Anthropic API reject
- และ `generate_sql` append `{"role":"user","content": question}` แม้ question ว่าง → invalid

การแก้ใน retry_loop (branch claude, เลียนแบบ pattern ของ matcha):
1. เมื่อเจอ tool_calls ครั้งแรก: ถ้า `working_question` ยังไม่ None → append `{"role":"user","content": working_question}` เข้า history แล้วตั้ง `working_question = None`
2. รวม **ทุก tool_use block ของ response เดียวกัน** ไว้ใน assistant message เดียว และ tool_result ทั้งหมดไว้ใน user message เดียวถัดมา (Anthropic กำหนดว่า tool_result ของ parallel calls ต้องอยู่ใน user message เดียวที่ตามหลัง assistant message นั้น):

```python
current_history.append({"role": "assistant", "content": [
    {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]}
    for c in tool_calls
]})
current_history.append({"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": c["id"], "content": str(results[c["id"]])}
    for c in tool_calls
]})
```
(ต้อง refactor loop ให้ execute ทุก tool ก่อน แล้วค่อย append สองก้อนนี้ทีเดียว)

3. `claude_provider.generate_sql`: append user question เฉพาะเมื่อ `question` ไม่ว่าง

**Test:** unit test mock Anthropic client — จำลอง response ที่มี tool_use 2 ก้อน → assert โครง messages ที่ส่งเข้า API turn ถัดไป: เริ่มด้วย user, assistant มี tool_use 2 block, user ถัดมามี tool_result 2 block ครบ id

---

## F2.7 — เก็บกวาด (แต่ละข้อเล็ก ทำรวดเดียว)

1. **`datetime.utcnow()` → `datetime.now(timezone.utc)`** ทั้ง repo (grep แล้วแก้ทุกจุด รวม `chat.py`, `api_key_service.py`) — ระวังจุดที่เทียบกับค่าใน DB ที่เก็บแบบ naive: ถ้า column เป็น naive datetime ให้ใช้ `datetime.now(timezone.utc).replace(tzinfo=None)` เพื่อไม่เปลี่ยน semantics เดิม แล้วจดใน FIX_NOTES ว่า migration ไป aware ทั้งระบบเป็นงานอนาคต
2. **`config.py`:** ลบ `@validator("DATABASE_URL", pre=True) assemble_db_connection` — เป็น pydantic v1 API (`PostgresDsn.build(user=...)`) ที่เป็น dead branch และจะ crash ถ้าเคยถูกเรียกบน pydantic v2; `DATABASE_URL` มี default เป็น str เสมออยู่แล้ว ลบ import `validator`, `PostgresDsn`, `AnyHttpUrl` ที่ไม่ใช้ตาม
3. **`providers/registry.py`:** ลบ `self._instances` (dead code) กันคนเข้าใจผิดว่า provider ถูก cache/แชร์ (การ mutate `.model` ใน tier logic ปลอดภัยเพราะสร้างใหม่ทุกครั้ง — ใส่ comment กำกับไว้ที่ `create_provider`)
4. **`vanna_service.py`:** เปลี่ยน `print(...)` เป็น `logger.info/warning` (module logger)

---

## Acceptance Criteria

- [ ] pytest ทั้ง suite + tests ใหม่ผ่าน
- [ ] grep `datetime.utcnow` = 0 ผลลัพธ์ใน `app/`
- [ ] grep `AdminConfigService()` นอก `deps.py`/`_build_provider_kwargs`/tests → ทุกจุดมี close path
- [ ] Manual SSE: เปิด `/chat/stream` แล้วปิด connection กลางทาง → log แสดง "query task cancelled" และไม่มี LLM call ค้างจนจบ
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md`
