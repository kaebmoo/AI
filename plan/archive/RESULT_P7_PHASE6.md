# RESULT Plan 7 Phase 6 — MCP สำหรับผู้เรียกภายนอก

**สถานะ:** สำรวจก่อนออกแบบ — ยังไม่เปิด endpoint; รอเจ้าของระบุผู้ใช้/client รายแรกตามข้อ 2 ของ prompt
**วันที่:** 2026-09-19–20 | **Branch:** `main` | **เริ่มจาก:** `c11df30` (`origin/main` ในเครื่อง = `52c3ee8`; ahead 2 เป็น commit เอกสาร prompt)
**แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 6; รวม Plan 1B-C / REMAIN-8 เมื่อผ่าน exit จริง

## 0. Baseline และสำรองข้อมูล

- Working tree สะอาดก่อนเริ่ม; ทำต่อบน `main` ตามคำสั่ง ไม่มี rebase / force-push / push
- Backup ด้วย SQLite backup API จาก connection `mode=ro`: `config.db` และ `app.db`; `PRAGMA quick_check` = `ok` ทั้งคู่
- Scratchpad: `/private/tmp/nt-ai-p7-phase6-612hskar/` — `backup/` = snapshot ก่อนงาน, `test/` = สำเนาที่ใช้ทดลอง, `manifest.json` = hash ก่อน/หลัง; **ไม่ commit DB/secret/log ทดสอบ**
- สำเนารัน `scripts/migrate_data_sources.py` + `scripts/migrate_workspaces.py` ก่อน baseline; เพิ่มคอลัมน์ Phase 4.5 เฉพาะสำเนา
- คำสั่ง baseline (export `CONFIG_DB_URL`, `DATABASE_URL`, `DATA_SOURCE_CACHE_DIR` ไป scratchpad ก่อน):

  ```bash
  venv/bin/python3.14 -m pytest -q -p no:cacheprovider
  ```

- **997 passed, 3 skipped in 12.05s**; log: `/private/tmp/nt-ai-p7-phase6-612hskar/baseline-pytest.log`
- SHA-256 ของไฟล์ DB จริงก่อน/หลัง baseline เท่ากันทั้งสองไฟล์ — หลีกเลี่ยง side effect เดิม `last_brain_relevant_change_at` ด้วยการชี้ config DB ไปสำเนา
- ยังไม่ migrate DB จริง / ออก key จริง / เปิด multi-context / รัน eval ด้วย LLM จริง

## 1. สำรวจ

### 1a. MCP ภายใน — 35 tools; ไม่มีตัวใดเป็น external API

หลักฐานจาก decorator `@mcp.tool()` ใน source ปัจจุบัน (เลขหลังชื่อ = บรรทัด): metadata **13**, query **5**, validation **4**, admin **13**. `MCPClientService` (`app/services/mcp_client.py:61–156`) เปิด metadata/query/validation ผ่าน **stdio subprocess** และรวม tools ที่ประกาศทั้งหมด; admin ไม่อยู่ในรายการ startup อัตโนมัติ

