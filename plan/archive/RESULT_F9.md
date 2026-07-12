# RESULT F9 — Agentic Latency Measurements

> กติกา: flag ใดจะถูกเปิดถาวรต้องมีแถวผลวัด (accuracy + latency ก่อน-หลัง) ในไฟล์นี้

## สถานะ (2026-07-11 — จบรอบ implement)

| Phase | Flag | สถานะโค้ด | สถานะ flag | ผลวัด |
|-------|------|-----------|-----------|-------|
| A Template answers | `template_answers_enabled` | ✅ implement + tests | **OFF** | ยังไม่วัด |
| B Parallel prep | (pure code — ไม่มี flag) | ✅ metadata load ขนานกับ SQL gen/exec | เปิดเสมอ | ดู trace: stage `exec_a*` ไม่ต้องรอ metadata อีกต่อไป |
| C Intent state | `intent_state_enabled` | ✅ implement + tests (in-memory TTL) | **OFF** (มีผลเมื่อ two_pass เปิดเท่านั้น) | ยังไม่วัด |
| D Escalation ladder | `escalation_ladder_enabled`, `escalation_tool_loop_enabled`, `query_latency_budget_s` (45) | ✅ implement + tests | **OFF** | ยังไม่วัด |
| E Heuristic router | `router_enabled` | ❌ **ไม่ได้ implement — decision-gated ต้องอนุมัติก่อน** | — | — |

## Measurement protocol (ตามแผน)

1. เลือก smoke set 20 ข้อจาก golden (mix ง่าย/ยาก/follow-up)
2. รัน `python -m scripts.eval.run_eval --limit ...` ก่อนเปิด flag → บันทึก accuracy + latency P50/P95 ต่อ stage จาก `query_trace` log
3. เปิด flag ใน admin_config → รันชุดเดิมซ้ำ → เทียบ
4. accuracy ตก = ห้ามเปิด

## ผลวัด (เติมเมื่อรันจริง)

_ยังไม่มีการเปิด flag ใด — ตารางว่างโดยตั้งใจ_
