# PLAN — Metrics convergence: ให้คำตอบถูกเป็น "ชั้น" ไม่ใช่ไล่แก้ทีละคำถาม

> เขียน 2026-10-24 หลัง go-live declared metrics (`86584b2`) และการแก้ `e2bc47d` (จัดอันดับตามค่า metric)
> **สำหรับสั่ง `/delegate` ใน session ใหม่** — แผนนี้คือ brief: §0 ข้อห้าม, §2 ข้อตัดสินที่เจ้าของเคาะ, §3–§7 งานเป็น phase/slice
> พร้อมไฟล์ที่อนุญาตและ acceptance ต่อ slice. ลำดับที่แนะนำ: **A → D → E → B → C** (C ต้องรอฝั่ง NT-Report; E ให้ feed มีคำอธิบายครบก่อน C-0b/C-01)

---

## 0. ก่อนเริ่ม — ข้อห้ามและสภาพแวดล้อม (เหมือน `PROMPT_RESEARCH_DECLARED_METRICS.md` §0)

- **server จริงรัน `uvicorn --reload` จาก working tree ของ `main`** (`/Users/seal/Documents/GitHub/AI`) — แก้ `.py` ใน main = ขึ้นของจริงทันที
  → ทำงานใน **worktree** (`/Users/seal/Documents/GitHub/_worktrees/AI-metrics` หรือใหม่) บน branch จาก `main`; ขึ้นของจริง = ff `main` หลัง review เท่านั้น
- ฝั่ง AI อ่าน contract ของ NT-Report ที่ `NT-Report/DataFeed/contracts/*.yaml` และ re-sync ทุก request → แก้ YAML = ขึ้นของจริงทันที
  → งาน Phase C ทำใน worktree ของ NT-Report (`_worktrees/NT-Report-metrics`) ผ่าน `tools/feed/domains.py` → `gen_contract.py` → `build_feed.py` ลง `dist` **ของสำเนา**
- ทดลองบนสำเนาเท่านั้น: `.ai/db/config.db` + `.ai/db/app.db` (มีอยู่จาก run `20261024-0104`), server ซ้อม port 8001+, key ซ้อม — **ห้าม port 8000, ห้าม API key id 4 (portal) และ id 5 (Claude Desktop)**
- pytest ใช้ `venv/bin/python3.14` (`venv/bin/python` = 3.10 ไม่มี pytest); server/eval ใช้ 3.10 เพราะมี RAG (`eval-python-rag`)
- อ่าน `docs/DECLARED_METRICS.md` ทั้งไฟล์ และ `plan/RESEARCH_DECLARED_METRICS.md` §4 (ข้อตัดสิน D-1..D-7) ก่อน

**Acceptance ที่ใช้ทุก slice (จาก root ของ worktree):**
```
ACC-T: env -i HOME=/Users/seal PATH=/usr/bin:/bin SECRET_KEY=ci-test-secret-key-not-for-prod REDIS_URL=redis://localhost:6379/0 ALLOWED_EMAIL_DOMAINS='["nt.th"]' CONFIG_DB_URL=sqlite:///.ai/db/config.db DATABASE_URL=sqlite:///.ai/db/app.db /Users/seal/Documents/GitHub/AI/venv/bin/python3.14 -I -m pytest tests -q --maxfail=5 -p no:cacheprovider   → exit 0 (baseline 2026-10-24: 1426 passed, 3 skipped)
ACC-L: /Users/seal/Documents/GitHub/AI/venv/bin/ruff check app mcp_servers scripts --select E9,F63,F7,F82   → exit 0
```

---

## 1. ปัญหาที่แผนนี้แก้ (หลักฐาน 2026-10-24)

คำถามจาก Claude Desktop ผ่าน MCP: **"หน่วยงานไหนได้ EBT สูงสุด 10 อันดับแรก"** / **"ศูนย์ต้นทุนไหนมี EBT สะสมปีนี้สูงสุด 10 อันดับ"**

| | ที่ระบบตอบ (ก่อนแก้) | ที่ถูก |
|---|---|---|
| อันดับ 1 | 2Q30102 = **1,744.60 ล้าน** (`query_audit` 407) | 2R30203 ระยอง = **130.03 ล้าน** |
| SQL | นับแต่ `รวมรายได้ทั้งสิ้น` (ไม่หักค่าใช้จ่าย) + `SUM(amount_ytd)` ข้าม 202601–202609 | 4 ก้อนตาม `ebt_dimension_breakdown`, `time_key = 202609` งวดเดียว, ใน 2 สายงานขาย |

สิ่งที่สำคัญกว่าตัวเลข: **สูตรที่ถูกอยู่ใน contract แล้ว** (`metrics: ebt` มิติถึง `cost_center`) แต่คำถามตกไปให้ LLM เขียน SQL เพราะ
`supports()` ปฏิเสธ `ordering.column = "ebt"` — ความผิดพลาดมาเป็น "ชั้น" (ทุกคำถามจัดอันดับ) ไม่ใช่รายคำถาม และ**ไม่มีอะไรจับได้**:
`plan()` คืน `None` เงียบ ๆ, guard หลัง pass 2 ไม่รู้ว่า `amount_ytd` เป็น point-in-time, eval ไม่มีคำถามรูปนี้, ต้องรอผู้ใช้เจอเอง

