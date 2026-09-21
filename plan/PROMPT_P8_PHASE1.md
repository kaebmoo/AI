Plan 8 Phase 8.1 — โมเดลความรู้: ที่มา + ความมั่นใจ + สถานะ ครบทั้ง 7 ตาราง
repo /Users/seal/Documents/GitHub/AI, branch main — ตรวจ `git status -sb` ก่อนเริ่มแล้วทำต่อบน HEAD ล่าสุดของ main
(ตอนส่งมอบ 2026-09-21: **ahead 8 ยังไม่ push** — ห้าม push จนกว่าจะสั่ง; ห้าม rebase / force-push; มี commit ใหม่จาก session อื่นให้ทำต่อบนนั้น)
repo NT-Report (/Users/seal/Documents/GitHub/NT-Report) = **อ่านอย่างเดียว**

## อ่านก่อน (บังคับ)
- `plan/archive/RESULT_P8_PHASE0.md` **ทั้งไฟล์** — ผลของ 8.0, ข้อตัดสินของเจ้าของ (§1.3, §8), ที่เจอสำหรับ 8.1 (§3.4), ข้อสังเกต (§9), สถานะของจริง (§7)
- `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md` §3 (หลักการ — โดยเฉพาะข้อ 2–4), §5 8.1, §6 (D-C)
- `plan/PROMPT_P8_PHASE0_1.md` หัวข้อ Phase 8.1 (ข้อ 7–11) และ **กติกา** — ยังใช้ทั้งหมด; ไฟล์นี้เพิ่มสิ่งที่เปลี่ยนหลัง 8.0
- ตัวเขียน 7 ตาราง (สำรวจครบก่อนแก้ — `memory/feedback_db_migration.md`):
  app: `app/services/context_onboarding.py`, `datafeed_knowledge.py`, `source_registration.py`, `hierarchy_service.py` (+ subprocess `scripts/extract_hierarchy.py`),
  `app/services/schema/context_store.py`, `schema/view_manager.py`, admin API `app/api/v1/admin/{mappings,rules,golden_examples,warnings,schema,workspaces}.py`,
  admin tools `app/tools/admin/{mapping,rule,example}_tools.py`, ตัวเรียนรู้ `app/services/scheduler.py` (`_job_auto_analyze` → `_apply_high_confidence_fixes` **เขียน `schema_semantic_mapping` เองทุกรอบ**),
  `auto_analyzer.py`, `config_gc.py`, `dedup_engine.py`, `feedback_service.py`, `warning_detector.py` · scripts: `grep` ตัวที่เขียน 7 ตารางใน `scripts/` (มี ~16 ตัว — แยกว่าตัวไหนยังใช้)
- ตัวอ่าน: `app/services/schema/prompt_builder.py`, `schema/service.py` (`build_hierarchy_rule_text`, semantic mappings, business rules),
  `app/services/ai/hierarchy_context.py` (`load_hierarchies_from_db`, `detect_level`, `format_level_note`), golden sync ของ Vanna

