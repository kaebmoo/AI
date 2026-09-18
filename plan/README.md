# plan/ — Development Plans

เอกสารวางแผนและติดตามสถานะการพัฒนา NT AI Assistant
(จัดโครงสร้างใหม่ 2026-07-12 — แผนที่เสร็จแล้วย้ายไป `archive/`)

## เอกสาร Reference (ใช้งานอยู่)

| ไฟล์ | เนื้อหา |
|------|---------|
| [PLAN_ROADMAP_MASTER.md](PLAN_ROADMAP_MASTER.md) | **เริ่มที่นี่** — สถานะรวมทุกแผน (Plans 0-6, F1-F11) + งานที่เหลือ |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | สถานะ implementation ราย area (source-verified) |
| [IMPLEMENTATION_TASKS.md](IMPLEMENTATION_TASKS.md) | Backlog งาน hardening รอบถัดไป |
| [PLAN_REMAINING_ITEMS.md](PLAN_REMAINING_ITEMS.md) | รายการงานคงเหลือหลัง Plans 0-5 (REMAIN-1..8) |
| [PLAN_FIX_MASTER.md](PLAN_FIX_MASTER.md) | Master ของรอบ code-review remediation F1-F11 (executed 2026-07-11) |
| [PLAN_F12_HISTORY_RENDER_PERSISTENCE.md](PLAN_F12_HISTORY_RENDER_PERSISTENCE.md) | F12 — persist chart/table/pivot ในประวัติการสนทนา (executed 2026-07-13, Phase A+B+C ครบ) |
| [FIX_NOTES.md](FIX_NOTES.md) | บันทึกปัญหา/ข้อค้างที่พบระหว่างทำ F-plans (มี open items) |

## แผนที่ยังไม่เริ่ม / รอตัดสินใจ

| ไฟล์ | สถานะ |
|------|--------|
| [PLAN_6_SAAS.md](PLAN_6_SAAS.md) | Design only — multi-tenant/SaaS (prerequisite Plan 5 เสร็จแล้ว) — ส่วน Model A/C/D ย้ายไปอยู่ใน Plan 7 |
| [PLAN_7_DATA_SOURCE_SERVICE.md](PLAN_7_DATA_SOURCE_SERVICE.md) | Design (2026-09-18) — zero-import: ถามข้อมูลจากแหล่งที่ผู้ใช้ลงทะเบียน (SQL / ไฟล์ผ่าน DuckDB), scope บังคับที่ SQL, API key ผูก context |
| [PLAN_PENDING_BGE_M3.md](PLAN_PENDING_BGE_M3.md) | **รออนุมัติ** — เปลี่ยน Vanna embedding เป็น BGE-M3 (ห้าม execute จนกว่าจะอนุมัติ) |

หมายเหตุ: Plan 1B-C (MCP SSE + API key auth) deferred ไปทำพร้อม Plan 6 — รายละเอียดใน `archive/PLAN_1B_MCP_CONSOLIDATION.md` และ REMAIN-8

## archive/ — แผนที่เสร็จแล้ว (historical record)

| กลุ่ม | ไฟล์ |
|-------|------|
| Plans 0-5 (เสร็จ 2026-03) | `PLAN_0_FIX_LEGACY_TESTS`, `PLAN_1_ADMIN_AGENT`, `PLAN_1B_MCP_CONSOLIDATION`, `PLAN_2_FEEDBACK_QUERYLOG`, `PLAN_3_SELF_LEARNING`, `PLAN_4_TELEGRAM`, `PLAN_4B_OPENMINICREW_READINESS`, `PLAN_5_DB_MIGRATION`, `PLAN_TEST_MASTER` |
| F-series (เสร็จ 2026-07-11) | `PLAN_F1`–`PLAN_F11`, `RESULT_F9` (มี measurement protocol รอรันเมื่อเปิด flag), `RESULT_F10` |
| Refactoring / อื่น ๆ | `NT_AI_REFACTORING_PLAN`, `PLAN_REFACTOR_ADMIN_SCHEMA_AI`, `ADMIN_SPLIT_PLAN`, `CONTEXT_ONBOARDING_WEBADMIN_PLAN`, `NT_AI_ASSISTANT_MEMORY_IMPROVEMENT_PLAN`, `PLAN_VANNA_DB_DRIVEN_DOCS`, `TASK_UPDATE_DOCS` |

> เอกสารใน archive เป็นบันทึกประวัติ ไม่สะท้อนสถานะปัจจุบัน — สถานะจริงดู `PLAN_ROADMAP_MASTER.md`
