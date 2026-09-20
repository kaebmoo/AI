# RESULT — เก็บช่องโหว่ของช่องทางเดิมก่อนเปิดใช้จริง (ต่อจาก Plan 7 Phase 6)

**สถานะ:** ✅ ข้อ 0–8 เสร็จ — code + test + เอกสาร; **ยังไม่ push**, **ยังไม่แตะ DB จริง** (ทุกอย่างทำบนสำเนา)
**วันที่:** 2026-09-20 | **Branch:** `main` | **เริ่มจาก:** `6751cd6` (ตอนเริ่ม ahead 12; ระหว่างทาง session อื่น push จน `origin/main` = `6751cd6` → ตอนจบ ahead 9 = ของงานนี้ล้วน)
**แผน/คำสั่ง:** `plan/PROMPT_P7_HARDENING.md` (เจ้าของตัดสินทุกข้อไว้แล้ว 2026-09-20)

---

## 0. Baseline และสำรองข้อมูล

- Working tree สะอาดก่อนเริ่ม; ไม่มี rebase / force-push / push
- Backup ด้วย SQLite backup API จาก connection `mode=ro`: `config.db` + `app.db`; `PRAGMA quick_check` = `ok` ทั้งคู่
- Scratchpad: `/private/tmp/nt-ai-hardening-XgaPWR2O/` — `backup/` snapshot ก่อนงาน, `test/` สำเนาสำหรับ pytest,
  `live/` สำเนาสำหรับ server จริง, `manifest.json` = hash ก่อน/หลัง. **ไม่ commit DB / key / log**
- Baseline: `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` → **1035 passed, 3 skipped**
- SHA-256 ของ `app.db` / `config.db` จริง **เท่าเดิมทั้งก่อนและหลัง** baseline

| ไฟล์ | SHA-256 (ก่อน = หลัง) |
|---|---|
| `app.db` | `af348bbb…4b55d9a4` |
| `config.db` | `1c91c756…c4664878` |

---

## 1. REST `/api/v1/query` ไม่ส่งของภายในออกไป — `eafc2e5`

`app/core/outbound.py` (ใหม่) = ชุดคำศัพท์ที่ REST กับ MCP facade ใช้ร่วมกัน: `ERRORS` (code → status + ข้อความตายตัว),
`NO_DATA`, `Refused`, `find`, `code_for`, `result_code`, `explanation_text`, `safe_answer`

| ข้อ | เดิม | ตอนนี้ |
|---|---|---|
| a | 0 แถว → ข้อความมี **SQL เต็ม** (`hybrid_flow.py:313/776`) แม้ `include_sql=false` | `ไม่พบข้อมูลที่ตรงกับเงื่อนไข`; SQL อยู่ใน field `sql` เมื่อขอเท่านั้น |
| b | `answer` / `error` / `parts[].*` มีข้อความ exception (path, ชื่อตาราง) | รหัส + ข้อความตายตัว; เหตุผลจริงอยู่ใน log + `query_audit.error` |
| b | `SourceUnavailable` มี path ของ DataFeed ในข้อความ | `source_unavailable` — ความหมายเดิม ("ข้อมูลอาจกำลังถูก publish") ไม่มี path |
| c | explanation เป็น dict → `str(dict)` (chart config ติดไปด้วย) | ข้อความอย่างเดียว |
| d | เกินโควตา = **401** (ตกไปหา session auth) | **429** + ข้อความตายตัว; `APIKeyService.check_key` แยก "key ใช้ไม่ได้" ออกจาก "เกิน limit" |

- `multi_context.Part` ได้ `error_code` (+ property `code` ที่ fallback เป็น `query_failed`) — ข้อความจริงของ part
  ยังอยู่ใน `part.error` สำหรับ audit/log ส่วน `combine()` เขียนข้อความตายตัว
- `mcp_facade._answer` เหลือเฉพาะของ MCP จริง ๆ: failure = tool error, ทิ้งผลที่ `llm_policy ≠ full`, cap ต่อ ask,
  ด่านสุดท้าย (เดิมตรวจ SQL) ตอนนี้ตรวจ**ข้อความ error ของ part ด้วย** และ **ปฏิเสธทั้งก้อน** แทนการแก้ข้อความ
- `validate_key` พฤติกรรมเดิมทุกบรรทัด (`return check_key(raw)[0]`)

## 2. `GET /api/v1/query/contexts` ต้อง auth — `ac2246c`

