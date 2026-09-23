# PROMPT — session ใหม่: ปิดงานค้างของ 8.1 แล้วเริ่ม Phase 8.2

repo `/Users/seal/Documents/GitHub/AI` (branch `main`) · เขียน 2026-09-23 หลังจบ 8.1 + รอบแก้ตามผลตรวจของ Codex

## อ่านก่อน (บังคับ)
- `plan/archive/RESULT_P8_PHASE1.md` **ทั้งไฟล์** — โดยเฉพาะ §12 (ของจริง + วิธีถอย), §12.5 (ขึ้นของจริงแล้ว + ที่ยังไม่ได้ตรวจ), §13 (ค้าง), §14 (ผลตรวจ 9 ข้อ + ที่แก้)
- `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md` §3 (หลักการ), §5 **8.2**, §6 (D-A/B/C)
- `plan/PROMPT_P8_PHASE1.md` — **กติกาทั้งหมดในไฟล์นั้นยังใช้อยู่**
- `plan/REVIEW_F1_F8_2026-09-21.md` — ข้อค้างของ F1–F8 + หัวข้อ "ตรวจต่อ 2026-09-22" (CI, pytest, `report_exports`)
- `CLAUDE.md` หัวข้อ **Plan 8.1** — กฎของตัวเขียน/ตัวอ่านความรู้ที่ code ใหม่ต้องทำตาม
- code ที่ 8.2 จะแตะ: `app/services/context_onboarding.py`, `data_sources.py` (`source_resolver`), `datafeed_knowledge.py`,
  `hierarchy_service.bootstrap_from_view`, `provenance.py`

## สถานะ (ตรวจซ้ำเองก่อนเชื่อ — ข้อมูลนี้ของ 2026-09-22 ดึก)
- `main` = `369390c` · remote = `7cdc7af` → **2 commit ยังไม่ push** (`36d1867` pin mcp, `369390c` เอกสาร F1–F8)
- ของจริง: `config.db` migrate ของ 8.1 แล้ว · server ที่เคยรันคือ code `1857dbe` · **ตอนเขียน prompt ไม่มี service ใดรัน**
  (เครื่อง reboot) — ตรวจ `lsof -nP -iTCP:8000 -sTCP:LISTEN`, 8090 (PocketBase), 8081 (frontend) ก่อนสรุปอะไรทั้งสิ้น
- start ครั้งถัดไป = ขึ้นทุก commit ใน `git log 1857dbe..HEAD` (แก้ 9 ข้อของ Codex + pivot + pin) — **ไม่ต้อง migrate**
  (ด่านเริ่ม server ผ่านบน schema ของจริงแล้ว) · ถอยกลับ: `git checkout 1857dbe -- app mcp_servers scripts` + restart
- CI บน GitHub แดงทุก push ตั้งแต่ 2026-09-18 เพราะ `mcp` 2.x → pin `mcp==1.26.0` แล้ว แต่ยังไม่ push จึง**ยังไม่รู้ว่าเขียว**
- pytest: `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` บน**สำเนา** DB — HEAD ผ่าน **1180, skipped 3**

## งาน — ตามลำดับ
0. **สำรวจของจริงก่อน (อ่านอย่างเดียว):** PID ของ 8000 / 8090 / 8081, `query_audit` แถวล่าสุด, `git log <commit ที่รันอยู่>..HEAD`
1. **ขึ้นของจริง:** ส่งคำสั่ง start ให้เจ้าของรันเอง (AI server, PocketBase, frontend) — อย่าไป start ของจริงเอง
2. **ตรวจที่ §12.5 ค้างไว้** (ต้องมี service รันแล้ว): หน้า admin 6 ตาราง + hierarchy, chat ของ context legacy, Telegram,
   ปุ่มแก้ SQL / thumbs-up ของ admin → แล้ว**ยืนยันจาก DB**: แถวที่คนแก้ = `manual` / `active`, ข้อเสนอของตัวเรียนรู้ =
   `learned` / `proposed` / `is_active = 0`, `knowledge_proposals` มีแถวตามที่คาด, job GC ไม่มี `no such column`
