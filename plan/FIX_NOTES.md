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
- ⚠️ `keyword_index.build_keyword_index` (admin `POST /admin/config/rebuild-keyword-index`) inspect column บน business DB แต่ `SELECT DISTINCT` บน **config DB** → SELECT ล้มทุกคอลัมน์ แต่ `DELETE` ใน transaction เดียวกัน commit → **กด rebuild = ลบ keyword index ทิ้งหมด (revenue 1679, expense 2155, pl_costtype 1271, transfer price 285 แถว) แล้วใส่ 0** (reproduce แล้วบนสำเนา config.db: revenue 1679 → 0) — `search_db_for_keyword` (value lookup ใน query path) มีรูปแบบเดียวกัน → คืน `[]` เสมอ
- `hierarchy_service` (`detect_changes`, `bootstrap_from_view`, `get_available_views`) query view ธุรกิจบน config DB → ผลว่างเสมอ; `scripts/extract_hierarchy.py` เขียน `master_hierarchy*` ลง **business DB** (ของจริงอยู่ config DB)
- `context_onboarding` ส่ง business DB path ให้ `ConfigApplicator`/`ConfigValidator` → apply ลงผิด DB (ล้มเงียบ), validate 500; `onboarding_tools` (admin agent) เรียก method ที่ไม่มี (`inspect_view`, `onboard`) → fail ทุกครั้ง
- `vanna_service._sync_ddl` หา DDL ใน config DB → ไม่เคย train DDL เลย
- `POST /chat/train` เช็ค `isinstance(check_res, dict)` แต่ `call_tool` คืน str → SQL ผิดไม่เคยถูกปฏิเสธ
- `nt_metadata_mcp` tools query ตาราง config บน business DB → ล้มทุกตัว (ใช้แค่ tool-loop mode); `nt_validation_mcp.check_business_rules` อ่าน `schema_business_rules` จาก app.db (ไม่มีตาราง) → rules ผ่านเงียบเสมอ; `nt_validation_mcp.get_db` ไม่ได้เปิด `mode=ro` (dead code)
- `QueryEngine` ผล dedup-blocked ไม่มี `context_name` → default `"revenue"` ถูกบันทึกใน chat_history และใช้เลือก context ของ follow-up
- `prompt_builder.get_syntax_rules` อ่าน dialect จาก **config** engine (แก้เฉพาะเส้น DuckDB; legacy คงเดิม)

- Concurrency review: ทุก process เปิด view DB ไฟล์เดียวกัน → ใช้ spill dir ของ DuckDB (`<db>.tmp`, ชื่อไฟล์ตายตัว) ร่วมกัน → spill พร้อมกันทำไฟล์กันเสีย (SIGSEGV) — แก้แล้ว `temp_directory=''` (ไม่ spill; query ใหญ่เกิน memory_limit จะ error ชัด ๆ) และ resolver เก็บ adapter เดียวต่อ source (ไม่รั่ว instance ทุกครั้งที่ re-register/re-point) — `65f9ed1`

**ข้อค้าง/ข้อจำกัดใหม่ (ส่งต่อ Phase 2+):**
- ⚠️ **publish race (ต้องตัดสิน):** publisher ของ NT-Report (`tools/feed/feed.py` บรรทัด ~552 `shutil.rmtree(latest)` → เขียน CSV ทับที่เดิม → `manifest.json` เขียนท้ายสุด บรรทัด ~590) — คำถามที่เข้ามาระหว่าง publish (หลายสิบวินาที) อ่านไฟล์ครึ่งไฟล์ได้ → **ตอบงวดล่าสุดเป็นงวดเก่า / ยอด NULL โดย success=True** (reviewer reproduce ได้) — ทางเลือก: (ก) NT-Report publish แบบ atomic: build ลง dir ใหม่แล้วสลับ symlink `latest` (AI ตาม re-point ได้แล้ว มี test) (ข) AI ตรวจ `manifest.json` ทุก query (มีไฟล์ + ขนาดไฟล์ตรง `bytes`) ไม่ตรง = ปฏิเสธชัด ๆ แทนตอบผิดเงียบ (ดึงงาน Phase 2 มาก่อน) (ค) ลงทะเบียน snapshot `dist/revenue/<period>/` แทน `latest/` แล้ว register ใหม่ทุกงวด — **แนะนำ (ก)+(ข)**; ระหว่างนี้ อย่ารัน `run_all --feed` ช่วงที่มีคนใช้ หรือ `--legacy` ก่อน publish
- query result cache (30 นาที): เปลี่ยน source ของ context แล้ว cache เดิมกลายเป็น miss เอง (แก้แล้ว `e4b2f69`) แต่ **publish งวดใหม่ลง `latest/` (registration เดิม)** คำตอบเดิมยังอยู่ได้ถึง 30 นาที — ต้องมี manifest version ใน key (Phase 2) หรือ `POST /admin/refresh-cache`
- runtime ยังไม่ตรวจ manifest ซ้ำ (reconcile/schema_version) — ตรวจตอน register เท่านั้น (Phase 2)
- tool-loop (`mode='mcp'`, `escalation_tool_loop_enabled`): `get_sample_values`/`get_table_stats` ตอบ error สำหรับ file source (fail closed) — ยังไม่มี implementation บน DuckDB
- หน้า admin (schema browser, onboarding, dimension families, keyword index, sync-brain DDL) เห็นแค่ business DB เดิม → สำหรับ `feed_*` จะเห็น **สำเนาเก่าที่ import ไว้** ไม่ใช่ไฟล์
- `/chat/train` validate SQL กับ legacy DB เสมอ (ไม่ route ตาม context)
- `.source_cache/<source>-<fingerprint>.duckdb` ของ fingerprint เก่าไม่ถูกลบ (ไฟล์ ~270KB ต่อครั้งที่ลงทะเบียนใหม่)
- eval ข้อ YTD (#64 `revenue_ytd` ทั้งบริษัท) ตกทั้ง legacy และ file source วันนี้ — โมเดล (matcha gpt-4.1) เขียน `month <= 5` แล้ว SUM(revenue_ytd) (F10 เดือน ก.ค. เขียน `= 5`) — กฎ `bg8_ytd_not_summable` ใน contract ห้ามแค่ "sum revenue รายเดือน" ไม่ได้ห้าม sum `revenue_ytd` ข้ามงวดตรง ๆ → ควรเพิ่มกฎใน contract/knowledge (Phase 2) — ไม่ใช่ผลของ file source