- ไม่มี credential / key ใช้ไม่ได้ / เจ้าของถูกปิด = **401** (เดิม: key ผิด → `allowed_contexts(None)` = เห็นทุก context ทุก workspace)
- key ที่ผูก workspace เห็นเฉพาะของตัวเอง; session user เห็นทั้งหมดตามเดิม
- ใช้ `authenticate` ไม่ใช่ `validate_key` → **ไม่นับโควตา ไม่ขยับ counter** (ยืนยันด้วย test: `usage_today == 0`)
- **สำรวจผู้เรียก:** ไม่มี runtime caller ใน repo นี้ — frontend ใช้ `/chat/contexts`, frontend-admin ใช้ `/admin/contexts`,
  telegram/OpenMiniCrew ไม่เรียก, NT-Report hook ไม่เรียก. แก้เฉพาะ `README.md` (curl ตรวจหลัง deploy) ให้ส่ง key

## 3. Claude Desktop ต่อ facade ผ่าน stdio bridge — `0ff2112` (+ `0c61c09`)

- `scripts/mcp_stdio_bridge.py` — stdio ↔ `POST /api/v1/mcp` ด้วย MCP SDK ที่มีอยู่แล้ว (**ไม่ลง npm package**)
  - tool มาจากที่ server ประกาศ (ไม่ hardcode — test ตรวจว่าชื่อ tool ไม่ปรากฏใน source ของ bridge)
  - tool error ส่งต่อทั้งก้อน → ใช้ raw handler ของ `CallToolRequest` เพราะ `@server.call_tool()` จะประกอบผลใหม่เป็น
    `isError=False` และแปลง exception เป็นข้อความของตัวเอง
  - key จาก `NT_AI_API_KEY`, URL จาก `NT_AI_BASE_URL`; ไม่เก็บ ไม่ log ไม่อยู่ในข้อความ error
  - 401 / flag ปิด / ต่อไม่ติด = จบ process ด้วยบรรทัดเดียวที่อ่านออกบน stderr (exit 1)
- ลบ `mcp_servers/claude_desktop_config.json`; README ของ `mcp_servers/` ชี้ไป bridge; ตัวอย่าง config อยู่ในคู่มือ
  (`command` = python ของ venv, `args` = path ของ bridge, `env` = ชื่อตัวแปร — **ไม่มี key จริงในไฟล์ตัวอย่าง**)
- `User-Agent` ของ bridge = `nt-ai-stdio-bridge/1.0` → audit `channel = mcp:nt-ai-stdio-bridge/1.0`
  (ไม่งั้นอ่านว่า `mcp:python-httpx/0.28.1`); **client ที่อยู่หลัง bridge แยกไม่ได้** — ตัวที่ระบุ installation คือ key
- ทดสอบ: 10 unit test (bridge ↔ facade จริงผ่าน ASGI) + รัน bridge เป็น **subprocess จริง** กับ server บนสำเนา DB
- ⏳ **ค้างให้เจ้าของ:** เสียบ Claude Desktop จริง — snippet อยู่ใน §9 (ห้ามแก้ไฟล์ config ของผู้ใช้เอง)

## 4. `ai_response` หมดอายุตาม `result_retention_days` — `cfece77` (+ `0c61c09`)

- `retention.EXPIRED_ANSWER` = `คำตอบหมดอายุตามนโยบายการเก็บข้อมูล — ถามใหม่ได้`; แถวที่**ไม่เคยมีคำตอบ**ยังเป็น `NULL`
- นาฬิกาเดียวกับแถวผลลัพธ์: override ต่อ workspace ใช้ได้, `days=0` = ไม่ลบ, idempotent
- คำถาม / SQL / `render_meta` / `query_audit` อยู่ครบ
- **สำรวจผู้อ่าน `ai_response`:** history ที่ส่งให้ LLM (`chat.py::_get_conversation_history`) — **ข้าม**คำตอบที่หมดอายุ
  และไม่สร้าง assistant turn ว่าง; feedback / conversations / admin analytics / export = ข้อความ placeholder แสดงได้ตามปกติ;
  DSR ลบทั้งแถวอยู่แล้ว
- **ตัวเลขบนสำเนาสดของ `app.db` จริง (2026-09-20):**

  | | จำนวน |
  |---|---|
  | `chat_history` ทั้งหมด | 1,513 (แถวใหม่สุด 2026-07-14 — เก่ากว่า 30 วันทั้งหมด) |
  | เดิมโดนล้าง `result_data` อยู่แล้ว | 1,285 |
  | คำตอบที่จะกลายเป็น placeholder | 1,513 |
  | แถวที่งานนี้แตะเพิ่มจากของเดิม | 228 |
  | คำถามที่ยังอยู่ / SQL ที่ยังอยู่ | 1,513 / 1,511 |
  | purge รอบสอง | 0 แถว (idempotent) |

  ⚠️ **ย้อนกลับไม่ได้** — backup ที่มีอยู่: `~/nt-ai-backups/pre-migrate-20260920/`; ให้ backup สดอีกครั้งก่อน start server จริง

