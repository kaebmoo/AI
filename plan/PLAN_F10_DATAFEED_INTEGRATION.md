# PLAN F10 — DataFeed → NT AI Assistant (ข้อมูล + ความรู้ + golden)

**Prerequisite:** PLAN_F1 เสร็จ; Phase C-D ต้องมี PLAN_F3-B; แนะนำทำใน Wave 5 (หลัง F4)
**ประมาณเวลา:** 2-3 วัน (pilot โดเมน revenue)
**Decision ที่บันทึกแล้ว (2026-07-04):** โหมด dashboard ให้ assistant query ตาราง `feed_*` ชุดเดียวกับที่ใช้ build dashboard — แผนนี้คือ prerequisite ของ PLAN_F11

## ข้อเท็จจริงที่ตรวจจากไฟล์จริงแล้ว (2026-07-04) — ไม่ต้องเดาซ้ำ

- Source: `/Users/seal/Documents/GitHub/NT-Report/DataFeed/dist/<domain>/latest/` (config ได้ อย่า hardcode)
- `latest/` ของ revenue มี fact **ครบทุกงวด** 202401→202605 (29 งวด) — 8 fact + 7 dim + `control_totals.csv` + `SCHEMA.md` + `manifest.json`; โฟลเดอร์ `cumulative/` คือไฟล์เดียวกัน (sha256 ตรงกัน) เปลี่ยนชื่อ → **ใช้ latest เป็นแหล่งเดียวพอ**
- `manifest.json` มี: `schema_version`, `period`, `built_at`, sha256 + bytes ต่อไฟล์, `row_counts` ต่อตาราง, `reconcile: {ok, tolerance{rel,abs}, checks[]}` → ใช้เป็น integrity gate ได้ทั้งหมด
- `control_totals.csv` columns: `bu_seq,bu,year_month,measure,value` มีแถว `bu == "__ALL__"` = ยอดรวมองค์กรต่องวด
- Contract yaml (`DataFeed/contracts/<domain>.yaml`) มี: dtype ต่อคอลัมน์ (integer/double/string), description, unit, keys, grain, `business_rules` (เช่น `bg8_ytd_not_summable`, `sales_is_not_revenue`), `reserved_word_columns`, `control_totals` spec พร้อม tolerance
- คำเตือนจาก USAGE_IT: อ่าน CSV ต้องบังคับคอลัมน์รหัสเป็น string (`*_code`, `*_key`, `*_seq`, `cost_center`) ไม่งั้นเลข 0 นำหน้าหาย → **dtype ต้องมาจาก contract เสมอ ห้ามให้ pandas เดา**
- ขนาด revenue: CSV รวม ~157MB, แถวมากสุด 147,619 (fact_org_subproduct_monthly) — SQLite รับสบาย

## READ FIRST (AI repo)

- `requirements.txt` — ยืนยันว่ามี pandas (dependency ของ vanna); เช็คว่ามี pyarrow หรือไม่: **มี → ใช้ parquet, ไม่มี → ใช้ CSV + dtype จาก contract** (ห้ามเพิ่ม pyarrow ในแผนนี้ — เพิ่ม dependency = deferred decision ตามนโยบาย)
- `app/config.py`, `mcp_servers/nt_query_mcp.py` — business DB path/engine ที่ใช้จริง
- กลไก context ทั้งหมด: `app/services/schema/` + context onboarding (service/admin tools ที่ทำ "Context Onboarding" ใน admin UI) — ต้องรู้วิธี register ตาราง/context ที่ถูกต้องก่อนเขียน Phase B
- สถานะจริงของระบบ Vanna DB-driven documentation (`plan/PLAN_VANNA_DB_DRIVEN_DOCS.md` + โค้ด): ตาราง `vanna_documentation` + `mark_brain_dirty()` มีจริงหรือยัง — **ถ้ายังไม่ implement** ให้ Phase B ใช้เส้นทาง train documentation ของ vanna ที่มีอยู่แทน แล้วจดใน FIX_NOTES ว่าค้าง migrate
- `app/models/feedback_models.py` — โครง golden_examples จริง (field ชื่ออะไร, category ใช้ยังไง)
- grep business DB: มีตารางชื่อขึ้นต้น `feed_` อยู่แล้วหรือไม่ (กันชน)