| Server / tool (บรรทัดใน `mcp_servers/<server>.py`) | อ่าน / เขียน / สิ่งที่คืน | ขอบเขต |
|---|---|---|
| `nt_metadata_mcp`: `get_available_contexts` 218, `route_question_to_context` 273, `get_context_info` 344 | อ่าน `schema_contexts`: context/view/keywords/description ทุก workspace | คงภายใน; ไม่มี key allowlist |
| `nt_metadata_mcp`: `get_schema_for_context` 395, `get_column_info` 481 | อ่าน `schema_metadata` รวม **cached sample_values** | **ห้ามเปิดตรง**; metadata มีค่าจริง |
| `nt_metadata_mcp`: `get_semantic_mappings` 557, `search_mapping_for_term` 618 | อ่าน mappings/conditions ที่อาจมี business literals | คงภายใน; ไม่มี workspace filter |
| `nt_metadata_mcp`: `get_business_rules` 702, `check_rule_violation` 768 | อ่าน rules + ตัวอย่าง SQL; checker รับ SQL/question | คงภายใน |
| `nt_metadata_mcp`: `get_golden_examples` 855, `find_similar_example` 911 | อ่านคำถาม + SQL ใน golden ซึ่งอาจมีค่าจาก control totals จริง | **ห้ามเปิดตรง** |
| `nt_metadata_mcp`: `get_database_info` 958, `get_syntax_rules` 978 | engine/context/view inventory; syntax rules | คงภายใน; inventory ไม่กรองสิทธิ์ |
| `nt_query_mcp`: `validate_sql` 240, `explain_sql_thai` 378 | ตรวจ/อธิบาย SQL จาก argument ไม่ execute | คงภายใน; ไม่จำเป็นต่อ facade |
| `nt_query_mcp`: `execute_query` 263 | **รับ SQL ดิบ** → business DB → แถว/columns/error | **ห้ามเปิดตรงเด็ดขาด**; ข้าม QueryEngine/workspace/scope/pinned/audit |
| `nt_query_mcp`: `get_sample_values` 295 | DISTINCT + COUNT DISTINCT ตาม table/column ที่รับมา; ค่าจริงสูงสุด 100 | **ห้ามเปิดตรงเด็ดขาด** |
| `nt_query_mcp`: `get_table_stats` 543 | count/schema + **sample row เต็มแถว** (`SELECT * … LIMIT 1`) | **ห้ามเปิดตรงเด็ดขาด**; ใช้แทน source status ไม่ได้ |
| `nt_validation_mcp`: `check_business_rules` 63, `get_validation_summary` 204 | อ่าน rules จาก config DB | คงภายใน; ไม่ใช่ authorization |
| `nt_validation_mcp`: `calculate_confidence_score` 128, `validate_result` 175 | คำนวณจาก arguments/ผลลัพธ์ที่ caller ส่ง | คงภายใน |
| `nt_admin_mcp`: `search_mappings` 62, `search_rules` 84, `search_examples` 103 | อ่าน config/golden ไม่มี key allowlist | คง admin local-only |
| `nt_admin_mcp`: `add_mapping` 72, `add_rule` 94, `add_example` 113 | **INSERT + commit config DB** + audit/cache | **ห้ามเปิดตรงเด็ดขาด** |
| `nt_admin_mcp`: `list_contexts` 125 | active contexts ทั้งหมด | ห้ามใช้ wrapper นี้เป็น external listing |
| `nt_admin_mcp`: `refresh_cache` 134 | **แก้สถานะ cache** ของ schema/warnings/patterns | **ห้ามเปิดตรง** |
| `nt_admin_mcp`: `search_hierarchy` 143 | อ่าน values/aliases; ไม่ส่ง context = ค้นทุก context | คงภายใน; source policy ไม่ใช่ key authorization |
| `nt_admin_mcp`: `inspect_view` 155, `validate_config` 164 | profiling view (samples/distinct/stats เมื่อ full); ตรวจ config | คง admin local-only |
| `nt_admin_mcp`: `analyze_query_logs` 173, `review_feedback` 185 | อ่าน app DB: คำถาม/SQL/error/feedback ของผู้ใช้อื่น | **ห้ามเปิดตรงเด็ดขาด** |

SQLite `mode=ro` กันการเขียน แต่ไม่ได้ให้สิทธิ์อ่าน; `safe_table` ตรวจ catalog ไม่ใช่ allowlist ของ key. Metadata/query มี CLI `--transport sse` อยู่แล้ว แต่ไม่มี auth ของแอป: **ไม่ใช้วิธีเปลี่ยน transport ของ server เดิมแล้วเปิดทั้งชุด**. ตัวอย่าง admin SSE ใน Plan 1B-C เป็นแผนเก่าที่ถูกแทนด้วย facade นี้

`mcp_servers/README.md` เก่า: นับ metadata 14 แทน 13, ไม่แสดง validation/admin ในตารางหลัก, checklist backend integration ยังไม่จบ — แก้พร้อมคู่มือ Phase 6 หลังเลือก client

### 1b. SDK / ASGI / request context — ตรวจของที่ติดตั้งจริง

