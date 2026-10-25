# RESULT — Metrics convergence (`plan/PLAN_METRICS_CONVERGENCE.md`)

> ไฟล์นี้เติมท้ายทุก run ของแผน (§8): A → D → E → B → C-0b → C-00/C-01 · หนึ่งหัวข้อต่อ phase

| Phase | สถานะ | วันที่ | commit (AI) |
|---|---|---|---|
| **A** มองเห็นเส้นทางของทุกคำถาม | ✅ **ขึ้นของจริงแล้ว** + push (CI เขียว run 40091378614) | 2026-10-24 | `34845de`, `655faeb` |
| **D** eval ที่สร้างเองจากคำประกาศ | ✅ **ขึ้นของจริงแล้ว** (main `011cef3`, reload 22:35) + push (CI เขียว run 40107701402) — วัดบน server ซ้อม: 96 → 157/174 หลังแก้ `plan()` | 2026-10-24 | `4cb8c62`, `ecdcc84`, แก้ `plan()` `3cd4e6c` |
| **E** คำอธิบายคอลัมน์ feed อัตโนมัติ | ✅ **ขึ้นของจริงแล้ว** (main `092f33f`, reload 23:47; ยังไม่ push) — วัดบนสำเนา: คำอธิบายว่าง 49.3% → 23.8% | 2026-10-24 | `3340f31`, `fc19128`, `fca9163`, `6826f75`, `cc0dfce` |
| **B** ตัวตรวจ SQL ของ pass 2 | 🟡 **ทำแล้วบน branch `ai/delegate-20261025-0951` — รอเจ้าของสั่งขึ้น** (ไม่ ff main, ไม่ push) — B-01 ข้าม; วัดบน server ซ้อม: 156 → 160/174, ผิดอย่างมั่นใจ 14 → 10 (ชั้น invariant 0 → 0) | 2026-10-25 | `aee811c`, `9ef7cf0`, `d8ce4e6`, `553566b`, `233daa1` |
| C-0b คำศัพท์ระดับหน่วยงานทุกโดเมน | ⬜ ยังไม่ทำ (ระหว่างนี้ feed_ebt + feed_expense เป็นแถว `manual` — §A.6) | | |
| C-00/C-01 metrics ของ revenue / sales | ⬜ ยังไม่ทำ | | |
| C-0c ratio จัดอันดับอย่างมีความหมาย | ✅ ทำก่อนแผนนี้ (`941cd0a`, ebt 1.6.0) | 2026-10-24 | |
| **CMP** เทียบสองงวดบนเส้นทาง compile (`plan/PLAN_METRICS_COMPARISON.md`) | ✅ **ขึ้นของจริงแล้ว** (main `862915c` = merge กับ Phase E, reload 07:32 2026-10-25) + push — วัดบน server ซ้อม: ชุดเทียบปีก่อน 3 → 20/27 | 2026-10-25 | `a54f76a`, `0a32b92` |

---

## A. มองเห็นเส้นทางของทุกคำถาม (A-01, A-02) — 2026-10-24

**วิธีทำ:** `/delegate` run `20261024-1805` ใน worktree `_worktrees/AI-metrics` (branch `ai/delegate-metrics`, base `c38601d` = main) —
Claude วางแผน/ตรวจรับ, Codex เขียน code ทั้งหมด · 2 slice, slice ละ 1 รอบ (Codex 2 ครั้ง), Claude ไม่ได้แก้ code เอง ·
บันทึก run: `.ai/20261024-1805/` (plan, brief, review ต่อ slice — ไม่อยู่ใน git)
**ข้อตัดสินของเจ้าของ:** M-1 = ก (คอลัมน์ `query_audit.metric_path`), M-3 = ก (คง official_scope) ·
**เพิ่มเติมระหว่าง run:** การเพิ่มคอลัมน์ใช้แบบ (ก) — `ensure_table()` เพิ่มคอลัมน์ที่ขาดเองเหมือน `request_group` (ไม่ใช่ "เขียน audit โดยไม่มีคอลัมน์ + warning"
ตามข้อความเดิมใน §3) เพราะ ORM ใส่ทุกคอลัมน์ใน INSERT/SELECT; `scripts/migrate_query_audit_metric_path.py` เป็นตัวห่อสำหรับขั้นขึ้นจริง

### A.1 ที่สร้าง
| commit | เนื้อหา |
|---|---|
| `34845de` (A-01) | `metric_compiler.plan_with_reason()` คืน `(CompileRequest, None)` หรือ `(None, <รหัส>)`; `plan()` / `supports()` คืนค่าเดิมทุกกรณี · `hybrid_flow` ตั้ง `trace.stages["metric_declined"]` + log `Metric declined: <รหัส>` (บรรทัดเดียว ไม่มี SQL/ค่าข้อมูล) · +58 tests |
| `655faeb` (A-02) | `query_audit.metric_path` (Text, nullable) · `QueryEngineResult.metric_path` จาก trace (compiled ชนะ declined; cache hit คัดลอกค่าของคำตอบเดิม) · `/admin/stats` เพิ่ม `metric_path` · script migration · +16 tests |

**รหัสเหตุผล (ชุดปิด):** `no_metric` · `mapping_triggered:<keyword>` · `period_filter:operator` · `period_filter:value` · `shape:intent_type:<type>` ·
`shape:dimension:<name>` / `shape:dimension:invalid` · `shape:filter:<column>` (คอลัมน์ไม่ได้ประกาศ) / `shape:filter:<operator>` (คอลัมน์ประกาศแต่ operator/ค่าไม่รองรับ) / `shape:filter:invalid` ·
`shape:ordering:<column>` / `shape:ordering:invalid` / `shape:ordering:direction` · `shape:invalid` · `reference_missing` · `time_range_invalid` · `compile_error` (จาก hybrid_flow)
— รายละเอียดหลัง `:` เป็นชื่อในสคีมาเท่านั้น ตัดเหลือบรรทัดเดียว ≤ 64 ตัวอักษร; ค่างวด/ค่าตัวกรองไม่เข้าไปในรหัส
(รหัส `period_filter:<operator|value>` ในแผนตีความเป็นสองรหัสตายตัว; `shape:invalid` และ `compile_error` เพิ่มเพราะมีทางที่ code ไปถึงจริง)

**ค่าใน `query_audit.metric_path`:** `compiled:<metric_id>` · `declined:<รหัส>` · NULL = context ไม่มี metric, pass 1 ล้ม, mode mcp, คำถามซ้ำ (dedup),
แถว error/ปฏิเสธ, แถว report/DSR และ**ทุกแถวก่อน 2026-10-24 18:32**