---

## Phase A — Import script (writer เดียวของตาราง feed_*)

สร้าง `scripts/datafeed/import_datafeed.py` — รันมือ/รายเดือนหลัง build feed; **เปิด write connection ของตัวเอง** (ไม่ผ่าน MCP — assistant อ่านผ่าน read-only ตาม F4 เท่านั้น)

CLI: `--source <path dist หรือ handoff ที่แตกแล้ว>` `--domain revenue|expense|sales|ebt` `--db <path>` (default จาก config) `--allow-schema-change`

ขั้นตอนต่อโดเมน (ทั้งหมดใน transaction เดียว ผิดพลาด = rollback ทุกตาราง):
1. โหลด `latest/manifest.json` → ถ้า `reconcile.ok != true` → **abort ทันที** (ข้อมูลไม่ผ่าน gate ของ feed เอง)
2. ตรวจ sha256 ของทุกไฟล์ที่จะใช้ เทียบ manifest → ไม่ตรง = abort
3. โหลด contract yaml → generate DDL: ตาราง `feed_<domain>_<dataset>` (เช่น `feed_revenue_fact_bu_monthly`), dtype map integer→INTEGER, double→REAL, string→TEXT; สร้าง index บนคอลัมน์ใน `keys` ของแต่ละ dataset
4. ตรวจ schema_version เทียบ import ครั้งก่อน (จาก `feed_import_log`) → ต่างกันต้องมี `--allow-schema-change` ไม่งั้น abort พร้อมบอกให้ regen docs (Phase B) ด้วย
5. DROP + CREATE + INSERT: อ่านไฟล์ (parquet ถ้ามี pyarrow, ไม่งั้น CSV ด้วย `pd.read_csv(dtype=<map จาก contract: string→str>)`) chunk 50,000 แถว → insert
6. ตรวจ row count ทุกตารางเทียบ `manifest.row_counts` → ไม่ตรง = rollback
7. **ตรวจ control totals ใน DB จริง:** query จากตารางที่เพิ่ง insert ตาม spec ใน contract (group by bu × year_month sum(revenue) + grand total) เทียบทุกแถวของ `control_totals.csv` รวมแถว `__ALL__` ภายใน tolerance_rel/abs จาก contract → แถวใดไม่ผ่าน = rollback + รายงานแถวที่พลาด (นี่คือการยืด reconcile gate ของ feed เข้ามาถึง DB ของ assistant)
8. บันทึก `feed_import_log` (ตารางเล็กใน business DB: domain, schema_version, period, built_at, imported_at, row_total, status) → COMMIT + สรุปเวลา/จำนวนแถวลง stdout

**Tests:** `tests/unit/test_datafeed_import.py` — fixture bundle จิ๋ว (contract ย่อ + csv 10 แถว + manifest ปลอม): happy path, sha ผิด → abort, row count ผิด → rollback (ตารางเดิมอยู่ครบ), control total เพี้ยนเกิน tolerance → rollback, คอลัมน์ string มี "007" → คงเป็น "007"

---

## Phase B — Context + ความรู้จาก contract

สร้าง `scripts/datafeed/gen_docs_from_contract.py` (idempotent — รันซ้ำได้หลัง re-import):
1. Register context `feed_<domain>` + ตาราง feed_* เข้า context ตามกลไกจริงที่อ่านมา (ห้ามเขียน mechanism ใหม่เอง)
2. Documentation ต่อชิ้น:
   - ต่อ dataset: ชื่อตาราง, kind (fact/dim), **grain**, keys, แถวโดยประมาณ
   - ต่อคอลัมน์: description + unit + null_ok จาก contract (มีภาษาไทยพร้อมอยู่แล้ว)
   - **business_rules ทุกข้อ** — สำคัญที่สุด โดยเฉพาะ `bg8_ytd_not_summable` ("ยอดสะสมใช้ revenue_ytd แบบ point-in-time ห้าม sum revenue รายเดือนข้ามงวด") และ `sales_is_not_revenue` — ถ้าไม่ใส่ SQL จะผิดแบบตรวจด้วยตาไม่เห็น
   - `reserved_word_columns` ต่อ dataset → กฎ: "คอลัมน์ <x> เป็น reserved word ต้อง quote เป็น \"<x>\" เสมอ" (SQLite ใช้ double quote)
   - กฎ format งวด: `year_month` เป็น ค.ศ. YYYYMM (โยงกับกฎแปลง พ.ศ. ที่ระบบมีอยู่)
