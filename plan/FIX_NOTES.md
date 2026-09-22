# FIX NOTES — สิ่งที่พบระหว่าง execute แผน (ไม่แก้ทันที ตามกฎ)

> **ตรวจ F1–F8 ซ้ำ 2026-09-21:** [รายงานพร้อมหลักฐาน](REVIEW_F1_F8_2026-09-21.md) — บันทึกด้านล่างเป็นประวัติ; F8 two-pass เปิดบน config จริงแล้วตาม RESULT_F11 แม้ code default ยัง OFF, F6 create/download ย้าย audit ไป `query_audit.record` แล้ว ส่วนตาราง `report_exports` บน deployment (2026-09-22: DB จริงยังไม่มี) และ F5 manual E2E ยังต้องยืนยัน · CI บน main แดง 2026-09-18..22 เพราะ mcp 2.x — pin แล้ว (ด้านล่าง)

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

- **`TWO_PASS_ENABLED` ยังคง code default OFF** — แต่ config จริงเปิด `two_pass_enabled = true` แล้วตาม `archive/RESULT_F11.md` §4.1 (2026-09-20); ข้อความ “รอเปิด” เดิมเป็นสถานะ ณ ก.ค. รอบตรวจ 2026-09-21 ไม่ได้เปลี่ยน flag
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

## จาก ebt 1.3.0 (2026-09-19 บ่าย)

- `c6e7cca`: **prompt ของ context ที่ instruction ระบุชื่อตารางอื่นของ source เดียวกัน** เปลี่ยนจาก "ต้องใช้ตาราง X เท่านั้น" เป็น "ใช้ X เป็นหลัก — ใช้ Y แทนได้เฉพาะกรณีที่คำแนะนำระบุ" (`hybrid_flow.table_rule`, 1 query ต่อ prompt) — ตอนนี้เข้าเงื่อนไขเฉพาะ `feed_ebt`; ถ้า contract อื่นเขียนชื่อ `feed_<d>_<dataset>` ลงใน business_rules ในอนาคต context นั้นจะเข้าเงื่อนไขด้วย (ตั้งใจ)
- ลอง main view = `primary_dataset` เมื่อ control source ไม่มีมิติ → 5/24 (โมเดลคำนวณยอดทางการเองจาก `fact_ebt`, ลืมรายการยกเว้น) → ไม่ใช้; main view คงเป็น `control_totals.source`
- golden ที่ถามแยก "ของเดือน" / "สะสม" ทำให้ ebt จาก 12/12 (ชุดเดิม ตรวจแค่ตัวเลข) เหลือ 18/24 — คะแนนที่ลดคือความหมายผิดที่ชุดเดิมมองไม่เห็น
- พบ: โมเดลตีความ "ก.ค. 69" (ปี 2 หลัก) เป็น 2025 ในคำถามหนึ่ง — ไม่ได้ไล่ต่อ (ไม่เฉพาะ ebt)

## จาก REMAIN-10 ข้อ 2 — rebuild keyword index (2026-09-19)

- `2243fbe`: ตัดสิน "ตัวเลข" จาก**ค่า** (`isinstance(value, str)`) ไม่ใช่ type ของคอลัมน์ — `unit_price` ของ transfer price เก็บเป็น text จึงยังถูก index ทั้งค่า (211 คำ) แต่ไม่ถูกแตกเป็นคำสั้น
- config.db จริง rebuild แล้ว → prompt ของ context legacy เปลี่ยน (block "Actual Values Found") — eval ก่อน/หลัง 30/63 → 31/63; ตัวเลขและ noise ที่เหลือใน `PLAN_REMAINING_ITEMS.md` REMAIN-10
- อ่านตัวเลข eval: 30–31/63 รวม feed 26 ข้อ (26/26) — ส่วน legacy = 4/37 → 5/37 เท่าระดับเดิมของ 2026-09-18 (19/51 รวม feed_revenue 14) ; golden legacy ส่วนใหญ่ mismatch จากรูปผลลัพธ์/alias ไม่เกี่ยวกับงานนี้

## จาก ebt 1.3.x + REMAIN-12 (2026-09-19)

- **intent ของ Pass 1 เชื่อไม่ได้ทั้งสองทาง:** บางรอบเติม filter จากกฎของ context ที่คำถามไม่ได้ขอ, บางรอบไม่ดึง filter ที่คำถามระบุ — guard จึงต้อง (ก) ยึดเฉพาะ filter ที่ค่าอยู่ในคำถาม (ข) ให้ Pass 1 รู้คอลัมน์ของตารางอื่นก่อน; ตัวตรวจแบบ substring (`column in sql`) ตั้งใจให้หลวม
- query cache 30 นาทีไม่รวมเวอร์ชัน code → ทดสอบ prompt ใหม่ต้อง `clear_query_cache()` (เจอคำตอบเก่าหลังแก้ guard)
- main view = ตารางยอดรวมทางการดีกว่า = ตารางรายละเอียด (5–6/24: โมเดลคำนวณ KPI ทางการเองจาก `fact_ebt`)
- ชื่อคอลัมน์ `expense` ชนกับคำทั่วไป → Pass 1 ใส่ metric `expense` แม้ถามรายเดือน (พลาดซ้ำ 1–2 ข้อทุกรอบ) — ชื่อแบบ `expense_ytd` จะไม่กำกวม (MAJOR ฝั่ง NT-Report — ไม่ได้ขอ)

## จาก Plan 7 Phase 4 (2026-09-19)

ผลลัพธ์/ตัวเลข: `plan/archive/RESULT_P7_PHASE4.md`

**Decision ที่ทำระหว่างทาง (ตรวจ/กลับได้):**
- **key ที่ถูกจำกัดใช้ได้เฉพาะ `/api/v1/query*`** — `/chat`, `/admin` รับ context ได้แต่ไม่รู้จัก allowlist; แก้ที่ `deps.enforce_key_surface` จุดเดียว
- **allowlist เก็บเป็นชื่อจริงใน DB** (ไม่ใช่ชื่อ normalize) และชื่อที่ผู้เรียกส่งมาถูกแปลงเป็นชื่อจริงก่อนใช้ — ที่มา: review รอบ 1 (critical)
- **`request_pinned`**: key ที่ถูกจำกัด + context legacy → รัน in-process ผ่าน `ScopedSQLite(main_view: "1")` = table allowlist จริง (เดิมมีแค่ prompt); ผู้เรียกที่ไม่ถูกจำกัดยังผ่าน MCP ตามเดิม
- **`workspace_id` NULL = `default`** ทุกจุด — context ที่สร้างหลัง migration (ลงทะเบียนใหม่ / admin UI) ไม่ต้องรู้จัก workspace
- **brain ต่อ workspace = Chroma directory แยก** (ไม่ใช่ metadata filter — Vanna base class ผูกชื่อ collection ตายตัว); `default` ใช้ path เดิม
- **gate/registration ย้ายเข้า `app/services/source_registration.py`** — app ห้าม import `scripts/`; ฟังก์ชันยัง `print` ความคืบหน้า (CLI ใช้ + test ของ importer อ่าน stdout)
- **`DATA_SOURCE_ALLOWED_ROOTS` อยู่ใน .env ไม่ใช่ admin_config** — เป็นขอบเขตความปลอดภัยของ admin API เอง (admin แก้ผ่าน UI ได้ = ไม่มีความหมาย)
- สร้าง workspace `nt-report` + ย้าย `feed_*` ใน config จริง (ย้อนได้ด้วย `PUT /admin/workspaces/{default}/contexts`); ยังไม่ได้ออก key จริง

**พบระหว่างทาง:**
- ⚠️ context ที่ resolve ไม่ได้ **ตกไป legacy DB พร้อม system prompt เปล่า** (`SourceResolver._resolve` → `LEGACY_SOURCE`, `build_system_prompt` → ข้อความ ERROR) — ปิดแล้วสำหรับ key ที่ถูกจำกัด; ผู้เรียกทั่วไปยังเป็นแบบเดิม
- anyio TaskGroup ห่อ exception ใน ExceptionGroup → branch ที่ endpoint เปิด MCP เองเคยคืน 200 + error แทน 400/403 (`b85dac4`) — ScopeError ของ Phase 3 ก็โดนแบบเดียวกัน
- test ของ QueryEngine ที่ไม่ patch `source_resolver` อ่าน `config.db` จริง (อ่านอย่างเดียว) — test ใหม่ patch ทั้งหมด
- แก้บันทึกก่อนหน้า: "expense ไม่เสีย retry เพราะ golden อยู่ใน Vanna" **ไม่จริง** — eval รันบน python3.14 ที่ vanna import ไม่ได้ และ `rag_enabled=false`; สาเหตุจริงไม่ได้ไล่ (หลังเพิ่มบรรทัดวิธีกรองงวดแล้วไม่ต่างกัน)
- NT-Report ออก contract ใหม่ 3 รอบระหว่างงาน (revenue 2.2.0→2.3.0, sales 1.3.0, ebt 1.4.0) — การเพิ่มตาราง/คอลัมน์ต้อง `register_file_source` ใหม่ทุกครั้ง (ตอนนี้ทำผ่าน `POST /admin/sources/register` ได้)

