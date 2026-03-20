# NT AI Assistant — Roadmap Master Plan

**Date:** 2026-03-19 (Updated)
**Project Root:** `/Users/seal/Documents/GitHub/AI/`
**OpenMiniCrew Root:** `/Users/seal/Documents/GitHub/openminicrew/`

---

## สถานะรวม (Updated 2026-03-19)

| Plan | สถานะ | % | Tests | สิ่งที่ค้าง |
|------|--------|---|-------|------------|
| **Plan 0** | ✅ DONE | 100% | 279→359 pass | — |
| **Plan 1** | ✅ DONE | 100% | 21 tests | — |
| **Plan 1B-A** | 🟡 PARTIAL | 80% | 14 tests | MCP delegate ไม่ครบ (confidence, validate_result) |
| **Plan 1B-B** | ✅ DONE | 95% | 8 tests | — |
| **Plan 2** | ✅ DONE | 95% | 14 tests | — |
| **Plan 3** | 🟡 PARTIAL | 65% | 19 tests | Audit ไม่ได้ integrate, Scheduled jobs ไม่มี, Dedup ไม่ครบ |
| **Plan 4** | 🟡 PARTIAL | 70% | 24 tests | Bot ไม่ได้ register ใน main.py, config ไม่มี |
| **Plan 4B** | ✅ DONE | 95% | 13 tests | — |
| **Plan 5** | 🟡 PARTIAL | 40% | 7 tests | CONFIG_DB_URL ไม่มี, session factory ไม่มี |
| **Plan 6** | ⬜ DESIGN | 0% | 0 | ยังไม่เริ่ม code |
| **Plan 1B-C** | ⬜ DEFERRED | 0% | 0 | ทำตอน Plan 6 |

**Tests รวม: 359 passed, 0 failed**

---

## Dependency Map

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
**Status:** Deferred (ทำตอน Plan 6)
**Detail:** เปลี่ยน MCP transport จาก stdio → SSE + API key auth

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
| 8 | PLAN-REMAIN-8: MCP SSE + Auth | 1-2 วัน | REMAIN-7 |

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
| 8.5 | Plan 1B Phase C: MCP SSE + Auth | 1-2 วัน | ⬜ DEFERRED |

---

## เอกสารประกอบ

| ไฟล์ | เนื้อหา |
|------|---------|
| `PLAN_0_FIX_LEGACY_TESTS.md` | ✅ Done |
| `PLAN_1_ADMIN_AGENT.md` | ✅ Done |
| `PLAN_1B_MCP_CONSOLIDATION.md` | 🟡 Phase A partial, Phase B done, Phase C deferred |
| `PLAN_2_FEEDBACK_QUERYLOG.md` | ✅ Done |
| `PLAN_3_SELF_LEARNING.md` | 🟡 Dedup+Analyzer done, Audit+Scheduler pending |
| `PLAN_4_TELEGRAM.md` | 🟡 Files done, registration pending |
| `PLAN_4B_OPENMINICREW_READINESS.md` | ✅ Done |
| `PLAN_5_DB_MIGRATION.md` | 🟡 Script done, config integration pending |
| `PLAN_6_SAAS.md` | ⬜ Design only |
| `PLAN_TEST_MASTER.md` | ✅ 359 tests |
| `docs/changelogs/PLANS_0_5_IMPLEMENTATION.md` | ✅ Changelog created |
| `docs/manuals/manual_admin_agent.md` | ✅ Manual created |
| `docs/manuals/manual_api_keys.md` | ✅ Manual created |
| `docs/manuals/manual_telegram_bot.md` | ✅ Manual created |
