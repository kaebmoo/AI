# Plan: Context Onboarding System

**Date:** 2026-03-18
**Status:** ✅ Phase 1-9 Implemented, LLM end-to-end pending

---

## Problem Statement

เมื่อนำเข้า view/table ใหม่ ต้องสร้าง config 7+ ตารางด้วยมือ:
- `schema_contexts` — context definition
- `schema_metadata` — column descriptions
- `schema_business_rules` — SQL correctness rules
- `golden_examples` — few-shot examples
- `schema_semantic_mapping` — keyword mappings
- `master_hierarchy` — dimension hierarchies
- `data_warnings` — quality alerts

ทำให้ช้า ผิดพลาดง่าย และพึ่งพาคนที่เข้าใจระบบ

### ตัวอย่างปัญหาที่เกิดจริง
P&L view (`v_pl_costtype_nt_mth_clean`) เป็น semi-crosstab แต่ไม่มี rule ห้าม blind SUM → AI สร้าง SQL ที่รวมรายได้+ค่าใช้จ่าย+กำไรเข้าด้วยกัน

## Solution: 5-Phase Automated Pipeline

```
Inspect (SQL) → Analyze (LLM) → Generate Config → Apply (DB) → Validate
```

### Phase 1: Data Inspection ✅
- SQL-based profiling ไม่ใช้ LLM
- ตรวจจับ semi-crosstab ด้วย cross-column analysis (mixed +/- signs)
- detect quality issues: case inconsistency, prefix changes, empty values

### Phase 2: LLM Analysis ✅
- Multi-provider: gemini, claude, matcha, OpenAI-compatible
- Structured prompt → structured JSON output
- ใช้ existing provider registry

### Phase 3: Config Generation ✅
- JSON → SQL INSERT statements สำหรับ 7 ตาราง
- Human-readable summary

### Phase 4: Apply ✅
- dry_run / apply modes
- Cache invalidation after apply

### Phase 5: Validate ✅
- ตรวจว่า config ถูก insert ครบ

## Delivery ✅

| Deliverable | Status |
|-------------|--------|
| `app/services/context_onboarding.py` | ✅ Implemented |
| `scripts/onboard_context.py` (CLI) | ✅ Implemented |
| `.claude/skills/onboard-context.md` | ✅ Implemented |
| Admin API endpoints (3) | ✅ Implemented |
| Quick Fix P&L (5 DB changes) | ✅ Applied |

## Future Enhancements

- [ ] Admin UI page for onboarding workflow
- [ ] Batch onboard multiple views
- [ ] Auto-detect new views/tables and suggest onboarding
- [ ] Compare generated config vs existing (diff mode)
- [ ] Use cheap model for inspection summary, expensive for full analysis