## จาก Plan 7 Phase 4.5 — Data protection (2026-09-19)

ผลลัพธ์/ตัวเลข/ตารางสำรวจ: `plan/archive/RESULT_P7_PHASE45.md`

**เจ้าของตัดสิน (2026-09-19):** D4 = **Matcha (NT Gateway) ใช้กับข้อมูลอ่อนไหวได้** · D5 = **เลื่อน** classification ต่อคอลัมน์ (4.5 ทำ policy ต่อ source เท่านั้น) · retention default = **30 วัน** · source ใหม่ = **`full`**

**Decision ที่ทำระหว่างทาง (ตรวจ/กลับได้):**
- **บังคับสองปลาย ไม่ใช่ที่ caller:** sink = `AIProvider.__init_subclass__` ห่อ 4 method ของทุก subclass (`app/core/llm_policy.py: guard_call`); source = ฟังก์ชันที่อ่านค่าจากแถว (`get_sample_values`, value lookup, value verifier, RAG, onboarding `to_dict`, keyword index, hierarchy) คืนของว่างเอง. เหตุผล: ชั้น provider เห็นแค่ string — แยก "ค่าจากข้อมูล" กับ "คำถาม" ไม่ได้ จึงปิดได้เฉพาะสิ่งที่รู้เชิงโครงสร้าง (`explain_result` มี `data`, tool loop, `history`); ที่เหลือต้องปิดที่ต้นทาง
- **taint เป็นชั้นสำรอง ไม่ใช่ตัวหลัก:** ค่าจากแถวผลลัพธ์ของ request (string ≥ 3 ตัวอักษร, ตัวเลข ≥ 5 หลัก, ไม่อยู่ในคำถาม) โผล่ใน payload = ปฏิเสธ — กัน caller ในอนาคตที่เอา `result.data` ไปต่อ prompt เอง; ใน flow ปัจจุบันไม่มี provider call หลัง execute นอกจาก explain (ซึ่งถูกตัดก่อน) จึงไม่มี false positive
- **"ความรู้ที่คนเขียน" ผ่าน, "ของที่เครื่องอ่านจากแถว" ไม่ผ่าน** — instruction/กฎ/mapping จาก contract และ admin ยังเข้า prompt ภายใต้ `schema_only` (มีชื่อกลุ่ม/ค่ามิติที่เจ้าของข้อมูลประกาศเอง); **RAG ถูกตัดทั้งก้อน** เพราะ brain ปน golden ที่ `gen_golden_from_controls` สร้างจาก control totals (รหัส/ชื่อกลุ่มจริง) แยกไม่ได้ตอน retrieve — ที่มา: review รอบ 1 (critical)
- **`aggregated_only` = ตรวจข้อความ SQL** (GROUP BY / SUM / COUNT / AVG, ไม่มี `OVER (`, ไม่มี `*`) — ไม่ใช่ k-anonymity; GROUP BY บน key ที่ไม่ซ้ำ หรือ aggregate ที่อยู่แค่ใน subquery ยังผ่าน → ของที่ห้ามเห็นรายแถวต้อง `schema_only`; k ≥ 5 ไปกับ D5
- **registry ที่ยังไม่ migrate = `full`** (ไม่มีคอลัมน์ = ไม่มีใครตั้ง policy ได้) แต่ **engine ที่ไม่ใช่ config DB เลย = `schema_only`** (`SchemaService` โหมด standalone ชี้ไป business DB) — แยกด้วย "มีตาราง config สักตัวไหม"; คอลัมน์มีแต่ NULL/ค่าแปลก = `schema_only`
- **audit เขียนไม่ได้ ≠ ไม่ตอบ** — log ERROR (`query audit NOT written`) แล้วตอบต่อ; ถ้าต้องการ fail closed สำหรับ workspace การเงิน ต้องเพิ่ม flag (ยังไม่ทำ)
- **DSR ไม่ลบแถว audit** — ตัด `user_id` + คำถามออก เหลือ SQL/จำนวนแถว/เวลา; การลบเองถูกบันทึกเป็นแถว `channel='dsr_erase'`
- **retention ล้าง `sql_result_summary` ด้วย** (= `str(data)[:1000]` แถวดิบ) ไม่ใช่แค่ `result_data`; **ไม่ล้าง `ai_response`** (คือบทสนทนา มีตัวเลขในข้อความ — ลบเมื่อ DSR เท่านั้น) ← ถ้าต้องการให้ข้อความคำตอบหมดอายุด้วย ต้องตัดสินเพิ่ม
- test เดิมที่แก้ 1 จุด: `test_scheduler.py` นับ job ตายตัว 3 → 4 (เพิ่ม job จริง)

**พบระหว่างทาง:**
- ⚠️ **`AuditService` เขียนไม่ลงมาตลอด:** INSERT ลง `audit_log` แต่ migration 028 สร้าง `config_audit_log` ที่ schema ไม่ตรง (CHECK ของ `action` = create/update/…, คอลัมน์ `created_by`) และ error ถูกกลืนที่ `logger.warning` — `config_audit_log` ใน app.db จริงมี 0 แถว; test ของมันสร้างตาราง `audit_log` เองจึงไม่เห็น → งานแยก (ไม่แก้ใน phase นี้)
  - ✅ **แก้แล้ว (2026-09-19):** เขียนลง `config_audit_log` (`INSERT`→`create`, `UPDATE`/`DELETE` → ตัวเล็ก, `user_id`→`created_by`), ค่าที่อยู่นอก CHECK ไม่เดา = ไม่เขียน, เขียนไม่ได้ = log **ERROR** + rollback; test ใช้ DDL จริงของ migration 028
  - ⚠️ **ยังค้าง 1 — audit ของ report export (F6) เขียนไม่ได้ตาม schema นี้:** `report_service.py` ส่ง `source="report_export"`, `reports.py` (download) ส่ง `action="SELECT"` — ทั้งคู่อยู่นอก CHECK และไม่ใช่ config change; ตอนนี้ log ERROR ทุกครั้ง (เดิมหายเงียบ) → ต้องตัดสิน: ขยาย CHECK (rebuild ตาราง — ไม่มีแถวให้เสียเพราะไม่เคยเขียนได้) หรือย้ายไปตาราง audit ของการเข้าถึงข้อมูล
    - ✅ **แก้แล้ว (2026-09-19) — ย้ายไป `query_audit`:** export/download คือการเข้าถึงข้อมูล ไม่ใช่ config change → `query_audit.record` (`channel` = `report_export` / `report_download`, ผู้ export, คำถาม, SQL; แถว download มี `row_count`) — ไม่ต้องแก้ schema/migration, ค้นได้ที่ `GET /admin/query-audit` (เพิ่ม filter `channel`), และ DSR ครอบคลุมอยู่แล้ว (`config_audit_log.created_by` ไม่อยู่ใน DSR). ไม่ขยาย CHECK ของ `config_audit_log` — ตารางนั้นคงไว้สำหรับ config change อย่างเดียว
  - ⚠️ **ยังค้าง 2 — admin agent tool ที่แตะ config table ใช้ session ผิด DB:** `AdminAgent(db)` รับ session ของ app.db (`deps.get_db`, telegram เช่นกัน) แล้วส่งต่อให้ tool ซึ่ง `db.query/add(SchemaSemanticMapping | SchemaBusinessRule | GoldenExample)` — ตารางเหล่านี้อยู่ใน config.db ตั้งแต่แยก DB (2026-03-21) → `add_mapping`/`add_rule`/`add_example`/`search_*` = `no such table` ก่อนถึงบรรทัด audit (ยืนยันแล้ว: `SearchMappingsTool` + `SessionLocal` บนสำเนาของ app.db → `no such table: schema_semantic_mapping`; unit test ใช้ DB เดียวจึงไม่เห็น; ประวัติ tool ใน app.db มีแต่ก่อนวันแยก DB) — ทางที่ audit เขียนได้จริงตอนนี้คือ scheduler auto-apply (ใช้ `ConfigSessionLocal` เอง + audit ลง app session)
    - ✅ **แก้แล้ว (2026-09-19):** tool ประกาศ DB ของตัวเอง (`AdminTool.database` = `config` ค่าเริ่มต้น / `app` สำหรับ analysis tools) และ caller เปิด session ให้ตรง (`tool_session()` ใน `app/tools/admin/base.py`; `AdminAgent._run_tool` แทน 3 จุดที่ส่ง `self.db`); audit ของ add tools ไป app DB เสมอ (`audit_change()`). **ด้านกลับของ bug เดียวกันใน `mcp_servers/nt_admin_mcp.py`:** ส่ง session ของ config.db ให้ทุก tool → `analyze_query_logs`/`review_feedback` (อ่าน `chat_history`) พัง และ audit หาตารางไม่เจอ → `_get_db(tool.database)`. test ใช้ DB สองไฟล์แยกกัน (`TestToolsRunOnTheirOwnDatabase`) + fixture autouse กัน test เขียน app.db จริง; ยืนยัน runtime บนสำเนาของ app.db + config.db: 6 tool ผ่าน `AdminAgent` สำเร็จ, mapping ลง config, audit 1 แถวลง app
