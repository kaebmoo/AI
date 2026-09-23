# PLAN FIX MASTER — Code Review Remediation (2026-07-04)

**ที่มา:** Code review เต็มรูปแบบ (อ่าน source จริง 21 ไฟล์) วันที่ 2026-07-04
**Project Root:** `/Users/seal/Documents/GitHub/AI/`
**สถานะ:** implementation ของ F1–F8 มีแล้ว; acceptance/operational checks ยังมีข้อค้าง — ตรวจ source ซ้ำ 2026-09-21 ที่ [REVIEW_F1_F8_2026-09-21.md](REVIEW_F1_F8_2026-09-21.md) ส่วน F9–F11 ดู `PLAN_ROADMAP_MASTER.md`

> Waves ด้านล่างเป็นลำดับทำงานในอดีต ไม่ใช่ backlog ให้ execute ซ้ำ; BGE-M3 ยัง PENDING และอยู่นอก waves

> **หมายเหตุ (2026-07-12):** ไฟล์แผน `PLAN_F1`–`PLAN_F11` และ `RESULT_F9`/`RESULT_F10` ที่อ้างถึงในเอกสารนี้ ถูกย้ายไป `plan/archive/` แล้วหลังงานเสร็จ

---

## หลักการทำงานสำหรับ Claude Code (บังคับทุกแผน)

1. **อ่านไฟล์จริงก่อนแก้เสมอ** — ทุกแผนมี section "READ FIRST" ต้องอ่านให้ครบก่อนเขียนโค้ด
2. ไฟล์ต่อไปนี้**ยังไม่เคยถูก review** — ถ้าแผนใดสั่งให้แตะ ต้องอ่านทั้งไฟล์ก่อน:
   `app/api/v1/query.py`, `app/services/cost_service.py`, `app/services/database_adapter.py`, `app/services/business_db.py`, `app/services/scheduler.py`, `app/services/audit_service.py`, `app/services/cache_service.py`, `mcp_servers/nt_metadata_mcp.py`, `app/providers/gemini_provider.py`, `app/providers/matcha_provider.py`, `app/services/ai/response_utils.py`, `app/services/ai/hierarchy_context.py`, `tests/`
3. หลังจบแต่ละแผน: รัน `pytest tests/unit tests/integration` ต้องผ่านทั้งหมด แล้วอัปเดต checklist ท้ายแผนนั้น
4. ห้ามแก้พฤติกรรมนอกขอบเขตแผน — ถ้าเจอบั๊กอื่นระหว่างทาง ให้จดใน `plan/FIX_NOTES.md` ไม่แก้ทันที
5. ทุก commit แยกตามแผน (1 แผน = 1 commit ขึ้นไป, ห้ามรวมข้ามแผน)

---

## Dependency Map และลำดับ Execution

```
Wave 0 (safety net ก่อนแก้อะไร)
  PLAN_F3_CI_EVAL.md — Phase A เท่านั้น (GitHub Actions CI)

Wave 1 (correctness ต่อ user — ทำก่อน)
  PLAN_F1_CORRECTNESS.md
  PLAN_F2_HYGIENE_LEAKS.md        (ทำหลัง F1 เพราะแตะ query_engine.py ทั้งคู่)

Wave 2 (security + interface)
  PLAN_F4_SQL_HARDENING.md
  PLAN_F5_TELEGRAM.md             (อิสระจาก F4 ทำขนานได้)

Wave 3 (measurement)
  PLAN_F3_CI_EVAL.md — Phase B (Eval harness)
  PLAN_F7_TOKEN_OBSERVABILITY.md  (ควรทำหลัง F3-B เพื่อมีตัววัด)

Wave 4 (feature + quality)
  PLAN_F6_REPORTS_EXPORT.md       (ต้องทำหลัง F1 และ F4)
  PLAN_F8_STRUCTURED_OUTPUT.md

Wave 5 (extensions — เพิ่ม 2026-07-04)
  PLAN_F10_DATAFEED_INTEGRATION.md  (หลัง F1; Phase C-D ต้องมี F3-B)
  PLAN_F9_AGENTIC_LATENCY.md        (Phase A,B หลัง F7 / C หลัง F8 / D หลัง F2 / E หลัง F3-B + อนุมัติ)

Wave 6 (integration ข้ามระบบ)
  PLAN_F11_DASHBOARD_EMBED.md       (หลัง F10 + F4.4; งานคร่อม repo NT-Report)

รอตัดสินใจ (ห้าม execute จนกว่าจะอนุมัติ)
  PLAN_PENDING_BGE_M3.md          (prerequisite: F3 Phase B ต้องเสร็จก่อนเพื่อมี baseline)
```

