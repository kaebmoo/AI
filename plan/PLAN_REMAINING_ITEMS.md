<!-- markdownlint-disable MD024 MD022 MD031 MD032 MD058 MD060 -->

# AI Assistant — Remaining Items (Post Plans 0-5)

**Created:** 2026-03-19
**Updated:** 2026-03-22 late (re-verified, post-refactor doc sync)
**Source:** Verification audit + code review + PLAN_AUDIT_CHECKLIST_2026-03-21.md
**Status:** REMAIN-1 ถึง REMAIN-6 implemented แล้ว, scheduler tests ถูกเพิ่มแล้ว, และ `pytest -q` ผ่านทั้งชุด

## Re-verified status of post-audit fixes

- `vanna_service.py`: lazy import guard now catches the real Python 3.14 import failure path and no longer blocks test collection
- `ai_service.py`: eager import path now falls back safely when Vanna/ChromaDB is unavailable
- `scheduler.py`: old `days` bug is gone and auto-apply flow exists in code
- `validation_service.py`: DB rules query now reads `pattern` + `check_type`, and confidence factors include `detail` again
- `nt_validation_mcp.py`: both `calculate_confidence_score()` and `validate_result()` delegate to `ValidationService`
- `telegram/bot.py`: webhook secret verification added
- `main.py`: shutdown cleanup added
- `query_engine.py`: `_build_provider_kwargs` now uses `ConfigSessionLocal`
- `nt_admin_mcp.py`: `_get_db()` now prefers `CONFIG_DB_URL`
- `SchemaService`: default constructor now auto-imports engines from `app.db.session`

## Current verification result

- `pytest -q` = `363 passed, 3 skipped`
- Vanna-related unit tests now pass in Python 3.14
- Validation MCP tests now pass after restoring `detail` in confidence factors
- Telegram integration/unit tests now pass
- `tests/unit/test_scheduler.py` ถูกเพิ่มแล้วและผ่าน
- admin/schema/ai refactor plan ถูกปิดแล้ว และเหลือเฉพาะ follow-up hardening แยก
- schema/vanna SQL interpolation hardening สำหรับจุดที่ยืนยันได้ถูกปิดแล้ว พร้อม regression tests ฝั่ง schema service

## Remaining follow-up work

ตอนนี้ไม่เหลือ blocker จากรายการ REMAIN เดิมแล้ว และงาน scheduler tests ถูกปิดแล้ว เหลืองาน hardening เชิง code quality เป็นหลัก:

1. เก็บ static analysis warnings ใน API layer
2. เพิ่ม integration coverage สำหรับ compatibility shim ของ schema/ai services
3. เก็บ minor consistency debt เช่น `_detect_hierarchy_level()` shim indirection ถ้าคุ้มค่า
4. พิจารณา hierarchy cache owner transfer ในรอบถัดไปเท่านั้น ไม่ใช่ blocker ปัจจุบัน

---

## Next Round Plan — Web Admin

งานรอบถัดไปฝั่ง web admin ควรเป็นการเก็บความแน่นและความเชื่อถือของ workspace ที่เพิ่ง refresh ไปแล้ว มากกว่าการเปิด feature ใหม่เพิ่มทันที

### ADMIN-N1: Secondary page polish and consistency

- ทำ visual/spacing pass ให้หน้า Settings, Query Logs, Providers, Models, API Keys, และ Vanna Knowledge ใช้มาตรฐาน page framing เดียวกัน
- ลด card ซ้อนหลายชั้นและ heading ซ้ำ
- เก็บ empty/loading/error states ให้สม่ำเสมอ

### ADMIN-N2: Dashboard contract and browser regression tests

- เพิ่ม API contract coverage สำหรับ `/api/v1/admin/dashboard-overview` และ `/api/v1/admin/config/ai/effective`
- เพิ่ม regression checks สำหรับ navigation persistence, lower-menu visibility, และ CTA routing จาก dashboard alerts
- เก็บ browser QA checklist สำหรับ release รอบถัดไป

### ADMIN-N3: Performance follow-up

- วิเคราะห์ shared vendor chunk ที่ยังใหญ่หลัง route-level split
- แยก import หนักที่ดึงเข้าทุกหน้าโดยไม่จำเป็น
- พิจารณา page-level data prefetch เฉพาะหน้าที่คุ้มค่า

### ADMIN-N4: Admin API decomposition

- ย้าย logic ที่ยังกองใน route layer ไป service layer เพิ่มเติม
- เก็บ naming และ invalidation policy ของ admin queries ให้ชัดเจนขึ้น
- ลด risk จาก broad exception handling ใน admin runtime paths

