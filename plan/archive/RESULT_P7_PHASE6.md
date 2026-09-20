# RESULT Plan 7 Phase 6 — MCP สำหรับผู้เรียกภายนอก

**สถานะ:** ✅ facade ใช้งานได้หลัง flag (ปิดเป็นค่าเริ่มต้น) — ข้อ 0–5 และ 7 เสร็จ, ข้อ 6 (widget) ไม่ทำ; ต่อ Claude Code จริงผ่านแล้วบนสำเนา DB; **ยังไม่เปิดบน DB จริง / ยังไม่ออก key จริง** (ดู §9)
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

---

## 4. เจ้าของตัดสิน (2026-09-20) — ตอบข้อค้างของ prompt ข้อ 2

| เรื่อง | ตัดสิน |
|---|---|
| Client รายแรก | **Claude Code บนเครื่องนี้ + สำเนา DB** (key ทดสอบบนสำเนา, อ่าน `feed_*` จริง) และ**ตัวอย่าง client ใน repo** (Python, MCP SDK) |
| Transport / ที่รัน | **stateless Streamable HTTP ใน FastAPI เดิม** ที่ `/api/v1/mcp`; ไม่ทำ legacy SSE, ไม่แยก process |
| Tools | `ask` / `list_contexts` / `source_status` เท่านั้น; `ask` มี `include_data` (แถวถูก cap); **ไม่มี `include_sql` — ไม่คืน SQL** |
| `scope` | (ก) สิทธิของ key = workspace / allowlist เท่านั้น — scope ที่ส่งมากรองให้แคบลงได้ แต่ไม่ใช่สิทธิระดับแถว |
| policy ≠ `full` | (ก) **ปฏิเสธบนช่องทาง MCP** — อ่าน policy ไม่ได้ = ปฏิเสธ |
| History | stateless เหมือน `/api/v1/query` |

## 5. ตรวจทานผลสำรวจ §1–2 ด้วย agent อิสระ 6 + ตรวจซ้ำ 6 (อ่านอย่างเดียว)

ข้อเท็จจริงใน §1–2: **82 ยืนยัน / 16 ไม่แม่น / 1 ตรวจไม่ได้ / 0 ผิด**. สิ่งที่ §1–2 ไม่ได้พูดถึงและมีผลกับการออกแบบ (ทุกข้อผ่านการตรวจซ้ำ):

1. **`policy_for_context` fail open** สำหรับกติกา "อ่านไม่ได้ = ปฏิเสธ": registry ที่ยังไม่ migrate / ไม่มีแถว = `full`, จับชื่อแบบ exact ไม่กรอง `is_active`. **config.db จริงยังไม่มีคอลัมน์ `llm_data_policy`** → facade ต้องมีตัวอ่านแบบเข้มของตัวเอง
2. **FastMCP ส่ง `str(exception)` ให้ client ตรง ๆ** (`Error executing tool ask: …`) และ REST เองก็ใส่ข้อความ exception ใน `answer` / `error` / `parts[].error` (`query.py`, `hybrid_flow.py:925-928`, `multi_context.py:320`) — มี path ไฟล์และ SQL ได้
3. **HTTP non-2xx ฆ่า session ของ MCP client** (ไม่ใช่ error ที่อ่านออก) → 401 ใช้กับ key ที่ใช้ไม่ได้เท่านั้น; โควตา / refusal ต้องเป็น tool error
4. **stateless ไม่ต้อง `initialize`**: `tools/call` เป็น request แรกได้ → "ปฏิเสธก่อนเปิด session" ต้องเป็น "ทุก HTTP request"; GET เปิด stream ค้างไม่มีกำหนด
5. หน่วยโควตาที่ §2 เสนอ (1 HTTP request = 1 usage) ทำให้ 1 คำถาม = 3–4 usage และไม่ตรงกับ "rate limit เดียวกับ REST" → เปลี่ยนเป็น **1 tool call = 1 usage**
6. `APIKey` (ORM) ใช้นอก session ที่ commit แล้วไม่ได้ (`DetachedInstanceError`) → principal ต้องเป็นค่าธรรมดา
7. `app/main.py` **เปิด CORS ทั้งแอป** (dev: ทุก origin ของ localhost + credentials + ทุก header) — prompt เข้าใจว่าไม่เปิด; `docs/PORTAL_INTEGRATION.md` ก็เขียนว่าไม่เปิด
8. Mount ที่ `/api/v1/mcp` = 307 บน URL ไม่มี `/` ท้าย และ `request.app` ใน sub-app ไม่ใช่ FastAPI ตัวแม่ → ใช้ `Route` ตรงไปที่ ASGI handler ของ SDK แทน
9. `channel` ของ REST มาจาก `source` ที่ผู้เรียกส่งเอง → `channel='mcp'` ปลอมได้
10. ของเดิมที่พบระหว่างทาง (ไม่ได้แก้ — ดู §9; ส่วน `track_usage` ที่ไม่ atomic แก้แล้วใน §8): `mcp_servers/claude_desktop_config.json` + README สอนต่อ `nt-query` (SQL ดิบ) เข้า Claude Desktop ตรง ๆ; `execute_query(validate_first=False)` ผู้เรียกปิด validator ได้; Redis ไม่ได้รันบนเครื่องนี้ (limit รายนาที fail-open)

