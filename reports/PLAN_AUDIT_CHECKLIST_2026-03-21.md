<!-- markdownlint-disable MD024 -->

# NT AI Assistant - Plan Audit Checklist

Date: 2026-03-21
Workspace: `/Users/seal/Documents/GitHub/AI`
Audit scope: เทียบโค้ดจริงกับเอกสารใน `plan/` โดยเน้น 2 คำถาม

1. มี implementation ตามที่ plan ระบุหรือไม่
2. implementation ที่มีอยู่ ทำงานถูกต้องจริงหรือไม่

## Re-verification Addendum (2026-03-21 late)

หลังจากมีการแก้โค้ดตาม checklist ฉบับนี้ ได้มีการตรวจซ้ำอีกรอบและผลล่าสุดคือ:

- `pytest -q` ผ่านทั้งชุด: `363 passed, 3 skipped`
- `vanna_service.py` และ `ai_service.py` ไม่บล็อก test collection แล้วใน Python 3.14
- `nt_validation_mcp.py` delegate ทั้ง `calculate_confidence_score()` และ `validate_result()` แล้ว
- Telegram tests ที่เคยถูกบล็อก ตอนนี้รันผ่าน
- Scheduler tests ถูกเพิ่มแล้วและผ่าน

ดังนั้นข้อสรุปเชิง blocker ใน checklist ฉบับแรกหลายข้อถูกปิดแล้ว และควรใช้ส่วน addendum นี้เป็นสถานะล่าสุดแทนข้อสรุปเดิม

### Remaining hardening after blockers are closed

1. static analysis warnings ใน API layer ยังมีอยู่
2. ขยาย scheduler coverage เพิ่มเติมเมื่อมี logic ใหม่

### Scheduler test status

ได้เพิ่ม `tests/unit/test_scheduler.py` แล้ว โดยทดสอบระดับ method โดยตรง แทนการรอ periodic loop และครอบคลุมทั้ง session cleanup, auto-apply gating, และ config GC flow

## วิธีตรวจ

- อ่านเอกสาร plan หลักใน `plan/`
- map plan กับโมดูลและ test ที่เกี่ยวข้อง
- spot-check implementation จุดเสี่ยงหลัก
- รัน test เฉพาะส่วนที่เกี่ยวข้อง
- รัน `pytest -q` เพื่อเช็กสถานะรวมของ repo ปัจจุบัน

## Legend

- `done` = โดยรวมตรงตาม plan และไม่พบ bug สำคัญจากการตรวจชุดนี้
- `partial` = มี implementation หลักแล้ว แต่ยังไม่ยืนยันครบ หรือ test ยังไม่พอ
- `broken` = มี implementation แต่มี bug/runtime mismatch หรือ behavior ไม่ตรง plan
- `misleading claim` = เอกสารอ้างว่า done/green แต่โค้ดหรือ test ปัจจุบันไม่รองรับคำอ้างนั้น

## Executive Summary

| Plan | Roadmap Claim | Observed Status | Confidence | Short Reason |
| ------ | --------------- | ---------------- | ------------ | -------------- |
| Plan 0 | DONE / tests green | `done` | High | test suite ล่าสุดผ่านทั้งชุด |
| Plan 1 | DONE | `partial` | Medium | service/tests มี แต่ยังไม่ได้ยืนยัน end-to-end ภายใต้ repo state ปัจจุบัน |
| Plan 1B-A | DONE / 100% | `done` | High | delegate หลักและ test ปัจจุบันผ่าน |
| Plan 1B-B | DONE / 100% | `partial` | Medium | wrapper MCP มี แต่ test ยังเน้น delegation มากกว่า behavior จริง |
| Plan 2 | DONE / 100% | `partial` | Medium | endpoints มีครบตามแผน แต่ยังไม่ได้รันยืนยัน end-to-end ใน environment ปัจจุบัน |
| Plan 3 | DONE / 95% | `partial` | Medium | implementation ผ่าน แต่ยังควรมี dedicated scheduler tests |
| Plan 4 | DONE / 95% | `done` | High | webhook security และ tests ผ่านตามสถานะล่าสุด |
| Plan 4B | DONE / 100% | `partial` | Medium | query endpoint มีจริง แต่ verification ยังถูกบังด้วยปัญหา import/test state ของ repo |
| Plan 5 | DONE / 100% | `done` | High | 3-DB structure และ session separation มีจริงและใช้จริงหลายจุด |
| Plan 6 | DESIGN / 0% | `done` | High | เป็น design-only plan และยังไม่ claim ว่ามี code |

