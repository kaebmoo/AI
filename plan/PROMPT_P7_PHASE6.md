ทำงานต่อ Plan 7 (Data Source as a Service) ใน repo /Users/seal/Documents/GitHub/AI — branch main
origin/main = 52c3ee8 (Phase 1–5 push แล้ว 2026-09-19); local นำอยู่แค่ commit ของ prompt นี้ — ตรวจด้วย `git status -sb` ก่อนเริ่ม; commit ใหม่ห้าม push จนกว่าจะสั่ง; ห้าม rebase / force-push
ถ้า main มี commit ใหม่จาก session อื่น ให้ทำต่อบนนั้น

## อ่านก่อน (บังคับ)
- plan/PLAN_7_DATA_SOURCE_SERVICE.md — หัวสถานะ, §2 เป้าหมายข้อ 4, §3 (ภาพสถาปัตยกรรม: ผู้เรียก → Auth → workspace → router → … ), §5 Phase 6, §6.2–6.3 (ห้าชั้นของสิทธิ; **v1 เชื่อ scope ใน body ได้เพราะ key อยู่ฝั่ง server ของผู้เรียกเท่านั้น**), §6.6 (llm_data_policy), §9 (Model D = MCP), §12 (D8)
- plan/PLAN_REMAINING_ITEMS.md REMAIN-8 (Plan 1B-C: MCP SSE + Auth — ของเดิมที่ deferred), plan/archive/ ของ Plan 1B ถ้ามี
- plan/archive/RESULT_P7_PHASE5.md (ทั้งไฟล์ — โดยเฉพาะ §4 โครงของ orchestrator, §6 review, §9 ข้อค้าง), RESULT_P7_PHASE45.md §1B แถว S13 (Telegram = ค่าจริงออกไปบุคคลที่สามนอก `llm_data_policy`) และ §4, RESULT_P7_PHASE4.md (key ผูก workspace, `enforce_key_surface`)
- plan/FIX_NOTES.md หัวข้อ "จาก Plan 7 Phase 5", "จาก Plan 7 Phase 4.5", "จาก Plan 7 Phase 4"
- docs/PORTAL_INTEGRATION.md (รูป request/response ของ `/api/v1/query` รวม `parts` / `computed`), docs/DEPLOYMENT_SECURITY.md, docs/manuals/manual_api_keys.md, mcp_servers/README.md
- code: mcp_servers/*.py (**MCP ภายใน 4 ตัว — stdio, ใช้โดย pipeline เอง**: nt_query มี `execute_query` รับ SQL ดิบ, nt_metadata, nt_validation, nt_admin), app/services/mcp_client.py,
  app/api/v1/query.py (ทางเข้าที่ครบที่สุดตอนนี้: allowed_contexts → `multi_context.ask` → refusal 400/403 → `_multi_response`), app/services/multi_context.py, app/services/query_engine.py (`query()` ตั้ง/รีเซ็ต ContextVar 3 ตัว),
  app/api/deps.py (`get_current_user`, `api_key_header`, `enforce_key_surface` — key ที่ถูกจำกัดใช้ได้เฉพาะ `/api/v1/query*`), app/services/api_key_service.py (validate, rate limit รายวันใน DB + รายนาทีใน Redis, `api_key_usage`),
  app/services/workspaces.py (`allowed_contexts`, `is_restricted`), app/services/query_audit.py (`channel`, `request_group`), app/main.py (lifespan เปิด MCP client ภายใน, router, middleware), requirements.txt (`mcp>=1.26.0`)

## สถานะตอนนี้ (2026-09-19)
- Phase 1–5 ✅ | pytest: **997 passed, 3 skipped** — `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` (python3.10 ใน venv ไม่มี pytest; vanna/chromadb import ได้เฉพาะ python3.10)
- ช่องทางที่มี: web chat (session), `POST /api/v1/query` (API key — ช่องทางเดียวที่รู้จัก workspace/allowlist/scope/multi-context), telegram; MCP = **ภายในเท่านั้น** (stdio subprocess ของ API)
- config.db จริง: workspace `default` (legacy 4 context) + `nt-report` (feed_revenue 2.3.0, feed_expense 1.2.0, feed_sales 1.3.0, feed_ebt 1.4.0); multi-context **ยังปิดทุก workspace**; **ยังไม่ได้รัน migration ของ Phase 4.5 บน DB จริง**; ยังไม่ได้ออก key จริงให้ portal
- งวดข้อมูล: revenue / expense / sales 202608, ebt 202607
- eval ล่าสุด: revenue 14/14, expense 12/12, sales 12/12, ebt 35/36; ข้ามโดเมน 8–9/10 (`run_eval --cross-domain scripts/eval/cross_domain_golden.json`, P50 ~8–9 s)

## คำสั่งที่ใช้บ่อย
- ทดลองกับสำเนา: CONFIG_DB_URL=sqlite:///<copy> DATABASE_URL=sqlite:///<copy> DATA_SOURCE_CACHE_DIR=<scratch> … (ห้ามทดลองบน config.db / app.db จริงโดยไม่ backup ลง scratchpad; สำเนาต้องรัน scripts/migrate_data_sources.py + scripts/migrate_workspaces.py ก่อน)
- eval: venv/bin/python3.14 -m scripts.eval.run_eval --context feed_<d> | --cross-domain scripts/eval/cross_domain_golden.json (LLM จริง — รันเท่าที่จำเป็น)
- เปิด multi-context บนสำเนา: `AdminConfigService().set_config('multi_context_workspaces', '["nt-report"]', …)` หรือ `PUT /admin/workspaces/{id}/multi-context`

## งานตามลำดับ (commit เป็นก้อนต่อข้อ, วัดจริงก่อน/หลัง)
0. baseline pytest; backup config.db + app.db ลง scratchpad
1. **สำรวจก่อนออกแบบ (ห้ามข้าม):**
   a. MCP ภายใน 4 ตัวเปิดอะไรไว้บ้าง (รายชื่อ tool + สิ่งที่แต่ละ tool อ่าน/เขียน) — ตัวไหน**ห้าม**ออกนอก process เด็ดขาด (SQL ดิบ, sample values, admin write) → ตารางใน plan/archive/RESULT_P7_PHASE6.md
   b. `mcp` SDK เวอร์ชันที่ติดตั้งจริงรองรับ transport อะไร (SSE แบบเดิม / Streamable HTTP), mount ใน FastAPI (ASGI) ได้ไหม, ส่ง header ของ request (API key) ถึง tool handler อย่างไร, client ที่เป็นเป้าหมาย (Claude Desktop / Claude Code / อื่น ๆ) ต่อ transport ไหนได้และส่ง header เองได้ไหม — ตรวจกับของจริงในเครื่อง อย่าเดาจากความจำ
   c. เส้นทาง auth ปัจจุบันของ API key ครบอะไรบ้างที่ MCP ต้องได้เท่ากัน: validate, rate limit (วัน/นาที), `api_key_usage`, `enforce_key_surface`, `allowed_contexts`, audit (`channel`)
   d. ใครคือผู้ใช้ MCP รายแรกจริง ๆ (ถามเจ้าของ) — ถ้ายังไม่มี ให้เสนอขอบเขตเล็กที่สุดที่พิสูจน์ช่องทางได้
2. เสนอแผนย่อย + exit criteria แล้ว **หยุดถามเจ้าของ** เรื่องที่ยังไม่ตัดสิน (ข้างล่าง); ส่วนที่ไม่ขึ้นกับคำตอบทำต่อได้
3. **MCP ภายนอก = facade บาง ๆ บนทางเข้าเดิม ไม่ใช่การเปิด MCP ภายในออกไป:** tool ชุดเล็ก (ข้อเสนอ: `ask(question, context?, scope?)`, `list_contexts()`, `source_status(context)`) ที่เรียก `multi_context.ask` / `QueryEngine.query` เส้นเดียวกับ `/api/v1/query` → ได้ allowlist / scope / pinned / llm policy / audit / cache / multi-context ครบโดยไม่เขียนซ้ำ; refusal (400/403) ต้องกลับไปเป็น error ของ tool ที่อ่านออก ไม่ใช่คำตอบเปล่า
4. Auth + ขอบเขต: API key เดิม (header) → user + workspace + allowlist; rate limit + usage นับรวมกับ REST; `enforce_key_surface` รู้จัก path ของ MCP; audit `channel='mcp'` (+ ชื่อ client ถ้า client ส่งมา); ไม่มี key / key ผิด = ปฏิเสธก่อนเปิด session
5. ทดสอบปลายทางจริง: MCP client ของ SDK ใน test (in-process) + ต่อจาก client จริงอย่างน้อยหนึ่งตัวบนเครื่องนี้; วัด latency เทียบ `/api/v1/query`
6. (ตัวเลือก — ทำเมื่อเจ้าของยืนยันว่ามี client ที่ 2) embeddable chat widget; ไม่งั้นบันทึกเป็น "ไม่ทำ" พร้อมเหตุผล
7. อัปเดต RESULT_P7_PHASE6.md, PLAN_7, ROADMAP (ปิด Plan 1B-C / REMAIN-8), FIX_NOTES, docs (คู่มือเชื่อมต่อ MCP สำหรับผู้ใช้ + DEPLOYMENT_SECURITY + manual_api_keys), docs/changelogs; CLAUDE.md + AGENTS.md (sync กัน, gitignored); แล้วหยุดถามก่อน Phase 7
   (ถ้า context ใกล้เต็มก่อนถึงข้อนี้ ให้หยุดแล้วเขียน prompt ส่งต่อ session ถัดไป)

## ข้อค้างที่รอเจ้าของตัดสิน (อย่าตัดสินเอง — ถามตอนข้อ 2)
- **ผู้ใช้รายแรกของ MCP คือใคร / client ตัวไหน** — กำหนด transport และวิธีส่ง key
- **Transport:** SSE (ตามชื่อในแผน / Plan 1B-C) หรือ Streamable HTTP (ขึ้นกับผลข้อ 1b) หรือทั้งสอง; **รันที่ไหน:** mount ใน FastAPI app เดิม (process เดียว, ใช้ MCP client ภายใน + cache ร่วม) หรือ process/port แยก
- **tool ที่เปิด:** ข้อเสนอ = `ask` / `list_contexts` / `source_status` เท่านั้น — **ไม่เปิด SQL ดิบ, sample values, admin tools**; ต้องการ tool แบบ "ขอ SQL + แถวข้อมูล" (`include_sql` / `include_data`) ไหม
- ⚠️ **ความน่าเชื่อถือของ `scope` เปลี่ยนไป:** §6.3 v1 เชื่อ scope ใน body เพราะ key อยู่ฝั่ง server ของผู้เรียก — ใน MCP **ผู้เรียกคือ LLM ของ client** (argument ของ tool ถูกโมเดลเลือกเอง และโดน prompt injection ได้) และ key อยู่ในเครื่องผู้ใช้ → scope ที่ส่งมาแคบลงได้แต่**บังคับให้แคบไม่ได้**; ทางเลือก: (ก) key ของ MCP = สิทธิระดับ workspace/allowlist เท่านั้น ไม่มีสิทธิระดับแถว (ข้อเสนอสำหรับ phase นี้) (ข) เพิ่ม "scope เพดานผูกกับ key" (สิทธิที่ใช้จริง = เพดาน ∩ ที่ส่งมา) (ค) entitlement token v2 (D7) — ใหญ่เกิน phase นี้
- ⚠️ **คำตอบที่คืนให้ MCP client เข้า LLM ของ client โดยสภาพ** (ตัวเลข/แถวผลลัพธ์ออกไปหาโมเดลที่เราไม่ได้คุม) — `llm_data_policy` คุมเฉพาะ provider ของเรา: source ที่ ≠ `full` จะ (ก) ปฏิเสธช่องทาง MCP (ข้อเสนอ — fail closed) (ข) คืนเฉพาะข้อความ template ไม่มีแถว (ค) ถือว่าเจ้าของ key ยอมรับเอง — เกี่ยวกับ D4 / DPO
- history / follow-up ผ่าน MCP: stateless เหมือน `/api/v1/query` (ข้อเสนอ) หรือมี conversation
- ค้างจาก Phase 5 (ไม่บล็อก): เปิด multi-context กับ `nt-report` จริงเมื่อไร (แนะนำหลัง NT-Report รับข้อเสนอ "ebt ไม่ใช่ทั้งบริษัท" ใน plan/PROMPT_NT_REPORT_P7.md); chat / telegram ข้าม context (ต้องออกแบบ follow-up ก่อน); ทำความสะอาด keyword ของ workspace `default`; fixture แยก config DB ของ test (full pytest ขยับ `last_brain_relevant_change_at` ใน config.db จริง)
- ค้างจาก Phase 4.5 (ไม่บล็อก): migrate DB จริง; `ai_response` หมดอายุตาม retention ไหม; audit เขียนไม่ได้ต้อง fail closed ไหม; Admin UI ของ workspaces / sources / policy / retention / audit / DSR / multi-context; ออก key จริงให้ portal
- ⚖️ D4 และ §6.6 ข้อ 8 ยังรอ DPO — ไม่ใช่งานของ session นี้

## กติกา
- พฤติกรรมของช่องทางเดิม (chat, `/api/v1/query`, telegram, MCP ภายในแบบ stdio) ต้องไม่เปลี่ยน; test เดิมต้องไม่พัง; ทุกความสามารถใหม่ต้องมี test ที่ fail บน code เดิม
- **ความปลอดภัย — MCP ภายนอกคือผู้เรียกแบบใหม่: อยู่นอกเครือข่าย, ถือ key เอง, และเป็น LLM:**
  - ห้ามเปิด tool ของ MCP ภายในออกไปตรง ๆ: `execute_query` = SQL ดิบที่ข้าม scope / allowlist / `request_pinned` / `check_select` ของ file source / audit; `get_sample_values` / `get_table_stats` / `get_column_info` = ค่าจริงนอก `llm_data_policy`; nt_admin = เขียน config — ทุกอย่างที่ออกนอก process ต้องผ่าน `QueryEngine.query` (หรือ `multi_context.ask`) เท่านั้น
  - ทุก tool call ต้องผ่าน auth ของ key **ต่อ call** (ไม่ใช่แค่ตอนเปิด session — key ถูก revoke / workspace ถูกปิดระหว่าง session ต้องมีผลทันที) + rate limit เดียวกับ REST; session ที่ไม่มี key ห้ามเห็นแม้แต่รายชื่อ tool/context
  - `list_contexts` / คำอธิบาย tool / ข้อความ error ห้ามมีชื่อ context นอกสิทธิ์ของ key; context นอกสิทธิ์ = error (เทียบเท่า 403) ไม่ตัดทิ้งเงียบ ไม่ re-route
  - ContextVar (`request_scope` / `request_pinned` / `request_llm_policy`) ถูกตั้ง/รีเซ็ตใน `QueryEngine.query` — ตรวจว่า transport ของ MCP (task ที่อยู่ยาวต่อ session, anyio TaskGroup) ไม่ทำให้ค่าของ call หนึ่งค้างไปถึงอีก call / อีก session; ตรวจด้วย test ที่ยิงสอง key พร้อมกัน
  - ข้อความจาก client (ชื่อ client, argument) คือ**ข้อมูลที่ไม่น่าเชื่อถือ** — ลง audit ได้ แต่ห้ามใช้ตัดสินสิทธิ; คำถามจาก MCP เข้า prompt เหมือนคำถามทั่วไป (ไม่มีสิทธิพิเศษ)
  - ห้ามผ่อน lock ของ DuckDB, gate `check_select`, scope / allowlist / `request_pinned` / `llm_data_policy`; CORS / origin / DNS-rebinding ของ endpoint ใหม่ต้องตั้งให้ชัด (ช่องทางเดิมไม่เปิด CORS)
  - งานที่แตะ auth / ขอบเขตของ key ให้ขอ review อิสระ (agent แยก, อ่านอย่างเดียว) ก่อนปิดงาน — Phase 3 เจอ high 1, Phase 4 critical 1, Phase 4.5 critical 2, Phase 5 medium 3
- fail closed: อ่าน key / allowlist / policy ไม่ได้ = ปฏิเสธ
- ข้อควรรู้ที่เจอมาแล้ว:
  - anyio TaskGroup ห่อ exception เป็น ExceptionGroup — refusal ต้องแกะก่อนตัดสิน (`_find_refusal` ใน query.py); MCP SDK ใช้ anyio ทั้งตัว
  - provider call ใด ๆ ที่ทำนอก `QueryEngine.query` รันโดย**ไม่มี policy** เว้นแต่ตั้ง `RequestPolicy` เอง (มีที่เดียวตอนนี้: `multi_context._split`) — facade ของ MCP ไม่ควรมี provider call ของตัวเองเลย
  - request dedup 5 วินาทีต่อ user + คำถาม; query cache 30 นาทีไม่รวมเวอร์ชัน code (ทดสอบ prompt ใหม่ต้อง `clear_query_cache()`)
  - test ที่สร้าง provider จริงต้อง patch `_build_provider_kwargs` ให้เหลือ key ของ provider เดียว (เครื่องนี้มี ANTHROPIC_API_KEY จริง)
  - test ไม่ได้แยก CONFIG_DB_URL อัตโนมัติ — test ที่เขียน config/app DB ใช้ DB ชั่วคราวเสมอ; QueryEngine test ต้อง patch source_resolver; full pytest ขยับ `admin_config.last_brain_relevant_change_at` ใน config.db จริง (ของเดิม — FIX_NOTES Phase 5)
  - `PUT /admin/config/settings/{key}` รับเฉพาะตัวเลขใน allowlist — config แบบข้อความต้องมี endpoint ของตัวเอง
  - app ห้าม import จาก scripts/; context ที่สร้างหลัง migration มี workspace_id NULL = 'default' ทุกจุด
  - การนับ keyword ซ้อนของ router (`ค่า` + `ค่าใช้จ่าย` + `จ่าย`) **ห้ามแก้** — วัดแล้วค้ำ routing ของ `default` อยู่ (RESULT_P7_PHASE5 ข้อ 3)
  - tests/unit/test_vanna_documentation.py รันเดี่ยว ๆ error (pandas circular import บน py3.14) — full suite ผ่าน
  - ruff มี error เดิมใน deps.py, schema.py, vanna_service.py, analytics.py (E711/E712), query_engine.py (`import uuid`), value_verifier.py, extract_hierarchy.py, admin/__init__.py — ไม่ใช่ของเรา
  - CLAUDE.md / AGENTS.md ถูก gitignore (แก้ได้ ต้อง sync กัน แต่ commit ไม่ได้)
- commit เป็นก้อนต่อข้อ; ข้อความ commit ห้ามมีชื่อโมเดลหรือ emoji; ลงท้าย Co-Authored-By: Claude <noreply@anthropic.com>
- ถ้าเจอสิ่งที่ขัดกับแผน ให้หยุดและรายงานพร้อมทางเลือก ไม่ตัดสินใจเองเงียบ ๆ
- จบแต่ละข้อ/phase สรุป: ทำอะไร, ตัวเลข exit criteria, commit list, ข้อค้างที่ต้องให้ผมตัดสิน
