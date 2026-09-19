# RESULT Plan 7 Phase 4.5 — Data protection

**วันที่:** 2026-09-19 | **Branch:** `main` (ยังไม่ push) | **แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §6.6, §6.8
**Baseline:** pytest 892 passed, 3 skipped (`venv/bin/python3.14 -m pytest -q -p no:cacheprovider`) | backup `config.db` + `app.db` อยู่ใน scratchpad ของ session

**Provider ของ eval:** admin default (matcha, gpt-4.1) | **Interpreter:** `venv/bin/python3.14`

## สรุป

| Exit criterion | ผล | ผ่าน? |
|---|---|---|
| ข้อ 1 — ไล่ทุกจุดที่ค่าจริงออกไปหา provider / ถูกเก็บถาวร (ปิด PLAN_7 §11.5) | ตาราง §1 ข้างล่าง: provider 15 จุด (L1–L15), เก็บ/ส่งออก 17 จุด (S1–S17) — พบเกินที่แผนระบุ: history ของแชท, tool loop, hint ของ value verifier, error ของ DB, RAG/golden, keyword index, และ **`/api/v1/query` + telegram ไม่มี audit เลย** | ✅ |
| ข้อ 3 — source ที่ตั้ง `schema_only`: ไม่มี request ใดมีค่าจากผลลัพธ์/ค่าตัวอย่าง (test ดักที่ provider layer ด้วย sentinel) | `tests/unit/test_llm_data_policy.py` 27 ข้อ: `QueryEngine → AIService → MatchaProvider` จริง ดัก payload ที่ขอบ httpx — ภายใต้ `full` กับดักเห็น sentinel **ครบ 5 ชนิด** (ค่าตัวอย่าง+แถวผลลัพธ์, ตัวเลขผลลัพธ์, value lookup, คำตอบเก่าใน history, golden ใน RAG) = ตัวควบคุมบวก; ภายใต้ `schema_only` **0 ใน request ใด ๆ** (one-pass, two-pass), ไม่มี request อธิบายผลเลย, ผู้เรียกยังได้แถวครบ; เรียก `provider.explain_result(rows)` ตรง ๆ = ไม่มีอะไรออก; provider ที่เพิ่มทีหลังถูกห่อเอง; tool loop = 403; policy อ่านไม่ได้/ค่าแปลก = `schema_only` | ✅ |
| ข้อ 3 — eval ของ context ที่ตั้ง `full` ไม่เปลี่ยน | `feed_revenue` บนสำเนา config ที่ migrate แล้ว: **14/14** (baseline `eval_20260919_1028` 14/14), P50 5.8 s / P95 6.6 s (เดิม 5.3 / 6.5), retry 0 — `eval_20260919_2035` | ✅ |
| ข้อ 4 — purge ลบจริงตามกำหนด, metadata อยู่, idempotent | unit 7 ข้อ + บน**สำเนา app.db จริง** (30 วัน): ล้าง `chat_history` **1,285** แถว (`result_data` 2, `sql_result_summary` 1,285) + `chat_session_data` 55; คำถาม 1,513 / SQL 1,511 / คำตอบ 1,513 **เท่าเดิม**; รอบสอง = 0 | ✅ |
| ข้อ 5 — DSR ลบของ user นั้นเท่านั้น | unit 4 ข้อ: ของ user 1 หายทุกตาราง + ไฟล์ export, user 2 ครบ, path นอก export dir ไม่ถูกลบ, audit เหลือแถวแต่ไม่มีตัวตน, รันซ้ำ = 0, app DB รุ่นเก่าที่ขาดบางตารางไม่พัง | ✅ |
| ข้อ 6 — audit ค้นและ export ได้ | unit 5 ข้อ: ทุกคำถาม (รวม cache hit และคำขอที่ถูกปฏิเสธ) = 1 แถว ครบ key/workspace/scope/context/SQL/คอลัมน์/จำนวนแถว, **ไม่มีค่าผลลัพธ์**; filter + CSV; `/api/v1/query` ส่ง `api_key_id` + `source` ถึง engine; audit พังไม่ทำให้คำตอบพัง (log ERROR) | ✅ |
| ข้อ 7 — onboarding / prompt builder เคารพ policy | unit 5 ข้อ: `InspectionResult.to_dict()` + prompt ของ onboarding ไม่มี sentinel, `get_sample_values` = `{}`, keyword index ไม่ถูกสร้าง + ถูกล้างทันทีที่ตั้งเข้มขึ้น | ✅ |
| review อิสระ (งานแตะ policy) — agent แยก อ่านอย่างเดียว 2 รอบ | รอบ 1 (ข้อ 3): **critical 1** (RAG/golden), high 1, medium 1 → แก้ `bccc332`; รอบ 2 (ข้อ 4–7 + การแก้): การแก้รอบ 1 ครบ, **critical 1** (CSV formula injection ใน audit export), high 2 (`intent_state` ข้าม policy, audit blocking) → แก้ `d02802d`; ที่ไม่แก้ = บันทึกไว้ใน §4 / §6 | ✅ |
| pytest | 892 → **936 passed**, 3 skipped (+44); test เดิมแก้ 1 จุด (`test_scheduler` นับ job 3 → 4) | ✅ |