---

## Next Round Plan — Vanna / Database

### VANNA-N1: Retrieval quality verification

- ทดสอบ 5-10 คำถามจริงต่อ context หลักหลังเปลี่ยน corpus เป็น DB-driven
- ตรวจ retrieved docs ว่าตรง expected context/rule/hierarchy หรือไม่
- จัด baseline query set สำหรับ revenue, expense, transfer_price, และ P&L

### VANNA-N2: Documentation coverage audit

- review `vanna_documentation` seed docs และ manual docs ที่ admin เพิ่ม
- แยก content ที่ควรอยู่ใน business rules ออกจาก content เชิง workflow/guide
- ตรวจว่าคำอธิบาย hierarchy กับ value lookup ไม่ซ้ำและไม่ชน retrieval กันเอง

### VANNA-N3: Business DB documentation refresh

- ปรับ docs ฝั่ง database/view ให้ตรงกับ main views ที่ใช้งานจริง (`revenue_search`, `v_expense_mart`, `v_pl_costtype_nt_mth`)
- เพิ่ม context-specific examples ที่ไม่ drift จาก schema metadata ปัจจุบัน
- วาง process ให้ onboarding context ใหม่มี doc follow-up ชัดเจน

### VANNA-N4: Sync operations hardening

- เพิ่ม runbook สำหรับ migration `031_vanna_documentation.sql`, brain sync, และ post-sync verification
- ตรวจ behavior เมื่อ migration ยังไม่ถูก apply หรือ table หาย
- เก็บ operational note เรื่อง Chroma reset/retrain duration และ failure handling

### Scheduler test status

ไฟล์ `tests/unit/test_scheduler.py` ถูกเพิ่มแล้วเพื่อพิสูจน์ behavior ของ scheduler โดยตรง ครอบคลุมอย่างน้อย:

- start/stop scheduler ไม่สร้าง task ซ้ำ
- `_job_auto_analyze()` ปิด DB session เสมอ
- `_apply_high_confidence_fixes()` apply เฉพาะ fix ที่เข้าเงื่อนไข
- `_job_config_gc()` log issue ได้โดยไม่ทำให้ scheduler ล้ม

---

## REMAIN-1: Audit Service Integration into Admin Tools

**Plan:** 3 | **Priority:** ⚡ High | **Effort:** 2-3 ชม.

### ปัญหา

`audit_service.py` สร้างแล้ว แต่ไม่มี admin tool ไหนเรียก `log_change()` — ทำให้ไม่มี audit trail

### ไฟล์ที่ต้องแก้

| ไฟล์ | แก้อะไร |
| ------ | --------- |
| `app/tools/admin/mapping_tools.py` | AddMappingTool.execute() — เพิ่ม audit log หลัง db.commit() |
| `app/tools/admin/rule_tools.py` | AddRuleTool.execute() — เพิ่ม audit log หลัง db.commit() |
| `app/tools/admin/example_tools.py` | AddExampleTool.execute() — เพิ่ม audit log หลัง db.commit() |

### วิธีแก้
```python
# เพิ่มหลัง db.commit() ในทุก Add tool:
try:
    from app.services.audit_service import AuditService
    audit = AuditService(db)
    audit.log_change(
        action="INSERT",
        table_name="schema_semantic_mapping",  # หรือตารางที่เกี่ยวข้อง
        record_id=new_record.id,
        new_value={"keyword": params["keyword"], ...},
        source="admin_agent",
    )
except Exception:
    pass  # Audit failure ไม่ควรทำให้ tool fail
```

### ทดสอบ
- ถาม Admin Agent ให้เพิ่ม mapping → ตรวจ audit_log table มี record ใหม่
- `tests/unit/test_audit_service.py` — มีอยู่แล้ว 4 tests

---

## REMAIN-2: AddExampleTool Missing Dedup Check

**Plan:** 3 | **Priority:** ⚡ High | **Effort:** 1 ชม.

### ปัญหา
`AddMappingTool` + `AddRuleTool` มี DedupEngine check แล้ว แต่ `AddExampleTool` ยังไม่มี → สามารถเพิ่ม example ซ้ำได้

### ไฟล์ที่ต้องแก้
`app/tools/admin/example_tools.py` — AddExampleTool.execute()

### วิธีแก้
```python
# เพิ่มก่อน db.add(example):
try:
    from app.services.dedup_engine import DedupEngine
    dedup = DedupEngine(db)
    dedup_result = dedup.check_example_duplicate(
        question=params["question"],
        sql=params["sql"],
    )
    if dedup_result.has_duplicate:
        return {
            "success": False,
            "message": f"พบ example ที่คล้ายกัน ({dedup_result.duplicate_type}): id={dedup_result.existing_id}",
        }
except Exception:
    pass  # Fallback: no dedup check
```