แผนนี้ตอบคำถามของเจ้าของ "ต้องไล่แก้ทีละคำถามตลอดไปไหม" ด้วย 5 กลไกที่ทำให้ระบบ**ลู่เข้า**แทนที่จะวนไล่:

| # | กลไก | ปิดช่องแบบไหน | Phase |
|---|---|---|---|
| 1 | นับและเก็บเหตุผลที่ `plan()` ปฏิเสธ + สัดส่วน compiled/free-SQL ต่อ context | "รอผู้ใช้เจอเอง" → เห็นชั้นที่ตกบ่อยสุดทุกสัปดาห์ | **A** |
| 2 | Eval ที่**สร้างเอง**จากคำประกาศ (metric × มิติ × งวด × top-N × คำพ้อง) เทียบ oracle จาก parquet | คำถามรูปใหม่ / ข้อมูลเดือนใหม่ = รันชุดเดิมซ้ำ ไม่ต้องเขียนคำถามมือ | **D** |
| 3 | ตัวตรวจ SQL ของ pass 2 ตาม invariant ของ contract (point-in-time ห้าม SUM ข้ามงวด ฯลฯ) | "ผิดอย่างมั่นใจ" → "ตอบไม่ได้/ลองใหม่" | **B** |
| 4 | ขยาย `metrics:` ไป revenue / sales / expense (+ ส่วนขยาย compiler ที่จำเป็น) | ย้ายคำถามส่วนใหญ่ออกจากเส้นทาง free-SQL | **C** |
| 5 | ตัวชี้วัดเดียว: % คำถามที่ตอบจากเส้นทาง compile (จาก #1) | รู้ว่าเหลือความเสี่ยงเท่าไร และลดลงจริงไหม | A → รายงานทุก phase |

---

## 2. ข้อตัดสินที่เจ้าของต้องเคาะก่อน /delegate (ค่าแนะนำ = ตัวหนา)

| # | เรื่อง | ทางเลือก | แนะนำ |
|---|---|---|---|
| **M-1** | ที่เก็บผลของ `plan()` ต่อคำถาม | (ก) **คอลัมน์ใหม่ `query_audit.metric_path`** (nullable text: `compiled:<id>` / `declined:<reason>` / NULL = context ไม่มี metric) — migration เพิ่มคอลัมน์อย่างเดียว · (ข) parse `query_trace` จาก log (log ของ server วันนี้ออก tty ไม่มีไฟล์) | **(ก)** — audit คือที่เก็บถาวรที่ portal/MCP เขียนอยู่แล้ว |
| **M-2** | เมื่อ SQL ของ pass 2 ละเมิด invariant แล้ว retry ครบ | (ก) **fail closed**: `error = query_failed` ข้อความตายตัว (ชุดเดียวกับ `app/core/outbound.py`) · (ข) ตอบพร้อมคำเตือน · (ค) log อย่างเดียว | **(ก)** — "ไม่มีคำตอบ" เจ็บน้อยกว่า "ตัวเลขผิดอย่างมั่นใจ"; log เหตุผลจริงใน server เท่านั้น |
| **M-3** | การแยกตามมิติ**โดยไม่มีตัวกรอง**อยู่ใน `official_scope` (เปลี่ยนแล้วใน `e2bc47d` ตาม D-3) | (ก) **คงไว้** · (ข) ถอยกลับ (คำนวณทุกสายงานเมื่อไม่ระบุ) | **(ก)** — คำถาม "ศูนย์ต้นทุนไหน EBT สูงสุด" หมายถึงรายงาน EBT ซึ่งคือ 2 สายงานขาย |
| **M-4** | revenue มีตารางสำเร็จรูปต่อ grain (`fact_bu_monthly`, `fact_org_monthly`, `fact_product_monthly`, …) แต่ metric หนึ่งผูก `dataset` เดียว | (ก) **compiler เลือกตารางตามมิติ**: `datasets: [{name, dimensions}]` เลือกตารางเล็กสุดที่มีมิติที่ขอครบ · (ข) ประกาศบนตารางละเอียดสุดตารางเดียว (`fact_org_subproduct_monthly`) แล้ว GROUP BY เอง · (ค) ประกาศ metric แยกต่อ grain (`revenue_by_bu`, `revenue_by_org`, …) | **(ก)** — ตรงกับที่ NT-Report build มาให้ และคำตอบตรง control totals ของ grain นั้นเอง |
| **M-5** | ยอดสะสมของ measure `agg: sum` ที่ไม่มีคอลัมน์ YTD (sales `amount`, expense `expense_value_thb`) | (ก) **compiler รองรับ `cumulative: {range: true}`** = `period BETWEEN y01 AND yMM` เฉพาะ measure ที่ประกาศ `agg: sum` · (ข) ให้ NT-Report เพิ่มคอลัมน์ `*_ytd` ทุก fact | **(ก)** — compiler รู้จาก contract ว่าคอลัมน์ไหนบวกข้ามงวดได้; (ข) เพิ่มงาน build โดยไม่จำเป็น |
| **M-6** | oracle ของ eval ที่สร้างเอง | (ก) **compiler + parquet ใน dist** (ทดสอบ "ประตู" — pass 1 เลือกถูกไหม — ไม่ใช่สูตร) · (ข) ผลลัพธ์ที่ NT-Report build ให้ (D-6 ข `fact_ebt_org_monthly` — ทดสอบสูตรด้วย) | **(ก) ก่อน, เพิ่ม (ข) เมื่อ D-6 ข ขึ้น** — สูตรถูกตรวจแล้วโดย `test_metrics_contract.py` + control totals |
| **M-8** | ร่างคำอธิบายคอลัมน์ feed ที่ว่าง (Phase E) มาจากอะไร | (ก) **profile ค่าจริงก่อน** (prefix ของค่า เช่น 77/114 ค่าขึ้นต้น 'ฝ่าย…' → "ฝ่าย", dtype, key, cardinality, ช่วงงวด) แล้วให้ LLM แค่เรียบเรียง · (ข) LLM จากชื่อคอลัมน์ + ตัวอย่าง 5 ค่า (เดาเก่ง แต่ `unit` → "หน่วย") · (ค) ไม่ร่าง ให้คนเขียนทั้งหมด | **(ก)** — ร่างทุกตัวเป็น `inferred` รอคนรับ ไม่ทับ `declared`/`manual` |
| **M-9** | คำอธิบายที่คนรับแล้วอยู่ที่ไหนในระยะยาว | (ก) **ไหลกลับ contract** (export เป็น `col_meta` ให้เจ้าของข้อมูลวางใน `domains.py` → PATCH) · (ข) อยู่ใน config.db เป็น `manual` ตลอด | **(ก)** — D-1 ที่มาเดียว; ระหว่างรอ contract แถว `manual` ยังใช้ได้และ contract ไม่ทับ (`may_replace`) |
| **M-7** | ขอบเขตของ Phase C รอบแรก | (ก) **revenue + sales** (ถามบ่อยสุดบน portal, มี target ให้ทำ `achievement` ต่อได้) · (ข) ทั้งสามโดเมน | **(ก)** — expense รอบถัดไป (`is_negative_reversal`, `overrides` ซับซ้อนกว่า) |

---

## 3. Phase A — มองเห็นเส้นทางของทุกคำถาม (AI, เล็ก, ขึ้นได้ทันที)

### A-01 — `plan()` บอกเหตุผลที่ปฏิเสธ
ALLOWED: `app/services/ai/metric_compiler.py`, `app/services/ai/hybrid_flow.py` (จุดเรียก `plan()` เท่านั้น), `tests/unit/test_metric_intent.py`, `tests/unit/test_metric_compiler.py`
- เพิ่ม `plan_with_reason(...) -> tuple[CompileRequest | None, str | None]`; `plan()` เดิมเป็น wrapper (API เดิมไม่เปลี่ยน)
- รหัสเหตุผลเป็นชุดปิด (string คงที่ ใช้ branch/นับได้): `no_metric`, `mapping_triggered:<keyword>`, `period_filter:<operator|value>`,
  `shape:intent_type:<type>`, `shape:dimension:<name>`, `shape:filter:<column|operator>`, `shape:ordering:<column>`, `reference_missing`, `time_range_invalid`
- `hybrid_flow`: `trace.stages["metric_declined"] = reason` + `logger.info("Metric declined: %s", reason)` (บรรทัดเดียว ไม่มี SQL/ค่าข้อมูล); ตอน compile สำเร็จยังตั้ง `metric_compiled` เหมือนเดิม
- Tests: ทุก `return None` ใน `plan()` มีเหตุผลที่ตรงกับ test หนึ่งข้อ (parametrize ครอบทุกรหัส); `plan()` เดิมคืนค่าเท่าเดิมทุก test ที่มีอยู่
Acceptance: ACC-T, ACC-L

### A-02 — `query_audit.metric_path` + สัดส่วน compiled ใน admin stats (M-1)
ALLOWED: `app/models/*audit*.py` (model ของ `query_audit`), `scripts/migrate_query_audit_metric_path.py` (new, idempotent: `ALTER TABLE ADD COLUMN` เมื่อยังไม่มี),
`app/services/*audit*.py` (จุดเขียน audit), `app/services/query_engine.py` (ส่งค่าจาก trace → audit), `app/api/v1/admin/analytics.py`, `tests/unit/test_query_audit_metric_path.py` (new), `tests/unit/test_admin_analytics*.py`
- ค่า: `compiled:<metric_id>` / `declined:<reason>` / NULL (context ไม่มี metric หรือ cache hit → คัดลอกค่าของคำตอบที่ cache)
- server เริ่มได้แม้คอลัมน์ยังไม่มี (เขียน audit แบบไม่มีคอลัมน์นี้ + warning ครั้งเดียว) — เหมือนหลัก `schema_metrics` ใน run ก่อน
- `/admin/stats` เพิ่ม `metric_path` ต่อ context: `{compiled, declined, none}` 7 วันล่าสุด + top 5 เหตุผล `declined` — นี่คือตัวชี้วัด #5
- Tests: migration idempotent; เขียน audit ทั้งสามค่า; stats นับถูกจาก fixture; DB ที่ไม่มีคอลัมน์ไม่ทำให้ request ล้ม
Acceptance: ACC-T, ACC-L · **ขึ้นจริง:** รัน migration บน `app.db` จริง (สำรองก่อน) → ff main

---

## 4. Phase D — Eval ที่สร้างเองจากคำประกาศ (AI, ไม่แตะ prompt path)

### D-01 — ตัวสร้างคำถาม + oracle
ALLOWED: `scripts/eval/gen_metric_questions.py` (new), `scripts/eval/metric_eval_lib.py` (new), `tests/unit/test_gen_metric_questions.py` (new), `tests/fixtures/ebt_metrics_1_5_0.yaml` (อ่านอย่างเดียว)
- อินพุต: contract (`--contract <yaml>`) + dist (`--dist <dir>` มี parquet) + งวดอ้างอิง (`--period 202609`)
- สร้าง case = ผลคูณของ **รูป** × **metric** × **ชุดคำพ้อง**:
  - รูป: total (official), by `<dim>` (ทุกมิติที่ประกาศ), filter เดี่ยว (`<dim> = <ค่าจริงจาก parquet>` 3 ค่าต่อมิติ), top-N by `<dim>` (N ∈ {5, 10}, DESC/ASC), month vs cumulative
  - คำถามไทย ≥ 3 แบบต่อรูปจาก template + คำพ้องของ metric (`synonyms`) + ชื่อมิติ (`*_fname`, `unit_short_name`, รหัส cost_center) — template อยู่ในไฟล์ lib ไม่ hardcode ใน test
  - expected = ผลของ `metric_compiler.compile(CompileRequest(...))` รันบน DuckDB เหนือ parquet (M-6 ก) — เก็บเป็นแถว `(dims..., value)` ปัดทศนิยม 2
- เอาต์พุต JSON (`scripts/eval/generated/<domain>_<period>.json`) รูปเดียวกับ `portal_real_questions.json` + ฟิลด์ `class` (รูป×metric), `expected_rows`, `request`
- Tests: จำนวน case ต่อรูปตามสูตร; ทุก case compile ได้; expected ของ total ตรง `fact_ebt_total_monthly.ebt` ของ fixture DuckDB เดิมใน `test_metric_compiler.py`
Acceptance: ACC-T, ACC-L

### D-02 — ตัววิ่งและการให้คะแนนเป็นชั้น
ALLOWED: `scripts/eval/run_metric_eval.py` (new), `scripts/eval/metric_eval_lib.py`, `tests/unit/test_run_metric_eval.py` (new), `docs/EVAL_HARNESS.md` (เพิ่มหัวข้อ)
- เรียก `POST /api/v1/query/` (`include_data: true`, `context`, `source: "eval"`) ที่ `--base-url` (default `http://localhost:8001` = server ซ้อมบนสำเนา) — **ห้าม default port 8000**
- ให้คะแนนต่อ case: แถวตรงทั้งชุด (ค่าใน `data` เทียบ expected, tolerance 0.5 บาท, ลำดับสำคัญเมื่อเป็น top-N) → `pass`; เก็บ `metric_path` จาก response ถ้ามี (A-02) หรือจาก audit บนสำเนา
- **รายงานเป็นชั้น**: ตาราง `class → pass/total`, แยก `compiled` vs `free-SQL`; `--score <json>` ให้คะแนนซ้ำไม่เรียก LLM (เหมือน `run_portal_questions.py`)
- `--period` ใหม่ = สร้างชุดใหม่จากข้อมูลเดือนใหม่ด้วยคำสั่งเดียว (นี่คือคำตอบของ "ข้อมูลวันข้างหน้า")
- Tests: scorer กับ response จำลอง (ตรง / ลำดับผิด / แถวขาด / ค่าเพี้ยน 1 บาท); รายงานรวมเป็นชั้นถูก
Acceptance: ACC-T, ACC-L · **วัดจริง (ไม่ใช่ slice ของ Codex):** server ซ้อม + `gen` ebt 202609 → `run` 1 รอบ → บันทึกผลเป็นชั้นลง `plan/RESULT_METRICS_CONVERGENCE.md` §D

---

## 5. Phase B — ตัวตรวจ SQL ของ pass 2 ตาม invariant ของ contract (M-2)

### B-01 — รู้ว่าคอลัมน์ไหน point-in-time ตอน request
ALLOWED: `app/models/schema_models.py`, `app/services/datafeed_knowledge.py`, `scripts/migrate_schema_contexts_measures.py` (new, idempotent), `tests/unit/knowledge_db.py`, `tests/unit/test_schema_metrics_sync.py` หรือไฟล์ test sync ที่มีอยู่
- `schema_contexts.measure_agg` (JSON `{column: "sum"|"point_in_time"}`) sync จาก `control_totals.measures[].agg` + `columns[].agg` ของ contract ทุก dataset (`datafeed_knowledge.py` บรรทัด ~153 มีการอ่านอยู่แล้ว — ใช้ที่เดียวกัน)
- server เริ่มได้แม้ยังไม่มีคอลัมน์; sync no-op + warning
- Tests: sync ebt → `{amount_ytd: point_in_time, amount: sum, ebt: point_in_time, ebt_month: sum, ...}`; re-sync idempotent; context legacy ไม่มีค่า
Acceptance: ACC-T, ACC-L

### B-02 — ตัวตรวจ invariant บน parse tree
ALLOWED: `app/services/ai/sql_invariants.py` (new), `tests/unit/test_sql_invariants.py` (new)
- อินพุต: SQL, `measure_agg`, ชื่อคอลัมน์งวดของ context (`scope_columns.year_month` ชื่อแรก) · ใช้ parse tree ของ DuckDB แบบเดียวกับ `check_select` (`app/services/database_adapter.py`) — ไม่ใช่ regex
- Invariants รอบแรก (แต่ละข้อคืนรหัสคงที่):
  - `I1 ytd_summed_across_periods`: `SUM`/`AVG` เหนือคอลัมน์ `point_in_time` ใน query block ที่เงื่อนไขงวด**ไม่ใช่** `= <ค่าเดียว>` (BETWEEN, IN หลายค่า, `>=`, ไม่มีเงื่อนไข) และ GROUP BY ไม่มีคอลัมน์งวด
  - `I2 ytd_without_period`: อ้างคอลัมน์ `point_in_time` โดยไม่มีเงื่อนไขงวดเลยใน block นั้น
  - `I3 month_summed_as_ytd` (เตือนเท่านั้น): `SUM(<sum-column>)` ข้ามหลายงวดใน context ที่มีคอลัมน์ `point_in_time` คู่กัน (`ebt_month` ↔ `ebt`) — บันทึก ไม่บล็อก
- ต้องผ่าน: SQL ของ `query_audit` 407 → `I1`; SQL ที่ compiler สร้าง (ทุก case จาก `test_metric_compiler.py`) → ไม่มี violation; CTE / subquery / alias ของตาราง / `CAST(time_key AS INTEGER)` ถูกมองทะลุ
Acceptance: ACC-T, ACC-L

### B-03 — ต่อเข้าเส้นทาง pass 2
ALLOWED: `app/services/ai/hybrid_flow.py`, `app/core/outbound.py` (เฉพาะถ้าต้องเพิ่มข้อความตายตัว — ห้ามสร้างชุดที่สอง), `tests/unit/test_hybrid_flow*.py`, `tests/integration/test_query_*`
- หลัง pass 2 ได้ SQL และก่อน execute: ตรวจ invariant เมื่อ context มี `measure_agg`; violation → นับเป็นความล้มเหลวของ attempt นั้น, ข้อความ retry บอกรหัส + คอลัมน์ (ภายใน prompt เท่านั้น) → ใช้ loop retry เดิม (`exec_a0/a1`)
- ครบ retry แล้วยังละเมิด → `error = query_failed` ข้อความตายตัวเดิม (M-2 ก); `trace.stages["invariant"] = "<code>"`; audit `error` คอลัมน์เดิม; **ไม่มี SQL/รหัสออกนอก process**
- เส้นทาง compile ไม่ผ่านตัวตรวจซ้ำ (compiler คือผู้รับรอง) — แต่ test ยืนยันว่าถ้าผ่านก็ไม่มี violation
- Tests: mock pass 2 คืน SQL 407 → retry ด้วยข้อความที่มีรหัส → คืน SQL ดี = ตอบได้; คืน SQL เสียทุกครั้ง = `query_failed`; context ไม่มี `measure_agg` = ไม่ตรวจ
Acceptance: ACC-T, ACC-L · วัด: รัน Phase D ซ้ำ — จำนวน case ที่ "ผิดอย่างมั่นใจ" ต้องเป็น 0 (กลายเป็น pass หรือ `query_failed`)

---

## 6. Phase C — ขยาย `metrics:` ไป revenue / sales (M-4, M-5, M-7)

### C-00 — ส่วนขยาย compiler (AI, ทำก่อน NT-Report)
ALLOWED: `app/services/ai/metric_compiler.py`, `app/services/datafeed_knowledge.py` (sync ฟิลด์ใหม่), `app/models/schema_models.py` (ถ้าต้องเพิ่มคอลัมน์ JSON — ใช้ `period`/`dataset` JSON เดิมได้ให้ใช้ก่อน), `tests/unit/test_metric_compiler.py`, `tests/fixtures/*.yaml`
- **M-4 ก** `datasets: [{name, dimensions: [...]}]` (เลือกตารางเล็กสุดที่มีมิติ+ตัวกรองที่ขอครบ; ไม่มีตารางไหนครบ → `plan()` ปฏิเสธด้วย `shape:dimension_set`) — `dataset:` เดิมยังใช้ได้ (= รายการเดียว)
- **M-5 ก** `period.value.cumulative: {range: true}` สำหรับ metric ที่ทุก term อ้าง measure `agg: sum`: `WHERE period BETWEEN year*100+1 AND period` — ปฏิเสธถ้า term ใดอ้างคอลัมน์ `point_in_time` (ห้ามบวกข้ามงวด)
- `terms` ที่มี `where` ว่าง = ทั้งตาราง (revenue ไม่มี measure_type) — ต้องชัดใน grammar และ test
- `official_total`/`reference` เหมือนเดิม; `supports()`/`plan()` ไม่เปลี่ยนรูป
- Tests: DuckDB + SQLite synthetic ของ revenue (3 grain tables, BG8 ytd ≠ sum รายเดือน) และ sales (amount + metric column + range cumulative); เลือกตารางถูก; range cumulative ตรง SUM มือ; point_in_time + range → ValueError
Acceptance: ACC-T, ACC-L

### C-01 — contract revenue + sales (NT-Report worktree)
ALLOWED (repo NT-Report): `tools/feed/domains.py`, `tools/feed/test_metrics_contract.py`, `DataFeed/contracts/{revenue,sales}.yaml` (ผลจาก `gen_contract.py` เท่านั้น), `DataFeed/README.md`
- revenue: `revenue` (`cumulative: revenue_ytd` point-in-time, `month: revenue`; datasets ตาม grain: total/bu/service_group/product/subproduct/org/org_product/org_subproduct; dimensions = union ของคอลัมน์มิติ; official_total = `fact_total_monthly`), `revenue_target` (fact_*_target_monthly, month เท่านั้น), `revenue_achievement` = `revenue / revenue_target` (extends, ratio) — ชื่อไทย/คำพ้องจาก `public_terminology`
- sales: `sales_amount` (fact_sales, `metric` column เป็น term ตาม `sales_metric_selection`, cumulative range), `sales_target` (fact_sales_target_monthly), `sales_achievement`; official_scope ตาม `sales_total_scope`; `sales_is_not_revenue` อยู่ใน `note_th`
- bump PATCH (`2.3.3`, `1.3.4`) → `gen_contract.py` → `pytest tools/feed` → `build_feed.py` ลง dist **สำเนา** (`.ai/dist/`)
- `test_metrics_contract.py`: ทุกคอลัมน์ที่ metric อ้างมีใน dataset ที่ประกาศ; `reference.control_totals` ตรง measure; achievement เป็น ratio ของ metric ที่มีจริง
Acceptance: `pytest tools/feed` เขียว; `python -c "yaml.safe_load"` ทั้งสองไฟล์; AI: `sync_knowledge` บนสำเนาได้ `schema_metrics` ของ revenue/sales (ตรวจด้วย SQL บน `.ai/db/config.db`)

### C-02 — วัดและขึ้นของจริง
- Phase D `gen` + `run` กับ revenue/sales 202609 บนสำเนา: บันทึก `class → pass/total` และ `metric_path` ก่อน/หลัง ลง `plan/RESULT_METRICS_CONVERGENCE.md` §C
- ขึ้นจริงตามลำดับ `docs/DECLARED_METRICS.md` §5: AI code (ff main) → contract/dist ของ NT-Report → ตรวจ `schema_metrics` ของจริง → ถามจริงผ่าน portal key และ nt-ai 1 คำถามต่อ metric

---

## 6b. Phase C-0b — คำศัพท์ระดับหน่วยงานถึงโมเดลทุกโดเมน (พบ 2026-10-24 บ่าย, ทำได้ก่อน C)

หลักฐาน: "ฝ่ายที่มี ebt สูงสุด 5 อันดับแรก" ตอบระดับสายงานแม้ contract/prompt/catalog บอกแล้วว่า ฝ่าย = `unit`; ที่ตัดสินคือ **`master_hierarchy`** (level note ของ pass 1)
ซึ่ง feed context ไม่เคยมี — ทำให้ feed_ebt แล้วด้วยมือ (5 ระดับ `manual`); ดู changelog `DECLARED_METRICS_2026_10_24.md` §แก้หลังขึ้นจริง

ALLOWED: `app/services/datafeed_knowledge.py`, `app/services/hierarchy_service.py`, `app/services/ai/hierarchy_context.py`, `tests/unit/test_hierarchy*.py`, `tests/unit/test_schema_metrics_sync.py`
- **ที่มาเดียว**: contract ประกาศ `org_levels:` (หรืออ่านจาก desc ที่มี "ระดับ N") → `sync_knowledge` เขียน `master_hierarchy` `declared` ของ context นั้น (provenance เหมือน `schema_metrics`;
  แถว `manual` ที่คนเขียนยังชนะ); keywords ตรวจจับ = คำของระดับ + "ราย<ระดับ>"; ห้ามใช้ "ส่วน" / "กลุ่ม" โดด (ชน ส่วนลด / กลุ่มธุรกิจ)
- **หลาย hierarchy ต่อ context**: revenue มีผลิตภัณฑ์ 3 ระดับอยู่แล้ว + หน่วยงาน 4 ระดับ → ตาราง `UNIQUE(context_name, level)` ไม่พอ → ตัดสิน: (ก) คอลัมน์ `chain` ใน `master_hierarchy` (migration) · (ข) level 10–14 สำหรับหน่วยงานโดย `format_level_note` แยก chain ตามช่วง · (ค) context ละ chain เดียว (ไม่ทำ revenue)
- **test ที่พิสูจน์ว่าความรู้ถึงโมเดล**: สำหรับทุก field ที่ sync ลง DB (description, hierarchy, metrics) มี test ว่า text นั้นอยู่ใน prompt ของ pass 1 จริง (`extract_intent` header) — ชั้นแบบนี้ eval คำถามเดี่ยวจับไม่ได้
Acceptance: ACC-T, ACC-L; วัดด้วย Phase D: คำถาม "<ระดับ>ไหน <metric> สูงสุด N อันดับ" ทุกระดับ × ทุกโดเมนที่มี metric → GROUP BY คอลัมน์ของระดับนั้น

## 6c. Phase E — คำอธิบายคอลัมน์ feed แบบอัตโนมัติ → admin รับ → ไหลกลับ contract (M-8, M-9)

สภาพ 2026-10-24 (นับจาก config.db จริง): context เดิมมี description/ชื่อไทยครบ 100% (คนเขียน, `manual`); **feed_* 36 ตาราง**
มี description 15–60% ใน fact / ~10% ใน dim, `display_name_th` = 0, `special_notes` = 0 — ผู้เขียนคนเดียวคือ contract และ
`gen_contract` เติม `''` ให้คอลัมน์ที่ `col_meta` ไม่พูดถึง. เครื่องมือ auto มีอยู่แล้ว 2 ตัวแต่ไม่ครอบ feed: **Context Onboarding**
(`/admin/contexts/onboard` — inspect + profile + LLM ร่าง metadata/rules ครบชุด) เปิด business DB ด้วย sqlite path จึงไม่เห็น
feed ที่เป็น DuckDB บน parquet; **Analyzer** (`/analyze/ai-suggest` → `import` เป็น `inferred`) ต้อง upload schema เอง.
web admin หน้า Schema แก้ `display_name_th` / `description` / `special_notes` ต่อคอลัมน์ได้แล้ว (PUT `/admin/schema/columns/{id}`) และ
`may_replace` รับรองว่า contract ไม่ทับของคน

### E-01 — inspector อ่าน feed source ได้
ALLOWED: `app/services/context_onboarding.py`, `app/services/data_sources.py` (เฉพาะ helper เปิด engine อ่านอย่างเดียวของ source), `app/api/v1/admin/onboarding.py` (`available-views` รวมตาราง feed), `tests/unit/test_context_onboarding*.py`
- `ViewInspector` รับ engine/connection แทน sqlite path: legacy = sqlite เดิม, feed = DuckDB ของ `data_sources` (อ่านอย่างเดียว, เคารพ `llm_data_policy`: source ที่ไม่ใช่ `full` profile ได้แต่**ไม่ส่งค่าตัวอย่างให้ LLM** — `_values_allowed` มีอยู่แล้ว ใช้ที่เดียวกัน)
- `available-views` แสดงตาราง `feed_*` พร้อม % คอลัมน์ที่ description ว่าง
- Tests: inspect ตาราง DuckDB จาก parquet synthetic (fact_ebt ย่อ) ได้ profile เท่ากับ sqlite เดิม; policy ไม่ใช่ full → ไม่มีค่าใน prompt
Acceptance: ACC-T, ACC-L

### E-02 — ร่างจาก profile ค่าจริง เป็น `inferred` รอคนรับ (M-8 ก)
ALLOWED: `app/services/context_onboarding.py` (หรือ `app/services/column_drafts.py` new), `app/api/v1/admin/schema.py` (`POST /schema/columns/draft?table=`), `app/services/provenance.py` (ใช้ `propose` เดิม ห้ามแก้กฎ), `frontend-admin/src/pages/Schema.tsx` (ปุ่ม "ร่างคำอธิบาย" + ป้าย `inferred/proposed` + รับ/ปฏิเสธ), `tests/unit/test_column_drafts.py` (new)
- heuristics ก่อน LLM (deterministic, ทดสอบได้): (1) **prefix ของค่า** ≥ 60% ของค่าที่ไม่ซ้ำขึ้นต้นคำเดียวกัน ("ฝ่าย", "ส่วน", "กลุ่ม", "สายงาน") → ระดับหน่วยงาน + ป้อน C-0b;
  (2) คอลัมน์คู่ `x` / `x_fname` / `x_sname` / `x_short_name` ที่ค่าสัมพันธ์ 1:1 → "ชื่อเต็ม/ชื่อย่อของ x"; (3) key/fk จาก contract → "รหัส… (join …)"; (4) `agg`/dtype/unit จาก contract → ประโยค SUM ได้/ไม่ได้; (5) งวด (YYYYMM, ช่วง min–max)
- LLM ใช้แค่**เรียบเรียง**ประโยคไทยจาก facts ข้างบน (ไม่เดาจากชื่อ) — ผ่าน provider ของ context ตาม policy; ไม่มี facts = ไม่ร่าง (ว่างดีกว่าเดาผิด)
- เขียนเป็น `inferred` + `status=proposed` ด้วย `propose()` เฉพาะคอลัมน์ที่ description ว่าง และไม่มีแถว `manual`/`declared` ที่มีค่า; คนรับในหน้า Schema → `manual`; ปฏิเสธ → `rejected` (contract เขียนทับไม่ได้ตามกฎเดิม)
- Tests: synthetic fact_ebt → ร่างของ `unit` มีคำว่า "ฝ่าย" และระดับ, ของ `unit_short_name` อ้าง `unit`, ของ `amount_ytd` บอกห้าม SUM ข้ามงวด; คอลัมน์ที่มี description แล้วไม่ถูกแตะ; รันซ้ำ idempotent
Acceptance: ACC-T, ACC-L · วัด: % คอลัมน์ feed ที่ description ว่าง ก่อน/หลัง (เป้า < 10% หลัง admin รับ)

### E-03 — ไหลกลับ contract (M-9 ก)
ALLOWED: `scripts/export_col_meta.py` (new), `tests/unit/test_export_col_meta.py` (new), `docs/DATAFEED_INTEGRATION.md` (หัวข้อใหม่)
- อ่าน `schema_metadata` ที่ `source='manual'` ของ context feed → พิมพ์ snippet `col_meta` ของ `tools/feed/domains.py` (python dict, เรียงตามคอลัมน์, รวม `display_name_th` เป็นคำแรกของ desc เพราะ contract ไม่มีช่องชื่อไทย) ให้เจ้าของข้อมูลวาง → PATCH → เมื่อ contract ประกาศแล้ว sync เห็นว่าค่าเท่ากัน แถว `manual` คงอยู่ (คนยังเป็นเจ้าของ) — ไม่มีความขัดแย้ง
- ถ้าต้องการให้ contract เป็นเจ้าของอีกครั้ง: admin ลบแถว `manual` → sync ครั้งถัดไปเขียน `declared` (พฤติกรรมเดิม) — บันทึกเป็นขั้นตอนใน docs
Acceptance: ACC-T, ACC-L; รันกับ config.db สำเนาแล้ว snippet วางใน `domains.py` ของ worktree NT-Report → `gen_contract` → `pytest tools/feed` เขียว

ลำดับกับ phase อื่น: E-01 ก่อน C-0b (hierarchy อัตโนมัติใช้ profile เดียวกัน) · E ทั้งหมดไม่แตะ prompt path จึงขึ้นของจริงได้ทันทีหลัง review

## 7. งานที่ไม่อยู่ในแผนนี้ (บันทึกไว้ไม่ให้หลง)

- expense metrics (M-7 ข), `is_negative_reversal` / `overrides_audit_layer` — รอบถัดไปหลัง C-02
- trend / comparison ข้ามงวด (`intent_type` อื่น) บนเส้นทาง compile — ต้องออกแบบ "สองงวด" ก่อน (RESULT_P8_DECLARED_METRICS "ยังไม่ทำ")
- admin UI สำหรับ metric `manual`; `metric` ใน REST/MCP response (มีประโยชน์กับ D-02 แต่ไม่จำเป็น — ใช้ audit บนสำเนาแทน)
- oracle จาก NT-Report (D-6 ข) — เมื่อ `fact_ebt_org_monthly` ขึ้น เพิ่มเป็น oracle ที่สองใน D-01 (`--oracle nt-report`)
- Phase A/B ไม่เปลี่ยนคำตอบใด ๆ ของคำถามที่ตอบถูกอยู่แล้ว — ถ้า eval ชั้นใดลดลงหลัง B-03 ให้ถือว่า invariant นั้นผิด ไม่ใช่คำตอบ

## 8. วิธีสั่ง /delegate (ตัวอย่าง)

```
/delegate ทำตาม plan/PLAN_METRICS_CONVERGENCE.md Phase A (slice A-01, A-02) ใน worktree นี้ บน branch จาก main;
ข้อตัดสิน M-1 = ก, M-3 = ก; acceptance ACC-T/ACC-L ตาม §0; หยุดก่อนรัน migration บน app.db จริง
```
Phase ถัดไปสั่งแยก run (D แล้ว B แล้ว C-00; C-01 เป็น run ในโปรเจกต์ NT-Report) — แต่ละ run จบด้วยการเติม `plan/RESULT_METRICS_CONVERGENCE.md`