**เจ้าของตัดสิน (ข้อ 2, 2026-09-19):** D4 = Matcha (NT Gateway) ใช้กับข้อมูลอ่อนไหวได้ · D5 = เลื่อน (4.5 ทำ policy ต่อ source เท่านั้น) · retention default 30 วัน · source ใหม่ = `full`

## 1. สำรวจ: ค่าจริงของ business data ออกไปไหนบ้าง (ปิด PLAN_7 §11.5 ข้อสุดท้าย)

"ค่าจริง" = แถวผลลัพธ์, ค่าตัวอย่าง/ค่า distinct ของคอลัมน์, ค่าที่ค้นเจอจากข้อมูล — ไม่รวมชื่อตาราง/คอลัมน์/ชนิดข้อมูล/คำอธิบายจาก contract

### 1A. ออกไปหา LLM provider

ทุก request ไป provider ผ่าน 4 method ของ `AIProvider` เท่านั้น (`generate_content`, `generate_structured`, `explain_result`, `generate_sql`) — ไม่พบการเรียก SDK/httpx ตรงนอก `app/providers/` → **ชั้น provider เป็นจุดบังคับจุดเดียวได้จริง**

| # | จุด (file:line) | ข้อมูลอะไร | เส้นทาง | คุมด้วย (ข้อ 3/7) |
|---|---|---|---|---|
| L1 | `ai/hybrid_flow.py:338,352` `build_explanation` → `provider.explain_result` → `chart_postprocessor.build_explain_prompt` (`json.dumps(data)`) | **แถวผลลัพธ์** (ย่อเมื่อเกิน `EXPLANATION_MAX_ROWS` แต่ยังเป็นค่าจริง) | ทุกคำถามที่มีผลลัพธ์ และ template ไม่ครอบคลุม | sink: `explain_result` ไม่ถูกเรียกจริงเมื่อ policy ≠ `full` (`aggregated_only`: เรียกได้เฉพาะ SQL ที่รวมยอด) |
| L2 | `ai/retry_loop.py:52,114-208` tool loop (`mode="mcp"` และ rescue `escalation_tool_loop_enabled`) | ผลของ tool ทุกตัวกลับเข้า history: `execute_query` (แถว), `get_sample_values` (100 ค่า), `get_table_stats` (**แถวตัวอย่างเต็มแถว**), `get_column_info` (`sample_values`) | `provider.generate_sql` | sink: `generate_sql` ปฏิเสธเมื่อ policy ≠ `full` (file source ปิด 2 tool อยู่แล้ว แต่ `execute_query` ยังไหล) |
| L3 | `api/v1/chat.py:155-169` → `hybrid_flow.py:442-443` | history ของแชท: `ai_response[:300]` ของรอบก่อน = **คำอธิบายที่มีตัวเลขผลลัพธ์** + SQL เดิม | `generate_content(history=…)`; telegram เก็บ `qr.explanation` ใน `user_data["history"]` เช่นกัน (`telegram/dispatcher.py:272`) | sink: policy ≠ `full` → assistant turn เหลือเฉพาะ block SQL |
| L4 | `ai/hierarchy_context.py:173-222` value lookup → `format_value_matches` → "Actual Values Found" ใน prompt (`hybrid_flow.py:553,605`, pass 2 `:1280`) | ค่าจริงจาก `keyword_value_index` (ทุกค่า distinct ของคอลัมน์ groupable — เก็บใน config DB) + `master_hierarchy_values` | `generate_content` / `generate_structured` (pass 1 ได้ `rag_context`, pass 2 ได้ value matches) | source: lookup คืน `[]` เมื่อ policy ≠ `full` |
| L5 | `schema/service.py:367-400` `get_sample_values` → `prompt_builder.py:85-104` "Available Values" ใน system prompt (`query_engine.py:568` `include_samples=True`) | DISTINCT 20 ค่า × ~10 คอลัมน์ + DATA_RANGE | system prompt ของทุกคำถาม | source: คืน `{}` เมื่อ policy ≠ `full` |
| L6 | `value_verifier.py:305-370` → `hybrid_flow.py:476-490,733` | hint แก้ค่า: **ค่าจริงที่ถูกต้อง** ของคอลัมน์ → `retry_history` → retry prompt (`:176-186`) | `generate_content` รอบ retry | source: ไม่ verify เมื่อ policy ≠ `full` |
| L7 | `hybrid_flow.py:752-764` error ของ `execute_query` → retry prompt | ข้อความ error ของ DB อาจมีค่าจริง (เช่น DuckDB conversion error: `Could not convert string '…'`) | `generate_content` รอบ retry | source: ลบ literal ออกจาก error เมื่อ policy ≠ `full` |
| L8 | `schema/prompt_builder.py` schema text จาก `schema_metadata.example_value / sample_values` (config DB), `mcp get_column_info` | ค่าตัวอย่างที่ onboarding เก็บไว้ | system prompt / tool loop | source: ไม่ใส่ค่าตัวอย่างเมื่อ policy ≠ `full` (ตรวจตอนทำข้อ 7) |
| L9 | `context_onboarding.py:285-305` (เก็บ) → `:673-706` (ส่ง) | `sample_values[:10]`, **`all_distinct` ทุกค่าเมื่อ cardinality < 100**, min/max/mean/sum, ยอดรวมรายหมวด (top 20), ตัวอย่าง quality issue | `generate_content` (provider/model/api_url เลือกต่อครั้ง) | source: `inspect()` ของ source ที่ ≠ `full` ไม่เก็บค่าเลย (ข้อ 7) |
| L10 | `api/v1/admin/schema.py:210-211` → `ai/service.py:379` `suggest_mappings` | 3 ค่าตัวอย่าง/คอลัมน์ จาก `get_sample_values` | `generate_structured` / `generate_content` | source เดียวกับ L5 |
| L11 | `api/v1/admin/schema.py:317-344` dimension-families analyze | 3 ค่าตัวอย่าง/คอลัมน์ | `generate_content` | source เดียวกับ L5 |
| L12 | `services/admin_agent.py:512-535` `_summarize_tool_results` | `json.dumps(tool result)[:3000]` — `inspect_view` (= L9), `search_hierarchy` (ค่า hierarchy + alias 30 แถว), `analyze_query_logs` / `review_feedback` (คำถาม + SQL ของผู้ใช้อื่น) | `generate_content`; และ `_load_history` ส่ง 20 ข้อความล่าสุดซ้ำ | L9 ปิดที่ source; ส่วนคำถามของผู้ใช้อื่น = **ไม่ใช่ business data — นอกขอบเขต policy ต่อ source** (บันทึกเป็นข้อค้าง) |
| L13 | `api/v1/schema_analyzer.py:172-222`, `services/analyzer_service.py:39-136` | 5 ค่าตัวอย่าง/คอลัมน์ ของ **ไฟล์ที่ admin upload เอง** (ยังไม่ใช่ source ที่ลงทะเบียน) | `generate_content` | ไม่มี source ให้ผูก policy — **นอกขอบเขต** (admin เลือกส่งเอง); บันทึกเป็นข้อค้าง |
| L14 | RAG: `hierarchy_context.py:95` Vanna context (golden question+SQL, doc, semantic mapping) | literal ใน SQL ตัวอย่าง — **รวม golden ที่ `gen_golden_from_controls` สร้างจาก control totals ของ source เอง (รหัส/ชื่อกลุ่มจริง)** แยกจากของที่คนเขียนไม่ได้ตอน retrieve | system/user prompt (one-pass + pass 1) | source: **ไม่ดึง RAG เลยเมื่อ policy ≠ `full`** (แก้หลัง review รอบ 1 — เดิมจัดเป็น "ความรู้ที่คนเขียน" ซึ่งผิด) |
| L15 | semantic mappings / business rules / instruction ของ context (`prompt_builder.py:51-172`), knowledge จาก contract (`datafeed_knowledge.py`) | ค่ามิติที่ admin/เจ้าของข้อมูลเขียนไว้เป็นกฎ | system prompt | เหมือน L14 |

