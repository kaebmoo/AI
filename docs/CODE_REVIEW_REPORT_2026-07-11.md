# รายงานการแก้ไขตาม PLAN_FIX_MASTER — สำหรับ Code Review

**วันที่ execute:** 2026-07-11
**ผู้ execute:** Claude Code (ตาม `plan/PLAN_FIX_MASTER.md` 2026-07-04)
**ผลรวม:** 12 แผน execute ครบตามลำดับ Wave — **531+ tests ผ่าน (เพิ่มใหม่ ~100 tests), 0 fail**
**Commits:** 9 commits ใน repo AI + 1 commit ใน repo NT-Report (1 แผน = อย่างน้อย 1 commit ตามกฎ)

---

## สรุป commit ต่อแผน

| Wave | แผน | Commit | สาระ |
|------|------|--------|------|
| 0 | F3-A CI | `566e5bd` | GitHub Actions: ruff critical + pytest |
| 1 | F1 Correctness | `24071cd` | cache×history, truncation warning, provider default, prompt date |
| 1 | F2 Hygiene/Leaks | `ca9dd39` | session leak, SSE cancel, dedup release, utcnow, claude mcp mode |
| 2 | F4 SQL Hardening | `9b0daff` | read-only DB, fetchmany row cap, single validator, rate limit |
| 2 | F5 Telegram | `d993d24` | webhook lifecycle (B5), /admin explicit (B6), polling hardening |
| 3 | F3-B Eval | (รวมใน F9/F10 commits) | `scripts/eval/run_eval.py` + baseline |
| 3 | F7 Token/Observability | `ee158b8` | TokenUsage จริง (B9), query_trace JSON 1 บรรทัด |
| 4 | F6 Reports/Export | `c74002f` | `/api/v1/reports` + xlsx + Celery + cleanup |
| 4 | F8 Structured Output | `8489503` | generate_structured 3 providers + intent schema |
| 5 | F9 Latency A-D | `546c15d` | template answers, parallel prep, intent state, escalation |
| 5 | F10 DataFeed | `2150fd8` | import 255k แถว + docs + golden + baseline (values 14/14, ดู round 2) |
| 6 | F11 Dashboard Embed | `2150fd8` (AI) + NT-Report `c340d70` | portal fields + PB hook + viewer panel |

---

## รายละเอียดต่อแผน (จุดที่ reviewer ควรดู)

### F3-A — CI (`566e5bd`)
- `.github/workflows/ci.yml` — ruff เฉพาะ error ร้ายแรง (E9,F63,F7,F82) + pytest; env มีแค่ `SECRET_KEY`+`ENVIRONMENT`
- ยืนยัน local: suite ผ่านด้วย env สะอาด (`env -i`) — ไม่มี test พึ่ง API key จริง
- **ค้าง:** ยังไม่ได้ push → ยังไม่เห็น CI เขียวบน GitHub จริง + PR ทดสอบ syntax error

### F1 — Correctness (`24071cd`) — accuracy ต่อ user
- **F1.1 (B1):** query cache เป็น first-turn only (`use_cache = not history`) — กัน follow-up ข้าม conversation ปนกัน; cache HIT คืน `dataclasses.replace` copy (เดิม mutate object ใน cache)
  - Reviewer: `app/services/query_engine.py` — shallow copy ยอมรับได้เพราะไม่มีที่ไหน mutate `query_result` หลังคืนค่า (ตรวจ chat.py แล้ว)
- **F1.2 (B2):** hybrid mode อ่าน flag `truncated` จาก dict payload (เดิมเช็ค list ที่แทบไม่เคยจริง) + เคลียร์ pending warning ต่อ attempt/request — `app/services/ai/hybrid_flow.py`
- **F1.3 (B3):** `ChatRequest.provider = None` (เดิม `"gemini"` ทับ admin config) — ตรวจ frontend แล้ว: ModelSelector auto-select default จาก API เสมอ ปลอดภัย
- **F1.4:** วันที่เข้า cache key ของ system prompt → rebuild รายวัน
- Tests: `test_query_cache.py`, `test_hybrid_limit_warning.py`, `test_provider_default_and_prompt_date.py`

### F2 — Leaks/Robustness (`ca9dd39`)
- **F2.1 (B4):** `deps.get_admin_config_service` (yield+close) inject เข้า chat//stream/query; `QueryEngine` track ownership + `close()`; telegram dispatcher ปิดใน finally
  - **จุดที่ reviewer ควรรู้:** `admin/config.py, providers.py, analytics.py, vanna_docs.py, admin_agent.py` ยังสร้าง `AdminConfigService()` แบบเดิม — นอกขอบเขต B4 จดใน FIX_NOTES