| ลำดับ | แผน | ประมาณเวลา | Prerequisite |
|-------|------|-----------|--------------|
| 1 | F3 Phase A (CI) | 0.5 วัน | ไม่มี |
| 2 | F1 Correctness | 1 วัน | F3-A |
| 3 | F2 Hygiene & Leaks | 1 วัน | F1 |
| 4 | F4 SQL Hardening | 1 วัน | F2 |
| 5 | F5 Telegram | 1 วัน | F2 |
| 6 | F3 Phase B (Eval) | 1-2 วัน | F1 |
| 7 | F7 Token & Observability | 1-2 วัน | F2 (แนะนำหลัง F3-B) |
| 8 | F6 Reports/Export | 2-3 วัน | F1, F4 |
| 9 | F8 Structured Output | 1-2 วัน | F2 |
| 10 | F10 DataFeed Integration (pilot revenue) | 2-3 วัน | F1 (+F3-B สำหรับ Phase C-D) |
| 11 | F9 Agentic Latency | 3-4 วัน (แยก phase) | F7 / F8 / F2 / F3-B ตาม phase |
| 12 | F11 Dashboard Embed (portal) | 2-3 วัน | F10, F4.4, F1 |
| — | PENDING BGE-M3 | 1-2 วัน | F3-B + **อนุมัติก่อน** |

---

## Mapping: Finding จาก review → แผน

| Finding | ความรุนแรง | แผน |
|---------|-----------|------|
| B1 Query cache ไม่รวม history → follow-up ปนข้าม conversation | สูงมาก (accuracy) | F1 |
| B2 คำเตือน truncate 1,000 แถวหายใน hybrid mode (+ heuristic เช็ค list แต่ payload เป็น dict) | สูงมาก (accuracy) | F1 |
| B3 `ChatRequest.provider` default `"gemini"` ทับ admin config | สูง | F1 |
| วันที่ปัจจุบันใน system prompt stale ได้ 6 ชม. (in-app cache) | กลาง | F1 |
| B4 Config DB session รั่ว (`deps.get_ai_service`, `QueryEngine.__init__`) | สูง | F2 |
| B8 mcp mode + Claude: message ordering ผิด + `temperature`+`top_p` พร้อมกัน | กลาง (latent) | F2 |
| B10 bare except / create_task ไม่เก็บ ref / `datetime.utcnow` / pydantic v1 dead branch / `_instances` dead code | ต่ำ-กลาง | F2 |
| SSE: client disconnect ไม่ cancel query task, event queue ไม่ drain | กลาง | F2 |
| Dedup mark ตอนเริ่ม → retry หลัง error โดนบล็อก 5 วิ | ต่ำ | F2 |
| `resolve_context_info` สร้าง SchemaService ใหม่ทุก attempt | กลาง (perf) | F2 |
| ไม่มี CI เลย (ยืนยัน `.github/` ไม่มี) | สูง (process) | F3-A |
| ไม่มี eval วัด NL→SQL accuracy | สูง (process) | F3-B |
| SQLite business DB เปิดแบบ writable, กันด้วย regex ชั้นเดียว | สูง (security) | F4 |
| B7 auto-LIMIT: syntax พังบน MSSQL + substring check ข้ามได้ + memory blowup | สูง | F4 |
| `validate_sql` duplicate สองที่ (drift risk) | กลาง | F4 |
| API key per-minute limit ไม่ enforce | กลาง | F4 |
| B5 Telegram webhook mode: sub-app startup ไม่รัน → ไม่ initialize + ไม่มี setWebhook | สูง (ถ้าใช้ webhook) | F5 |
| B6 regex admin routing จับ "เพิ่มขึ้น/ติดลบ" ผิด | สูง (UX admin) | F5 |
| B9 token accounting hybrid = hardcode 500 → cost tracking ปลอม | กลาง | F7 |
| Timing log กระจัดกระจาย ไม่มี trace ต่อ request | กลาง | F7 |
| Reports/Export ยังไม่มี (ช่องว่างหลักตาม IMPLEMENTATION_STATUS) | feature | F6 |
| Intent JSON / SQL fence พึ่ง regex parse | กลาง | F8 |
| Vanna ใช้ Chroma default embedding (MiniLM อังกฤษ) กับคำถามไทย | สูง (retrieval) | **PENDING** BGE-M3 |