**หลักการแบ่ง (ใช้ตัดสิน L14–L15):** ภายใต้ `schema_only` provider เห็นได้ = schema + คำถาม + **ความรู้ที่คนเขียน/เจ้าของข้อมูลประกาศ** (contract, กฎ, mapping ที่ admin ใส่); เห็นไม่ได้ = **ทุกอย่างที่ระบบอ่านมาจากแถวข้อมูล** (ผลลัพธ์, sample, distinct, value lookup, ค่าใน hint/error, `master_hierarchy_values` ที่ `source='auto'`, keyword index)

ไม่เรียก provider เลย (ตรวจแล้ว): `auto_analyzer`, `warning_detector`, `dedup_engine`, `scheduler`, `app/telegram/*`, `app/workers/*`, `report_service`

### 1B. ถูกเก็บถาวร / ส่งออกนอก process

| # | จุด | ข้อมูล | ผูก user? | อายุ | คุมด้วย |
|---|---|---|---|---|---|
| S1 | `chat.py:365-368` `chat_history.result_data` | แถวผลลัพธ์ ≤ `HISTORY_RENDER_MAX_ROWS` (1000) | `user_id` | **ไม่มี** | ข้อ 4 purge + โหมดไม่เก็บ |
| S2 | `chat.py:229-241` `chat_history.sql_result_summary` | `str(data)[:1000]` = แถวดิบ | `user_id` | ไม่มี | ข้อ 4 (purge พร้อม S1) |
| S3 | `chat_history.ai_response` | คำอธิบายที่มีตัวเลข | `user_id` | ไม่มี | **คงไว้** (เป็นบทสนทนา; ลบเมื่อ DSR) — ดูข้อค้าง |
| S4 | `chat.py:392-399` `chat_session_data.last_data` | แถวผลลัพธ์เต็ม + chart config (upsert ต่อ conversation) | ผ่าน `conversations.user_id` เท่านั้น | ไม่มี | ข้อ 4 + ข้อ 5 |
| S5 | `report_service.py:151-175` `data/exports/{uuid}.xlsx` + `report_exports` | ผลลัพธ์เต็ม ≤ 100k แถว + คำถาม + SQL | `user_id` | 7 วัน (`export_retention_days`) ✅ | ข้อ 5 ลบตาม user |
| S6 | `tools/report_export.py:56-79` CSV ใน `tempfile.gettempdir()/nt_reports/` | ผลลัพธ์เต็ม | **ไม่ผูก** | **ไม่มี cleanup** | ข้อ 4 (sweep ตามอายุไฟล์) |
| S7 | `query_engine.py:88-178` `_query_cache` | `QueryEngineResult` ทั้งก้อน (ทุกแถว) ใน memory | key ไม่มี user (มี scope + allowlist + build) | 30 นาที / 500 entries | ข้อ 3 (policy ใน key), ข้อ 5 (`clear_query_cache()`), โหมดไม่เก็บ = ไม่ cache |
| S8 | `ai/service.py:250-276` `query_correction_log` | คำถาม + ค่าเดิม + **ค่าจริงที่ถูก** | ไม่ผูก | ไม่มี | ปิดเองเมื่อ L6 ปิด (policy ≠ `full`); ข้อ 4 purge ตามอายุ |
| S9 | `hierarchy_service.py:575-597` `unmatched_keywords` | keyword + `last_question[:500]` | ไม่ผูก | ไม่มี | คำถามของผู้ใช้ ไม่ใช่ business data — ข้อค้าง |
| S10 | `schema/keyword_index.py:106-141` `keyword_value_index` (config DB) | **ทุกค่า distinct** ของคอลัมน์ groupable | — | rebuild ทับ | ข้อ 7: ไม่ build ให้ source ที่ ≠ `full` |
| S11 | `master_hierarchy_values` (`source='auto'`), `schema_metadata.sample_values/example_value` (config DB) | ค่าจริงที่ดูดจากข้อมูล | — | — | ข้อ 7: onboarding/extract ไม่เก็บให้ source ที่ ≠ `full` |
| S12 | `admin_agent.py:474-492` `admin_agent_messages.tool_result` | tool result เต็ม (รวม L9/L12) | conversation `user_id` | ไม่มี | ข้อ 5 ลบตาม user |
| S13 | `telegram/dispatcher.py:285-301` | 15 แถวเป็นข้อความ + กราฟ 20 แถว → **Telegram Bot API (บุคคลที่สาม)** | chat_id | — | ไม่ใช่ LLM — **นอก `llm_data_policy`**; ข้อค้าง (ควรปิด telegram ต่อ workspace/source ที่อ่อนไหว) |
| S14 | `audit_service.py:38-51` | `old/new_value` ของ config | `user_id` | ไม่มี | ⚠️ **bug เดิม: INSERT ลง `audit_log` ซึ่งไม่มี (ตารางจริง `config_audit_log`) — ทุก write ล้มเงียบ** (`FIX_NOTES`) |
| S15 | log: `retry_loop.py:113` (args ของ tool = SQL เต็ม), `query.py:90-93` (scope), `value_verifier.py:102,332,348` (col=value, DEBUG), `hybrid_flow.py:481-487` (ค่าที่แก้, INFO) | literal ใน SQL / ค่าที่แก้ | — | ตาม log rotation | L6 ปิด = log ค่าที่แก้หายไปด้วย; `PIIRedactingFormatter` ไม่รู้จัก business value (regex: email/เบอร์/บัตร/secret) — ดู §11.5: **พึ่ง policy ที่ต้นทางแทนการเพิ่ม regex** |
| S16 | `ai/trace.py` | `question[:80]`, tokens, timings — **ไม่มีแถว/ค่า** | — | log | ไม่ต้องทำ |
| S17 | Vanna/Chroma | DDL, กฎ, mapping, golden Q+SQL — ไม่มีแถวผลลัพธ์ | — | rebuild ตอน sync | แยก workspace แล้ว (Phase 4b) |