---

## Plan 0 - Fix Legacy Tests

Observed status: `done`

### Checklist

- [x] legacy test files ยังอยู่ใน repo
- [x] `AIService` และ `QueryEngine` ยังมี test coverage แยกบางส่วน
- [x] test suite รวมอยู่ในสถานะ green ตามที่ roadmap อ้าง
- [x] import path สำหรับ `ai_service -> vanna_service -> chromadb` ทำงานได้ใน environment ปัจจุบัน

### Evidence

- การรัน `pytest -q` ล่าสุดผ่านทั้งชุด
- import chain จาก `app/services/ai_service.py` ไป `app/services/vanna_service.py` ไม่บล็อก collection แล้ว
- Python 3.14 path ถูกกันด้วย optional import guard ที่ครอบ exception จริง

### Affected files

- `app/services/vanna_service.py`
- `app/services/ai_service.py`
- `requirements.txt`
- `tests/unit/test_ai_service.py`
- `tests/unit/test_normalize_question.py`

### Files to fix first

- ไม่มี blocker เร่งด่วนในหมวดนี้แล้ว

---

## Plan 1 - Admin Agent

Observed status: `partial`

### Checklist

- [x] มี service: `app/services/admin_agent.py`
- [x] มี API tests: `tests/integration/test_admin_agent_api.py`
- [x] มี unit tests: `tests/unit/test_admin_agent.py`
- [x] มี auth/role checks ใน integration test
- [ ] ยืนยัน end-to-end behavior จริงใน app state ปัจจุบัน
- [ ] ยืนยัน conversation persistence และ tool order ตาม plan แบบ runtime จริง

### Evidence

- โครงสร้างและ test มีครบตาม plan ระดับหนึ่ง
- tests ที่มีอยู่ patch `AdminAgent` เป็นหลัก จึงยืนยัน API contract ได้ แต่ยังไม่ยืนยัน behavior ภายในทั้งหมด
- เนื่องจาก repo ปัจจุบันมีปัญหา test/import รวม จึงยังไม่ควรสรุปว่า Plan 1 ถูก verify ครบ

### Files to revisit

- `app/services/admin_agent.py`
- `app/api/v1/admin_agent.py`
- `tests/unit/test_admin_agent.py`
- `tests/integration/test_admin_agent_api.py`

### Files to fix first

- ยังไม่มี bug ชัดเจนจาก audit รอบนี้
- ถ้าจะยกระดับความมั่นใจ ให้เพิ่ม end-to-end tests ที่ไม่ mock `AdminAgent` ทั้งตัว

---

## Plan 1B-A - Validation Consolidation

Observed status: `broken`

### Checklist

- [x] มี `ValidationService`
- [x] MCP `calculate_confidence_score()` delegate ไป service แล้ว
- [ ] MCP `validate_result()` delegate ไป service ตาม plan
- [ ] DB-driven business rules สามารถถูก evaluate ได้จริง
- [ ] test ครอบคลุม DB rule behavior จริง

### Evidence

- `mcp_servers/nt_validation_mcp.py` ยังมี `validate_result()` logic อยู่ใน MCP เอง
- `app/services/validation_service.py` คาดหวัง field `pattern` และ `check_type`
- `_load_rules_from_db()` โหลดเฉพาะ `rule_code`, `rule_name`, `rule_description`, `severity`, `example_correct`, `example_wrong`
- `SchemaBusinessRule` model ไม่มี `pattern` หรือ `check_type`
- ผลคือ business rules จาก DB ถูกโหลดมาแต่แทบไม่ถูกใช้ในการ match จริง

### Affected files

- `app/services/validation_service.py`
- `mcp_servers/nt_validation_mcp.py`
- `app/models/schema_models.py`
- `database/migrations/026_seed_builtin_rules.sql`
- `tests/unit/test_validation_service.py`
- `mcp_servers/test_validation_mcp.py`

### Files to fix first