Client (ตรวจกับ binary + เอกสารทางการ): Claude Code 2.1.270 รองรับ HTTP + header + ขยาย `${VAR}`; Claude Desktop remote connector ออกจาก cloud ของ Anthropic → เข้า localhost ไม่ได้; Claude Code เลิกแนะนำ SSE และ Codex ไม่มี SSE → ยืนยันการไม่ทำ legacy SSE

## 6. สิ่งที่สร้าง

```text
MCP client ──POST /api/v1/mcp (X-API-Key ทุก request)──▶ Gate (ASGI ล้วน, หน้า transport)
   flag admin_config.mcp_external_enabled (ปิด = 404) · GET/DELETE = 405
   APIKeyService.authenticate (ไม่มี side effect) + เจ้าของ active + scope query/full + key ต้องผูก workspace/allowlist → ไม่ผ่าน = 401
        ▼ SDK transport (stateless, ตรวจ Host/Origin จาก MCP_ALLOWED_HOSTS / MCP_ALLOWED_ORIGINS)
   tool call: validate_key + track_usage (= 1 usage ของ REST) → Principal(allowed, usable = allowed ∩ source policy 'full' แบบอ่านเข้ม)
   ask → run_simple_query (ตัวเดียวกับ POST /api/v1/query) → multi_context.ask → QueryEngine.query   [allowed_contexts = usable]
   list_contexts → contexts_for(usable) · source_status → canonical_context(usable) แล้วจึง resolve
        ▼ ขาออก: ตัด SQL, ตัดข้อความ error, ทิ้งคำตอบที่ llm_policy ≠ full → code + ข้อความตายตัว + request_id
```

- `app/api/v1/mcp_facade.py` (ใหม่, ไฟล์เดียว) — ไม่มี provider call ของตัวเอง, ไม่แตะ ContextVar, ไม่ proxy MCP ภายใน
- `app/api/v1/query.py` — แยก `run_simple_query` / `contexts_for` ให้ REST กับ MCP ใช้ร่วม (สัญญาของ REST เดิม — test เดิม 71 ข้อผ่านโดยไม่แก้); `_rest_channel`: REST เขียน channel ที่ขึ้นต้น `mcp` ไม่ได้ (`api:mcp…`)
- `APIKeyService.authenticate` = ครึ่งที่ไม่มี side effect ของ `validate_key` (พฤติกรรม `validate_key` เดิม)
- `deps.enforce_key_surface` รู้จัก `/api/v1/mcp`; `config.py`: `MCP_ALLOWED_HOSTS`, `MCP_ALLOWED_ORIGINS` (ว่าง = ปฏิเสธทุก Origin), `MCP_MAX_ROWS=100`; flag โผล่ใน `get_feature_flags`
- `app/main.py`: `Route` (ไม่ใช่ mount — ไม่มี 307, `request.app.state.mcp_client` ใช้ได้) + `session_manager.run()` ใน lifespan
- policy ≠ full: ใช้ **เซต `usable` เป็น `allowed_contexts` ของ engine** → routing อัตโนมัติ, ผู้สมัครของ multi-context, cache key (`|allow:`), `request_pinned` อยู่ในเซตนี้ด้วยกลไกเดิม; ระบุชื่อ context ที่อยู่ในสิทธิ์แต่ไม่ `full` = `policy_refused`; ตรวจ `llm_policy` ของผลลัพธ์ (และทุก part) ซ้ำก่อนส่งออก
- `scripts/mcp_client_example.py` — ตัวอย่าง client + ตัววัด latency; `docs/manuals/manual_mcp_external.md`