### 1C. Audit ของคำถาม — ของที่มีอยู่

- **ไม่มีตาราง query log** — ที่ใกล้สุดคือ `chat_history` (เขียนจาก `chat.py` ที่เดียว): มี user / คำถาม / SQL / context; **ไม่มี** api_key, workspace, scope, คอลัมน์, จำนวนแถว
- **`POST /api/v1/query` (ช่องทางของ API key) และ telegram ไม่เขียนอะไรเลย** — มีแค่ตัวนับ `api_key_usage`; ช่องทางที่ Phase 4 เปิดให้ระบบภายนอก = ช่องทางที่ตรวจย้อนหลังไม่ได้
- ค้นได้: `GET /admin/query-logs` (`admin/analytics.py:258`, filter วันที่/context/user/error) — ไม่มี export
- → ข้อ 6 ต้องมีตารางใหม่ (เขียนที่ `QueryEngine.query` = จุดเดียวที่ chat / query / telegram ผ่าน) — ไม่ซ้ำกับของเดิม

## 2. แผนย่อย + exit criteria (ตามที่เสนอก่อนลงมือ)

| ข้อ | ทำอะไร | Exit (วัดได้) |
|---|---|---|
| 3a | `data_sources.llm_data_policy` + `llm_provider_allowlist` (migration idempotent; source เดิม = `full`), อยู่บน `ResolvedSource`; `policy_for_table()`; admin API `PUT /admin/sources/{name}/policy` | migration รันซ้ำได้; อ่านไม่ได้ / ค่าไม่รู้จัก = `schema_only`; config ที่ยังไม่ migrate = พฤติกรรมเดิม |
| 3b | **sink ที่ชั้น provider** — `AIProvider.__init_subclass__` ห่อ 4 method ของทุก subclass (รวม provider ที่เพิ่มในอนาคต): อ่าน policy ของ request จาก ContextVar (แบบ `request_scope`) → `explain_result` ไม่ออก, `generate_sql` ปฏิเสธ, history เหลือ SQL, provider นอก allowlist ปฏิเสธ, ค่าจากแถวผลลัพธ์ของ request โผล่ใน payload ใด ๆ = ปฏิเสธ (กัน caller ในอนาคตที่ลืม) | test: เรียก `provider.explain_result(sentinel)` ตรง ๆ ภายใต้ `schema_only` → HTTP/SDK ปลอมไม่ได้รับอะไรเลย |
| 3c | **source ของค่า** — `get_sample_values`, value lookup, value verifier, error ของ execute คืนของว่าง/ไม่มี literal เมื่อ policy ≠ `full`; คำอธิบาย = template (`build_template_answer`) แล้วตกไป "พบข้อมูล N รายการ" | **test ดักหลัก:** `QueryEngine.query` ครบ pipeline บน source ทดสอบที่ทุกค่าเป็น sentinel, ดัก payload ที่ขอบ HTTP ของ provider → ไม่มี sentinel ใน request ใดเลย (และ fail บน code เดิม); ตั้ง `full` → test เดิม + eval `feed_revenue` ไม่เปลี่ยน |
| 3d | cache key รวม policy; QueryEngine เลือก provider ใน allowlist (ผู้เรียกระบุ provider นอก allowlist = 403) | test |
| 4 | `purge_results(days)` ใน scheduler: ล้าง `result_data` + `sql_result_summary` + `chat_session_data` + CSV ชั่วคราว (S6) + `query_correction_log` ที่เกิน N วัน; `admin_config.result_retention_days`, override ต่อ workspace; `store_result_data=false` = ไม่เขียน S1/S2/S4 และไม่ cache | test: แถวเก่าถูกล้าง แถวใหม่อยู่, คำถาม/SQL/ai_response อยู่ครบ, รันซ้ำ = 0 |
| 5 | `DELETE /admin/users/{id}/data` (+ `dry_run` นับก่อน): history, session data, conversations, feedback, chart feedback, exports + ไฟล์, admin agent, query cache; audit ของคำถาม = ตัดตัวตนออก (ไม่ลบแถว) | test: ของ user A หายหมด ของ B ไม่แตะ; รันซ้ำ = 0 |
| 6 | ตาราง `query_audit` (app DB) เขียนที่ `QueryEngine.query`: เวลา, user, api_key, workspace, context, scope, คำถาม, SQL, คอลัมน์, จำนวนแถว, provider, policy, cache_hit, error; `GET /admin/query-audit` (filter + `format=csv`) | test: `/query` ด้วย key → มีแถว audit ครบ field; export CSV ได้ |
| 7 | onboarding `inspect()` / keyword index / hierarchy extract / schema text ไม่เก็บและไม่ส่งค่าของ source ที่ ≠ `full` | test sentinel ที่ onboarding + admin endpoints (L9–L11) |
| — | review อิสระ (agent แยก อ่านอย่างเดียว) ก่อนปิดข้อ 3 และข้อ 7 | ไม่เหลือ critical/high |

