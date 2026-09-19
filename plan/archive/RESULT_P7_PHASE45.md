# RESULT Plan 7 Phase 4.5 — Data protection

**วันที่:** 2026-09-19 | **Branch:** `main` (ยังไม่ push) | **แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §6.6, §6.8
**Baseline:** pytest 892 passed, 3 skipped (`venv/bin/python3.14 -m pytest -q -p no:cacheprovider`) | backup `config.db` + `app.db` อยู่ใน scratchpad ของ session

> สถานะ: **ข้อ 1 (สำรวจ) เสร็จ — ข้อ 2 รอเจ้าของตัดสิน** (ดูท้ายไฟล์)

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
| L14 | RAG: `hierarchy_context.py:95` Vanna context (golden question+SQL, doc, semantic mapping) | literal ใน SQL ตัวอย่าง / `target_condition` (ค่ามิติที่ admin หรือ contract เขียนไว้) — **ไม่มีแถวผลลัพธ์ ไม่มี sample_values** | system/user prompt | ถือเป็น **knowledge ที่คนเขียน** ไม่ใช่ค่าที่ดูดจากข้อมูล → ยังส่ง (ดูหลักการข้างล่าง); `rag_enabled=false` ใน config จริง |
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

## 2. แผนย่อย + exit criteria

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

## ข้อค้างที่รอเจ้าของตัดสิน (ข้อ 2)

ดูคำถามใน session — D4, D5, ค่า default ของ retention, default policy ของ source ใหม่
