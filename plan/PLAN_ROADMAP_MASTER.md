# AI Assistant — Roadmap Master Plan

**Date:** 2026-03-19 (Updated)
**Project Root:** `/Users/seal/Documents/GitHub/AI/`
**OpenMiniCrew Root:** `/Users/seal/Documents/GitHub/openminicrew/`

---

## สถานะรวม (Updated 2026-09-18)

> **โครงสร้างโฟลเดอร์ (2026-07-12):** แผนที่ทำเสร็จแล้วทั้งหมด (Plans 0-5, F1-F11, refactoring plans) ย้ายไป `plan/archive/` — โฟลเดอร์ `plan/` ชั้นบนเหลือเฉพาะเอกสาร reference ที่ยังมีผล และแผนที่ยังไม่เริ่ม/รอตัดสินใจ ดู `plan/README.md`

| Plan | สถานะ | % | Tests | หมายเหตุ |
|------|--------|---|-------|---------|
| **Plan 0** | ✅ DONE | 100% | full suite green | legacy blockers ที่เคยทำให้ collection พัง ถูกแก้แล้ว |
| **Plan 1** | ✅ DONE | 95% | 21 tests | API/tests มีและ suite รวมผ่าน |
| **Plan 1B-A** | ✅ DONE | 95% | 18 tests | MCP delegate ครบตาม flow ปัจจุบัน |
| **Plan 1B-B** | ✅ DONE | 90% | 8 tests | Wrapper ทำงาน, session lifecycle ยังเป็น global singleton |
| **Plan 2** | ✅ DONE | 95% | 14 tests | Endpoints ครบ, suite รวมผ่าน |
| **Plan 3** | ✅ DONE | 90% | 19 tests | scheduler/auto-apply มีจริงแล้ว, ควรเพิ่ม dedicated scheduler tests |
| **Plan 4** | ✅ DONE | 90% | 25 tests | Telegram integration tests ผ่าน |
| **Plan 4B** | ✅ DONE | 95% | 13 tests | Query endpoint ทำงาน, mock-heavy tests |
| **Plan 5** | ✅ DONE | 100% | 7 tests | 3-DB live, ConfigBase แยก, business_engine ครบทุก call path |
| **Plan 6** | ⏸ DEFERRED | 0% | 0 | multi-tenant เลื่อนเป็น Tier 3 — ตัดสิน 2026-09-18 ใช้แบบผสม (ภายใน NT หลาย workspace / ลูกค้าภายนอก private deployment) ดู PLAN_7 §12 |
| **Plan 7** | 🟡 Phase 1–6 ✅ · hardening ✅ · **go-live ✅ (2026-09-20) — ปุ่ม portal เปิดเฉพาะ `revenue`** | 7/8 phases | suite **1092 passed / 3 skipped** | Data Source as a Service (zero-import) — Phase 1 เสร็จ 2026-09-18; Phase 2: `data_as_of`, knowledge re-sync อัตโนมัติ, 4 โดเมนลงทะเบียน (revenue 14/14, expense 12/12, sales 12/12 — 2026-09-19; ebt 1.3.0 eval 18/24 ปิดไว้ รอกฎ point-in-time ใน contract); Phase 3 (2026-09-19): `scope` บังคับที่ชั้น SQL ทั้ง file/legacy — ดู archive/RESULT_P7_PHASE{2,3}.md, PROMPT_NT_REPORT_P7.md; Phase 4.5 (2026-09-19): `llm_data_policy` + provider allowlist ต่อ source (บังคับที่ชั้น provider, test ดัก sentinel), retention 30 วัน, DSR, `query_audit` ทุกช่องทาง — archive/RESULT_P7_PHASE45.md; Phase 5 (2026-09-19): คำถามข้ามหลาย context — แตกคำถามต่อ context → `QueryEngine.query` เดิม → รวมด้วย template + คำนวณใน code, flag ต่อ workspace ที่ `/api/v1/query`; eval ข้ามโดเมน 0/10 → 8–9/10 — archive/RESULT_P7_PHASE5.md; Phase 6 (2026-09-20): MCP สำหรับผู้เรียกภายนอก — facade `/api/v1/mcp` (stateless Streamable HTTP + `X-API-Key` ทุก request, 3 tools `ask` / `list_contexts` / `source_status` ผ่านทางเข้าเดียวกับ `/api/v1/query`, ไม่คืน SQL / ข้อความ exception, policy ≠ `full` ถูกปฏิเสธ), flag `mcp_external_enabled` ปิดเป็นค่าเริ่มต้น; ต่อ Claude Code 2.1.270 จริงบนสำเนา DB, overhead เส้นทาง cache +6.6 / +11.4 ms (P50 / P95); **ยังไม่เปิดบน DB จริง / ยังไม่ออก key จริง**; widget ไม่ทำ — archive/RESULT_P7_PHASE6.md; Phase 7 ยังไม่เริ่ม; **go-live 2026-09-20**: config.db migrate แล้ว, server รัน, key จริงของ portal ผูก workspace `nt-report` (20/นาที 2,000/วัน), `llm_provider_allowlist` = `["matcha"]`, retention รอบแรกล้าง 1,513 คำตอบ + 55 session row ตามที่ซ้อมไว้ทุกตัวเลข, ทุก source ok ที่ contract 2.3.1/1.2.1/1.3.1/1.4.1 — **แต่เทียบ 10 คำถามต่อ report_type ได้ 8/8/8/5 ยังไม่ถึง 9/10 จึงยังไม่เปิดปุ่ม**; ต้นเหตุ (scope 13–24 เดือนไม่มีงวดยึด) แก้แล้วที่ `308acb1` — archive/RESULT_P7_GOLIVE.md, RESULT_F11.md, docs/manuals/manual_portal_runbook.md |
| **Plan 8** | 🟡 8.0 ✅ ขึ้นของจริง (2026-09-21) · **8.1 ✅ ขึ้นของจริง 2026-09-21 22:06** (`RESULT_P8_PHASE1` §12.5) · D-A/B/C ตัดสินแล้ว | 2/7 phases | suite **1161 passed / 3 skipped** | Self-service: ต่อแหล่งข้อมูลเอง (อ่าน ณ ที่อยู่) → pipeline ความรู้เดียวสองโหมด (อนุมาน + contract) → คิวให้คนตัดสินเฉพาะที่ไม่แน่ใจ → ถามตอบผ่าน web / API / Claude Desktop; BYOK + API key self-service; ทุกอย่างต่อ workspace (Tier 3 สมัครเองรอ trigger ตาม D8); gate ก่อนลูกค้าภายนอก: DPO, security review, D7, packaging — plan/PLAN_8_SELF_SERVICE_ONBOARDING.md |
| **Plan 1B-C** | ✅ DONE (ผ่าน Plan 7 Phase 6) | 100% | 38 tests | ปิด 2026-09-20 ด้วย external facade `/api/v1/mcp` — stateless Streamable HTTP + API key เดิม ผ่าน query pipeline เดิม; MCP ภายในคง stdio ไม่เปิดออก; **ไม่ทำ SSE โดยตั้งใจ** (Claude Code เลิกแนะนำ SSE, Codex ไม่มี SSE, และ legacy SSE ต้องครอบ auth สองทาง GET/POST); ยังไม่เปิดบน DB จริง — archive/RESULT_P7_PHASE6.md |

