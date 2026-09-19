# FIX NOTES — สิ่งที่พบระหว่าง execute แผน (ไม่แก้ทันที ตามกฎ)

## จาก F1 (2026-07-11)

- **F1.3 frontend QA:** `frontend/components/Chat/ModelSelector.tsx` auto-select default provider จาก `/admin/config/ai/providers` (`is_default`) แล้ว `frontend/app/(app)/index.tsx` ส่ง `provider` ชัดเจนทุก request — ไม่มี hardcode "gemini" ฝั่ง frontend ถ้า API ล่มจะ fallback (ดู adminService.ts) — พฤติกรรมยอมรับได้ ไม่ต้องแก้
- **F1.4:** `SchemaService._cache` (`set_cached_value` ใน `app/services/schema/service.py:88`) ไม่มี eviction — โตไม่จำกัดในทางทฤษฎี แต่ key space เล็ก (provider×context×language×วัน) และ instance ถูกสร้างใหม่บ่อย ยอมรับได้ระยะนี้; ถ้า SchemaService กลายเป็น singleton ค้างนาน ควรเพิ่ม TTL eviction
- `app/api/v1/query.py` (stateless API) ไม่ส่ง `provider` เลย → ใช้ admin default โดยธรรมชาติ ไม่มี B3 pattern

## จาก F2 (2026-07-11)

- **datetime migration:** ทั้ง repo ใช้ `app.core.time_utils.utcnow()` (naive UTC — semantics เดิมของ `datetime.utcnow()`) เพราะ DB columns เก็บ naive datetime — **migration ไป timezone-aware ทั้งระบบเป็นงานอนาคต** (ต้องทำพร้อม DB migration)
- **`AdminConfigService()` ที่ยังสร้าง per-call โดยไม่ close:** `app/api/v1/admin/config.py`, `providers.py`, `analytics.py`, `vanna_docs.py`, `_shared.py`, `app/services/admin_agent.py` — อยู่นอกขอบเขต F2.1 (B4 ระบุเฉพาะ `deps.get_ai_service` + `QueryEngine.__init__`) แต่เป็น pattern เดียวกัน ควรย้ายมาใช้ `deps.get_admin_config_service` ในรอบถัดไป
- **`tests/unit/test_db_separation.py`** มี assertion เกี่ยวกับ session — ผ่านอยู่ ไม่แตะ

## จาก F4 (2026-07-11)

- **⚠️ ต้องถามเจ้าของโปรเจกต์:** `app/services/schema/view_manager.py:57-60` **เขียนลง business DB** (CREATE/DROP VIEW ผ่าน `business_engine`) — เป็น admin feature (view manager) ที่ตั้งใจ ดังนั้น F4.1 จึง**ไม่ได้**ทำ `business_engine` ฝั่ง app เป็น read-only (ทำเฉพาะ MCP servers ซึ่งเป็น reader ล้วน) — ถ้าต้องการ RO ฝั่ง app ด้วย ต้องแยก engine สำหรับ view_manager ก่อน
- **`app/services/database_adapter.py` และ `app/services/business_db.py` ไม่มี production caller** (business_db มีแค่ test import) — เป็น dead module ควรพิจารณาลบในรอบ cleanup
- validate_sql delegation: import `app.services.validation_service` จาก MCP process ใช้เวลา ~0.07s — ไม่มีปัญหา startup

## จาก F5 (2026-07-11)

- **Manual webhook end-to-end ยังไม่ได้ทดสอบ** — ต้องใช้ bot token จริง + tunnel (ngrok/cloudflared) ซึ่งไม่มีใน environment นี้ — โค้ด initialize/set_webhook/delete_webhook เขียนตาม PTB 22 docs และ unit tests ผ่าน แต่ acceptance ข้อ "Manual webhook end-to-end" ค้างไว้ให้เจ้าของโปรเจกต์รัน (ขั้นตอนอยู่ใน PLAN_F5 หัวข้อการทดสอบ)
- python-telegram-bot ติดตั้งเฉพาะ system python3.10 (ไม่อยู่ใน venv) — venv ที่ใช้รัน pytest ไม่มี PTB แต่ tests mock หมดจึงผ่าน

## จาก F7 (2026-07-11)

- **`app/services/cost_service.py` ไม่มี caller เลย** (dead module เหมือน database_adapter/business_db) — F7.2 ข้อ 5 จึงไม่มีอะไรต้อง wire; ถ้าจะใช้จริงต้องเรียก `calculate_cost` จาก usage_breakdown ที่มีแล้ว (input/output แยกให้แล้ว) — พิจารณาลบหรือ wire ในรอบถัดไป
- trace ถูกสร้าง/emit ที่ระดับ **QueryEngine** (ไม่ใช่ hybrid_flow) เพื่อให้ cache hit ถูก trace ด้วย — hybrid_flow เติม stages/usage ผ่าน parameter
- mcp mode (`query_with_retry`) ยังไม่ผูก trace/stage breakdown — tokens จาก generate_sql ของ provider ถูกรวมอยู่แล้ว (ไม่ hardcode) แต่ไม่มี per-stage breakdown — ยอมรับได้เพราะ hybrid คือ default

## จาก F8 (2026-07-11)

