Plan 8 Phase 8.0 + 8.1 — ใช้เครื่องมือที่มีอยู่กับ `feed_*` ให้ครบ แล้ววางฐานโมเดลความรู้ (ที่มา + ความมั่นใจ + สถานะ)
repo /Users/seal/Documents/GitHub/AI, branch main — ตรวจ `git status -sb` ก่อนเริ่ม (ตอนเขียน: **ahead 22 ยังไม่ push**, HEAD `421e9bb`)
commit ใหม่ห้าม push จนกว่าจะสั่ง; ห้าม rebase / force-push; ถ้า main มี commit ใหม่จาก session อื่นให้ทำต่อบนนั้น
repo NT-Report (/Users/seal/Documents/GitHub/NT-Report) = **อ่านอย่างเดียว**

## อ่านก่อน (บังคับ)
- `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md` ทั้งไฟล์ — โดยเฉพาะ §2 (ของที่มี/ขาด), §3 (หลักการ), §5 Phase 8.0–8.1, §6 (ข้อตัดสิน), §8 (ความสัมพันธ์กับ Plan 6/7 + gate)
- `plan/archive/RESULT_F11.md` §7–§9 — คำถามจริง 12 ข้อของ portal, สาเหตุที่แก้แล้ว, และ**ปี พ.ศ. ในข้อความผิด 7/12** (§9)
- `plan/archive/RESULT_P7_GOLIVE.md` §5–§6, `plan/FIX_NOTES.md` หัวข้อล่าสุด 2 หัวข้อ (บทเรียนของ go-live)
- `docs/manuals/manual_context_onboarding.md`, `docs/DATAFEED_INTEGRATION.md`, `docs/manuals/manual_portal_runbook.md`
- code: `app/services/hierarchy_service.py` (`bootstrap_from_view`, `auto_extract`, `detect_changes`, `log_unmatched_keyword`),
  `app/services/ai/hierarchy_context.py` (`detect_hierarchy_level`), `app/services/ai/hybrid_flow.py` (ประตู `if value_matches:` ราวบรรทัด 583,
  `scope_note`, `extract_intent`), `app/services/ai/service.py` + `app/providers/base.py` (`explain_result`),
  `app/services/context_onboarding.py` (ตัวเขียน 7 ตาราง), `app/services/datafeed_knowledge.py`, `app/services/schema/prompt_builder.py`

## สถานะตอนนี้ (2026-09-21 — ตรวจแล้ว)
- pytest **1092 passed, 3 skipped** — `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` โดยชี้ `CONFIG_DB_URL` / `DATABASE_URL` /
  `DATA_SOURCE_CACHE_DIR` ไป**สำเนา** เสมอ (`venv/bin/python` = 3.10 ไม่มี pytest; แต่ server และ vanna ใช้ 3.10)
- **ของจริงมีผู้ใช้อยู่:** portal เปิดปุ่มเฉพาะ `revenue` (`ASSISTANT_CONTEXT_MAP=revenue=feed_revenue`); key ของ portal = id 4 `nt-report-portal`
  → **ห้ามเพิกถอน / หมุน / ใช้ key นี้ทดสอบ**; AI server รันที่ port 8000 (`pgrep -f "uvicorn app.main"`); Redis **หยุดอยู่** (limit รายนาที fail-open)
- `admin_config.two_pass_enabled = true` บนของจริง → **pass 1 (`extract_intent`) คือที่ที่งวด/ปีถูกเลือก** — แก้ prompt ต้องครอบคลุม pass 1 เสมอ
- ความรู้ของ `feed_*` เทียบ legacy: `schema_semantic_mapping` 0 vs 192 · `master_hierarchy` 0 vs 10 ระดับ · `master_hierarchy_values` 0 vs 3,475 ·
  `schema_business_rules` 0 vs 72 · `data_warnings` 0 vs 1 · `unmatched_keywords` ของ `feed_*` = 39 คำจากการใช้งานจริง