## 7. Exit criteria — ตัวเลข

| Exit | ผล |
|---|---|
| pytest | **1035 passed, 3 skipped** (baseline 997/3; +38 ใน `tests/unit/test_mcp_facade.py` — SDK client จริงผ่าน ASGI, DB ชั่วคราว); รันบนสำเนา, SHA-256 ของ `config.db` / `app.db` จริงเท่าเดิม |
| REST ไม่เปลี่ยน | test เดิมของ `/api/v1/query` 71 ข้อผ่านโดยไม่แก้ |
| tools/list | 3 ชื่อพอดี; คำอธิบาย tool + `list_contexts` ไม่มีชื่อ context นอกสิทธิ์ |
| ไม่มี key / key ผิด / key ไม่ผูก workspace / ไม่มี scope `query` | 401 ที่ `tools/call` **โดยไม่มี handshake**; SDK client ไม่ได้ tool list |
| revoke กลาง session | request ถัดไป = 401 |
| โควตา | handshake + tools/list = 0 usage, 2 tool calls = 2 usage; โควตารายวันที่ใช้หมดทาง REST → `rate_limited` ทาง MCP |
| refusal อ่านออก | `invalid_scope` / `context_not_allowed` / `policy_refused` / `rate_limited` / `duplicate_request` / `query_failed` / `internal_error` — รวม refusal ที่ถูกห่อใน ExceptionGroup; context ที่ไม่มีอยู่กับ context นอกสิทธิ์ได้คำตอบเดียวกัน |
| ไม่มี SQL / ข้อความ exception / path | ตรวจด้วย sentinel ใน result ทั้งก้อน (single, part ของ multi-context, exception, `source_status`) |
| policy ≠ full | ไม่อยู่ใน `list_contexts`; ระบุชื่อ = `policy_refused`; ผลลัพธ์ที่ `llm_policy` ≠ full / None ถูกทิ้ง; registry ไม่ migrate / config อ่านไม่ได้ = เซตว่าง |
| สอง key พร้อมกัน | `QueryEngine.query` ตัวจริง: แต่ละ call เห็น scope ของตัวเอง, `request_pinned=True`, หลังจบค่ากลับเป็น default |
| Host / Origin | Host แปลก = 421, มี Origin = 403 |
| Client จริง | **Claude Code 2.1.270** (`claude -p --mcp-config … --strict-mcp-config`, key จาก `${NT_AI_API_KEY}`): `list_contexts` → `feed_*` 4 ตัว; `source_status feed_sales` → ok / 202608 / schema 1.3.0; `ask` (feed_sales, LLM จริง) → 3,480.99 ล้านบาท; `source_status revenue` → `context_not_allowed`. audit: `channel = mcp:claude-code/2.1.270`, `api_key_id`, workspace `nt-report` |
| Latency (uvicorn py3.10, สำเนา DB, key + คำถามเดียวกัน, สลับกัน, เว้น 5.1 s กัน dedup) | เส้นทาง cache n=12: REST P50 **12.9** / P95 **17.6** ms — MCP P50 **19.5** / P95 **29.0** ms → overhead +6.6 / +11.4 ms (เป้า ≤100 ms); คำตอบแรก LLM จริง: REST 7.4 s, MCP 8.1 s (คนละคำถาม — provider เป็นตัวกำหนด) |
| ข้อ 6 widget | **ไม่ทำ** — ไม่มี client ที่ 2 ที่ต้องการ; NT-Report ใช้ panel + PB proxy ของตัวเอง |