- admin tool `search_hierarchy` เรียก `HierarchyService.search_alias` ซึ่งไม่มี (มีแต่ `search_aliases`) → tool พังอยู่แล้ว (เลยไม่รั่ว) → รวมในงานแยกข้างบน
  - ✅ **แก้แล้ว (2026-09-19):** พังสามชั้น ไม่ใช่ชั้นเดียว — `HierarchyService(db)` (class ไม่รับ argument), ชื่อ method, และ key ของผลลัพธ์ (`aliases`/`level_name` ไม่มีจริง); ไม่ระบุ context = ค้นทุก context ของ `list_contexts()`; policy ยังบังคับใน `search_aliases` ต่อ context (test: context ที่ไม่ `full` ไม่ออก)
- **`/api/v1/query` และ telegram ไม่เคยทิ้งร่องรอยคำถามเลย** ก่อน Phase 4.5 (มีแค่ตัวนับ `api_key_usage`) — ช่องทางที่ Phase 4 เปิดให้ระบบภายนอกคือช่องทางที่ตรวจย้อนหลังไม่ได้
- two-pass **ฝัง history ลงในข้อความ prompt** (`build_history_context`) — ไม่ได้ส่งทาง `history=` → ตัวกรองที่ชั้น provider มองไม่เห็น; test ดักเป็นตัวจับ → ตัด history ครั้งเดียวใน `QueryEngine`
- feature flag `rag_enabled` **ไม่ได้คุม** การดึง RAG ใน hybrid flow (`get_vanna_context_string` ถูกเรียกเสมอ; `rag_enabled=True` ที่ `query_engine` เป็นค่าตายตัวและคุมแค่รูปแบบ prompt) — ที่ config จริงไม่มี RAG เพราะ vanna import ไม่ได้บน python3.14 ไม่ใช่เพราะ flag (ที่มา: review รอบ 1; ยังไม่แก้ — เปลี่ยนพฤติกรรมของ deployment ที่รัน python3.10)
- test ที่ให้ engine สลับ provider ตาม allowlist **ยิงออกไปหา Anthropic จริง 1 ครั้ง** ระหว่างพัฒนา (เครื่องนี้มี `ANTHROPIC_API_KEY`; ข้อมูลที่ส่ง = ค่าสังเคราะห์ของ test) → test ปัจจุบัน patch `_build_provider_kwargs` ให้ hermetic; บทเรียน: test ที่สร้าง provider จริงต้องปิด key ของ provider อื่นเสมอ
- `query_correction_log` ถูกสร้างแบบ lazy โดย `AIService` — app.db จริงยังไม่มีตารางนี้

**จาก review รอบ 2:** CSV ของ audit export นำหน้า cell ที่ขึ้นต้น `= + - @` ด้วย `'`; source ที่ ≠ `full` ไม่รับ `intent_state` ของรอบก่อน (เก็บต่อ conversation อย่างเดียว — ค่า filter จาก value lookup ของ source อื่นติดมาได้); audit เขียนผ่าน `asyncio.to_thread`. **ไม่แก้:** `PolicyMCPClient` ลบ literal เฉพาะ error ที่ *คืนมา* ไม่ใช่ที่ *raise* — ตอนนี้ `execute_select` คืน dict เสมอ (raise แค่ `SourceUnavailable`) จึงไม่รั่ว แต่ tool ใหม่ที่ raise พร้อมค่าจากแถวจะหลุดเข้า retry prompt → ถ้าเพิ่ม data tool ให้คืน error เป็น dict

**ข้อค้าง (ไม่บล็อก):**
- Admin UI ของ policy / retention / audit / DSR — มีแต่ API
- นอก `llm_data_policy`: Telegram (15 แถว + กราฟไป Bot API), schema analyzer (ไฟล์ที่ admin upload), admin agent สรุปคำถาม/SQL ของผู้ใช้อื่น
- ค่าที่ extract ไว้แล้วใน `master_hierarchy_values` / `schema_metadata.sample_values` ของ source ที่ถูกตั้งเข้มขึ้น ยังอยู่ใน config DB (ไม่ถูกค้น/ส่งแล้ว แต่ไม่ได้ลบ)
- DSR ไม่แตะ: `user_sessions`, `otp_requests`, `api_key_usage`, `trending_queries` (ไม่ผูก user), `unmatched_keywords.last_question` / `query_correction_log` (ไม่มี user_id — หมดอายุตาม retention), `golden_examples.added_by`, history ใน memory ของ telegram bot
- `PIIRedactingFormatter` (PLAN_7 §11.5): ไม่เพิ่ม regex — ค่าธุรกิจใน log ลดที่ต้นทางแทน (verifier/lookup ไม่ทำงานกับ source ที่เข้ม); ที่ยังเหลือคือ literal ใน SQL ที่ log ระดับ INFO
- app DB เข้ารหัส at-rest, TLS, credential store (§6.6 ข้อ 6) — เรื่อง deployment (Phase 7)

## จาก Plan 7 Phase 5 — ถามข้ามหลาย context (2026-09-19)

ผลลัพธ์/ตัวเลข/ตารางสำรวจ: `plan/archive/RESULT_P7_PHASE5.md`

**เจ้าของตัดสิน (2026-09-19):** orchestrator + **template รวมคำตอบ (ไม่มี LLM ในขั้นรวม ทุก policy)** · ชุด 10 ข้อ = ชุดร่างใน RESULT (ความจริง = SQL ตรวจมือบน source ที่กระทบยอดกับ control totals) · งวดของ source ไม่เท่ากัน = **ตอบ + เตือน, ไม่คำนวณข้าม** · คำนวณข้ามโดเมนใน code ได้ทั้ง **ratio และส่วนต่าง พร้อมป้าย "ไม่ใช่กำไร / EBT ทางการ"** · **ไม่ข้าม workspace** · scope ที่ context หนึ่งในชุดไม่ประกาศ = **400 ทั้งคำถาม** · เปิดที่ **`/api/v1/query` ก่อน** · เพดาน latency P50 ≤ 15 s / P95 ≤ 30 s

