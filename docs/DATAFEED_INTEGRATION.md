# DataFeed Integration (F10)

**วันที่:** 2026-07-12
**Scripts:** `scripts/datafeed/import_datafeed.py`, `gen_docs_from_contract.py`, `gen_golden_from_controls.py`
**Plan / ผลลัพธ์:** `plan/archive/PLAN_F10_DATAFEED_INTEGRATION.md`, `plan/archive/RESULT_F10.md`

## DataFeed คืออะไร

DataFeed คือ data bundle ที่ build จากโปรเจกต์ NT-Report
(`NT-Report/DataFeed/dist/<domain>/latest/`) ประกอบด้วย:

- ไฟล์ CSV ราย dataset (fact + dim)
- `manifest.json` — schema_version, period, built_at, sha256 + row_counts ต่อไฟล์,
  ผล reconcile ของ feed เอง (`reconcile.ok`)
- `control_totals.csv` — ยอดควบคุมต่อ BG × งวด (`bu_seq,bu,year_month,measure,value`
  มีแถว `bu = "__ALL__"` = ยอดรวมองค์กร)
- Contract yaml (`DataFeed/contracts/<domain>.yaml`) — dtype/description/unit ต่อคอลัมน์,
  grain, keys, `business_rules`, `reserved_word_columns`, spec ของ control totals

F10 นำ bundle นี้เข้า business DB ของ assistant เป็นตาราง `feed_*`
พร้อม generate ความรู้ (context/docs) และ golden examples จาก contract โดยอัตโนมัติ —
เป็น prerequisite ของโหมด dashboard (F11) ที่ assistant query ตาราง `feed_*`
ชุดเดียวกับที่ใช้ build dashboard

## Context `feed_revenue` (pilot)

- Context name: `feed_revenue` — **main_view = `feed_revenue_fact_bu_monthly`**
  (มาจาก `control_totals.source` ใน contract)
- งวด (`year_month`) เป็น ค.ศ. รูปแบบ YYYYMM (เช่น 202605 = พฤษภาคม 2026) —
  user ถาม พ.ศ. ระบบต้องแปลง (พ.ศ. - 543)
- Business rules สำคัญที่เข้า knowledge จาก contract:
  - `bg8_ytd_not_summable` — ยอดสะสมต้องใช้ `revenue_ytd` แบบ point-in-time
    **ห้าม sum revenue รายเดือนข้ามงวด**
  - `sales_is_not_revenue` — ยอดขายไม่ใช่รายได้

## ตารางใน business DB (ตรวจจริง 2026-07-12)

Fact 8 ตาราง / Dim 7 ตาราง / import log 1 ตาราง:

| กลุ่ม | ตาราง |
|---|---|
| Fact | `feed_revenue_fact_bu_monthly`, `feed_revenue_fact_total_monthly`, `feed_revenue_fact_org_monthly`, `feed_revenue_fact_org_product_monthly`, `feed_revenue_fact_org_subproduct_monthly`, `feed_revenue_fact_product_monthly`, `feed_revenue_fact_service_group_monthly`, `feed_revenue_fact_subproduct_monthly` |
| Dim | `feed_revenue_dim_bu`, `feed_revenue_dim_org`, `feed_revenue_dim_org_mapping`, `feed_revenue_dim_org_used`, `feed_revenue_dim_product`, `feed_revenue_dim_service_group`, `feed_revenue_dim_sub_product` |
| Log | `feed_import_log` (domain, schema_version, period, built_at, imported_at, row_total, status) |

## Import workflow (Phase A)

```bash
python -m scripts.datafeed.import_datafeed --domain revenue \
    --source /path/to/DataFeed/dist [--db nt_fi_report.sqlite] [--allow-schema-change]
```

`--domain` รับ `revenue|expense|sales|ebt` — script เขียนแบบ domain-agnostic
(อ่านทุกอย่างจาก contract) รันมือ / รายเดือนหลัง build feed

ทั้งหมดทำใน **transaction เดียว** — gate ใดพลาด = rollback ไม่มีอะไรเปลี่ยน:

1. **Gate 1 — reconcile:** `manifest.reconcile.ok` ต้องเป็น true (feed ไม่ผ่าน gate ตัวเอง → abort)
2. **Gate 2 — sha256:** ตรวจทุกไฟล์ที่จะใช้ (dataset CSV + `control_totals.csv`) เทียบ manifest
3. ตรวจ `schema_version` เทียบ import ครั้งก่อน (จาก `feed_import_log`) —
   เปลี่ยนแล้วต้องใส่ `--allow-schema-change` และรัน `gen_docs_from_contract` ใหม่ด้วย