- **F2.3:** dedup แบบ mark/release — refactor `query()` แยก `_execute_query()` เพื่อ wrap try/except (แตะ signature ภายในเท่านั้น)
- **F2.4:** SSE drain queue + `finally: query_task.cancel()` เมื่อ client หลุด (พึ่ง F2.2 แก้ bare except ใน mcp_client ที่กลืน CancelledError)
- **F2.6 (B8):** claude mcp mode — batch parallel tool_use เป็น assistant msg เดียว + tool_results เป็น user msg เดียว; ลบ `top_p` (Claude 4.5+ reject คู่ temperature)
- **F2.7:** `datetime.utcnow` → `app/core/time_utils.utcnow()` (naive UTC — semantics เดิม) ~90 จุดทั้ง repo แบบ mechanical; pydantic v1 dead validator ลบจาก config.py; `_instances` dead code ลบ; vanna print→logger
  - Reviewer: การ replace เป็น semantics-preserving by construction แต่ควร spot-check `app/models/*` (column defaults) และ `api_key_service.py`

### F4 — SQL Hardening (`9b0daff`) — security
- **F4.1:** MCP servers เปิด SQLite `mode=ro` ที่ระดับ connection (พิสูจน์: INSERT ผ่าน `validate_first=False` → "attempt to write a readonly database")
  - **⚠️ Decision ที่ต้องการเจ้าของโปรเจกต์:** `business_engine` ฝั่ง app **ไม่ได้ทำ RO** เพราะ `view_manager.py` เขียน CREATE/DROP VIEW ลง business DB (admin feature) — ดู FIX_NOTES
- **F4.2 (B7):** เลิก append `LIMIT` string → `cursor.fetchmany(max_rows)` (MSSQL-safe, subquery LIMIT ไม่หลุด cap); PG wrap subquery กัน client memory blowup
- **F4.3:** `validate_sql` เหลือแหล่งเดียว (`validation_service.py`) — MCP delegate, import chain ตรวจแล้ว ~0.07s
- **F4.4:** per-minute rate limit ผ่าน Redis fixed-window, fail-open + warning ครั้งเดียว — `docs/DEPLOYMENT_SECURITY.md`

### F5 — Telegram (`d993d24`)
- **F5.1 (B5):** webhook mode initialize/start PTB app จาก main lifespan (sub-app startup ไม่เคยรัน) + auto `set_webhook`; shutdown ตาม PTB 22 order ใช้ `.running` public
- **F5.2:** polling `delete_webhook` ก่อน (กัน 409) + เก็บ task ref
- **F5.3 (B6):** ลบ `_ADMIN_PATTERNS` regex (จับ "เพิ่มขึ้น/ติดลบ" ผิด) → `/admin <คำสั่ง>` explicit + role check
- **F5.4:** `_guess_chart_type` อ่าน visualization จาก explanation dict (attribute `qr.visualization` ไม่เคยมีจริง — ยืนยันกับ `QueryResult` แล้ว)
- **ค้าง manual:** webhook E2E ต้อง bot token + tunnel จริง (FIX_NOTES)

### F3-B — Eval Harness
- `scripts/eval/run_eval.py` — execution-match (เทียบ multiset ของ value-tuples, float tolerance 1e-6, ปิด query cache ต่อข้อ, สถานะ `golden_broken` แยก), CLI `--provider/--context/--limit/--compare`, timeout 180s/ข้อ (เพิ่มหลังพบ hang จริง)
- **Baseline (รอบแรก — value-based เกณฑ์หลวม):** ทั้งชุด 19/51 = 37.3% (golden เก่า 12 ข้อ `golden_broken` — data drift; admin ควร review); subset ใหม่ `feed_revenue` = 13/14 = 92.9% — **ตัวเลขนี้ถูกแทนที่ด้วยเกณฑ์ strict หลัง review P1-4 (ดู round 2)**; committed `BASELINE.json` เป็นเวอร์ชัน strict แล้ว
- **บทเรียนจากการรันจริง:** full run แรก hang ที่ข้อ 22 (LLM call ค้าง >30 นาที ไม่ตาย) → เพิ่ม `asyncio.wait_for` ต่อข้อ

### F7 — Token/Observability (`ee158b8`)
- **B9:** `TokenUsage` + `provider.last_usage` ทุก API call (Claude รวม cache fields, Gemini `usage_metadata`, Matcha tolerate usage หาย); hardcode 500 ถูกลบ; `QueryResult.usage_breakdown` per-stage
  - Reviewer: `last_usage` ปลอดภัยเพราะ provider สร้างใหม่ต่อ request + call เป็น sequential — docstring กำกับที่ base class
- **F7.3:** `query_trace {json}` 1 บรรทัด/request จาก QueryEngine (cache hit ก็ trace) — request_id จาก middleware contextvar; ย้าย timing logs ย่อยเป็น debug
- พบ `cost_service.py` ไม่มี caller (dead module — FIX_NOTES)