**Decision ที่ทำระหว่างทาง (ตรวจ/กลับได้):**
- **flag = รายชื่อ workspace** (`admin_config.multi_context_workspaces`, JSON list; ไม่มี/อ่านไม่ได้ = ปิด) ไม่ใช่ bool — keyword ของ workspace `default` ยังปนกันมาก (`ฝ่าย`/`หน่วยงาน` ของ `transfer price`, `กำไร` ของ `revenue`) เปิดทั้งระบบ = คำถาม context เดียวจำนวนมากจะถูกส่งไปแตก; ตั้งผ่าน `PUT /admin/workspaces/{id}/multi-context` (endpoint ใหม่ — `PUT /admin/config/settings/{key}` รับเฉพาะตัวเลขใน allowlist)
- **ผู้สมัคร = context ที่ keyword "เฉพาะตัว" อยู่ในคำถาม** (ไม่มี context อื่นใน workspace เดียวกัน + ในสิทธิ์ ใช้คำเดียวกัน) — marker ร่วม (`feed`, `dashboard`) จึงไม่นับ; ทั้งหมดมาจาก `schema_contexts.keywords` (DB) ไม่มีคำใน code
- **ตัวแตกคำถามเป็น LLM 1 call แต่ผลถูกตรวจใน code:** context ⊆ ผู้สมัคร, ≤ 1 ข้อต่อ context, operation ∈ {none, ratio, difference} + operands ชี้ส่วนที่มีจริง; ผิดรูป = **กลับไปเส้นทาง context เดียว** (ไม่ใช่ error ของผู้เรียก); ตอบว่า context เดียวพอ = ใช้ context นั้นกับ**คำถามเดิม** (ได้ routing ของทางเลือก 1 มาด้วย เช่น "ค่าใช้จ่ายและ EBT ของสายงานขาย 1" → `feed_ebt` แทน `feed_expense`)
- **provider call ของตัวแตกรันใต้ `RequestPolicy` ที่ตั้งเอง** = policy เข้มสุด + intersection ของ allowlist ของทุก source ผู้สมัคร (ว่าง = `LLMPolicyError` ก่อนเรียก); resolve source ตรงนี้**ไม่มี scope** (ใช้อ่าน policy เท่านั้น) — scope ถูกบังคับในคำถามย่อย
- **`_provider_for`** แยกออกจาก `_execute_query` (ย้าย code เดิมทั้งก้อน) ให้ตัวแตกใช้กติกาเลือก provider ชุดเดียวกัน
- **ตัวเลขที่ใช้คำนวณ = ตัวเลขตัวเดียวในแถวเดียวของส่วนนั้น** (float ตัวเดียวชนะ int เช่นคอลัมน์งวด); สอง measure ในแถว = ไม่คำนวณ (แสดงทั้งสองส่วนตามปกติ)
- **ไม่มี cache ของคำตอบรวม** — คำถามย่อยมี cache ของตัวเองที่ผูก scope + allowlist + build + policy และเคารพ `stores_results` อยู่แล้ว
- **audit:** `query_audit.request_group` (คอลัมน์ใหม่, เพิ่มเองแบบ lazy เหมือน `ensure_api_key_columns`) — แถวแม่ไม่มี SQL, แถวลูกมี
- **response:** เพิ่ม `parts` + `computed` (null สำหรับคำตอบ context เดียว — field เดิมไม่เปลี่ยน)

**พบระหว่างทาง:**
- ⚠️ **การนับ keyword ซ้อน (`ค่า` + `ค่าใช้จ่าย` + `จ่าย` = 3 คะแนนจากคำเดียว) ค้ำ routing ของ `default` อยู่** — ลองเลิกนับซ้ำแล้ววัดกับคำถามจริง 989 ข้อ: แย่ลง 14, ดีขึ้น 3 → revert; งานแยก = ทำความสะอาด keyword ผ่าน admin UI พร้อมวัดด้วยชุดเดียวกัน
- ⚠️ **pipeline context เดียวเรียกตัวเลขของโดเมนหนึ่งด้วยชื่อของอีกโดเมน** เมื่อคำถามพูดถึงสองโดเมน: `SUM(expense_value_thb) AS "รายได้ลบค่าใช้จ่าย"`, "รายได้รวม 1,206 M" (= รายได้ฐานยอดขายของ 2 สายงานใน `feed_ebt`; จริง 3,274 M) — baseline ของชุด 10 ข้อ = 0/10
- ⚠️ **"กำไรของทั้งบริษัท" → `feed_ebt` ตอบ −284 M ของ 2 สายงานขายว่าเป็น "กำไรสุทธิรวมของบริษัท"** — context เดียว ไม่เกี่ยวกับ orchestrator; contract ไม่มีกฎสำหรับคำถามนอกขอบเขต → ข้อเสนอใน `PROMPT_NT_REPORT_P7.md`
- sales publish งวด 202608 แล้ว (prompt ของ session ระบุ 202607) — เหลือ ebt ตัวเดียวที่ 202607
- ⚠️ **full pytest เขียน `config.db` จริง 1 แถว** (มีก่อน phase นี้): `admin_config.last_brain_relevant_change_at` ถูกขยับทุกครั้งที่รัน suite — `mark_brain_dirty()` (`app/api/v1/admin/_shared.py`, `datafeed_knowledge`) เปิด `AdminConfigService()` เอง = `ConfigSessionLocal` จริง ไม่ใช่ DB ของ test; ผล = brain ถูกมองว่า dirty เสมอหลังรัน test (ไม่มีข้อมูลอื่นเปลี่ยน — diff ของ dump ทั้ง DB กับ backup ต่างแถวเดียว) → งานแยก: fixture autouse ที่ patch `mark_brain_dirty` / ชี้ `CONFIG_DB_URL` ของ test ไป DB ชั่วคราว
- ข้ามโดเมนด้วย `cost_center` ได้ทั้ง 4 โดเมน; ด้วยชื่อสายงานได้เฉพาะ expense ↔ ebt (revenue ต่าง 1 ชื่อ, sales ไม่มีสายงาน); กลุ่มธุรกิจ revenue ↔ sales ตรงกัน แต่ ebt ใช้ `03.Mobile`
- expense ↔ ebt กระทบยอดตรงทุกสตางค์เมื่อกรอง 2 สายงานเดียวกัน (1,490,506,698.33) — คำถาม "ค่าใช้จ่ายของสายงานขาย 1" ตอบจาก `feed_expense` หรือ `feed_ebt` ได้เลขเดียวกัน

**ข้อค้าง (ไม่บล็อก):**
- chat / telegram ยังเป็น context เดียว — chat เก็บ `context_name` ไว้ให้ follow-up; ชื่อแบบ `a+b` จะพาคำถามถัดไปตก legacy DB → ต้องออกแบบ follow-up ของคำตอบหลาย context ก่อนเปิด
- คำถามซ้ำภายใน 5 วินาที: คำถามย่อยโดน dedup → ส่วนนั้นรายงาน "คำถามซ้ำ" (ไม่มี dedup ระดับคำถามแม่)
- ตัวแตกคำถามเห็น `description` ของ context ซึ่งตอนนี้เป็นอังกฤษสั้น ๆ จาก contract ("NT Revenue Data Feed")

## จาก REMAIN-9 (2026-09-19)
- 9.4: DDL ที่ train เพิ่มจะมีผลเมื่อ admin กด Sync Brain — ยังไม่ได้วัดผลต่อ eval
- 9.5: `extract_hierarchy.py` เลิกรับ `--db` (อ่านข้อมูลผ่าน source ของ context, config ผ่าน CONFIG_DB_URL) — ไม่มี caller ที่ส่ง `--db`
- 9.8: `get_business_rules(revenue)` ของ nt-metadata คืน 0 rule — ตารางอ่านได้แล้ว แต่ filter ของ tool อาจไม่ตรงกับข้อมูล (ไม่ได้ไล่ต่อ — tool-loop เท่านั้น)

## จาก DataFeed contract → context description (2026-09-20)

- `schema_contexts.description` ของ context `feed_*` คือสิ่งที่ **`multi_context._split` แสดงให้ LLM เลือก context** และที่
  `GET /query/contexts` + MCP `list_contexts` คืนให้ผู้เรียก — ไม่ใช่ field ประดับ. `register_context` เคยเก็บ `contract["title"]`
  (ป้ายชื่อ "NT EBT Data Feed") ทำให้ประโยคไทยใน `contract.description` ไม่มีผลกับอะไรเลย → แก้เป็น
  `description or title` และบีบเหลือบรรทัดเดียว (splitter พิมพ์ 1 context ต่อบรรทัด; contract อาจใช้ literal block `|`)
- ข้อเสนอ Phase 5 ข้อ 6 เขียนว่า "`contract.description` ถูกใช้อยู่แล้ว" — **ไม่จริง** ตอนนั้น; NT-Report ใส่ description มาถูกแล้ว ฝั่ง AI ต่างหากที่ไม่ได้อ่าน
- re-sync เกิดเองเมื่อ sha ของไฟล์ contract หรือ schema_version ของ build เปลี่ยน (`knowledge_key`) — ไม่ต้องรัน script;
  แต่ `description` ถูกเขียนทับทุกครั้งที่ re-sync (ต่างจาก keywords / priority ที่เป็น insert-only) → admin แก้ผ่าน UI แล้วจะหายเมื่อ contract เปลี่ยน