- `mcp==1.26.0` ทั้ง `venv/bin/python3.14` (3.14.3) และ `venv/bin/python3.10` (3.10.11); requirements กำหนด `mcp>=1.26.0`
- SDK `FastMCP` รองรับ `stdio`, legacy `sse`, `streamable-http`; `sse_app()` / `streamable_http_app()` คืน Starlette ASGI app จึง mount ใน FastAPI ได้
- Proof แยกจากแอป/DB/provider: `/private/tmp/p7_sdk_transport_probe.py` ใช้ SDK `ClientSession` จริง + `httpx.ASGITransport`: **initialize → list_tools → call_tool ผ่าน** ทั้ง stateful/stateless Streamable HTTP; mount ทดสอบ `/external/mcp`
- ต้องเปิด `session_manager.run()` ใน lifespan ของ parent อย่างชัดเจน; probe ที่ไม่เปิด lifespan ล้มด้วย `Task group is not initialized` ตามคาด. ห้าม start lifespan ของ `app.main` จริงเพื่อทดลอง เพราะเปิด scheduler/Telegram ด้วย
- Tool อ่าน HTTP request ปัจจุบันผ่าน `ctx.request_context.request`; headers และ `request.state` เปลี่ยนตาม header ของ tool call แต่ละครั้งจริง
- **Stateful:** เก็บ `session.client_params.clientInfo` ได้; แต่ middleware ContextVar ยังถือค่าของ request ที่สร้าง session แม้ request ถัดไปเปลี่ยน key. Session manager หา session ด้วย session ID ไม่ได้ผูกกับ principal ของแอป → หากเลือก stateful ต้อง bind key/session เพิ่มและตรวจทุก request
- **Stateless:** ไม่มี session ID; `client_params` เป็น `None` ใน tool แม้ initialize ส่ง clientInfo มา. ชื่อ client ต้องมาจาก metadata/header ที่ส่งใน request ปัจจุบัน (เช่น User-Agent หรือ header ชื่อ client) และถือเป็น self-reported เท่านั้น
- Legacy SSE แยก GET `/sse` กับ POST `/messages/`: auth ต้องครอบทั้งสองทาง ไม่ใช่เฉพาะตอนเปิด stream
- DNS rebinding guard ของ SDK ยังต้องเปิด: probe ใช้ `localhost:8000`; hostname `localhost` ไม่มี port ไม่ตรง default `localhost:*` และได้ 421. Deployment ต้องตั้ง allowed hosts/origins ให้ตรง URL จริง

หลักฐาน SDK อยู่ใต้ `venv/lib/python3.14/site-packages/mcp/`: `server/fastmcp/server.py:279,837,950` (transport/ASGI), `server/streamable_http_manager.py:83,215` (lifespan/session lookup), `server/streamable_http.py:264` + `server/lowlevel/server.py:727` (request metadata), `server/session.py:163` (clientInfo). Probe เก็บสำเนาและ output ใน scratchpad `sdk_transport_probe.py` / `sdk_transport_probe.log`; ไม่มี real key หรือข้อมูลธุรกิจ

| Client ที่พบในเครื่อง | หลักฐานในเครื่อง | สิ่งที่พิสูจน์ได้ตอนสำรวจ |
|---|---|---|
| Claude Code **2.1.270** | `claude --version`, `claude mcp add --help` | stdio / SSE / HTTP และ custom `--header` → ส่ง `X-API-Key` ได้ตาม CLI; ยังไม่ได้ต่อ facade จริง |
| Gemini CLI **0.58.0** | `gemini --version`, `gemini mcp add --help` | stdio / SSE / HTTP + `--header`; ยังไม่ได้ต่อ facade จริง |
| Codex CLI **0.144.6** | `codex --version`, `codex mcp add --help` | `--url` สำหรับ Streamable HTTP + `--bearer-token-env-var`; CLI help นี้อย่างเดียว **ไม่พิสูจน์**วิธีส่ง `X-API-Key` |
| Claude Desktop **2.2553.1** | app bundle version | พบแอป แต่ยังไม่พิสูจน์ custom API-key header จาก UI/การเชื่อมต่อจริง; ไม่ถือว่ารองรับเหมือน Claude Code โดยอัตโนมัติ |