### F6 — Reports/Export (`c74002f`)
- Export **รัน SQL ใหม่เสมอ**จาก `generated_sql` ผ่าน read-only connection — ไม่ใช้ session data ที่ truncate
- `report_exports` model + `report_service` (ownership+validation gate, cap 100k, xlsx temp-then-rename) + `/api/v1/reports` (10/hour, Celery→inline fallback) + cleanup job รายวัน + `docs/API_REPORTS.md`
- Reviewer: `_run_export_sql` แยก sqlite RO / non-sqlite (business_engine — MSSQL credential-level)

### F8 — Structured Output (`8489503`)
- `generate_structured` บน 3 providers: Claude forced tool_choice / Matcha json_schema→json_object auto-fallback (จำ capability ต่อ instance) / Gemini json mime + schema ใน prompt (เหตุผลใน FIX_NOTES)
- `extract_intent` structured-first + text fallback เดิม; `intent_source` ลง trace; แก้เลขข้อซ้ำ (4,5,5) ใน prompt เดิม
- **`TWO_PASS_ENABLED` ยัง OFF** — เปิดต้องเทียบ eval ก่อน (decision แยก)

### F9 — Agentic Latency A-D (`546c15d`) — flags ทั้งหมด default OFF
- A: `template_answer.py` — ตัวเลขไม่ผ่าน LLM เด็ดขาด; contract dict เดียวกับ explanation เดิม
- B (pure code): `load_execution_metadata` วิ่งขนานกับ SQL gen/validate/execute
- C: `intent_state.py` in-memory TTL (เหตุผล: zero migration — FIX_NOTES) + follow-up prompt แบบ "อัปเดต intent เดิม"
- D: escalation ladder — attempt 2 → strong tier, attempt 3 → tool-loop rescue (read-only เดิม), latency budget 45s
- **E ไม่ได้ทำ — decision-gated**; `plan/RESULT_F9.md` มี protocol การวัดก่อนเปิด flag ใด ๆ

### F10 — DataFeed (`2150fd8`) — รันกับข้อมูลจริงแล้ว
- 3 scripts domain-agnostic ใน `scripts/datafeed/`: import (4 integrity gates — ผิดชั้นเดียว rollback หมด), gen_docs (idempotent — รันซ้ำพิสูจน์แล้ว), gen_golden (deterministic periods)
- ผลจริง: 255,404 แถว/3.4s ผ่านทุก gate; **ค่าถูก 14/14 (value-based); strict exact-match 0/14 เพราะ alias ไม่ตรง golden**; YTD questions ใช้ `revenue_ytd` ทั้งคู่ (business rule เข้า knowledge จริง) — `plan/RESULT_F10.md`
- Reviewer: `import_datafeed.py::check_control_totals` คือการยืด reconcile gate ของ feed เข้ามาถึง DB ปลายทาง

### F11 — Dashboard Embed (AI `2150fd8` + NT-Report `c340d70`)
- AI: `/api/v1/query` รับ `pinned_filters`/`source` (v1 log-only ตามเกณฑ์ 0.5 วันของแผน) + `docs/PORTAL_INTEGRATION.md`
- NT-Report: `pb_hooks/assistant.pb.js` — **`canAccessReport` ก่อน request ออกเสมอ**, context map จาก env, error ภาษาไทยไม่ leak upstream, `writeAudit` ทุกคำถาม; `viewer.html` panel + provenance บังคับ
- ตรวจ `.gitignore` แล้ว (pb_hooks un-ignored) — ไฟล์ไม่หาย
- **ค้าง manual:** ออก API key จริง, E2E local PB, ตารางเทียบ 10 คำถาม → `RESULT_F11.md`

---

## รายการค้าง / ต้องการ decision จากเจ้าของโปรเจกต์

