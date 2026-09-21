# Deployment Security Notes

## Business DB — Read-only Enforcement (F4.1, 2026-07-11)

### SQLite (dev / current)

MCP servers (`nt_query_mcp`, `nt_metadata_mcp`) open the business DB with
`mode=ro` at the connection level. Writes fail with
`attempt to write a readonly database` even if regex validation is bypassed.

- The DB file **must exist** before the MCP server starts (fail-loud by design).
- WAL mode is supported as long as the `-wal`/`-shm` files are readable.
- `immutable=1` is intentionally NOT used — ETL updates the file while the app runs.

Note: the app-side SQLAlchemy `business_engine` is NOT read-only because the
admin view-manager feature legitimately creates/drops views in the business DB
(see `app/services/schema/view_manager.py`). See `plan/FIX_NOTES.md`.

### MSSQL (production)

Read-only enforcement happens at the **credential level** — the login used for
the business DB connection string must have `SELECT` only (`db_datareader`
role, no `db_datawriter`/`db_owner`). The query MCP server logs a one-line
reminder at startup when `engine=mssql`.

## Plan 7 — file sources, scope, workspace keys (2026-09-19)

- **Upgrade:** รัน `python scripts/migrate_data_sources.py` และ `python scripts/migrate_workspaces.py` (idempotent) — คอลัมน์ใหม่ของ `api_keys` app เติมเองตอน lookup ครั้งแรก แต่ฝั่ง config DB ต้องรัน script
- **File source (DuckDB):** read-only, `allowed_paths` = ไฟล์ของ build, `enable_external_access=false`, `lock_configuration=true`, SQL จาก LLM ผ่าน query gate (`check_select`) เสมอ — ห้ามผ่อน
- **`DATA_SOURCE_ALLOWED_ROOTS`** (.env, คั่นด้วย `,`; ค่าเริ่มต้นว่าง): directory ที่ `POST /admin/sources/register` อ่าน bundle **ใหม่**ได้ (เทียบด้วย realpath) — ว่าง = API ลงทะเบียนซ้ำได้เฉพาะโดเมนที่ลงไว้แล้ว; CLI ไม่ถูกจำกัด. เป็นค่าใน .env โดยตั้งใจ (ขอบเขตความปลอดภัยของ admin API เอง ไม่ให้แก้ผ่าน UI)
- **Key ที่ผูก workspace/allowlist:** ใช้ได้เฉพาะ `/api/v1/query*`; context นอกสิทธิ์ = 403; context legacy อ่านได้เฉพาะ main view ที่ชั้น SQL — ออก key ของระบบภายนอกแบบนี้เสมอ (`docs/manuals/manual_api_keys.md`)
- **`scope`** ใน `/api/v1/query`: บังคับที่ชั้น SQL; key ที่ context ไม่ประกาศ = 400 (`docs/PORTAL_INTEGRATION.md`)
- **เอกสาร OpenAPI เต็มปิดเป็นค่าเริ่มต้น** (2026-09-21): `/api/v1/openapi.json`, `/docs`, `/redoc` = 404 เว้นแต่ตั้ง `API_DOCS_ENABLED=true` — เดิมเปิดโดยไม่ต้อง login และมีทุก route (admin 90 จาก 115) = แผนที่ของพื้นผิวที่โจมตีได้; endpoint ของ admin ยังต้อง auth ทุกตัวอยู่แล้ว ที่ปิดคือแผนที่ **ห้ามเปิดบน server ที่คนนอกเข้าถึงได้**; เอกสารสาธารณะที่คัดแล้วเป็นงานของ Plan 8.5
- **Vanna brain ต่อ workspace:** `<VANNA_CHROMA_PATH>__<workspace>` (default ใช้ path เดิม) — backup/restore ต้องรวม directory เหล่านี้

## Plan 8.1 — ที่มา + สถานะของความรู้ (2026-09-21)

- **Upgrade:** รัน `python scripts/migrate_knowledge_provenance.py` (idempotent) **ก่อน** start code ของ 8.1 — server ไม่ยอมเริ่มถ้า config DB ยังไม่มีคอลัมน์
  (`config DB has no provenance columns on … — run: …`); รันซ้ำหลัง restart เพื่อติดป้ายแถวที่ code เดิมเขียนระหว่างนั้น · ลำดับที่ซ้อมแล้ว: `plan/archive/RESULT_P8_PHASE1.md` §12