## 3. สิ่งที่ทำ

### ข้อ 3 `llm_data_policy` + `llm_provider_allowlist` (`fc204ee`, `bccc332`)
- `data_sources.llm_data_policy` (`DEFAULT 'full'` → source เดิมและใหม่ทุกตัวเป็น `full`), `llm_provider_allowlist` (JSON list; NULL = ทุกตัว); ลงทะเบียนซ้ำ (contract ใหม่) คง policy เดิม; `PUT /admin/sources/{name}/policy` (ชื่อ provider ที่ไม่รู้จัก = 400)
- **sink:** `AIProvider.__init_subclass__` ห่อ `generate_sql` / `explain_result` / `generate_content` / `generate_structured` ของทุก subclass → `guard_call` อ่าน `request_llm_policy` (ContextVar ที่ `QueryEngine` ตั้งเมื่อรู้ source): provider นอก allowlist = ปฏิเสธ (ทุก policy); policy ≠ `full`: tool loop ปฏิเสธ, `explain_result` คืน template โดยไม่เรียก LLM (`aggregated_only` + SQL รวมยอด = เรียกได้), history เหลือเฉพาะ block SQL, payload ที่มีค่าจากแถวผลลัพธ์ของ request = ปฏิเสธ
- **source ของค่า** คืนของว่างเมื่อ policy ≠ `full`: `get_sample_values`, value lookup, value verifier, RAG (`get_vanna_context_string`), error ของ `execute_query` ถูกลบ literal (`PolicyMCPClient`), history ถูกตัดคำตอบเก่าใน `QueryEngine` (two-pass ฝัง history ในข้อความ prompt)
- `QueryEngine`: resolve context/source **ก่อน** เลือก provider; provider นอก allowlist → ผู้เรียกระบุเอง = `LLMPolicyError` (403), ไม่ระบุ = เลือกตัวแรกใน allowlist ที่ตั้งค่าไว้; cache hit ต้อง policy ตรง + provider ยังอยู่ใน allowlist; `include_samples` (อยู่ใน key ของ prompt cache) ตาม policy
- fail closed: NULL / ค่าไม่รู้จัก / อ่านไม่ได้ / engine ที่ไม่ใช่ config DB = `schema_only`; allowlist ที่ parse ไม่ได้ = ไม่มีใครผ่าน; registry ก่อน Phase 4.5 (ไม่มีคอลัมน์) = `full`