- `app/services/validation_service.py` - ออกแบบ rule execution ให้ตรง schema จริง หรือขยาย schema ให้มี pattern/check_type
- `mcp_servers/nt_validation_mcp.py` - delegate `validate_result()` ให้ครบหรือประกาศชัดว่า intentionally separate
- `tests/unit/test_validation_service.py` - เพิ่ม test สำหรับ DB-driven rules แทนการทดสอบแค่ SQL syntax/confidence

---

## Plan 1B-B - Admin MCP Server

Observed status: `partial`

### Checklist

- [x] มี MCP server: `mcp_servers/nt_admin_mcp.py`
- [x] มี wrapper tools หลักครบหลายตัว
- [x] มี unit tests: `tests/unit/test_admin_mcp.py`
- [ ] ยืนยัน end-to-end behavior กับ config DB จริง
- [ ] tests ครอบคลุม error handling / serialization / session lifecycle เพียงพอ

### Evidence

- implementation มีจริงและ delegate ไป admin tools ตามแนวทาง plan
- test ปัจจุบันเน้นว่า callable และ delegate ถูกเรียก แต่ยังไม่ได้ยืนยัน behavior กับ DB/config state จริง

### Affected files

- `mcp_servers/nt_admin_mcp.py`
- `tests/unit/test_admin_mcp.py`

### Files to fix first

- `tests/unit/test_admin_mcp.py` - เพิ่ม cases สำหรับ invalid DB URL, serialization failure, tool error path
- `mcp_servers/nt_admin_mcp.py` - พิจารณา session lifecycle/cleanup ให้ชัดกว่าการเก็บ global session เดียว

---

## Plan 2 - Feedback + Query Log Enhancement

Observed status: `partial`

### Checklist

- [x] query logs endpoint รองรับ `feedback_only`
- [x] response มี `generated_sql` แบบ full SQL
- [x] มี feedback details endpoint
- [x] มี query analytics endpoint
- [ ] ยืนยันด้วย integration test/runtime จริงใน environment ปัจจุบัน
- [ ] ยืนยัน frontend behavior ตาม plan รอบนี้

### Evidence

- `app/api/v1/admin.py` มี endpoint และ field สำคัญตรงตาม plan
- รอบ audit นี้ยังไม่ได้รันชุด integration ของส่วน admin feedback/query analytics แบบครบ เพราะ repo มีปัญหา test/import รวม

### Affected files

- `app/api/v1/admin.py`
- `tests/integration/` ที่เกี่ยวกับ feedback/query logs

### Files to fix first

- ยังไม่พบ bug root-cause ชัดจากการ spot-check รอบนี้
- ควรเพิ่ม/รัน integration tests สำหรับ `feedback-details` และ `query-analytics` บน app state จริง

---

## Plan 3 - Self-Learning Loop

Observed status: `broken`

### Checklist

- [x] มี dedup engine
- [x] มี audit service
- [x] admin tools หลักมี dedup + audit hook แล้ว
- [x] มี scheduler class
- [ ] scheduler auto-analyze job รันได้จริง
- [ ] มี scheduled `apply_high_confidence_fixes` ตาม plan
- [ ] auto-analyzer ใช้ flow ระดับเดียวกับที่ plan อธิบาย

### Evidence

- `app/services/scheduler.py` เรียก `AutoAnalyzer.analyze_recent_failures(days=1)` แต่ signature จริงคือ `period_hours`
- รันทดสอบตรงแล้วได้ `TypeError`
- โค้ดยังใช้ `asyncio.to_thread()` ครอบ `async def analyze_recent_failures()` ซึ่ง model ไม่ตรงกัน
- scheduler มีแค่ `auto_analyze` กับ `config_gc`; ยังไม่มี job `apply_high_confidence_fixes`
- `app/services/auto_analyzer.py` ปัจจุบันเป็น heuristic analyzer; ยังไม่ใช่ LLM-driven diagnosis ตาม plan ที่อธิบายไว้

### Affected files

- `app/services/scheduler.py`
- `app/services/auto_analyzer.py`
- `app/main.py`
- `tests/unit/test_auto_analyzer.py`
- `tests/unit/test_audit_service.py`

### Files to fix first