- **`TWO_PASS_ENABLED` ยังคง default OFF** — F8 ทำให้ Pass 1 พร้อมใช้ (structured output + fallback) แต่การเปิด flag ถาวรรอเทียบ eval (F3-B baseline) ก่อน — decision ของเจ้าของโปรเจกต์
- **Gemini structured output ใช้ mime json + schema ใน prompt** (ไม่ใช่ `response_schema`) — การแปลง JSON Schema → google-genai Schema type เปราะต่อเวอร์ชัน SDK; วิธีที่เลือกเสถียรกว่าและยอมรับตามแผน
- **งานอนาคต:** เปลี่ยน main SQL generation path เป็น structured output — ยังไม่ทำเพราะ CoT + ```sql fence ทำงานอยู่และต้องมี eval คุมก่อน
- Manual smoke ที่ต้องเปิด two_pass + ยิงคำถาม follow-up 3 แบบกับ key จริง — ค้างให้เจ้าของโปรเจกต์ (env นี้เรียก LLM ผ่าน default provider ได้ แต่การเปิด two-pass ใน admin_config เป็น state change ที่ควรทำใน dev ของทีม)

## จาก F9 (2026-07-11)

- **Phase E (heuristic router) ไม่ได้ implement** — decision-gated ตามแผน ต้องอนุมัติก่อน
- **Intent state ใช้ in-memory dict (TTL 1 ชม.)** แทน DB column — เหตุผล: zero migration, เสียแค่ latency optimization เมื่อ restart (fallback เงียบ), app รัน single-process; ถ้าย้ายเป็น multi-worker ต้องย้ายไป Redis/DB
- ยังไม่มี flag ใดถูกเปิด — `archive/RESULT_F9.md` มี measurement protocol รอรันเมื่อจะเปิด

## จาก F10 (2026-07-11)

- Import จริงผ่านครบ 4 gates — ดู `plan/archive/RESULT_F10.md` (ค่าถูก 14/14 value-based; strict exact-match 0/14 เพราะ alias ไม่ตรง golden; YTD rule พิสูจน์แล้ว)
- ข้อ eval ที่ตก 1 ข้อ: โมเดลใส่คอลัมน์ `bu` เกิน → column-count mismatch (ค่าน่าจะถูก) — พิจารณาผ่อนเกณฑ์เทียบ (ignore constant label columns) ในรอบปรับปรุง eval
- `vanna_documentation` มีจริง + `mark_brain_dirty()` มีจริง — ใช้เส้นทาง DB-driven docs ตามแผน (ไม่มีของค้าง migrate)
- Acceptance "ถามผ่าน UI 5 คำถาม" ค้าง manual (ต้องเปิด frontend)

## จาก F12 (2026-07-13)

- **app.db size ก่อน/หลัง migration:** 8,368,128 bytes ทั้งก่อนและหลัง (`ALTER TABLE ADD COLUMN` เป็น schema-only change ใน SQLite ไม่ rewrite ทั้งไฟล์; แถวเก่าได้ `NULL` โดยไม่เพิ่มขนาด) — QA จริงที่เพิ่ม 2 conversation ทำให้ไฟล์โตชั่วคราว แต่ลบ test data ออกหมดแล้วก่อนบันทึกตัวเลขนี้ ดังนั้นตัวเลข "หลัง" นี้ยังไม่สะท้อน steady-state growth จริงจาก `result_data` — ต้องรอ production traffic สะสมสักพักก่อนตัดสินใจเรื่อง retention job
- **Baseline pytest ในแผนคลาดเคลื่อน:** แผนระบุ baseline `363 passed, 3 skipped` (ค่าจาก PLAN_FIX_MASTER ตอน 2026-07-11) แต่ตอนเริ่มงานจริง (2026-07-13) วัดได้ `617 passed, 3 skipped` แล้ว (มี test เพิ่มจากงานอื่นระหว่างทาง) — ใช้ 617 เป็น baseline จริงแทน ไม่ใช่บั๊ก แค่เอกสารไม่ sync
- **raw-SQL DDL fixture drift:** `tests/unit/test_auto_analyzer.py` และ `tests/unit/test_feedback_enhanced.py` สร้าง `chat_history` ด้วย SQL ดิบ (ไม่ใช่ `Base.metadata.create_all`) จึงไม่ sync กับ ORM model อัตโนมัติ — ต้องแก้ DDL เพิ่ม `render_meta`/`result_data` ด้วยมือ (in-scope เพราะจำเป็นให้ suite เขียว ไม่ใช่ scope creep) — **รูปแบบนี้จะเกิดซ้ำทุกครั้งที่มีคน migrate `chat_history` ในอนาคต** ควรพิจารณาเปลี่ยน fixture 2 ไฟล์นี้ไปใช้ `Base.metadata.create_all` แทนในรอบ cleanup ถัดไป เพื่อไม่ต้อง sync มือทุกครั้ง
- **codex review พบ 2 bugs จริง หลังจบ Phase C** (แก้แล้วใน commit `7416fe3`, มี test คุม): (1) `_persist_chart_only_switch` เลือกแถวผิดถ้า turn ล่าสุดเป็น text-only/error (มี `render_meta` แต่ไม่มี `result_data`) — เพิ่มเงื่อนไข `result_data IS NOT NULL`; (2) `_safe_json` ป้องกันแค่ JSON syntax เสีย ไม่ป้องกัน shape ผิด (valid JSON แต่ไม่ใช่ dict/list ตามที่ควร) — เพิ่ม `expected_type` param
- **Phase A.4 หมายเหตุ:** `msg["chart_config"]` (จาก `GET /conversations/{id}`) ไม่เท่ากับ `chat_response["chart_config"]` (จาก `POST /chat/`) แบบ 1:1 เพราะ `/chat/` re-serialize ผ่าน `ChatResponse`/`ChartConfig` pydantic model ซึ่งเติม key ที่ไม่มีค่าเป็น `null` เพิ่ม ส่วนที่ persist ไว้เป็น raw dict ก่อน pydantic (ตามที่แผนตั้งใจ — "ใช้ Dict[str, Any] ไม่ import ChartConfig schema") — ไม่ใช่บั๊ก แต่ควรรู้ไว้ถ้าจะเขียน consumer ที่ diff สอง response นี้ตรง ๆ ในอนาคต

## จาก F11 (2026-07-11)

- **Phase A:** `pinned_filters` = รับ-log เท่านั้นใน v1 (inject เข้า intent pipeline เกิน 0.5 วันตามที่แผนให้ตัดสิน) — งานต่อ: inject เป็น filter จริงเมื่อ demand ชัด
- **Phase B/C commit แล้วใน repo NT-Report** (`c340d70`) — `$http.send` มีจริงใน PB v0.38 JSVM
- **ค้าง manual (บังคับก่อนเปิดใช้จริง):** (1) ออก API key จริงให้ portal (ดู docs/PORTAL_INTEGRATION.md), (2) E2E ผ่าน local PB — user ไม่มีสิทธิ์ → 403 ไม่มี call ออก, audit ครบ, rate limit จริง, (3) ตารางเทียบเลข 10 คำถาม vs dashboard ลง `plan/archive/RESULT_F11.md`
- Phase D (postMessage filter state, streaming) = deferred ตามแผน

## จาก Plan 7 Phase 1 — Source registry + DuckDB file source (2026-09-18)

ผลลัพธ์/ตัวเลข: `plan/archive/RESULT_P7_PHASE1.md`

**ค่า default ที่ใช้แทนการตัดสินใจ Phase 0** (บันทึกใน PLAN_7 §11.1 ด้วย): D1 = local path ต่อ source (ไม่ทำ S3/HTTPS), D2 = DuckDB, D3 = ไม่แตะ `pinned_filters`/scope

**Decision ที่ทำระหว่างทาง (ตรวจ/กลับได้):**
- **เพิ่ม `duckdb-engine` นอกจาก `duckdb`** — `SchemaService` ทั้งก้อนเป็น SQLAlchemy (`inspect()`, `text()`) ต้องมี dialect ถึงจะ inspect view ของ DuckDB ได้ (DATA_RANGE ใน prompt, dimension families) โดยไม่แก้ SchemaService
- **LIKE → ILIKE บน file source** (`_sqlite_like` ใน `database_adapter.py`) — SQLite LIKE ไม่สนตัวพิมพ์ DuckDB สน; prompt/golden/ValueVerifier/WarningDetector สร้างบนพฤติกรรม SQLite → eval รอบแรกตก 3 ข้อ (`bu LIKE '%HARD INFRA%'` ได้ 0 แถว) — SQL ที่แสดง/บันทึกยังเป็น `LIKE` ตามที่ LLM เขียน แต่รันเป็น `ILIKE`
- **อ่าน CSV ไม่ใช่ Parquet** ตามแผน แม้ bundle มี `.parquet` (sha256 ใน manifest) อยู่แล้ว — latency ผ่านเกณฑ์ จึงไม่ทำ Parquet cache (ถ้าอนาคตถามตารางใหญ่บ่อย: อ่าน `.parquet` ที่ publish มาเลยง่ายกว่าสร้าง cache เอง — CSV 186MB scan ~350ms, Parquet ~7ms)
- **SQL ของ file source รัน in-process** (ไม่ผ่าน MCP subprocess) ผ่าน `SourceBoundMCPClient` — จุดเดียวที่ครอบ hybrid execute, ValueVerifier, WarningDetector และ tool loop; `execute_select` เป็น definition เดียวที่ MCP tool ใช้ร่วม

**DuckDB 1.5.5 — option ที่ตรวจจริง (PLAN_7 §11.5):**
- `allowed_paths` ตั้งผ่าน `config=` ตอน connect **ไม่ได้** ("Cannot change/set allowed_paths before the database is started") ต้อง `SET` หลัง connect และต้องก่อน `enable_external_access=false` ("Cannot change allowed_paths when enable_external_access is disabled") แล้วค่อย `lock_configuration=true`
- read_only DB ยังให้ `CREATE TEMP VIEW` ได้ → view ชื่อเดียวกันทับของจริงได้ใน connection นั้น — แก้ด้วย cursor ใหม่ทุก query (มี test)
- ⚠️ **`lock_configuration` ไม่ได้กัน table function `enable_logging()`** (พบโดย security review, reproduce แล้ว): `SELECT * FROM enable_logging(storage='file', storage_path='/x')` ผ่าน validator แล้ว query ถัดไป **ทำ process ล่ม** (libc++abi terminate); แบบ `enable_logging('QueryLog')` ทำให้อ่าน SQL ของผู้ใช้อื่นได้ผ่าน `duckdb_logs` — แก้ด้วย query gate ใน `DuckDBFileAdapter.execute_query`: parse ด้วย `json_serialize_sql` ของ DuckDB เอง อนุญาต SELECT เดียวที่อ้าง view ที่ลงทะเบียน/CTE เท่านั้น ห้าม table function ทุกตัวและ system view (ตรวจกับ SQL จริง 58 แบบจาก eval/chat_history: ไม่ปฏิเสธผิดเลย) — `duckdb_settings()` / `duckdb_logs` ที่เคยเปิดเผย path ก็ถูกปิดด้วย gate นี้
- DuckDB ใส่ temp directory ของตัวเองใน `allowed_directories` อัตโนมัติ → SQL ที่ข้าม gate (มีแต่ code ภายในที่ใช้ `cursor()` ตรง) ยัง `COPY TO` ลง temp dir ได้ — untrusted SQL ทุกเส้นผ่าน gate จึงไม่มีทางถึง
- `allowed_paths` ถูกตรึงกับ realpath ตอน `SET` → ถ้า `latest/` เป็น symlink แล้วถูกชี้ใหม่ adapter เดิมจะอ่านไม่ได้ — resolver ใส่ realpath ของ root ใน fingerprint จึงสร้าง adapter ใหม่ให้เอง (มี test)

**Bug เดิมที่พบระหว่างไล่ query path (ไม่แก้ — พฤติกรรม legacy ต้องไม่เปลี่ยน):**
- ⚠️ `keyword_index.build_keyword_index` (admin `POST /admin/config/rebuild-keyword-index`) inspect column บน business DB แต่ `SELECT DISTINCT` บน **config DB** → SELECT ล้มทุกคอลัมน์ แต่ `DELETE` ใน transaction เดียวกัน commit → **กด rebuild = ลบ keyword index ทิ้งหมด (revenue 1679, expense 2155, pl_costtype 1271, transfer price 285 แถว) แล้วใส่ 0** (reproduce แล้วบนสำเนา config.db: revenue 1679 → 0) — `search_db_for_keyword` (value lookup ใน query path) มีรูปแบบเดียวกัน → คืน `[]` เสมอ — **แก้แล้วในงานแยก `0f3aaa7`** (commit อยู่บน branch `plan7-phase1` ด้วย; ผล/eval ดูหัวข้อ "Keyword index engine fix" ท้ายไฟล์)
- `hierarchy_service` (`detect_changes`, `bootstrap_from_view`, `get_available_views`) query view ธุรกิจบน config DB → ผลว่างเสมอ; `scripts/extract_hierarchy.py` เขียน `master_hierarchy*` ลง **business DB** (ของจริงอยู่ config DB)
- `context_onboarding` ส่ง business DB path ให้ `ConfigApplicator`/`ConfigValidator` → apply ลงผิด DB (ล้มเงียบ), validate 500; `onboarding_tools` (admin agent) เรียก method ที่ไม่มี (`inspect_view`, `onboard`) → fail ทุกครั้ง
- `vanna_service._sync_ddl` หา DDL ใน config DB → ไม่เคย train DDL เลย
- `POST /chat/train` เช็ค `isinstance(check_res, dict)` แต่ `call_tool` คืน str → SQL ผิดไม่เคยถูกปฏิเสธ
- `nt_metadata_mcp` tools query ตาราง config บน business DB → ล้มทุกตัว (ใช้แค่ tool-loop mode); `nt_validation_mcp.check_business_rules` อ่าน `schema_business_rules` จาก app.db (ไม่มีตาราง) → rules ผ่านเงียบเสมอ; `nt_validation_mcp.get_db` ไม่ได้เปิด `mode=ro` (dead code)
- `QueryEngine` ผล dedup-blocked ไม่มี `context_name` → default `"revenue"` ถูกบันทึกใน chat_history และใช้เลือก context ของ follow-up
- `prompt_builder.get_syntax_rules` อ่าน dialect จาก **config** engine (แก้เฉพาะเส้น DuckDB; legacy คงเดิม)

- Concurrency review: ทุก process เปิด view DB ไฟล์เดียวกัน → ใช้ spill dir ของ DuckDB (`<db>.tmp`, ชื่อไฟล์ตายตัว) ร่วมกัน → spill พร้อมกันทำไฟล์กันเสีย (SIGSEGV) — แก้แล้ว `temp_directory=''` (ไม่ spill; query ใหญ่เกิน memory_limit จะ error ชัด ๆ) และ resolver เก็บ adapter เดียวต่อ source (ไม่รั่ว instance ทุกครั้งที่ re-register/re-point) — `65f9ed1`

**ข้อค้าง/ข้อจำกัดใหม่ (ส่งต่อ Phase 2+):**
- **publish race** (ตัดสิน 2026-09-18: แก้สองฝั่ง): ✅ ฝั่ง AI `820052e` — ตรวจ manifest ต่อ build, stat ก่อน/หลังทุก query, `SourceUnavailable` (ไม่ใช่ SQL error → ไม่ส่งให้ LLM แก้ SQL), cache ผูก build; replay publisher แบบ NT-Report วน 20 วินาที: เดิมตอบผิดเงียบ **181** ครั้ง → **0** (ที่เหลือเป็นคำตอบถูก หรือ error "กำลัง publish") — ✅ ฝั่ง NT-Report code `7d639b0` (build ใหม่ทั้งชุด → สลับ symlink `latest`); replay layout ใหม่: 2,978 ถูก / 0 error / 0 ผิด — รอ NT-Report publish จริงครั้งแรก
- query result cache (30 นาที) ผูกกับ source + build แล้ว (`e4b2f69`, `820052e`) — publish งวดใหม่ไม่ต้อง `refresh-cache`
- runtime ตรวจ manifest ต่อ build แล้ว (`820052e`) — ที่เหลือ: re-sync knowledge อัตโนมัติเมื่อ contract เปลี่ยน + `data_as_of` (Phase 2)
- พิจารณารัน SQL ของ file source **นอก process** (แบบ MCP subprocess ของ legacy) — DuckDB รันใน API process: bug/abort ของ DuckDB ในอนาคต (แบบ `enable_logging` ที่ปิดด้วย query gate แล้ว) จะล้มทั้ง API; gate ตรวจแล้วกับทุก vector ที่ reviewer เสนอ (`query()`, `json_execute_serialized_sql`, `FROM '/path'`, comment/quote tricks, subquery) — เหลือ scalar ที่ผ่านได้แค่ตัวอ่านอย่างเดียว/no-op (`current_setting`, `getvariable`, `write_log` ขณะ logging ปิด)
- tool-loop (`mode='mcp'`, `escalation_tool_loop_enabled`): `get_sample_values`/`get_table_stats` ตอบ error สำหรับ file source (fail closed) — ยังไม่มี implementation บน DuckDB
- หน้า admin (schema browser, onboarding, dimension families, sync-brain DDL) เห็นแค่ business DB เดิม → สำหรับ `feed_*` จะเห็น **สำเนาเก่าที่ import ไว้** ไม่ใช่ไฟล์ (keyword index rebuild แก้แล้ว — scan source ของแต่ละ context, `0f3aaa7`)
- `/chat/train` validate SQL กับ legacy DB เสมอ (ไม่ route ตาม context)
- `.source_cache/<source>-<fingerprint>.duckdb` ของ fingerprint เก่าไม่ถูกลบ (ไฟล์ ~270KB ต่อครั้งที่ลงทะเบียนใหม่)
- ✅ eval ข้อ YTD (#64) แก้แล้ว 2026-09-18: NT-Report เพิ่มกฎ `ytd_point_in_time` (contract 2.0.1) → `gen_docs_from_contract` → eval file source 14/14 สองรอบ (เดิมโมเดลเขียน `month <= 5` แล้ว SUM `revenue_ytd` = 47,015,616,686.55 บาท แทน 15,749,891,371.23)

## จาก Keyword index engine fix (2026-09-18)

แก้ bug ข้างบน (หัวข้อ Plan 7 Phase 1) — `0f3aaa7` — งานแยก ไม่ใช่ Plan 7

**สิ่งที่แก้:**
- `build_keyword_index`: `SELECT DISTINCT` รันบน `service.business_engine` (source ของ context) → `DELETE`+`INSERT` ลง `keyword_value_index` บน config engine ใน transaction เดียว **หลัง** scan เสร็จ
- fail closed: scan คอลัมน์ไหน error หรือ scan ได้ 0 ค่า → **คง index เดิม** คืน 0 (เดิม error ถูกกลืนรายคอลัมน์แล้ว DELETE commit)
- `search_db_for_keyword`: SELECT บน `service.business_engine` (เดิมบน config → `[]` เสมอ)
- `POST /admin/config/rebuild-keyword-index`: ผูก SchemaService กับ source ของแต่ละ context (`source_resolver.for_context`) ไม่ใช่ global business engine — ถ้าไม่ผูก `feed_revenue` จะถูก index จาก**สำเนาเก่า**ใน legacy DB (29 งวด ถึง 202605) แทนไฟล์ (32 งวด ถึง 202608) — response มี `failed_contexts` (context ที่คง index เดิม)
- tests: config/business SQLite แยกไฟล์ 5 ข้อ (rebuild เติมใหม่, scan ล้ม/ได้ 0 ค่าไม่ลบ, search_db เจอค่า, endpoint ผูก source ต่อ context) — **fail บน code เดิมครบ 5** — full suite 700 passed, 3 skipped

**Rebuild บนสำเนา config.db** (ของจริง**ยังไม่ได้ rebuild**): code เดิม ทุก context → 0 แถว; code ใหม่ revenue 1679→6701, expense 2155→4064, transfer price 285→16821, pl_costtype 1271→1641, feed_revenue 0→47 (จากไฟล์)

**ผลต่อ prompt — ตรวจแบบ deterministic ไม่เรียก LLM** (value lookup ของ golden 63 ข้อ, code เดิม vs ใหม่, `PYTHONHASHSEED=0`):
- block "Actual Values Found" เปลี่ยน **4/63 ข้อ** ทั้งหมดเป็น feed_revenue #52/55/58/61 (`1.Hard Infrastructure` → เจอ `bu` = `1.Hard Infrastructure`) — **context legacy ไม่เปลี่ยนเลยใน golden**: keyword ที่ตกไป fallback ของ legacy (`percentile`, `COALESCE`, `radio`, ...) ไม่เจอค่าใน view — คำถามจริงที่มีคำอังกฤษตรงค่าใน data แต่ไม่อยู่ใน index จะได้ค่าจริงเพิ่ม (golden ไม่ครอบคลุม)
- ⚠️ **latency:** fallback scan จริงแล้ว — `v_expense_mart` 333k แถว ~0.2 วินาที/คอลัมน์ × ~11 คอลัมน์ ≈ **2.2 วินาทีต่อ keyword** ที่ไม่อยู่ใน index/alias — golden expense #6/17/34/36 value lookup +2.3–5.4 วินาที (อยู่บน critical path ก่อนสร้าง prompt) — ถ้าเป็นปัญหา: scan ครั้งเดียวต่อ keyword ข้ามทุกคอลัมน์ แทน 1 scan ต่อคอลัมน์ หรือ rebuild index ให้ keyword ตก fallback น้อยลง

**Eval ก่อน/หลัง** (matcha gpt-4.1 default, full 63 ข้อ, รันต่อกันวันเดียวกัน):

| | strict | incl. value_match | value_match | golden_broken |
|---|---|---|---|---|
| ก่อน (`eval_20260918_1403_default`) | 4/51 = 7.84% | 37.25% | 15 | 12 |
| หลัง (`eval_20260918_1414_default`) | 3/51 = 5.88% | 35.29% | 15 | 12 |

- ต่าง 1 ข้อ: #25 "รายได้รายสายงาน" exact_match → mismatch (หลังรอบ LLM ลืม `BUSINESS_GROUP != 'รายได้อื่น'` → 12 แถวแทน 11) — value block ของข้อนี้ว่างทุกรอบ ไม่ถูก fix แตะ → **noise ของ LLM ไม่ใช่ผลของ fix**
- 4 ข้อที่ prompt เปลี่ยน: value_match คงเดิมทั้ง 4 — SQL เปลี่ยนจาก `bu LIKE '%HARD INFRA%'` เป็น `bu LIKE '%1.Hard%'` ตาม recommendation (ค่าเท่าเดิม)
- สรุป: **ไม่มีผล accuracy ที่วัดได้** บน golden ชุดนี้ (ทั้งบวกและลบ) — ความต่าง 1 ข้อ อยู่ในระดับ noise ระหว่าง run; latency รวมของ eval 632 → 611 วินาที (LLM variance กลบ +2–5 วินาทีของ lookup)
- ⚠️ eval รอบก่อน fix ทั้งหมด (รวม baseline และผล Phase 1) วัดตอน `search_db_for_keyword` ยังคืน `[]`

**⚠️ ยังไม่ควรกด rebuild บน production:** rebuild ใช้งานได้จริงแล้ว และจะ index ทุกคอลัมน์ที่ `schema_metadata.is_groupable=1` **รวมคอลัมน์ตัวเลข** (transfer price `total_price_value` 7597 + `quantity` 5486 แถว, `gl_code`, `PRODUCT_KEY`, `month` ...) → keyword ตัวเลขสั้น 479 คำ (`10`, `20`, `25`, ...) กลายเป็น known terms ที่ match ตัวเลขในคำถาม — บนสำเนาที่ rebuild แล้ว block "Actual Values Found" เปลี่ยน **37/63 ข้อ**: ได้ค่าจริงที่ดีขึ้น (feed_revenue ได้ BU `7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม`, `8.รายได้อื่น`; ตัด keyword ขยะ `ค่า`/`io` ของ expense) แต่มี noise ใหม่ (`10`/`20` จาก "10 อันดับ", `ด้วย`) — ก่อน rebuild จริง: ทบทวน `is_groupable` ของคอลัมน์ตัวเลข หรือกรอง keyword ที่เป็นตัวเลขล้วน แล้วรัน eval กับสำเนา config.db (`CONFIG_DB_URL=sqlite:///<copy> python -m scripts.eval.run_eval`)