3. ล้าง docs เดิมของ context นี้ก่อน insert ใหม่ (ตาม mechanism: vanna_documentation หรือ vanna train path — ตามที่ตรวจพบใน READ FIRST) แล้ว trigger brain sync (`mark_brain_dirty()` ถ้ามี)

**Test:** รัน script กับ contract revenue จริง → นับจำนวน docs ที่เกิด (ตาราง+คอลัมน์+rules ครบ), รันซ้ำ → จำนวนเท่าเดิมไม่บวม

---

## Phase C — Golden examples จาก control_totals

สร้าง `scripts/datafeed/gen_golden_from_controls.py`:
- เลือกงวด: ล่าสุด + สุ่มย้อนหลัง 3 งวด
- ต่องวดสร้างคำถามไทย: (ก) รวมองค์กร "รายได้รวมทั้งบริษัทเดือน<เดือนไทย> <ปี พ.ศ.> เท่าไร" → SQL ต่อ `feed_revenue_fact_total_monthly`; (ข) ราย BG 2-3 ตัวอย่าง (สุ่มรวม BG ชื่อไทยอย่าง "7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม" เพื่อทดสอบ string matching); (ค) 1 ข้อ YTD ที่คำตอบถูกต้องต้องใช้ `revenue_ytd` (ทดสอบ business rule ตรง ๆ)
- ปริมาณรวม ~15-25 ข้อ — พอเป็นชุดวัด ไม่ flood knowledge; ใส่ marker ใน field ที่เหมาะ (เช่น note/source = `datafeed_auto`) ให้ลบ/regen ได้สะอาด
- expected value จาก control_totals → เก็บคู่กับ golden ตามโครง golden_examples จริง (คำถาม พ.ศ. จงใจ exercise กฎแปลงปีของระบบ)

## Phase D — Baseline eval ของ context ใหม่

รัน `scripts/eval/run_eval.py --context feed_revenue` → บันทึกผล + latency ลง `plan/RESULT_F10.md` — นี่คือ baseline ที่ PLAN_F11 และ PLAN_F9 จะใช้อ้างอิง

---

## ขอบเขต / งานอนาคต (จดไว้ ไม่ทำในแผนนี้)

- Pilot = **revenue โดเมนเดียว** — โดเมนอื่น (expense/sales/ebt) รัน 3 script เดิมซ้ำเมื่อ pilot ผ่าน (script ต้องเขียนแบบ domain-agnostic ตั้งแต่แรก อ่านทุกอย่างจาก contract)
- MSSQL variant สำหรับ production = งานอนาคต (โครง DDL/insert แยก engine ไว้ใน adapter layer ให้เพิ่มได้)
- DuckDB query ตรงจากไฟล์ = deferred decision (บันทึกใน PLAN_FIX_MASTER แล้ว)
- Auto-sync ต่อท้าย pipeline ของ NT-Report (`--feed` แล้ว trigger import) = ทำหลัง manual flow นิ่ง

## Acceptance Criteria

- [ ] Import revenue จริงผ่าน integrity ครบทุกชั้น (reconcile.ok, sha256, row counts, control totals) — แนบเวลา import ใน commit message
- [ ] ถามผ่าน UI 5 คำถามที่คำตอบอยู่ใน control_totals → ตรงทุกข้อภายใน tolerance
- [ ] ถาม "รายได้สะสมของ BG 8 ..." → SQL ที่ generate ใช้ `revenue_ytd` (พิสูจน์ว่า business rule เข้า knowledge จริง)
- [ ] `plan/RESULT_F10.md` มี baseline eval + latency ของ context feed_revenue
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md`
