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

## File source (DuckDB) — zero-import (Plan 7 Phase 1)

ตั้งแต่ Plan 7 Phase 1 context `feed_*` **อ่านไฟล์ CSV ใน `DataFeed/dist/<domain>/latest/` ตรง**
ผ่าน DuckDB — ไม่ต้อง import อีก NT-Report publish งวดใหม่ลง `latest/` เมื่อไร คำถามถัดไปเห็นทันที
(ตาราง `feed_revenue_*` ใน `nt_fi_report.sqlite` ยังอยู่เป็น fallback แต่ context ไม่ได้อ่านมันแล้ว)

| Context (2026-09-19) | Source | schema / งวด | สถานะ | eval |
|---|---|---|---|---|
| `feed_revenue` | `datafeed_revenue` | 2.1.0 / 202608 | ✅ active | 14/14 |
| `feed_expense` | `datafeed_expense` | 1.2.0 / 202608 | ✅ active | 12/12 |
| `feed_sales` | `datafeed_sales` | 1.2.0 / 202608 | ✅ active (2026-09-19 — contract มีกฎ actual/target + `control_totals.filter`) | 12/12 |
| `feed_ebt` | `datafeed_ebt` | 1.3.0 / 202607 | ⏸ ปิด (`is_active=0`) — มีทั้งรายเดือน (`*_month`) และสะสม แต่โมเดลยัง SUM คอลัมน์สะสมข้ามงวด / ใช้สะสมตอบรายเดือน รอกฎใน contract | 18/24 |

(รายละเอียด: `plan/archive/RESULT_P7_PHASE2.md` หัวข้ออัปเดต 2026-09-19, `plan/PLAN_REMAINING_ITEMS.md` REMAIN-11)

### วิธีลงทะเบียน source

```bash
python -m scripts.datafeed.register_file_source --domain revenue \
    --source /path/to/DataFeed/dist          # migrate + gate + registry + context/knowledge ในคำสั่งเดียว
python -m scripts.datafeed.gen_golden_from_controls --domain revenue \
    --source /path/to/DataFeed/dist          # golden สำหรับ eval (ถ้า contract มี control_totals)
```

`register_file_source` ผ่าน gate ชุดเดียวกับ importer แต่ตรวจ **ไฟล์ในที่เดิม** และเขียน registry
เฉพาะเมื่อผ่านทุกข้อ (ไม่ผ่าน = registry ไม่เปลี่ยน):

1. `manifest.reconcile.ok` = true
2. sha256 ของทุกไฟล์ที่ใช้ตรง manifest — **allowlist = dataset ใน contract ที่ CSV อยู่ใน `manifest.files`**
3. row count ผ่าน view (DuckDB) ตรง `manifest.row_counts`
4. control totals ผ่าน view ตรง `control_totals.csv` ทุกแถว — ตาม spec ใน contract: `__ALL__` = grand-total dataset
   ถ้ามี ไม่งั้นรวมจาก source (expense/sales); `filter: {column: value}` (sales `metric: actual`) = กรอง source ก่อนรวม
   (grand-total dataset ที่แยกต่างหากไม่ถูกกรอง); ไม่มี `bg_key` (ebt `fact_ebt_total_monthly`) = source ยอดรวมอย่างเดียว
   ทุกแถวของ control totals คือยอดของงวดนั้น; contract ที่ไม่มี `control_totals` ข้าม gate นี้

แล้วเขียนใน **transaction เดียว**: `data_sources` (`datafeed_<domain>`, `duckdb_file`, `root_path` = `.../latest`,
`contract_file`, `knowledge_sha`), `source_tables` (ชื่อ view `feed_<domain>_<dataset>` → ไฟล์ + ชนิดคอลัมน์จาก contract),
context `feed_<domain>` + knowledge (สร้างถ้ายังไม่มี) และผูก `schema_contexts.source_id` — server ที่รันอยู่เห็นผลใน request ถัดไป
(ไม่ต้อง restart; คำตอบที่ cache ไว้จาก source เดิมจะไม่ถูกใช้ต่อ)

### Knowledge ตาม contract อัตโนมัติ (Phase 2)

logic อยู่ที่ `app/services/datafeed_knowledge.py` (`gen_docs_from_contract` เหลือเป็น wrapper สำหรับโหมด import/สั่งมือ):
- ทุก request ของ file source: `stat` ไฟล์ contract (~0.5 ms) — ถ้า contract หรือ `schema_version` ของ build เปลี่ยน
  → เขียน context instruction / `schema_metadata` / `vanna_documentation` ใหม่จาก contract **ครั้งเดียวข้ามทุก process**
  (compare-and-set บน `data_sources.knowledge_sha`) + `mark_brain_dirty()` + ล้าง query cache — ไม่ต้องรันอะไร