**พบระหว่างทาง (ไม่แก้):**
- `get_known_terms` เรียง term ยาวเท่ากันตามลำดับ `set` → ขึ้นกับ `PYTHONHASHSEED` → keyword ใน prompt สลับตัวพิมพ์ระหว่าง process (#14 `NT HOME PHONE`/`NT Home Phone`, #18 `Mobile`/`mobile`) → prompt ของ eval ไม่ reproducible ข้าม run (แก้ง่าย: sort ด้วย `(-len, term)`)
- หน้า admin Settings (`frontend-admin/src/pages/Settings.tsx`) โชว์แค่ `total_entries` — `failed_contexts` เห็นใน API response/`message` เท่านั้น

## จาก Plan 7 Phase 2 — Contract-driven knowledge + freshness (2026-09-18)

ผลลัพธ์/ตัวเลข: `plan/archive/RESULT_P7_PHASE2.md`

**Decision ที่ทำระหว่างทาง (ตรวจ/กลับได้):**
- **keywords/priority ของ context `feed_*` ตั้งเฉพาะตอนสร้าง** (เดิม `gen_docs_from_contract` เขียนทับทุกครั้ง) — ไม่งั้น re-sync อัตโนมัติจะทับ routing ที่ admin แก้; instruction/metadata/docs ยังเขียนใหม่ทุกครั้งตามเดิม (ต้องตาม contract)
- **router default:** feed context = คำโดเมนชุดเดียวกับ legacy (substring เดียวกัน เช่น "ค่าใช้จ่าย" ชน "ค่า"/"จ่าย") + marker `feed/datafeed/dashboard/แดชบอร์ด`, priority 1 → ชนะ legacy เฉพาะเมื่อมี marker (priority 1 ตัดเสมอกับ +1.0 ของ legacy revenue) — golden 63 ข้อ route เหมือนเดิม; อัปเดต `feed_revenue` ใน config จริงเป็น default ใหม่ด้วยมือครั้งเดียว
- **"ยอดขาย" (ไม่มี marker) ยังไป legacy `revenue`** (keyword `sales`/`ยอดขาย` ของ legacy) ทั้งที่ contract บอก `sales_is_not_revenue` — ไม่แก้ เพราะเปลี่ยน routing ของ legacy; ถ้าจะให้ไป `feed_sales` ต้องลบ 2 คำนี้จาก legacy revenue (admin) หลัง sales ตอบถูกแล้ว
- **knowledge key = sha ของ contract + `schema_version` ของ build** — contract อยู่นอก bundle (`DataFeed/contracts/`) ไม่ได้ publish พร้อม build; ถ้าอนาคตย้ายเข้า bundle (S3/HTTPS §13) key เดิมใช้ต่อได้
- **ปิด `feed_sales` / `feed_ebt` (`is_active=0`)** หลังพบว่าตอบเลขผิดความหมาย — source + knowledge ยังลงทะเบียนอยู่ เปิดคืนได้ทันที

**พบระหว่างทาง:**
- ⚠️ **DuckDB CSV sniffer ดูแค่ ~20k แถวแรก** → ไฟล์ที่ quote ครั้งแรกหลังจากนั้น (`fact_sales.csv` บรรทัด ~43k) ถูกอ่านเป็น `quote=''` → แก้แล้ว (pin dialect) — revenue ไม่กระทบเพราะมี quote ในช่วงต้นไฟล์
- ⚠️ **sales:** `metric` มี `actual` + `target`; contract ไม่มีกฎห้ามรวม และ `control_totals.csv` รวมทั้งสอง → golden จาก control totals ให้คะแนนคำตอบที่ถูกว่าผิด; โมเดลตอบ "ยอดขายรวม" = actual+target
- ⚠️ **ebt:** contract ไม่มี control_totals และไม่มีกฎ EBT = รายได้ − ค่าใช้จ่าย (ค่าใช้จ่ายเก็บเป็นบวก) → โมเดลตอบ "กำไร" = รายได้ + ค่าใช้จ่าย
- ebt/revenue: `schema_version` ใน manifest (build) ตามหลัง contract (1.0.0 vs 1.0.1, 2.0.0 vs 2.0.1) — ปกติ (แก้แค่กฎ ไม่ได้ build ใหม่); knowledge มาจาก contract จึงมีกฎล่าสุดแล้ว
- schema เปลี่ยนแบบเพิ่ม/ลบคอลัมน์: knowledge re-sync เอง แต่ view ใช้ชุดคอลัมน์ตอนลงทะเบียน → ต้องรัน `register_file_source` ใหม่ (ไม่ได้ทำอัตโนมัติ — การลงทะเบียนมี gate row count/control totals ที่ไม่ควรข้าม)
- value lookup บน file source: fallback scan ทีละคอลัมน์ = อ่าน CSV ทั้งไฟล์ต่อคอลัมน์ (REMAIN-10) — expense eval P50 7.07 s vs revenue 6.68 s
- ruff: unused import เดิม 2 จุด (`app/api/v1/query.py` `HTTPException`, `app/services/query_engine.py` `uuid`) — มีก่อนงานนี้ ไม่แก้

## จาก REMAIN-10 ข้อ 1 — value lookup scan ครั้งเดียว (2026-09-18)

- ⚠️ **DuckDB: `SELECT DISTINCT col … LIMIT n` ไม่ deterministic** (ไม่มี ORDER BY, aggregate แบบขนาน) → "Actual Values Found" ของ context file source อาจได้ค่าคนละชุดระหว่าง request เมื่อคอลัมน์มีค่าตรงเกิน limit
  (เรียก code เดิมซ้ำ 4 ครั้ง = 4 ผลต่างกัน) — ไม่แก้ (เพิ่ม ORDER BY = เปลี่ยนผลของ legacy ด้วย); ถ้าต้องการ prompt ที่ reproducible ให้ ORDER BY เฉพาะ dialect duckdb
- probe บน SQLite ตัดครึ่ง `UPPER(x) LIKE UPPER(kw)` ออก — เท่ากันก็ต่อเมื่อไม่มี `PRAGMA case_sensitive_like=ON` (ไม่มีที่ไหนตั้ง)

## จาก Plan 7 Phase 3 — Scope enforcement (2026-09-19)

ผลลัพธ์/ตัวเลข: `plan/archive/RESULT_P7_PHASE3.md`

**Decision ที่ทำระหว่างทาง (ตรวจ/กลับได้):**
- **scope ผ่าน ContextVar (`request_scope`) ไม่ใช่ส่ง parameter** — resolver ทุกจุดใน request (prompt, value lookup, verifier, warning detector) ได้ scope เองโดยไม่ต้องแก้ signature; ลืมส่งที่ไหน = รั่ว จึงเลือกแบบ default-on
- **legacy ที่มี scope รัน in-process** (ไม่ผ่าน nt_query MCP) — TEMP view ต้องอยู่บน connection เดียวกับ query; legacy ไม่มี scope ไม่เปลี่ยน
- **ใช้ parser ของ DuckDB ตรวจ SQL ของ SQLite** — parse ไม่ผ่าน = ปฏิเสธ (fail closed); SQL จริง 1,548 ชุดตัดสินเหมือนเดิมทุกชุด
- **ตารางที่ไม่มีคอลัมน์ของ scope = ใช้ไม่ได้** (รวม dim) — ปลอดภัยไว้ก่อน รอเจ้าของประกาศ `scope_exempt`
- **scope_columns ของ legacy = ชื่อคอลัมน์เท่านั้น** (ไม่รับ expression เช่น `year*100+month`) — กัน SQL จาก config; revenue legacy ใช้ key `year`/`month` แยก
- ตั้ง `scope_columns` ใน config จริงเฉพาะ period (`feed_revenue`, `feed_expense`) — org ให้ contract เป็นคนประกาศ

**พบระหว่างทาง:**
- ⚠️ **gate ของ Phase 1 มี bypass (CTE scoping)** — review อิสระพบ; แก้แล้ว `525c5b6` (รายละเอียดใน RESULT_P7_PHASE3) — ไม่เคยถูกใช้จริงเท่าที่ตรวจได้จาก chat_history (1,548 SQL ตัดสินเหมือนเดิม)
- DuckDB: TEMP object อยู่ใน catalog `temp` schema `main` → `main.<view>` ใน TEMP view ชี้กลับหาตัวเอง (infinite recursion) ต้องอ้าง `"<db catalog>".main.<view>`
- SQLite: ชื่อตารางใน body ของ view ใน main resolve ภายใน main เสมอ → shadow ตาราง raw ด้วย TEMP view ว่างได้โดย view หลักยังอ่านข้อมูลจริง
- ต้องบอกโมเดลใน prompt ว่าตารางหลักใช้ไม่ได้ภายใต้ scope — ไม่งั้นโมเดลวนใช้ main view จนหมดรอบ retry
- `tests/unit/test_vanna_documentation.py` รันไฟล์เดี่ยว ๆ error 12 ข้อ (pandas circular import บน py3.14) — มีก่อนงานนี้, full suite ผ่าน

## จาก Plan 7 Phase 2 รอบปิด sales/ebt (2026-09-19)

ผลลัพธ์/ตัวเลข: `plan/archive/RESULT_P7_PHASE2.md` หัวข้ออัปเดต 2026-09-19

**Decision ที่ทำระหว่างทาง (ตรวจ/กลับได้):**
- `control_totals.bg_key` **ไม่ default เป็น `bu` แล้ว** — ไม่มี = source ยอดรวมอย่างเดียว (อ่านแบบเดียวกับ `feed.py` ของ NT-Report); contract ทั้ง 4 ประกาศ `bg_key` ชัดอยู่แล้ว ยกเว้น ebt ที่ตั้งใจไม่มี
- `filter` ใช้กับ source เท่านั้น — grand-total dataset ที่แยกต่างหากไม่ถูกกรอง (คอลัมน์ของ filter เป็นของ source)
- instruction ของ `feed_*` เพิ่มบรรทัดวิธีกรองงวดเมื่อ contract ไม่มีคอลัมน์ `year` (generic จาก `period_key` ไม่ hardcode โดเมน) — revenue ไม่เปลี่ยน; knowledge key ไม่รวม code → context เดิมได้บรรทัดนี้เมื่อ contract เปลี่ยนหรือลงทะเบียนใหม่ (expense ได้แล้วจาก re-sync 1.2.0)
- **เปิด `feed_ebt` แล้วปิดกลับ** ในรอบเดียวกัน หลังพบว่า NT-Report เปลี่ยนนิยามยอดรวมระหว่างงาน — golden 12 ข้อเก็บไว้แบบ `is_active=0`

**พบระหว่างทาง:**
- ⚠️ **two-pass + contract ที่ไม่มีคอลัมน์ year/month:** Pass 1 คืน `time_range {year, month}` → Pass 2 เขียน `year = 2025 AND CAST(month AS INTEGER) = 1` ก่อนเสมอ → Binder error → retry (ทุกข้อของ sales/ebt); expense ไม่เป็นเพราะ golden ของมันอยู่ใน Vanna เป็น few-shot — แก้ด้วยบรรทัดใน instruction (`9ec6666`)
- ⚠️ **main view = `control_totals.source`** ใช้ได้เมื่อ source มีมิติ (revenue `fact_bu_monthly`, sales/expense = fact หลัก) แต่ ebt 1.1.0+ source คือตารางยอดรวมที่ไม่มีมิติ → prompt two-pass ("ต้องใช้ตาราง main view เท่านั้น") ทำให้คำถามรายสายงานได้ยอดรวม — ยังไม่แก้ (ผูกกับการตัดสินนิยาม ebt)
- ⚠️ **golden จาก control totals ตรวจตัวเลข ไม่ได้ตรวจความหมาย** — ebt 1.2.1 ได้ 12/12 ได้ทั้งที่คำถามพูดว่า "เดือน … ทั้งบริษัท" แต่ค่าเป็น YTD ของ 2 สายงาน; `agg` ของ measure ใน contract (`sum` vs `point_in_time`) คือสิ่งเดียวที่บอก generator ว่าต้องถามแบบไหน
- `register_context` ตั้ง `is_active=1` ทุกครั้งที่ sync — context ที่ admin ปิดไว้ไม่ถูก re-sync เอง (resolver ข้าม context ที่ปิด) แต่ `register_file_source` จะเปิดคืน → ลงทะเบียน ebt ใหม่ต้องปิดเองอีกครั้งถ้ายังไม่พร้อม
- eval 1 ข้อ `execution_failed` detail ว่าง latency 61 s = gateway timeout (ไม่เกี่ยวกับ SQL) — `run_eval` เก็บ `str(e)` ซึ่งว่างสำหรับ timeout

## จาก REMAIN-10 ข้อ 2 — rebuild keyword index (2026-09-19)

- `2243fbe`: ตัดสิน "ตัวเลข" จาก**ค่า** (`isinstance(value, str)`) ไม่ใช่ type ของคอลัมน์ — `unit_price` ของ transfer price เก็บเป็น text จึงยังถูก index ทั้งค่า (211 คำ) แต่ไม่ถูกแตกเป็นคำสั้น
- config.db จริง rebuild แล้ว → prompt ของ context legacy เปลี่ยน (block "Actual Values Found") — eval ก่อน/หลัง 30/63 → 31/63; ตัวเลขและ noise ที่เหลือใน `PLAN_REMAINING_ITEMS.md` REMAIN-10
- อ่านตัวเลข eval: 30–31/63 รวม feed 26 ข้อ (26/26) — ส่วน legacy = 4/37 → 5/37 เท่าระดับเดิมของ 2026-09-18 (19/51 รวม feed_revenue 14) ; golden legacy ส่วนใหญ่ mismatch จากรูปผลลัพธ์/alias ไม่เกี่ยวกับงานนี้

## จาก REMAIN-9 (2026-09-19)
- 9.4: DDL ที่ train เพิ่มจะมีผลเมื่อ admin กด Sync Brain — ยังไม่ได้วัดผลต่อ eval
- 9.5: `extract_hierarchy.py` เลิกรับ `--db` (อ่านข้อมูลผ่าน source ของ context, config ผ่าน CONFIG_DB_URL) — ไม่มี caller ที่ส่ง `--db`
- 9.8: `get_business_rules(revenue)` ของ nt-metadata คืน 0 rule — ตารางอ่านได้แล้ว แต่ filter ของ tool อาจไม่ตรงกับข้อมูล (ไม่ได้ไล่ต่อ — tool-loop เท่านั้น)
