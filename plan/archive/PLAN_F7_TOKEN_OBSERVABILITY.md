# PLAN F7 — Token Accounting จริง + Request Trace แบบ log เดียว

> **ตรวจ source ซ้ำ 2026-09-21:** แผนนี้มี implementation แล้ว ไม่ต้อง execute ซ้ำ; สถานะรายข้อ หลักฐาน และ acceptance ที่ยังค้างดู [รายงาน F1–F8](../REVIEW_F1_F8_2026-09-21.md) ข้อความและ checklist ด้านล่างคงไว้เป็นแผนในอดีต

**Prerequisite:** PLAN_F2 เสร็จ (แนะนำหลัง F3 Phase B เพื่อใช้ eval เช็คว่าไม่กระทบคุณภาพ)
**ประมาณเวลา:** 1-2 วัน
**ขอบเขตชัดเจน:** log-based เท่านั้น — Langfuse/OpenTelemetry เป็น deferred decision (ดู PLAN_FIX_MASTER) ห้ามเพิ่ม dependency ใหม่ในแผนนี้

## READ FIRST

- `app/providers/base.py` ทั้งไฟล์ (โครง `QueryResult`, `AIProvider` interface)
- `app/providers/claude_provider.py`, `app/providers/gemini_provider.py` ←, `app/providers/matcha_provider.py` ← สองไฟล์หลังยังไม่เคย review อ่านทั้งไฟล์ ดูว่า response object ของแต่ละ SDK ให้ usage ตรงไหน
- `app/services/ai/hybrid_flow.py` (จุด `tokens_used=500` hardcode + ทุกจุดเรียก provider)
- `app/services/cost_service.py` ← ยังไม่เคย review — ดูว่าคำนวณจากอะไร ผูกกับตารางไหน
- `app/api/v1/chat.py::_save_history` (จุดเก็บ tokens_used)
- grep: `tokens_used`, `token_count`

---

## F7.1 — Provider รายงาน usage จริงทุก call

**ปัญหา (B9):** `generate_sql_attempt` คืน `tokens_used=500` hardcode เพราะ `generate_content` คืนแค่ text — ตัวเลข token/cost ทั้งระบบใน hybrid mode (default) เป็นค่าปลอม

**Design ที่เลือก:** เพิ่ม attribute `last_usage` บน provider — set หลังทุก API call สำเร็จ อ่านโดย caller ทันทีหลัง call
เหตุผล: ไม่ต้องแตะ signature ของ `generate_content/explain_result` ที่มี caller หลายสิบจุด; provider instance ถูกสร้างใหม่ต่อ request (ยืนยันแล้วใน registry — F2.7 ใส่ comment ไว้) และการเรียกภายใน request เป็น sequential → ปลอดภัย **เขียน docstring กำกับข้อจำกัดนี้ไว้ที่ base class**

1. `providers/base.py`:

```python
@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    model: str = ""

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

class AIProvider(...):
    last_usage: Optional[TokenUsage] = None
```

2. แต่ละ provider set `self.last_usage = TokenUsage(...)` ใน **ทุก** method ที่ยิง API (`generate_content`, `explain_result`, `generate_sql`):
   - Claude: `response.usage.input_tokens / output_tokens / cache_read_input_tokens / cache_creation_input_tokens` (getattr ป้องกัน field ไม่มี)
   - Gemini (google-genai): `response.usage_metadata` — ชื่อ field ตาม SDK เวอร์ชันที่ติดตั้ง (`prompt_token_count`, `candidates_token_count` หรือใกล้เคียง — **ดูจาก SDK จริง อย่าเดา**)
   - Matcha (OpenAI-compatible): `response["usage"]["prompt_tokens"/"completion_tokens"]` — gateway อาจไม่ส่ง usage → default 0 + `logger.debug` ครั้งเดียว
3. reset `self.last_usage = None` ต้นทุก method (กันอ่านค่าค้างจาก call ก่อน)

## F7.2 — hybrid_flow รวม usage จริง

