# NT AI Assistant — Documentation

AI Query Assistant สำหรับ NT (National Telecom) — แปลงคำถามภาษาไทยเป็น SQL
ผ่าน Claude / Gemini / Matcha (NT Gateway).

> สำหรับภาพรวมโปรเจกต์และ schema reference ดู [`../CLAUDE.md`](../CLAUDE.md)

## Start here

| Doc | เนื้อหา |
|-----|---------|
| [CAPABILITIES.md](CAPABILITIES.md) | ภาพรวมความสามารถทั้งหมดของระบบ |
| [ai_workflow.md](ai_workflow.md) | AI communication workflow — คำถามภาษาไทย → SQL → คำตอบ |
| [rag_explanation.md](rag_explanation.md) | RAG (Retrieval-Augmented Generation) ทำงานอย่างไร |

## Data & Schema

| Doc | เนื้อหา |
|-----|---------|
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | พจนานุกรมข้อมูล — column, type, ความหมาย |
| [DATABASE_TABLES_GUIDE.md](DATABASE_TABLES_GUIDE.md) | คู่มือตารางใน 3-DB architecture |
| [INTERNAL_SCHEMA.md](INTERNAL_SCHEMA.md) | Internal schema reference (config tables) |
| [SEMANTIC_MAPPING_GUIDE.md](SEMANTIC_MAPPING_GUIDE.md) | Semantic mapping — keyword → column/value |

## AI Providers

| Doc | เนื้อหา |
|-----|---------|
| [PROVIDER_MODEL_MANAGEMENT.md](PROVIDER_MODEL_MANAGEMENT.md) | จัดการ provider/model (Claude, Gemini, Matcha) |
| [ADDING_NEW_PROVIDER.md](ADDING_NEW_PROVIDER.md) | วิธีเพิ่ม AI provider ใหม่ |

## Admin

| Doc | เนื้อหา |
|-----|---------|
| [ADMIN_CONFIGURATION.md](ADMIN_CONFIGURATION.md) | ระบบ config แบบ DB-driven (3-tier fallback) |
| [ADMIN_MASTER_DATA_GUIDE.md](ADMIN_MASTER_DATA_GUIDE.md) | จัดการ master data & hierarchy |

## Manuals (คู่มือผู้ใช้)

| Doc | เนื้อหา |
|-----|---------|
| [manual_web_admin_comprehensive.md](manuals/manual_web_admin_comprehensive.md) | คู่มือระบบแอดมิน (ฉบับสมบูรณ์) |
| [manual_admin_agent.md](manuals/manual_admin_agent.md) | Admin Agent — สั่งงาน config ด้วยภาษาธรรมชาติ |
| [manual_context_management.md](manuals/manual_context_management.md) | การจัดการบริบทข้อมูล (Context Management) |
| [manual_context_onboarding.md](manuals/manual_context_onboarding.md) | Context Onboarding — เพิ่ม view ใหม่อัตโนมัติ |
| [manual_api_keys.md](manuals/manual_api_keys.md) | การจัดการ API Keys |
| [manual_telegram_bot.md](manuals/manual_telegram_bot.md) | Telegram Bot |

## Vanna (RAG / Vector DB)

| Doc | เนื้อหา |
|-----|---------|
| [VANNA_IMPROVEMENTS_QUICKSTART.md](vanna/VANNA_IMPROVEMENTS_QUICKSTART.md) | Quick start |
| [VANNA_CONFIG_UPDATE.md](vanna/VANNA_CONFIG_UPDATE.md) | สรุปการอัปเดต config |
| [VANNA_IMPLEMENTATION_REVIEW.md](vanna/VANNA_IMPLEMENTATION_REVIEW.md) | รีวิวการ implement Vanna + vector DB |
| [VANNA_VERIFICATION_REPORT.md](vanna/VANNA_VERIFICATION_REPORT.md) | รายงานตรวจสอบ |

## Changelogs

| Doc | เนื้อหา |
|-----|---------|
| [DB_SEPARATION_3DB.md](changelogs/DB_SEPARATION_3DB.md) | แยกเป็น 3-database architecture |
| [DB_DRIVEN_HARDCODE_REMOVAL.md](changelogs/DB_DRIVEN_HARDCODE_REMOVAL.md) | ลบ hardcode → DB-driven (2026-03-08) |
| [MASTER_DATA_HIERARCHY.md](changelogs/MASTER_DATA_HIERARCHY.md) | Master data & DB-driven hierarchy |
| [CONTEXT_ONBOARDING_SYSTEM.md](changelogs/CONTEXT_ONBOARDING_SYSTEM.md) | Context onboarding + P&L quick fix |
| [ADMIN_WORKSPACE_REFRESH_2026_03_23.md](changelogs/ADMIN_WORKSPACE_REFRESH_2026_03_23.md) | Admin workspace refresh + Vanna ops |
| [CACHING_AND_CONTEXT_IMPROVEMENTS.md](changelogs/CACHING_AND_CONTEXT_IMPROVEMENTS.md) | Caching & context improvements |
| [WEB_VISUALIZATION_ECHARTS.md](changelogs/WEB_VISUALIZATION_ECHARTS.md) | WebDataRocks + ECharts |
| [CHART_TABLE_ENHANCEMENTS.md](changelogs/CHART_TABLE_ENHANCEMENTS.md) | Chart & table enhancements |
| [TOOLTIP_IMPROVEMENTS.md](changelogs/TOOLTIP_IMPROVEMENTS.md) | Tooltip สำหรับข้อความยาว |
| [BUGFIX_CSV_EXPAND.md](changelogs/BUGFIX_CSV_EXPAND.md) | Bug fix: CSV export & expand button |
| [REFACTORING_PHASE_1_2_3_5.md](changelogs/REFACTORING_PHASE_1_2_3_5.md) | Refactoring phases 1-2-3-5 |
| [PLANS_0_5_IMPLEMENTATION.md](changelogs/PLANS_0_5_IMPLEMENTATION.md) | Plans 0-5 implementation |
| [PLANS_0_5_COMPLETION.md](changelogs/PLANS_0_5_COMPLETION.md) | Plans 0-5 completion |

## Planning (historical design docs)

> เอกสารวางแผน/ออกแบบ — เก็บไว้อ้างอิงประวัติการตัดสินใจ ไม่ใช่สถานะปัจจุบัน

- [nt-revenue-assistant-plan.md](planning/nt-revenue-assistant-plan.md) · [v2](planning/nt-revenue-assistant-plan-v2.md) — production implementation plan
- [summary_context.md](planning/summary_context.md) — implementation summary
- [mcp_server_plan.md](planning/mcp_server_plan.md) · [v2](planning/mcp_server_plan_v2.md) — MCP server plan
- [Admin-UI-and-Schema-Analyzer-Plan.md](planning/Admin-UI-and-Schema-Analyzer-Plan.md) — Admin UI + schema analyzer
- [API_KEY_MANAGEMENT_PLAN.md](planning/API_KEY_MANAGEMENT_PLAN.md) — API key management
- [CONTEXT_ONBOARDING_PLAN.md](planning/CONTEXT_ONBOARDING_PLAN.md) — context onboarding
- [MASTER_DATA_PLAN.md](planning/MASTER_DATA_PLAN.md) — master data & hierarchy
- [Metadata-Driven-Plan.md](planning/Metadata-Driven-Plan.md) — metadata-driven approach
- [Matcha_Model_Improve_Plan.md](planning/Matcha_Model_Improve_Plan.md) — Matcha model improvements
- [CoT.md](planning/CoT.md) — chain-of-thought notes