## 5. audit เขียนไม่ได้ = ไม่ส่งคำตอบออก (เฉพาะช่องทางที่ถือ key) — `f5b56be` (+ `ca71357`)

- `query_audit.record()` คืน `bool` (ยัง **never raises** → ผู้เรียกเดิมไม่เปลี่ยนพฤติกรรม); `AuditUnavailable` เป็น exception ใหม่
- `QueryEngine.query`: เขียนไม่สำเร็จ **และ** มี `api_key_id` → raise; cache hit อยู่ใต้กติกาเดียวกัน
- multi-context: แถวแม่หรือแถวลูกหายไปแถวเดียว = ทั้งคำถามไม่ออก
- REST = **503** + ข้อความตายตัว, MCP = tool error `audit_unavailable`; chat / telegram / session user = fail-open ตามเดิม + ERROR ใน log
- ⚠️ trade-off ที่ยอมรับ: audit เขียน**หลัง**คำถามรันแล้ว → 503 เกิดหลังจ่าย provider call และนับโควตาไปแล้ว (ไม่มี retry loop, ไม่นับซ้ำ)
- ทดสอบด้วย app DB ที่**เขียนไม่ได้จริง** (ไฟล์ read-only) และตาราง `query_audit` ที่สร้างไม่ได้

## 6. Review อิสระ (agent แยก อ่านอย่างเดียว) — 3 มุม, code review ของข้อ 1, 2, 5

| มุม | ผล |
|---|---|
| ข้อ 1 (สิ่งที่ REST คืน) | **1 critical** — แก้แล้วใน `f884e44` |
| ข้อ 2 (auth ของ `/contexts`) | ไม่พบช่องโหว่; 1 เอกสารค้าง (แก้แล้ว) + 1 ข้อสังเกต (ตั้งใจ) |
| ข้อ 5 (audit fail-closed) | **2 finding** — แก้แล้วใน `ca71357` |

**สิ่งที่แก้ตาม review:**

| ระดับ | Finding | แก้ |
|---|---|---|
| **critical** | body ของ 400 / 403 ยังสร้างจาก `str(exception)`: ชื่อคอลัมน์ scope ที่ context รองรับ, `scripts/migrate_data_sources.py` เมื่อ config DB ยังไม่ migrate, ชื่อ source + `llm_provider_allowlist`, และ `ContextNotAllowed` สองสำนวน = **existence oracle** | status เดิม (portal branch ที่ 400) + ข้อความตายตัวจากตารางร่วม + log เหตุผลจริง (`f884e44`, +5 test) |
| medium | `raise AuditUnavailable` อยู่ใน `try` ที่ audit failure ด้วย → ยิงเขียนซ้ำใส่ DB ที่เพิ่งปฏิเสธ (รอ lock สองรอบ, คูณจำนวน part) | re-raise ทันที ไม่เขียนซ้ำ (`ca71357`) |
| medium | `ensure_table` เป็น check-then-act บน set ระดับ process; สองคำขอพร้อมกันบนตารางก่อน Phase 5 → `ALTER TABLE ADD COLUMN` ซ้ำ (SQLite ไม่มี `IF NOT EXISTS`) → ผู้แพ้ได้ 503 | `threading.Lock` + re-check ข้างใน (`ca71357`) |
| ข้อสังเกต — ไม่แก้ | `_may_list` ไม่ fall back ไป session auth เมื่อส่ง key ที่ใช้ไม่ได้มาด้วย (ต่างจาก `get_current_user`) | ตรงกับข้อตัดสิน "key ผิด = 401" และเข้มกว่า ไม่ใช่หลวมกว่า |
| ข้อสังเกต — ไม่แก้ | 429 ใน `get_current_user` มีผลกับทุก endpoint และมาก่อน `enforce_key_surface` | ตั้งใจ — key ที่หมดโควตาไม่ใช่ "ไม่ได้ login"; ไม่มีผู้เรียกใน repo ที่พึ่ง fallback เดิม |
| ข้อสังเกต — ไม่แก้ | `MCP_MAX_ROWS < 4` ทำให้ยอดรวมแถวเกิน cap เล็กน้อย (floor + `max(1,…)` ต่อ part) | config ที่ไม่มีจริง; ค่าปัจจุบัน 100 |