- legacy `revenue` ประกาศ hierarchy L2 = `PRODUCT_NAME` พร้อมคำตรวจจับ "บริการ / รายบริการ / แต่ละบริการ" — `feed_revenue` ไม่มี
- `hierarchy_service.bootstrap_from_view` อ่าน source ของ context เองผ่าน `source_resolver` (`_data_engine`) → **ใช้กับ file source ได้แล้ว แต่ไม่เคยรันกับ `feed_*`**
- `context_onboarding` ใช้ `sqlite3.connect()` → อ่าน file source **ไม่ได้** (เรื่องของ 8.2 ไม่ใช่งานนี้)
- สคริปต์วัดผลของ session ก่อนอยู่ใน scratchpad ที่หายไปแล้ว — **ชุดคำถามจริงยังไม่มีใน repo** (งานข้อ 1)

## งานตามลำดับ (commit เป็นก้อนต่อข้อ; **ทุกการเขียน DB จริงต้องได้คำสั่งจากเจ้าของต่อครั้ง + backup สดก่อน**)

### Phase 8.0
0. baseline: pytest บนสำเนา; backup `config.db` + `app.db` จริง (SQLite backup API จาก connection `mode=ro` + `PRAGMA quick_check` + SHA-256 ก่อน/หลัง)
1. **ชุดคำถามจริงที่เก็บใน repo** — ดึงคำถามทั้งหมดของ `query_audit` channel `portal` (อ่านอย่างเดียว; 12 ข้อของ `RESULT_F11` §7 + ที่เข้ามาใหม่)
   ลงไฟล์ใน `scripts/eval/` (เช่น `portal_real_questions.json`) พร้อม scope ที่ hook ส่งจริง และ oracle — ข้อที่มีใน `RESULT_F11` §7/§9 ใช้ค่านั้น;
   ข้อใหม่คำนวณจาก `control_totals` / SQL อิสระ และ**ติดป้ายว่ารอเจ้าของยืนยัน**; คำถามที่ไม่ระบุเวลาต้องบอกฐานที่ยอมรับได้ (เดือนงวดอ้างอิง หรือ YTD — ตามเกณฑ์ ⚠3 ของ `NT-Report/DataFeed/handoff/assistant_reference_202608.md`)
   + ตัวรันที่ถามด้วย body รูปเดียวกับ hook **บน server ที่ชี้สำเนา DB ด้วย key ซ้อมที่สร้างบนสำเนา** และให้คะแนน
   **ทั้งตัวเลขใน `data` และข้อความ** (ปี พ.ศ. ที่ข้อความพูดต้อง = ปี ค.ศ. ของแถว + 543; คำถามที่ไม่ระบุเวลาต้องบอกฐาน) — เอาตัวรันเข้า `scripts/eval/` ไม่ใช่ scratchpad
   → วัด baseline (ควรได้ราว 4/12 แบบเข้ม ตาม §9) · **ตัวให้คะแนนที่อ่านแต่ `data` คือเหตุที่ "10/12" ของ session ก่อนผิด**
2. **ปี พ.ศ. ในข้อความผิด** (§9) — ไล่ก่อนว่าขั้นอธิบายผล (`explain_result`) เห็นอะไรเรื่องปี (system prompt ของขั้นนี้มีบรรทัด "ปี พ.ศ. ปัจจุบัน" ไหม
   ข้อมูลที่ส่งให้มีปีรูปไหน) แล้วแก้แบบ**ไม่พึ่งการขอร้องโมเดล**: code แปลงปีของแถวเป็น พ.ศ. ให้เอง หรือตรวจข้อความหลังสร้าง — เลือกด้วยหลักฐาน;
   test ต้อง fail บน code เดิม; ต้องไม่เปลี่ยนคำตอบที่ถูกอยู่แล้ว (ข้อที่ผู้ใช้พิมพ์ปี พ.ศ. มาเอง)
3. **hierarchy ของ `feed_*`** — รัน `bootstrap_from_view` กับ 4 context **บนสำเนา** → รายงานระดับ/คอลัมน์/คำตรวจจับที่ได้ + ค่าที่ extract →
   เจ้าของตรวจ (เทียบกับของ legacy `revenue` ที่คนทำไว้) → ใส่ของจริงเมื่อได้คำสั่ง (backup สดก่อน; `source` ของแถวที่เครื่องสร้าง = `auto`)