1. `generate_sql_attempt`: หลัง `generate_content` สำเร็จ → `usage = getattr(service.provider, "last_usage", None)` → คืน `usage.total` แทน 500 (None → 0)
2. เก็บ breakdown ต่อ stage: ใน `query_hybrid` สร้าง `usage_log: list[dict]` แล้ว append หลังทุก provider call (stage: `intent`, `sql_gen`, `explain`, attempt no., model, tokens จาก TokenUsage) — ส่งผ่านเข้า `run_hybrid_attempt`/`build_explanation`/`extract_intent` ด้วย parameter (อย่าใช้ global)
3. `providers/base.py::QueryResult` เพิ่ม field ใหม่แบบ optional ท้ายสุด: `usage_breakdown: Optional[List[Dict]] = None` (backward compatible — ตรวจทุกจุดที่ instantiate QueryResult ว่าไม่พังเพราะ positional args)
4. `chat.py::_save_history`: `tokens_used` = ผลรวมจริง (มีอยู่แล้วผ่าน result.tokens_used — แค่ตรวจว่าค่าไหลถูก)
5. อ่าน `cost_service.py` แล้ว wire ให้ใช้ตัวเลขจริง — ถ้า cost_service คำนวณจาก tokens_used เดิมอยู่แล้วก็จบที่ตัวเลขถูกขึ้นเอง; ถ้ามี logic แยก input/output pricing ให้ส่ง breakdown เข้าไป (ตัดสินใจตามโค้ดจริง จดเหตุผล)

## F7.3 — Request trace: log JSON บรรทัดเดียวต่อ query

**ปัญหา:** timing กระจายเป็น `logger.info` หลายบรรทัด (RAG took, SQL Generation took, Execution took, Total...) — อ่าน/aggregate ยาก

**การแก้:** dataclass `QueryTrace` ใน `hybrid_flow.py` (หรือ module ใหม่ `app/services/ai/trace.py`):

```python
@dataclass
class QueryTrace:
    request_id: str
    question_preview: str      # 80 ตัวอักษรแรก — ห้ามเก็บเต็ม (ลด PII ใน log)
    context: str = ""
    provider: str = ""
    attempts: int = 0
    stages: dict = field(default_factory=dict)   # {"rag": 0.12, "intent": 1.4, "sql_gen": 2.1, ...}
    usage: list = field(default_factory=list)    # usage_log จาก F7.2
    cache_hit: bool = False
    error: str = ""
    total_s: float = 0.0
```

- สร้างต้น `query_hybrid` (request_id: ดึงจาก RequestID middleware ถ้าเข้าถึงได้ — เช็ค `app/core/middleware.py` ว่า expose ผ่าน contextvar หรือไม่ ถ้าไม่มีใช้ uuid ใหม่และจดไว้)
- จบ request (สำเร็จ/ล้มเหลว): `logger.info("query_trace %s", json.dumps(asdict(trace), ensure_ascii=False))` **บรรทัดเดียว**
- คง log บรรทัดย่อยเดิมไว้ที่ระดับ `debug` (ลด noise ที่ info)
- QueryEngine level: cache hit ก็ต้อง log trace (stages ว่าง, cache_hit=true) — ย้ายการสร้าง trace ขึ้นไปที่ QueryEngine ถ้าทำได้สะอาดกว่า (ตัดสินใจตอนเขียนจริง จดเหตุผล)

**ไม่ทำในแผนนี้:** เก็บ trace ลง DB, dashboard — รอตัดสินใจ observability platform

## การทดสอบ

- `tests/unit/test_token_usage.py`: mock SDK response ของทั้ง 3 provider ที่มี usage → `last_usage` ถูก populate ครบ field; gateway ไม่ส่ง usage → 0 ไม่ crash
- hybrid flow (mock provider): `QueryResult.tokens_used` = ผลรวม usage ปลอมที่กำหนด (ไม่ใช่ 500), `usage_breakdown` มี stage ครบ
- trace: capture log record → parse JSON ได้ มี key ครบ

## Acceptance Criteria

- [ ] pytest ผ่าน + grep `tokens_used=500` และ `500, None` (จุด hardcode เดิม) = 0
- [ ] Manual: ยิงคำถามจริง 1 ครั้ง → `chat_history.tokens_used` ตรงกับผลรวมใน log trace และ (สำหรับ claude) cache_read ปรากฏใน call ที่สอง
- [ ] Log มี `query_trace {...}` หนึ่งบรรทัดต่อ request, parse เป็น JSON ได้
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md`