### ข้อ 4 Retention (`a47adfe`)
`app/services/retention.py` + job รายวันใน scheduler; `result_retention_days` (default 30, 0 = ไม่ลบ), `store_result_data` (feature flag), override ต่อ workspace (`workspaces.result_retention_days` / `store_result_data`, `PUT /admin/workspaces/{id}/retention`); ล้าง `result_data` + `sql_result_summary` + `chat_session_data` + `query_correction_log` + CSV ชั่วคราวของ chat tool; โหมดไม่เก็บ = ไม่เขียน history rows / session data / query cache

### ข้อ 6 Audit (`e3d16f9`)
`query_audit` (app DB, สร้างเองตอนใช้ครั้งแรก) เขียนที่ `QueryEngine.query` — session แยก ไม่ commit transaction ของผู้เรียก; `api_key_id` + `channel` ส่งมาจาก `/api/v1/query` (= `source` ของผู้เรียก), chat, telegram; `GET /admin/query-audit` filter + `format=csv`

### ข้อ 5 DSR (`f7b90a1`)
`DELETE /admin/users/{id}/data` (`dry_run=true` เป็นค่าเริ่มต้น); การลบถูกบันทึกใน `query_audit` (`channel='dsr_erase'`) เพราะ `AuditService` เขียนไม่ลง (ดู FIX_NOTES)