4. **ประตู `if value_matches:`** ใน `hybrid_flow.py` — วันนี้ `detect_hierarchy_level` ทำงานเฉพาะเมื่อ value lookup เจอค่า จึงไม่ช่วยคำถามอย่าง
   "รายได้ บริการ 10 อันดับแรก"; เปิดให้ตรวจระดับชั้นได้โดยไม่ต้องมีค่า — **กระทบ legacy ด้วย** → วัด eval ของ legacy (`scripts/eval/run_eval.py`) ก่อน/หลัง
   และชุดคำถามจริง; test ที่ fail บน code เดิม
5. **`unmatched_keywords` ของ `feed_*` 39 คำ → รายการเสนอ semantic mapping** (ไฟล์รายงานให้เจ้าของตัดสิน — ยังไม่มีคอลัมน์ `status` จนกว่าจะจบ 8.1;
   ใส่เฉพาะที่เจ้าของรับ); คำที่เป็นค่าข้อมูลจริงอยู่แล้ว (เช่น `1.hard infrastructure`, `102020019`) แยกออกจากคำที่ต้องมี mapping จริง
6. วัดชุดคำถามจริง + legacy eval หลังข้อ 2–5 → **Exit 8.0: ชุดคำถามจริงถูกทั้งตัวเลขและปีในข้อความเพิ่มขึ้นอย่างมีนัยจากฐาน 4/12, legacy eval ไม่ลด**
   → `plan/archive/RESULT_P8_PHASE0.md` → **หยุดรายงาน** (ตัวเลข, commit, สถานะของจริง, ข้อค้าง) ก่อนเริ่ม 8.1

### Phase 8.1
7. สำรวจ (อ่านอย่างเดียว): ทั้ง 7 ตาราง (`schema_contexts`, `schema_metadata`, `schema_business_rules`, `golden_examples`, `schema_semantic_mapping`,
   `master_hierarchy` (+ `_values`), `data_warnings`) มี `source` / `status` / `confidence` อะไรอยู่แล้ว ค่าจริงเป็นอะไร และ**ตัวเขียนทุกตัว**
   (onboarding, `datafeed_knowledge`, hierarchy, admin API, admin tools, ตัวเรียนรู้) เขียนตารางไหนอย่างไร → ตาราง "มี / ต้องเพิ่ม" ในไฟล์ผล
8. migration แบบ idempotent (ซ้อมบนสำเนาสด แล้ว diff ของ dump ก่อน/หลัง = เฉพาะที่ประกาศ) — ของจริงเมื่อได้คำสั่ง
9. กฎเดียวของตัวเขียนทุกตัว: `declared` (contract) / `manual` (คน) **ไม่ถูกเครื่องเขียนทับ**; ขัดกัน = `proposed` เข้าคิว — **D-C: เข้าคิวทุกครั้ง
   แม้ระหว่าง contract กับ admin** และระหว่างรอ แถวที่ `active` อยู่ใช้ต่อ
10. prompt / RAG ใช้เฉพาะ `active` — ตรวจทุกจุดที่อ่าน 7 ตาราง (prompt builder, hierarchy context, semantic mapping text, golden sync ของ Vanna)
11. **Exit 8.1:** รันตัวเติมทุกตัวซ้ำสองรอบ → แถว `declared` / `manual` ไม่เปลี่ยนแม้แต่ตัวเดียว (test); prompt ของคำขอเดิมไม่เปลี่ยน
    เมื่อทุกแถวเป็น `active` (เทียบกับ commit ก่อนหน้าแบบที่ `RESULT_F11` §4.1 ทำ — โหลด module ของ commit ก่อนหน้าแล้วเทียบทีละไบต์); pytest ผ่าน; ชุดคำถามจริงไม่ลด
    → `plan/archive/RESULT_P8_PHASE1.md`; อัปเดต `PLAN_8` (หัวสถานะ + §5), ROADMAP, FIX_NOTES, docs ที่เกี่ยว, CLAUDE.md + AGENTS.md (sync กัน, gitignored); แล้วหยุด
    (ถ้า context ใกล้เต็มก่อนถึงข้อนี้ ให้หยุดแล้วเขียน prompt ส่งต่อ session ถัดไป)

