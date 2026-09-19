# Prompt สำหรับ session ใหม่ — Plan 7 Phase 5: ถามข้ามหลาย context (เขียน 2026-09-19)

> ส่งทั้ง block ข้างล่างให้ session ใหม่ใน repo `AI`

```
ทำงานต่อ Plan 7 (Data Source as a Service) ใน repo /Users/seal/Documents/GitHub/AI — branch main
origin/main = 6edf8cd; local นำอยู่ 11 commit (d7c9503 + Phase 4.5: e818da3..52d26b0 + prompt นี้) — ยังไม่ push; commit ใหม่ห้าม push จนกว่าจะสั่ง; ห้าม rebase / force-push
⚠️ มี session แยก (worktree อื่น) กำลังแก้ AuditService + admin tool search_hierarchy — อย่าแตะ app/services/audit_service.py, app/tools/admin/system_tools.py, tests/unit/test_audit_service.py; ถ้า main มี commit ใหม่จากงานนั้น ให้ทำต่อบนนั้น

## อ่านก่อน (บังคับ)
- plan/PLAN_7_DATA_SOURCE_SERVICE.md — หัวสถานะ, §2 เป้าหมายข้อ 5, §3.3–3.4 (scope, freshness), §5 Phase 5 (+ exit), §6.2 (ห้าชั้นของสิทธิ — สิทธิที่ใช้จริง = เพดานของ key ∩ entitlement), §7 แถว "คำถามข้ามโดเมนตอบผิดแบบมั่นใจ", §11.7
- plan/archive/RESULT_P7_PHASE45.md (ทั้งไฟล์ — โดยเฉพาะ §3 ข้อ 3 และ §4 review สองรอบ), plan/archive/RESULT_P7_PHASE4.md, plan/archive/RESULT_P7_PHASE2.md (นิยาม EBT / ยอดขาย ≠ รายได้)
- plan/FIX_NOTES.md หัวข้อ "จาก Plan 7 Phase 4.5", "จาก Plan 7 Phase 4", "จาก ebt 1.3.x + REMAIN-12", "จาก Plan 7 Phase 3"
- docs/DEPLOYMENT_SECURITY.md (หัวข้อ Phase 4.5), docs/PORTAL_INTEGRATION.md, docs/DATAFEED_INTEGRATION.md
- code: app/services/query_engine.py (ทั้งไฟล์ — query() ตั้ง/รีเซ็ต ContextVar 3 ตัว, _execute_query: resolve source → policy → provider → prompt → audit, cache validity, detect_context_from_question),
  app/core/llm_policy.py (RequestPolicy, guard_call, restricted, rows_may_reach_llm, PolicyMCPClient, no_llm_explanation),
  app/services/data_sources.py (ResolvedSource: version / data_as_of / llm_data_policy / llm_providers; request_scope, request_pinned, ScopeError, policy_for_context),
  app/services/workspaces.py (canonical_context, check_context, workspace_of_context, ContextNotAllowed), app/services/retention.py (stores_results), app/services/query_audit.py,
  app/services/ai/hybrid_flow.py (query_hybrid, build_explanation), app/services/ai/template_answer.py, app/providers/chart_postprocessor.py (build_explain_prompt),
  app/api/v1/query.py + app/api/v1/chat.py (ทางเข้า, _find_refusal, SSE), app/services/datafeed_knowledge.py (instruction ของ feed_* มาจาก contract), scripts/eval/run_eval.py + scripts/datafeed/gen_golden_from_controls.py

## สถานะตอนนี้ (2026-09-19)
- Phase 1–4.5 ✅ | pytest: 936 passed, 3 skipped — `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` (python3.10 ใน venv ไม่มี pytest; vanna/chromadb import ได้เฉพาะ python3.10)
- config.db จริง: workspace `default` (revenue, expense, transfer price, pl_costtype — legacy) + `nt-report` (feed_revenue 2.3.0, feed_expense 1.2.0, feed_sales 1.3.0, feed_ebt 1.4.0 — file source);
  two_pass_enabled=true, rag_enabled=false, intent_state_enabled=false; **ยังไม่ได้รัน migration ของ Phase 4.5 บน config.db/app.db จริง** (ถามเจ้าของก่อนรัน — job retention รอบแรกจะล้างผลลัพธ์เก่า ~1,285 แถว)
- งวดข้อมูลไม่เท่ากัน: revenue/expense 202608, sales/ebt 202607 (ตรวจใหม่ด้วย GET /admin/sources/{name}/status — NT-Report publish build ใหม่เอง)
- eval ล่าสุด: revenue 14/14, expense 12/12, sales 12/12, ebt 35/36 (P50 5.3–6.7 s ต่อคำถาม = LLM 2–3 call)
- คำถามหนึ่งข้อ = context เดียว = source เดียว = policy เดียว ตลอด pipeline ตอนนี้ (router เลือก context เดียวจาก keyword; ไม่มี orchestrator)

## คำสั่งที่ใช้บ่อย
- ทดลองกับสำเนา: CONFIG_DB_URL=sqlite:///<copy> DATABASE_URL=sqlite:///<copy> DATA_SOURCE_CACHE_DIR=<scratch> ... (ห้ามทดลองบน config.db / app.db จริงโดยไม่ backup ลง scratchpad; สำเนาต้องรัน scripts/migrate_data_sources.py + scripts/migrate_workspaces.py ก่อน)
- eval: venv/bin/python3.14 -m scripts.eval.run_eval --context feed_<d> (LLM จริง ~2 นาที/12 ข้อ — รันเท่าที่จำเป็น; ทดสอบ prompt ใหม่ต้อง clear_query_cache())
- ลงทะเบียน source: python -m scripts.datafeed.register_file_source --domain <d> --source /Users/seal/Documents/GitHub/NT-Report/DataFeed/dist

## งานตามลำดับ (commit เป็นก้อนต่อข้อ, วัดจริงก่อน/หลัง)
0. baseline pytest; backup config.db + app.db ลง scratchpad
1. **สำรวจก่อนออกแบบ (ห้ามข้าม):**
   a. คำถามข้ามโดเมนที่ผู้ใช้ถามจริงมีแบบไหน — ดู chat_history / trending_queries / unmatched (อ่านอย่างเดียว) + dashboard ของ NT-Report (/Users/seal/Documents/GitHub/NT-Report) ว่าหน้าไหนแสดงตัวเลขจากมากกว่าหนึ่งโดเมน
   b. แต่ละแบบตอบได้จาก **context ที่รวมมาแล้วจากต้นทาง** (ทางเลือก 1 ของแผน — เช่น feed_ebt = ยอดขาย − ค่าใช้จ่าย รายสายงาน/ศูนย์ต้นทุน) หรือ**ต้อง orchestrator** (ทางเลือก 2) — ไล่ contract ทุกโดเมน (/Users/seal/Documents/GitHub/NT-Report/DataFeed/contracts/<d>.yaml + dist/<d>/latest/SCHEMA.md, control_totals.csv) ว่า grain / key / นิยาม measure ตรงกันแค่ไหน
   c. วัด router ปัจจุบันกับคำถามข้ามโดเมน: เลือก context ไหน, ตอบอะไร, **เดาตัวเลขไหม** (= baseline ของ exit)
   → ตารางใน plan/archive/RESULT_P7_PHASE5.md: คำถาม / โดเมนที่เกี่ยว / ตอบจาก context เดียวได้ไหม / key ที่ใช้เทียบข้ามโดเมน / ตัวเลขอ้างอิงจาก dashboard
2. เสนอแผนย่อย + exit criteria + ชุดคำถาม 10 ข้อ (ร่าง) แล้ว **หยุดถามเจ้าของ** เรื่องที่ยังไม่ตัดสิน (ข้างล่าง); ส่วนที่ไม่ขึ้นกับคำตอบทำต่อได้
3. **ทางเลือก 1 ก่อน (ถูกที่สุด):** ให้ router เลือก context ที่รวมมาแล้วให้ถูก (keyword / instruction ของ context ผ่าน contract หรือ admin — ไม่ hardcode ใน code); ถ้าขาดตาราง/measure ที่ต้นทาง ให้เขียนข้อเสนอถึง NT-Report ใน plan/PROMPT_NT_REPORT_P7.md แทนการคำนวณเองฝั่ง AI
4. **ทางเลือก 2 Orchestrator** (เฉพาะแบบคำถามที่ข้อ 1 ชี้ว่าจำเป็น; หลัง feature flag default OFF ใน admin_config):
   - ตรวจว่าเป็นคำถามข้าม context แบบ deterministic เท่าที่ทำได้ (intent ของ Pass 1 เชื่อไม่ได้ทั้งสองทาง) → แตกเป็นคำถามย่อยต่อ context → รันแต่ละข้อผ่าน `QueryEngine.query` เดิม (ได้ scope / allowlist / pinned / policy / audit / cache ครบโดยไม่เขียนซ้ำ) → รวมคำตอบ
   - **ไม่ JOIN ข้าม source ใน SQL** (key ของแต่ละโดเมนไม่ตรงกัน); การคำนวณข้ามโดเมน (ส่วนต่าง, อัตราส่วน) ทำแบบ deterministic ใน code จากผลของคำถามย่อย ไม่ให้ LLM คิดเลข
   - คำตอบต้อง**แสดงที่มาของแต่ละตัวเลข**: context, SQL, `data_as_of` ของ source นั้น — งวดไม่เท่ากัน (202608 vs 202607) ต้องบอกผู้ใช้ ไม่เทียบข้ามงวดเงียบ ๆ
   - ข้อย่อยใดตอบไม่ได้ / ถูกปฏิเสธ → บอกว่าส่วนนั้นตอบไม่ได้ **ไม่เดาตัวเลข** และไม่ตอบส่วนที่เหลือราวกับครบ
5. Eval ข้ามโดเมน: golden 10 ข้อ + ตัวเลขอ้างอิง (ต่อยอด scripts/eval/run_eval.py — อย่าสร้าง harness ใหม่) — **Exit ของแผน: ถูก ≥ 8/10 เทียบ dashboard; ข้อที่ตอบไม่ได้ต้องบอกว่าไม่ได้**; eval รายโดเมนเดิม (14/12/12/35) ต้องไม่ลด; รายงาน P50/P95 ของคำถามข้ามโดเมนแยก
6. อัปเดต RESULT_P7_PHASE5.md, PLAN_7, ROADMAP, FIX_NOTES, docs (PORTAL_INTEGRATION ถ้า response เปลี่ยน, manual ที่เกี่ยว), docs/changelogs; CLAUDE.md + AGENTS.md (sync กัน, gitignored); แล้วหยุดถามก่อน Phase 6
   (ถ้า context ใกล้เต็มก่อนถึงข้อนี้ ให้หยุดแล้วเขียน prompt ส่งต่อ session ถัดไป)

## ข้อค้างที่รอเจ้าของตัดสิน (อย่าตัดสินเอง — ถามตอนข้อ 2)
- ชุดคำถามข้ามโดเมน 10 ข้อ + ตัวเลขอ้างอิง: ใครให้ (เจ้าของ / ดึงจาก dashboard ของ NT-Report เอง) และ dashboard หน้าไหนคือ "ความจริง"
- ขอบเขต: ทางเลือก 1 พอไหม หรือต้องมี orchestrator ใน phase นี้ (ขึ้นกับผลข้อ 1)
- ข้าม **workspace** ได้ไหม (เช่น revenue ของ `default` + feed_sales ของ `nt-report`) — ข้อเสนอ: ไม่ได้ (brain / สิทธิ / retention แยกต่อ workspace); key ที่ถูกจำกัด = เฉพาะ context ใน allowlist เสมอ
- `scope` ที่ context หนึ่งในชุดไม่ได้ประกาศ (เช่น org_code ที่ feed_sales ไม่มี): ปฏิเสธทั้งคำถาม (400 — ตรงกับ Phase 3 "ไม่ตอบแบบไม่มี scope") หรือตอบเฉพาะส่วนที่บังคับได้พร้อมบอก
- งวดของ source ไม่เท่ากัน: ตอบพร้อมคำเตือน / ปรับไปงวดร่วมล่าสุด / ปฏิเสธ
- ขั้นรวมคำตอบภายใต้ policy ที่ไม่ใช่ `full`: template อย่างเดียว (ข้อเสนอ) หรือปฏิเสธ orchestrator สำหรับ source นั้น
- เพดาน latency: คำถามข้าม 2 context ≈ 2 เท่าของ 6 s (รันขนานได้ แต่ LLM ของ gateway มี rate limit) — ยอมรับได้แค่ไหน; ช่องทางไหนเปิดก่อน (chat / `/api/v1/query` / telegram)
- ค้างจาก Phase 4.5 (ไม่บล็อก): `ai_response` หมดอายุตาม retention ไหม; audit เขียนไม่ได้ต้อง fail closed สำหรับ workspace การเงินไหม; migrate DB จริงเมื่อไร; Admin UI ของ workspaces / sources / policy / retention / audit / DSR; context ที่ไม่มีอยู่จริงของผู้เรียกที่ไม่ถูกจำกัดยังตกไป legacy DB; ออก key จริงให้ portal
- ⚖️ D4 (Matcha ใช้กับข้อมูลอ่อนไหวได้) และ §6.6 ข้อ 8 ยังรอ DPO — ไม่ใช่งานของ session นี้

## กติกา
- พฤติกรรมของคำถาม context เดียวต้องไม่เปลี่ยน (flag ปิด = เหมือนเดิมทุกอย่าง); test เดิมต้องไม่พัง; ทุกความสามารถใหม่ต้องมี test ที่ fail บน code เดิม
- **ความปลอดภัย — orchestrator คือ caller ใหม่ที่ถือผลลัพธ์ของหลาย source พร้อมกัน ซึ่งของเดิมไม่เคยมี:**
  - `request_llm_policy` / `request_scope` / `request_pinned` ถูกตั้งและ**รีเซ็ตใน `QueryEngine.query` แต่ละครั้ง** → provider call ใด ๆ ที่ orchestrator ทำเอง**นอก** query() (แตกคำถาม, รวมคำตอบ) จะรันโดย**ไม่มี policy = ไม่ถูกจำกัด** → ขั้นรวมต้องตั้ง `RequestPolicy` เอง = **policy ที่เข้มที่สุด**ของทุก source ที่เกี่ยว และ provider allowlist = **intersection** (ว่าง = ปฏิเสธ); ค่าจากผลลัพธ์ของ source ที่ ≠ `full` ห้ามเข้า prompt ของขั้นรวม (taint ของ Phase 4.5 เป็นต่อ request — ข้ามคำถามย่อยไม่ติดมา ต้องจัดการเอง)
  - ขั้นแตกคำถามเห็นได้แค่คำถาม + ชื่อ/คำอธิบายของ context ที่ผู้เรียก**มีสิทธิ์** — รายชื่อ context นอก allowlist ห้ามเข้า prompt; คำถามย่อยทุกข้อผ่าน canonical_context / check_context (นอกสิทธิ์ = 403 ทั้งคำถาม ไม่ตัดทิ้งเงียบ)
  - cache ของคำตอบรวม (ถ้ามี) ต้องผูกกับ scope + allowlist + build + policy ของ**ทุก** source และเคารพ `stores_results` ของทุก context; audit: คำถามย่อยได้แถวของตัวเองอยู่แล้ว — คำถามแม่ต้องมีแถวที่โยงถึงกัน
  - ห้ามผ่อน lock ของ DuckDB (read_only, allowed_paths, enable_external_access=false, lock_configuration, temp_directory=''); SQL จาก LLM ผ่าน check_select เสมอ; scope / allowlist / request_pinned / llm_data_policy ห้ามอ่อนลง
  - งานที่แตะ gate / scope / auth / policy ให้ขอ review อิสระ (agent แยก, อ่านอย่างเดียว) ก่อนปิดงาน — Phase 4 เจอ critical 1, Phase 4.5 เจอ critical 2 (RAG/golden ที่สร้างจาก control totals; CSV formula injection) — test แบบ sentinel ที่ขอบ HTTP ของ provider (tests/unit/test_llm_data_policy.py) ต้องครอบ orchestrator ด้วย: source A = `full`, source B = `schema_only` → ไม่มีค่าของ B ใน request ใดเลย
- fail closed: อ่าน policy / allowlist / scope ไม่ได้ = เข้มที่สุด / ปฏิเสธ
- ข้อควรรู้ที่เจอมาแล้ว:
  - intent ของ Pass 1 (โมเดลเล็ก) เชื่อไม่ได้ทั้งสองทาง → ของที่ต้องบังคับ ตรวจแบบ deterministic ไม่ใช่ prompt
  - ความหมายข้ามโดเมนไม่ตรงกัน: **ยอดขายใน feed_ebt (กลุ่ม 01.รายได้) ≠ รายได้ใน feed_revenue** (ฐานยอดขาย รวมบัตร prepaid); feed_sales `metric` = actual/target ห้ามรวม; feed_ebt คอลัมน์ไม่มี suffix = สะสม (YTD) ห้าม SUM ข้ามงวด, `*_month` = รายเดือน; ยอดรวมทางการอยู่ในตาราง total — orchestrator ที่ "รายได้ − ค่าใช้จ่าย" เองจาก feed_revenue + feed_expense จะ**ไม่เท่ากับ** EBT ทางการ
  - two-pass ฝัง history ลงในข้อความ prompt (build_history_context) — ตัวกรองที่ชั้น provider มองไม่เห็น; `intent_state` เก็บต่อ conversation อย่างเดียว
  - test ที่สร้าง provider จริงต้อง patch `_build_provider_kwargs` ให้เหลือ key ของ provider เดียว (เครื่องนี้มี ANTHROPIC_API_KEY จริง — เคยยิงออกไปแล้วครั้งหนึ่ง)
  - anyio TaskGroup ห่อ exception เป็น ExceptionGroup (endpoint ที่เปิด MCP session เอง) — refusal ต้องแกะก่อนตัดสิน status code (`_find_refusal` ใน query.py)
  - query cache 30 นาทีไม่รวมเวอร์ชัน code; request dedup 5 วินาทีต่อ user + คำถาม — คำถามย่อยที่ซ้ำกันในหน้าต่างนี้จะโดน "duplicate_request"
  - test ไม่ได้แยก CONFIG_DB_URL อัตโนมัติ — test ที่เขียน config/app DB ใช้ DB ชั่วคราวเสมอ; QueryEngine test ต้อง patch source_resolver (ไม่งั้นอ่าน config.db จริง); `stores_results` / `policy_for_table` อ่าน config จริงถ้าไม่ patch (อ่านอย่างเดียว)
  - app ห้าม import จาก scripts/; context ที่สร้างหลัง migration มี workspace_id NULL = 'default' ทุกจุด
  - DuckDB: LIKE → ILIKE, `/` เป็นทศนิยม, SELECT DISTINCT … LIMIT ไม่ deterministic; SourceUnavailable = กำลัง publish (ต้องไปถึงผู้ใช้ ห้ามส่งให้ LLM แก้ SQL)
  - tests/unit/test_vanna_documentation.py รันเดี่ยว ๆ error (pandas circular import บน py3.14) — full suite ผ่าน
  - ruff มี error เดิมใน deps.py, schema.py, vanna_service.py, analytics.py (E711/E712), query_engine.py (`import uuid`), value_verifier.py, extract_hierarchy.py, admin/__init__.py — ไม่ใช่ของเรา
  - CLAUDE.md / AGENTS.md ถูก gitignore (แก้ได้ ต้อง sync กัน แต่ commit ไม่ได้)
- commit เป็นก้อนต่อข้อ; ข้อความ commit ห้ามมีชื่อโมเดลหรือ emoji; ลงท้าย Co-Authored-By: Claude <noreply@anthropic.com>
- ถ้าเจอสิ่งที่ขัดกับแผน ให้หยุดและรายงานพร้อมทางเลือก ไม่ตัดสินใจเองเงียบ ๆ
- จบแต่ละข้อ/phase สรุป: ทำอะไร, ตัวเลข exit criteria, commit list, ข้อค้างที่ต้องให้ผมตัดสิน
```