- ตัวอ่านที่ถึง prompt / RAG / routing / สิทธิ์ของ key ใช้เฉพาะแถว `status='active'` — ข้อเสนอของเครื่อง (`proposed`) และที่คนปฏิเสธ (`rejected`) ไม่ถึง LLM
- **restart = ขึ้นทุก commit ของสาขาที่ server รัน** (server รันจาก working tree) — ก่อน restart ไล่ `git log <commit ที่รันอยู่>..HEAD` ว่ามี commit ที่ต้อง migrate ก่อนไหม
- ถอย code ไม่ต้องถอย DB (เพิ่มคอลัมน์อย่างเดียว) แต่ code ก่อน 8.1 อ่าน `is_active` ไม่อ่าน `status` → ซ่อนข้อเสนอก่อน (`RESULT_P8_PHASE1` §12.3)

## Plan 7 Phase 4.5 — Data protection (2026-09-19)

- **Upgrade:** รัน `python scripts/migrate_data_sources.py` + `python scripts/migrate_workspaces.py` อีกครั้ง (idempotent — เพิ่ม `data_sources.llm_data_policy` / `llm_provider_allowlist`, `workspaces.result_retention_days` / `store_result_data`); ตาราง `query_audit` (app DB) ถูกสร้างเองตอนใช้ครั้งแรก. Source เดิมและ source ใหม่ทุกตัว = `full` → พฤติกรรมไม่เปลี่ยนจนกว่า admin จะตั้ง
- **`llm_data_policy` ต่อ source** (`PUT /admin/sources/{name}/policy`):
  | ค่า | provider เห็นอะไร |
  |---|---|
  | `full` | เหมือนก่อน Phase 4.5 (ค่าตัวอย่าง, value lookup, แถวผลลัพธ์, RAG) |
  | `aggregated_only` | เหมือน `schema_only` ยกเว้น: แถวผลลัพธ์ของ SQL ที่รวมยอด (GROUP BY / SUM / COUNT / AVG, ไม่มี window function, ไม่มี `*`) ส่งให้ LLM อธิบายได้ — **เป็นการตรวจจากข้อความ SQL ไม่ใช่ k-anonymity**: GROUP BY บน key ที่ไม่ซ้ำยังผ่าน → ข้อมูลที่ห้ามเห็นรายแถวเด็ดขาดให้ใช้ `schema_only` |
  | `schema_only` | schema + คำถาม + ความรู้ที่คน/contract เขียน (instruction, กฎ, mapping) เท่านั้น — ไม่มีค่าตัวอย่าง, value lookup, RAG/golden, แถวผลลัพธ์, คำตอบเก่าใน history, ค่าใน error/hint; คำอธิบายผล = template ไม่ผ่าน LLM; tool loop (`mode=mcp`) ถูกปฏิเสธ (403) |
  - บังคับที่ **ชั้น provider** (`AIProvider.__init_subclass__` → `app/core/llm_policy.py: guard_call`) — provider ที่เพิ่มภายหลังถูกห่อเอง — และที่ **ต้นทางของค่า** (`get_sample_values`, value lookup, value verifier, RAG, onboarding, keyword index, hierarchy); caller ตรงกลางไม่ต้องรู้จัก policy
  - อ่าน policy ไม่ได้ / ค่าไม่รู้จัก / NULL = `schema_only`; allowlist ที่ parse ไม่ได้ = ไม่มี provider ใดผ่าน
  - ตั้งเข้มขึ้นผ่าน API → ลบ `keyword_value_index` ของ context ใน source นั้นทันที + ล้าง query cache; ค่าที่เคย extract ไว้ใน `master_hierarchy_values` ยังอยู่ใน config DB แต่ไม่ถูกค้น/ส่งอีก