---

## REMAIN-3: Telegram Bot Registration in main.py

**Plan:** 4 | **Priority:** ⚡ High | **Effort:** 3-4 ชม.

### ปัญหา
Telegram bot code ครบ (`app/telegram/`) แต่ไม่ได้ register ใน `app/main.py` → bot ไม่ทำงาน

### ไฟล์ที่ต้องแก้/สร้าง
| ไฟล์ | แก้อะไร |
|------|---------|
| `app/config.py` | เพิ่ม TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, TELEGRAM_BOT_MODE |
| `app/main.py` | เพิ่ม startup event สำหรับ bot |
| `app/api/v1/telegram.py` (NEW) | webhook endpoint (optional, ถ้าใช้ webhook mode) |

### config.py
```python
# Telegram Bot
TELEGRAM_BOT_TOKEN: str = ""
TELEGRAM_WEBHOOK_SECRET: str = ""
TELEGRAM_BOT_MODE: str = "polling"  # "polling" or "webhook"
TELEGRAM_WEBHOOK_URL: str = ""  # สำหรับ webhook mode
```

### main.py startup
```python
# ใน lifespan หรือ startup event:
if settings.TELEGRAM_BOT_TOKEN:
    from app.telegram.bot import NTAIBot
    bot = NTAIBot(token=settings.TELEGRAM_BOT_TOKEN)
    if settings.TELEGRAM_BOT_MODE == "polling":
        asyncio.create_task(bot.start_polling())
    else:
        # Webhook mode: mount as sub-app
        from app.api.v1.telegram import router as telegram_router
        app.include_router(telegram_router, prefix=f"{settings.API_V1_STR}/telegram")
```

### ทดสอบ
- ตั้ง TELEGRAM_BOT_TOKEN ใน .env → start server → ส่งข้อความหา bot
- `tests/unit/test_telegram_dispatcher.py` — 8 tests มีอยู่แล้ว
- `tests/integration/test_telegram_webhook.py` — 3 tests มีอยู่แล้ว

---

## REMAIN-4: MCP Full Delegation (Validation)

**Plan:** 1B-A | **Priority:** 🔧 Medium | **Effort:** 2-3 ชม.

### ปัญหา
`check_business_rules` delegate แล้ว แต่ `calculate_confidence_score` + `validate_result` ยัง hardcode ใน MCP

### ไฟล์ที่ต้องแก้
`mcp_servers/nt_validation_mcp.py`

### วิธีแก้
1. เพิ่ม `calculate_confidence()` ใน `ValidationService`
2. เพิ่ม `validate_result()` ใน `ValidationService`
3. MCP functions delegate ไป ValidationService
4. เก็บ logic เดิมเป็น fallback (กรณี import fail)

### Note
ปัจจุบัน logic ใน MCP **ทำงานถูกต้อง** — เป็น duplicate code issue ไม่ใช่ bug
แต่ถ้าแก้ logic ต้องแก้ 2 ที่ (MCP + Service) → ควรรวมเป็นที่เดียว

---

## REMAIN-5: Scheduled Jobs (Auto-Analyzer + GC)

**Plan:** 3 | **Priority:** 🔧 Medium | **Effort:** 4-6 ชม.

### ปัญหา
Services สร้างแล้ว (`auto_analyzer.py`, `config_gc.py`) แต่ไม่มีอะไร schedule ให้ทำงาน

### ไฟล์ที่ต้องแก้/สร้าง
| ไฟล์ | แก้อะไร |
|------|---------|
| `app/main.py` | เพิ่ม APScheduler หรือ background tasks |
| `requirements.txt` | เพิ่ม `apscheduler>=3.10` (ถ้าใช้) |
| `app/services/scheduler.py` (NEW) | Job definitions + scheduler setup |

### Jobs ที่ต้องตั้ง
| Job | Schedule | Service.method() |
|-----|----------|-------------------|
| Auto-analyze failures | ทุก 6 ชม. | `AutoAnalyzer.analyze_recent_failures()` |
| Config GC scan | ทุก 24 ชม. | `ConfigGC.run_full_scan()` |
| Apply auto-fixes | ทุก 6 ชม. (หลัง analyze) | ดึง fixes ที่ confidence ≥ 0.8 → apply |