## สถานะตอนนี้ (2026-09-21 — ตรวจแล้ว)
- **8.0 ขึ้นของจริงแล้ว 14:51** (เจ้าของ restart เอง): ปี พ.ศ. ตรวจใน code (`thai_year.py`), ระดับชั้นที่คำถามพูดถึงถึง pass 1 (`format_level_note`),
  hierarchy `feed_revenue` 3 ระดับ `source='auto'` (ค่า 8 / 32 / 175) — คำถามจริงแรกหลัง restart (#281) ผ่านครบ
- pytest **1110 passed, 3 skipped** — `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` โดยชี้ `CONFIG_DB_URL` / `DATABASE_URL` / `DATA_SOURCE_CACHE_DIR` ไป**สำเนา**
- **ตัวเลขที่ต้องไม่ลด (baseline ของ 8.1):** คำถามจริง P01–P12 **8/12**, ทั้ง 15 ข้อ **10/15** (`scripts/eval/run_portal_questions.py`) ·
  legacy eval **8/37** (`python -m scripts.eval.run_eval --legacy`, 12 golden_broken) · โมเดลผันผวนราย ±1 ข้อ — ตัดสินจากสองรอบขึ้นไป
- `source` ที่มีอยู่แล้ว: `master_hierarchy` / `_values` (`auto` / `manual`) — ตารางอื่นยังต้องสำรวจ (ข้อ 7)
- ของจริงมีผู้ใช้: portal เปิดเฉพาะ `revenue` · key ของ portal = id 4 **ห้ามเพิกถอน / หมุน / ใช้ทดสอบ** · AI server port 8000 · Redis รัน · `two_pass_enabled = true`

## ที่ 8.0 เจอและเป็นงานของ 8.1
1. `hierarchy_service.bootstrap_from_view` ทับ `level_columns` / `detection_keywords` ด้วย `ON CONFLICT DO UPDATE` **โดยไม่ดู `source`** — ขัดหลัก "คนชนะเครื่อง"
2. `_job_auto_analyze` เขียน semantic mapping เอง = ตัวเรียนรู้ที่ต้องเข้ากฎเดียว (ผลของมันควรเป็น `proposed` ไม่ใช่ `active`)
3. **ค่าคงที่ใน prompt path** (ข้อ 10): `prompt_builder._build_thai_prompt` บรรทัด ~365 "ใช้ `year` และ `month` สำหรับ filter เวลา / `CAST(month AS INTEGER)`" + ฉบับอังกฤษ ~415 —
   ขัด `build_date_instructions` ของ `feed_ebt` / `feed_expense` / `pl_costtype` (ชนิดเดียวกับ `RESULT_F11` §8) · ตัวอย่าง `"เดือนมกราคม 2568"` ใน `chart_postprocessor.build_explain_prompt`
   — แก้ต้องวัดคำถามจริง + legacy ก่อน/หลัง และ test ที่ fail บน code เดิม
4. legacy `revenue` / `pl_costtype` / `revenue_org` / `expense_org` มี "กลุ่ม" เดี่ยว ๆ เป็นคำตรวจจับ (แถว `manual`) — ขัดข้อตัดสินของเจ้าของ แต่เป็นของคน: **เสนอ ไม่แก้เอง**

## ข้อตัดสินของเจ้าของที่ต้องเคารพ (2026-09-21)
- **คำกำกวม** ("กลุ่ม", `cctv`, `internet`) ชี้ได้หลายชั้น ขึ้นกับบริบท/การเจาะจง → ห้าม semantic mapping ตายตัวไปชั้นเดียว; ห้าม "กลุ่ม" เดี่ยว ๆ เป็นคำตรวจจับของชั้นใด
- **BG8** (8.1 ผลตอบแทนทางการเงิน + 8.2 รายได้อื่น): ภาพรวมต้องมี · มุมกลุ่มธุรกิจไม่นับเป็น operation หลัก · **รายเดือนรวมเป็นสะสมไม่ได้** (รายได้อื่น / ค่าใช้จ่ายอื่น) — ใช้ YTD แบบ net
- **ของจริง: เจ้าของ restart server เอง** — ส่งคำสั่งที่ทดสอบกับสำเนาแล้ว + backup + วิธีถอยกลับ (แบบ `RESULT_P8_PHASE0` §3.3 / §7); เขียน DB จริงต้องได้คำสั่งต่อครั้ง

## งาน — Phase 8.1 (ข้อ 7–11 ของ `PROMPT_P8_PHASE0_1.md`; commit เป็นก้อนต่อข้อ)
7. สำรวจ (อ่านอย่างเดียว) ทั้ง 7 ตาราง: มี `source` / `status` / `confidence` อะไรอยู่ ค่าจริงเป็นอะไร (นับจาก `config.db` แบบ `mode=ro`) และ**ตัวเขียนทุกตัว**ข้างบนเขียนอะไรอย่างไร
   → ตาราง "มี / ต้องเพิ่ม" ในไฟล์ผล — **หยุดถามก่อนข้อ 8 ถ้าชุดค่าที่จะใช้ต่างจาก PLAN_8 §3 ข้อ 2** (`declared` / `manual` / `inferred` / `learned` + `active` / `proposed` / `rejected`)
8. migration แบบ idempotent — ซ้อมบนสำเนาสด แล้ว diff ของ dump ก่อน/หลัง = เฉพาะที่ประกาศ; ของจริงเมื่อได้คำสั่ง (ส่งคำสั่งให้เจ้าของรันเอง)
9. กฎเดียวของตัวเขียนทุกตัว: `declared` / `manual` **ไม่ถูกเครื่องเขียนทับ**; ขัดกัน = `proposed` เข้าคิว — **D-C: เข้าคิวทุกครั้งแม้ระหว่าง contract กับ admin**; ระหว่างรอ แถว `active` ใช้ต่อ
10. prompt / RAG ใช้เฉพาะ `active` — ทุกจุดที่อ่าน 7 ตาราง (prompt builder, hierarchy context, semantic mapping text, golden sync ของ Vanna) + ข้อ 3 ของหัวข้อก่อน
11. **Exit 8.1:** รันตัวเติมทุกตัวซ้ำสองรอบ → แถว `declared` / `manual` ไม่เปลี่ยนแม้แต่ตัวเดียว (test) · prompt ของคำขอเดิมเท่าเดิมทุกไบต์เมื่อทุกแถว `active`
    (โหลด module ของ commit ก่อนหน้าเป็นอีกโมดูลแล้วเทียบ — วิธีใน `RESULT_P8_PHASE0` §4) · pytest ผ่าน · คำถามจริงไม่ต่ำกว่า 8/12 · legacy ไม่ต่ำกว่า 8/37
    → `plan/archive/RESULT_P8_PHASE1.md`; อัปเดต `PLAN_8` (หัวสถานะ + §5), ROADMAP, FIX_NOTES (บทเรียนของ 8.0 ยังไม่ได้ลง — ใส่ด้วย), docs ที่เกี่ยว,
    CLAUDE.md + AGENTS.md (sync กัน, gitignored) → **หยุดรายงาน** (ถ้า context ใกล้เต็มก่อนถึงข้อนี้ ให้หยุดแล้วเขียน prompt ส่งต่อ)

## วิธีวัดที่ไม่แตะของจริง (ของใน scratchpad ของ session ก่อนหายแล้ว — สร้างใหม่ตามนี้)
```bash
# backup สด (ใช้เป็นต้นทางของสำเนาด้วย)
D=~/nt-ai-backups/p8-1-$(date +%Y%m%d-%H%M%S) && mkdir -p $D && sqlite3 "file:config.db?mode=ro" ".backup $D/config.db" && sqlite3 "file:app.db?mode=ro" ".backup $D/app.db" && sqlite3 $D/config.db "PRAGMA quick_check"
# server ซ้อม port 8001 บนสำเนา (P = โฟลเดอร์ใน scratchpad ที่มี config.db / app.db / chroma_db สำเนา)
CONFIG_DB_URL=sqlite:///$P/config.db DATABASE_URL=sqlite:///$P/app.db DATA_SOURCE_CACHE_DIR=$P/cache VANNA_CHROMA_PATH=$P/chroma_db \
  REDIS_URL=redis://localhost:6379/1 TELEGRAM_BOT_TOKEN= EMAIL_HOST= venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```
- key ซ้อม: `APIKeyService(db).create_key(user_id=37, name="p8-practice-copy", scopes="query", rate_limit_per_minute=1000, rate_limit_per_day=100000,
  workspace_id=ws, allowed_contexts=allowed)` กับ `resolve_key_binding("nt-report", None)` — **รันด้วย `DATABASE_URL` / `CONFIG_DB_URL` ของสำเนาเท่านั้น**, raw key เก็บในไฟล์ scratchpad `chmod 600`
- สำเนาต้องมี hierarchy `feed_revenue` เหมือนของจริง (มาจาก backup ของจริงหลัง 14:51 แล้ว — ตรวจ `master_hierarchy` ก่อนวัด)
- `PORTAL_EVAL_API_KEY=<key ซ้อม> venv/bin/python3.14 -m scripts.eval.run_portal_questions --base-url http://localhost:8001` (ตัวรันปฏิเสธ port 8000 เอง)
- restart server ซ้อมก่อนทุกรอบ (query cache) · ให้คะแนนใหม่โดยไม่ยิง: `--score eval_results/portal_real_<ts>.json`
- legacy eval: รัน in-process ด้วย env ชุดเดียวกัน (สำเนาอีกชุด) `venv/bin/python -m scripts.eval.run_eval --legacy` (~10 นาที)

## ข้อค้างที่รอเจ้าของ (ไม่บล็อก 8.1 — ถามเมื่อถึงจุดที่ต้องใช้)
- ตัด BG8 ออกจากการจัดอันดับ "บริการ / กลุ่มธุรกิจ" เป็นค่าเริ่มต้นไหม — ถ้าใช่ ควรเป็นกฎใน contract ของ NT-Report
- ตัดย่อหน้า "ข้อเสนอแนะสำหรับการนำเสนอข้อมูล / แผนภูมิ…" ที่โมเดลเขียนท้ายคำตอบ (prompt ห้ามอยู่แล้วแต่ไม่ฟัง) ใน code
- P12 "ค่าใช้จ่ายมีไหม" ตอบด้วยรายได้เมื่อมี hierarchy (0/5) — ต้องเป็นกฎของ context
- retention ของคำตอบใน chat (ข้อเสนอ: คงการหมดอายุ + ปุ่ม "ดูคำตอบใหม่" ที่รัน SQL เดิมผ่านด่านเดิม) — รอตัดสิน
- oracle ที่คำนวณเอง (P03/P08–P11 รายแถว, P13–P15) → NT-Report ยืนยัน · `-ER` ของ EXP4 · push commit

## กติกาเพิ่มจาก `PROMPT_P8_PHASE0_1.md`
- ทุกการแก้ที่กระทบ prompt: วัดคำถามจริง **และ** legacy ก่อน/หลัง — 8.0 เจอ regression ที่ test ไม่จับ (legacy 8/37 → 5/37) จากการวัดนี้เท่านั้น
- แถวที่ 8.0 ใส่ในของจริง (hierarchy `feed_revenue`, `source='auto'`) — เมื่อ migrate ให้เป็นสถานะที่ตรงความจริง (เครื่องเสนอ + เจ้าของรับ) และบอกในรายงานว่าเลือกค่าอะไรเพราะอะไร
- ข้อความ commit ห้ามมีชื่อโมเดลหรือ emoji; บรรทัดแรก = subject แล้วเว้นบรรทัดก่อน body; ลงท้าย `Co-Authored-By: Claude <noreply@anthropic.com>`