**Current verification note:** `pytest -q` on this workspace = `1092 passed, 3 skipped` (2026-09-21, `main` หลังแก้ของที่ไม่อ่านคำอธิบายข้อมูล — รันบนสำเนา DB; หลัง go-live = 1084 / 3; หลัง Phase 6 = 1035 / 3; หลัง Phase 5 = 997 / 3; ก่อน Plan 7 = 635).

### ข้อจำกัดที่ยังมี (honest assessment)
- End-to-end tests ส่วนใหญ่ mock-heavy — ยืนยัน contract แต่ไม่ยืนยัน behavior ครบ
- Scheduler มี dedicated test file แล้ว แต่ยังควรขยาย coverage เมื่อ logic ซับซ้อนขึ้น
- ยังมี static analysis warnings ใน API layer บางไฟล์ แม้ runtime/test จะผ่านแล้ว

### Re-verification Result (2026-03-21 late)

- `pytest -q` ผ่านทั้งชุด
- Vanna-related tests ผ่านใน Python 3.14
- Validation MCP tests ผ่านหลังคืน `detail` ใน confidence factor
- Telegram tests ผ่านทั้ง integration และ unit
- Scheduler tests ถูกเพิ่มและผ่านแล้ว

### Recommended hardening

1. เก็บ static analysis warnings ใน API layer
2. ขยาย coverage ของ scheduler tests หากมี logic ใหม่เพิ่ม