### ข้อ 7 Onboarding / ต้นทางอื่น (`0dcb939`)
`InspectionResult.values_allowed` (จาก `policy_for_table`) → `to_dict()` เหลือโครงสร้าง; keyword index ไม่ build + ถูกล้างเมื่อ rebuild หรือทันทีที่ตั้งเข้มขึ้นผ่าน API; `search_aliases` / `extract_hierarchy.py` ข้าม context ที่ source ≠ `full`

## 4. Review อิสระ

**รอบ 1** (agent แยก อ่านอย่างเดียว, บน `fc204ee`):
- **CRITICAL — RAG/golden:** `gen_golden_from_controls` เขียน golden SQL จาก control totals ของ source เอง (รหัส/ชื่อกลุ่มจริง) → Chroma → `get_vanna_context_string` → prompt โดยไม่ผ่านการตรวจใด (ตารางสำรวจของเราจัด L14 เป็น "ความรู้ที่คนเขียน" — ผิดสำหรับของชิ้นนี้) → source ที่ ≠ `full` ไม่ได้ RAG เลย + test ด้วย golden ที่มี sentinel
- HIGH — `is_aggregate_sql` เป็น regex: window function / `t.*` + subquery ผ่าน → ไม่นับ `OVER (` และ `*`; เพดานที่เหลือ (GROUP BY บน key ไม่ซ้ำ) เขียนไว้ใน code + docs
- MEDIUM — `SchemaService` standalone ชี้ `self.engine` ไป business DB → `policy_for_table` อ่านผิด DB = `full` → DB ที่ไม่มีตาราง config เลย = `schema_only`
- ยืนยันว่าถูก: argument binding ของทุก provider, tool loop fail closed, รูปแบบ history ตรงกับที่ `chat.py` เขียน, ContextVar ข้าม `create_task` / `to_thread`, `_scoped` / `_pinned` คง policy, cache ของ prompt และของคำตอบ, allowlist + fallback