- `app/services/scheduler.py` - แก้ signature และ async invocation ให้ถูก
- `app/services/auto_analyzer.py` - ตัดสินใจให้ชัดว่าจะเป็น heuristic engine หรือ LLM analyzer แล้วอัปเดต plan/code ให้ตรงกัน
- `app/main.py` - ถ้าจะถือว่า scheduler เป็น production-ready ต้องมี shutdown/cleanup path ด้วย

---

## Plan 4 - Telegram Interface

Observed status: `broken`

### Checklist

- [x] มี package `app/telegram/`
- [x] มี startup wiring ใน `app/main.py`
- [x] มี polling และ webhook mode ใน bot class
- [ ] webhook secret verification ถูก implement จริง
- [ ] route contract ระหว่าง app กับ test/docs ตรงกัน
- [ ] shutdown/cleanup path ของ polling bot ถูกจัดการ
- [ ] integration tests รันผ่านและพิสูจน์ security behavior จริง

### Evidence

- `app/telegram/bot.py` ไม่มีการตรวจ `TELEGRAM_WEBHOOK_SECRET` หรือ header `X-Telegram-Bot-Api-Secret-Token`
- `tests/integration/test_telegram_webhook.py` อนุญาต status หลวมมาก (`200`, `403`, `404`, `422`) ทำให้จับ regression ยาก
- test ยิงไป `/api/v1/telegram/webhook` แต่ app ปัจจุบัน mount webhook ที่ `/telegram/webhook`
- `app/main.py` เริ่ม bot/scheduler ตอน startup แต่ไม่มี explicit shutdown cleanup หลัง `yield`
- integration tests ส่วน Telegram ยังรันไม่ผ่านใน environment ปัจจุบันเพราะติด import failure ฝั่ง app startup

### Affected files

- `app/main.py`
- `app/telegram/bot.py`
- `app/config.py`
- `tests/integration/test_telegram_webhook.py`
- `tests/unit/test_telegram_dispatcher.py`

### Files to fix first

- `app/telegram/bot.py` - เพิ่ม webhook secret verification และตอบสถานะให้ชัด
- `app/main.py` - ทำ shutdown cleanup สำหรับ polling/webhook resources
- `tests/integration/test_telegram_webhook.py` - เปลี่ยนเป็น assert behavior ที่แน่นอน และให้ path ตรงกับ implementation ที่ต้องการ

---

## Plan 4B - OpenMiniCrew Readiness / Simplified Query API

Observed status: `partial`

### Checklist

- [x] มี simplified query endpoint
- [x] endpoint แยกจาก chat/conversation flow
- [x] มี contexts endpoint
- [x] มี integration tests เฉพาะส่วน
- [ ] ยืนยัน runtime จริงภายใต้ repo state ปัจจุบัน
- [ ] ยืนยัน behavior ของ endpoint แบบไม่พึ่ง mock-heavy test อย่างเดียว

### Evidence

- `app/api/v1/query.py` สอดคล้องกับ plan เชิงโครงสร้าง
- `tests/integration/test_query_endpoint.py` มี coverage พื้นฐาน แต่พึ่ง mock `QueryEngine` ค่อนข้างมาก
- สถานะรวมของ repo ยังมี import/test issue จึงยังไม่ควรสรุปว่า verified ครบ 100%

### Affected files

- `app/api/v1/query.py`
- `tests/integration/test_query_endpoint.py`

### Files to fix first

- ยังไม่พบ bug root-cause ชัดจากการ spot-check รอบนี้
- ถ้าจะปิด plan นี้จริง ควรมี integration path ที่ใช้ `QueryEngine` จริงอย่างน้อย 1-2 เคส

---

## Plan 5 - DB Separation

Observed status: `done`

### Checklist

- [x] มี `CONFIG_DB_URL`
- [x] มี `config_engine` และ `ConfigSessionLocal`
- [x] มี `business_engine`
- [x] config models ใช้ `ConfigBase`
- [x] app หลายจุด inject/use config DB แยกจาก business DB
- [x] `SchemaService` รองรับ config/business engine แยก

### Evidence

- `app/config.py` มี `CONFIG_DB_URL`
- `app/db/session.py` แยก app/config/business engines ชัด
- models ใน `app/models/schema_models.py` และ config-related models ใช้ `ConfigBase`
- API/services หลายจุด import `config_engine` และ `business_engine` ไปใช้งานจริง