### ทางเลือก
1. **APScheduler** — simple, in-process, ดีสำหรับ single instance
2. **Celery Beat** — distributed, ดีสำหรับ multi-instance (Plan 6 SaaS)
3. **FastAPI BackgroundTasks** — ง่ายสุด แต่ไม่มี scheduling

### แนะนำ: ใช้ APScheduler ก่อน → ย้ายเป็น Celery ตอน Plan 6

---

## REMAIN-6: DB Separation — Config DB Session

**Plan:** 5 | **Priority:** 🔧 Medium | **Effort:** 4-6 ชม.

### ปัญหา
Migration script (`migrate_config_to_separate_db.py`) สร้างแล้ว แต่ app ยังไม่รู้จัก config.db

### ไฟล์ที่ต้องแก้
| ไฟล์ | แก้อะไร |
|------|---------|
| `app/config.py` | เพิ่ม `CONFIG_DB_URL` setting |
| `app/db/session.py` | เพิ่ม `config_engine` + `ConfigSessionLocal` |
| `app/services/schema_service.py` | ใช้ config session สำหรับ schema_contexts, mappings, rules |
| `app/api/deps.py` | เพิ่ม `get_config_db()` dependency |

### config.py
```python
# Config DB (schema_contexts, mappings, rules, hierarchy, etc.)
CONFIG_DB_URL: str = ""  # Empty = use same DB as DATABASE_URL (backward compatible)
```

### session.py
```python
# Config DB — only if CONFIG_DB_URL is set, otherwise reuse main engine
if settings.CONFIG_DB_URL:
    config_engine = create_engine(settings.CONFIG_DB_URL)
    ConfigSessionLocal = sessionmaker(bind=config_engine)
else:
    config_engine = engine  # Same as app DB
    ConfigSessionLocal = SessionLocal
```

### Note
ต้อง backward compatible — ถ้าไม่ตั้ง CONFIG_DB_URL ต้องทำงานเหมือนเดิม (ใช้ DB เดียว)

---

## REMAIN-7: Plan 6 — SaaS / Multi-tenant

**Plan:** 6 | **Priority:** 📋 Future | **Effort:** 2-4 สัปดาห์

### สถานะ
Design เสร็จ (PLAN_6_SAAS.md) แต่ยังไม่เริ่ม code

### Prerequisite
- REMAIN-6 (DB Separation) ต้องเสร็จก่อน
- API Key auth (Plan 4B) ต้องเสร็จก่อน ✅

### ขั้นตอนหลัก
1. Tenant model + table
2. Tenant middleware (extract from API key)
3. Per-tenant config DB + business DB
4. Upload endpoint (CSV → SQLite)
5. Auto Context Onboarding per tenant
6. Tenant isolation tests

---

## REMAIN-8: Plan 1B Phase C — MCP SSE + Auth

**Plan:** 1B | **Priority:** 📋 Future | **Effort:** 1-2 วัน

### สถานะ
Deferred (ทำตอน Plan 6 SaaS)

### เนื้อหา
- เปลี่ยน MCP transport จาก stdio → SSE (Server-Sent Events)
- เพิ่ม API key auth สำหรับ MCP connections
- รองรับ remote MCP clients

---

## REMAIN-9: Wrong-DB / broken paths ที่พบระหว่าง Plan 7 Phase 1 (2026-09-18)

**Plan:** 7 (พบระหว่างไล่ query path) | **Priority:** ต่อข้อ | **Effort:** ต่อข้อ | รายละเอียด: `plan/FIX_NOTES.md` หัวข้อ Plan 7 Phase 1