---

## Dependency Map

หมายเหตุ: แผนภาพด้านล่างเป็น dependency/historical snapshot ของลำดับการทำงาน ไม่ใช่สถานะ verification ล่าสุด

```
Plan 0 ✅ ──────────────────────────────────────── (DONE)
  Fix 15 Legacy Tests

Plan 1 ✅ ──────────────────────────────────────── (DONE)
  Admin Agent + Tool Calling
       │
       ├──→ Plan 1B Phase B ✅: Admin MCP Server
       │
       ├──→ Plan 2 ✅: Feedback + Query Log Enhancement
       │
       ├──→ Plan 3 🟡: Self-Learning Loop ← ยังค้าง
       │
       └──→ Plan 4 🟡: Telegram Interface ← ยังค้าง

Plan 1B Phase A 🟡 ─────────────────────────────── (80%)
  Validation Consolidation ← MCP delegate ไม่ครบ

Plan 4B ✅ ──────────────────────────────────────── (DONE)
  OpenMiniCrew Readiness

Plan 5 🟡 ──────────────────────────────────────── (40%)
  DB Separation ← CONFIG_DB_URL + session factory ยังไม่มี
       │
       └──→ Plan 6 ⬜: Multi-tenant / SaaS
```

---

## สิ่งที่ค้างทำ — จัดตามลำดับความสำคัญ

### ⚡ Priority 1: Integration Gaps (ทำให้ระบบที่สร้างแล้วทำงานจริง)

#### PLAN-REMAIN-1: Audit Service Integration
**Plan:** 3
**Effort:** 2-3 ชม.
**Files:**
- `app/tools/admin/mapping_tools.py` — เพิ่ม `audit_service.log_change()` หลัง add
- `app/tools/admin/rule_tools.py` — เพิ่ม `audit_service.log_change()` หลัง add
- `app/tools/admin/example_tools.py` — เพิ่ม `audit_service.log_change()` หลัง add

**Detail:**
```python
# ตัวอย่างที่ต้องเพิ่มใน AddMappingTool.execute() หลัง db.commit():
from app.services.audit_service import AuditService
audit = AuditService(db)
audit.log_change(
    action="INSERT", table_name="schema_semantic_mapping",
    record_id=mapping.id,
    new_value={"keyword": params["keyword"], "target_column": params["target_column"]},
    source="admin_agent",
)
```

#### PLAN-REMAIN-2: AddExampleTool Missing Dedup
**Plan:** 3
**Effort:** 1 ชม.
**File:** `app/tools/admin/example_tools.py`
**Detail:** เพิ่ม `DedupEngine.check_example_duplicate()` เหมือนที่ทำใน AddMappingTool

#### PLAN-REMAIN-3: Telegram Bot Registration
**Plan:** 4
**Effort:** 3-4 ชม.
**Files:**
- `app/config.py` — เพิ่ม TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, TELEGRAM_BOT_MODE
- `app/main.py` — เพิ่ม startup event สำหรับ bot (polling หรือ webhook)
- Optional: `app/api/v1/telegram.py` — webhook endpoint

**Detail:**
```python
# config.py
TELEGRAM_BOT_TOKEN: str = ""
TELEGRAM_WEBHOOK_SECRET: str = ""
TELEGRAM_BOT_MODE: str = "polling"  # "polling" or "webhook"

# main.py — ใน lifespan/startup:
if settings.TELEGRAM_BOT_TOKEN:
    from app.telegram.bot import NTAIBot
    bot = NTAIBot(token=settings.TELEGRAM_BOT_TOKEN)
    if settings.TELEGRAM_BOT_MODE == "polling":
        asyncio.create_task(bot.start_polling())
    else:
        app.mount("/telegram", bot.get_webhook_app())
```

### 🔧 Priority 2: Completion Items (ทำให้ plan ครบ 100%)

#### PLAN-REMAIN-4: MCP Full Delegation
**Plan:** 1B-A
**Effort:** 2-3 ชม.
**File:** `mcp_servers/nt_validation_mcp.py`
**Detail:**
- `calculate_confidence_score()` — delegate ไป `ValidationService.calculate_confidence()`
- `validate_result()` — delegate ไป `ValidationService.validate_result()`
- ปัจจุบัน logic ยังอยู่ใน MCP (ทำงานได้ แต่ duplicate code)