1. **F4.1:** จะทำ `business_engine` ฝั่ง app เป็น read-only ไหม? ต้องแยก write engine ให้ view_manager ก่อน (FIX_NOTES)
2. **Dead modules:** `database_adapter.py`, `business_db.py`, `cost_service.py` ไม่มี caller — ลบหรือ wire?
3. **Flags รอวัด/อนุมัติ:** `TWO_PASS_ENABLED`, F9 A/C/D flags (วัดตาม RESULT_F9 protocol), F9-E router (อนุมัติก่อน implement), PENDING_BGE_M3 (มี baseline แล้ว — พร้อมตัดสินใจ)
4. **Manual QA ค้าง:** Telegram webhook E2E, F11 E2E + RESULT_F11, F1 manual 3 ข้อผ่าน UI, F8 two-pass smoke
5. **AdminConfigService per-call ไม่ close** ในไฟล์ admin/* — ควรย้ายมาใช้ dependency ในรอบถัดไป
6. ยังไม่ได้ **push** — CI เขียวบน GitHub ยังไม่พิสูจน์

## ไฟล์ความรู้ประกอบ

- `plan/FIX_NOTES.md` — ทุก decision/ข้อค้นพบระหว่างทาง (ตามกฎห้ามแก้นอกขอบเขต)
- `plan/RESULT_F10.md`, `plan/RESULT_F9.md` — ผลวัด
- `plan/IMPLEMENTATION_STATUS.md` — behavior changes ทั้งหมด
- `docs/DEPLOYMENT_SECURITY.md`, `docs/API_REPORTS.md`, `docs/PORTAL_INTEGRATION.md`

---

## Review Fixes (รอบสอง — หลัง code review, commit `f70302e`)

ผลตรวจจาก reviewer: **Fix-then-ship** — แก้ P1×5 + P2×4 ครบแล้ว

| Finding | การแก้ | พิสูจน์ |
|---------|--------|---------|
| P1 CI clean checkout ล้ม | เพิ่ม `REDIS_URL` + `ALLOWED_EMAIL_DOMAINS` ใน ci.yml; `test_list_contexts` เลิกพึ่ง config.db local (self-contained) | รัน suite ใน git worktree สะอาด (ไม่มี .env/DB files) → 517 passed |
| P1 `/admin` ไม่ถูก register | `handle_admin` + `CommandHandler("admin")` ใน bot.py | test ระดับ Application (fake telegram.ext) assert wiring |
| P1 F9 flags เปิดไม่ได้จริง | เพิ่ม 5 keys ใน `get_feature_flags()` + `_get_float_config` validate budget | wiring test: ค่าจาก admin config → `query_hybrid` kwargs |
| P1 eval ผ่านทั้งที่ column ผิด | `exact_match` ต้อง column names ตรง (case-insensitive); ค่าตรง-ชื่อต่าง = `value_match` แยก metric (`accuracy_incl_value_match`) | `test_eval_match.py`; **BASELINE ถูก regenerate ด้วยเกณฑ์ใหม่** |
| P1 row-count gate bypass ได้ | dataset ที่ไม่มีใน `manifest.row_counts` = abort | test เพิ่ม; ตรวจ manifest จริงครอบ 15 datasets — re-import ไม่พัง |
| P2 rate limit per-IP | เปลี่ยนเป็น DB count ต่อ user (10/hr) → 429 | integration test 429 |
| P2 matcha tokens ไม่ robust | คืน `last_usage.total` หลัง normalize; รองรับ usage null / total-only | tests 2 กรณีใหม่ |
| P2 RO ตัดสินจาก extension | ตัดสินจาก URL scheme (sqlite/bare path = sqlite) | — |
| P2 cleanup ลบไฟล์กลางเขียน | temp อยู่ `exports/.tmp/` — orphan sweep กวาดเฉพาะ `exports/*.xlsx` | — |

**ผลรวมหลังแก้: 534 tests ผ่าน (เพิ่ม 18)** — clean-worktree CI simulation ผ่าน

---

## Review Round 2 (commit `54945b2`)

Reviewer ยืนยัน P1/P2 ทั้ง 9 ข้อแก้แล้ว (clean env 537 passed) — residual ที่แจ้งเพิ่มแก้ครบ:

| Finding | การแก้ |
|---------|--------|
| [P2] export quota race (count→insert ไม่ atomic) | insert-then-verify: ทุก request นับใหม่หลัง insert ของตัวเอง เกิน cap = ลบ reservation + 429 — over-run เป็นไปไม่ได้ (over-reject ที่ขอบยอมรับได้) |
| [P3] `enabled_features` นับ budget (float) เป็น feature | filter เฉพาะ `isinstance(bool)` |
| F9 flags ไม่มีใน Admin UI | เพิ่ม 4 switches + Latency Budget (InputNumber) ใน Settings.tsx, ขยาย `FeatureFlags` type, endpoint ใหม่ `PUT /admin/config/settings/{key}` (allowlist + validate บวก) — `tsc --noEmit` ผ่าน |

**Baseline ใหม่ (เกณฑ์ strict หลัง P1-4):** exact 3/51 = 5.9% / รวม value_match 18/51 = 35.3% — feed_revenue ค่าถูก 14/14 แต่ alias ไม่ตรง golden เลย (รายละเอียด `plan/RESULT_F10.md`) — ตัวเลขนี้คือ baseline ที่ซื่อสัตย์กว่าเดิมสำหรับตัดสินใจ F8/F9/BGE-M3

หมายเหตุ: ไฟล์ uncommitted ใน worktree (`.vscode/tasks.json`, `app/services/otp_service.py`, `frontend/app/(auth)/login.tsx`, `verify.tsx`) เป็น WIP ฝั่งเจ้าของโปรเจกต์ — ไม่ถูกแตะ/รวมใน commits ชุดนี้