- **`llm_provider_allowlist` ต่อ source:** provider นอกรายการถูกปฏิเสธที่ชั้น provider; ผู้เรียกระบุ provider นอกรายการ = 403 (ไม่สลับเงียบ); ไม่ระบุ = ระบบเลือกตัวแรกในรายการที่ตั้งค่าไว้. **D4 (ตัดสิน 2026-09-19): Matcha (NT Gateway) ใช้กับข้อมูลอ่อนไหวได้** → source อ่อนไหวตั้ง `["matcha"]`. ⚠️ allowlist คุม *ชื่อ provider* — gateway ส่งต่อไปที่โมเดลใด/ที่ใดเป็นเรื่องของสัญญากับ gateway ไม่ใช่สิ่งที่ code ตรวจได้
- **นอกขอบเขตของ `llm_data_policy`** (ไม่ใช่ LLM provider หรือไม่มี source ให้ผูก): Telegram (ส่ง 15 แถว + กราฟไป Bot API), ไฟล์ที่ admin upload ให้ schema analyzer, คำถาม/SQL ของผู้ใช้ที่ admin agent สรุป — ดู `plan/archive/RESULT_P7_PHASE45.md`
- **Retention:** `result_retention_days` (admin_config, **default 30**, 0 = ไม่ลบ; `PUT /admin/config/settings/result_retention_days`) — job รายวันล้าง `chat_history.result_data` + `sql_result_summary` + **`ai_response`** (แทนด้วยข้อความตายตัว "คำตอบหมดอายุตามนโยบายการเก็บข้อมูล — ถามใหม่ได้"; แถวที่ไม่เคยมีคำตอบยังเป็น `NULL`), `chat_session_data`, `query_correction_log`, CSV ชั่วคราวของ chat tool; คำถาม / SQL / `render_meta` / `query_audit` อยู่ครบ. คำตอบที่หมดอายุแล้วไม่ถูกส่งเข้า LLM เป็นบริบทของคำถามต่อเนื่อง. ⚠️ **รอบแรกหลัง upgrade จะล้างผลลัพธ์และข้อความคำตอบที่เก่ากว่า 30 วันทั้งหมด** (ประวัติยังเปิดอ่านได้ — คำถามและ SQL อยู่ครบ — แต่ไม่มีตาราง/กราฟ/คำตอบ; วัดบนสำเนาของ app DB จริง 2026-09-20: 1,513 แถว) — ต้องการเก็บนานกว่า ให้ตั้งค่าก่อน start. `store_result_data=false` (feature flag) = ไม่เขียนแถวผลลัพธ์ลง history / session data / query cache เลย. Override ต่อ workspace: `PUT /admin/workspaces/{id}/retention`
- **DSR:** `DELETE /admin/users/{id}/data` (`dry_run=true` เป็นค่าเริ่มต้น = นับอย่างเดียว) — ลบ history, session data, conversations, feedback, exports + ไฟล์, admin-agent conversations, query cache; `query_audit` คงแถวไว้แต่ตัด `user_id` + คำถาม; บัญชีและ API key ไม่ถูกแตะ. **ไม่ย้อนกลับได้** — backup app DB ก่อน
- **Audit ของคำถาม:** `query_audit` เขียนที่ `QueryEngine.query` (chat, `/api/v1/query`, telegram) และที่ xlsx export (`channel` = `report_export` ตอนขอ, `report_download` ตอนดาวน์โหลด พร้อมจำนวนแถว): user, api_key, channel, workspace, context, scope, คำถาม, SQL, ชื่อคอลัมน์, จำนวนแถว, provider, policy, cache_hit, error (รวมคำขอที่ถูกปฏิเสธ) — **ไม่มีค่าผลลัพธ์**. ค้น/ export: `GET /admin/query-audit?...&format=csv`. เขียนไม่ได้: ผู้เรียกที่**ถือ API key** (REST ด้วย key, MCP facade) ได้ **503** / tool error `audit_unavailable` และ**ไม่มีคำตอบออกไป** (NIST AU-5 — คำถามข้าม context: แถวแม่หรือแถวลูกหายไปแถวเดียว = ทั้งคำถามไม่ออก; cache hit ก็ต้องเขียนได้ก่อนส่ง); chat / telegram / session user ยังตอบตามเดิม (มี `chat_history` เป็นร่องรอย) — ตั้ง alert ที่ข้อความ `query audit NOT written`. ⚠️ โควตาถูกนับไปแล้วก่อนรันคำถาม จึงเสีย 1 usage + 1 provider call เมื่อได้ 503
- ⚖️ กรอบ PDPA (§6.6 ข้อ 8 ของแผน) ยังต้องให้ DPO/ฝ่ายกฎหมายทบทวน — มาตรการข้างบนเป็นเครื่องมือทางเทคนิค ไม่ใช่การรับรองความสอดคล้องตามกฎหมาย

## Plan 7 Phase 5 — คำถามข้ามหลาย context (2026-09-19)