ที่ผู้ตรวจไล่แล้วผ่าน (ตัวอย่าง): chat / telegram ไม่ได้รับผลกระทบ (ไม่ import `outbound` / `multi_context`);
`result_code` ไม่มีทางชนกับ error string จริงของ engine; `Part.code` ไม่รายงาน part ที่ว่างเป็น failure;
`allowed_contexts` fail closed ทุกทาง (JSON พัง / config DB ล่ม / workspace ปิด / workspace_id ชี้แถวที่ไม่มี);
401 ของ dependency ไม่ถูกกลืนโดย `try/except` ของ endpoint; `record()` ใช้ session แยก — `rollback` ของผู้เรียกไม่ล้ม commit ที่ลงแล้ว;
`api_key_id` ถูกส่งเฉพาะจาก REST-with-key และ facade เท่านั้น (chat / telegram / eval / report worker ไม่ส่ง)

## 7. ตรวจของจริงหลังแก้ (server บนสำเนา DB — ไม่แตะ DB จริง)

`.claude/launch.json` entry ชั่วคราว `backend-hardening` (port 8011, env ชี้ไป `live/`, `TELEGRAM_BOT_TOKEN=`) — **ลบออกแล้ว**
flag `mcp_external_enabled` + `multi_context_workspaces` เปิดบน**สำเนา**; key ทดสอบผูก workspace `nt-report` (ออกบนสำเนา)