## จาก hardening ของช่องทางเดิม (2026-09-20)

ผลลัพธ์/ตัวเลข/review: `plan/archive/RESULT_P7_HARDENING.md` | เอกสาร: `docs/PORTAL_INTEGRATION.md` (ตาราง status code), `docs/DEPLOYMENT_SECURITY.md`

**เจ้าของตัดสิน (2026-09-20):** REST แก้ครบ 4 ข้อ (SQL ในคำตอบ 0 แถว / ข้อความ exception / `str(dict)` / เกินโควตา = 429) · `GET /query/contexts` ต้อง auth เสมอ · Claude Desktop ต่อผ่าน stdio bridge + ลบ `claude_desktop_config.json` · `ai_response` หมดอายุตาม `result_retention_days` เดิม (ไม่เพิ่ม config ใหม่) · audit เขียนไม่ได้ = ไม่ส่งคำตอบออก **เฉพาะช่องทางที่ถือ key**

**สิ่งที่ session ถัดไปต้องรู้ (gotcha):**
- ⚠️ **`app/core/outbound.py` คือชุดคำศัพท์ร่วมของ REST + MCP** — ช่องทางขาออกใหม่ใด ๆ ต้องใช้ตัวนี้ ไม่สร้างชุดที่สอง. `safe_answer()` ปล่อยข้อความของ engine เฉพาะผลที่**มีแถว** (0 แถว = SQL เต็มใน explanation, ล้ม = ข้อความ exception)
- ⚠️ **body ของ 400 / 403 ก็รั่วได้** ไม่ใช่แค่ `answer` / `error`: `ScopeError` บอกชื่อคอลัมน์ scope ที่ context รองรับ และบอก `scripts/migrate_data_sources.py` เมื่อ config DB ยังไม่ migrate; `LLMPolicyError` บอกชื่อ source + `llm_provider_allowlist`; `ContextNotAllowed` มีสองสำนวน ("ไม่มีสิทธิ์" vs "ไม่พบ") = existence oracle → ทั้งหมดผ่าน `code_for()` + ข้อความตายตัว, เหตุผลจริงลง log + `query_audit.error`
- `multi_context.Part` มีทั้ง `error` (ข้อความจริง — audit/log) และ `error_code` + property `code` (ของที่ส่งออก). ผู้สร้าง `Part` เองต้องตั้ง `error_code`; ถ้าลืม `code` fallback เป็น `query_failed` (ไม่ใช่ "ไม่พบข้อมูล")
- `APIKeyService.check_key()` = `validate_key` ที่บอกเหตุผล (`unauthorized` / `rate_limited`); `validate_key` เป็น wrapper เดิม — ผู้เรียกเดิมไม่เปลี่ยน. test ที่ mock `validate_key` เพื่อให้ผ่าน dependency ต้องเปลี่ยนไป mock `check_key`
- **429 อยู่ใน `get_current_user`** จึงมีผลกับทุก endpoint และมาก่อน `enforce_key_surface`: key ที่หมดโควตาไม่ตกไป session auth อีกแล้ว
- ⚠️ **`query_audit.record()` คืน `bool` แล้ว** (ยัง never raises). ผู้เรียกที่ส่ง `api_key_id` ต้องถือว่า `False` = ไม่ส่งคำตอบ. `AuditUnavailable` ต้องอยู่ในรายการที่ `_find_refusal` แกะออกจาก ExceptionGroup ไม่งั้น `except AuditUnavailable` ที่ endpoint ไม่ทำงาน
- ⚠️ **อย่า raise จากใน `try` ที่ except ของมัน audit failure ด้วย** — `QueryEngine.query` เคยยิงเขียนซ้ำใส่ DB ที่เพิ่งปฏิเสธ (รอ lock สองรอบ ต่อ sub-question)
- ⚠️ **`ensure_table` ต้องมี lock:** `record()` รันใน worker thread; สองคำขอพร้อมกันบนตาราง `query_audit` ก่อน Phase 5 จะ `ALTER TABLE ADD COLUMN` ซ้ำ (SQLite ไม่มี `IF NOT EXISTS`) — เดิมเสียแค่แถว audit ตอนนี้เสียคำตอบด้วย
- retention: `EXPIRED_ANSWER` เป็นข้อความตายตัวที่ **`chat.py::_get_conversation_history` ต้องกรองทิ้ง** ไม่งั้นโมเดลอ่านเป็น "คำตอบก่อนหน้า"; แถวที่ `ai_response IS NULL` ต้องคง NULL (ใช้ `CASE` ไม่ใช่ assignment ตรง) และเงื่อนไข WHERE ต้องกัน row เดิมไม่ให้แมตช์ซ้ำ (idempotent)
- bridge (`scripts/mcp_stdio_bridge.py`): ใช้ **raw handler ของ `CallToolRequest`** — `@server.call_tool()` ประกอบผลใหม่เป็น `isError=False` และแปลง exception เป็นข้อความของตัวเอง (tool error จะไม่ถึง client ทั้งก้อน). ต้องตั้ง `User-Agent` เอง ไม่งั้น audit `channel` อ่านว่า `mcp:python-httpx/…`; client ที่อยู่หลัง bridge แยกไม่ได้ — ตัวที่ระบุ installation คือ key
- test ของ bridge ใช้ `mcp.shared.memory.create_connected_server_and_client_session` + patch `streamablehttp_client` ให้ใส่ `httpx_client_factory` ที่เป็น ASGI transport
- eval cross-domain **แกว่ง 6–9/10 ระหว่างรัน** ด้วย code เดียวกัน (วัด worktree ก่อนแก้ = 8/10 วันเดียวกัน DB เดียวกัน) — อย่าอ่านตัวเลขครั้งเดียวว่าเป็น regression

**ของเดิมที่ยังไม่แก้:** CORS เปิดทั้งแอป (เจ้าของยังไม่ตัดสิน) · REST ไม่ตรวจ `has_scope('query')` · `execute_query(validate_first=False)` · dedup 5 วินาที · Redis ไม่ได้รัน · `error` ระดับบนของคำถามข้าม context ยังเป็นสรุปคำเตือน ไม่ใช่รหัส

## จาก Plan 7 Phase 6 — MCP สำหรับผู้เรียกภายนอก (2026-09-20)

ผลลัพธ์/ตัวเลข/ตารางสำรวจ/review: `plan/archive/RESULT_P7_PHASE6.md` | คู่มือ: `docs/manuals/manual_mcp_external.md`

**เจ้าของตัดสิน (2026-09-20):** client รายแรก = **Claude Code บนเครื่องนี้ + สำเนา DB** + ตัวอย่าง client ใน repo · **stateless Streamable HTTP ใน FastAPI เดิม** ที่ `/api/v1/mcp` (ไม่ทำ legacy SSE, ไม่แยก process) · tools = `ask` / `list_contexts` / `source_status` เท่านั้น, `ask` มี `include_data` (cap) — **ไม่มี `include_sql`, ไม่คืน SQL** · สิทธิของ key = workspace / allowlist เท่านั้น, `scope` กรองให้แคบลงได้แต่**ไม่ใช่สิทธิระดับแถว** · policy ≠ `full` = **ปฏิเสธบนช่องทางนี้**, อ่าน policy ไม่ได้ = ปฏิเสธ · history = stateless เหมือน `/api/v1/query`

**Decision ที่ทำระหว่างทาง (เข้มกว่า REST — ตรวจ/ผ่อนได้):**
- MCP รับเฉพาะ key ที่**ผูก workspace / allowlist** และมี scope `query` / `full` (REST ไม่ตรวจ scope `query`, รับ key ไม่ผูก) — key นี้ไปอยู่ในเครื่องของผู้ใช้
- **1 tool call = 1 usage** (handshake / `tools/list` ตรวจ key ทุกครั้งแต่ไม่นับ) — ข้อเสนอเดิม 1 HTTP request = 1 usage ทำให้ 1 คำถาม = 3–4 usage ไม่ตรงกับ "rate limit เดียวกับ REST"
- ชื่อ client อยู่ใน `channel` (`mcp:<user-agent>`, self-reported) ไม่เพิ่มคอลัมน์ใน `query_audit`
- policy ≠ `full`: ใช้เซต `usable` (= allowed ∩ source policy `full`) **เป็น `allowed_contexts` ของ engine** → routing อัตโนมัติ / ผู้สมัคร multi-context / cache key / `request_pinned` อยู่ในเซตนี้ด้วยกลไกเดิม; refusal จาก policy ของ context ที่ระบุชื่อลง audit เป็น `ContextNotAllowed` แต่ client เห็น `policy_refused`
- facade **ไม่มี provider call ของตัวเอง, ไม่แตะ ContextVar, ไม่ proxy MCP ภายใน** — ทุกอย่างผ่าน `run_simple_query` ตัวเดียวกับ `POST /api/v1/query`