4. DROP + CREATE ตาราง `feed_<domain>_<dataset>` ตาม DDL จาก contract
   (integer→INTEGER, double→REAL, string→TEXT) แล้ว insert ทีละ chunk 50,000 แถว —
   **dtype ของคอลัมน์ string บังคับจาก contract เสมอ** (กันเลข 0 นำหน้าหายใน `*_code`)
   พร้อมสร้าง index ตาม `keys` ของแต่ละ dataset
5. **Gate 3 — row counts:** จำนวนแถวทุกตารางต้องตรง `manifest.row_counts`
   (entry หายจาก manifest = fail ไม่ใช่ skip)
6. **Gate 4 — control totals:** query จากแถวที่เพิ่ง insert จริง
   เทียบทุกแถวของ `control_totals.csv` (รวม `__ALL__` กับตาราง grand total)
   ภายใน tolerance_rel/abs จาก contract
7. บันทึก `feed_import_log` status='ok' → COMMIT

## กฎเหล็ก: writer เดียว

> **`import_datafeed.py` คือ writer เดียวของตาราง `feed_*` —
> assistant อ่านผ่าน read-only connection (ตาม F4) เท่านั้น**

Importer เปิด write connection ของตัวเอง ไม่ผ่าน MCP —
ห้ามให้โค้ดอื่นใดเขียน/แก้ตาราง `feed_*`

## Generate docs + golden จาก contract (Phase B, C)

```bash
# Phase B — context + knowledge (idempotent — รันซ้ำหลังทุก re-import)
python -m scripts.datafeed.gen_docs_from_contract --domain revenue \
    --contract /path/to/DataFeed/contracts/revenue.yaml

# Phase C — golden examples จาก control_totals
python -m scripts.datafeed.gen_golden_from_controls --domain revenue \
    --source /path/to/DataFeed/dist
```

**gen_docs_from_contract** (delete + reinsert = idempotent):
- Upsert context `feed_<domain>` ใน `schema_contexts` (main_view, keywords,
  instruction_th ที่รวม business rules ทุกข้อ)
- `schema_metadata` ต่อคอลัมน์: description + unit จาก contract,
  is_summable (double), is_groupable (string/key)
- `vanna_documentation` (doc_key ขึ้นต้น `datafeed_<domain>_`): ต่อตาราง
  (kind/grain/keys/จำนวนแถว/คอลัมน์), กฎ reserved word ต่อคอลัมน์
  ("ต้อง quote เป็น double quote เสมอ"), business rules ทุกข้อ, กฎ format งวด YYYYMM
- จบแล้ว `mark_brain_dirty()` ให้ Vanna re-sync

**gen_golden_from_controls** (marker: `category = 'feed_<domain>'` — ลบ/regen สะอาด):
- เลือกงวดแบบ deterministic: ล่าสุด + 3 งวดย้อนหลังกระจายเท่า ๆ กัน
- ต่องวด: (ก) ยอดรวมองค์กร → `feed_<domain>_fact_total_monthly`,
  (ข) ราย BG รวม BG ชื่อไทย (ทดสอบ string matching) → `feed_<domain>_fact_bu_monthly`,
  (ค) คำถาม YTD ที่ต้องใช้ `revenue_ytd` (ทดสอบกฎ bg8 ตรง ๆ)
- คำถามใช้เดือนไทย + พ.ศ. — จงใจ exercise กฎแปลงปีของระบบ
- ค่าที่คาดหวังมาจาก control_totals → ใช้กับ eval harness
  (`python -m scripts.eval.run_eval --context feed_revenue` — ดู `docs/EVAL_HARNESS.md`)

## สถานะปัจจุบัน (pilot: revenue)

จาก `plan/archive/RESULT_F10.md` (2026-07-11):

- Import จริงผ่าน gate ครบ 4 ชั้น — **255,404 แถว ใน 3.4 วินาที**
  (schema 1.0.0, period 202605, control totals 522 แถวใน tolerance)
- Knowledge: 159 schema_metadata rows + 21 vanna_documentation docs, idempotent ✓
- Golden: 14 ข้อ (category=`feed_revenue`)
- Baseline eval: **ค่าถูกทุกข้อ (accuracy_incl_value_match = 100%)** —
  strict = 0/14 เพราะ alias ที่โมเดลตั้งไม่ตรง golden (value_match 14/14),
  Latency P50/P95 = 10.5s/17.4s
- Business rule พิสูจน์แล้ว: คำถาม YTD ทั้ง 2 ข้อ → SQL ใช้ `revenue_ytd` จริง
- โดเมนอื่น (expense/sales/ebt): รัน 3 scripts เดิมซ้ำเมื่อพร้อม —
  MSSQL variant / DuckDB / auto-sync = งานอนาคต (จดใน plan แล้ว)