- **ปิดเป็นค่าเริ่มต้น**; เปิดต่อ workspace: `PUT /admin/workspaces/{id}/multi-context` `{"enabled": true}` → `admin_config.multi_context_workspaces` (JSON list; อ่านไม่ได้ = ปิด); มีผลที่ `/api/v1/query` เมื่อผู้เรียกไม่ระบุ `context` — ไม่ต้อง migrate (`query_audit.request_group` ถูกเพิ่มเองเมื่อใช้ครั้งแรก)
- orchestrator (`app/services/multi_context.py`) ถือผลของหลาย source พร้อมกัน — สิ่งที่บังคับ:
  - context ผู้สมัคร = ใน **workspace เดียวกัน** และ**ในสิทธิ์ของ key** เท่านั้น; ชื่อ context อื่นไม่เข้า prompt ของตัวแตกคำถาม; ผลของตัวแตกถูกตรวจใน code (context ⊆ ผู้สมัคร)
  - provider call ของตัวแตก (call เดียวที่อยู่นอก `QueryEngine.query`) รันใต้ policy **เข้มสุด**ของทุก source ที่เกี่ยว + **intersection** ของ `llm_provider_allowlist` (ว่าง = 403) — เห็นแค่คำถาม + ชื่อ/คำอธิบาย/keyword ของ context ไม่มีค่าจากข้อมูล
  - คำถามย่อยทุกข้อรันผ่าน `QueryEngine.query` = scope / allowlist / pinned / `llm_data_policy` / audit ของแต่ละ source ตามเดิม; **ขั้นรวมคำตอบไม่มี LLM** → ค่าของ source ที่ ≠ `full` ไม่มีทางไปถึง provider (test sentinel: `tests/unit/test_multi_context.py`)
  - ข้อย่อยถูกปฏิเสธ (scope 400 / allowlist 403 / policy 403) = ปฏิเสธทั้งคำถาม; ข้อย่อยล้ม = บอกว่าส่วนนั้นตอบไม่ได้ ไม่คำนวณข้ามส่วน
  - ไม่ JOIN ข้าม source; อัตราส่วน/ส่วนต่างคำนวณใน code จากผลของคำถามย่อย เฉพาะเมื่องวดล่าสุดของ source เท่ากัน
- audit: แถวแม่ + แถวคำถามย่อยใช้ `request_group` เดียวกัน (`GET /admin/query-audit?request_group=…`)

## Plan 7 Phase 6 — MCP สำหรับผู้เรียกภายนอก (2026-09-20)

Endpoint `/api/v1/mcp` (`app/api/v1/mcp_facade.py`) — stateless Streamable HTTP, 3 tools (`ask`, `list_contexts`, `source_status`). คู่มือเชื่อมต่อ: [`docs/manuals/manual_mcp_external.md`](manuals/manual_mcp_external.md) | ผล/หลักฐาน: `plan/archive/RESULT_P7_PHASE6.md`

**Threat model:**
- ผู้เรียกคือ **LLM / agent ที่ถือ key เองในเครื่องของผู้ใช้ นอกเครือข่ายที่เราคุม** — ไม่ใช่ trusted server แบบ portal; argument ทุกตัว (`context`, `scope`) เป็นสิ่งที่โมเดลเลือกเอง
- **`scope` ไม่ใช่ entitlement:** ผู้ถือ key อ่านได้**ทุกแถว**ของทุก context ที่ key เห็น — `scope` กรองให้แคบลงได้ (บังคับที่ชั้น SQL) แต่ไม่ใช่สิทธิระดับแถว. ผู้ใช้ที่ควรเห็นบางหน่วยงาน/บางรายงาน → ใช้ REST ผ่าน server ที่เชื่อถือได้ซึ่งเป็นผู้ใส่ `scope` ไม่ใช่แจก key
- **คำตอบเข้า LLM ของ client** ที่เราไม่ได้คุม — `llm_data_policy` / `llm_provider_allowlist` คุมได้เฉพาะ provider ฝั่ง server
- ข้อความของ engine (explanation / error) มี SQL, path, ข้อความ exception ได้ และ FastMCP ส่ง `str(exception)` ให้ client ตรง ๆ ถ้าไม่จับ
- stateless transport ไม่ต้อง `initialize` — `tools/call` เป็น request แรกได้; ชื่อ client เป็นข้อมูลที่ client แจ้งเอง ไม่ใช่หลักฐานตัวตน
- request จาก browser (DNS rebinding / cross-origin) ไปยัง server ที่รันบน localhost