| ตรวจ | ผล |
|---|---|
| start server | ขึ้นครบ (MCP ภายใน 3 ตัว + scheduler + session manager) |
| retention job รอบแรก (สำเนา) | `chat_history` 1,513 · `chat_session_data` 55 · รอบสอง 0 |
| `source_status` ทุก context | `feed_revenue` 202608 v2.3.0 · `feed_expense` 202608 v1.2.0 · `feed_sales` 202608 v1.3.0 · `feed_ebt` 202607 v1.4.0 — ok ทั้งหมด |
| smoke REST 1 คำถาม/context | 3,434.07 / 3,690.47 / 3,480.99 / 417.33 ล้านบาท — ไม่มี SQL, ไม่มี path ใน response |
| smoke MCP | ตอบได้, `context_not_allowed` เมื่อขอ context นอกสิทธิ์ |
| 0 แถว (REST + MCP) | `ไม่พบข้อมูลที่ตรงกับเงื่อนไข` ทั้งสองช่องทาง, `sql = null`, ไม่มี ```` ```sql ```` |
| `GET /query/contexts` | ไม่มี auth = **401** · key ผิด = **401** · key จริง = `feed_revenue, feed_expense, feed_sales, feed_ebt` |
| scope ที่ context ไม่ประกาศ | **400** + ข้อความตายตัว (ไม่บอกชื่อคอลัมน์ที่รองรับ) |
| context นอกสิทธิ์ vs ไม่มีอยู่ | **403** ข้อความ**เดียวกัน** — existence oracle ปิด |
| scope ที่ถูกต้อง | ตอบได้ตามปกติ (202607) |
| audit | `hardening-check` 11 แถว (3 เป็น refusal), `mcp:nt-ai-stdio-bridge/1.0`, `mcp:python-httpx/0.28.1`; เหตุผลจริง (`ScopeError: scope ไม่รู้จัก ['division']`) อยู่ใน `query_audit.error` |
| bridge เป็น subprocess จริง | `tools/list` = 3 ชื่อ · `list_contexts` = 4 context · refusal ส่งต่อทั้งก้อน · `ask` ตอบได้ · ไม่มี SQL/path |
| bridge key ผิด | exit 1 + `nt-ai bridge: API key ใช้ไม่ได้ — ตรวจค่า NT_AI_API_KEY …` |
| eval `feed_revenue` (5 ข้อ) | value_match 5/5 (รัน 2 ครั้ง) |
| eval cross-domain (10 ข้อ) | **ก่อนแก้ (worktree ที่ `6751cd6`, DB เดียวกัน, วันเดียวกัน): 8/10** · หลังแก้: **8 / 6 / 9** — LLM noise, ทุก failure เป็นการ generate SQL (เช่น ตีความ "เดือนล่าสุด" เป็นเดือนปัจจุบัน) ไม่ใช่ envelope/auth; diff ไม่แตะ prompt / routing / SQL |

pytest หลังงานทั้งหมด: **1077 passed, 3 skipped** (baseline 1035 → +42)

## 8. Test ที่แก้เพราะเจ้าของสั่งเปลี่ยนพฤติกรรม

| ไฟล์ | test | เหตุผล |
|---|---|---|
| `tests/unit/test_multi_context.py` | `test_a_failed_part_is_said_and_nothing_is_computed` | `combine()` ไม่อ้างข้อความของ engine อีก |
| `tests/unit/test_multi_context.py` | `test_a_failed_sub_question_is_reported_not_guessed` | ข้อความ exception ไม่อยู่ในคำตอบ |
| `tests/unit/test_mcp_facade.py` | `test_a_failed_part_of_a_multi_context_answer_keeps_its_reason_inside` | ด่านสุดท้ายปฏิเสธทั้งก้อนแทนการแก้ข้อความ |
| `tests/unit/test_mcp_facade.py` | `test_parts_a_failed_one_with_a_result_an_empty_one_and_the_row_cap_per_ask` | ข้อความที่ `combine()` ผลิตเป็นข้อความตายตัวแล้ว |
| `tests/unit/test_workspace_keys.py` | `test_the_403_survives_the_auth_dependency` | dependency เรียก `check_key` (mock plumbing ไม่ใช่พฤติกรรม) |
| `tests/unit/test_workspace_keys.py` | `test_restricted_key_lists_only_what_it_can_use` | `/contexts` ไม่ public แล้ว (+เพิ่ม test key ใช้ไม่ได้ = 401) |
| `tests/unit/test_simple_query.py` | `test_contexts_list` | เดิม pin "public, no auth needed" |
| `tests/integration/test_query_endpoint.py` | `test_query_contexts_public` | เดิม pin public |
| `tests/unit/test_retention.py` | `test_purge_drops_old_rows_keeps_metadata_and_is_idempotent` | เดิม pin "คำตอบอยู่ครบ" |

## 9. ⏳ ค้างให้เจ้าของ — snippet ของ Claude Desktop

ห้ามให้ผมแก้ไฟล์ config ของผู้ใช้ — วางเองที่ `~/Library/Application Support/Claude/claude_desktop_config.json`
แล้ว**ปิด-เปิด Claude Desktop ใหม่** (ใส่ key จริงแทน `ntai_...`; ถ้าไม่มีคีย์ `mcpServers` อยู่แล้วให้ใส่ทั้งก้อน):

```json
{
  "mcpServers": {
    "nt-ai": {
      "command": "/Users/seal/Documents/GitHub/AI/venv/bin/python",
      "args": ["/Users/seal/Documents/GitHub/AI/scripts/mcp_stdio_bridge.py"],
      "env": {
        "NT_AI_API_KEY": "ntai_...",
        "NT_AI_BASE_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

ตรวจก่อนเสียบ: `NT_AI_API_KEY=ntai_... venv/bin/python scripts/mcp_stdio_bridge.py` — ต้องค้างเงียบ ๆ (ถ้า key ผิด /
flag ปิด / server ไม่ขึ้น จะจบทันทีพร้อมเหตุผล). ⚠️ ตัวเลขที่ตอบไปถึงโมเดลของ Anthropic เหมือน Claude Code —
บนของจริงให้ใช้ key ที่ผูก workspace เดียวและ revoke ได้

## 10. ข้อค้าง (ไม่ได้ทำในงานนี้)

- **ยังไม่ push** — 9 commit ของงานนี้ (`origin/main` ขยับไป `6751cd6` ระหว่างทางด้วย push จาก session อื่น = จุดเริ่มของงานนี้พอดี จึงเหลือ ahead 9); **ยังไม่แตะ DB จริง**: ไม่ได้เปิด flag, ไม่ได้ออก key จริง,
  ไม่ได้ start server ด้วย DB จริง (รอบแรกจะล้างตาม §4)
- Redis ยังไม่รัน → limit รายนาที fail-open (ของเดิม)
- CORS เปิดทั้งแอปใน `app/main.py` ขณะที่เอกสารเขียนว่าไม่เปิด — **เจ้าของยังไม่ตัดสิน** (อยู่นอกขอบเขตงานนี้)
- REST ยังไม่ตรวจ `has_scope('query')` (ของเดิม; MCP ตรวจ)
- `error` ระดับบนของคำถามข้าม context ยังเป็นสรุปคำเตือน ไม่ใช่รหัส (ข้อความของเราเอง ไม่ใช่ของ engine)
- Admin UI ของ workspaces / sources / policy / retention / audit / flag — ยังมีแต่ API

## 11. Commits

`eafc2e5` REST ไม่ส่งของภายใน · `ac2246c` `/contexts` ต้อง auth · `0ff2112` stdio bridge + ลบ config เดิม ·
`cfece77` `ai_response` หมดอายุ · `f5b56be` audit fail-closed · `0c61c09` สองข้อที่เจอตอนรันจริง ·
`f884e44` review: body ของ refusal · `ca71357` review: audit เขียนซ้ำ + race ของ `ensure_table` · (ถัดไป) เอกสาร
