# Plan 7 Phase 6 — MCP สำหรับผู้เรียกภายนอก (2026-09-20)

แผน: `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 6 (รวม Plan 1B-C / REMAIN-8) · ผล + ตารางสำรวจ + review: `plan/archive/RESULT_P7_PHASE6.md` · คู่มือ: `docs/manuals/manual_mcp_external.md`

## สิ่งที่เพิ่ม

| เรื่อง | ก่อน | หลัง (เมื่อเปิด) |
|---|---|---|
| MCP client ภายนอก (Claude Code, Gemini CLI, Codex CLI, โปรแกรมที่ใช้ MCP SDK) | ไม่มีช่องทาง — MCP ภายใน 35 tools เป็น stdio หลัง pipeline (SQL ดิบ / ค่าจริง / admin writes; ไม่มี key, allowlist, scope, audit) | `POST /api/v1/mcp` — stateless Streamable HTTP ใน FastAPI เดิม, `X-API-Key` **ทุก request**, 3 tools: `ask(question, context?, scope?, include_data?)`, `list_contexts()`, `source_status(context)` |
| ทางเข้าของคำถาม | `POST /api/v1/query` | REST กับ MCP เรียก `run_simple_query` ตัวเดียวกัน → `multi_context.ask` → `QueryEngine.query` (scope / allowlist / pinned / policy / cache / audit / คำถามข้าม context ตามเดิม) |
| สิ่งที่คืนให้ client | — | `answer`, `context`, `row_count`, `execution_time_ms`, `data_as_of`, `data` (เมื่อขอ, ไม่เกิน `MCP_MAX_ROWS` ต่อ ask), `parts[]` + `computed` — **ไม่มี SQL / ข้อความ exception / path ในทุกกรณี**; ไม่พบข้อมูล / part ที่ล้ม = ข้อความตายตัว |
| การปฏิเสธ | — | key ใช้ไม่ได้ = HTTP 401 ทุก request; ที่เหลือเป็น tool error (`isError=true`) `{code, http_status, message, request_id}`: `rate_limited`, `invalid_scope`, `context_not_allowed`, `policy_refused`, `invalid_arguments`, `duplicate_request`, `source_unavailable`, `query_failed`, `internal_error` |
| source ที่ `llm_data_policy` ≠ `full` | — | **ไม่มีอยู่บนช่องทางนี้**: ไม่อยู่ใน `list_contexts`, ระบุชื่อ = `policy_refused`; registry ยังไม่ migrate / อ่าน policy ไม่ได้ = ปฏิเสธทุก context |
| audit | — | `query_audit.channel = mcp:<user-agent ของ client>` (เช่น `mcp:claude-code/2.1.270`) |

Legacy SSE **ไม่ทำ** (client ที่ตรวจไม่ต้องใช้); MCP ภายในยังเป็น stdio ไม่ถูกเปิดออก / ไม่มี passthrough; embeddable widget **ไม่ทำ** (ไม่มี client ที่ 2)

**ปิดเป็นค่าเริ่มต้น** — endpoint ตอบ 404 จนกว่า admin จะเปิด flag (ไม่ต้อง deploy ใหม่):
```bash
curl -X POST "http://localhost:8000/api/v1/admin/config/features/mcp_external_enabled/toggle?enabled=true" \
  -H "X-Session-Token: <admin session>"