3. **push เมื่อเจ้าของสั่ง** แล้วดู `gh run list --branch main` — ถ้ายังแดง ไล่จาก log จริงของ run (อย่าเดา) แล้วรายงาน
4. **Phase 8.2** ตาม `PLAN_8` §5:
   - `context_onboarding` อ่านผ่าน `source_resolver` แทน `sqlite3.connect()` (แบบที่ `hierarchy_service` ทำแล้ว)
   - ลำดับเดียว: เชื่อมต่อ → profile → ความรู้ที่ประกาศ (ถ้ามี contract) → อนุมานส่วนที่เหลือด้วย LLM → hierarchy →
     golden → รายงานความพร้อม · contract = input ที่มีสิทธิ์สูงสุด ไม่ใช่ทางแยก (`datafeed_knowledge` = ตัวอ่าน contract)
   - แก้ของที่ onboarding ล้มอยู่วันนี้: hierarchy / warnings ล้มเพราะ NOT NULL, golden ซ้ำ (RESULT §7.3)
   - **Exit 8.2:** onboard `feed_revenue` สองครั้งบน source เดียวกัน — ครั้งแรกใช้ contract, ครั้งที่สองปิดการอ่าน contract
     (อนุมานล้วน) → ได้ครบ 7 ตารางทั้งคู่, วัดด้วยชุดคำถามจริงชุดเดียวกัน, รายงาน**ช่องว่างของสองโหมด**เป็นตัวเลข
5. **ข้อค้างที่หยิบได้ระหว่างทาง** (RESULT §13): กฎข้อ 5 กับ P12 · YTD ถูก SUM ข้ามงวด (115,090 vs 26,036) ·
   ตัวอย่างปีใน prompt อธิบายผล · ของทดสอบในของจริง (golden 41–50, กฎ `TEST_001`) · `revenue_org.parent_column = "GROUP"` ·
   `extract_hierarchy.py` ล้มที่ `revenue_gl` · `RunOnboarding` `dry_run=False` · `import_master_data.py` ชี้ business DB ·
   admin ลบจริง 7 ตาราง
6. **F1–F8 ที่ยังค้าง** (REVIEW_F1_F8): F5 manual webhook E2E · F6 ตาราง `report_exports` ยังไม่มีบน DB จริง ·
   F7 trace ของ early exit + usage ของ fallback

## กติกา (ย้ำ — ผิดข้อไหนถือว่างานใช้ไม่ได้)
- **ของจริงเจ้าของทำเอง**: migrate / restart / start — ส่งคำสั่งที่ซ้อมกับสำเนาแล้ว พร้อม backup และวิธีถอยกลับ
- **ห้าม push จนกว่าจะสั่ง** · ห้าม rebase / force-push · commit เป็นก้อนต่อข้อ · ข้อความ commit ห้ามมีชื่อโมเดลหรือ emoji ·
  บรรทัดแรก = subject เว้นบรรทัดก่อน body · ลงท้าย `Co-Authored-By: Claude <noreply@anthropic.com>`
- **ห้ามใช้ port 8000 ทดสอบ** (ของจริง) · **ห้ามใช้ key ของ portal (id 4)** · NT-Report = อ่านอย่างเดียว ·
  secret / raw key / เนื้อหา `.env` ห้ามอยู่ใน commit / log / เอกสาร — ตรวจ `git diff --cached` ก่อน commit ทุกครั้ง
- **ทุกการแก้ที่กระทบ prompt**: วัดคำถามจริง (`scripts/eval/run_portal_questions.py`, server ซ้อมบนสำเนา + key ซ้อม) **และ**
  legacy (`run_eval.py --legacy`) ก่อน/หลัง อย่างน้อยสองรอบ · และพิสูจน์ว่า prompt เท่าเดิมทุกไบต์เมื่อทุกแถว `active`
- **ตัวเขียนความรู้ใหม่**: ผ่าน `provenance.py` + `replaceable(writer)` ใน WHERE ของคำสั่งเขียน + ตารางที่ไม่มี key เขียนทีละ row id
  · **ตัวอ่านใหม่ที่ถึง LLM / RAG / routing / สิทธิ์ของ key**: กรอง `status = 'active'` + test แบบ `test_provenance_readers.py`
- pytest บนสำเนาเท่านั้น (`venv/bin/python3.14`; `venv/bin/python` = 3.10 ไม่มี pytest)
- **เจอสิ่งที่ขัดกับแผน → หยุดและรายงานพร้อมทางเลือก** อย่าตัดสินใจแทนเจ้าของ