**สิ่งที่บังคับ:**
- **ปิดเป็นค่าเริ่มต้น:** flag `admin_config.mcp_external_enabled` (ปิด = 404); GET / DELETE = 405
- **Gate ทุก HTTP request หน้า transport:** `X-API-Key` (ตัวเดียว — มากกว่าหนึ่ง = 401) ต้อง active / ไม่หมดอายุ, เจ้าของ active, มี scope `query` หรือ `full`, และ**ผูก workspace หรือ allowlist** — ไม่ผ่าน = 401; key ใน query string / Bearer / session token ใช้แทนไม่ได้; revoke มีผลใน request ถัดไป
- **Key ที่ผูกแล้วใช้ได้เฉพาะ** `/api/v1/query*` และ `/api/v1/mcp` (`enforce_key_surface`) — ไม่ได้สิทธิ์ `/chat`, `/admin` เพิ่ม; ปิด workspace = context ของ workspace นั้นหายจากช่องทางนี้ทันที (รวม key ที่ผูกด้วย allowlist อย่างเดียว)
- **policy `full` เท่านั้น:** context ที่ source ≠ `full` ไม่อยู่ใน `list_contexts`, ระบุชื่อ = `policy_refused`, ผลลัพธ์ (และทุก part) ที่ `llm_policy` ≠ `full` ถูกทิ้งก่อนส่งออก; ตัวอ่าน policy ของ facade เป็นแบบเข้ม — registry ยังไม่ migrate / config อ่านไม่ได้ = **ปฏิเสธทุก context** (ต่างจาก `policy_for_context` ที่ถือว่า `full`)
- **ไม่มี SQL / ข้อความ exception / path ขาออก:** ไม่มี `include_sql`; ข้อความของ engine ออกได้เฉพาะผลที่มีแถว; ไม่มีแถว / part ที่ล้ม / error ทุกชนิด = code + ข้อความตายตัว + `request_id` (รายละเอียดอยู่ใน log / `query_audit` ฝั่ง server); context ที่ไม่มีอยู่กับ context นอกสิทธิ์ได้คำตอบเดียวกัน; `source_status` ไม่คืน path / ชื่อ source / สาเหตุ
- **Host / Origin** (DNS rebinding guard ของ SDK เปิดอยู่): `MCP_ALLOWED_HOSTS` — Host นอกรายการ = 421 (reverse proxy ต้องส่ง `Host` เดิม หรือเพิ่ม host ของ proxy); `MCP_ALLOWED_ORIGINS` — **ว่าง = request ที่มี `Origin` ถูกปฏิเสธ 403 ทั้งหมด**
- **แถวขาออก:** `ask(include_data=true)` ไม่เกิน `MCP_MAX_ROWS` (default 100) ต่อ ask — ผู้เรียกเพิ่มเองไม่ได้
- **โควตา:** **1 tool call = 1 usage** ตัวนับเดียวกับ REST (`api_key_usage` รายวัน + Redis รายนาที); `initialize` / `tools/list` ตรวจ key ทุกครั้งแต่ไม่นับ; เกิน = tool error `rate_limited` (ไม่ใช่ HTTP error — non-2xx ทำให้ session ของ MCP client ล้ม)
- **Audit:** ทุก `ask` ลง `query_audit` ด้วย `channel = mcp:<user-agent ของ client>`; REST เขียน channel ที่ขึ้นต้น `mcp` ไม่ได้ (บันทึกเป็น `api:mcp…`); ค้น: `GET /admin/query-audit?channel=mcp` (จับ prefix `mcp:`). การปฏิเสธที่ gate (401) เกิดก่อนถึง engine จึงไม่มีแถว audit
- facade ไม่มี provider call ของตัวเอง — ทุกคำถามผ่าน `QueryEngine.query` (scope / allowlist / pinned / `llm_data_policy` / audit ตามเดิม)

**Checklist ก่อนเปิดใช้กับ DB จริง (ยังไม่ได้ทำ ณ 2026-09-20):**
1. รัน `scripts/migrate_data_sources.py` + `scripts/migrate_workspaces.py` บน `config.db` จริง — ไม่มีคอลัมน์ `llm_data_policy` = MCP ปฏิเสธทุก context
2. เปิด flag `mcp_external_enabled`, ออก key จริงที่**ผูก workspace** (scope `query`), ตั้ง `MCP_ALLOWED_HOSTS` ถ้าไม่ได้เรียกผ่าน localhost
3. รัน Redis ในเครื่องที่ให้บริการ — ไม่มี Redis = limit รายนาที fail-open; เพดานรายวันคือเพดานเดียวที่บังคับจริง