| # | ปัญหา | ไฟล์ | ผลกระทบ | Priority |
|---|---|---|---|---|
| 9.1 | ✅ 2026-09-19 — onboarding facade ส่ง business DB path ให้ `ConfigApplicator`/`ConfigValidator` → แก้: facade รับ `config_db_path` (default = CONFIG_DB_URL); inspect ยังอ่าน business DB | `app/services/context_onboarding.py` | onboard context ผ่าน UI: apply เขียนผิด DB (ล้มเงียบ), validate 500 | ⚡ High |
| 9.2 | ✅ 2026-09-19 — `/chat/train` เช็ค `isinstance(check_res, dict)` แต่ `call_tool` คืน str + validate กับ legacy DB เสมอ → แก้: parse JSON, ไม่ success = 400, รันบน source ของ context | `app/api/v1/chat.py` (~L859) | SQL ผิดไม่เคยถูกปฏิเสธก่อนบันทึกเป็น golden | Medium |
| 9.3 | ✅ 2026-09-19 — dedup-blocked result ไม่มี `context_name` → `"revenue"` ถูกบันทึก → แก้: ใส่ context ที่ resolve จาก request | `app/services/query_engine.py` (~L410) | follow-up ถูกส่งไป context ผิด | Medium |
| 9.4 | ✅ 2026-09-19 — `vanna_service._sync_ddl` หา DDL ใน config DB → แก้: อ่านจาก business DB เฉพาะ main view ของ context ที่ active (ไม่ train ตาราง raw) — ผลต่อ accuracy ยังไม่ได้วัด (มีผลเมื่อ admin กด Sync Brain) | `app/services/vanna_service.py` (~L116) | sync-brain ไม่เคย train DDL | Medium |
| 9.5 | ✅ 2026-09-19 — `hierarchy_service` (detect_changes / bootstrap_from_view / get_available_views) query view บน config DB; `scripts/extract_hierarchy.py` เขียน `master_hierarchy*` ลง business DB → แก้: อ่านข้อมูลผ่าน source ของ context (legacy/file), config อ่าน/เขียนที่ config DB; script เลิกใช้ `--db` | `app/services/hierarchy_service.py`, `scripts/extract_hierarchy.py` | admin hierarchy ได้ผลว่าง / extract ลงผิด DB | Medium |
| 9.6 | (ยังไม่ทำ — ทำพร้อม Plan 7 Phase 4) admin schema browser, dimension families, onboarding, sync-brain เห็นแค่ business DB เดิม | `app/api/v1/admin/*` | สำหรับ `feed_*` เห็นสำเนาเก่า ไม่ใช่ไฟล์ — ต้องผูกกับ source ของ context (ทำพร้อม Plan 7 Phase 4 admin) | Medium |
| 9.7 | ✅ 2026-09-19 — admin agent `onboarding_tools` เรียก method ที่ไม่มี (`inspect_view`, `onboard`) → แก้: ใช้ pipeline เดียวกับ admin API, ส่ง path ของ business DB (เดิมส่ง session), `validate_config` query config DB (model `SchemaContext` ไม่มีอยู่จริง) | `app/tools/admin/onboarding_tools.py` | tool fail ทุกครั้ง | Low |
| 9.8 | ✅ 2026-09-19 — `nt_metadata_mcp` query ตาราง config บน business DB (ล้มทุก tool — tool-loop เท่านั้น); `nt_validation` อ่าน rules จาก app.db (ผ่านเงียบ); `nt_validation.get_db` ไม่ `mode=ro` (dead) → แก้: nt-metadata ต่อ `CONFIG_DB_URL` (client ส่ง path absolute), rules อ่านผ่าน `ConfigSessionLocal`, ลบ adapter ที่ไม่ได้ใช้ | `mcp_servers/` | tool-loop mode ได้ข้อมูล schema ไม่ได้ | Low |
| 9.9 | (รอตัดสิน — ไม่ลบเอง) dead code ชี้ DB ผิด: `matcha_examples.py` (ใช้แค่ `scripts/test_matcha_improvements.py`), `business_db.py` (มีแค่ test ของตัวเองใน `test_db_separation.py` — ลบ = ลบ test), `create_adapter`/`get_adapter_for_settings` + adapter SQLite/PostgreSQL/MSSQL (PLAN_7 §4/§9 นับเป็นฐานของ SQL source ในอนาคต) | `app/services/` | ไม่มีผลตอนนี้ — cleanup | Low |

---

## REMAIN-10: Keyword index — fallback scan ช้า + rebuild ของจริง

**Plan:** keyword-index fix (`0f3aaa7`) | **Priority:** Medium | **Effort:** 0.5–1 วัน

### ปัญหา
1. หลัง `0f3aaa7` value lookup ค้นข้อมูลจริงแล้ว แต่ fallback scan ทีละคอลัมน์ — `v_expense_mart` (333k แถว) ~2.2 วินาทีต่อ keyword ที่ไม่อยู่ใน index → คำถาม expense บางข้อช้าลง 2–5 วินาที
2. keyword index ใน `config.db` จริงยังไม่ได้ rebuild — ถ้า rebuild ตอนนี้ คอลัมน์ตัวเลขเพิ่มคำสั้น ~479 คำ และ prompt ของ golden เปลี่ยน 37/63 ข้อ