## ข้อค้างที่รอเจ้าของตัดสิน (ไม่บล็อก 8.0 / 8.1 — ถามเมื่อถึงจุดที่ต้องใช้)
- **OpenAPI เต็มเปิดโดยไม่ต้อง login** (`/api/v1/openapi.json`, `/api/v1/docs` — 90 จาก 115 endpoint เป็นของ admin): ปิด / ต้อง auth ตอนนี้ หรือรอ 8.5
- Redis (หยุดอยู่ → limit รายนาที fail-open) · push commit ที่ค้าง
- D-D (BYOK ค่าเริ่มต้น), D-E (เกณฑ์ "พร้อมใช้"), D-F (REST เป็น source) — ของ 8.3 / 8.5 / 8.4 ไม่ใช่งานนี้
- oracle ของคำถามจริงข้อใหม่ที่คำนวณเอง (ข้อ 1) — ส่งให้เจ้าของข้อมูล (NT-Report) ยืนยัน

## กติกา
- **ของจริงมีผู้ใช้:** ทุกอย่างทำบนสำเนาก่อน; เขียน DB จริง / restart server จริง / sync brain จริง ต้องได้คำสั่งต่อครั้ง + backup สดที่ตรวจแล้ว + บอกวิธีถอยกลับ
- พฤติกรรมของช่องทางเดิม (chat / telegram / legacy context) เปลี่ยนได้เฉพาะที่วัดแล้วไม่ลด; ทุกการแก้มี test ที่ fail บน code เดิม
- **ห้ามใส่ชื่อคอลัมน์หรือค่าธุรกิจตายตัวใน prompt path** — อ่านจาก metadata / contract / DB เสมอ (บทเรียน `RESULT_F11` §8); ค่าเริ่มต้นเท่านั้นที่ hardcode ได้
- ห้ามผ่อน: scope / allowlist / `request_pinned` / `llm_data_policy` / `check_select` / audit; การอนุมานที่ส่งค่าจากแถวให้ LLM ต้องเคารพ `restricted()`
- ตัวให้คะแนนต้อง**อ่านสิ่งที่ผู้ใช้เห็น** (ข้อความ + ปี + ฐาน) ไม่ใช่แค่ตัวเลขที่ระบบคำนวณ; ยิงซ้ำแล้วได้เหมือนเดิมอาจเป็น **cache hit** (30 นาที ผูก scope + key) ไม่ใช่ความนิ่ง
- หลังแก้ code: restart server (query cache ไม่ผูกเวอร์ชันของ code) · หลังเพิ่ม golden: sync brain ด้วย `venv/bin/python` (3.10 — vanna ไม่อยู่ใน 3.14) แล้ว restart ·
  knowledge ของ `feed_*` re-sync เมื่อ `schema_version` เปลี่ยน หรือล้าง `data_sources.knowledge_sha`
- test ที่สร้าง provider จริงต้อง patch `_build_provider_kwargs` (เครื่องนี้มี key จริง); app ห้าม import จาก `scripts/`;
  ruff มี error เดิมหลายไฟล์ที่ไม่ใช่ของเรา (เช่น `import uuid` ที่ไม่ได้ใช้ใน `query_engine.py`) — ตรวจเฉพาะไฟล์ที่แตะ
- code ที่อ้างหมวดของเอกสาร: **หมวดนั้นต้องมีจริงก่อน commit** (session ก่อนอ้าง §8 ที่ยังไม่ได้เขียนอยู่หนึ่งวัน)
- secret: raw key, provider key, เนื้อหา `.env` ห้ามอยู่ใน commit / log / RESULT / ข้อความสรุป; ตรวจ `git diff --cached` ก่อน commit ทุกครั้ง
- ข้อความ commit ห้ามมีชื่อโมเดลหรือ emoji; ลงท้าย `Co-Authored-By: Claude <noreply@anthropic.com>`
- ถ้าเจอสิ่งที่ขัดกับแผน ให้หยุดและรายงานพร้อมทางเลือก ไม่ตัดสินใจเองเงียบ ๆ
- จบแต่ละ phase สรุป: ทำอะไร, ตัวเลข exit criteria, สถานะของจริง (อะไรเปลี่ยน / ยัง), commit list, ข้อค้างที่ต้องให้ผมตัดสิน
