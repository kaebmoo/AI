# Prompt สำหรับ session ใหม่ — Plan 7 Phase 4.5: Data protection (เขียน 2026-09-19)

> ส่งทั้ง block ข้างล่างให้ session ใหม่ใน repo `AI`

```
ทำงานต่อ Plan 7 (Data Source as a Service) ใน repo /Users/seal/Documents/GitHub/AI — branch main
origin/main = 6edf8cd (เจ้าของ push เองแล้ว) — commit ใหม่ห้าม push จนกว่าจะสั่ง; ห้าม rebase / force-push

## อ่านก่อน (บังคับ)
- plan/PLAN_7_DATA_SOURCE_SERVICE.md — หัวสถานะ, §6 ทั้งหัวข้อ (โดยเฉพาะ §6.6 ตารางสถานะ + มาตรการ 1–8, §6.8 Phase 4.5 + exit), §11.1 (D4, D5 ยังไม่ตัดสิน), §11.5 สองข้อท้าย, §12
- plan/archive/RESULT_P7_PHASE4.md, plan/FIX_NOTES.md หัวข้อ "จาก Plan 7 Phase 4" และ "จาก ebt 1.3.x + REMAIN-12"
- docs/changelogs/PLAN_7_DATA_SOURCE_SERVICE_P1_4.md, docs/DEPLOYMENT_SECURITY.md, docs/manuals/manual_api_keys.md
- code: app/services/ai/service.py + app/services/ai/hybrid_flow.py + app/services/ai/retry_loop.py (ทุกจุดที่เรียก provider: generate_content / generate_structured / explain_result / suggest_mappings),
  app/providers/base.py + providers ทุกตัว, app/services/context_onboarding.py + app/services/schema/prompt_builder.py (sample_values / all_distinct ที่เข้า prompt),
  app/services/ai/hierarchy_context.py (value lookup → "Actual Values Found" ใน prompt), app/services/value_verifier.py, app/services/warning_detector.py,
  app/models/chat.py (chat_history.result_data — comment เรื่อง retention job), app/services/scheduler.py (background jobs), app/services/audit_service.py,
  app/core/logging.py (PIIRedactingFormatter), app/services/data_sources.py, app/services/workspaces.py, app/services/query_engine.py (cache)

## สถานะตอนนี้ (2026-09-19)
- Phase 1–4 ✅ | REMAIN-9 ทั้งข้อ ✅ | REMAIN-10 ✅ | REMAIN-11 ✅ | REMAIN-12 ส่วนใหญ่ ✅
- pytest: 892 passed, 3 skipped — `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` (python3.10 ใน venv ไม่มี pytest; vanna/chromadb import ได้เฉพาะ python3.10)
- config.db จริง: workspace `default` (revenue, expense, transfer price, pl_costtype) + `nt-report` (feed_revenue 2.3.0, feed_expense 1.2.0, feed_sales 1.3.0, feed_ebt 1.4.0 — file source ทั้งหมด);
  two_pass_enabled=true, rag_enabled=false; ยังไม่มี API key จริง (เจ้าของออกเอง)
- eval ล่าสุดบน config จริง: revenue 14/14, expense 12/12, sales 12/12, ebt 35/36 (P50 5.3–6.7 s)
- ข้อมูลรั่วออกนอกระบบตอนนี้ (PLAN_7 §6.6): explain_result ส่งแถวผลลัพธ์ให้ provider; onboarding/prompt ส่ง sample values; value lookup ใส่ค่าจริงใน prompt;
  chat_history.result_data ไม่มีวันหมดอายุ; ไม่มี classification / DSR / audit export

## คำสั่งที่ใช้บ่อย
- ทดลองกับ config สำเนา: CONFIG_DB_URL=sqlite:///<copy> DATA_SOURCE_CACHE_DIR=<scratch> ... (ห้ามทดลองบน config.db / app.db จริงโดยไม่ backup ลง scratchpad)
- eval: venv/bin/python3.14 -m scripts.eval.run_eval --context feed_<d> (LLM จริง ~2 นาที/12 ข้อ — รันเท่าที่จำเป็น; ต้อง clear_query_cache() เมื่อทดสอบ prompt ใหม่ในสคริปต์เอง)
- ลงทะเบียน source: python -m scripts.datafeed.register_file_source --domain <d> --source /Users/seal/Documents/GitHub/NT-Report/DataFeed/dist (หรือ POST /admin/sources/register)

## งานตามลำดับ (commit เป็นก้อนต่อข้อ, วัดจริงก่อน/หลัง)
0. baseline pytest; backup config.db + app.db ลง scratchpad
1. **สำรวจก่อนออกแบบ (ห้ามข้าม):** ไล่ทุกจุดที่ข้อมูลจากผลลัพธ์/ค่าจริงของ business data ออกไปหา provider หรือถูกเก็บถาวร
   (explain, retry feedback ที่มี error + ค่า, value lookup, sample values ใน system prompt, onboarding, suggest_mappings, admin agent, telegram, report export, query cache, chat_history, logs, trace)
   → ตารางใน plan/archive/RESULT_P7_PHASE45.md: จุด / ข้อมูลอะไร / ไปไหน / ควบคุมด้วย policy ไหน — นี่คือฐานของ test ดัก (PLAN_7 §11.5)
2. เสนอแผนย่อย + exit criteria แล้ว **หยุดถามเจ้าของ** เรื่องที่ยังไม่ตัดสิน (ดูข้างล่าง) ก่อนเขียน code ที่ขึ้นกับคำตอบ; ส่วนที่ไม่ขึ้นกับคำตอบทำต่อได้เลย
3. `llm_data_policy` ต่อ source (`data_sources`): `schema_only` / `aggregated_only` / `full` (default ของ source เดิม = `full` → พฤติกรรมเดิมไม่เปลี่ยน) + `llm_provider_allowlist` ต่อ source
   - `schema_only`: provider เห็นแค่ schema + คำถาม; ไม่มี sample values / value lookup / แถวผลลัพธ์ / ค่าใน retry feedback; คำอธิบายผลใช้ template (มี template_answers อยู่แล้ว — ดู flag `template_answers_enabled`)
   - บังคับที่ **ชั้น provider** (จุดเดียวที่ทุก request ผ่าน) ไม่ใช่กระจายตาม caller — caller ลืม = ต้องไม่รั่ว
   - **Exit:** source ที่ตั้ง `schema_only` → test ดักที่ provider layer: ไม่มี request ไหนมีค่าจากผลลัพธ์/ค่าตัวอย่างเลย (ใช้ค่า sentinel ในข้อมูลทดสอบแล้ว assert ว่าไม่ปรากฏใน payload ใด ๆ); eval ของ context ที่ตั้ง `full` ไม่เปลี่ยน
4. Retention: purge job ของ `chat_history.result_data` เกิน N วัน (ตั้งค่าได้ — admin_config; ต่อ workspace ถ้าทำได้ไม่ซับซ้อน) + โหมด "ไม่เก็บผลลัพธ์" — **Exit:** job ลบจริงตามกำหนด, metadata (คำถาม/SQL) ยังอยู่, idempotent
5. DSR: endpoint ลบข้อมูลของ user (history, feedback, cache, export files) — zero-import = ข้อมูลหลักอยู่ที่เจ้าของข้อมูล ฝั่งเราลบแค่ร่องรอยของ user
6. Audit ของคำถาม: key / workspace / scope / context / SQL / คอลัมน์ / จำนวนแถว — ค้นและ export ได้ (ดูของที่มีใน query log / audit_service ก่อน อย่าสร้างซ้ำ)
7. Onboarding / prompt builder เคารพ policy เดียวกัน (ไม่ส่ง sample ของ source ที่ไม่ใช่ `full`)
8. อัปเดต RESULT_P7_PHASE45.md, PLAN_7, ROADMAP, FIX_NOTES, docs (DEPLOYMENT_SECURITY, ADMIN_CONFIGURATION, manual ที่เกี่ยว), docs/changelogs; แล้วหยุดถามก่อน Phase 5
   (ถ้า context ใกล้เต็มก่อนถึงข้อนี้ ให้หยุดแล้วเขียน prompt ส่งต่อ session ถัดไป)

## ข้อค้างที่รอเจ้าของตัดสิน (อย่าตัดสินเอง — ถามตอนข้อ 2)
- D4: มี LLM ภายใน/ในประเทศที่ใช้กับข้อมูล confidential/personal ได้ไหม (ถ้าไม่มี: source อ่อนไหวต้อง `schema_only` เท่านั้น)
- D5: ใครกำหนด data classification ต่อคอลัมน์ (contract ของเจ้าของข้อมูล / admin ตอน onboard) และจะทำ classification ใน Phase 4.5 หรือเลื่อน — แผนเขียนว่า "ไม่ระบุ = confidential" ซึ่งถ้าใช้ตรง ๆ จะเปลี่ยนพฤติกรรมของทุก context ทันที
- ค่า default ของ retention (N วัน) และ default policy ของ source ใหม่ (`full` เพื่อไม่เปลี่ยนพฤติกรรม หรือ `aggregated_only`)
- ข้อค้างจาก Phase 4 (ไม่บล็อก 4.5): admin UI ของ workspaces/sources; context ที่ไม่มีอยู่จริงของผู้เรียกที่ไม่ถูกจำกัดยังตกไป legacy DB พร้อม prompt เปล่า (reviewer แนะนำ 400 ทุกกรณี — เปลี่ยนพฤติกรรม legacy); ออก key จริงให้ portal
- ⚖️ ประเด็น PDPA ใน §6.6 ข้อ 8 เป็นกรอบเทคนิค ต้องให้ DPO/กฎหมายทบทวน — ไม่ใช่งานของ session นี้

## กติกา
- พฤติกรรมของ context/ source ที่ไม่ได้ตั้ง policy ต้องไม่เปลี่ยน; test เดิมต้องไม่พัง; ทุกความสามารถใหม่ต้องมี test ที่ fail บน code เดิม
- ความปลอดภัย: ห้ามผ่อน lock ของ DuckDB (read_only, allowed_paths, enable_external_access=false, lock_configuration, temp_directory=''); SQL จาก LLM ผ่าน check_select เสมอ;
  scope / allowlist / request_pinned ห้ามอ่อนลง; งานที่แตะ gate / scope / auth / policy ให้ขอ review อิสระ (agent แยก, อ่านอย่างเดียว) ก่อนปิดงาน — Phase 4 รอบแรก review เจอ critical จริง
- fail closed: อ่าน policy ไม่ได้ = ใช้ policy ที่เข้มที่สุด ไม่ใช่ `full`
- ข้อควรรู้ที่เจอมาแล้ว:
  - intent ของ Pass 1 (โมเดลเล็ก) เชื่อไม่ได้ทั้งสองทาง: เติม filter จากกฎเอง / ไม่ดึง filter ที่คำถามระบุ → ของที่ต้องบังคับ ให้ตรวจแบบ deterministic ไม่ใช่ prompt
  - anyio TaskGroup ห่อ exception เป็น ExceptionGroup (endpoint ที่เปิด MCP session เอง) — refusal ต้องแกะก่อนตัดสิน status code
  - query cache 30 นาทีไม่รวมเวอร์ชัน code; cache key รวม scope + allowlist + build ของ source — ถ้า policy มีผลต่อคำตอบ ต้องรวมใน key ด้วย
  - test ไม่ได้แยก CONFIG_DB_URL อัตโนมัติ — test ที่เขียน config/app DB ใช้ DB ชั่วคราวเสมอ; QueryEngine test ต้อง patch source_resolver (ไม่งั้นอ่าน config.db จริง)
  - app ห้าม import จาก scripts/ (ทิศทางเดียว: scripts → app)
  - context ที่สร้างหลัง migration มี workspace_id NULL = 'default' ทุกจุด
  - DuckDB: LIKE → ILIKE, `/` เป็นทศนิยม, SELECT DISTINCT … LIMIT ไม่ deterministic, CSV pin dialect, TEMP view อ้างต้นฉบับด้วย "<catalog>".main.<view>
  - SourceUnavailable = กำลัง publish (ต้องไปถึงผู้ใช้ ห้ามส่งให้ LLM แก้ SQL)
  - tests/unit/test_vanna_documentation.py รันเดี่ยว ๆ error (pandas circular import บน py3.14) — full suite ผ่าน
  - ruff มี error เดิมใน deps.py (E402/F401), schema.py (F401), vanna_service.py (E741) — ไม่ใช่ของเรา
  - CLAUDE.md / AGENTS.md ถูก gitignore (แก้ได้ ต้อง sync กัน แต่ commit ไม่ได้)
  - NT-Report ออก contract ใหม่บ่อย: เพิ่มตาราง/คอลัมน์ต้องลงทะเบียน source ใหม่; knowledge re-sync เอง
- commit เป็นก้อนต่อข้อ; ข้อความ commit ห้ามมีชื่อโมเดลหรือ emoji; ลงท้าย Co-Authored-By: Claude <noreply@anthropic.com>
- ถ้าเจอสิ่งที่ขัดกับแผน ให้หยุดและรายงานพร้อมทางเลือก ไม่ตัดสินใจเองเงียบ ๆ
- จบแต่ละข้อ/phase สรุป: ทำอะไร, ตัวเลข exit criteria, commit list, ข้อค้างที่ต้องให้ผมตัดสิน
```