### วิธีแก้ (ข้อเสนอ)
1. `search_db_for_keyword`: scan ครั้งเดียวหาว่าคอลัมน์ไหนมีค่าตรง (`SELECT MAX(c1 LIKE :kw ...), MAX(c2 LIKE :kw ...) FROM view`) แล้วค่อย `SELECT DISTINCT` เฉพาะคอลัมน์ที่เจอ — ผลเหมือนเดิมทุกกรณี, keyword ที่ไม่เจอเหลือ 1 scan
2. rebuild: ไม่ index คอลัมน์ตัวเลข → rebuild บนสำเนา `config.db` → eval เทียบ → ทำของจริงพร้อม backup

### ทดสอบ
ผลของ `search_db_for_keyword` เท่าเดิมบน golden 63 ข้อ (deterministic, ไม่เรียก LLM) + latency ของ expense #6/17/34/36 ก่อน/หลัง

### สถานะ (2026-09-18)
- ✅ **ข้อ 1 เสร็จ** — probe `MAX(CASE WHEN col LIKE … )` ครั้งเดียวต่อ keyword แล้ว DISTINCT (query เดิมทุกตัวอักษร) เฉพาะคอลัมน์ที่เจอ;
  บน SQLite probe ใช้ `LIKE` อย่างเดียว (upper() กับ LIKE ของ SQLite พับตัวพิมพ์แค่ ASCII เหมือนกัน → คอลัมน์ที่เจอเท่าเดิม, ครึ่ง UPPER กินเวลา ~2/3);
  DuckDB: คอลัมน์ที่ LIKE ไม่ได้ (non-text) ถูกตัดออกเหมือนที่ query รายคอลัมน์เคย error แล้วข้าม
  - ผลเท่าเดิม: golden 75 ข้อ (63 + feed_expense 12) ผ่าน value lookup จริง + ค้นตรง 15 keyword × 6 context (รวม `%`, `_`, `'`, ตัวเลข, ไทย) = 165 ครั้ง —
    SQLite เท่ากันทุก byte; DuckDB เท่ากันที่ชุดคอลัมน์ + จำนวน (code เดิมเองให้ค่าต่างกันทุกครั้งที่เรียก: `DISTINCT … LIMIT` ไม่มี ORDER BY)
  - latency value lookup: expense #6 2.72 → **0.61 s**, #17 1.37 → **0.31 s**, #34 1.41 → **0.33 s**, #36 1.42 → **0.32 s**; ทุก golden รวม 13.1 → 7.8 s
  - แย่ลงได้กรณีเดียว: keyword ที่ตรงทุกคอลัมน์ (+1 scan) — เช่น `%`/`_`; คำจริงที่ตก fallback ส่วนใหญ่ไม่ตรงเลย