### Affected files

- ไม่มี blocker สำคัญจาก audit รอบนี้

### Files to fix first

- ไม่มีไฟล์ที่ต้องแก้แบบเร่งด่วนเพื่อให้ Plan 5 ตรงตามแผน

---

## Plan 6 - Multi-tenant / SaaS

Observed status: `done`

### Checklist

- [x] เอกสาร design มีอยู่
- [x] roadmap ระบุชัดว่ายังไม่เริ่ม code
- [x] ไม่พบ misleading claim ว่ามี implementation แล้ว
- [x] Plan 5 ซึ่งเป็น prerequisite หลัก มีฐานรองรับแล้วระดับหนึ่ง

### Evidence

- เอกสาร plan นี้ยังอยู่ในสถานะ design-only และไม่ได้อ้างว่า code เสร็จแล้ว
- ดังนั้น ณ ตอนนี้ code ที่ยังไม่มีถือว่าไม่ขัด plan

### Affected files

- ไม่มีไฟล์ต้องแก้จากมุมมอง “plan mismatch” ในรอบนี้

### Files to fix first

- ไม่มี จนกว่าจะเริ่ม implementation ของ Plan 6

---

## Meta Plan Docs

### `plan/PLAN_ROADMAP_MASTER.md`

Observed status: `misleading claim`

Checklist:

- [ ] ตัวเลข test status สอดคล้องกับ repo ปัจจุบัน
- [ ] Plan 1B-A claim ว่า delegate ครบ สอดคล้องกับโค้ดจริง
- [ ] Plan 3 claim ว่า scheduler ใช้งานได้ สอดคล้องกับ runtime จริง
- [ ] Plan 4 claim ว่า bot registered และใช้งานได้จริง สอดคล้องกับ security/route contract

Files to fix first:

- `plan/PLAN_ROADMAP_MASTER.md`

### `plan/PLAN_REMAINING_ITEMS.md`

Observed status: `misleading claim`

Checklist:

- [x] ระบุ items ที่เคยค้างได้ถูกบางส่วน
- [ ] สถานะ “remain-1 ถึง remain-6 เสร็จแล้ว” สอดคล้องกับโค้ด/runtime ปัจจุบัน

Files to fix first:

- `plan/PLAN_REMAINING_ITEMS.md`

### `plan/PLAN_TEST_MASTER.md`

Observed status: `partial`

Checklist:

- [x] มีประโยชน์เป็น historical test plan
- [ ] reflect current test state ของ repo

Files to fix first:

- `plan/PLAN_TEST_MASTER.md`

---

## Priority Fix List

1. Stabilize import/test path
   - `app/services/vanna_service.py`
   - `app/services/ai_service.py`
   - `requirements.txt`

2. Fix Plan 3 runtime bugs
   - `app/services/scheduler.py`
   - `app/services/auto_analyzer.py`
   - `app/main.py`

3. Complete Plan 1B-A validation consolidation
   - `app/services/validation_service.py`
   - `mcp_servers/nt_validation_mcp.py`
   - `app/models/schema_models.py`
   - related tests

4. Fix Telegram contract and security
   - `app/telegram/bot.py`
   - `app/main.py`
   - `tests/integration/test_telegram_webhook.py`

5. Update stale planning docs after code is corrected
   - `plan/PLAN_ROADMAP_MASTER.md`
   - `plan/PLAN_REMAINING_ITEMS.md`
   - `plan/PLAN_TEST_MASTER.md`

---

## Commands Used During Audit

- `rg -n "^(#|##|###|- \[.\])" plan/*.md`
- `pytest tests/unit/test_validation_service.py -q`
- `pytest tests/integration/test_telegram_webhook.py -q`
- `pytest -q`
- direct runtime execution of `BackgroundScheduler._job_auto_analyze()`

## Current Conclusion

ระบบนี้มีหลายส่วนที่ทำมาถึงระดับ production structure แล้ว โดยเฉพาะ Plan 5
แต่เอกสาร roadmap ปัจจุบัน optimistic เกินโค้ดจริงในอย่างน้อย 4 ด้าน:

1. test suite status
2. validation consolidation
3. self-learning scheduler/runtime behavior
4. Telegram security + integration verification