**`/admin/stats` → `metric_path`** (ตัวชี้วัด #5): `{context: {compiled, declined, none, top_declined: [{reason, count}] ≤ 5}}` ย้อนหลัง 7 วัน,
ไม่นับ channel `report_download` / `report_export` / `dsr_erase` (channel NULL นับ) · หน้า admin ยังไม่แสดง — อ่านจาก response ของ API หรือ SQL:
```sql
SELECT context_name, metric_path, COUNT(*) FROM query_audit
WHERE created_at >= datetime('now', '-7 days') GROUP BY context_name, metric_path;
```

### A.2 ผลทดสอบ
| | baseline (`c38601d`) | slice 01 | slice 02 (`655faeb`) |
|---|---|---|---|
| ACC-T (pytest ทั้ง `tests`, python3.14, env แบบ CI, สำเนา `.ai/db`) | 1440 passed, 3 skipped | 1498 passed | **1514 passed, 3 skipped** |
| ACC-L (ruff E9,F63,F7,F82) | ผ่าน | ผ่าน | ผ่าน |
| CI GitHub (main) | เขียว | | **เขียว** run 40091378614 (1m26s) |

ตรวจเพิ่มโดย Claude: parse ด้วยไวยากรณ์ Python 3.10 + import โมดูลที่แก้ด้วย `venv/bin/python` (3.10 = server จริง) ผ่าน · test เดิมไม่ถูกแก้/ลบสักบรรทัด

### A.3 ขึ้นของจริง (2026-10-24)
| เวลา | ขั้น | ผล |
|---|---|---|
| 18:31 | สำรอง app.db (`sqlite3 .backup`) | `~/nt-ai-backups/a02-metric-path-20261024-183133/app.db` — integrity ok, 435 แถว |
| 18:31 | `scripts/migrate_query_audit_metric_path.py` กับ `/Users/seal/Documents/GitHub/AI/app.db` | "Added query_audit.metric_path." — 435 แถวเดิมเป็น NULL, integrity ok |
| 18:32 | ff `main` `c38601d..655faeb` | worker ของ `uvicorn --reload` เริ่มใหม่ 18:32:06 |
| 18:48 | push `main` | CI เขียว |

**ถอยกลับ:** `git revert 655faeb 34845de` บน main (คอลัมน์ที่เพิ่มแล้วทิ้งไว้ได้ — nullable, code เก่าไม่อ่าน) หรือคืน app.db จากไฟล์สำรองข้างบน

### A.4 ตรวจหลังขึ้น
- `GET /api/v1/admin/stats` ไม่มี token → 401 (route ทำงาน, ไม่ 500)
- เรียก `get_dashboard_stats()` ด้วย code ของ main บน app.db + config.db จริงแบบอ่านอย่างเดียว (`mode=ro`) ได้ `metric_path` ครบทุก context —
  ทุกแถวเป็น `none` เพราะเป็นคำถามก่อนคอลัมน์มี: feed_ebt 82 · feed_revenue 22 · feed_expense 16 · pl_costtype 8 · revenue 1
- คำถามจริงหลังขึ้น (audit 436–452, 17 แถว) เป็น feed_expense / expense ทั้งหมด → NULL ถูกต้อง (context ไม่มี metric)
- **ยังไม่เห็น `compiled:` / `declined:` จริงสักแถว** — ยังไม่มีคำถาม feed_ebt หลัง 18:32; ค่าแรกจะมาเมื่อมีผู้ถาม EBT

### A.5 ตัวชี้วัด #5 — % คำถามที่ตอบจากเส้นทาง compile
**ฐาน:** เริ่มนับ 2026-10-24 18:32 · มีเฉพาะ feed_ebt ที่มี metric ประกาศ (ebt, ebt_excluding_personnel, ebt_margin) จึงเป็น context เดียวที่ค่าไม่ใช่ NULL ได้
ตอนนี้ · วัดครั้งแรกเมื่อ feed_ebt มีคำถามจริง ≥ 20 ข้อ — บันทึก compiled / declined และ 5 เหตุผลแรกที่นี่ แล้วใช้จัดลำดับงานใน B / C-0b / D
(คำถามรูปที่ตกบ่อยสุดคือชั้นที่ต้องแก้ก่อน)

| วันที่ | context | compiled | declined | none | top declined |
|---|---|---|---|---|---|
| (รอข้อมูล) | feed_ebt | | | | |

### A.6 พบระหว่าง run (นอก Phase A) — ระดับหน่วยงานของ feed_expense
คำถามบน expense dashboard 2026-10-24: "ฝ่ายไหนมีค่าใช้จ่ายมากที่สุด" ตอบระดับสายงาน, "ขอส่วนงานที่มีค่า OT สูงสุด 10 อันดับ" GROUP BY รหัสศูนย์ต้นทุน —
สาเหตุเดียวกับ §6b ของแผน: `feed_expense` ไม่มี `master_hierarchy` เลย · แก้ด้วยข้อมูล (ไม่แตะ code) ใน session แยก:
5 ระดับ `manual` (ids 34–38) ลง config.db จริง 18:48, สำรอง `~/nt-ai-backups/feed-expense-hierarchy-20261024-184826/config.db` ·
ยืนยันบน portal จริง: audit 438 GROUP BY `unit_fname` (ฝ่าย), 437 GROUP BY `sub_unit_fname` (ส่วนงาน) · feed_sales ไม่ต้องเพิ่ม (ชื่อหน่วยงานอยู่บน fact)
→ ตอนนี้ feed 2 จาก 3 โดเมนที่มีคอลัมน์หน่วยงานพึ่งแถว `manual` — เหตุผลเพิ่มให้ทำ **C-0b** (contract ประกาศระดับ → sync เป็น `declared` ทุกโดเมน)

### A.7 ค้าง / ข้อสังเกต
- หน้า admin (`frontend-admin`) ยังไม่แสดง `metric_path` ของ `/admin/stats`
- เก็บกวาด (ไม่กระทบความถูกต้อง): `_validate_shape` กับ `_support_reason` ใน `metric_compiler.py` ตรวจรูปซ้ำกันสองที่ (แก้ที่หนึ่งต้องแก้อีกที่);
  `_metric_path_stats` ส่ง datetime ผ่าน `text()` แบบดิบ (พึ่ง datetime adapter ของ sqlite3 ที่ deprecated ตั้งแต่ Python 3.12)
- **คอลัมน์ใหม่ของ query_audit ขึ้นเองเมื่อ ff main** (`ensure_table()` ALTER ตอนเขียน audit ครั้งแรกหรือเปิด `/admin/stats`) — ลำดับที่ถูก: สำรอง → script → ff main
- ไฟล์ว่าง `app.db"` (มีเครื่องหมายคำพูดในชื่อ, 13:52) ใน main checkout — น่าจะมาจากตัวอ่าน `DATABASE_URL="sqlite:///./app.db"` ที่ไม่ตัดเครื่องหมายคำพูด; ยังไม่ได้ไล่
- CI เตือน: action ที่ใช้ Node 20 (`actions/checkout@v4`, `actions/setup-python@v5`) กำลังถูกเลิก และ `ubuntu-latest` กำลังย้ายไป Ubuntu 26

---

## D. Eval ที่สร้างเองจากคำประกาศ (D-01, D-02) + แก้ `plan()` จากผลวัด — 2026-10-24

**วิธีทำ:** `/delegate` run `20261024-2013` (worktree `_worktrees/AI-metrics`, branch `ai/delegate-metrics`, base `be89108` = main) —
Codex เขียน code 2 slice (slice 01 สองรอบ: รอบแรก brief ของ Claude ระบุ key คำอธิบายคอลัมน์ผิดเป็น `desc` แทน `description`),
Claude ตรวจรับและวัดผลเอง · ข้อตัดสิน M-6 = ก (oracle = compiler + parquet: ทดสอบ "ประตู" ไม่ใช่สูตร) ·
การแก้ `plan()` หลังวัด (`3cd4e6c`) Claude เขียนเองตามคำสั่งเจ้าของ · บันทึก run + ผลดิบ: `.ai/20261024-2013/` (ไม่อยู่ใน git)

### D.1 ที่สร้าง
| commit | เนื้อหา |
|---|---|
| `4cb8c62` (D-01) | `scripts/eval/gen_metric_questions.py` + `metric_eval_lib.py`: contract + dist (parquet) + งวด → ชุดคำถาม = รูป (total / by / filter 3 ค่าจริง / top5–10 ×DESC/ASC) × metric × เดือน/สะสม × มิติ, ≥ 3 แบบประโยคต่อ case (หมุนคำพ้องของ metric + คำเรียกมิติจาก `description` ของ contract) · expected = SQL ของ compiler รันบน DuckDB เหนือ parquet · มิติที่เป็นคอลัมน์ชื่อ (`*_fname` / `*_short_name`) และคอลัมน์ไม่ใช่ข้อความ (`is_hq`) ไม่ทำเป็น class · ไฟล์ออก `eval_results/` (git ignore เพราะมีตัวเลขและชื่อหน่วยงานจริง) · +19 tests |
| `ecdcc84` (D-02) | `scripts/eval/run_metric_eval.py`: ยิง `POST /api/v1/query/` ที่ server ซ้อม (ปฏิเสธ port 8000), ให้คะแนนรายแถว (บาท ±0.5 หรือรูปล้านบาท, percent ±0.01 หรือรูป ratio, top-N ต้องตรงตามลำดับ), อ่าน `metric_path` จาก `query_audit` ของสำเนา (`--audit-db`), รายงานเป็นชั้น class / (รูป, metric, โหมด) / รูป + แยก compiled / free-SQL + 5 เหตุผล decline · `--score` ให้คะแนนซ้ำไม่เรียก server · หัวข้อใหม่ใน `docs/EVAL_HARNESS.md` · +57 tests |
| `3cd4e6c` (แก้ `plan()`) | (1) ช่วงงวดที่เริ่มเดือนมกราคม (`BETWEEN y01 AND yMM`, `>=` คู่ `<=`, `IN` เดือนต่อเนื่อง, หรือ `<= yMM` เมื่อ `time_range.cumulative`) = ยอดสะสม ณ yMM; ช่วงอื่น (เช่น ก.ค.–ก.ย.) ปฏิเสธด้วยรหัสใหม่ `period_filter:range` · (2) mapping ที่ keyword เป็นคำเรียกมิติที่ metric ประกาศ (`dimension_labels` — สายงาน / กลุ่ม / ฝ่าย / ส่วน / ศูนย์ต้นทุน) ไม่บล็อกเส้นทาง compile · +21 tests (แก้พารามิเตอร์ test เดิม 4 ค่าที่คาดว่า `<=` / `BETWEEN 202601–202609` จะถูกปฏิเสธ) |

ผลทดสอบ: ACC-T 1514 → **1611 passed, 3 skipped**; ACC-L ผ่าน

### D.2 วิธีวัด
- ชุดคำถาม: ebt contract 1.6.0 + `NT-Report/DataFeed/dist/ebt/latest` (build `202609-20261024T104245Z`) งวด 202609 → 174 class / 702 คำถาม ·
  oracle ตรงตัวเลขที่ยืนยันแล้ว (EBT สะสม 570,852,985.68 · ไม่รวมบุคลากร 5,799,842,156.45 · อันดับ 1 ระยอง 130.03 ล้าน · margin ต่ำสุดนครนายก −13.8%)
- ตัวอย่าง: 1 คำถามต่อ class = 174 ข้อ, แบบประโยคหมุนตามลำดับ class (ไม่ใช่แบบที่ 0 ทุกข้อ) — ชุดเดียวกันทั้งก่อนและหลัง (จับคู่ได้)
- server ซ้อม 127.0.0.1:8001 บนสำเนา config.db / app.db / Chroma (`.ai/db/practice/`), key ซ้อม id 6 บนสำเนา, Python 3.10 (มี RAG), ไม่มี Telegram/อีเมล ·
  **ก่อน** = code ของ main `be89108` · **หลัง** = code ของ branch (`3cd4e6c`) · ความรู้/contract/ข้อมูลเท่ากัน · app.db จริงไม่ถูกแตะ

### D.3 ผล (ebt 202609, 174 คำถาม)
| | ก่อน (`be89108`) | หลัง (`3cd4e6c`) |
|---|---|---|
| **ถูกทั้งชุด** | **96 (55.2%)** | **157 (90.2%)** |
| ตอบด้วย compiler (ตัวชี้วัด #5) | 82 (47.1%) → ถูก 73 | **165 (94.8%)** → ถูก 155 |
| ตอบด้วย free-SQL | 92 → ถูก 23 (25%) | 9 → ถูก 2 |
| คู่ที่ต่างกัน | | หลังถูก/ก่อนผิด **64**, ก่อนถูก/หลังผิด 3 — **McNemar exact p = 6.8e-16** |

รายรูป (ก่อน → หลัง / n): total 6→6/6 · by 12→18/18 · filter 15→20/30 · top5_desc 14→28/30 · top5_asc 17→28/30 · top10_desc 17→30/30 · top10_asc 15→27/30

เหตุผล decline — ก่อน: `mapping_triggered:สายงาน` 35 (ถูก 19) · **`period_filter:operator` 30 (ถูก 2)** · `mapping_triggered:ส่วน` 14 · `ฝ่าย` 4 · `กลุ่ม` 2 · อื่น ๆ 7 ·
หลัง: `shape:filter:group_0` 4 · `shape:dimension:group_1` 2 · `mapping_triggered:เดือน…` 2 · `shape:intent_type:lookup` 1

สิ่งที่ผลบอก: ชั้นที่ตกบ่อยสุดสองชั้น (ยอดสะสมที่ส่งเป็นช่วงงวด = บั๊กเดียวกับ §1 ของแผน, และคำระดับหน่วยงานที่ถูกนับเป็น mapping) เป็นเหตุของ
คำถามที่ไปเส้นทาง free-SQL 85 จาก 92 ข้อ — แก้ที่ `plan()` สองจุดแล้วเหลือ free-SQL 9 ข้อ · ทาง compiler ถูก 94% (155/165)

### D.4 ที่ยังผิดหลังแก้ (17 ข้อ) → งานถัดไป
| กลุ่ม | ข้อ | ไปที่ |
|---|---|---|
| "กลุ่มไหน… / ส่วนไหน…" (คำโดด) pass 1 เลือก `division` | 2 | C-0b (คำระดับหน่วยงาน) — คนพิมพ์จริงมักใช้ "ส่วนงาน"; ตัวสร้างคำถามใช้คำแรกของ description ("ส่วน", "กลุ่ม") |
| ratio + ตัวกรองหน่วยที่เป็น HQ: pass 1 ใส่ทั้ง dimension และ filter ของหน่วยเดียวกัน → compiler ใส่ `ranking.scope` (`is_hq = 0`) → 0 แถว ("EBT Margin ของสายงานบริหารองค์กร", สายงาน กรรมการผู้จัดการใหญ่) | 2 (+ 3 ข้อในกลุ่ม oracle = NULL ถัดไปโดนแบบเดียวกัน) | **compiler**: ไม่ใส่ `ranking.scope` เมื่อทุกมิติที่ขอถูกกรองด้วย `=` (เป็นการถามหน่วยที่ระบุชื่อ ไม่ใช่การจัดอันดับ) — follow-up ของ C-0c |
| margin ของหน่วยไม่มีรายได้ (oracle = NULL) | 4 | eval: ตัวสร้างควรข้าม case ที่ค่าคาดหวังเป็น NULL หรือ scorer รับ "ไม่มีแถว/NULL" — ไม่ใช่ความผิดของ compiler |
| ค่า "กรรมการผู้จัดการใหญ่…" มีอยู่ทุกระดับ (กรองผิดระดับ) | 1 | ตัวสร้าง: ข้ามค่าที่ซ้ำในหลายระดับ |
| compiler กรอง `sub_unit LIKE '%ส่วนธุรกิจลูกค้าภาครัฐ 12%'` แล้วค่าไม่ตรง oracle | 1 | ยังไม่ได้ไล่ (LIKE ของชื่อหน่วยอาจตรงหลายหน่วย) |
| pass 1 ใส่ตัวกรอง `group_0` / มิติ `group_1` / intent `lookup` / mapping "เดือน…" | 7 | ความแปรปรวนของ LLM — B (ตัวตรวจ invariant) คือชั้นที่ป้องกันเส้นทาง free-SQL ที่เหลือ |

3 ข้อที่ก่อนถูกแต่หลังผิด: 2 ข้อเป็น margin ที่ oracle = NULL (กลุ่มที่ 3) และ 1 ข้อ pass 1 ใส่ `group_0` (ความแปรปรวน) — ไม่ได้มาจากการแก้

**ข้อสังเกตเพิ่ม (A-02):** เมื่อคำตอบของ compiler ถูกทิ้งแล้ว retry เขียน SQL เอง (`ranking.scope` ทำให้ไม่มีแถว) `metric_path` ยังเป็น `compiled:` —
ควรบันทึกเส้นทางของ attempt ที่ให้คำตอบสุดท้าย · ตัวรัน: `score_case` ล้มถ้า metric ไม่มี `unit`, และบันทึกผลตอนจบเท่านั้น (ใช้รันเป็นก้อนต่อรูปแทน)

### D.5 ข้อจำกัด / ขึ้นของจริง
- คำถามมาจาก template ไม่ใช่คนพิมพ์ — ยืนยันกับคำถามจริงด้วยตัวชี้วัด #5 ของ §A.5 หลังขึ้นของจริง · 1 ข้อต่อ class ตัวเลขราย class จึงแกว่ง ตัวเลขรายชั้น/รวมคือสัญญาณ
- **ขึ้นของจริงแล้ว 2026-10-24 22:35**: ff main `be89108..011cef3` → worker ของ `uvicorn --reload` เริ่มใหม่ 22:35:26 · push แล้ว CI เขียว
  run 40107701402 · `3cd4e6c` แตะ prompt path (เปลี่ยนว่าคำถามไหนไป compile) — วัดแล้วดีขึ้น 64 คู่ แย่ลง 3 (ไม่เกี่ยวการแก้) ·
  ถัดไป: ดู `metric_path` ของคำถาม EBT จริงใน `/admin/stats` (§A.5) · scripts/tests ของ D ไม่มีผลกับ server ·
  ถอยกลับ: `git revert 3cd4e6c` บน main (ไม่มี migration)
- รันชุดใหม่เมื่อข้อมูลเดือนใหม่: `gen_metric_questions --period <YYYYMM>` แล้ว `run_metric_eval` (คำสั่งใน `docs/EVAL_HARNESS.md`)

---

## E. คำอธิบายคอลัมน์ feed อัตโนมัติ (E-01, E-02, E-03) — 2026-10-24

**วิธีทำ:** `/delegate` run `20261024-2015` (worktree `_worktrees/AI-phase-e`, branch `ai/delegate-phase-e`, base `be89108`, merge main `011cef3` แล้ว) —
Codex เขียน code 5 slice (slice 02 สองรอบ: รอบแรกตัดคำนำหน้าตามช่องว่างซึ่งใช้กับชื่อหน่วยงานไทยไม่ได้ — ร่างได้ 2 จาก ~60 คอลัมน์),
Claude ตรวจรับและวัดผลเอง · ข้อตัดสิน M-8 = ก, M-9 = ก · ไม่มี LLM ในการร่าง (template ไทยจากข้อเท็จจริงที่วัดได้) ·
บันทึก run + probe: `.ai/20261024-2015/` (ไม่อยู่ใน git)

### E.1 ที่สร้าง
| commit | เนื้อหา |
|---|---|
| `3340f31` (E-01) | `DataInspector` อ่านผ่าน path หรือ SQLAlchemy Engine · `inspect` ของตาราง feed ไปที่ engine ของ source (`source_resolver.for_context`) ไม่ fallback ไป copy เก่า · `available-views` แสดงตาราง feed + `description_empty` / `description_empty_pct` · `/contexts/onboard/inspect` รับ feed (onboard / apply-sql ยังปฏิเสธ) |
| `fc19128` (E-02) | `app/services/column_drafts.py`: ข้อเท็จจริง = ระดับจาก `master_hierarchy`, คู่ `_fname/_sname/_short_name/_abbr`, คำนำหน้าจาก `level_label_th` (≥ 60%), YYYYMM / เดือน / ปี ค.ศ.–พ.ศ., คีย์ของ contract, agg/unit · เคารพ `llm_data_policy` (ไม่ full = ข้อเท็จจริงจาก contract เท่านั้น) · เข้าคิว `knowledge_proposals` เป็น `inferred` ผ่าน `propose()` · API `POST /admin/schema/columns/draft`, `GET …/drafts`, `POST …/drafts/{id}/accept` (→ `manual`/active), `…/reject` |
| `fca9163` (E-02 UI) | หน้า Schema: เลือกตาราง, "ร่างคำอธิบาย", แก้ข้อความแล้วรับ/ปฏิเสธ, ป้าย source/status |
| `6826f75` (E-03) | `python -m scripts.export_col_meta --context feed_<domain>` (อ่านอย่างเดียว): แถว `manual` + active → snippet `col_meta` สำหรับ NT-Report, รวมต่อคอลัมน์ทุกตาราง, ข้อความขัดกันออก stderr · หัวข้อใหม่ใน `docs/DATAFEED_INTEGRATION.md` |
| `cc0dfce` (แก้) | ข้อความร่างไม่ใส่รายชื่อคีย์ต่อตาราง ช่วงค่า และ % (เก็บใน `facts`) — `col_meta` ผูกชื่อคอลัมน์ทั้ง domain และช่วงปีจะล้าสมัยเมื่อเดือนใหม่เข้า |

ผลทดสอบ: ACC-T 1514 → 1569 (E อย่างเดียว) → **1666 passed, 3 skipped** หลัง merge main (รวม D); ACC-L ผ่าน; `npm --prefix frontend-admin run build` ผ่าน

### E.2 ผล (สำเนา config.db + CSV จริงของ DataFeed `dist/<domain>/latest`)
- ร่างครบ 36 ตาราง feed → 91 ร่าง · รับทั้งหมด: คำอธิบายว่าง **176/357 (49.3%) → 85/357 (23.8%)** — **ไม่ถึงเป้า < 10%**:
  คอลัมน์ที่เหลือ (เช่น `month_th`, `geo_cluster`, dim ส่วนใหญ่ของ expense 55/85) ไม่มีข้อเท็จจริงให้วัด จึงไม่ร่าง (ว่างดีกว่าเดาผิด) — ต้องให้คนเขียน
- export: ebt 3 · revenue 18 (ขัดกันจริง 2: `service_group_nt`, `service_group_seq` เป็นคีย์ในบางตาราง) · sales 8 · expense 6
- ทางกลับ (จำลองในหน่วยความจำแทนข้อ A6): ใส่ `desc` ที่ export ลง contract จริงทั้ง 4 แล้ว `sync_schema_metadata` → แถว `manual` เปลี่ยน 0/250 ·
  ข้อเสนอ `declared` ที่เปิดอยู่มาจากสองคอลัมน์ที่ไม่ได้ export เท่านั้น

### E.3 ข้อจำกัด / ขึ้นของจริง
- ยังไม่ได้ตรวจ: คลิก UI ใน browser จริง · NT-Report `gen_contract` + `pytest tools/feed` (worktree ใหม่ไม่มีข้อมูลดิบ)
- ไม่มี migration (`knowledge_proposals` มีอยู่แล้ว) · ไม่แตะ prompt path · ขึ้น = ff main + restart · การกด "ร่างคำอธิบาย" บนของจริงเขียนแถว `inferred`
  ลง `knowledge_proposals` ของ config.db จริง (ไม่มีผลกับคำตอบจนกว่าคนจะรับ)
- ยังไม่ทำ: ใช้ `fk` ของ contract เป็นข้อเท็จจริง · LLM เรียบเรียงข้อความ (ตัดออกตามข้อ A1)

### E.4 ขึ้นของจริง (2026-10-24 23:47)
- ff main `07543cd` → `092f33f` · uvicorn `--reload` (port 8000) เริ่ม worker ใหม่ 23:47:25 · route ใหม่ตอบ 401 (มีอยู่ ต้อง login) · admin vite (5173) เสิร์ฟ `Schema.tsx` ใหม่
- ก่อนขึ้น ซ้อมบน server 8002 + สำเนา config.db/app.db ด้วย call ชุดเดียวกับหน้า Schema (`feed_sales_fact_sales`): ร่าง 8 · รับ 1 (แก้ข้อความ) → แถว `manual`/active ·
  ปฏิเสธ 1 → proposal `rejected` แถวเดิมไม่เปลี่ยน · ร่างค้าง 6 · inspect ตาราง feed ได้ (114,235 แถว 25 คอลัมน์) · onboard ยังปฏิเสธ (400) ·
  ไม่ได้คลิกใน browser (extension ของ Chrome ไม่เชื่อมต่อ)
- NT-Report: **ยังไม่มีอะไรต้องส่ง** — config.db จริงมีแถวคอลัมน์ feed 357 แถวเป็น `declared` ทั้งหมด, export ทั้ง 4 domain ได้ 0 รายการ ·
  ทางกลับเริ่มเมื่อ admin รับร่างบนของจริงแล้ว: `export_col_meta` → `col_meta` ใน `tools/feed/domains.py` + PATCH → `gen_contract.py` → `build_feed.py` → `pytest tools/feed`

---

## B. ตัวตรวจ SQL ของ pass 2 ตาม invariant ของ contract (B-02, B-03; B-01 ข้าม) + ranking.scope ของหน่วยที่ระบุชื่อ — 2026-10-25

**วิธีทำ:** `/delegate` run `20261025-0951` (worktree `.claude/worktrees/vigorous-edison-ffcc57`, branch `ai/delegate-20261025-0951`,
base `1d004bc` = main) — Codex เขียน code 5 slice รอบเดียวทุก slice, Claude ตรวจรับและวัดผลเอง · ข้อตัดสิน **M-2 = ก** (fail closed) ·
บันทึก run + ผลดิบ: `.ai/20261025-0951/`, `.ai/eval/` (ไม่อยู่ใน git)

**ข้าม B-01** (`schema_contexts.measure_agg` + `scripts/migrate_schema_contexts_measures.py`) — ตัดสินโดย session ต้นทางแทนเจ้าของ:
agg ต่อคอลัมน์มีอยู่แล้วใน `schema_metadata` (`sync_schema_metadata` เขียน double + `is_summable` 0/1 จาก `columns[].agg` /
`control_totals.measures[].agg` ของ contract; `_cumulative_columns` อ่านแถว active) — ทำ B-01 = ที่เก็บ agg ชุดที่สอง + migration
config.db จริงโดยไม่ได้อะไรเพิ่ม · **ไม่มี migration ใน run นี้** · ข้อจำกัดที่ยอมรับ: admin แก้ `is_summable` ได้ (แถวเป็น `manual`) = การตัดสินของคน

### B.1 ที่สร้าง
| commit | เนื้อหา |
|---|---|
| `aee811c` (slice 01) | compiler: ไม่ใส่ `ranking.scope` (`is_hq = 0`) เมื่อทุกมิติที่ขอถูกกรองด้วย `=` บนคอลัมน์ของมันเอง (ถามหน่วยที่ระบุชื่อ ไม่ใช่จัดอันดับ) — ทั้งงวดเดียวและเทียบสองงวด · +11 tests |
| `9ef7cf0` (B-02) | `app/services/ai/sql_invariants.py`: `check(sql, point_in_time, summable, period_columns)` บน parse tree ของ DuckDB (`json_serialize_sql` แบบ `check_select`) — **I1** `ytd_summed_across_periods` (SUM/AVG ของคอลัมน์ point-in-time ใน block ที่ไม่ได้ปักงวดเดียว และไม่ GROUP BY งวด), **I2** `ytd_without_period` (อ้างคอลัมน์ point-in-time โดย block ไม่มีเงื่อนไข/คอลัมน์งวดเลย), **I3** `month_summed_as_ytd` (เตือนเท่านั้น) · มองทะลุ CTE / subquery / alias / `CAST` / `::` / `= (SELECT MAX…)` / `IN (ค่าเดียว)` / pivot `SUM(CASE WHEN งวด = X …)` / window `PARTITION BY งวด` · +99 tests: audit 407 → I1, SQL ของ compiler ทุกรูป (30 + ranking) → ไม่มี violation |
| `d8ce4e6` (B-03) | `hybrid_flow.cumulative_sum_error` (จุดเดิม — guard ชุดเดียว) เปลี่ยนจาก regex เป็น `sql_invariants.check`; ข้อความ retry ขึ้นต้นด้วย `<code> <name>: ` + คอลัมน์ (ใน prompt เท่านั้น); ตัวตรวจพัง → log แล้วปล่อยผ่าน · attempt สุดท้ายยังละเมิด → `error = "query_failed"`, explanation = `outbound.message("query_failed")`, `sql_query = ""`, `trace.stages["invariant"]`, **ไม่ใช้ tool-loop rescue** (SQL ที่ไม่มีใครตรวจ) · +18 tests |
| `553566b` (slice 04, พบจากการวัด) | pass 1 ส่งหน่วยที่ระบุชื่อเป็น `LIKE` ("EBT Margin ของสายงานบริหารองค์กร" → `division LIKE …` + มิติ division, ไม่มี ordering) → ยังโดน `is_hq = 0` → 0 แถว: กฎใหม่ = ทุกมิติมีตัวกรองบนคอลัมน์ตัวเอง และ (ทุกตัวเป็น `=` **หรือ** ไม่มี ordering); `LIKE`/`IN` ที่มี ordering ยังเป็นการจัดอันดับในขอบเขต · +8 tests |
| `233daa1` (slice 05) | `_double_columns` query เดียวของ schema_metadata; `_cumulative_columns` / `_summable_columns` เป็น wrapper (เงื่อนไขของ session ต้นทาง: ไม่คัด query ซ้ำ) · +1 test |

ผลทดสอบ: ACC-T 1708 → **1845 passed, 3 skipped**; ACC-L ผ่าน; import ด้วย Python 3.10 ผ่าน

**จุดที่ต่างจากแผน §5:** (1) เส้นทาง compile ยังผ่าน guard (test เดิม `test_precompiled_sql_still_runs_guards` ตรึงไว้ และ SQL ของ compiler ทุกรูปผ่าน) ·
(2) I3 ไม่จับคู่ `ebt_month ↔ ebt` ด้วยชื่อ — เตือนเมื่อ SUM คอลัมน์ summable ข้ามงวดในตารางของ context ที่มีคอลัมน์ point-in-time (ทั้งสองรายการจาก schema_metadata ชุดเดียว; จับคู่รายคอลัมน์ต้องเดาชื่อ) ·
(3) จุดที่ ~1667 (`_cumulative_columns` ใน prompt ยอดสะสม) ไม่ใช่ guard — ไม่เปลี่ยน

### B.2 วิธีวัด
- ชุด 174 ข้อของ §D (ebt 202609, 1 ข้อต่อ class, ชุดเดียวกัน) + ชุด portal (NT-Report `DataFeed/eval/portal_questions_{revenue,sales,expense,ebt}.json` + `scripts/eval/portal_real_questions.json`)
  — ชุดหลังคือเส้นทาง free-SQL ที่มีคอลัมน์ YTD (`revenue_ytd`) ซึ่งชุด ebt ไม่แตะ
- server ซ้อม 127.0.0.1 บนสำเนาแยกต่อ server ของ config.db / app.db / Chroma (สำรอง 09:50 แบบ read-only) + สำเนา `nt_fi_report.sqlite`, key ซ้อม id 6 บนสำเนา,
  Python 3.10 (มี RAG), ไม่มี Telegram/อีเมล · **ก่อน** = main `1d004bc` (port 8023, worktree แยก) · **หลัง** = branch `233daa1` (port 8024) ·
  ตรวจหลัง B (slice 01–03 เท่านั้น, port 8022) ด้วย · app.db / config.db จริงไม่ถูกแตะ (api_keys สูงสุดยังเป็น 5)
- "ผิดอย่างมั่นใจ" = ไม่มี error, มีแถวที่มีค่า, ไม่ตรง oracle · "ชั้น invariant" = SQL ของคำตอบนั้นละเมิด I1/I2 (ตรวจย้อนด้วย `sql_invariants.check`)

### B.3 ผล
| ชุด ebt 174 ข้อ | ก่อน (`1d004bc`) | หลัง B (`d8ce4e6`) | **หลัง (`233daa1`)** |
|---|---|---|---|
| ถูก | 156 | 157 | **160** |
| ผิดอย่างมั่นใจ | 14 | 11 | **10** |
| — ในนั้น SQL ละเมิด I1/I2 | 0 | 0 | **0** |
| ตอบไม่ได้ (query_failed / ไม่มีแถว) | 4 | 6 | 4 |
| ตอบด้วย compiler | 167 | 166 | 166 |

คู่ ก่อน → หลัง: หลังถูก/ก่อนผิด 5, ก่อนถูก/หลังผิด 1 (McNemar p = 0.22) · รายรูป: filter 20 → 22/30, top5_desc 27 → 29/30, อื่นเท่าเดิม ·
"EBT Margin ของสายงานบริหารองค์กร" และ "…สายงาน กรรมการผู้จัดการใหญ่…" (§D.4) ได้แถวจริงแล้ว (ก่อน: 0 แถว) · ข้อที่หลังผิด (M0527) และ 2 ข้อที่ยัง query_failed
คือ margin ของหน่วยรายได้ 0 (oracle = NULL; compiler ได้แถว NULL → นับเป็นไม่มีข้อมูล → retry ล้ม) = กลุ่ม "oracle NULL" ของ §D.4 ไม่ใช่ invariant ·
query_failed ข้อที่ 4 (M0196, free-SQL `shape:filter:group_0`) ก่อนหน้าเป็นผิดอย่างมั่นใจ — ล้มด้วยเหตุอื่น ไม่ใช่ fail closed ของ invariant

**ตัวตรวจย้อนกับผลรันเก่าทุกชุด** (SQL ที่บันทึกในผลรัน): be89108 (ก่อน §D) จับคำตอบผิดได้ 7 · 3cd4e6c 1 · ทุกชุด **จับคำตอบที่ถูก 0** —
ข้อเดียวที่ดูเหมือนจับผิด (0a32b92 M0646) คือ `SUM(amount_ytd) … BETWEEN 202501 AND 202512` ที่ละเมิดจริง แต่ "ถูก" เพราะ oracle เป็น NULL

| ชุด portal (ถูกครบ) | revenue | sales | expense | ebt | real | รวม |
|---|---|---|---|---|---|---|
| ก่อน | 9/10 | 9/10 | 9/10 | 11/14 | 7/15 | 45/59 |
| หลัง | 9/10 | 10/10 | 9/10 | 11/14 | 9/15 | **48/59** |

guard ทำงานจริงบนชุด portal ของหลัง 5 ครั้ง (I1 `revenue_ytd`: "รายได้สะสมตั้งแต่ต้นปีถึงเดือนกันยายน 2569", "รายได้สะสมของกลุ่ม Mobile", …) —
ทุกครั้ง retry ได้ SQL `year_month = <งวด>` และตอบได้; fail closed (attempt สุดท้ายยังละเมิด) **0 ครั้ง** · ชุด ebt 174 ข้อ guard ไม่ทำงานเลย (ไป compiler 95%)

**เทียบกับเกณฑ์ "ผิดอย่างมั่นใจต้องเป็น 0":** ชั้นที่ตัวตรวจรับผิดชอบ (SUM/อ้าง YTD ข้ามงวด) = **0** ทั้งก่อนและหลังบนชุดนี้ (main ส่ง 95% ไป compiler อยู่แล้ว) ·
ที่เหลือ 10 ข้อ **ไม่ใช่ความผิดเรื่องงวด** — pass 1 เลือกระดับผิด ("ส่วนไหน/กลุ่มไหน" → division, ตัวกรอง "กรรมการผู้จัดการใหญ่" ผิดระดับ),
LIKE ชื่อหน่วยตรงหลายหน่วย, หรือ free-SQL ใช้แถว `3.1 กำไร (ขาดทุน) ของส่วนงาน` แทนสูตร EBT 4 ก้อน — invariant เรื่องงวดจับไม่ได้โดยนิยาม

### B.4 ที่ยังเหลือ / ข้อจำกัด
- free-SQL ของ context ที่มี metric ประกาศแต่ใช้แถว/สูตรอื่น (`group_1 = '3.1 กำไร…'`, `group_1` เป็นมิติ) → ผิดอย่างมั่นใจ 4 ข้อ: invariant ถัดไปที่เป็นไปได้ = "context มี metric นี้แต่ SQL ไม่อ้าง term ของมัน" (ยังไม่ออกแบบ)
- ตัวตรวจรู้จักงวดจาก `scope_columns` เท่านั้น: `WHERE year = 2026 AND month = 9` (งวดเดียวผ่าน year + month) และ JOIN กับ CTE งวด ถูกนับว่าไม่ปักงวด →
  retry (regex เดิมก็ทำแบบเดียวกัน); บนชุด portal retry ได้ `year_month = …` ทุกครั้ง · ponytail: ตาราง fact ที่ JOIN กับ CTE ที่ปักงวดถือว่าปักงวด
- margin ของหน่วยรายได้ 0: compiler ได้แถว NULL → hybrid ถือว่าไม่มีข้อมูล → retry ด้วย LLM → `query_failed` (3 ข้อ) — ควรตอบ "ไม่มีรายได้ คำนวณ margin ไม่ได้" ตรง ๆ
- `metric_path` ยังเป็น `compiled:` เมื่อคำตอบของ compiler ถูกทิ้งแล้ว retry (ข้อสังเกตเดิมของ §D.4)
- **ยังไม่ขึ้นของจริง:** ขึ้น = ff main → `ai/delegate-20261025-0951` (`1d004bc..233daa1`, ไม่มี migration, ไม่แตะ config.db) · ถอยกลับ: `git revert` 5 commit ·
  ถัดไปหลังขึ้น: ดู log `Hybrid Mode: I1/I2` และ audit `error = query_failed` ของ feed_revenue/feed_expense บน portal จริง

---

## CMP. เทียบสองงวดบนเส้นทาง compile — 2026-10-25 (แผน: `plan/PLAN_METRICS_COMPARISON.md`)

**ที่มา:** คำถามจริงบน portal 2026-10-24 ดึก ตอบผิดทั้งคู่ และทั้งคู่ไปเส้นทาง free-SQL ด้วย `declined:shape:intent_type:comparison`
- audit 453 "EBT ของหน่วยงานไหน ดีกว่าปีก่อนหน้าบ้าง" → LLM ใช้ตาราง 2 สายงาน + `current > previous` → 0 แถว → "ไม่พบข้อมูลที่ตรงกับเงื่อนไข"
  (สายงานไม่มีที่ดีขึ้นจริง แต่ระดับส่วนดีขึ้น 40/139, ฝ่าย 7/21)
- audit 454 "จังหวัดไหน มี ebt ดีขึ้นกว่าปีก่อนบ้าง" → LLM จัดกลุ่มตาม `sub_division_fname` (กลุ่ม) ตั้งชื่อคอลัมน์ "จังหวัด" และไม่จำกัด 2 สายงานขาย →
  ได้กลุ่ม HQ (กลุ่มธุรกิจลูกค้าองค์กร, กลุ่มกฎหมาย, สายงานบริหารองค์กร …); ที่ถูก: ส่วนขายจังหวัด 98 ส่วน ดีขึ้น 21 (ปทุมธานี 1 +43.24 ล้าน …)
- ทำไมมีหน่วยงาน HQ: `fact_ebt` มีทุกศูนย์ต้นทุนของ NT 12 สายงาน; รายงาน EBT = เฉพาะ 2 สายงานขาย (`ebt_report_scope_and_exclusions`) — compiler ใส่ขอบเขตให้, SQL ที่ LLM เขียนเองไม่ใส่

**ข้อตัดสินของเจ้าของ:** CMP-1 = ก (งวดเดียวกันปีก่อน; ถ้า pass 1 ให้สองงวดใช้ตามนั้น) · CMP-2 = ข (กรองเฉพาะหน่วยที่เปลี่ยนตามคำในคำถาม) · CMP-3 = ค (ถามกลับเมื่อขอแยกราย "หน่วยงาน" / "จังหวัด" โดยไม่บอกระดับ)

### CMP.1 ที่สร้าง (Claude เขียนเอง ไม่ใช่ /delegate)
| commit | เนื้อหา |
|---|---|
| `a54f76a` | `compile()`: `CompileRequest.base_period` → SQL เดียวอ่านสองงวด (แต่ละ term มีเงื่อนไขงวดของตัวเองใน `CASE WHEN`), คอลัมน์ `<metric> <งวดฐาน>`, `<metric> <งวดหลัก>`, `ผลต่าง` (ratio: `ผลต่าง (จุด %)`), มีมิติ → เฉพาะหน่วยที่มีข้อมูลทั้งสองงวด + `change` up/down (`HAVING ผลต่าง > 0 / < 0`), เรียงตามผลต่าง; ยอดรวมไม่มีมิติ → official table สองงวด; `ranking.scope` ใช้เฉพาะเมื่อแยกมิติ · `plan_with_reason()`: รับ `intent_type = comparison` (`supports()` เดิมไม่เปลี่ยน), ทิศจากคำในคำถาม (`CHANGE_WORDS`), ชื่อคอลัมน์รายเดือนใน metrics → โหมดเดือน · `hybrid_flow`: ถามกลับ (`Clarification` → `QueryResult.clarification = True`, ไม่มี SQL, audit `declined:clarify:level`) — `outbound.safe_answer` ส่งข้อความถามกลับเฉพาะเมื่อ `clarification is True` (อย่างอื่นยัง fail-closed เป็น "ไม่พบข้อมูล") · eval: `gen_metric_questions --compare` เพิ่มรูป `compare_total` / `compare_up` |
| `0a32b92` | อ่านงวดของคำถามเทียบตามที่ pass 1 เขียนจริง: รายการเดือนของแต่ละปีถึงเดือนอ้างอิง (`IN 202601…202609, 202501…202509`; ปีก่อนทั้งปีถึง 202512 → ใช้งวดเดียวกัน), `BETWEEN 202601 AND 202609` = ยอดสะสม ณ 202609, `time_key` ในมิติ → ตัดออก |

ผลทดสอบ: ACC-T 1611 → **1653 passed, 3 skipped**; ACC-L ผ่าน; import ด้วย Python 3.10 ผ่าน

### CMP.2 ผลวัด (server ซ้อม 127.0.0.1:8001 บนสำเนาชุดเดียวกับ §D, key ซ้อม id 6)
ชุดเทียบปีก่อนจาก `gen_metric_questions --compare` (ebt 202609): 27 class (รูป compare_total + compare_up ราย 5 ระดับ × 3 metric × เดือน/สะสม;
class ที่ผลเกิน 50 แถวข้าม), 1 คำถามต่อ class แบบประโยคหมุน — ชุดเดียวกันทุกรอบ

| | ก่อน (main `07543cd`) | หลัง รอบ 1 (`a54f76a`) | **หลัง รอบ 2 (`0a32b92`)** |
|---|---|---|---|
| ถูก | 3/27 | 16/27 | **20/27** |
| ตอบด้วย compiler | 0 | 17 (ถูก 15) | **23 (ถูก 20)** |
| เหตุผล decline | `period_filter:range` 21, `shape:intent_type:comparison` 6 | `period_filter:compare` 6, `shape:dimension:time_key` 2, … | `shape:filter:group_0` 2, `group_1` 1, `period_filter:range` 1 |

คำถามจริง 7 ข้อ (453, 454 + ชุด probe):
| คำถาม | ก่อน | หลัง (รอบ 2) |
|---|---|---|
| EBT ของหน่วยงานไหน ดีกว่าปีก่อนหน้าบ้าง | "ไม่พบข้อมูล" | ถามกลับ: "คำว่า "หน่วยงาน" ใช้ได้หลายระดับ — ต้องการแยกตามระดับไหน: สายงาน, กลุ่ม, ฝ่าย, ส่วน, ศูนย์ต้นทุน?" |
| จังหวัดไหน มี ebt ดีขึ้นกว่าปีก่อนบ้าง | กลุ่ม HQ 12 แถวในชื่อ "จังหวัด" | ถามกลับ (แบบเดียวกัน) |
| ส่วนงานไหนมี EBT สะสมดีกว่าปีก่อน | query_failed | compiled: ส่วนที่ดีขึ้น เรียงตามผลต่าง (ส่วนวิศวกรรมและบริหารโครงข่าย +130.55 ล้าน, ปทุมธานี 1 +43.24 ล้าน …) |
| ฝ่ายไหนมี EBT สะสมแย่ลงกว่าปีที่แล้ว | query_failed | compiled: ฝ่ายที่แย่ลง (ฝ่ายขายฯ กรุงเทพตะวันออก ปทุมธานี และสมุทรปราการ = นน.2: −105.60 → −240.39 ล้าน …) |
| EBT ก.ย. เทียบ ส.ค. ฝ่ายไหนเพิ่มขึ้น | query_failed | compiled รายเดือน 08/2569 → 09/2569 |
| EBT ปีนี้เทียบกับปีก่อนเป็นอย่างไร | 4 แถวไขว้กันผิด | compiled: สะสม 09/2568 = 1,139.46 ล้าน → 09/2569 = 570.85 ล้าน (−568.61) |
| สายงานไหนมี EBT margin ลดลงจากปีก่อน | ratio เป็นทศนิยม | compiled: สายงาน 1 39.5% → 33.8% (−5.7 จุด), สายงาน 2 29.9% → 26.3% |

**ไม่ถดถอย:** ชุด 174 ข้อของ §D บนโค้ดใหม่ 156/174 (เทียบ 157/174 ของ §D) — ดีขึ้น 8 แย่ลง 9, McNemar p = 1; ไป compiler 165 ข้อเท่าเดิม ·
ข้อที่ต่างเป็นความแปรปรวนของ pass 1 (ตัวกรอง `group_0`, "ส่วน/กลุ่ม" โดด → สายงาน) ไม่ใช่เส้นทางเปรียบเทียบ

### CMP.3 ที่ยังผิด / ข้อจำกัด
- คำถามเทียบรายเดือนที่ pass 1 ไม่ให้ `time_range` (ให้แค่ `IN [202609, 202509]`) → โหมดสะสมโดยปริยาย (2 ข้อในชุด: ยอดรวมรายเดือนของ ebt_excluding_personnel / ebt_margin)
- "ส่วนไหน / กลุ่มไหน" (คำโดด) ยังได้ `division` → C-0b
- คำว่า "หน่วยงาน" / "จังหวัด" ถามกลับเฉพาะ context ที่มี metric ประกาศ (ตอนนี้ feed_ebt); context อื่นพฤติกรรมเดิม
- `CHANGE_WORDS` เป็นรายการคำสั้น ๆ ใน code (ponytail) — เติมเมื่อ audit `metric_path` แสดงคำถามที่พลาด
- **ขึ้นของจริงแล้ว 2026-10-25 07:32**: main ขยับไประหว่างทาง (Phase E `6640cae`) → merge main เข้า branch (`862915c`, ชนกันแค่ไฟล์นี้),
  ACC-T 1708 passed → ff main `6640cae..862915c` → worker ของ `--reload` เริ่มใหม่ 07:32:50 · ถัดไป: ถามคำถาม 453/454 บน portal จริง
  แล้วดู `metric_path` (`declined:clarify:level` / `compiled:ebt`) · ไม่มี migration · ถอยกลับ: `git revert -m 1 862915c` หรือ `git revert 0a32b92 a54f76a`