**รอบ 2** (บน `6edf8cd..bccc332` — ข้อ 4–7 + การแก้รอบ 1): ยืนยันว่าการแก้รอบ 1 ครบ (RAG มี call site เดียวและถูก gate; hierarchy/กฎ/instruction ใน system prompt มีแต่ชื่อคอลัมน์/ระดับ ไม่มีค่าจาก `master_hierarchy_values`; `datafeed_knowledge` เขียนจาก contract เท่านั้น) และไม่พบเส้นทางอื่นในการตอบคำถามปกติ — เจอใหม่ แก้แล้ว `d02802d`:
- **CRITICAL — CSV export ของ `/admin/query-audit` เสี่ยง formula injection:** คำถามที่ผู้เรียกพิมพ์ (`=HYPERLINK(...)`) ลง cell ตรง ๆ → cell ที่ขึ้นต้นด้วย `= + - @` ถูกนำหน้าด้วย `'` (เฉพาะ CSV; แถวใน DB และ JSON ไม่เปลี่ยน)
- HIGH — `intent_state` เก็บ intent ต่อ conversation อย่างเดียว: ค่า filter ที่ value lookup เจอบน source `full` ในรอบก่อน เข้า prompt ของ pass 1 ของ source ที่เข้มในรอบถัดไปได้ (ต้องเปิด `intent_state_enabled` — default ปิด) → source ที่ ≠ `full` ไม่รับ intent เก่า + test
- HIGH — `query_audit.record` เป็น SQLite I/O แบบ blocking ใน async path ของทุกคำถาม → `asyncio.to_thread`; ไม่ audit `CancelledError` (ผู้เรียกตัดการเชื่อมต่อ)
- MEDIUM (ไม่แก้ — บันทึก): `PolicyMCPClient` ลบ literal เฉพาะ `error` ใน dict ที่คืนมา ไม่ใช่ exception ที่ถูก raise — ตรวจแล้ว**ตอนนี้ไม่รั่ว** (`execute_select` จับทุก exception แล้วคืน dict; raise เฉพาะ `SourceUnavailable` ซึ่งไม่มีค่าจากแถว และต้องไปถึงผู้ใช้ทั้งก้อน) แต่เป็นจุดเดียวที่กัน; source ใหม่ = `full` (เจ้าของตัดสินแล้ว); ช่องว่างของ DSR (รายการใน §6)
- ยืนยันว่าถูก: SQL ของ retention (expanding bind, `days=0`, รูปแบบเวลา), `commonpath` ของ DSR (realpath ทั้งสองข้าง), key ของ prompt cache, การสลับลำดับ resolve source ก่อน provider, `to_thread` กับ Session ของ scheduler, telegram ส่ง `user_id` เข้า dedup = แก้ bug เดิม (ผู้ใช้ต่างคนถามเหมือนกันใน 5 วินาทีเคยบล็อกกัน)

## 5. สถานะ DB จริง
ยัง**ไม่ได้** migrate `config.db` / `app.db` จริงใน session นี้ (ทดลองบนสำเนาใน scratchpad ทั้งหมด) — ต้องรัน `scripts/migrate_data_sources.py` + `scripts/migrate_workspaces.py` ก่อน start; ⚠️ job retention รอบแรก (30 วัน) จะล้าง 1,285 แถวผลลัพธ์เก่า

## 6. ค้าง / ข้อสังเกต
- Admin **UI** ของ policy / retention / audit / DSR ยังไม่มี (API ครบ)
- D5 (classification ต่อคอลัมน์, k ≥ 5, mask) เลื่อน → `aggregated_only` ยังเป็นการตรวจข้อความ SQL
- นอก `llm_data_policy`: Telegram (S13), schema analyzer ไฟล์ upload (L13), admin agent สรุปคำถาม/SQL ของผู้ใช้อื่น (L12)
- ค่าที่ extract ไว้แล้ว (`master_hierarchy_values`, `schema_metadata.sample_values`) ของ source ที่ตั้งเข้มขึ้น ยังอยู่ใน config DB (ไม่ถูกส่งแล้ว)
- `ai_response` (ข้อความคำตอบ มีตัวเลข) ไม่หมดอายุตาม retention — ลบเมื่อ DSR เท่านั้น ← ต้องการให้หมดอายุด้วยไหม
- audit เขียนไม่ได้ = ตอบต่อ + log ERROR ← workspace การเงินต้องการ fail closed ไหม
- bug เดิมที่พบ (งานแยก): `AuditService` เขียนลงตารางที่ไม่มี; admin tool `search_hierarchy` เรียก method ที่ไม่มี; flag `rag_enabled` ไม่ได้คุม RAG ใน hybrid flow
- ⚖️ §6.6 ข้อ 8 (PDPA) รอ DPO — ไม่ใช่งานของ phase นี้

## Commits
```
e818da3 docs(P7-4.5): survey of every place business values reach a provider or are stored; sub-plan and exit criteria
fc204ee feat(P7-4.5): llm_data_policy and provider allowlist per source, enforced at the provider layer
a47adfe feat(P7-4.5): retention of stored result rows - daily purge and a don't-store mode
e3d16f9 feat(P7-4.5): audit of every question - key, workspace, scope, context, SQL, columns, row count
f7b90a1 feat(P7-4.5): DSR - erase one user's traces
0dcb939 feat(P7-4.5): onboarding, admin schema pages, keyword index and hierarchy lookup obey the source's policy
bccc332 fix(P7-4.5): review round 1 - no RAG context for a restricted source; stricter aggregate check; a DB that isn't the config DB is an unreadable policy
d02802d fix(P7-4.5): review round 2 - CSV export neutralises formula cells; a restricted source gets no stored intent; the audit is written off the event loop
```