- instruction + กฎ + metadata มีผลกับ request ถัดไปทันที (อ่านจาก config DB ตรง); docs ใน Vanna รอ admin กด Sync Brain
- re-sync ล้ม (เช่น yaml เสีย) = คง knowledge เดิม, log error, request ไม่ล้ม
- keywords/priority ของ context ตั้งตอนสร้างครั้งแรกเท่านั้น — admin แก้ได้ ไม่ถูกทับ
  (default: คำโดเมน + marker `feed`/`datafeed`/`dashboard`/`แดชบอร์ด`, priority 1 → router เลือก feed เฉพาะเมื่อคำถามมี marker;
  portal ส่ง `context` มาตรง ไม่ผ่าน router)
- schema เพิ่ม/ลบคอลัมน์: knowledge ตามเอง แต่ view ยังเป็นชุดคอลัมน์ตอนลงทะเบียน → รัน `register_file_source` ใหม่
- `scope_columns` ใน contract (`{scope key: column}`, Plan 7 Phase 3) → `schema_contexts.scope_columns` — กำหนดว่า portal
  จำกัดขอบเขตด้วย `scope` ได้ด้วย key อะไร; dataset ที่ไม่มีคอลัมน์นั้นจะใช้ไม่ได้ภายใต้ scope (ดู `docs/PORTAL_INTEGRATION.md`)

**ย้อนกลับไปใช้ข้อมูลที่ import ไว้ (fallback):**
`python -m scripts.datafeed.register_file_source --domain revenue --legacy` แล้วรัน
`import_datafeed.py` ตามปกติ — importer ยังทำงานเหมือนเดิมทุกอย่าง

### ทำงานอย่างไร

- Context → `schema_contexts.source_id` → `data_sources` (`SourceResolver`, `app/services/data_sources.py`)
  — context ที่ไม่มี `source_id` หรือผูกกับ `legacy` = business DB เดิมผ่าน MCP เหมือนก่อน Plan 7
- `DuckDBFileAdapter` (`app/services/database_adapter.py`) สร้าง view ชื่อเดิมของ F10
  (`feed_revenue_fact_bu_monthly` ฯลฯ) บน `read_csv(<root>/<file>, columns={...})` ชนิดคอลัมน์จาก
  contract → คอลัมน์ string (เช่น `service_group_seq` "3.10", `*_code`) ไม่ถูกเดาเป็นตัวเลข —
  knowledge/golden ของ F10 จึงใช้ต่อได้โดยไม่ต้อง regen
- อ่าน CSV ด้วย dialect ที่ pin ไว้ (`delim=','`, `quote='"'`, `escape='"'` แบบที่ pandas เขียน) — sniffer ของ DuckDB
  ดูแค่ ~20k แถวแรก ไฟล์ที่ field มี quote ครั้งแรกทีหลัง (`fact_sales.csv`) จะถูกเดาเป็นไม่มี quote แล้วพัง
- view definition (ไม่ใช่ข้อมูล) อยู่ในไฟล์เล็ก `DATA_SOURCE_CACHE_DIR/<source>-<fingerprint>.duckdb`
  (default `./.source_cache/`) สร้างใหม่ต่อ process
- SQL ที่ LLM สร้างสำหรับ context นี้รัน in-process บน DuckDB (ไม่ผ่าน MCP) — ผ่าน F4 validator เสมอ
  และ prompt ได้กฎ syntax ของ DuckDB (`//` หารจำนวนเต็ม, `ILIKE`, `current_date`)
- export xlsx ของคำตอบจาก context นี้รันกับ source เดียวกัน; eval harness รัน golden SQL กับ source ของ context

### ความปลอดภัย (บังคับที่ engine ไม่ใช่แค่ regex)

ตรวจกับ DuckDB 1.5.5 จริง — `lock_configuration` **ไม่ได้**กัน table function อย่าง `enable_logging()`
(แบบ file ทำ process ล่ม, แบบ memory เปิดให้อ่าน SQL ของผู้ใช้คนอื่นผ่าน `duckdb_logs`) จึงมี query gate เป็นอีกชั้น:

| มาตรการ | ผล |
|---|---|
| view DB เปิด `read_only` | `CREATE`/`DROP`/`INSERT` ล้ม |
| `allowed_paths` = เฉพาะไฟล์ที่ลงทะเบียน แล้ว `enable_external_access=false` | อ่านไฟล์อื่น (รวมไฟล์อื่นใน root เช่น `control_totals.csv`), `glob`, `COPY TO`, `ATTACH`, `EXPORT`, http, `INSTALL`/`LOAD` ล้มหมด (ยกเว้น temp directory ของ DuckDB เอง — จึงต้องมี query gate) |
| `lock_configuration=true` | `SET` ค่ากลับไม่ได้ |
| cursor ใหม่ทุก query | `CREATE TEMP VIEW` ทับชื่อ view ไม่ติดไปถึง query ถัดไป |
| query gate (DuckDB parser, `json_serialize_sql`) ทุก SQL ที่มาจากภายนอก | ต้องเป็น SELECT เดียว อ่านได้เฉพาะ view ที่ลงทะเบียน/CTE ของตัวเอง — ห้าม table function ทุกตัว (`read_*`, `query()`, `enable_logging()` …) และห้าม system view (`duckdb_logs`, `information_schema`) |
| F4 validator | ปฏิเสธ non-SELECT, หลาย statement และการเรียก `read_*`/`*_scan`/`glob` ตรง ๆ |
| registry | `file_name` ที่หลุด root (`..`, symlink) หรือชนิดคอลัมน์นอก allowlist = ปฏิเสธตอนสร้าง view |