## แผนส่วนขยาย (เพิ่ม 2026-07-04 — ไม่ใช่ finding จาก review แต่เป็นงานต่อยอด)

| แผน | สาระ | Gate สำคัญ |
|------|------|-----------|
| F9 Agentic Latency | template answers, parallel prep, follow-up state, escalation ladder, router | ทุก phase flag default OFF; เปิดได้ต่อเมื่อมีผลวัดใน `plan/archive/RESULT_F9.md`; Phase E ต้องอนุมัติแยก |
| F10 DataFeed Integration | import `feed_*` จาก NT-Report DataFeed + docs จาก contract + golden จาก control_totals | integrity gate 4 ชั้น (reconcile.ok, sha256, row counts, control totals) — พลาดชั้นเดียว = rollback |
| F11 Dashboard Embed | chat panel ใน viewer.html ของ portal + PB hook proxy | **Decision บันทึกแล้ว (2026-07-04): dashboard mode ตอบจาก `feed_*` ชุดเดียวกับที่ build dashboard**; สิทธิ์ตรวจที่ PB ก่อนถึง assistant เสมอ |

## Deferred decisions (ยังไม่ทำแผน — รอเจ้าของโปรเจกต์ตัดสินใจ เพราะเป็นการเพิ่ม software/dependency ใหม่)

- **Langfuse / OpenTelemetry GenAI** — observability platform เต็มรูปแบบ (self-host ได้, ตรง on-prem) — F7 ทำแบบ log-based ไปก่อน พอเพียงระยะนี้
- **sqlglot AST validation** — บังคับกฎ "ห้าม OR ข้าม hierarchy" เชิงโครงสร้างแทน prompt — dependency ใหม่ (pure Python) รอประเมินหลัง F3-B มีตัววัด
- **MCP transport ภายใน** — การแทน stdio เพื่อ scale / Celery ยังเป็น decision แยก; facade **ภายนอก** ใช้ Streamable HTTP แล้วใน Plan 7 Phase 6 (`app/api/v1/mcp_facade.py`, default OFF) ห้ามตีความว่า HTTP ยังไม่มีทั้งระบบ

---

## Definition of Done — ตรวจสถานะ 2026-09-21

- [x] F1/F2/F4 มี implementation และ regression tests ใน repo (รอบนี้ยังไม่ได้ผล pytest ใหม่)
- [x] F3-A มี CI workflow; F3-B มี harness + baseline ที่ commit แล้ว
- [x] F5 มี lifecycle และ explicit `/admin` ใน code
- [x] F6 มี export API/service/worker/cleanup ใน code
- [x] F7 ใช้ provider usage และ JSON trace ในเส้นทางหลัก
- [x] F8 ใช้ structured intent + fallback
- [x] อัปเดตสถานะเอกสารและเชื่อมหลักฐาน source
- [ ] ยืนยัน CI ล่าสุดบน main และ regression suite ของ revision ที่จะ deploy — 2026-09-22: CI แดงตั้งแต่ 09-18 เพราะ mcp 2.x (pin `36d1867`; CI run 35751495745 / 35810415450 ผ่าน collection แต่ล้ม 5 test ที่พึ่ง config DB ของเครื่อง dev — fixture แก้แล้ว `RESULT_P8_PHASE1` §15); suite ในเครื่องที่ HEAD `7cdc7af` ผ่าน 1180
- [ ] F5 manual webhook E2E ผ่าน tunnel
- [ ] F6 ยืนยันตาราง `report_exports` และ export/cleanup บน deployment (go-live เดิมพบตารางหาย) — 2026-09-22: DB จริงยังไม่มีตาราง
- [ ] F7 ยืนยัน/ปิดช่องว่าง trace early exits และ usage ของ fallback ตามรายงานตรวจ

รายละเอียดและขอบเขตหลักฐาน: [REVIEW_F1_F8_2026-09-21.md](REVIEW_F1_F8_2026-09-21.md)