เอกสาร official ที่ตรวจประกอบ: [Claude Code MCP](https://code.claude.com/docs/en/mcp) ระบุ HTTP/SSE/custom headers; [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) ระบุ `http_headers`/`env_http_headers` (ยังไม่ลองกับ binary). [Claude remote connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp) ระบุว่า remote connection มาจาก Anthropic cloud และ endpoint ต้องเข้าถึงได้จากภายนอก — **ไม่เท่ากับ** CLI ต่อ localhost; เอกสารส่วนนี้ไม่ยืนยัน arbitrary `X-API-Key` ใน UI. ถ้าเลือก Desktop ต้องทดสอบวิธีส่ง key และเส้นทางเข้าถึงจริงก่อนตกลง transport

**ยังไม่มีผู้ใช้ MCP รายแรกที่เจ้าของระบุ** — การพบ client ติดตั้งอยู่ไม่เท่ากับมี use case หรืออนุมัติส่งข้อมูล. ข้อเสนอ transport: **stateless Streamable HTTP**, เพิ่ม legacy SSE เฉพาะหาก client ที่เลือกจำเป็นต้องใช้

### 1c. Auth / usage / audit ที่มีจริง และจุด reuse

| ลำดับ | พฤติกรรมปัจจุบัน | สิ่งที่ facade ต้องได้ |
|---|---|---|
| Key validation | `APIKeyService.validate_key` (`:85`) ตรวจ prefix/hash/active/expiry/rate; commit `last_used_at` | ตรวจทุก HTTP request ก่อนเข้า transport; ไม่รับ session/Bearer-session fallback เมื่อ X-API-Key ขาด/ผิด |
| Quota | `_check_rate_limits` (`:179`): รายวันจาก `api_key_usage`, รายนาที increment Redis `ratelimit:apikey:<id>:<minute>`; Redis ล่ม = fail-open + warning | ใช้ quota/key ID เดียวกับ REST; validate **ครั้งเดียว**ต่อหน่วยที่นับ |
| Usage / owner | `get_current_user` (`deps.py:63–75`) enforce surface → track_usage → ตรวจ owner active | อย่าส่ง ORM session/global principal ค้างข้ามผู้ใช้; ส่ง principal ที่ยืนยันแล้วผ่าน request.state ไป handler |
| Surface | `enforce_key_surface` (`deps.py:38`) ยอมเฉพาะ `/api/v1/query` และลูกของ path นี้ | เพิ่มเฉพาะ exact facade path ที่ตกลง; `/chat`, `/admin` ยังไม่ได้สิทธิ์เพิ่ม |
| Contexts | `allowed_contexts` (`workspaces.py:46`) workspace ∩ allowlist; อ่านไม่ได้ = เซตว่าง | ทั้ง 3 tools ใช้ allowlist เดียวกัน; canonicalize ชื่อก่อน lookup; ปฏิเสธนอกสิทธิ์ |
| Query | `query.py:130–194` → `multi_context.ask` → `QueryEngine.query` | ใช้การสร้าง response/refusal ชุดเดียวกับ REST; ไม่เรียก `_query`/`_execute_query` ตรง |
| Isolation | `QueryEngine.query:418–436` ตั้ง/reset scope, pinned, llm policy ใน finally | ทำงานพร้อมกันสอง key แล้วค่าไม่ปน; cache อยู่ใต้ allowlist/scope/build/policy เดิม |
| Audit | QueryEngine + orchestrator เขียน parent/parts ด้วย `request_group`; `query_audit.record` ต้องมี app DB session | channel เป็น **`mcp`** ฝั่ง server; client name แยกจาก channel และไม่ใช่หลักฐานตัวตน; schema ปัจจุบันยังไม่มี client-name field |

ข้อจำกัดเดิมที่ต้องระบุให้ตรง ไม่รายงานว่า parity ครบก่อนแก้:

- `validate_key` **มี side effects**: middleware + tool เรียกซ้ำ = rate นับซ้ำ. ตรวจแค่ initialize = revoke/expiry/owner เปลี่ยนแล้วอาจยังใช้ session ต่อได้
- เกิน API-key quota ตอนนี้ `validate_key` คืน `None` แล้ว REST มักได้ **401**; คู่มือที่บอก 429 ไม่ตรงเส้นทางนี้. ไม่แก้ semantics ของ REST เงียบ ๆ ระหว่างเพิ่ม transport
- `get_current_user`/`simple_query` ยังไม่ตรวจ `has_scope(key, "query")`; admin ตรวจ `admin/full` ต่างหาก. Facade ควรตรวจ query/full ชัดเจน
- `GET /query/contexts` เป็น **public**; key ผิด → `validate_key(None result)` → `allowed_contexts(None)` = unrestricted. ต้อง reuse การอ่านรายการหลัง authenticate สำเร็จแล้ว ไม่ใช้ endpoint public เป็น auth ของ MCP
- Audit ปัจจุบันเริ่มเมื่อเข้าถึง QueryEngine (รวม refusal ของมัน); auth failure ก่อนเข้าถึง engine ไม่ใช่แถว query audit และ audit ที่เขียนไม่ได้ยัง fail-open ตาม Phase 4.5
- การอ่าน source status ให้ authorize **context** ก่อน resolver และคืนเฉพาะ status/freshness/schema version; ไม่ส่ง path/credential/stack trace หรือ admin source dump

### 1d. ขอบเขตผู้ถือ key / ผลลัพธ์ที่ออกไปหา client — ต้องตัดสินพร้อม client

1. **Scope ไม่ใช่ entitlement ของผู้ใช้ desktop:** Plan 7 §6.3 v1 เชื่อ body เพราะ trusted server ถือ key. Key ปัจจุบันมีเพดาน context แต่ไม่มี row ceiling; ละ scope = `request_scope=None`. Desktop/agent ที่ถือ key จึงสามารถอ่านข้อมูลทุกแถวของ contexts ที่ key เห็นได้ในทางเทคนิค และเลือก filter เอง; ไม่ได้หมายความว่าเจ้าของอนุมัติสิทธิ์นั้นแล้ว. ถ้าผู้ใช้มีสิทธิ์แค่บางรายงาน/หน่วยงาน ต้องผ่าน trusted proxy ที่สร้าง scope หรือเพิ่ม entitlement ก่อน
2. **ผล MCP อยู่นอก server provider policy:** ภายใต้ `schema_only` ผู้เรียกยังได้คำตอบจาก template ที่อาจมีค่าจริง (`llm_policy.py:156`, `query.py:166`). `include_data=False` ไม่ได้ทำให้ answer ปราศจากตัวเลข; client ส่งต่อให้ LLM ของตัวเองได้ และ `llm_provider_allowlist` ของ server คุมปลายทางนั้นไม่ได้ — ลักษณะเดียวกับ Telegram S13 ใน RESULT Phase 4.5
3. ข้อเสนอเล็กที่สุดถ้ายังไม่มีผู้ใช้จริง: **PoC ด้วยข้อมูลสังเคราะห์ + restricted query key ทดสอบบนสำเนา** และ client CLI ที่เจ้าของเลือกหนึ่งตัว. ไม่ใช้ portal key จริงและไม่ส่งข้อมูล NT จริงไป client จนระบุขอบเขตที่อนุมัติ; การผ่าน PoC ยังไม่ใช่เปิดใช้งานจริง

## 2. แผนย่อย + exit criteria (ข้อเสนอ — รอเจ้าของ)

โครงที่เสนอ:

```text
MCP client → exact HTTP facade path → shared API-key auth/usage → request.state principal
  ask → shared stateless query entry/response → multi_context.ask → QueryEngine.query
  list_contexts / source_status → allowed_contexts → filtered metadata/source resolver
Internal stdio MCP tools ยังอยู่หลัง pipeline เดิม ไม่มี passthrough tool registry
```

| ก้อนงาน / commit | ขอบเขต | Exit ที่ตรวจได้ |
|---|---|---|
| 3. Shared query entry + facade | แยกส่วน execute/format/refusal จาก REST ให้ REST/MCP เรียกฟังก์ชันเดียว; 3 tools = `ask(question, context?, scope?)`, `list_contexts()`, `source_status(context)`; transport/path ตาม client (เสนอ `/api/v1/mcp` แบบ stateless HTTP) | REST contract เดิมรวม `parts/computed/data_as_of` ไม่เปลี่ยน; tools/list มีเพียง 3 ชื่อ; SQL ดิบ/admin/sample tools เรียกไม่ได้; refusal 400/403 เป็น `isError=true` พร้อมข้อความและรหัสที่อ่านได้ |
| 4. Auth + usage + audit | X-API-Key เดิม; เสนอให้ facade รับเฉพาะ restricted key ที่มี query/full scope; helper ใช้ร่วมกับ auth เดิมโดย REST ยังรับ session ตามเดิม; `channel=mcp` + client label ที่ sanitize/truncate | ขาด/ผิด/revoked/expired key หรือ owner inactive ถูกปฏิเสธก่อน initialize; key A อ่าน listing/status/context B ไม่ได้; config fail = deny; context ที่สะกดต่าง canonicalize; ไม่เปิด chat/admin |
| 4. หน่วย quota (ข้อเสนอ implementation) | **authenticated HTTP request** = 1 usage รวม initialize/list/notifications/tool calls; authenticate+track ครั้งเดียวหน้า transport ไม่เรียกซ้ำใน tool; ใช้ Redis/DB counter เดียวกับ REST | ทดสอบจำนวน requests กับ counter แบบเป๊ะ; quota REST+MCP รวมกัน; revoked key มีผลใน request ถัดไป; session token ใช้แทน API key ไม่ได้ |
| 5a. SDK end-to-end ใน test | ASGI MCP SDK client จริงบน DB ชั่วคราว, provider synthetic; ใช้ public tools เรียก pipeline จริงตามสมควร | single + multi-context, scope 400, allowlist/policy 403, source unavailable, cache, audit parent/parts, ContextVar cleanup/concurrent keys; provider sentinel ยืนยัน policy ภายในและข้อจำกัดของผลที่ออก client |
| 5b. Client จริง + latency | client ที่เจ้าของเลือกอย่างน้อยหนึ่งตัวต่อ facade จริง; key/ข้อมูลทดสอบตามขอบเขตที่อนุมัติ | initialize/list/tools และ 3 tools ผ่าน; refusal อ่านรู้เรื่อง; บันทึก client/version/transport/header/ผล และ P50/P95 เทียบ REST |
| 6. Widget | **ไม่ทำในขอบเขตเริ่มต้น** — ยังไม่มี client ที่ 2 ยืนยันความต้องการ; NT-Report มี panel + proxy แล้ว | บันทึกไม่ทำ/เหตุผล; เพิ่มเมื่อเจ้าของยืนยัน use case จริง |
| 7. ปิด phase | review อิสระ auth/data boundary + suite; อัปเดต RESULT/PLAN/ROADMAP/REMAIN-8/FIX_NOTES/คู่มือ MCP/security/API keys/changelog; CLAUDE.md + AGENTS.md sync (gitignored) | ไม่มี critical/high ค้าง; baseline 997/3 ไม่ถอย; ปิด Plan 1B-C/REMAIN-8 เมื่อ client จริงผ่านเท่านั้น; หยุดก่อน Phase 7; ไม่ push |

**การวัด latency ที่เสนอ:** แยก (ก) transport overhead ด้วยคำตอบ synthetic คงที่ อย่างน้อย 30 คู่หลัง warm-up (เสนอ P95 overhead ≤100 ms บนเครื่องเดียวกัน) กับ (ข) representative real pipeline single/multi บนสำเนาเมื่ออนุมัติ client/data แล้ว. REST/MCP ใช้ key/provider/context/scope เดียวกัน สลับลำดับ; วัด warm/cache แยก cold, กัน dedup ไม่ให้สร้างตัวเลขปลอม. รายงานขนาดตัวอย่างและ provider outlier; ไม่ใช้ SDK toy proof ข้างบนอ้างว่า Phase 6 latency ผ่านแล้ว

**ก่อนเริ่ม implementation เจ้าของต้องระบุ:** ผู้ใช้รายแรก + client (Claude Code / Claude Desktop / อื่น ๆ / ยังไม่มีผู้ใช้จริง) และข้อมูลที่จะให้ client นั้นเห็น. ถ้าเลือก desktop/direct agent ต้องยืนยันว่าผู้ถือ key เห็นทุกแถวของ contexts ที่อนุญาตได้ และคำตอบส่งถึง provider ของ client ได้; ถ้าไม่ใช่ให้ใช้ trusted proxy หรือ PoC สังเคราะห์ก่อน

## 3. สถานะ ณ จุดหยุดถาม

- ข้อ 0 baseline/backup ✅; ข้อ 1 สำรวจ code/SDK/client ที่ติดตั้ง ✅ (ผู้ใช้รายแรกยังไม่ระบุ); ข้อ 2 แผนย่อยพร้อมพิจารณา
- **ยังไม่มี external endpoint หรือ production config เปลี่ยน**; SDK probe เป็นของทดลองแยก ไม่ใช่ facade ที่ส่งมอบ
- Plan 1B-C / REMAIN-8 **ยังไม่ปิด**; ยังไม่ทำข้อ 3–7 และยังไม่เริ่ม Phase 7
- การหยุดนี้มาจาก **คำสั่งเจ้าของใน prompt ข้อ 2** โดยตรง ไม่ใช่ skill หรือข้อจำกัดเครื่องมือ