### ข้อจำกัด (Phase 1)

- **ระหว่าง NT-Report publish:** publisher ปัจจุบันลบ `latest/` แล้วเขียน CSV ทับทีละไฟล์ — AI ตรวจ `manifest.json` (reconcile.ok + sha256 ทุกไฟล์) ครั้งเดียวต่อ build และ stat ไฟล์ก่อน/หลังทุก query → คำถามช่วง publish ได้ข้อความ "ข้อมูลกำลังถูก publish — กรุณาถามใหม่" **ไม่มีทางได้คำตอบจากไฟล์ครึ่งไฟล์** (replay จริง: 0 คำตอบผิด) — เมื่อ NT-Report publish ด้วยโค้ดใหม่ (`7d639b0`: build ใหม่ทั้งชุดแล้วสลับ symlink `latest`) จะไม่มีช่วงที่ถามไม่ได้เลย (replay: 2,978 คำตอบถูก 0 error ระหว่างสลับ build) — ฝั่ง AI ไม่ต้องลงทะเบียนใหม่
- ไม่มี spill ลงดิสก์ (`temp_directory=''` — กัน process แย่ง spill dir กัน) → query ที่ใช้หน่วยความจำเกิน memory_limit จะ error แทน
- file source = **local path เท่านั้น** (D1 default) — S3/HTTPS ยังไม่ทำ
- อ่าน **CSV** เท่านั้น — Parquet ที่ bundle มีอยู่แล้วยังไม่ใช้ (ดูผล latency ใน `plan/archive/RESULT_P7_PHASE1.md`)
- ตรวจ manifest ต่อ build เฉพาะ source ที่มี `data_sources.manifest_file` (`register_file_source` ตั้งให้);
  `/api/v1/query` คืน `data_as_of` (`period`, `built_at`, `build_id` ของ build ที่ตรวจแล้ว — `docs/PORTAL_INTEGRATION.md`)
- MCP tool `get_sample_values` / `get_table_stats` (ใช้เฉพาะ tool-loop mode) ตอบ error สำหรับ file source
  แทนการอ่าน DB เดิมเงียบ ๆ
- หน้า admin (schema browser, onboarding, keyword index rebuild, sync-brain DDL) ยังเห็นแค่ business DB เดิม
- query result cache (30 นาที) ผูกกับ build: publish งวดใหม่หรือเปลี่ยน source แล้ว คำตอบเดิมไม่ถูกใช้ต่อ (ไม่ต้อง `refresh-cache`)

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

**gen_golden_from_controls** (marker: `category = 'feed_<domain>'` — ลบ/regen สะอาด) — ทุกอย่างอ่านจาก `control_totals` ของ contract:
- เลือกงวดแบบ deterministic: ล่าสุด + 3 งวดย้อนหลังกระจายเท่า ๆ กัน
- ต่องวด (measure `agg: sum`): (ก) ยอดรวมองค์กร → grand-total dataset ถ้ามี ไม่งั้น `SUM` จาก source,
  (ข) กลุ่มแรก + กลุ่มชื่อไทยอีกกลุ่ม (ทดสอบ string matching; ใช้คอลัมน์ `*_name` ใน group_keys เป็นชื่อในคำถามถ้ามี)
  → source (`SUM` เมื่อ source ละเอียดกว่า group × งวด),
  (ค) measure `agg: point_in_time` → คำถาม YTD (ทดสอบกฎ ytd ตรง ๆ)
- `filter` ใน control_totals → ทุก SQL ต่อท้าย `AND <column> = <value>` (sales: `AND metric = 'actual'`)
- source ที่ไม่มี `bg_key` (ยอดรวมอย่างเดียว) → หนึ่งคำถามต่อ measure ต่องวด ถามเป็น "ของเดือน…" หรือ "สะสมตั้งแต่ต้นปีถึงเดือน…" ตาม measure
  (`MEASURE_WORDS`; measure ที่ไม่รู้จัก = `note` + `agg: point_in_time` → สะสม) — คำถามต้องบอกฐานให้ชัด ไม่งั้นคำตอบผิดความหมายได้คะแนน
- main view ที่เป็นตารางยอดรวมไม่มีมิติ (control totals ไม่มี `bg_key`): instruction ของ context ชี้ตารางรายละเอียด (`primary_dataset`) พร้อมคอลัมน์
  และ prompt ยอมให้ใช้ตารางที่ instruction ระบุชื่อ (`hybrid_flow.table_rule`) — context ที่ instruction ไม่เอ่ยถึงตารางอื่นยังถูกตรึงที่ main view เหมือนเดิม
- contract ที่ไม่มี `control_totals` → ไม่สร้าง golden (ของเดิมไม่ถูกลบ)
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
