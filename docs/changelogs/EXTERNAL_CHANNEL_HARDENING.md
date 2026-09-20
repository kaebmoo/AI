# Hardening ของช่องทางเดิมก่อนเปิดใช้จริง (2026-09-20)

คำสั่ง: `plan/PROMPT_P7_HARDENING.md` (เจ้าของตัดสินทุกข้อ) · ผล + review + ตัวเลข: `plan/archive/RESULT_P7_HARDENING.md`
เอกสารสำหรับผู้เรียก: `docs/PORTAL_INTEGRATION.md` (ตาราง status code) · `docs/DEPLOYMENT_SECURITY.md` · `docs/manuals/manual_api_keys.md` · `docs/manuals/manual_mcp_external.md`

Phase 6 สร้าง MCP facade ที่ไม่ส่งของภายในออกไปเลย แล้วพบว่า **ช่องทางเดิม (`POST /api/v1/query`) ยังส่งอยู่** — งานนี้คือการทำให้ทั้งสองช่องทางใช้กติกาเดียวกัน
**chat / telegram / MCP ภายในแบบ stdio ไม่เปลี่ยน** — ที่นั่นผู้ใช้ยังเห็น SQL และ error จริง

## สิ่งที่เปลี่ยน

| เรื่อง | ก่อน | หลัง |
|---|---|---|
| คำตอบที่ได้ 0 แถว | ข้อความมี **SQL เต็ม** แม้ `include_sql=false` | `ไม่พบข้อมูลที่ตรงกับเงื่อนไข`; SQL อยู่ใน field `sql` เมื่อขอเท่านั้น |
| คำถามที่ล้ม | `answer` / `error` / `parts[].error` เป็นข้อความ exception (path, ชื่อตาราง) | **รหัส + ข้อความตายตัว** (`query_failed` · `source_unavailable` · `duplicate_request` · `internal_error`); เหตุผลจริงอยู่ใน log + `query_audit.error` |
| body ของ 400 / 403 | `str(exception)` — ชื่อคอลัมน์ scope ที่ context รองรับ, `scripts/migrate_data_sources.py`, ชื่อ source + `llm_provider_allowlist` | ข้อความตายตัว; status เดิม; **context นอกสิทธิ์ = context ที่ไม่มีอยู่** (ปิด existence oracle) |
| explanation ที่เป็น dict | `str(dict)` (chart config ติดไปด้วย) | ข้อความอย่างเดียว |
| เกิน rate limit / โควตา | **401** (ตกไปหา session auth) | **429** + ข้อความตายตัว |
| `GET /api/v1/query/contexts` | public — key ผิด = เห็นทุก context ของทุก workspace | ต้องมี key หรือ session token (401); key ผูก workspace เห็นเฉพาะของตัวเอง; **ไม่นับโควตา** |
| `chat_history.ai_response` | เก็บตลอดไป ขณะที่แถวผลลัพธ์หมดอายุใน 30 วัน | หมดอายุตาม `result_retention_days` เดียวกัน → ข้อความตายตัว; คำถาม / SQL / metadata / audit อยู่ครบ; ไม่ถูกส่งเข้า LLM เป็นบริบทของคำถามต่อเนื่อง |
| `query_audit` เขียนไม่ได้ | ERROR ใน log แล้วส่งคำตอบต่อ | ผู้เรียกที่ถือ API key (REST + MCP): **503** / tool error `audit_unavailable` และไม่มีคำตอบออกไป (NIST AU-5); chat / telegram / session user = ตามเดิม |
| Claude Desktop | `mcp_servers/claude_desktop_config.json` ต่อ `nt-query` = SQL ดิบ ไม่มี key / allowlist / scope / audit | ไฟล์ถูกลบ; ต่อผ่าน `scripts/mcp_stdio_bridge.py` → `/api/v1/mcp` (ตัวแปลง stdio↔HTTP ล้วน, key จาก env, กติกาอยู่ฝั่ง server) |

## ของใหม่ในโค้ด

- `app/core/outbound.py` — ชุดคำศัพท์ร่วมของช่องทางที่ตอบผู้เรียกนอก process: `ERRORS` (code → status + ข้อความ),
  `NO_DATA`, `Refused`, `code_for()`, `result_code()`, `safe_answer()`. **ช่องทางขาออกใหม่ต้องใช้ตัวนี้ ไม่สร้างชุดที่สอง**
- `APIKeyService.check_key()` — `validate_key` ที่บอกเหตุผล (`unauthorized` / `rate_limited`); `validate_key` เป็น wrapper เดิม
- `query_audit.record()` คืน `bool` (ยัง never raises) + `AuditUnavailable`; `ensure_table` มี lock แล้ว
- `multi_context.Part.error_code` / `.code` — ข้อความจริงอยู่ใน `.error` (audit/log), รหัสคือสิ่งที่ส่งออก
- `retention.EXPIRED_ANSWER`
- `scripts/mcp_stdio_bridge.py` (+ `mcp_servers/claude_desktop_config.json` ถูกลบ)

## ตัวเลข

- pytest **1077 passed, 3 skipped** (baseline 1035 → +42 test ใหม่ ทุกตัว fail บน code เดิม)
- ตรวจของจริงบนสำเนา DB: source ทั้ง 4 ok, smoke 1 คำถาม/context ทาง REST + MCP, 0 แถวไม่มี SQL ทั้งสองช่องทาง,
  `/query/contexts` ไม่มี auth = 401, 403 ของ context นอกสิทธิ์ = ของ context ที่ไม่มีอยู่
- eval: `feed_revenue` 5/5 value_match; cross-domain 6–9/10 — **แกว่งระหว่างรันด้วย code เดียวกัน**
  (worktree ก่อนแก้ วันเดียวกัน DB เดียวกัน = 8/10) ไม่ใช่ regression
- retention รอบแรกบนสำเนาของ `app.db` จริง: `chat_history` 1,513 แถว, `chat_session_data` 55; รอบสอง 0 (idempotent);
  คำถาม 1,513 และ SQL 1,511 อยู่ครบ

## Review อิสระ (agent แยก อ่านอย่างเดียว)

3 มุม (สิ่งที่ REST คืน / auth ของ `/contexts` / audit fail-closed) — แก้ 3 finding: body ของ 400·403 ยังเป็น
`str(exception)` (critical), การเขียน audit ซ้ำใส่ DB ที่เพิ่งปฏิเสธ, และ race ของ `ensure_table` ที่ `ALTER TABLE` ซ้ำ