#### PLAN-REMAIN-5: Scheduled Jobs (Auto-Analyzer + GC)
**Plan:** 3
**Effort:** 4-6 ชม.
**Files:**
- `app/main.py` — เพิ่ม APScheduler startup
- `requirements.txt` — เพิ่ม `apscheduler>=3.10`

**Jobs ที่ต้องตั้ง:**
| Job | Schedule | Service | Method |
|-----|----------|---------|--------|
| Auto-analyze failures | ทุก 6 ชม. | `auto_analyzer.py` | `analyze_recent_failures()` |
| Config GC scan | ทุก 24 ชม. | `config_gc.py` | `run_full_scan()` |
| Apply auto-fixes (confidence ≥ 0.8) | ทุก 6 ชม. | `auto_analyzer.py` | `apply_high_confidence_fixes()` |

**Alternative:** ใช้ Celery Beat แทน APScheduler ถ้าต้องการ distributed

#### PLAN-REMAIN-6: DB Separation — Config + Session
**Plan:** 5
**Effort:** 4-6 ชม.
**Files:**
- `app/config.py` — เพิ่ม `CONFIG_DB_URL: str = "sqlite:///./config.db"`
- `app/db/session.py` — เพิ่ม `config_engine` + `ConfigSessionLocal`
- `app/services/schema_service.py` — ใช้ ConfigSessionLocal แทน default session

**Detail:**
```python
# app/db/session.py
from app.config import settings

# App DB (users, sessions, chat_history)
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Config DB (schema_contexts, mappings, rules, etc.)
config_engine = create_engine(settings.CONFIG_DB_URL)
ConfigSessionLocal = sessionmaker(bind=config_engine)
```

### 📋 Priority 3: Future Plans (ยังไม่ต้องทำ)

#### PLAN-REMAIN-7: Plan 6 — SaaS / Multi-tenant
**Status:** Design only (PLAN_6_SAAS.md exists)
**Prerequisite:** Plan 5 (DB Separation) ต้องเสร็จก่อน
**Effort:** 2-4 สัปดาห์

#### PLAN-REMAIN-8: Plan 1B Phase C — MCP SSE + Auth
**Status:** ✅ DONE 2026-09-20 — ปิดด้วย Plan 7 Phase 6 (`archive/RESULT_P7_PHASE6.md`)
**Detail:** External facade `/api/v1/mcp` — stateless Streamable HTTP + API key เดิม (`X-API-Key` ทุก request) ผ่าน query pipeline เดิม, 3 tools; Internal MCP คง stdio. **ไม่ทำ SSE โดยตั้งใจ** — client ที่ตรวจ (Claude Code, Codex) ไม่ต้องใช้ และ legacy SSE ต้องครอบ auth สองทาง. ปิดเป็นค่าเริ่มต้น (flag `mcp_external_enabled`); ก่อนเปิดกับ DB จริงดู RESULT §9 และ `docs/manuals/manual_mcp_external.md`

---

## ลำดับ Execution ที่เหลือ (แนะนำ)

| ลำดับ | Item | Effort | Prerequisite |
|-------|------|--------|-------------|
| 1 | PLAN-REMAIN-1: Audit Integration | 2-3 ชม. | — |
| 2 | PLAN-REMAIN-2: Example Dedup | 1 ชม. | — |
| 3 | PLAN-REMAIN-3: Telegram Registration | 3-4 ชม. | — |
| 4 | PLAN-REMAIN-4: MCP Full Delegation | 2-3 ชม. | — |
| 5 | PLAN-REMAIN-5: Scheduled Jobs | 4-6 ชม. | REMAIN-1 |
| 6 | PLAN-REMAIN-6: DB Config Separation | 4-6 ชม. | — |
| 7 | PLAN-REMAIN-7: Plan 6 SaaS | 2-4 สัปดาห์ | REMAIN-6 |
| 8 | PLAN-REMAIN-8: External MCP + Auth | ✅ DONE 2026-09-20 | ปิดด้วย Plan 7 Phase 6 |

**Total remaining effort: ~20-25 ชม. สำหรับ Items 1-6**

---

## แผนเดิม (ลำดับ Execution)