⚠️ **MCP server ภายใน (`mcp_servers/*.py` — stdio) ห้ามเปิดให้ client ภายนอกเด็ดขาด** ไม่ว่าจะด้วยการเปลี่ยน transport (`--transport sse`) หรือ config ของ desktop client: มี `execute_query` (SQL ดิบ), `get_sample_values` / `get_table_stats` (ค่าจริง), admin tools ที่เขียน config DB และอ่านคำถามของผู้ใช้อื่น — ไม่มี key, allowlist, scope, audit หรือ `llm_data_policy`. ไฟล์ `mcp_servers/claude_desktop_config.json` ที่เคยสอนวิธีต่อ `nt-query` เข้า Desktop **ถูกลบแล้ว** (2026-09-20). ผู้เรียกภายนอกใช้ `/api/v1/mcp` ทางเดียว — Claude Desktop ต่อผ่าน `scripts/mcp_stdio_bridge.py` ซึ่งเป็นตัวแปลง stdio↔HTTP ล้วน (ไม่มี tool ของตัวเอง, key มาจาก env, กติกาทั้งหมดอยู่ฝั่ง server; audit `channel = mcp:nt-ai-stdio-bridge/1.0`)

## Hardening ของช่องทางเดิม (2026-09-20)

ช่องทางที่ตอบ**ผู้เรียกนอก process** คือ `POST /api/v1/query` และ MCP facade ทั้งสองใช้ชุดรหัส/ข้อความเดียวกัน
(`app/core/outbound.py`) และไม่ส่งของภายในออกไป chat / telegram / MCP ภายในแบบ stdio **ไม่เปลี่ยน** — ที่นั่นผู้ใช้ยังเห็น SQL และ error จริง

- **ไม่มี SQL ในข้อความคำตอบ:** query ที่รันแล้วได้ 0 แถว ข้อความของ engine มี SQL เต็ม (`hybrid_flow.py`) → REST คืน `ไม่พบข้อมูลที่ตรงกับเงื่อนไข`;
  SQL ออกได้เฉพาะ field `sql` เมื่อผู้เรียกส่ง `include_sql`
- **ไม่มีข้อความ exception:** `answer` / `error` / `parts[].error` / `parts[].answer` และ body ของ 400 / 403 เป็น **รหัส + ข้อความตายตัว**
  (ก่อนหน้านี้มี path ของไฟล์, ชื่อ source, `llm_data_policy`, และ `scripts/migrate_data_sources.py`); เหตุผลจริงอยู่ใน log + `query_audit.error`
- **ไม่มี existence oracle:** context ที่ไม่มีอยู่ กับ context ที่มีแต่ไม่มีสิทธิ์ ได้ข้อความ 403 เดียวกัน
- **explanation ที่เป็น dict** คืนเฉพาะข้อความ (เดิมเป็น `str(dict)` = chart config ติดไปด้วย)
- **เกินโควตา = 429** (เดิม 401 ซึ่งทำให้ผู้เรียกไปหาสาเหตุผิดที่); `APIKeyService.check_key` แยก "key ใช้ไม่ได้" ออกจาก "เกิน limit"
- **`GET /api/v1/query/contexts` ต้อง auth** — ไม่มี key/session หรือ key ใช้ไม่ได้ = 401 (เดิมเป็น public และ key ผิด = เห็นทุก context ของทุก workspace);
  การ list ไม่นับโควตา (`authenticate` ไม่ใช่ `validate_key`)
- **audit เขียนไม่ได้ = ไม่ส่งคำตอบ** สำหรับผู้เรียกที่ถือ key (ดูหัวข้อ Audit ด้านบน)
- **`ai_response` หมดอายุ**ตาม `result_retention_days` เดียวกับแถวผลลัพธ์ (ดูหัวข้อ Retention ด้านบน)

## API Key Rate Limiting (F4.4)

- Daily limit: enforced in DB (`api_key_usage`).
- Per-minute limit: Redis fixed-window (`ratelimit:apikey:<id>:<minute>`).
  Requires `REDIS_URL`. When Redis is unavailable the check **fails open**
  (availability first for internal use) and logs a warning once per process.