**สิ่งที่ session ถัดไปต้องรู้ (gotcha):**
- ⚠️ **FastMCP ส่ง `str(exception)` ให้ client ตรง ๆ** (`Error executing tool ask: …`) — tool ของ facade ต้องจับทุก exception แล้วคืน code + ข้อความตายตัว + `request_id` เอง; refusal ที่ถูกห่อใน `ExceptionGroup` ก็ต้องแกะ
- ⚠️ **ข้อความของ engine ไม่ปลอดภัยสำหรับช่องทางขาออก:** query ที่สำเร็จแต่ได้ 0 แถว `hybrid_flow.py:776` ใส่ **SQL เต็ม**ใน explanation (`error=None`); query ที่ล้มใส่ข้อความ exception (path / SQL) ใน `answer` / `error` / `parts[].error` (`query.py`, `hybrid_flow.py:925-928`, `multi_context.py:320`) — **ช่องทางขาออกใหม่ใด ๆ ห้ามส่งต่อข้อความนี้**: ให้ข้อความของ engine ออกได้เฉพาะผลที่มีแถว, ที่เหลือ = ข้อความตายตัว (facade มีด่านสุดท้ายทิ้งคำตอบที่ยังมี SQL ที่รันจริงหรือ ```` ```sql ````). REST ยังคืนของเหล่านี้อยู่ (ดูข้อค้าง)
- ⚠️ **HTTP non-2xx ฆ่า session ของ MCP client** (client เห็นเป็นการเชื่อมต่อล้ม ไม่ใช่ error ที่อ่านออก) → 401 ใช้กับ key ที่ใช้ไม่ได้เท่านั้น; โควตา / refusal ทุกชนิดต้องเป็น tool error (`isError=true`)
- ⚠️ **stateless transport ไม่ต้อง `initialize`** — `tools/call` เป็น request แรกได้ → auth ต้องทำ**ทุก HTTP request** (gate ASGI หน้า transport) ไม่ใช่ตอนเปิด session; GET เปิด stream ค้างไม่มีกำหนด → GET / DELETE = 405; `client_params` เป็น `None` ใน tool (ชื่อ client มาจาก header ของ request ปัจจุบัน)
- `validate_key` **มี side effects** (rate นับ, commit `last_used_at`) — เรียกซ้ำ = นับซ้ำ → gate ใช้ `APIKeyService.authenticate` (ครึ่งที่ไม่มี side effect), `validate_key` + `track_usage` เรียกครั้งเดียวใน tool call
- `APIKey` (ORM) ใช้นอก session ที่ commit แล้วไม่ได้ (`DetachedInstanceError`) → `Principal` เป็นค่าธรรมดา ไม่ส่ง ORM object ข้าม request
- **`Route` ไม่ใช่ `Mount`:** mount ที่ `/api/v1/mcp` = 307 บน URL ไม่มี `/` ท้าย และ `request.app` ใน sub-app ไม่ใช่ FastAPI ตัวแม่ (`request.app.state.mcp_client` หาย) → route ตรงไปที่ ASGI handler ของ SDK; routed ASGI app ไม่มี lifespan ของตัวเอง → `session_manager.run()` อยู่ใน lifespan ของ `app/main.py` (ไม่เปิด = `Task group is not initialized`)
- **`session_manager.run()` ใช้ได้ครั้งเดียวต่อ instance** → test สร้าง app ของตัวเองผ่าน `mcp_facade.build()` (คู่ใหม่ทุก app); ห้าม start lifespan ของ `app.main` จริงเพื่อทดลอง (เปิด scheduler / Telegram ด้วย)
- ⚠️ **`policy_for_context` fail open** สำหรับกติกา "อ่านไม่ได้ = ปฏิเสธ": registry ที่ยังไม่ migrate / ไม่มีแถว = `full`, จับชื่อแบบ exact, ไม่กรอง `is_active` → facade มีตัวอ่านแบบเข้มของตัวเอง (`full_policy_contexts`; registry ไม่ migrate / config อ่านไม่ได้ = เซตว่าง). **`config.db` จริงยังไม่มีคอลัมน์ `llm_data_policy`** → เปิด flag โดยไม่ migrate = MCP ปฏิเสธทุก context
- `track_usage` เปลี่ยนเป็น **upsert อะตอมมิกคำสั่งเดียว** (เดิม read-modify-write: ยิงพร้อมกัน 30 call นับได้ 3–6, เกินโควตารายวัน, `IntegrityError` แถวแรกของวัน — กระทบ REST ด้วย); อาศัย `UNIQUE(api_key_id, date)` ของ `api_key_usage`; facade ตรวจเพดานซ้ำหลังนับ
- `channel` ของ REST มาจาก `source` ที่ผู้เรียกส่งเอง → `_rest_channel` กันไม่ให้ REST เขียน channel ที่ขึ้นต้น `mcp` (บันทึกเป็น `api:mcp…`); `GET /admin/query-audit?channel=mcp` จับ prefix `mcp:`
- DNS rebinding guard ของ SDK เปิดอยู่: Host ไม่อยู่ใน `MCP_ALLOWED_HOSTS` = 421 (`localhost` ไม่มี port ไม่ตรง `localhost:*`), มี `Origin` และ `MCP_ALLOWED_ORIGINS` ว่าง = 403
- argument ผิดชนิด / ชื่อ tool ที่ไม่มี ถูก SDK ตอบก่อนถึง tool (ข้อความของ pydantic สะท้อน input ของผู้เรียกเอง, ไม่นับ usage) — ไม่แก้ เพราะต้องแตะ API ภายในของ SDK
- script ที่รันเดี่ยว (นอกแอป) แล้ว query `User`: ต้อง `import app.db.base` ก่อน เพื่อให้ model ถูก import ครบทุกตัว (relationship ของ `User` อ้าง model อื่น)
- รัน server จริงแล้วมีคำถามแรกของ workspace → เกิด `chroma_db__<workspace>/` ใน root ของ repo (Phase 4b) — เพิ่ม `chroma_db__*/` ใน `.gitignore` แล้ว
- latency: วัด REST/MCP สลับกันต้องเว้น > 5 s (dedup 5 วินาทีผูก user + คำถาม ไม่มี context / key) ไม่งั้นได้ `duplicate_request`

**ของเดิมที่พบ — ไม่ได้แก้ (พฤติกรรมของช่องทางเดิม, รอเจ้าของ — RESULT §9):**
- REST `/api/v1/query` คืน **SQL ในข้อความคำตอบ**เมื่อได้ 0 แถวแม้ `include_sql=false`, คืนข้อความ exception ใน `answer` / `error` / `parts[].error`, คืน `str(dict)` เมื่อ explanation เป็น dict — portal ได้ของเหล่านี้อยู่วันนี้
- `GET /api/v1/query/contexts` เป็น public: key ผิด → `allowed_contexts(None)` = เห็นทุก context ของทุก workspace
- REST เกินโควตา = **401** (คู่มือเขียน 429); REST ไม่ตรวจ `has_scope('query')`
- `mcp_servers/claude_desktop_config.json` + README สอนต่อ `nt-query` (SQL ดิบ ไม่มี key / audit) เข้า Claude Desktop ตรง ๆ; `execute_query(validate_first=False)` ผู้เรียกปิด validator ได้ — เอกสารติดป้าย development-only แล้ว ไฟล์ยังอยู่
- dedup 5 วินาที: LLM client ที่ถามซ้ำเร็ว ๆ ได้ `duplicate_request`; client ตัดการเชื่อมต่อกลางคำถาม pipeline ทำงานจนจบ (เสีย provider call)
- Redis ไม่ได้รันบนเครื่องนี้ → limit รายนาที fail-open; เพดานรายวันคือเพดานเดียวที่บังคับจริง

**ข้อค้าง (ก่อนเปิดกับ DB จริง — ต้องสั่ง):** migrate `config.db` จริง (`migrate_data_sources.py` + `migrate_workspaces.py`) → เปิด flag `mcp_external_enabled` + ออก key จริงที่ผูก workspace + ตั้ง `MCP_ALLOWED_HOSTS` → รัน Redis. ค้างจาก phase ก่อน: เปิด multi-context กับ `nt-report`; admin UI ของ workspaces / sources / policy / audit / flag นี้; D4 / DPO; entitlement v2 (D7) สำหรับสิทธิระดับแถว. Widget ไม่ทำ (ไม่มี client ที่ 2)

## จาก go-live ของ portal (2026-09-20)

ผล: `plan/archive/RESULT_P7_GOLIVE.md`, `plan/archive/RESULT_F11.md` · runbook: `docs/manuals/manual_portal_runbook.md`

1. **scope เป็นตัวกรอง ไม่ใช่จุดยึด — และโมเดลไม่เคยเห็นมัน** (`308acb1`)
   `request_scope` ถูกอ่านแค่ใน `data_sources.py` เพื่อห่อ view. ตอน portal ส่งเดือนเดียวไม่มีใครรู้สึก:
   SQL ที่ลืมใส่เงื่อนไขงวดยังถูก **เพราะ view มีเดือนเดียว**. พอ portal ขยายเป็น 13–24 เดือน
   (entitlement ใหม่เพื่อให้ถามแนวโน้มได้) view มีเดือนสิงหาคมสองครั้ง → SQL เดิมรวมสองปีหรือเลือกปีผิด
   → คะแนนตกจาก 7–8/10 เหลือ 3–4/10 ทั้งสี่โดเมน
   **แก้:** `hybrid_flow.scope_note()` เติมขอบเขต + "ค่ามากสุด = งวดอ้างอิง" ลง prompt; คำขอที่ไม่มี scope
   ได้ prompt เดิมทุกไบต์
   ⚠️ **ต้องเติม 4 จุด** — จุดที่สำคัญที่สุดคือ **pass 1 ของ two-pass (`extract_intent`)** เพราะ
   `two_pass_enabled = true` บน config จริง → intent เลือกปีก่อนที่ prompt ของ SQL จะถูกสร้าง;
   ใส่แต่ pass 2 แล้ววัด sales / ebt ยังตอบจาก ส.ค. 2568 เหมือนเดิม
2. **`error` เป็นรหัสแล้ว ผู้เรียกที่ match ข้อความจะเงียบ ๆ พัง** — hook ของ portal หา `/publish/i`
   ใน `payload.error` ซึ่งตอนนี้คือ `source_unavailable` → ระหว่าง publish ผู้ใช้ได้คำแนะนำผิด
   บทเรียน: เปลี่ยน field จาก "ข้อความ" เป็น "รหัส" ต้องไล่ผู้เรียกที่ match ข้อความด้วย ไม่ใช่แค่ที่ match status
3. **retention รอบแรกซ้อมได้แม่นยำ** — รันบนสำเนาสดก่อน ได้ 1,513 / 55 เท่ากับของจริงทุกตัวเลข
   (job รัน 30 วินาทีหลัง start จึงตั้ง `result_retention_days` ก่อน start เท่านั้น)
4. **วัดคุณภาพคำตอบรอบเดียวไม่พอ** — รอบยืนยันกลายเป็น cache hit ทั้งหมด (query cache ผูก scope + key)
   แล้ว cache hit 20 ครั้งในไม่กี่วินาทีก็ชน rate limit 20/นาที (Redis) → 429
   ถ้าจะวัดซ้ำจริงต้องเว้นให้พ้น 30 นาที หรือเปลี่ยนคำถาม; และโมเดลผันผวน ±1 ข้อระหว่างรอบ
5. **process เก่ากิน config ใหม่ไม่ได้** — PocketBase ที่รันมาตั้งแต่ 15 ก.ย. ยังใช้ `pb_hooks/*.js` ตัวเก่า
   ทั้งที่ไฟล์ถูกแก้แล้ว; ฝั่ง AI ก็เช่นกัน (query cache 30 นาทีไม่ผูกกับเวอร์ชันของ code) → restart หลัง deploy
6. **`export_cleanup` ล้มทุกรอบ** บน `app.db` จริง: `no such table: report_exports` — ของเดิม ไม่เกี่ยวกับ go-live

## จากคำถามจริงของ portal + การไล่ของที่ "ไม่อ่านคำอธิบายข้อมูล" (2026-09-20 ดึก → 2026-09-21)

ผล: `plan/archive/RESULT_F11.md` §7–§8, `plan/archive/RESULT_P7_GOLIVE.md` §6 · แผนต่อ: `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md`

1. **ค่าคงที่ใน prompt path ชนะ metadata ทั้งชั้น** — `get_date_format()` รับชื่อตารางแล้วโยนทิ้ง คืน "ใช้ YEAR และ MONTH"
   ให้ทุก context มาตั้งแต่ยุคที่มี context เดียว → 3 ใน 7 context ถูกสั่งให้ใช้คอลัมน์ที่ไม่มี. **ก่อนเติม metadata ให้ context ใหม่
   ให้ค้นค่าคงที่ใน prompt path ก่อน** (เจออีกตัว: `REVENUE_VALUE` เป็น metric ปริยายของ pass 2)
2. **contract ประกาศแล้ว แต่ตัวอ่านเดาเอง** — `is_summable` มาจาก dtype ทั้งที่ contract ประกาศ `agg: point_in_time` →
   `SUM(revenue_ytd)` = 115,090 MB ทั้งที่กฎในข้อความก็อยู่ใน prompt แล้ว: **metadata ที่ขัดกับข้อความมีน้ำหนักกว่าข้อความ**.
   `agg` อยู่ที่ `columns[].agg` (contract 2.3.2+) — `control_totals.measures` มีแค่ measure ที่ใช้กระทบยอด; key ไม่มี agg จึงยังต้องเช็ก dtype
3. **ชื่อ scope key ≠ ชื่อคอลัมน์** — expense / ebt map `year_month` → `time_key`; prompt ที่เรียกด้วยชื่อ key พินงวดไว้กับคอลัมน์ที่ไม่มี
4. **PocketBase:** handler ของ `routerAdd` รันใน goja runtime แยก **มองไม่เห็น function ระดับไฟล์** (`ReferenceError`) และ test แบบ node
   ดักไม่ได้ → หลังแก้ hook ต้องยิงผ่าน PB จริง · PB **ไม่โหลด `.env` เอง** ต้อง start ผ่าน `scripts/serve.sh`
5. **ชุดคำถามที่ทีมเขียนเองให้คะแนนเกินจริง** — ระบุเดือน/ปีครบเกือบทุกข้อ ได้ 8/10; ผู้ใช้จริงพิมพ์สั้น ไม่ระบุเวลา ใช้คำว่า "บริการ" ได้ 4/12
6. **ยิงซ้ำแล้วได้เหมือนเดิม ≠ นิ่ง** — query cache 30 นาทีผูก scope + key: รอบที่ 2–3 เป็น cache hit (และ cache hit 20 ครั้งติดกันชน limit 20/นาที)
7. **code ที่อ้างเอกสารต้องตรวจตอนเขียนเอกสาร** — code 5 จุดอ้าง `RESULT_F11 §8` ที่ยังไม่ได้เขียน อยู่หนึ่งวันเต็ม

## จาก Plan 8 Phase 8.0 — เครื่องมือเดิมกับ `feed_*` + คำถามจริงของ portal (2026-09-21)

ผล: `plan/archive/RESULT_P8_PHASE0.md`

1. **ให้คะแนนจากสิ่งที่ผู้ใช้อ่าน ไม่ใช่ `data`** — SQL เลือกปีถูกแต่ข้อความเขียน 2026 เป็น "2566" / "2568" ใน 7 จาก 12 คำถามจริง
   และตัวให้คะแนนที่อ่านแค่ `data` นับผ่าน → เกณฑ์อ่านข้อความ: ทุกปีที่ข้อความพูด + ยอด + ฐานของคำถามที่ไม่ระบุเวลา
2. **แปลงปีในแถวอย่างเดียวไม่พอ** (P15 มี `"year": 2026` ในแถวก็ยังเขียน 2566) → ตรวจข้อความใน code หลังสร้าง (`thai_year.py`) ·
   ตัวแก้ต้องไม่แตะเลขที่ไม่ใช่ปี: รุ่นแรกเลื่อน "2500 ล้านบาท" เป็น "2569 ล้านบาท" และยอม "ปี 2568" เพราะมียอด 2,568 บาท (`RESULT_P8_PHASE0` §10)
3. **pass 1 ของ two-pass ไม่เคยเห็นระดับชั้น** — ประตู `if value_matches:` · เปิดแล้ว legacy ตก 8/37 → 5/37 เพราะ "ค่าใช้จ่าย" เป็นทั้งคำเลือกโดเมน
   และคำตรวจจับระดับ → คำที่เป็น routing keyword ของ context ไม่นับเป็นคำบอกระดับ · การแก้ที่กระทบ prompt: วัดคำถามจริง**และ** legacy ก่อน/หลังเสมอ
4. **การปฏิเสธคำถามข้ามโดเมนไม่มีอะไรยึด** — P12 "ค่าใช้จ่ายมีไหม" ใน context รายได้ ผ่าน/ตกตามส่วนอื่นของ prompt
   (มี hierarchy = ตก 5/5; 8.1: กฎเวลาใหม่ 0/7 เทียบเดิม 3/7) → ต้องเป็นกฎของ context
5. **test ที่ผู้ตรวจอีกคนเขียนหลังขึ้นของจริงเจอ 4 ข้อบกพร่องที่ test ของเราไม่จับ** — ให้ผู้ตรวจยิง test ที่ล้มก่อนแก้ แล้วเก็บ test นั้นไว้ใน repo

## จาก Plan 8 Phase 8.1 — ที่มา + สถานะของความรู้ (2026-09-21)

ผล: `plan/archive/RESULT_P8_PHASE1.md` · คำสั่งขึ้น / ถอยของจริง §12

1. **server รันจาก working tree ของ `main` → restart = ขึ้นทุก commit บน `main`** — 19:57 เจ้าของ restart ตามคำสั่งของงาน 8.0 ("ไม่มีการเขียน DB")
   แต่ `main` มี 8.1 ข้อ 8–9 ที่ ORM อ่านคอลัมน์ใหม่อยู่ก่อนแล้ว → หน้า admin 6 ตาราง + GC + ตัวเรียนรู้ `no such column` บนของจริง
   (คำถามปกติ — เส้นทางคำถามใช้ raw SQL) · **คำสั่ง restart ต้องไล่ `git log <code ที่รันอยู่>..HEAD`** · commit ที่ต้อง migrate ก่อน
   ห้ามลงสาขาที่ server รันก่อน migrate ของจริง — หรือ code ต้องทน DB เดิมได้
2. **module ที่ import ตอนใช้ครั้งแรกโหลดไฟล์ของตอนนั้น ไม่ใช่ของตอน restart** — server ที่รันอยู่ + ไฟล์ที่แก้หลัง start = code ผสม
   (onboarding, MCP ลูกที่เริ่มใหม่) · จำลองได้: เริ่ม server บน commit เก่าแล้วสลับไฟล์ใต้มัน · ตรวจ `sys.modules` หลัง startup ว่าอะไรโหลดแล้ว
3. **SQLite ถอด UNIQUE ไม่ได้ถ้าไม่สร้างตารางใหม่** — 8 ใน 9 ตารางความรู้มีคีย์ UNIQUE → แถว `proposed` ที่คีย์ชนแถว `active` อยู่ตารางเดียวกันไม่ได้
   → คิวแยก `knowledge_proposals` (partial unique index: หนึ่งข้อเสนอที่รออยู่ต่อคีย์ต่อผู้เสนอ, ข้อเสนอใหม่รวมทีละช่อง)
4. **trigger ที่ประทับ `updated_at` ทำให้ "ติดป้าย" กลายเป็น "แก้"** — migration ถอด trigger ระหว่าง backfill แล้วใส่กลับด้วย SQL เดิมใน transaction เดียว;
   dump ก่อน/หลังทีละแถวจับได้
5. **Chroma ไม่นิ่งเอง** — RAG ดึงเอกสารต่างกันระหว่างรอบแม้ DB/store เดียวกัน (4–6 ใน 14 ข้อ) → เทียบ prompt ทุกไบต์ต้องตรึง RAG
   (บันทึก/เล่นซ้ำ, คีย์ = brain ของ workspace + คำถาม — คำถามเดียวกันอยู่ได้หลาย brain)
6. **ตัวเขียนที่ "มีอยู่" แต่ไม่เคยทำงาน** — `/chat/train`, feedback review, analyzer import, ตัวเรียนรู้ ใช้ session ของ app.db กับตารางของ config.db
   มาตั้งแต่แยก DB และ auto-apply ต้อง ≥ 0.8 ที่ heuristic ให้ไม่เกิน 0.5 — ไม่มีใครเห็นเพราะกลืน error · ตัวอ่านที่กลืน error แล้วคืนค่าว่าง
   = DB ที่ลืม migrate ทำ prompt ขาดแบบเงียบ → server ไม่ยอมเริ่มถ้าไม่มีคอลัมน์
7. **ค่าคงที่ในตัวอย่างของ prompt มีผลจริง** — เอาปีออกจาก "เดือนมกราคม 2568" ทำให้ P11 เลิกบอกงวดที่เทียบ (2/2) → ถอย · แยกตัวแปรทีละการแก้
   (รุ่นที่แก้กฎ SQL อย่างเดียว) จึงรู้ว่าตัวไหนทำ
8. **รอบที่เป็น cache hit ทั้งหมดไม่ได้พิสูจน์อะไร** — รอบตรวจหลัง migrate ตอบข้อละ 3 ms → ใช้คำถามที่ไม่อยู่ใน cache หรือ restart
9. **ค่าที่อ่านจากข้อมูลไม่ใช่ข้อเท็จจริงแบบที่คนตัดสิน** — `parent_column = "GROUP"` ที่ view ไม่มี: SQLite อ่านชื่อในเครื่องหมายคำพูดที่ไม่ใช่คอลัมน์เป็นข้อความ
   → ข้อเสนอค่าแม่ 122 จาก 123 เป็นขยะ → extract ไม่เสนอค่าแม่ (คิวที่ยาวด้วยขยะ = ไม่มีคิว)
10. **กฎที่ตรวจใน Python ก่อนเขียน ต้องตรวจซ้ำใน WHERE ของคำสั่งเขียน** (ตรวจโดย Codex 2026-09-22 — `RESULT_P8_PHASE1` §14) — อ่าน provenance
    แล้ว UPDATE ด้วย key อย่างเดียว = คนแก้ระหว่างอ่านกับเขียนถูกทับ → `provenance.replaceable()` ใน WHERE + rowcount 0 = เข้าคิว
11. **dict ที่ใช้คอลัมน์ที่ไม่ unique เป็น key ซ่อนแถว** — `golden_examples` ไม่มี key: คำถามเดียวกันมีทั้งของคนและของ contract → UPDATE ตามคำถามเปลี่ยนทั้งคู่ →
    เขียนทีละ row id
12. **pysqlite เริ่ม transaction เฉพาะก่อน DML** — DROP TRIGGER ก่อน backfill commit ทันที, backfill ล้มแล้ว rollback ไม่คืน trigger → `isolation_level = None` +
    `BEGIN IMMEDIATE` เอง แล้วเขียน test ของทางที่ล้ม
13. **`json_patch` ตีความ JSON null ว่าลบ key** (RFC 7396) — ข้อเสนอให้ล้างค่าหายเมื่อรวม → `json_set`
14. **test ของเราผ่านหมด แต่ผู้ตรวจอีกคนเจอ 9 ข้อ** — race, แถวซ้ำ, แถว rejected ถูกถอนแล้วกลับมา, ทางที่ migration ล้ม, ตัวอ่านที่ลืมระดับแม่: ทุกข้อคือกรณีที่ไม่มี test ·
    ให้ไล่ทั้งช่วง commit ก่อนถือว่า Exit ผ่าน

## จาก CI ที่แดงโดยไม่มีใครเห็น (2026-09-22)

1. **dependency ที่ไม่มีเพดาน major version** — `mcp>=1.26.0` ให้ CI ได้ mcp 2.2.0 (API เปลี่ยน) → ทุก push บน main ล้มตั้งแต่ 2026-09-18
   ขณะที่ในเครื่องยังเป็น 1.26.0 และ suite ผ่าน → pin เวอร์ชันที่ code และ test ใช้จริง (`mcp==1.26.0`); ยกเพดานพร้อมงาน migrate เท่านั้น
2. **ไม่มีใครดูผล CI หลัง push** — แดง 8 รอบติด 4 วัน ขณะที่งานขึ้นของจริงไปหลายรอบ → ดู `gh run list --branch main` หลังทุก push