## 8. Review อิสระ (agent แยก อ่านอย่างเดียว) — commit `f868b91` + `fd67d07`

5 มุม (gate / ข้อมูลขาออก / concurrency-lifecycle / REST regression / ความแข็งของ test), finding แต่ละข้อส่งให้ agent อีกตัวพยายามหักล้าง. ผู้ตรวจ 4 จาก 5 มุมจบ; มุม test และการหักล้าง 6 ข้อหยุดเพราะโควตา session — ข้อที่ไม่ได้หักล้างผม reproduce เองเป็น test ที่ **fail บน code เดิมทุกข้อ** (8 test) และทำ mutation check แทนมุม test. แก้ครบใน `69d896a`:

| ระดับ | Finding | แก้ |
|---|---|---|
| **high** | query ที่รันสำเร็จแต่ได้ 0 แถว: `hybrid_flow.py:776` ใส่ **SQL เต็ม** ไว้ใน explanation (`error=None`) → ออกไปเป็น `answer` | ข้อความของ engine ออกได้เฉพาะผลที่**มีแถว**; ไม่มีแถว = ข้อความตายตัว; ด่านสุดท้ายทิ้งคำตอบที่ยังมี SQL ที่รันจริงหรือ ```` ```sql ```` อยู่ |
| **high** | multi-context: `parts[].answer` ของ part ที่ fail (มี result) พาข้อความ exception / path ออกไป; part 0 แถวพา SQL ออกไป | part ที่ fail = ข้อความตายตัว + ตัด `data`; part ไม่มีแถว = ข้อความตายตัว |
| medium | `track_usage` เป็น read-modify-write: ยิงพร้อมกัน 30 call → นับได้ 3–6, เกินโควตารายวัน, `IntegrityError` แถวแรกของวัน (ของเดิม กระทบ REST ด้วย) | upsert อะตอมมิกคำสั่งเดียว (`app.db` จริงมี `UNIQUE(api_key_id, date)`); facade ตรวจเพดานซ้ำหลังนับ |
| medium | ปิด workspace ไม่ตัด key ที่ผูกด้วย allowlist อย่างเดียว | เซต context ของช่องทางนี้ต้องอยู่ใน workspace ที่ active |
| low | `X-API-Key` สองตัว: gate กับ tool เลือกคนละตัว | มากกว่าหนึ่ง = 401 |
| low | cap ของ `include_data` เป็นต่อ part (สูงสุด 4×) | แบ่งเพดานต่อ ask |
| low | `question` ว่าง = `internal_error` | `invalid_arguments` (400) |
| low | `GET /admin/query-audit?channel=mcp` ไม่เจอ `mcp:<client>` | filter ด้วย prefix `mcp:` |
| low — ไม่แก้ | argument ผิดชนิด / ชื่อ tool ที่ไม่มี ถูก SDK ตอบก่อนถึง tool: ข้อความของ pydantic (สะท้อน input ของผู้เรียกเอง ไม่มีข้อมูลของเรา) และไม่นับ usage | บันทึกใน docstring + คู่มือ; แก้ต้องแตะ API ภายในของ SDK |

ที่ผู้ตรวจลองแล้วผ่าน (ตัวอย่าง): key ใน query string / Bearer / session token = 401; key หมดอายุ / revoke / เจ้าของถูกปิด / scope อื่น = 401; allowlist `[]` หรืออ่านไม่ได้ = เซตว่าง; context ถูกปิดระหว่าง session มีผล call ถัดไป; websocket scope ไม่ถึง transport; path แปลก = 404; JSON-RPC batch ถูก SDK ปฏิเสธ (ไม่มีทาง N call ใน 1 request); `authenticate` ไม่มี side effect และ `validate_key` เหมือนเดิมทุกบรรทัด; context นอกสิทธิ์ / legacy / ไม่มีอยู่ ได้ `context_not_allowed` เหมือนกันโดย provider ไม่ถูกเรียก; ผู้เรียกเพิ่ม `max_rows` เองไม่ได้; python3.10 รันได้

Mutation check ของ test (10 mutant): ฆ่า 7 (ตัด policy filter, ตัด post-check `llm_policy`, ตัด scope check, ไม่นับ usage, ข้าม `canonical_context`, เปิด GET, ตัด row cap); 2 เทียบเท่า (ตัด `is_restricted` ยังได้ 401 จากชั้นถัดไป, `exclude sql` ซ้ำซ้อนกับ `include_sql=False`); 1 รอด (เจ้าของถูกปิด) → เพิ่ม test แล้ว

ตรวจกับ engine จริงหลังแก้: "ยอดขายรวมของปี 2099" (feed_sales) → คำตอบไม่มี SQL; คำถามปกติ + `include_data` → 3,480.99 ล้านบาท + แถว

## 9. ข้อค้าง — รอเจ้าของตัดสิน

**ก่อนเปิดใช้กับ DB จริง (ไม่ได้ทำ — ต้องสั่ง):**
1. รัน `scripts/migrate_data_sources.py` + `scripts/migrate_workspaces.py` บน `config.db` จริง (ค้างจาก Phase 4.5) — ไม่มีคอลัมน์ `llm_data_policy` = MCP ปฏิเสธทุก context
2. เปิด flag `mcp_external_enabled`, ออก key จริงที่ผูก workspace, ตั้ง `MCP_ALLOWED_HOSTS` ถ้าไม่ใช่ localhost
3. รัน Redis ในเครื่องที่ให้บริการ — ตอนนี้ limit รายนาที fail-open (ของเดิม); เพดานรายวันคือเพดานเดียวที่บังคับจริง

**การตัดสินใจที่ผมเลือกไปก่อน (เข้มกว่า REST — ผ่อนได้ถ้าต้องการ):**
- MCP รับเฉพาะ key ที่ผูก workspace / allowlist และมี scope `query` / `full` (REST ไม่ตรวจ scope `query`, รับ key ไม่ผูก)
- registry ที่ยังไม่ migrate = อ่าน policy ไม่ได้ = ปฏิเสธ (ต่างจาก `policy_for_context` ที่ถือว่า `full`)
- 1 tool call = 1 usage (handshake ไม่นับ) แทนข้อเสนอเดิม 1 HTTP request = 1 usage
- ชื่อ client อยู่ใน `channel` (`mcp:<user-agent>`) ไม่เพิ่มคอลัมน์ใหม่ใน `query_audit`
- refusal จาก policy ของ context ที่ระบุชื่อ ลง audit เป็น `ContextNotAllowed` (engine เป็นผู้ปฏิเสธจากเซต `usable`) — client เห็น `policy_refused`

**ของเดิมที่พบ — ✅ ปิดแล้วในงาน hardening 2026-09-20 (`plan/archive/RESULT_P7_HARDENING.md`):**
- ~~REST `/api/v1/query` คืน**SQL ในข้อความคำตอบ**เมื่อได้ 0 แถว แม้ `include_sql=false`, คืนข้อความ exception ใน `answer` / `error` / `parts[].error`, และคืน `str(dict)` เมื่อ explanation เป็น dict~~ → รหัส + ข้อความตายตัวจาก `app/core/outbound.py` (รวม body ของ 400 / 403 ที่ review พบเพิ่ม)
- ~~`GET /api/v1/query/contexts` เป็น public: key ผิด = เห็นทุก context ของทุก workspace~~ → ต้อง auth เสมอ, ไม่นับโควตา
- ~~REST เกินโควตา = 401 (คู่มือเขียนว่า 429)~~ → **429**; REST ยังไม่ตรวจ `has_scope('query')` (ยังค้าง)
- ~~`mcp_servers/claude_desktop_config.json` + README สอนต่อ `nt-query` (SQL ดิบ ไม่มี key / audit) เข้า Claude Desktop ตรง ๆ~~ → ลบไฟล์แล้ว, Desktop ต่อผ่าน `scripts/mcp_stdio_bridge.py`; `execute_query(validate_first=False)` ยังค้าง
- เพิ่มในงานเดียวกัน: `ai_response` หมดอายุตาม `result_retention_days`; audit เขียนไม่ได้ = ไม่ส่งคำตอบออก (เฉพาะช่องทางที่ถือ key)
- `app/main.py` เปิด CORS ทั้งแอป ขณะที่ `docs/PORTAL_INTEGRATION.md` เขียนว่าไม่เปิด
- dedup 5 วินาทีผูกกับ user + คำถาม (ไม่มี context / key): LLM client ที่ถามซ้ำเร็ว ๆ ได้ `duplicate_request`
- client ตัดการเชื่อมต่อกลางคำถาม: pipeline ทำงานจนจบ (เสีย provider call)
- `chroma_db__<workspace>/` เกิดใน root ของ repo เมื่อมีคำถามแรกของ workspace (Phase 4b) — เพิ่มใน `.gitignore` แล้ว

**ยังค้างจริง ๆ:** CORS เปิดทั้งแอป (เจ้าของยังไม่ตัดสิน), dedup 5 วินาที, client ตัดการเชื่อมต่อกลางคำถาม, Redis ไม่ได้รัน, `execute_query(validate_first=False)`, REST ไม่ตรวจ scope `query`

**ค้างจาก phase ก่อน (ไม่เปลี่ยน):** เปิด multi-context กับ `nt-report`; admin UI ของ workspaces / sources / policy / audit / flag นี้; D4 / DPO; entitlement v2 (D7) สำหรับสิทธิระดับแถว

## 10. Commits

`8d67523` สำรวจ (session ก่อน) · `f868b91` ทางเข้าร่วม REST/MCP · `fd67d07` facade + gate + 29 test · `2bcd120` ตัวอย่าง client + latency · `69d896a` แก้ตาม review · (ถัดไป) เอกสาร — **ยังไม่ push**; หยุดก่อน Phase 7

## 11. หลังปิด phase (2026-09-20 เย็น) — migrate DB จริง + ข้อตัดสินของงานถัดไป

- **`config.db` จริง migrate แล้ว** (เจ้าของสั่ง): ซ้อมบนสำเนาสดก่อน → schema ต่างเฉพาะ 4 คอลัมน์ (`data_sources.llm_data_policy` = `full` ทั้ง 5 source, `llm_provider_allowlist`, `workspaces.result_retention_days`, `store_result_data`); `app.db` ไม่เปลี่ยน (SHA เท่าเดิม); รันซ้ำ = ไม่มีแถวเปลี่ยน (ขยับแค่ `sqlite_sequence`); `quick_check` ok; context ที่ MCP ใช้ได้บนของจริง = 8 ตัว. Backup ก่อน migrate: `~/nt-ai-backups/pre-migrate-20260920/`
- ยังไม่ได้ทำ: เปิด flag, ออก key จริง, start server (start ครั้งแรกล้างผลลัพธ์เก่ากว่า 30 วัน ~1,285 แถว — เจ้าของรับแล้วโดยมี backup), Redis (เจ้าของรันเอง)
- **เจ้าของตัดสินข้อค้างของ §9:** REST แก้ครบ 4 ข้อ (SQL ในคำตอบ 0 แถว, ข้อความ exception, `str(dict)`, เกินโควตา = 429) · `GET /query/contexts` ต้อง auth เสมอ · Claude Desktop ต่อ facade ผ่าน stdio bridge + ลบ `claude_desktop_config.json` · `ai_response` หมดอายุตาม `result_retention_days` · audit เขียนไม่ได้ = ไม่ส่งคำตอบออก เฉพาะช่องทางที่ถือ key → งานอยู่ใน `plan/PROMPT_P7_HARDENING.md` (ทำก่อน go-live ของ portal)
