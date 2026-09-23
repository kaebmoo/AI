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
| [PLAN_FIX_MASTER.md](PLAN_FIX_MASTER.md) | Master ของรอบ remediation — implementation แล้ว; acceptance บางข้อยังค้าง |
| [REVIEW_F1_F8_2026-09-21.md](REVIEW_F1_F8_2026-09-21.md) | ตรวจแผนเดิม F1–F8 + BGE-M3 กับโค้ดจริง แยก implementation / tests / operational gaps |
| [PLAN_F12_HISTORY_RENDER_PERSISTENCE.md](PLAN_F12_HISTORY_RENDER_PERSISTENCE.md) | F12 — persist chart/table/pivot ในประวัติการสนทนา (executed 2026-07-13, Phase A+B+C ครบ) |
| [FIX_NOTES.md](FIX_NOTES.md) | บันทึกปัญหา/ข้อค้างที่พบระหว่างทำ F-plans (มี open items) |

## แผนที่ยังไม่เริ่ม / รอตัดสินใจ

| ไฟล์ | สถานะ |
|------|--------|
| [PLAN_6_SAAS.md](PLAN_6_SAAS.md) | Design only — multi-tenant/SaaS (prerequisite Plan 5 เสร็จแล้ว) — ส่วน Model A/C/D ย้ายไปอยู่ใน Plan 7 — ⚠️ Model B (upload = import) ถูกปรับโดยหลักของเจ้าของ 2026-09-21 (ดู Plan 8 §8) |
| [PLAN_7_DATA_SOURCE_SERVICE.md](PLAN_7_DATA_SOURCE_SERVICE.md) | 🟡 **Phase 1–6 ✅ + hardening ✅ + go-live ฝั่ง AI ✅ (2026-09-20)** — ปุ่ม portal เปิดเฉพาะ `revenue`; Phase 7 (packaging Tier 2) ยังไม่เริ่ม; ผล: `archive/RESULT_P7_*.md`, `archive/RESULT_F11.md`; งานฝั่ง NT-Report: [PROMPT_NT_REPORT_P7.md](PROMPT_NT_REPORT_P7.md) |
| [PROMPT_P8_PHASE2.md](PROMPT_P8_PHASE2.md) | สั่งงาน session ใหม่: ปิดงานค้างของ 8.1 (start service, ตรวจหลัง start, push + CI) แล้วเริ่ม Phase 8.2 |
| [PROMPT_CODEX_REVIEW_2.md](PROMPT_CODEX_REVIEW_2.md) | สั่งผู้ตรวจรอบ 2: การแก้ตามผลตรวจ 9 ข้อ + pin CI (`0868447..369390c`) |
| [PLAN_8_SELF_SERVICE_ONBOARDING.md](PLAN_8_SELF_SERVICE_ONBOARDING.md) | 📝 **ร่าง 2026-09-21** — ต่อแหล่งข้อมูลเอง → เตรียมพร้อมอัตโนมัติ (pipeline เดียว สองโหมด: อนุมาน + contract) → คนตัดสินเฉพาะที่ไม่แน่ใจ; BYOK, key self-service; D-A/B/C ตัดสินแล้ว; งานแรก: [PROMPT_P8_PHASE0_1.md](PROMPT_P8_PHASE0_1.md) |
| [PLAN_PENDING_BGE_M3.md](PLAN_PENDING_BGE_M3.md) | **รออนุมัติ** — เปลี่ยน Vanna embedding เป็น BGE-M3 (ห้าม execute จนกว่าจะอนุมัติ) |

หมายเหตุ: Plan 1B-C (MCP สำหรับผู้เรียกภายนอก + API key auth) ✅ ปิดแล้ว 2026-09-20 ด้วย Plan 7 Phase 6 (facade `/api/v1/mcp` — stateless Streamable HTTP, ไม่ทำ SSE) — ผล: `archive/RESULT_P7_PHASE6.md`; แผนเดิม: `archive/PLAN_1B_MCP_CONSOLIDATION.md`, REMAIN-8

## archive/ — แผนที่เสร็จแล้ว (historical record)

| กลุ่ม | ไฟล์ |
|-------|------|
| Plans 0-5 (เสร็จ 2026-03) | `PLAN_0_FIX_LEGACY_TESTS`, `PLAN_1_ADMIN_AGENT`, `PLAN_1B_MCP_CONSOLIDATION`, `PLAN_2_FEEDBACK_QUERYLOG`, `PLAN_3_SELF_LEARNING`, `PLAN_4_TELEGRAM`, `PLAN_4B_OPENMINICREW_READINESS`, `PLAN_5_DB_MIGRATION`, `PLAN_TEST_MASTER` |
| F-series (เสร็จ 2026-07-11) | `PLAN_F1`–`PLAN_F11`, `RESULT_F9` (มี measurement protocol รอรันเมื่อเปิด flag), `RESULT_F10` |
| Refactoring / อื่น ๆ | `NT_AI_REFACTORING_PLAN`, `PLAN_REFACTOR_ADMIN_SCHEMA_AI`, `ADMIN_SPLIT_PLAN`, `CONTEXT_ONBOARDING_WEBADMIN_PLAN`, `NT_AI_ASSISTANT_MEMORY_IMPROVEMENT_PLAN`, `PLAN_VANNA_DB_DRIVEN_DOCS`, `TASK_UPDATE_DOCS` |

> เอกสารใน archive เป็นบันทึกประวัติ ไม่สะท้อนสถานะปัจจุบัน — สถานะจริงดู `PLAN_ROADMAP_MASTER.md`