- ✅ **ข้อ 2 เสร็จ 2026-09-19** (`2243fbe`) — ไม่ index ค่าที่ไม่ใช่ข้อความ (ดูจากค่า ไม่ใช่ type ที่ประกาศ — view ของ SQLite มักไม่มี type) + ไม่เก็บตัวเลขล้วนที่ถูกตัดออกมาจากค่ายาว (`700` ของ `MY 5G 700 MHZ`); ค่าที่เป็นรหัสทั้งค่า (`gl_code`, `'007'`) ยังค้นได้
  - บนสำเนา: keyword ตัวเลขล้วน 1,062 → 700 (เหลือแต่รหัสทั้งค่า: feed_expense `gl_code` 640, revenue `SUB_ITEM` 29, pl `report_date` 26, `gl_prefix` 5) — ไม่มี golden ข้อไหนได้ keyword ตัวเลข ("10 อันดับ" ไม่ match แล้ว)
  - block "Actual Values Found" เปลี่ยน 33/42 ข้อ: expense เลิกได้ขยะ `ค่า` (8 ข้อ) ได้ `บัญชี`/`ตบชง.` แทน, feed_revenue ได้ BU ตรงชื่อ (9 ข้อ); noise ใหม่: `ด้วย` (transfer price 1 ข้อ), `ค่า` ของ feed_expense (12 ข้อ)
  - eval เต็ม (matcha gpt-4.1, วันเดียวกัน): ก่อน `eval_20260919_0712` **30/63** → หลัง `eval_20260919_0722` **31/63** (ต่าง #35 mismatch → exact; feed_revenue 14/14, feed_expense 12/12 ทั้งสองรอบ; golden_broken 12 เท่าเดิม); value lookup ของ golden ทั้งชุด 2.12 → 1.88 s
  - **rebuild ของจริงแล้ว** (backup ใน scratchpad ของ session): 5,390 → 21,538 แถว — revenue 1,679→6,133, expense 2,155→3,403, transfer price 285→3,421, pl_costtype 1,271→1,399, feed_revenue 0→15, feed_expense 0→1,620, feed_sales 0→5,547; `feed_sales` eval หลัง rebuild 12/12 (`eval_20260919_0725`)
  - เหลือ (ไม่ทำ): noise คำไทยสั้น (`ค่า`, `ด้วย`) มาจากการตัดคำด้วยช่องว่าง — ถ้าจะแก้ ให้เพิ่ม stop words ฝั่ง index (ตอนนี้กรองแค่ฝั่งคำถาม `THAI_STOP_WORDS`)

---

## REMAIN-11: DataFeed sales / ebt — contract ขาดความหมายที่ AI ต้องใช้ (Plan 7 Phase 2)

**Plan:** 7 Phase 2 exit | **Priority:** ⚡ High (บล็อก exit Phase 2) | **Effort:** NT-Report ~0.5 วัน + AI ~0.5 วัน | รายละเอียด: `plan/archive/RESULT_P7_PHASE2.md`

| โดเมน | ปัญหา | ผลตอนนี้ |
|---|---|---|
| sales | `metric` = actual + target ไม่มีกฎห้ามรวม; `control_totals.csv` รวมทั้งสอง; ไม่ชัดว่ายอดรวมบริษัทนับ BG 8/โครงการภาครัฐไหม | "ยอดขายรวม ก.ค. 69" ตอบ 6,978 M (actual จริง 3,290 M) |
| ebt | ไม่มี control_totals; ไม่มีกฎ EBT = รายได้ − ค่าใช้จ่าย | "กำไร ก.ค. 69" ตอบ +7,201 M (ที่ถูก −1,088 M) |

สถานะ: source + knowledge ลงทะเบียนแล้ว, context `feed_sales`/`feed_ebt` ปิดไว้ (`is_active=0`) — ✅ ตัดสิน 2026-09-19: **ทางเลือก A** (NT-Report แก้ contract; EBT = ยอดขาย − ค่าใช้จ่าย โดยยอดขาย = กลุ่ม 01.รายได้ ใน fact_ebt ซึ่งเป็นรายได้ฐานยอดขาย ≠ รายได้ในรายงานรายได้ เช่น รวมยอดขายบัตร prepaid) → prompt `plan/PROMPT_NT_REPORT_P7.md`
หลังแก้ contract (ทางเลือก A): knowledge re-sync เอง → เปิด context → `gen_golden_from_controls` → eval ≥ 90%

**อัปเดต 2026-09-19:**
- ✅ **sales ปิดแล้ว** — NT-Report sales 1.2.0 (`control_totals.filter {metric: actual}` + กฎ); ฝั่ง AI `dfce5d5` + `9ec6666`; `feed_sales` active, golden 12 ข้อ, eval **12/12** (P50 7.5 s)
- ⬜ **ebt ยังเปิดอยู่ (รอเจ้าของตัดสิน)** — ebt 1.2.0 ให้ −1,088,133,452.03 ตามที่กำหนด (eval 12/12) แต่ NT-Report `90fd787` (1.2.1) เปลี่ยนยอดรวมเป็น YTD ของ 2 สายงานขาย (+417.33 MB);
  AI ตอบยอดสะสมเป็นยอดเดือน และตอบยอดรวมเมื่อถามรายสายงาน → `feed_ebt` ปิดไว้, golden 12 ข้อ `is_active=0` — ทางเลือก A/B/C: `plan/archive/RESULT_P7_PHASE2.md`
  - **2026-09-19 บ่าย — ตัดสินแล้ว: ebt 1.3.0 มีทั้งรายเดือน (`*_month`) และสะสม**; ฝั่ง AI `c6e7cca` (golden แยกเดือน/สะสม 24 ข้อ, instruction ชี้ `fact_ebt`, prompt ยอมตารางที่ instruction ระบุ); eval **18/24 = 75%** → ยังปิด —
    รอ NT-Report: `agg: point_in_time` ของ measure สะสม + กฎห้าม SUM ข้ามงวดของตารางยอดรวม + description ขึ้นต้น "ยอดสะสม" + กฎ EBT รายสายงาน (รายละเอียด RESULT_P7_PHASE2)
  - (เดิม) งานฝั่ง AI ที่ต้องทำไม่ว่าเลือกทางไหน: main view ของ context ไม่ควรเป็นตารางยอดรวมที่ไม่มีมิติ (ตอนนี้ = `control_totals.source`) เพราะ prompt two-pass บังคับใช้ main view

---

## REMAIN-12: two-pass Pass 1 เห็นเฉพาะคอลัมน์ของ main view (เสนอ 2026-09-19)

**Plan:** 7 (context ที่มีหลายตาราง) | **Priority:** Medium | **Effort:** ~1 วัน + eval ทุก feed context

context ของ file source มีหลายตาราง แต่ Pass 1 (intent) และ schema metadata ใน prompt มาจาก main view ตารางเดียว → คำถามที่ filter ด้วยมิติของตารางอื่น
(ebt: "EBT ของสายงาน 1" ขณะ main view = ตารางยอดรวมที่ไม่มี division) ถูกทิ้ง filter เงียบ ๆ แล้วตอบยอดรวม. `c6e7cca` แก้ได้เฉพาะกรณี GROUP BY ("แยกตามสายงาน").
ข้อเสนอ: ให้ Pass 1 เห็นคอลัมน์ของทุกตารางที่ instruction ระบุ (ชุดเดียวกับ `hybrid_flow.table_rule`) และถ้า intent มี filter/dimension ที่ไม่อยู่ใน main view ให้ Pass 2 ใช้ตารางที่มีคอลัมน์นั้น; ถ้าไม่มีตารางไหนมี → ตอบว่าตอบไม่ได้ ไม่ตอบยอดรวม

**สถานะ 2026-09-19:** ✅ ส่วน "ห้ามทิ้ง filter เงียบ ๆ" แก้แล้ว `a458cda` — Pass 2 ได้บรรทัดชี้ตารางที่มีคอลัมน์ + **ตรวจ SQL แบบ deterministic** (คอลัมน์ filter/dimension ของ intent ที่มีเฉพาะในตารางอื่นของ context ต้องปรากฏใน SQL ไม่งั้น attempt ถูกปฏิเสธแล้ว retry); prompt อย่างเดียวไม่พอ (ลองแล้วยังทิ้ง filter). ถามจริง: สายงาน 1 → `fact_ebt` + `division = …` (แถว COMPUTED 3.1), ศูนย์ต้นทุน 2P10200 → `fact_ebt` + `cost_center` = 124.93 M (เดิม 8,050 M); eval ebt เท่าเดิม 18/24, guard ยิง 0 ครั้งใน 24 ข้อยอดรวม; กระทบเฉพาะ context ที่ instruction ระบุตารางอื่น (config จริง: `feed_ebt` ตัวเดียว).
⬜ ที่เหลือ: Pass 1 ยังเห็นเฉพาะคอลัมน์ของ main view (ตอนนี้ได้ชื่อคอลัมน์ถูกเพราะ instruction ของ ebt ระบุคอลัมน์ของ `fact_ebt`); ชื่อคอลัมน์ที่ไม่มีตารางไหนมี ยังปล่อยให้ Pass 2 map เอง (เช่น `business_unit` → `bu`)

---

## Backlog / Nice-to-Have

| Item | Plan | Detail |
|------|------|--------|
| CLAUDE.md outdated | — | ยังอ้าง `revenue.sqlite` ควรเปลี่ยนเป็น `nt_fi_report.sqlite` |
| MEMORY.md truncated | — | เกิน 200 บรรทัด — ย้าย detail ไป topic files |
| Admin Agent: per-stage model | 1 | ใช้ cheap model สำหรับ summarize, default model สำหรับ tool selection |
| Telegram: CSV export | 4 | User ขอ export → bot ส่งไฟล์ CSV |
| API Key: scope enforcement | 4B | scope=query ใช้ได้แค่ /query/, scope=admin ใช้ได้ /admin/ |
| `ChatBubble.tsx` Key Metric box can still duplicate `DataChart` | UI Chart Wave 3 | `visualization==='single_value'`/`'table'` fallback-to-vertical_bar case ถูกแก้แล้ว (`buildEChartsOption` early-return guard, ดู `PLAN_UI_CHART_IMPROVEMENT.md` Wave 3 หมายเหตุ B1) แต่ Key Metric box เงื่อนไข (`ChatBubble.tsx` ~line 259: `data.length===1 && Object.keys(data[0]).length<=2`) เป็น**คนละเงื่อนไข**จาก `visualization` โดยสิ้นเชิง — ถ้า AI เลือก `bar_chart` (ไม่ใช่ `single_value`) สำหรับ data 1 แถว ≤2 คอลัมน์ ทั้ง `DataChart` (กราฟแท่ง 1 แท่งจริง) และกล่องตัวเลขใหญ่จะ render พร้อมกันได้ — ยังไม่ได้ตัดสินใจว่าควรทำ mutually exclusive อย่างไร (ให้ DataChart ชนะเสมอ / ให้ Key Metric ชนะเมื่อ data shape เข้าเงื่อนไข / เช็ค `visualization` ประกอบด้วย) |