| ลำดับ | Plan | ประมาณเวลา | สถานะ |
|-------|------|-----------|--------|
| 1 | Plan 0: Fix Legacy Tests | 1 วัน | ✅ DONE |
| 2 | Plan 1: Admin Agent | 3-5 วัน | ✅ DONE |
| 2.5 | Plan 1B Phase A: Validation Consolidation | 1-2 วัน | 🟡 80% |
| 3 | Plan 2: Feedback Enhancement | 1-2 วัน | ✅ DONE |
| 3.5 | Plan 1B Phase B: Admin MCP Server | 1-2 วัน | ✅ DONE |
| 4 | Plan 4B: OpenMiniCrew Readiness | 2-3 วัน | ✅ DONE |
| 5 | Plan 3: Self-Learning Loop | 3-5 วัน | 🟡 65% |
| 6 | Plan 4: Telegram Interface | 3-5 วัน | 🟡 70% |
| 7 | Plan 5: DB Separation | 2-3 วัน | 🟡 40% |
| 8 | Plan 6: SaaS Architecture | 2-4 สัปดาห์ | ⬜ DESIGN |
| 8.5 | Plan 1B Phase C: External MCP + Auth | 1-2 วัน | ✅ DONE (P7-6, 2026-09-20) |

---

## เอกสารประกอบ

| ไฟล์ | เนื้อหา |
|------|---------|
| `archive/PLAN_0_FIX_LEGACY_TESTS.md` | ✅ Done |
| `archive/PLAN_1_ADMIN_AGENT.md` | ✅ Done |
| `archive/PLAN_1B_MCP_CONSOLIDATION.md` | 🟡 Phase A partial, Phase B done, Phase C done under P7-6 (facade แทนแผน SSE เดิม) |
| `archive/PLAN_2_FEEDBACK_QUERYLOG.md` | ✅ Done |
| `archive/PLAN_3_SELF_LEARNING.md` | 🟡 Dedup+Analyzer done, Audit+Scheduler pending |
| `archive/PLAN_4_TELEGRAM.md` | 🟡 Files done, registration pending |
| `archive/PLAN_4B_OPENMINICREW_READINESS.md` | ✅ Done |
| `archive/PLAN_5_DB_MIGRATION.md` | 🟡 Script done, config integration pending |
| `PLAN_6_SAAS.md` | ⬜ Design only |
| `archive/PLAN_TEST_MASTER.md` | ✅ 359 tests |
| `docs/changelogs/PLANS_0_5_IMPLEMENTATION.md` | ✅ Changelog created |
| `docs/manuals/manual_admin_agent.md` | ✅ Manual created |
| `docs/manuals/manual_api_keys.md` | ✅ Manual created |
| `docs/manuals/manual_telegram_bot.md` | ✅ Manual created |

---

## PLAN_FIX_MASTER (Code Review Remediation) — implementation แล้ว, acceptance บางข้อยังค้าง

ตรวจ source F1–F8 ซ้ำ 2026-09-21: [REVIEW_F1_F8_2026-09-21.md](REVIEW_F1_F8_2026-09-21.md) — F5 manual E2E, F6 deployment และ F7 trace/usage coverage ยังไม่ปิด; รอบนั้นรัน pytest ไม่ได้ (interpreter ที่ลองไม่มี pytest — suite รันด้วย `venv/bin/python3.14`: HEAD `7cdc7af` ผ่าน 1180) · **CI บน main แดง 2026-09-18..22 เพราะ mcp 2.x** — pin `mcp==1.26.0` แล้ว (`36d1867`) — CI หลัง pin ผ่าน collection แต่ล้ม 5 test ที่พึ่ง config DB ของเครื่อง dev; fixture แก้แล้ว (`RESULT_P8_PHASE1` §15 R2-5)

F3-A CI, F1 Correctness, F2 Hygiene/Leaks, F4 SQL Hardening, F5 Telegram, F3-B Eval Harness,
F7 Token/Observability, F6 Reports/Export, F8 Structured Output, F9 A-D (flags OFF),
F10 DataFeed pilot (values correct 14/14 value-based; strict 0/14 alias-mismatch), F11 Dashboard Embed (AI + NT-Report)

รายละเอียด: `docs/CODE_REVIEW_REPORT_2026-07-11.md` | ค้าง/decision: `plan/FIX_NOTES.md`
PENDING_BGE_M3: มี baseline เก่าแล้ว แต่ยังต้องมี A/B บน corpus/golden/config เดียวกันก่อน Go/No-Go; คง PENDING และอยู่นอก execution order (ห้าม execute จนกว่าอนุมัติ)