```
ก่อนเปิดกับ DB จริง (ยังไม่ได้ทำ ณ 2026-09-20): (1) รัน `scripts/migrate_data_sources.py` + `scripts/migrate_workspaces.py` บน `config.db` จริง — ไม่มีคอลัมน์ `llm_data_policy` = MCP ปฏิเสธทุก context
(2) ออก key ที่**ผูก workspace / allowlist** + scope `query` / `full`, ตั้ง `MCP_ALLOWED_HOSTS` ถ้าไม่ได้เรียกผ่าน localhost (3) รัน Redis — ไม่มี = limit รายนาที fail-open. ต่อ client: ดูคู่มือ §3

## Settings / flag
- `admin_config.mcp_external_enabled` (feature flag, default ปิด = 404) — อยู่ใน `get_feature_flags`
- `.env`: `MCP_ALLOWED_HOSTS` (Host นอกรายการ = 421), `MCP_ALLOWED_ORIGINS` (ว่าง = request ที่มี `Origin` ถูกปฏิเสธ 403 ทั้งหมด), `MCP_MAX_ROWS` (default 100)

## ขอบเขตที่บังคับ
gate ทุก HTTP request หน้า transport (stateless ไม่ต้อง `initialize`) · key ต้องผูก workspace / allowlist + scope `query` / `full` + เจ้าของ active; `X-API-Key` มากกว่าหนึ่งตัว = 401 ·
GET / DELETE = 405 · context ของช่องทางนี้ต้องอยู่ใน workspace ที่ active · policy `full` เท่านั้น (ตัวอ่านแบบเข้ม + ตรวจ `llm_policy` ของผลลัพธ์และทุก part ซ้ำก่อนส่งออก) ·
1 tool call = 1 usage ตัวนับเดียวกับ REST (handshake ไม่นับ) · facade ไม่มี provider call ของตัวเอง ไม่แตะ ContextVar — รายละเอียด + threat model: `docs/DEPLOYMENT_SECURITY.md`

## พฤติกรรมของ code เดิมที่เปลี่ยน
- `APIKeyService.track_usage` → **upsert อะตอมมิกคำสั่งเดียว** (เดิม read-modify-write: ยิงพร้อมกัน 30 call นับได้ 3–6, เกินโควตารายวัน, `IntegrityError` แถวแรกของวัน) — มีผลกับ REST ด้วย
- `APIKeyService.authenticate` (ใหม่) = ครึ่งที่ไม่มี side effect ของ `validate_key`; `validate_key` พฤติกรรมเดิม
- `/api/v1/query`: `source` ที่ขึ้นต้นด้วย `mcp` ถูกบันทึกเป็น `api:mcp…` — REST เขียน audit channel `mcp…` ไม่ได้; สัญญาอื่นของ REST ไม่เปลี่ยน (test เดิม 71 ข้อผ่านโดยไม่แก้)
- `GET /admin/query-audit?channel=mcp` จับ prefix `mcp:` (เจอทุก `mcp:<client>`)
- `deps.enforce_key_surface` รู้จัก `/api/v1/mcp` — key ที่ผูก workspace / allowlist ใช้ได้ที่ `/api/v1/query*` และ `/api/v1/mcp` เท่านั้น
- `.gitignore`: `chroma_db__*/` (Vanna brain ต่อ workspace เกิดใน root ของ repo เมื่อมีคำถามแรกของ workspace)

ที่**ไม่ได้แก้** (พฤติกรรมของ REST เดิม — รอเจ้าของ, RESULT §9): REST ยังคืน SQL ในข้อความคำตอบเมื่อได้ 0 แถว และข้อความ exception ใน `answer` / `error` / `parts[].error`; `GET /api/v1/query/contexts` เป็น public; REST เกินโควตา = 401 (คู่มือเขียน 429); REST ไม่ตรวจ scope `query`

## ตัวเลข
- pytest **1035 passed, 3 skipped** (baseline 997 / 3; +38 ใน `tests/unit/test_mcp_facade.py` — MCP SDK client จริงผ่าน ASGI บน DB ชั่วคราว); รันบนสำเนา DB, SHA-256 ของ `config.db` / `app.db` จริงเท่าเดิม
- Client จริง: **Claude Code 2.1.270** บนสำเนา DB — `list_contexts` → `feed_*` 4 ตัว; `source_status feed_sales` → ok / 202608 / schema 1.3.0; `ask` (LLM จริง) ตอบได้; `source_status revenue` → `context_not_allowed`
- Latency เส้นทาง cache (n=12): REST P50 12.9 / P95 17.6 ms — MCP P50 19.5 / P95 29.0 ms → overhead +6.6 / +11.4 ms (เป้า ≤100 ms); คำตอบแรก LLM จริง: REST 7.4 s, MCP 8.1 s (คนละคำถาม)
- Review อิสระ: high 2 (SQL ใน explanation เมื่อ 0 แถว; ข้อความ exception / SQL ใน `parts[].answer`), medium 2, low 4 — แก้ครบใน `69d896a`; low 1 ข้อบันทึกไว้ไม่แก้ (SDK ตอบ argument ผิดชนิด / ชื่อ tool ที่ไม่มี ก่อนถึง tool); mutation check 10 mutant: ฆ่า 7, เทียบเท่า 2, รอด 1 → เพิ่ม test แล้ว

## ไฟล์หลัก
- `app/api/v1/mcp_facade.py` (ใหม่) — `Gate` (ASGI หน้า transport), `authenticate` → `Principal`, `full_policy_contexts` (ตัวอ่าน policy แบบเข้ม), 3 tools, `build()` (FastMCP + ASGI app คู่ใหม่ต่อ app)
- `app/api/v1/query.py` — `run_simple_query`, `contexts_for`, `_rest_channel`
- `app/services/api_key_service.py` — `authenticate`, `track_usage` (upsert)
- `app/api/deps.py` — `enforce_key_surface`; `app/config.py` — `MCP_*`; `app/services/admin_config_service.py` — flag; `app/api/v1/admin/analytics.py` — filter `channel` แบบ prefix
- `app/main.py` — `Route(mcp_facade.PATH, …)` (ไม่ใช่ mount — ไม่มี 307) + `session_manager.run()` ใน lifespan
- `scripts/mcp_client_example.py` — ตัวอย่าง client (MCP SDK) + ตัววัด latency (`list` / `status` / `ask` / `bench`)
- `tests/unit/test_mcp_facade.py`, `tests/unit/test_query_audit.py`
- เอกสาร: `docs/manuals/manual_mcp_external.md`, `docs/DEPLOYMENT_SECURITY.md`, `docs/manuals/manual_api_keys.md`, `mcp_servers/README.md` (คำเตือน: server ภายในห้ามต่อ client ภายนอก)

Commits: `8d67523` สำรวจ · `f868b91` ทางเข้าร่วม REST/MCP · `fd67d07` facade + gate · `2bcd120` ตัวอย่าง client + latency · `69d896a` แก้ตาม review
