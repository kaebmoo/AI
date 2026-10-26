# RESULT — Metrics convergence (`plan/PLAN_METRICS_CONVERGENCE.md`)

> ไฟล์นี้เติมท้ายทุก run ของแผน (§8): A → D → E → B → C-0b → C-00/C-01 · หนึ่งหัวข้อต่อ phase

| Phase | สถานะ | วันที่ | commit (AI) |
|---|---|---|---|
| **A** มองเห็นเส้นทางของทุกคำถาม | ✅ **ขึ้นของจริงแล้ว** + push (CI เขียว run 40091378614) | 2026-10-24 | `34845de`, `655faeb` |
| **D** eval ที่สร้างเองจากคำประกาศ | ✅ **ขึ้นของจริงแล้ว** (main `011cef3`, reload 22:35) + push (CI เขียว run 40107701402) — วัดบน server ซ้อม: 96 → 157/174 หลังแก้ `plan()` | 2026-10-24 | `4cb8c62`, `ecdcc84`, แก้ `plan()` `3cd4e6c` |
| **E** คำอธิบายคอลัมน์ feed อัตโนมัติ | ✅ **ขึ้นของจริงแล้ว** (main `092f33f`, reload 23:47; ยังไม่ push) — วัดบนสำเนา: คำอธิบายว่าง 49.3% → 23.8% | 2026-10-24 | `3340f31`, `fc19128`, `fca9163`, `6826f75`, `cc0dfce` |
| **B** ตัวตรวจ SQL ของ pass 2 | ✅ **ขึ้นของจริงแล้ว** (main ff `1d004bc..0cd5e0b`, reload 14:37 2026-10-25; ยังไม่ push) — B-01 ข้าม; วัดบน server ซ้อม: 156 → 160/174, ผิดอย่างมั่นใจ 14 → 10 (ชั้น invariant 0 → 0) | 2026-10-25 | `aee811c`, `9ef7cf0`, `d8ce4e6`, `553566b`, `233daa1` |
| **C-0b** คำศัพท์ระดับหน่วยงาน — feed_revenue | ✅ **ขึ้นของจริงแล้ว** 2026-10-26 22:05 (ff AI main `eea6250..491c579`, NT-Report main `5854e5a..514c6f0` มี `52811cc`; audit 485–487 — §C0b.4); eval 174/200, ผิดอย่างมั่นใจ 18 → 2; feed_ebt + feed_expense ยังเป็นแถว `manual` (§A.6) | 2026-10-26 | `631cc7e`, `c9499aa`; NT-Report `52811cc` |
| **C-0b** — feed_ebt / feed_expense จาก contract | ✅ **ขึ้นของจริงแล้ว** 2026-10-27 00:22 (ปิด manual 29–38 → ff NT-Report main `514c6f0..05f989b`; audit 488–489 — §C0b2.5) — ebt 1.7.0, expense 1.3.0 `org_levels`, AI ไม่แก้ code; วัด: declared = manual (ebt 85/90 vs 82/90, expense 14/30 vs 15/30 — ระดับต่างเฉพาะข้อที่ไม่มี keyword); ขั้นขึ้น = ปิด manual 0–4 **ก่อน** แล้ววาง contract (§C0b2) | 2026-10-26 | `d9149ad` (test) |
| **C-00** ส่วนขยาย compiler สำหรับ revenue (`datasets`, term ว่าง, M-5) + `period.parts` + ตัวกรองตัวเลข + มิติงวดในคำถามงวดเดียว | ✅ **ขึ้นของจริงแล้ว** (migrate config.db 14:11, ff AI main `beed1f3..c63da29`, reload 14:12 2026-10-26; ยังไม่ push); server ซ้อม: revenue compiled 3/6 → 4/6, 5/6 หลัง `period.parts` → 5/6 หลังตัวกรองตัวเลข → 4/6 ใน r5 (pass 1 เปลี่ยนเป็น `month <= 9`) → **5/6 ใน r7 และ r9** หลังรับ `month <= M` + ผ่อน R3 (เหลือ `shape:dimension_set` ตามข้อตัดสิน) ตัวเลขตรง parquet ทุกข้อที่ compile | 2026-10-26 | `5f3d62a`, `86e85b5`, `3a30c85`, `fdb9b72`, `22819bf`, `a9116b6`, `48a8875` |
| **C-01** contract revenue (NT-Report) | ✅ **ขึ้นของจริงแล้ว** (ff NT-Report main `b08aa3c..738ea8b` 2026-10-26, revenue **2.4.0**; ยังไม่ push) — ของจริง audit 481–484 ผ่าน; server ซ้อม r11: revenue **6/6** compiled, คำถามเทียบเป้า 3/3 ไปทางเดิมด้วย `excluded_word` | 2026-10-26 | NT-Report `738ea8b`; AI `0e63227` (`excluded_words`) |
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
- **ขึ้นของจริงแล้ว 2026-10-25 14:37** (เจ้าของสั่ง): ff main `1d004bc..0cd5e0b` → worker ของ `--reload` เริ่มใหม่ 14:37:04 · ยังไม่ push · ไม่มี migration, ไม่แตะ config.db · ถอยกลับ: `git revert` 5 commit ·
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

## SALES. ยอดขายเทียบเป้า (`sales_vs_target`, sales 1.4.0) — 2026-10-25

**ที่มา:** คำถามจริง (portal audit 463, MCP 464–466) "หน่วยงานที่ยอดขายมากกว่าเป้ามีหน่วยไหนบ้าง" ได้ 71 หน่วย — รายงาน `NT_Sales_Report_Workbook_202609.xlsx`
ชีต `Sales_Dept_Summary` มี **5** (62 จาก 71 ไม่มีเป้าเลย; ฝ่ายบริหารการเงินฯ 2,001 ล้าน "เกินเป้า 1,876 ล้าน" คือ 8.รายได้อื่นทั้งก้อน — รายงาน: 53,740 บาท ไม่มีเป้า)
และ "ยอดขายรวมทั้งบริษัทเทียบเป้า" ได้ "สูงกว่าเป้า 627 ล้าน" (30,197 vs 29,570 — ยอดขายรวม BG 8 เทียบเป้าที่ไม่มี BG 8) ทั้งที่รายงาน = 27,317 / 29,570 = **92.38% At Risk**.
ทุกข้อเป็น free SQL (`metric_path` ว่าง): KPI ของรายงาน = BG 1–7 เท่านั้น; จัดกลุ่ม `unit_fname` หรือ `sales_dept_current` ก็ได้ 5 หน่วยเท่ากันเมื่อกรอง BG 1–7

### SALES.1 ที่สร้าง (Claude เขียนเอง)
- NT-Report (`ai/…` worktree `NT-Report-metrics`): `DOMAINS["sales"]["metrics"]` = `sales_vs_target` → contract 1.4.0 (MINOR) · `test_metrics_contract` รับ period ไม่มี `cumulative`, `extra_columns`, `ranking.positive/threshold` + test ใหม่ · CHANGELOG, SPEC §5.5
- AI compiler: period ไม่มีคอลัมน์สะสม = `BETWEEN y01 AND yMM` ของคอลัมน์รายเดือน (เทียบสองงวดด้วย) · `extra_columns` · `ranking.positive` (ไม่ใช้เมื่อตัวกรองระบุชื่อหน่วย) ·
  `ranking.threshold` + `CompileRequest.threshold` · ตัวกรองหลายตัวบนคอลัมน์เดียว = OR (เดิม AND → 0 แถว) · `schema_metrics.extra_columns` (migrate script) + validation ใน `sync_metrics`
- `plan()` รับพฤติกรรม pass 1 ที่เห็นจริง (`docs/DECLARED_METRICS.md` §4): ตัวกรอง/ mapping ที่เป็นนิยามของ metric (`metric = 'actual'`), mapping ที่ keyword มีชื่อ metric อยู่ข้างใน,
  ช่วง "ม.ค.-ก.ย." = ยอดสะสม, metric ที่มี threshold: comparison/lookup = เทียบกับเป้า และ ordering ชื่อแต่งเอง = เรียงตามค่า
- test: `tests/unit/test_metric_sales.py` (fixture `sales_metrics_1_4_0.yaml` = contract) — ACC-T 1708 → **1743 passed, 3 skipped**; NT-Report `pytest tools/feed` 38 → 39

### SALES.2 ผลวัด (server ซ้อม 127.0.0.1:8001, สำเนา config.db/app.db/Chroma ของจริง 14:50, contract ชี้ worktree, key ซ้อม id 6)
11 คำถาม × 7 รอบ (restart ก่อนทุกรอบ) — ผลดิบ `.ai/eval/sales_vs_target_r1…r7.json`; เฉลย = รายงาน 202609 (รายฝ่าย/สายงาน/รวม) และ feed BG 1–7 (เดือน, กลุ่มธุรกิจ)

| รอบ | โค้ด | ถูก | compiled (จาก 9 ข้อเทียบเป้า) | decline ที่เหลือ |
|---|---|---|---|---|
| r1 | metric อย่างเดียว | 3/11 | 1 | `shape:filter:metric` ×6, `mapping_triggered:ยอดขายเทียบเป้า`, `shape:dimension:year_month` |
| r2 | + ตัวกรองนิยาม, keyword มีชื่อ, OR, period ออกจากมิติ | 8/11 | 6 | mapping แต่ง ("ยอดขาย", "ยอดขายบริการรวมทั้งบริษัท"), ordering `achievement_diff` |
| r3 | + mapping ที่เป็นนิยาม / ชื่อคอลัมน์ที่แสดง | 8/11 | 7 | `lookup`, ordering `amount - target_amt`; Q4 ได้ ก.ย. เดือนเดียว (pass 1 `cumulative: false`) |
| r4 | + ช่วง ม.ค.-…, lookup | 11/11 | 9 | — |
| r5 | (เดิม) | 10/11 | 8 | ordering `achievement_diff` |
| r6–r7 | + ordering ชื่อแต่งเอง = ค่า | **11/11, 11/11** | **9, 9** | — |
| r8 | merge main (`51b8dc7`: scope ของหน่วยที่ระบุชื่อ, pass-2 invariants) | 9/11 | 8 | `detail` (→ แก้แล้ว: อ่านเหมือน lookup); Q4 pass 1 ทิ้งหน่วยที่สอง (ไม่ใช่ code) |

คำตอบที่ compiled ตรงรายงานทุกตัวเลข: 5 ฝ่ายเกินเป้า (รสส. 232.11%, อดจ. 126.72%, ปอธ. 120.92%, ททค. 112.17%, สกบ. 111.54%), 24 ฝ่ายไม่ถึงเป้า,
บลบ. 95.78% / พธย. 19.21%, รายสายงาน 11 แถวตรง `Sales_Dept_Summary` ทุกแถว ("หน่วยงานอื่น" ไม่มีเป้า → ไม่แสดง), ก.ย. 2569 = 3,149.82 / 3,449.24 ล้าน = 91.32%,
รวม ม.ค.–ก.ย. 27,317.01 / 29,570.15 ล้าน = 92.38%, รายกลุ่มธุรกิจ 7 แถว · R1/R2 (ยอดขายเฉย ๆ) ยังไม่ผ่าน metric (`no_metric`) และยังได้ full disclosure 3,385.51 / 30,197.03 ล้าน

**ไม่ถดถอยฝั่ง EBT** (โค้ดเดียวกัน, server ซ้อมเดียวกัน — การแก้ `plan()` ใช้กับทุก metric): ชุดเต็ม 702 ข้อ 612/702 (compiler 95.6%), ชุดเทียบปีก่อน 783 ข้อ 674/783 ·
จับคู่กับข้อเดิมของ §D (174 ข้อ): 157 → **153** (ดีขึ้น 4 แย่ลง 8, McNemar exact p ≈ 0.39); ข้อที่แย่ลงทั้ง 8 ไม่ได้มาจากโค้ดนี้ — pass 1 ใส่ `group_0` (3), lookup (1),
mapping "เดือน" (1), เลือก `unit_short_name` แทน `unit` (1), "กลุ่ม" → `division` (2, C-0b) · ชุดเทียบของ §CMP (27 ข้อ): 20 → **20** (2/2; ข้อที่แย่ลงคือ "เดือนกันยายน" ที่ pass 1 ไม่ให้ `time_range`
→ สะสม = CMP.3 เดิม) · ผล: `eval_results/metric_eval_feed_ebt_202609_20261025_1635.json`, `…_1810.json`

### SALES.2b ขึ้นของจริง (2026-10-26)
- 06:48 backup `~/nt-ai-backups/sales-metric-golive-20261026-064809/` → `migrate_schema_metrics.py` (ของ branch) บน config.db จริง (`extra_columns` เพิ่ม, quick_check ok)
  → ff AI main `51b8dc7..aed320d` (merge main เข้า branch ก่อน: `38fd3a8`) → worker ใหม่ 06:49:05; audit 467 `compiled:ebt` 570.85 ล้าน
  → ff NT-Report main `61f390c..b08aa3c` (sales 1.4.0) → `schema_metrics.sales_vs_target` declared/active
- คำถามแรก (MCP): 468 ห้าฝ่ายตรงรายงาน · 469 รวม 92.38% · 470 ยอดขายเฉย ๆ `no_metric` 30,197.03 ล้าน · 471 "ยังไม่ถึงเป้า" ได้ LIMIT 10 ที่ pass 1 แต่งเอง
  → `5c13e03` (threshold list ตัด limit เมื่อคำถามไม่มีตัวเลข) → 472 ครบ 24 ฝ่าย
- portal (473, เจ้าของทดสอบ): `declined:period_filter:range` → free SQL 91 หน่วย เป้า 0 ทุกแถว — portal ส่ง scope year_month 202501…202609 และ pass 1 ลอก
  scope เป็น `BETWEEN 202501 AND 202609`; MCP ไม่มี scope จึงไม่เห็น → `plan()` ไม่นับตัวกรองงวดที่เท่ากับ scope ของ request ทั้งก้อน (`_restates_scope`) ·
  server ซ้อมด้วย scope แบบ portal: 11/11 (compiled 9/9) · portal_questions_ebt 10/14 (ข้อผิด = P05 cost_ratio, P06/P14 LIMIT 1, P09 ฐาน — ค้างเดิม)

### SALES.3 ที่ยังไม่ทำ / ข้อควรรู้
- **ยังไม่ขึ้นของจริง** — ลำดับ: AI ก่อน (merge → `scripts/migrate_schema_metrics.py` บน config.db จริง **ก่อน restart** — ไม่งั้น `load_metrics` อ่านคอลัมน์ `extra_columns` ไม่ได้
  และปิด metric ทุก context) → NT-Report merge (server จริงอ่าน `NT-Report/DataFeed/contracts/sales.yaml` ของ main checkout และ re-sync เองใน request ถัดไป);
  rebuild dist ไม่จำเป็น (schema/ข้อมูลเท่าเดิม) นอกจากอยากให้ SCHEMA.md ของ build แสดง metric
- "เกินเป้ามากที่สุด" อ่านเป็น % สูงสุด (ไม่ใช่ส่วนต่างเป็นบาท) — ถ้าต้องการส่วนต่าง ประกาศ metric `sales_vs_target_gap` (actual − target, บาท) เพิ่ม
- ตัวกรองที่เป็นนิยาม: ใน ebt `group_1` / `measure_type` ถูกทุก term เลือกด้วยค่าคงที่ จึงเข้ากฎเดียวกัน — ถ้า pass 1 เลือก metric ebt แล้วกรอง `group_1 = 'รวมรายได้ทั้งสิ้น'`
  จะได้ EBT แทนการตกไป free SQL (ไม่เห็นในชุดวัด 1,485 ข้อ; ถ้าเกิด ให้ประกาศ selector ใน contract แทนการเดาจาก term)
- ช่วงที่ไม่เริ่ม ม.ค. ("ก.ค.-ก.ย.") ยังอ่านตาม pass 1 (มักเป็นเดือนสุดท้าย) — compiler ยังไม่มีรูปผลรวมหลายเดือนกลางปี
- ยอดขายเฉย ๆ (ไม่เทียบเป้า) ยังเป็น free SQL ตามกฎ `sales_total_scope` (full disclosure รวม BG 8) — ไม่ได้ประกาศ metric `sales`

---

## C. ขยาย `metrics:` ไป revenue — C-00 ส่วนขยาย compiler (2026-10-26)

**วิธีทำ:** `/delegate` run `20261026-0720` ใน worktree `_worktrees/AI-metrics` (branch `ai/delegate-metrics`, base `beed1f3` = main) —
2 slice, Codex 3 รอบ (slice 02 รอบ 2 แก้ข้อความ §5 ของ docs ที่ยังบอกผลของการไม่ migrate แบบเดิม + ย้าย import) · ข้อตัดสิน **M-4 = ก**, **M-5 = ก**, **M-7 = ก** (รอบนี้ revenue; sales ขึ้นแล้วทาง §SALES)

### C.1 ที่สร้าง
- `5f3d62a` (slice 01, การเก็บ + sync): คอลัมน์ `schema_metrics.datasets` (`scripts/migrate_schema_metrics.py` idempotent, model, `DECLARED_FIELDS`) ·
  `Metric.datasets` + `__post_init__` (มิติของ metric = union ของมิติทุก dataset ตามลำดับที่พบ) · `resolve`/sync ให้ลูก `extends` รับ `datasets` ·
  `load_metrics` อ่าน `SELECT *` (config.db ที่ยังไม่ migrate ยังโหลด metric เดิมได้) · `_validate_metric`: `dataset` XOR `datasets`; item = `{name, dimensions}`;
  ห้ามประกาศ `dimensions` ระดับ metric คู่กับ `datasets`; คอลัมน์ period / term / `ranking.scope` / `official_scope` ต้องมีใน**ทุก**ตารางที่ระบุ;
  term ต้องเป็น mapping และ `where` ไม่มี / null / ว่าง = ทุกแถว; **M-5**: period ไม่มี `cumulative` แต่คอลัมน์ `month` เป็น `agg: point_in_time` (ลำดับ: column → control_totals → sum) → ไม่รับ
- `86e85b5` (slice 02, compiler): `_dataset_for` เลือกตารางที่มีมิติ+คอลัมน์ตัวกรองครบและมีมิติน้อยสุด (เท่ากัน = ลำดับประกาศ) · ไม่มีตารางไหนครบ → `compile()` ValueError,
  `plan_with_reason()` → `shape:dimension_set` (เฉพาะ metric ที่มี `datasets`) · term ว่าง render เป็น `CASE WHEN (1 = 1)` (ยังต่อเงื่อนไขงวดของการเทียบสองงวดได้) ·
  `dimension_labels` อ่านคำอธิบายมิติจากตารางของแต่ละ grain · M-5 ใช้เส้นทาง `summed` เดิม (BETWEEN y01..yMM) ไม่มีชุดที่สอง · `docs/DECLARED_METRICS.md` §3 (ไวยากรณ์ + ตัวอย่าง revenue) และ §5
- test ใหม่: `tests/unit/test_metric_datasets_sync.py` (43), `tests/unit/test_metric_revenue.py` (33, DuckDB + SQLite ผลเท่ากัน; fixture `tests/fixtures/revenue_metrics_draft.yaml`):
  3 grain total/bu/org, BG 8 ytd 202609 = 210 ≠ ผลรวมรายเดือน 270 → by bu ได้ 210 (`= 202609`, ไม่มี BETWEEN, `sql_invariants` ไม่มี violation); ตัวกรอง `bu` อย่างเดียวเลือกตาราง bu;
  `unit_name` → org; bu × unit → `shape:dimension_set`; เทียบ 202608/202609 บนตาราง bu; period ไม่มี cumulative → BETWEEN 202601 AND 202609 = 270
- test ของ ebt/sales เดิม**ไม่ได้แก้** (แก้เฉพาะ helper `tests/unit/knowledge_db.py` ให้ DDL มีคอลัมน์ `datasets` เหมือน config.db หลัง migrate)

### C.2 ผลทดสอบ
- ACC-T: baseline 1886 → **1962 passed, 3 skipped** (exit 0) · ACC-L exit 0
- sync contract จริงของ NT-Report main (ebt 1.6.1, sales 1.4.0, revenue 2.3.3, expense 1.2.6) ลง DB ชั่วคราวด้วยโค้ดใหม่: ebt 3/3, sales 1/1 metric ยัง active, ไม่มีคำเตือน skip

### C.3 วัดบนข้อมูลจริง
**ออฟไลน์ (parquet จริง `NT-Report/DataFeed/dist/revenue/latest`, อ่านอย่างเดียว):** SQL ที่ compile จาก metric ร่าง — รวม ytd 202609 = **29,389.41 ล้าน**
(official และผ่าน term ได้เท่ากัน = ผลรวมแถว bu = ผลรวม org) · เดือน ก.ย. 3,353.09 ล้าน (= `control_totals` `__ALL__` revenue) ·
**BG 8 = 2,103.05 ล้าน** (ytd ณ งวด — ผลรวมรายเดือน ม.ค.–ก.ย. = 2,711.64 ล้าน) · ฝ่ายสูงสุด: ธุรกิจลูกค้าภาครัฐ 6,613.89 ล้าน · `sql_invariants` ไม่มี violation ทุกรูป

**server ซ้อม 127.0.0.1:8002** (โค้ด branch นี้, สำเนา `.ai/db/c00` จาก `.ai/db/sales`, migrate สำเนา 2 ครั้ง — ครั้งที่สองไม่เปลี่ยนอะไร, contract revenue ร่าง =
2.3.3 จริง + metric `revenue` (`datasets` total/bu/org ครบ 9 มิติองค์กร) ที่ `.ai/db/c00/contracts/revenue.yaml`, key ซ้อม id 6) — sync ได้ `revenue` declared/active:

| คำถาม | `metric_path` (audit สำเนา) | ผล |
|---|---|---|
| EBT สะสมปีนี้ทั้งบริษัท | `compiled:ebt` | 570.85 ล้าน (เท่าของจริง audit 467) |
| หน่วยงานที่ยอดขายมากกว่าเป้ามีหน่วยไหนบ้าง | `compiled:sales_vs_target` | 5 ฝ่าย ตรงรายงาน |
| รายได้สะสมปีนี้ทั้งบริษัท | `compiled:revenue` (total) | 29,389.41 ล้าน ✓ |
| รายได้สะสมปีนี้แยกตามกลุ่มธุรกิจ | `compiled:revenue` (bu) | 8 BG, BG 8 = 2,103.05 ล้าน ✓ |
| รายได้อื่น (กลุ่มธุรกิจ 8) สะสมปีนี้เท่าไร | `compiled:revenue` (bu, ตัวกรอง LIKE) | 2,103.05 ล้าน ✓ |
| ฝ่ายไหนมีรายได้สะสมสูงสุด 5 อันดับแรก | `declined:shape:filter:year` → free SQL | ตัวเลขถูก (SQL ของ LLM อ่าน ytd งวดเดียว) |
| รายได้เดือนกันยายน 2569 ทั้งบริษัท | `declined:shape:filter:year` → free SQL | 3,353.09 ล้าน ถูก |
| รายได้สะสมของแต่ละกลุ่มธุรกิจ แยกตามฝ่าย | `declined:shape:dimension_set` → free SQL | `query_failed` (LLM ใช้ `bu` บนตาราง org ที่ไม่มีคอลัมน์นี้) |

### C.4 พบระหว่างวัด → งาน C-01 / C-02
- **pass 1 ใส่งวดเป็น `year = 2026` + `month = 9`** ในตัวกรอง (ตาราง revenue มีคอลัมน์ `year`, `month` แยกจาก `year_month`) → `shape:filter:year` 2/6 ข้อ —
  ชั้นเดียวกับ "ใส่งวดลง filters" ที่ `plan()` รับแล้วสำหรับคอลัมน์งวด; ทางแก้ที่ต้องตัดสิน: `plan()` ถือตัวกรองบนคอลัมน์ปี/เดือนที่ตรงกับ `time_range` เป็นงวด
  (ต้องรู้ว่าคอลัมน์ไหนคือปี/เดือน — ประกาศใน `period` ของ contract เช่น `parts: {year: year, month: month}`) หรือเอาออกจาก prompt ของ pass 1
  → **แก้แล้ว** ด้วย `period.parts` (§C.4b) · ตัวเลขรอบแรกคือ revenue compiled **3/6** (เดิมเขียนผิดเป็น 4/6 ที่ตารางสถานะ)
- **กลุ่มธุรกิจ × ฝ่าย** ไม่มีตารางใดใน 3 grain ที่ประกาศ → `shape:dimension_set` ตามข้อตัดสิน; C-01 ประกาศ `fact_org_product_monthly` (มี `bu` + มิติองค์กร) ใน `datasets` ก็จะ compile ได้
  (free SQL ที่ล้มคือพฤติกรรมเดิมของทางนั้น ไม่ใช่การถดถอย)
- `scripts/eval/metric_eval_lib.generate()` ยังอ่าน `metric.dataset` ตัวเดียว — ต้องขยายรับ `datasets` ก่อน `gen` ของ revenue ใน C-02
- `revenue_achievement` (รายได้เทียบเป้า) อยู่คนละตาราง (`fact_*_target_monthly`) — SELECT เดียวทำไม่ได้ด้วย C-00; ต้องออกแบบ (join ตาม grain หรือ metric ต่อ grain)

### C.4b `period.parts` — ปีและเดือนที่ประกาศเป็นงวด (2026-10-26, `/delegate` run `20261026-0947`)
- `3a30c85`: contract ประกาศ `period: {column: year_month, parts: {year: year, month: month}, value: …}` ได้ (sync ตรวจ: mapping ไม่ว่างของ year/month → คอลัมน์ที่มีในทุกตาราง,
  ไม่ซ้ำกัน, ไม่ใช่ `period.column`) · `plan()` แปลงตัวกรองบนคอลัมน์ที่ประกาศ (year `=`/`IN`, month `=`/`IN`/`BETWEEN`) เป็น**ตัวกรองเดียวบนคอลัมน์งวด** (`= 202609` / `IN […]`)
  แล้วให้กฎงวดเดิมตัดสิน (YTD จาก 01, เทียบสองงวด, เหตุผลปฏิเสธเดิม) — ไม่มีตรรกะงวดชุดที่สอง; ปีอย่างเดียว = เติม `time_range.year`; ตัดคอลัมน์ปี/เดือนออกจากมิติของการเทียบเหมือนคอลัมน์งวด ·
  metric ที่ไม่ประกาศ `parts` ทำงานเหมือนเดิม (`year` ยังเป็น `shape:filter:year`) · `parts` อยู่ใน JSON `period` เดิม — **ไม่ต้อง migrate**
- Codex 2 รอบ (รอบแรก BLOCKED: Codex ต่อ OpenAI ไม่ได้ ไม่ได้แก้อะไร; รอบสอง PASS) · test ใหม่ `tests/unit/test_metric_period_parts.py` (65) · ACC-T 1962 → **2027 passed, 3 skipped** · ACC-L exit 0 ·
  contract จริง (ebt/sales) ยัง sync active ครบ
- วัดซ้ำบน server ซ้อม 127.0.0.1:8002 (สำเนา c00, contract ร่างเพิ่ม `parts`, key id 6), restart ก่อนแต่ละรอบ:

| คำถาม | รอบแรก (C-00) | r2 | r3 |
|---|---|---|---|
| รายได้สะสมปีนี้ทั้งบริษัท | compiled | compiled | compiled |
| รายได้สะสมปีนี้แยกตามกลุ่มธุรกิจ | compiled | compiled | compiled |
| ฝ่ายไหนมีรายได้สะสมสูงสุด 5 อันดับแรก | `shape:filter:year` | **compiled** (org, `= 202609`) | **compiled** |
| รายได้เดือนกันยายน 2569 ทั้งบริษัท | `shape:filter:year` | **compiled** (`revenue` 3,353.09 ล้าน) | **compiled** |
| รายได้อื่น (กลุ่มธุรกิจ 8) สะสมปีนี้เท่าไร | compiled | `shape:filter:=` → free SQL (2,103.05 ถูก) | compiled |
| รายได้สะสมของแต่ละกลุ่มธุรกิจ แยกตามฝ่าย | `shape:dimension_set` | `shape:dimension_set` | `shape:dimension_set` |
| **revenue compiled** | **3/6** | **4/6** | **5/6** |

  ทั้ง r2 และ r3 pass 1 ยังเขียน `year = 2026` + `month = 9` ใน Q3/Q4 — ตอนนี้ compile ทั้งหมด · ebt 570.85 ล้าน / ยอดขาย 5 ฝ่าย ยัง compiled ทุกรอบ · ตัวเลขที่ compile ตรง parquet ทุกข้อ
- **พบใหม่ (r2):** pass 1 เลือก `bu_seq = 8` (ค่าตัวเลข) แทน `bu LIKE '%8.รายได้อื่น%'` → `shape:filter:=` เพราะไวยากรณ์ตัวกรองของ metric รับ `=`/`IN` เฉพาะค่า string —
  มิติที่เป็นตัวเลข (`bu_seq`) ต้องรับค่า int และ render เป็นตัวเลข; งานถัดไป (ไม่ได้ทำในรอบนี้) — r3 pass 1 กลับไปใช้ `bu` จึง compile → **แก้แล้ว §C.4c**

### C.4c ตัวกรองค่าตัวเลขบนมิติที่เป็นตัวเลข (2026-10-26, `/delegate` run `20261026-1146`)
- `fdb9b72`: `numeric_dimensions(metrics)` อ่าน `schema_metadata.data_type` ของทุกตารางที่ metric ประกาศมิตินั้น (ตัวเลขในทุกตาราง = ใช้ได้; อ่านไม่ได้ = ไม่รับตัวเลขเลย) →
  `hybrid_flow` ส่งเข้า `plan_with_reason(…, numeric=…)` · `=` / `IN` ที่ค่าเป็นตัวเลข (int หรือ float จำกัด ไม่ใช่ bool; `IN` ต้องเป็นตัวเลขทั้งรายการ) ผ่านเฉพาะบนมิติในชุดนั้น
  และ render เป็นตัวเลข (`"bu_seq" = 8`, `IN (1, 4)`) — ตัวเลขบนคอลัมน์ข้อความยัง `shape:filter:=` เพราะ DuckDB เทียบ VARCHAR กับตัวเลขไม่ได้ · SQL ของ ebt/sales/revenue เดิมเหมือนเดิมทุกไบต์
- Codex 2 รอบ (รอบแรก FAIL: เงื่อนไข "เป็นตัวเลข" เขียนซ้ำ 4 ที่ + บรรทัด docs เป็นภาษาอังกฤษ; รอบสอง PASS) · test ใหม่ `tests/unit/test_metric_numeric_filters.py` (54, DuckDB + SQLite) ·
  ACC-T 2027 → **2081 passed, 3 skipped** · ACC-L exit 0
- server ซ้อม r4 (restart, สำเนา c00, key id 6): ชุด 6 ข้อ **5/6 compiled** — Q5 รอบนี้ pass 1 เขียน `bu_seq = 8` อีกครั้งและ **compile ได้** (bu, 2,103.05 ล้าน) ·
  ebt 570.85 ล้าน / ยอดขาย 5 ฝ่าย ยัง compiled · คำถามเสริม "รายได้สะสมของกลุ่มธุรกิจลำดับที่ 1 และ 4" → `compiled:revenue` `"bu_seq" IN (1, 4)` = 6,198.22 / 13,024.48 ล้าน ✓
- **พบใหม่:** "รายได้สะสมของกลุ่มธุรกิจลำดับที่ 8 (bu_seq 8)" → pass 1 ใส่ `year_month` เป็น**มิติ**ของคำถามยอดเดียว (aggregation ไม่ใช่ comparison) → `shape:dimension:year_month` → free SQL (ตัวเลขถูก 2,103.05) —
  ตัดคอลัมน์งวดออกจากมิติตอนนี้ทำเฉพาะการเทียบ; ถ้าจะรับ ต้องตัดสินว่ามิติงวดในคำถามงวดเดียว = งวดเดียว (ไม่ใช่ trend) — งานถัดไป → **แก้แล้ว §C.4d**

### C.4d คอลัมน์งวดเป็นมิติในคำถามงวดเดียว (2026-10-26, `/delegate` run `20261026-1218`)
- `22819bf`: `plan()` ตัดคอลัมน์งวด (และ `period.parts`) ออกจาก `dimensions` เมื่อครบทุกข้อ: ไม่ใช่การเทียบ · งวดถูกตรึงที่เดือนเดียว (`time_range.month` หรือ filter `=` บนงวด รวมตัวที่แปลงจาก parts) ·
  ไม่มี filter ช่วงงวด (IN / BETWEEN / >= / <=) · คำถามไม่มีคำใน `TREND_WORDS` (รายเดือน, แต่ละเดือน, ทุกเดือน, เดือนละ, ตามเดือน, เดือนไหน, เดือนใด, แนวโน้ม, รายปี, แต่ละปี, ปีไหน, ไตรมาส, trend, monthly)
  — ข้อใดไม่ครบ = ปฏิเสธ `shape:dimension:<คอลัมน์>` เหมือนเดิม (`BETWEEN y01..yMM` + มิติงวด ยังปฏิเสธ เพราะกำกวมกับ "รายเดือน ม.ค.–ก.ย.") · ใช้กับทุก metric (ebt `time_key` ด้วย)
- Codex 1 รอบ PASS · test ใหม่ `tests/unit/test_metric_period_dimension.py` (57; replay intent จริงของ r4) · ACC-T 2081 → **2138 passed, 3 skipped** · ACC-L exit 0
- server ซ้อม r5 + r6 (restart ทุกรอบ, สำเนา c00, key id 6):

| คำถาม | r4 (ก่อน) | r5 | r6 |
|---|---|---|---|
| ชุด 6 ข้อ (revenue compiled) | 5/6 | 4/6 (Q5: `period_filter:operator`) | — |
| รายได้สะสมของกลุ่มธุรกิจลำดับที่ 8 (bu_seq 8) | `shape:dimension:year_month` | compiled (pass 1 ไม่ใส่มิติงวดรอบนี้) | `period_filter:operator` |
| รายได้สะสมของกลุ่มธุรกิจลำดับที่ 1 และ 4 | compiled | compiled | compiled |
| รายได้รายเดือนปีนี้ (ตัวกันไม่ให้ตัด trend) | — | `shape:dimension:month` (คงไว้ ✓) | `shape:dimension:year_month` (คงไว้ ✓) |

  ebt / ยอดขาย ยัง compiled · ข้อที่ไป free SQL ได้ตัวเลขถูกทุกข้อ (Q5 2,103.05 ล้าน; รายเดือนได้ 9 แถว)
- **ผลที่ต้องอ่านให้ถูก:** กฎใหม่พิสูจน์ด้วย unit test ที่ replay intent จริงของ r4 และตัวกันคำถาม trend ทำงานบน server ทั้งสองรอบ — แต่รูปเดียวกับ r4 (มิติงวด + ตัวกรองไม่มีช่วง) **ยังไม่เกิดซ้ำบน server**:
  r5 pass 1 ไม่ใส่มิติงวด, r6 ใส่มิติงวด**พร้อม** `month <= 9` ซึ่งถูกปฏิเสธก่อนถึงกฎนี้
- **พบใหม่ (r5 Q5, r6):** pass 1 เขียนยอดสะสมเป็น `year = 2026` + **`month <= 9`** — `period.parts` รับเดือนแค่ `=` / `IN` / `BETWEEN` (`<=` อยู่นอกขอบเขตของ §C.4b) → `period_filter:operator`;
  ทางแก้: เดือน `<= M` (ปีเดียว) = เดือน 1..M = ยอดสะสม ณ M (กฎเดียวกับคอลัมน์งวด `<=` ที่มี `time_range.cumulative`) — งานถัดไป → **แก้แล้ว §C.4e**

### C.4e เดือน `<= M` ใน `period.parts` = ยอดสะสม ณ M (2026-10-26, `/delegate` run `20261026-1241`)
- `a9116b6`: ส่วนเดือนของ `period.parts` รับ `<=` M (1..12) → เดือน 1..M แล้วให้กฎงวดเดิมตัดสิน (ปีเดียว = YTD ณ M; หลายปี = เทียบสองงวด; ไม่มีปี = ปีจาก `time_range`/reference) ·
  `<`, `>=`, `>` บนเดือน และ `<=` บนปี ยัง `period_filter:operator` · กฎ R3 ของ §C.4d ไม่เปลี่ยน: มิติงวด **พร้อม** `month <= M` (รูป r6) ยังปฏิเสธ `shape:dimension:year_month`
  (เป็นช่วงงวด — กันความกำกวมกับ "รายเดือน ม.ค.–ก.ย."; test ของ run ก่อนตรึงไว้) — **แก้คำทำนายเดิมของผมที่ว่าแก้ `<=` แล้วรูป r6 จะ compile: ไม่จริง**
- Codex 1 รอบ PASS · test ใหม่ `tests/unit/test_metric_period_parts_ytd.py` (23; replay intent r5) · ACC-T 2138 → **2161 passed, 3 skipped** · ACC-L exit 0
- server ซ้อม r7 + r8 (restart ทุกรอบ, สำเนา c00, key id 6):

| คำถาม | r7 | r8 |
|---|---|---|
| ชุด 6 ข้อ (revenue compiled) | **5/6** (เหลือ `shape:dimension_set` ตามข้อตัดสิน) | — |
| รายได้อื่น (กลุ่มธุรกิจ 8) สะสมปีนี้เท่าไร | compiled (`bu LIKE`) | compiled (`bu LIKE`) |
| รายได้สะสมของกลุ่มธุรกิจลำดับที่ 8 (bu_seq 8) | compiled (ไม่มีมิติงวด) | **compiled — pass 1 ส่ง `dimensions: ["year_month"]` + `bu_seq = 8`** (กฎ §C.4d ทำงานบน server ครั้งแรก) |
| รายได้สะสมของกลุ่มธุรกิจลำดับที่ 1 และ 4 | compiled (`IN (1, 4)`) | — |
| รายได้ตั้งแต่ต้นปีถึงเดือนกันยายนของกลุ่มธุรกิจ 4 | — | compiled (`bu_seq = 4`, 13,024.48 ล้าน) |
| รายได้รายเดือนปีนี้ (ตัวกัน trend) | `shape:dimension:year_month` (คงไว้ ✓) | — |

  ebt / ยอดขาย ยัง compiled · ตัวเลขที่ compile ตรง parquet ทุกข้อ
- **ผลที่ต้องอ่านให้ถูก:** r7/r8 pass 1 **ไม่ได้เขียน `month <= 9` อีกเลย** — ทางใหม่ของรอบนี้พิสูจน์ด้วย unit test ที่ replay intent จริงของ r5 เท่านั้น ยังไม่เห็นบน server ·
  r7 คำถาม "รายได้รายเดือนปีนี้" ไป free SQL แล้วได้ **แถวเดียว (ยอดสะสม ก.ย.) แทน 9 เดือน** — ทาง pass 2 ที่ไม่ได้แก้ในรอบนี้ (r5/r6 ได้ 9 แถวถูก); `plan()` ปฏิเสธถูกตามกฎ

### C.4f ผ่อน R3: ช่วงยอดสะสมไม่ขวางการตัดมิติงวดเมื่อคำถามบอก "สะสม" (2026-10-26, `/delegate` run `20261026-1303`)
- ข้อตัดสินเจ้าของ: คำถามมีคำว่า "สะสม" **และ** `time_range.cumulative` = true → ช่วง y01..yMM ถือเป็นงวดเดียว yMM จึงตัดมิติงวดได้ (R1, R2, R4/`TREND_WORDS` เหมือนเดิม —
  "รายได้รายเดือนสะสม" ยังไม่ตัด) · `48a8875`: เปลี่ยนเงื่อนไขเดียวใน `plan_with_reason` ·
  test ที่ตรึงกติกาเดิม 2 ตัวแก้ตามที่เจ้าของอนุญาต: `test_period_ranges_keep_dimension` → `…_strip_only_for_explicit_cumulative_question` (ช่วง 4 รูป × มี/ไม่มี "สะสม" / cumulative false / คำแนวโน้ม)
  และ `test_practice_r6_keeps_period_dimension_decline` → `test_practice_r6_cumulative_question_compiles` (รูป r6 compile ได้; ไม่มี "สะสม" ยังปฏิเสธ)
- Codex 1 รอบ PASS · ACC-T 2161 → **2185 passed, 3 skipped** · ACC-L exit 0
- server ซ้อม r9 (restart, สำเนา c00, key id 6): ชุด 6 ข้อ **5/6** (เหลือ `shape:dimension_set` ตามข้อตัดสิน — free SQL รอบนี้ตอบได้ ไม่ได้ตรวจตัวเลข) · bu_seq 8 compiled
  (pass 1 ส่ง `["year_month"]` + `bu_seq = 8` ไม่มีช่วง = กฎ §C.4d) · BG 1 และ 4 compiled · "รายได้รายเดือนปีนี้" ยังปฏิเสธ ✓ (free SQL ได้ 9 เดือนถูก) · ebt / ยอดขาย compiled
- **ทาง `month <= M` (§C.4e) เห็นบน server ครั้งแรก:** "รายได้สะสมตั้งแต่มกราคมถึงกันยายนของกลุ่มธุรกิจลำดับที่ 8" → `bu_seq = 8, month <= 9, year = 2026` → compiled 2,103.05 ล้าน ·
  "ยอดรายได้สะสม ม.ค.-ก.ย. 2569 ของแต่ละกลุ่มธุรกิจ" → `year = 2026, month <= 9` + มิติ `bu` → compiled 8 แถวตรง parquet
- **ยังไม่เห็นบน server:** รูปที่กฎผ่อน R3 ของรอบนี้ใช้ (มิติงวด **พร้อม** ช่วงยอดสะสม + "สะสม") ไม่เกิดใน r9 — พิสูจน์ด้วย unit test ที่ replay intent r6 เท่านั้น

### C.4g C-01 — contract revenue 2.4.0 + `excluded_words` (2026-10-26, Claude เขียนเอง)
- **พบก่อนเขียน C-01 (server ซ้อม r10, metric ร่าง):** คำถามเทียบเป้า 3/3 ("รายได้สะสมเทียบเป้าแยกตามกลุ่มธุรกิจ", "รายได้ปีนี้ทั้งบริษัทเทียบเป้าเป็นกี่เปอร์เซ็นต์",
  "กลุ่มธุรกิจไหนรายได้ต่ำกว่าเป้า") pass 1 เลือก `metric_id: revenue` + `comparison` → **compile เป็นรายได้เทียบปีก่อน = ผิดอย่างมั่นใจ** (ก่อนมี metric คำถามนี้ไป free SQL ที่ใช้ตารางเป้า)
  → เจ้าของเลือก: ประกาศใน contract
- AI `0e63227`: `excluded_words: [...]` (ไม่สืบทอด) → `plan()` ไม่รับ `excluded_word:<คำ>` ก่อนวางแผน; คอลัมน์ `schema_metrics.excluded_words` ใน migration เดิม (idempotent);
  sync ตรวจเป็นรายการคำไม่ว่าง · test ใหม่ `tests/unit/test_metric_excluded_words.py` (12) · ACC-T 2185 → **2197 passed, 3 skipped** · ACC-L exit 0
- NT-Report `738ea8b` (worktree `NT-Report-metrics`, branch `ai/delegate-metrics`): `DOMAINS["revenue"]["metrics"] = [revenue]` → contract **2.4.0** (MINOR):
  `datasets` 8 ตาราง fact (total/bu/service_group/product/subproduct/org/org_product/org_subproduct) + มิติของแต่ละตาราง, `period.parts {year, month}`,
  `terms {rev: {}}`, `official_total` = `fact_total_monthly.revenue_ytd`, `reference: {control_totals: revenue_ytd}`, `excluded_words: [เป้า, target]` ·
  `gen_contract.py --domain revenue` เปลี่ยนแค่ version + บล็อก `metrics` · `test_metrics_contract` รู้จัก datasets (ตรวจการอ้างกับ intersection ของทุกตาราง)/parts/term ว่าง/excluded_words
  + M-5 (period ไม่มี cumulative ห้ามชี้ point_in_time) + test revenue ใหม่ · SCHEMA.md แสดง dataset ต่อ grain, term "(ทุกแถว)", คำที่ไม่ตอบ · SPEC §5.5, CHANGELOG ·
  `pytest tools/feed` (Python 3.10 framework — venv ของ AI ไม่มี pyarrow) **39 → 41 passed** · ไม่ rebuild dist (schema/ข้อมูลเท่าเดิม)
- sync contract ของ worktree ด้วยโค้ด AI branch: ebt 3/3, sales 1/1, **revenue 1/1 active**
- server ซ้อม r11 (สำเนา c00 ชี้ contract revenue ของ worktree, migrate สำเนา 2 ครั้ง, key id 6):

| คำถาม | `metric_path` | ผล |
|---|---|---|
| ชุด revenue 6 ข้อ | **6/6 compiled** | Q6 "กลุ่มธุรกิจ × ฝ่าย" ใช้ `fact_org_product_monthly` (เดิม `shape:dimension_set`) — ผลรวมรายกลุ่มธุรกิจ = ตาราง bu ทุกแถว (รวม 29,389.41 ล้าน) |
| รายได้สะสมเทียบเป้าแยกตามกลุ่มธุรกิจ | `declined:excluded_word:เป้า` → free SQL | ใช้ `fact_bu_target_monthly` |
| รายได้ปีนี้ทั้งบริษัทเทียบเป้าเป็นกี่เปอร์เซ็นต์ | `declined:excluded_word:เป้า` → free SQL | 27,286.36 / 29,569.06 ล้าน = **92.28%** (ฐาน BG 1–7 ตรงกฎ `revenue_target_basis`, ตรงที่คำนวณจาก parquet) |
| กลุ่มธุรกิจไหนรายได้ต่ำกว่าเป้า | `declined:excluded_word:เป้า` → free SQL | ใช้ตารางเป้า |
| รายได้สะสมปีนี้เทียบกับปีก่อนแยกตามกลุ่มธุรกิจ | compiled (เทียบสองงวด) | ตามเดิม |
| bu_seq 8 / BG 1 และ 4 / รายเดือน | compiled / compiled / `shape:dimension:month` | ตามเดิม |

  ebt / ยอดขาย ยัง compiled
- ข้อจำกัด: ยังไม่ได้ทำ Phase D `gen` ของ revenue (C-02 — `metric_eval_lib.generate()` ยังอ่าน `metric.dataset` ตัวเดียว); `revenue_target` / `revenue_achievement` ยังไม่ประกาศ
  (ข้ามตาราง — SELECT เดียวทำไม่ได้); คำถามเทียบเป้าจึงยังเป็น free SQL

### C.5 ขึ้นของจริง (2026-10-26 บ่าย, เจ้าของสั่ง)
- 14:11 backup `~/nt-ai-backups/revenue-metric-golive-20261026-141129/` (config.db quick_check ok, app.db, `revenue-2.3.3.yaml`)
  → `scripts/migrate_schema_metrics.py` (ของ branch) บน config.db จริง: เพิ่ม `datasets`, `excluded_words`; quick_check ok; metric เดิม 4 ตัวยัง active
- ff AI main `beed1f3..c63da29` (15 commit; โค้ด 6 ไฟล์) → `uvicorn --reload` ได้ worker ใหม่ 14:12:02
  → nt-ai: audit **479** `compiled:ebt` 570.85 ล้าน, **480** `compiled:sales_vs_target` 5 ฝ่ายตรงรายงาน
- ff NT-Report main `b08aa3c..738ea8b` (revenue 2.4.0) → request ถัดไป re-sync: `schema_metrics.feed_revenue.revenue` declared/active, `excluded_words` = [เป้า, target]
  → nt-ai: **481** รายได้สะสมทั้งบริษัท `compiled:revenue` **29,389.41 ล้าน** · **482** รายกลุ่มธุรกิจ `compiled:revenue` (BG 8 = **2,103.05**) ·
  **483** ทั้งบริษัทเทียบเป้า `declined:excluded_word:เป้า` → free SQL **92.28%** (27,286.36 / 29,569.06 ล้าน, ฐาน BG 1–7) ·
  **484** แบบ portal (scope year_month 202501…202609) กลุ่มธุรกิจ × ฝ่าย `compiled:revenue` (org_product, 215 แถว)
- ยังไม่ push ทั้งสอง repo · ย้อนกลับ: `git -C AI reset` ไป `beed1f3` + `NT-Report` ไป `b08aa3c` (contract 2.3.3 ใน backup) — คอลัมน์ใหม่ใน config.db ไม่ต้องถอด (โค้ดเก่าไม่อ่าน)

ลำดับที่ใช้ (ผู้อ่านก่อน): backup config.db → `scripts/migrate_schema_metrics.py` บน config.db จริง (เพิ่ม `datasets`, `excluded_words`; **ก่อน** ff — ไม่งั้น re-sync contract
ของทุก feed context ล้มและค้าง knowledge เดิม; `load_metrics` ยังอ่านได้) → ff AI main (server `--reload`) → ตรวจ EBT/ยอดขายเทียบเป้า 1 ข้อแต่ละโดเมนว่ายัง `compiled:*`
→ ff NT-Report main `b08aa3c..738ea8b` (server อ่าน `NT-Report/DataFeed/contracts/revenue.yaml` ของ main checkout และ re-sync ใน request ถัดไป) → ตรวจ `schema_metrics` ของ `feed_revenue`
มี `revenue` declared/active → ถามจริงผ่าน portal key และ nt-ai: รายได้สะสมรวม (29,389.41 ล้าน), รายกลุ่มธุรกิจ (BG 8 = 2,103.05), เทียบเป้า (ต้องเป็น `declined:excluded_word:เป้า`)

### C.6 C-02 — eval ที่สร้างเองของ revenue 202609 (2026-10-26 ค่ำ, `/delegate` run `20261026-1901`)
- `c2c88e3`: `scripts/eval/metric_eval_lib.py` รองรับ metric ที่ประกาศ `datasets` — `contract_metrics()` แปลง `datasets`/`excluded_words` แบบเดียวกับแถวที่ sync;
  `generate()` ตรวจ parquet ทุกตาราง และถาม compiler (`_dataset_for`) ว่ามิติไหนอยู่ตารางไหน → ค่าตัวอย่าง, ชื่อเรียก และคำตอบที่ถูกมาจากตารางเดียวกัน · metric ตารางเดียวได้ผลเท่าเดิมทุกไบต์ ·
  test ใหม่ 13 · ACC-T 2197 → **2210 passed, 3 skipped** · Codex 1 รอบ PASS
- gen จาก contract จริง 2.4.0 + dist จริง (`--compare`): **792 คำถาม / 200 ชั้น** (16 มิติ; ข้าม `bu_seq` = ตัวเลข, 28 ชั้น "แยกตาม" ที่เกิน 50 แถว) → `.ai/eval/metric_revenue_202609.json`
- run บน server ซ้อม c00 (127.0.0.1:8002, โค้ด = main ที่ขึ้นแล้ว + eval, contract 2.4.0, key id 6) แบบ **1 คำถามต่อชั้น (200 ข้อ)** — ผล `eval_results/metric_eval_feed_revenue_202609_20261026_1942.json`

| | ถูก | หมายเหตุ |
|---|---|---|
| **รวม** | **153/200 (76.5%)** | |
| compiled | **135/153** ถูก | compile 153/200 = 76.5% ของคำตอบ; **ผิดอย่างมั่นใจ 18** |
| free SQL | 18/47 ถูก | |
| total / compare_total | 2/2, 2/2 | |
| by / filter | 11/16, 24/32 | filter ส่วนใหญ่ไป free SQL (mapping / ชื่อย่อ) |
| top5 / top10 (desc+asc) | 51/64, 50/64 | |

- **ผิดอย่างมั่นใจ (compiled แต่ผิด) 18 ข้อ = pass 1 เลือกระดับผิด ไม่ใช่ compiler:** "กลุ่ม" (`sub_division_name`) → pass 1 เลือก `bu` (**กลุ่ม**ธุรกิจ) 12 ข้อ ·
  "ส่วน" → `unit_name` 2 · ชื่อย่อระดับ 2/4 → ชื่อย่อระดับบน 3 · compare_up รายฝ่าย 10 จาก 20 แถว 1 → ชั้นเดียวกับ C-0b (คำศัพท์ระดับหน่วยงานยังไม่ถึง pass 1 ของ feed_revenue —
  revenue มี hierarchy ผลิตภัณฑ์ แต่ไม่มีระดับองค์กรใน `master_hierarchy`)
- **free SQL ผิด 29 ข้อ:** มิติชื่อย่อ (`*_sname`) → pass 1 ใช้ `department_abbr` ของ `dim_org` (`shape:dimension:department_abbr` 16) แล้ว SQL อิสระว่าง/ผิด ·
  mapping กลางของคำย่อ (`กกง.`, `อป.2`) และ "กรรมการผู้จัดการใหญ่" ถูกกระตุ้น (`mapping_triggered` 21 ครั้งรวม) → SQL อิสระล้ม (`query_failed`) ·
  mapping "1.Hard Infrastructure" ทำให้ SQL AND กับ BG 8
- ชื่อเรียกบางมิติในคำถามมาจาก contract ที่ยังไม่มีคำอธิบาย ("business group (8 = รายได้อื่น)", `service_group_seq`) — Phase E ของ revenue ช่วยได้
- งานถัดไปตามน้ำหนัก: (1) **C-0b สำหรับ revenue** — ระดับองค์กร 4 ระดับลง `master_hierarchy` + แยก "กลุ่ม" (ระดับ 2) ออกจาก "กลุ่มธุรกิจ" = ปิดผิดอย่างมั่นใจ 15/18 ·
  (2) mapping กลางของคำย่อ/ชื่อหน่วยไม่ควรบล็อก metric เมื่อค่าเป็นมิติที่ประกาศ (หรือ scope mapping ตามคอลัมน์) · (3) คำอธิบายคอลัมน์ revenue (Phase E) ·
  ยังไม่ได้รันครบ 792 ข้อ (ผลข้างบนคือ 1 ต่อชั้น)

---

## C0b. Phase C-0b — ระดับหน่วยงานของ feed_revenue ถึง pass 1 (2026-10-26 ค่ำ, session แยกจาก §C.6)

ที่มา §C.6: compile แล้วผิด 18 ข้อ = pass 1 เลือกระดับผิด ("กลุ่ม" → `bu` 12, "ส่วน" → `unit_name` 2, ชื่อย่อระดับ 2/4 → ระดับบน 3) เพราะ `master_hierarchy`
ของ feed_revenue มีแต่สายผลิตภัณฑ์ (แถว `manual` 0–2) — ไม่มีระดับองค์กร

### C0b.1 ข้อตัดสินของเจ้าของ (2026-10-26)
- **หลาย hierarchy ต่อ context = (ข)**: ระดับองค์กรอยู่ที่ level **10+i** (หนึ่งสายต่อหลักสิบ) ใต้ `UNIQUE(context_name, level)` เดิม — ไม่มี migration
- **"กลุ่ม" โดด ๆ ไม่ชี้ระดับ**: ใช้เฉพาะรูปที่ชัด "กลุ่มไหน / รายกลุ่ม / แต่ละกลุ่ม / ตามกลุ่ม / ทุกกลุ่ม / ระดับกลุ่ม / กลุ่มงาน / กลุ่มขาย" → กลุ่มองค์กร (`sub_division_name`);
  "กลุ่ม Fixed Line" (ที่ระบบเดิมหมายถึงกลุ่มบริการ) ไม่ได้ note — ค่าที่ค้นเจอตัดสินเหมือนเดิม · "ส่วน" ทำแบบเดียวกัน (ห้ามโดด: สัดส่วน / ส่วนลด)

### C0b.2 ที่สร้าง
- **NT-Report `52811cc`** (worktree `_worktrees/NT-Report-metrics`, branch `ai/delegate-metrics`): revenue **2.5.0** — `org_levels:` ใน `DOMAINS["revenue"]`
  (สายงาน > กลุ่ม > ฝ่าย > ส่วน > ศูนย์ต้นทุน; `columns` ชื่อเต็มก่อน ชื่อย่อตาม + `keywords`) → `gen_contract` ส่งผ่าน (diff ของ contract = key ใหม่ + เวอร์ชันเท่านั้น);
  `test_metrics_contract`: คอลัมน์ของทุกระดับมีใน fact และไม่มีคำโดด; SPEC §5.4b, CHANGELOG · `pytest tools/feed` **42 passed** · ไม่ต้อง rebuild dist
- **AI `631cc7e`**: `datafeed_knowledge.sync_hierarchy` — `org_levels` → `master_hierarchy` ของ `feed_<domain>` level 10+i แบบ `declared` ด้วย `_declare` เดิม
  (แถวที่คนแก้ชนะ ฉบับ contract รอใน `knowledge_proposals`; ระดับที่ contract เลิกประกาศหรือคอลัมน์ไม่มีจริง = ถอนเฉพาะแถวของ contract; config DB ที่ไม่มีตาราง = ข้าม);
  ล้าง cache ของ hierarchy (TTL 1 ชม.) หลัง re-sync · `named_levels`: keyword ที่ถูก keyword ยาวกว่าล้ำทับ ("ตามกลุ่ม" ใน "ตามกลุ่มธุรกิจ", "แต่ละกลุ่ม" ใน "แต่ละกลุ่มบริการ") ไม่นับ ·
  `format_level_note`: "ลำดับชั้น:" แสดงเฉพาะสายของระดับที่ถูกพูดถึง · docs `DATAFEED_INTEGRATION.md`
- **AI `c9499aa`** (นอก ALLOWED ของ §6b แต่จำเป็นกับ (ข)): ตัวอ่าน `master_hierarchy` อีกสามที่รวมทุกระดับเป็นสายเดียว → แยกตาม `level // 10`:
  STEP 1.5 ของ system prompt (`schema/service.py` — ก่อนแก้ pass 1 ของทุกคำถาม feed_revenue เห็น "กลุ่มธุรกิจ > กลุ่มบริการ > บริการ/ผลิตภัณฑ์ > สายงาน > กลุ่ม > …"),
  ตัวอย่าง hierarchy ของ explain (`hybrid_flow`), ร่างคำอธิบายคอลัมน์ของ Phase E (`column_drafts` — จะเขียน "ระดับ 12 ของโครงสร้าง")
- tests `tests/unit/test_hierarchy_org_levels.py` 13 ข้อ: sync/idempotent/คนชนะ/ถอน · คำถาม 8 แบบ → ระดับที่ถูก (รวม "ตามกลุ่มธุรกิจ", "สัดส่วน…", "กลุ่ม Fixed Line") ·
  note แสดงสายเดียว · STEP 1.5 แยกสาย · **contract → sync → master_hierarchy → prompt ของ pass 1 มี "กลุ่ม → คอลัมน์ `sub_division_name`"** (ชั้นที่ eval คำถามเดี่ยวมองไม่เห็น)
- ACC-T **2223 passed, 3 skipped** (2210 + 13) · ACC-L เขียว

### C0b.3 วัด (server ซ้อม 127.0.0.1:8003 บนสำเนา c00 → `.ai/db/c0b/`, contract 2.5.0 จาก worktree NT-Report, key id 6, คำถามชุดเดียวกับ §C.6 1 ต่อชั้น)
re-sync ครั้งแรกเขียน 5 ระดับ `declared` (10–14) ข้างแถว `manual` 0–2 ของสายผลิตภัณฑ์ — log `Synced 1 metrics, 5 org levels for feed_revenue`

| | ฐาน §C.6 | รอบ 1 (`631cc7e`) | **สุดท้าย (`c9499aa`)** |
|---|---|---|---|
| ถูกรวม | 153/200 | 174/200 | **174/200 (87%)** |
| compiled ถูก / ทั้งหมด | 135/153 | 162/167 | **162/164** |
| **ผิดอย่างมั่นใจ** (compiled แต่ผิด) | **18** | 5 | **2** |
| free SQL ถูก | 18/47 | 12/33 | 12/36 |

- **ชั้น "กลุ่ม → bu" ปิดครบ 12/12** (by / top5 / top10 / compare_up × เดือน/สะสม ของ `sub_division_name` → GROUP BY `sub_division_name` บน `fact_org_monthly`) ·
  "ส่วน → ฝ่าย" 2/2 · ชื่อย่อระดับ 4 (`sub_unit_sname`) 2/2 · บวก: ชื่อย่อฝ่าย (`unit_sname`) 8 ข้อที่เคยถูกปฏิเสธด้วย `shape:dimension:department_abbr` ตอนนี้ compile ถูก,
  `sub_unit_name` top10, `division_sname` by
- เทียบรายข้อกับฐาน (รอบสุดท้าย): ถูกขึ้น 26, ผิดลง 5 (153 + 26 − 5 = 174) — ไม่มีข้อไหนผิดเพราะเลือกระดับ: `M0418` (ชื่อเรียก "business group (8 = รายได้อื่น)" จาก desc ทำให้ pass 1 ใส่ตัวกรอง BG 8),
  `M0619` (free SQL ใช้ `division_abbr` ของ `dim_org`), `M0403` / `M0601` / `M0703` (free SQL หลัง `mapping_triggered` — ใช้ revenue แทน revenue_ytd หรือคืนหลายแถว)
- ข้อที่ผิดลงในรอบ 1 (6 ข้อ) ถามซ้ำหลังล้าง cache (restart) ถูก 3 = ความแกว่งของโมเดล; `M0082` / `M0304` ที่ยังผิดซ้ำ ถูกในรอบสุดท้ายหลังแก้ STEP 1.5
- **ผิดอย่างมั่นใจที่เหลือ 2:** `M0418` (ข้างบน — ชื่อเรียกที่มาจาก desc ของ `bu`, Phase E ของ revenue) · `M0700` compare_up รายฝ่ายสะสม ได้ 10 จาก 20 แถว (pass 1 ใส่ `limit 10` กับ comparison — เป็นตั้งแต่ฐาน §C.6)
- ไฟล์ผล: `eval_results/metric_eval_feed_revenue_202609_20261026_2117.json` (รอบ 1), `…_2201.json` (สุดท้าย) ใน worktree นี้ (gitignored)

### C0b.4 ขึ้นของจริง (2026-10-26 22:04–22:09, เจ้าของสั่ง)
- 22:04 backup `~/nt-ai-backups/c0b-org-levels-golive-20261026-220452/config.db` (integrity_check ok) — ไม่มี migration
- ff AI main `eea6250..491c579` (พา `c2c88e3` eval generator + `1cac6c0` docs ไปด้วย; โค้ด server 5 ไฟล์) → `uvicorn --reload` worker ใหม่ 22:05:12, `/` ตอบ 200
- NT-Report main ไปไกลกว่า branch แล้ว (`5854e5a`, sggap 3 commit แตะเฉพาะ `SGGap/`) → merge main เข้า `ai/delegate-metrics` ใน worktree (`514c6f0`),
  `pytest tools/feed` 42 passed → ff NT-Report main `5854e5a..514c6f0` (revenue **2.5.0**)
- request แรกของ feed_revenue re-sync: `master_hierarchy` = 0–2 `manual` + **10–14 `declared`/active** (สายงาน/กลุ่ม/ฝ่าย/ส่วน/ศูนย์ต้นทุน), `knowledge_sha` `82ee8c6d…:2.3.2`, quick_check ok
- ถามจริงผ่าน nt-ai (key id 5 — ช่องทางเดียวกับ §C.5; คำถามแบบ portal ส่ง `scope` ของ portal):
  **485** "กลุ่มไหนมีรายได้สะสมสูงสุด 5 อันดับ" `compiled:revenue` GROUP BY `sub_division_name` (กลุ่มธุรกิจลูกค้าองค์กร 10,461 ล้าน) ·
  **486** คำถามเดียวกันแบบ portal (scope `year_month` 202501…202609) → ผลเดียวกัน · **487** "รายได้สะสมปีนี้แยกตามกลุ่มธุรกิจ" ยัง GROUP BY `bu` (BG 8 = **2,103.05** เท่า audit 482)
- ยังไม่ push ทั้งสอง repo · ย้อนกลับ: `git -C AI reset --hard eea6250` + NT-Report `reset --hard 5854e5a` → re-sync ถอนแถว 10–14 เอง (หรือคืน config.db จาก backup)

ลำดับที่วางไว้ก่อนขึ้น:
ลำดับตาม CHANGELOG ("ผู้อ่านรองรับก่อน แล้วจึงวาง contract"): (1) ff AI main ด้วย `631cc7e` + `c9499aa` (ไม่มี migration — ตาราง `master_hierarchy` เดิม) →
(2) ff NT-Report main ด้วย `52811cc` (revenue 2.5.0) → request แรกของ feed_revenue re-sync เอง เขียน level 10–14 `declared` (สำรอง config.db ก่อน) →
(3) ตรวจ `SELECT level, level_label_th, source FROM master_hierarchy WHERE context_name='feed_revenue'` = 0–2 manual + 10–14 declared →
(4) ถามจริงผ่าน portal key "กลุ่มไหนมีรายได้สะสมสูงสุด 5 อันดับ" → audit GROUP BY `sub_division_name`

### C0b.5 ที่ยังไม่ทำ / ข้อควรรู้
- **feed_ebt / feed_expense** ยังพึ่งแถว `manual` 0–4 (§A.6) — ถ้าจะให้ contract เป็นเจ้าของ: ประกาศ `org_levels` ใน contract ของสองโดเมน **และ** ปิด/ลบแถว manual 0–4 ตอนวาง
  (ไม่งั้นสองสายมีคำเดียวกัน "ฝ่าย" → note สองระดับ) · feed_sales ไม่ต้อง
- free SQL ผิด 24 ข้อของ revenue ยังเป็นเรื่อง mapping กลาง (`กกง.` 18 ครั้ง, `กรรมการผู้จัดการใหญ่` 7) บล็อก metric — งานถัดไปข้อ (2) ของ §C.6
- คำ "ชื่อย่อของกลุ่ม (เช่น กกง., อป.2)" ในคำถาม eval มาจาก desc ของ contract — ไม่มีรูปที่ชัดของ "กลุ่ม" จึงไม่มี note (`M0280` sub_division_sname ยังไปผิด/ไม่ compile) — ผู้ใช้จริงพิมพ์ "กลุ่มไหน" มากกว่า
- server ซ้อม 8003 หยุดแล้ว (`./.ai/db/c0b/serve.sh <tag>` เปิดใหม่ได้)
- คำอธิบาย (explain) ของ 485 ยังเรียกผลว่า "แต่ละกลุ่มธุรกิจ" แม้ข้อมูลเป็นกลุ่มองค์กร — ตัวเลข/คอลัมน์ถูก แต่ถ้อยคำของ explain ไม่รู้ระดับ

## C0b2. ระดับหน่วยงานของ feed_ebt / feed_expense จาก contract (2026-10-26 ดึก, session แยกจาก §C0b)

ที่มา §C0b.5: feed_ebt (ids 29–33) / feed_expense (ids 34–38) ตอบรายฝ่ายถูกเพราะแถว `manual` 0–4 ที่เขียนมือใน config.db (§A.6) — ไม่อยู่ใน git, ไม่ตามข้อมูล

### C0b2.1 ที่สร้าง
- **NT-Report `05f989b`** (worktree `_worktrees/NT-Report-metrics`, branch `ai/delegate-metrics`): ebt **1.7.0** / expense **1.3.0** — `org_levels:` คำและคอลัมน์เดียวกับแถว manual
  (อ่านจากสำเนา config.db 22:51): ebt บน `fact_ebt` (`division` / `sub_division` / `unit` + `unit_short_name` / `sub_unit` / `cost_center`);
  expense บน `dim_org_snapshot` (`division` / `sub_division_fname` / `unit_fname` / `sub_unit_fname` + ชื่อย่อ / `cost_center`) ไม่มี "รายกลุ่ม" ·
  `test_metrics_contract`: ระดับอ้างคอลัมน์ของ fact **หรือของ dim ที่ JOIN fact ด้วย `scope_columns.org_code`** + ตรึงคอลัมน์แรกของสามโดเมน + expense ไม่มี "รายกลุ่ม" ·
  `test_functional_deps` เคยตรึง expense `1.2.x` → รับ MINOR หลัง 1.2 · SPEC §5.4b, CHANGELOG · diff ของ contract = key ใหม่ + เวอร์ชัน ·
  `pytest tools/feed` **42 passed** (รอบแรก `test_atomic_publish` ล้ม 1 ครั้ง — test จังหวะ concurrency, รันซ้ำ 3 รอบผ่าน) ·
  หลัง commit นี้ branch มี `37e7246` (revenue 2.5.1 ของอีก session) ต่อท้าย — ไม่แตะ ebt/expense
- **AI ไม่ต้องแก้ code**: `sync_hierarchy` รวมคอลัมน์ของทุก dataset (dim ด้วย) · ตัวอ่านทุกตัวแยกสายด้วย `level // 10` อยู่แล้ว (มีแต่ 10–14 = สายเดียว) ·
  ใน request `source_resolver.for_context` (re-sync + ล้าง cache) มาก่อน pass 1 — คำถามแรกหลังวางเห็นระดับใหม่ ·
  pass 1 JOIN `cost_center` + `effective_month` เองเมื่อ note ชี้คอลัมน์ของ dim (เห็นใน SQL ของ expense สายงาน/ฝ่าย/ส่วน ทั้งแบบ manual และ declared)
- **AI `d9149ad`** test: contract แบบ expense (คอลัมน์อยู่ใน dim) → sync → 10–14 `declared` → note "ฝ่าย → `unit_fname`" + STEP 1.5 สายเดียว + "รายกลุ่มค่าใช้จ่าย" ไม่ชี้ระดับ ·
  docs `DATAFEED_INTEGRATION.md` · ACC-T **2224 passed, 3 skipped** (2223 + 1) · ACC-L เขียว

### C0b2.2 วัด (server ซ้อม 127.0.0.1:8004 บนสำเนา config.db/app.db/Chroma ของจริง 22:51 → `.ai/db/c0b2/`, code ของ worktree นี้, key ซ้อม id 6)
- **ebt**: generator (`gen_metric_questions`, contract 1.7.0 + dist 202609) ชั้น `top5_desc` ทั้งหมด **90 ข้อ** = 3 metric × เดือน/สะสม × 5 ระดับ × 3 สำนวน
  (สำนวนแรก = รูป §6b "<ระดับ>ไหนมี … สูงสุด 5 อันดับ", ที่เหลือ "ขอ 5 อันดับ<ระดับ>ที่มี…" / "… แยกตาม<ระดับ>")
- **expense** ไม่มี metric → **30 ข้อ** รูปเดียวกัน (`.ai/eval/gen_expense_levels.py`), oracle บน parquet: `fact_expense` JOIN `dim_org_snapshot` ON `cost_center` + `effective_month = time_key` (กฎของ contract)
- ให้คะแนนสองชั้น: **ตัวเลข** ตรง oracle (`score_case` เดิม) · **ระดับ** = คอลัมน์ระดับที่ละเอียดที่สุดใน GROUP BY ของ SQL (`.ai/eval/levels.py`)
- **A** = แถว manual 0–4 (ของจริงวันนี้) · **B** = contract 1.7.0 / 1.3.0 + ปิด manual 0–4 (re-sync แรก log `Synced 3 metrics, 5 org levels for feed_ebt` → 10–14 `declared`/active) ·
  **C** = B + รูปที่ชัดเพิ่ม (ไม่ commit): กลุ่ม + "กลุ่มไหน" "กลุ่มงาน"; ส่วน = รายการของ revenue 2.5.0 ("ส่วนไหน / แต่ละส่วน / ตามส่วน / ทุกส่วน" + เดิม) — วัดเฉพาะชั้นกลุ่ม/ส่วน

| ebt (ตัวเลข · ระดับ) | A manual | B declared | C |
|---|---|---|---|
| สายงาน (18) | 18 · 18 | 18 · 18 | — |
| กลุ่ม (18) | 16 · 16 | 16 · 16 | **17 · 17** |
| ฝ่าย (18) | 18 · 18 | 18 · 18 | — |
| ส่วน (18) | 13 · 15 | 15 · 17 | **16 · 18** |
| ศูนย์ต้นทุน (18) | 17 · 18 | 18 · 18 | — |
| **รวม 90** | **82 · 85** | **85 · 87** | (87 · 89) |

| expense (ตัวเลข · ระดับ) | A manual | B declared | C |
|---|---|---|---|
| สายงาน (6) | 3 · 6 | 2 · 6 | — |
| กลุ่ม (6) | 0 · 0 | 0 · 0 | 0 · 0 |
| ฝ่าย (6) | 6 · 6 | 6 · 6 | — |
| ส่วน (6) | 0 · 0 | 0 · 0 | **4 · 4** |
| ศูนย์ต้นทุน (6) | 6 · 6 | 6 · 6 | — |
| **รวม 30** | **15 · 18** | **14 · 18** | (18 · 22) |

- **declared = manual**: ข้อที่**ระดับ**ของ A กับ B ต่างกันทุกข้อเป็นข้อที่ไม่มี keyword ในคำถาม (ไม่มี note ทั้งสองแบบ) = ความแกว่งของโมเดล;
  ข้อที่มี keyword ต่างกันเฉพาะตัวเลข ระดับถูกทั้งคู่ (M0340 A `declined:mapping_triggered`, X001 A ปี พ.ศ., X017 B `LIKE '%สายงาน%'`) ·
  ระดับที่คำถามมี keyword (สายงาน / ฝ่าย / ศูนย์ต้นทุน) ถูกระดับ **54/54** (ebt) และ **18/18** (expense) ทั้ง A และ B
- **ช่องที่แถว manual มีอยู่แล้ว**: รูป §6b "กลุ่มไหน" / "ส่วนไหน" และ "แยกตามส่วน" / "ขอ 5 อันดับกลุ่มที่…" ไม่มี keyword → ไม่มี note:
  ebt ไปสายงาน (M0040 / M0085 / M0202 / M0509 / M0553 ได้ 2 แถว) หรือ `group_0` / `group_1` (บรรทัดของรายงาน → `declined:shape`); expense "ส่วน" → `cat_l2_th` 12/12
- **C ปิดช่องของ ebt**: ชั้นกลุ่ม/ส่วน ระดับถูก **35/36** (A 31, B 33) — เหลือ M0393 "แยกตามกลุ่ม" → `group_1` ("ตามกลุ่ม" ไม่ได้ใส่ — ข้อถัดไป);
  expense "ส่วนไหน" / "แยกตามส่วน" → `sub_unit_fname` 4/6 (เหลือ "ขอ 5 อันดับส่วนที่…" ที่ไม่มี keyword)
- **expense "กลุ่ม" = กลุ่มค่าใช้จ่าย**: แม้ C ส่ง note "กลุ่ม → `sub_division_fname`" (log `Hierarchy: level 11` ครบ 2 ข้อ) โมเดลยังตอบ `expense_group_name` ทุกข้อ —
  metadata ของ expense เรียกคอลัมน์นั้นว่า "กลุ่มค่าใช้จ่าย"; ในโดเมนค่าใช้จ่ายการอ่านนี้มีเหตุผล → ไม่แนะนำ "กลุ่มไหน" ใน expense
- ไม่ใส่ "ตามกลุ่ม / แต่ละกลุ่ม / ทุกกลุ่ม" ใน ebt/expense: ล้ำเข้า "ตามกลุ่มค่าใช้จ่าย" (ทั้งสองโดเมนมีกลุ่มค่าใช้จ่าย; `named_levels` ตัดเฉพาะเมื่อมี keyword ที่ยาวกว่า) ·
  ตรวจ offline กับคำของ C: "ค่าใช้จ่ายแยกตามกลุ่มค่าใช้จ่าย", "สัดส่วนค่าใช้จ่ายตามกลุ่มค่าใช้จ่าย", "กลุ่มค่าใช้จ่ายไหนสูงสุด" ไม่ชี้ระดับ; "แต่ละส่วนลด…" ชี้ส่วน (ความเสี่ยงเดียวกับ revenue ที่เจ้าของรับแล้ว)
- expense สายงานผิดเฉพาะตัวเลข (ระดับถูก): free SQL ใส่ `division LIKE '%สายงาน%'` เอง ตัด "กรรมการผู้จัดการใหญ่ บมจ.เอ็นที" (แถวที่ 5 ของ oracle) ออก; X001 ของ A ใส่ `time_key = 256909` (ปี พ.ศ.) ได้ 0 แถว
- ไฟล์ผล (gitignored, worktree นี้): `eval_results/metric_eval_feed_{ebt,expense}_202609_20261026_{2312,2317}` (A) · `_{2330,2334}` (B) · `_{2340,2342}` (C); คำถามและตัวให้คะแนนใน `.ai/eval/`

### C0b2.3 ขั้นขึ้นของจริง (ที่วางไว้ — ทำแล้วตาม §C0b2.5)
ผู้อ่านไม่เปลี่ยน code → ไม่ต้อง ff AI main ก่อน (commit ของ AI ใน branch นี้ = test + docs)
0. ตรวจ: NT-Report main = `514c6f0` สะอาด (ตรวจแล้ว 23:45) · `05f989b` ต่อจาก `514c6f0` ตรง ๆ
1. backup: `sqlite3 -readonly /Users/seal/Documents/GitHub/AI/config.db ".backup ~/nt-ai-backups/c0b2-ebt-expense-golive-<ts>/config.db"` + `integrity_check`
2. **ปิดแถว manual ก่อน แล้ววาง contract — คำสั่งเดียว** (ซ้อมบนสำเนาด้วย venv 3.10 แล้ว: ปิด 10 แถว, feed_revenue ไม่ถูกแตะ):
   ```
   cd /Users/seal/Documents/GitHub/AI && venv/bin/python -c "
   from app.services.hierarchy_service import HierarchyService
   s = HierarchyService()
   for ctx in ('feed_ebt', 'feed_expense'):
       for level in range(5):
           s.delete_level(ctx, level)" && git -C /Users/seal/Documents/GitHub/NT-Report merge --ff-only 05f989b
   ```
   ลำดับนี้เพราะการปิดจากโปรเซสอื่นไม่ล้าง cache ของ server: ถ้าวาง contract ก่อน request ในช่วงนั้น re-sync แล้วโหลด**ทั้งสองสาย**เข้า cache
   ("ฝ่าย" → ระดับ 2 และ 12) ค้างได้ถึง 1 ชม.; ลำดับนี้ช่วงระหว่างสองคำสั่ง server ยังใช้ cache เดิม (manual) จน re-sync ซึ่งเกิดก่อน pass 1 ของ request แรกของแต่ละ context ·
   `05f989b` = commit นี้อย่างเดียว — `37e7246` (revenue 2.5.1) บน branch เดียวกันเป็นงานของอีก session เจ้าของตัดสินแยก
3. ถามหนึ่งข้อต่อ context → `SELECT context_name, level, source, is_active FROM master_hierarchy WHERE context_name IN ('feed_ebt','feed_expense')`
   = 0–4 manual / is_active 0 + 10–14 declared / 1
4. "ฝ่ายไหนมี ebt สูงสุด 5 อันดับ" → audit `compiled:ebt` GROUP BY `unit` · "ฝ่ายไหนมีค่าใช้จ่ายสะสมปี 2569 สูงสุด 5 อันดับ" → GROUP BY `unit_fname` (ฝ่ายเสาโทรคมนาคม 3,072.72 ล้าน)
- ย้อนกลับ: `git -C NT-Report reset --hard 514c6f0` (re-sync ถอนแถว 10–14 เอง) + `UPDATE master_hierarchy SET is_active = 1 WHERE id BETWEEN 29 AND 38` — หรือคืน config.db จาก backup

### C0b2.4 ข้อตัดสินของเจ้าของ
- **ขึ้นด้วยคำเดิม** (เจ้าของสั่ง 2026-10-27) — ไม่ได้ทำทางเลือกเพิ่มรูปที่ชัดตาม C ก่อน (PATCH ebt 1.7.1 / expense 1.3.1): ebt กลุ่ม + "กลุ่มไหน" "กลุ่มงาน", ส่วน = รายการของ revenue;
  expense ส่วน = รายการของ revenue (ไม่ใส่ "กลุ่มไหน") — ผล C: ebt ชั้นกลุ่ม/ส่วน ระดับถูก 33 → 35/36, expense ชั้นส่วน 0 → 4/6
- server ซ้อม 8004 หยุดแล้ว (`./.ai/db/c0b2/serve.sh <tag>` เปิดใหม่ได้; สำเนาตอนนี้อยู่ในสภาพ C — `config.pristine.db` = สำเนาก่อนแตะ)

### C0b2.5 ขึ้นของจริง (2026-10-27 00:22, เจ้าของสั่ง "ขึ้นของจริงตาม §C0b2.3 ด้วยคำเดิม (05f989b)")
- ก่อน: server live pid 75437 (`--reload`, port 8000) ตอบ 200 · NT-Report main `514c6f0` สะอาด · แถว 29–38 `manual`/active
- 00:22:02 backup `~/nt-ai-backups/c0b2-ebt-expense-golive-20261027-002202/config.db` (integrity_check ok) — ไม่มี migration, ไม่ ff AI main (ผู้อ่านไม่เปลี่ยน code)
- 00:22:33 `HierarchyService.delete_level` × 10 → แถว 29–38 `is_active = 0` · 00:22:35 ff NT-Report main `514c6f0..05f989b` (ebt **1.7.0**, expense **1.3.0**; ไม่รวม `37e7246`)
- request แรกของแต่ละ context re-sync: `master_hierarchy` = 0–4 `manual`/0 + **10–14 `declared`/1** ทั้ง feed_ebt และ feed_expense ·
  `knowledge_sha` ebt `8fc79f1e…:1.6.0`, expense `cc892d87…:1.2.3` · quick_check ok
- ถามจริงผ่าน nt-ai (key id 5, ช่องทางเดียวกับ §C0b.4):
  **488** "ฝ่ายไหนมี EBT สะสมปี 2569 สูงสุด 5 อันดับ" `compiled:ebt` GROUP BY `unit_short_name` (ระดับฝ่าย) — 5 แถวตรง oracle ตามลำดับ (อป.2 462,782,754.61 … ตน.1 245,136,409.28) ·
  **489** "ฝ่ายไหนมีค่าใช้จ่ายสะสมปี 2569 สูงสุด 5 อันดับ" free SQL JOIN `dim_org_snapshot` ON `cost_center` + `effective_month` GROUP BY `unit_fname` (ฝ่ายเสาโทรคมนาคม 3,072,723,731.19 ตรง oracle)
- ข้อสังเกต: ebt เลือก `unit` หรือ `unit_short_name` (สองคอลัมน์ของระดับฝ่าย) ปนกันตั้งแต่ก่อนย้าย — server ซ้อม A 14/4, B 13/5 — ไม่ใช่ผลของการย้าย
- ยังไม่ push ทั้งสอง repo · commit ของ AI (`d9149ad` test, `6748dac` + ฉบับนี้ docs) อยู่บน branch `claude/angry-wright-bf7dca` ยังไม่เข้า main ·
  ย้อนกลับ: `git -C NT-Report reset --hard 514c6f0` (re-sync ถอนแถว 10–14 เอง) + `UPDATE master_hierarchy SET is_active = 1 WHERE id BETWEEN 29 AND 38` — หรือคืน config.db จาก backup

---

## COLDESC. คำอธิบายคอลัมน์ไทยของ feed_revenue ผ่าน Phase E round-trip — revenue 2.5.1 → 2.5.2 (2026-10-26/27, session แยกจาก §C0b)

ที่มา §C0b.3: ผิดอย่างมั่นใจ `M0418` มาจากคำอธิบาย `bu` = "business group (8 = รายได้อื่น)" (pass 1 ใส่ตัวกรอง BG 8) · ชื่อย่อทั้ง 4 ระดับยกตัวอย่าง "กกง., อป.2"
ซึ่งเป็นชื่อย่อของ**ฝ่าย**ทั้งคู่ (ป้ายนี้เข้าไปในคำถาม eval แล้วกระตุ้น mapping กลาง `กกง.` 18 ครั้ง) · คอลัมน์ของ revenue ว่าง 34 ชื่อ

### COLDESC.1 ทำอะไร
- สำเนา `.ai/db/cmeta/` (จาก `.ai/db/c0b/` ของ worktree `c0b-revenue-levels-2876c5` หลังรอบสุดท้ายของ §C0b — contract 2.5.0, org levels 10–14) ·
  ร่าง Phase E (`draft_columns` ตัวเดียวกับ `POST /admin/schema/columns/draft`) ทั้ง 17 ตาราง `feed_revenue_*` → 71 ร่าง `inferred`
- เขียนใหม่ทีละคอลัมน์จากข้อเท็จจริงที่วัดใน parquet ของ dist (คู่ 1:1, จำนวนค่า, ค่าจริงต่อระดับ, ยอดรวม 8 BG = ยอดองค์กร), `Revenue/pipeline/01_etl.py`
  (ชื่อย่อใน `fact_org_*` มาจาก NT_BU = `dim_org`; คอลัมน์ "2.0" = โครงสร้างปัจจุบันที่ใช้ remap org) และ `tools/feed/feed.py` COLUMN_OVERRIDES (ชื่อต้นทาง) ·
  ร่างอัตโนมัติผิด 2 ที่ — `dim_org.business_group` เขียนว่า "ระดับ 'กลุ่ม'" (จริง = กลุ่มของสายงาน 6 ค่า ต้นทางคอลัมน์ 'กลุ่มธุรกิจ' ของ NT_BU),
  `bu_seq` เขียนว่า "กลุ่มธุรกิจ — ระดับ 1" — แทนด้วยข้อความที่เขียนเอง · ข้อเสนอเต็ม: notes `revenue-col-desc-proposal.md` ของ session กลุ่มนี้
- เจ้าของอนุมัติ 34 คอลัมน์ → รับบนสำเนาผ่าน endpoint ของ admin (TestClient + override `require_admin`: accept ร่าง 71 แถว, PUT 44 แถว → `manual` 115) →
  `export_col_meta --context feed_revenue` (34 รายการ ไม่มีขัดกัน) → `col_meta` ใน NT-Report → **revenue 2.5.1** (`37e7246`, PATCH: contract ต่างจาก 2.5.0 เฉพาะ `description` + เวอร์ชัน)
- วัด 2.5.1 แล้วพบชั้นใหม่ (COLDESC.2) → แก้ชื่อเรียก 3 คอลัมน์ ทดสอบบนสำเนา เจ้าของอนุมัติ → **revenue 2.5.2** (`3d948e6`) ·
  `pytest tools/feed` **42 passed** ทั้งสองครั้ง (`/Library/Frameworks/Python.framework/Versions/3.10/bin/python3` — venv ของ AI ไม่มี pyarrow, `.venv` ของ NT-Report ไม่มี duckdb) ·
  ตรวจ round-trip: `col_meta` = ข้อความที่อนุมัติ = export จากสำเนา = contract ที่ทดสอบ; คำถามที่สร้างจาก contract 2.5.2 ตรงกับไฟล์ที่วัดทุกข้อ

### COLDESC.2 ชื่อเรียก (ส่วนก่อน " — ") คือป้ายมิติของ pass 1
`metric_compiler.dimension_labels` ใส่ส่วนแรกของคำอธิบาย (ก่อน " — " / ";", ≤ 60 ตัว) เป็นป้ายของแต่ละมิติใน catalog ของ pass 1 และ eval ใช้ส่วนเดียวกันเป็นป้ายในคำถาม —
ข้อความหลัง " — " ไม่ถึง pass 1 (schema ใน prompt = main view `fact_total_monthly` เท่านั้น)
- 2.5.1 `bu` = "กลุ่มธุรกิจ (BG) — …": คำถาม "กลุ่มไหน… / แยกตามกลุ่ม / แยกตามชื่อย่อของกลุ่ม" ไป GROUP BY `bu` ทั้งที่ level note บอก "กลุ่ม → `sub_division_name`"
  (audit 2838, 2840, 2844, 2845, 2945 — คลาส `sub_division_name` 13 → 9/14; server ซ้อม 8003 ของ §C0b เห็นแบบเดียวกันหลัง re-sync 2.5.1 กลางรอบ: audit 2837/2839/2943 ใน `.ai/db/c0b`)
- 2.5.1 `sub_product_key` = "รหัสบริการย่อย 2 หลัก ('00'–'99') — …": pass 1 ใส่ `sub_product_key BETWEEN '00' AND '99'` → `declined:shape:filter:BETWEEN` 6 (14 → 10)
- 2.5.2: `bu` = "business group (BG) — กลุ่มธุรกิจ …", `bu_seq` = "business group number — เลขกลุ่มธุรกิจ …", `sub_product_key` = "รหัสบริการย่อย — 2 หลัก ('00'–'99') …"
  (ข้อความไทยหลัง " — " เท่าเดิม; คำถาม "กลุ่มธุรกิจ" ถึง `bu` ผ่าน `master_hierarchy` level 0 อยู่แล้ว) · probe 56 คลาส: `bu` 14/14, `sub_division_name` 14/14, `sub_product_key` 12/14
- กติกาสำหรับคำอธิบายครั้งต่อไป: ชื่อเรียกสั้น ไม่มีค่า/ช่วงค่า/ตัวอย่าง และไม่ใช้คำที่ซ้อนกับคำของระดับอื่นใน `master_hierarchy` (เช่น "กลุ่ม…" ของมิติที่ไม่ใช่กลุ่มองค์กร)

### COLDESC.3 วัด (server ซ้อม 127.0.0.1:8006 บน `.ai/db/cmeta/`, โค้ด = main `8d8aeec`, key id 6, Redis db 6; คำถาม 792 ข้อ / 200 ชั้น สร้างใหม่จาก contract แต่ละรุ่น, 1 ต่อชั้น)
id / ชั้น / คำตอบที่ถูกของคำถามเหมือนฐานทุกข้อ — ต่างกันแค่ป้าย (126 จาก 200 ข้อที่ถูกเลือกเปลี่ยนข้อความ) จึงเทียบรายชั้น

| | ฐาน §C0b (2.5.0) | 2.5.1 | **2.5.2** |
|---|---|---|---|
| ถูกรวม | 174/200 | 179/200 | **187/200 (93.5%)** |
| compiled ถูก / ทั้งหมด | 162/164 | 160/167 | **170/174** |
| ผิดอย่างมั่นใจ (compiled แต่ผิด) | 2 | 7 | **4** |
| free SQL ถูก | 12/36 | 19/33 | 17/26 |
| ชั้นที่ป้ายเปลี่ยน (126) / ไม่เปลี่ยน (74) | 104 / 70 | 113 / 66 | **115 / 72** |
| `mapping_triggered:กกง.` | 18 | 4 | 4 (= ค่าจริงในคำถามกรอง `unit_sname`) |

รายมิติ (ฐาน → 2.5.2, จำนวนชั้น): `bu` 11 → **14**/14 · `sub_division_name` 13 → **14**/14 · `sub_division_sname` 0 → **12**/14 · `division_sname` 12 → 14/14 ·
`unit_name` 10 → 11/12 · `sub_product_key` 14 → 12/14 · `service_group_seq` 14 → 12/14 · `service_group_nt` 14 → 13/14 · `product_name` 10 → 9/10 · มิติอื่นเท่าเดิม ·
shape: top5/top10 ทั้งสองทาง 128/128, compare_up 19/20, by 12/16, filter 24/32

- **ส่วนที่ได้มาจากป้ายในคำถามเอง (ไม่ใช่ผู้ใช้จริง):** `sub_division_sname` 0 → 12 และ `M0418` — คำถามเดิมมี "(เช่น กกง., อป.2)" / "(8 = รายได้อื่น)" อยู่ในตัว;
  ป้ายใหม่ "ชื่อย่อของกลุ่มไหน…" ยังมีคำ "กลุ่มไหน" ที่ level note จับได้ · ที่เป็นผลของคำอธิบายต่อ pass 1 จริง: ชั้น "กลุ่ม" คงที่ 14/14 และ `bu` 14/14 ภายใต้ป้ายไทยของมิติอื่น
- **ผิดอย่างมั่นใจที่เหลือ 4:** `M0256` / `M0652` "แยกตามชื่อย่อของกลุ่ม" (ไม่มีรูปที่ชัดของ "กลุ่ม" → ไม่มี level note → `division_sname` / `bu`; ฐาน 0/14 อยู่แล้ว) ·
  `M0127` / `M0523` "แยกตามรหัสบริการย่อย": โมเดล GROUP BY `sub_product_key, sub_product_name` (411 แถว) ตามคำอธิบาย "ใช้คู่กับ product_key เสมอ" แต่ oracle
  GROUP BY รหัส 2 หลักอย่างเดียว (28 แถว — รวมบริการย่อยต่างผลิตภัณฑ์ที่เลขซ้ำกัน) — oracle ของมิติที่ไม่ใช่คีย์เดี่ยวควรตัดออกจาก eval
- ผิดลงที่เหลือ (free SQL หลัง mapping กลาง เป็นตั้งแต่ฐาน): `M0034` / `M0430` (`1.1`), `M0502` (`calling card`), `M0727` (`กรรมการผู้จัดการใหญ่`), `M0478` (`shape:filter:revenue_ytd`)
- ไฟล์ผล (gitignored, worktree `vigilant-engelbart-bec7f0`): `eval_results/metric_eval_feed_revenue_202609_20261026_2337.json` (2.5.1), `…_20261026_2346.json` (probe),
  `…_20261027_0005.json` (2.5.2); คำถาม `.ai/eval/metric_revenue_202609_{250,251,v2}.json`

### COLDESC.4 ลำดับขึ้นของจริงที่วางไว้
- **AI ไม่มี code เปลี่ยน** — ขึ้น = contract อย่างเดียว · `05f989b` (ebt 1.7.0 / expense 1.3.0 ของ §C0b2) ขึ้น NT-Report main ไปก่อนแล้ว (§C0b2.5) จึง ff ได้ตรง ๆ
- ลำดับ: (1) สำรอง config.db (2) ff NT-Report main → request แรกของ feed_revenue re-sync 2.5.2 เอง (แถว `declared` 174 แถวได้ข้อความใหม่)
  (3) **แถว `manual` 2 แถวของ `feed_revenue_dim_bu` บนของจริงชนะ contract**: `bu` = ข้อความสองชุดต่อกัน (ร่างระดับ 1 + "business group (8 = รายได้อื่น)"),
  `bu_seq` = "ลำดับของกลุ่มธุรกิจ" — แก้ผ่าน admin (PUT ข้อความ 2.5.2) ไม่ใช่ SQL ตรง; proposal `declared` #31/#32 ที่เปิดค้างเป็นข้อความเก่า ปฏิเสธได้
  (4) ตรวจ `SELECT source, count(*) FROM schema_metadata WHERE table_name LIKE 'feed_revenue_%' GROUP BY 1` และถาม "กลุ่มไหนมีรายได้สะสมสูงสุด 5 อันดับ" → GROUP BY `sub_division_name`
- contract ใน worktree ที่ใช้ร่วมกันขยับใต้ server ซ้อมทุกตัวที่ชี้มัน (server 8003 ของ §C0b re-sync 2.5.1 กลางรอบ) — server ซ้อมควรชี้สำเนา contract ของตัวเอง

### COLDESC.4b ขึ้นของจริง (2026-10-27 00:58–01:1x, เจ้าของสั่ง)
- 00:58 backup `~/nt-ai-backups/coldesc-golive-20261027-005821/config.db` (integrity_check ok; ก่อนขึ้น `knowledge_sha` `82ee8c6d…:2.3.2`, `declared` 174 + `manual` 2)
- 00:59 ff NT-Report main `05f989b..3d948e6` (revenue **2.5.2**) — request แรกของ feed_revenue (audit 490) re-sync: `knowledge_sha` `2dd1c6ff…:2.3.2`, แถว `declared` 174 แถวได้ข้อความใหม่
- แก้แถว `manual` ของ `feed_revenue_dim_bu` (`bu`, `bu_seq`) เป็นข้อความ 2.5.2 ผ่านหน้า Schema ของ admin (Browser pane, เจ้าของ login) → PUT `/admin/schema/columns/{id}` ·
  ตรวจใน config.db (อ่านอย่างเดียว) ทั้งสองแถว `manual`/active ข้อความตรง; proposal `declared` #31/#32 ถูก re-sync รวมเป็นข้อความ 2.5.2 แล้ว (เท่ากับแถว manual — ไม่ต้องทำอะไร) ·
  `export_col_meta` บน config.db จริงได้ `bu` / `bu_seq` ตรงกับ contract
- ถามจริงผ่าน nt-ai (key id 5 — ช่องทางเดียวกับ §C.5/§C0b.4):
  **490** "กลุ่มไหนมีรายได้สะสมสูงสุด 5 อันดับ" `compiled:revenue` GROUP BY `sub_division_name` (กลุ่มธุรกิจลูกค้าองค์กร 10,461 ล้าน = audit 485) ·
  **491** คำถามเดียวกันแบบ portal (scope `year_month` 202501…202609 ชุดเดียวกับ 486) → ผลเดียวกัน ·
  **492** "รายได้สะสมปีนี้แยกตามกลุ่มธุรกิจ" GROUP BY `bu` 8 แถว ไม่กรอง BG 8 (8.รายได้อื่น 2,103.05 ล้าน = audit 482/487) ·
  **493** "รายได้เดือนกันยายน 2569 แยกตามกลุ่มบริการ" GROUP BY `service_group_nt` 27 แถว (ตรงจำนวนใน parquet; ยอดรวม 3,353.09 ล้าน = `fact_total_monthly` 202609)
- AI: ff main `82634ee` → commit เอกสารนี้ (ไม่มี code — server ไม่ต้อง restart) · ยังไม่ push ทั้งสอง repo ·
  ย้อนกลับ: `git -C NT-Report reset --hard 05f989b` → re-sync คืนข้อความเดิมของแถว `declared` (แถว `dim_bu` ที่แก้ผ่าน admin คงอยู่) — หรือคืน config.db จาก backup

### COLDESC.5 ที่ยังไม่ทำ / ข้อควรรู้
- expense / sales / ebt ยังมีคำอธิบายชื่อย่อ "(เช่น กกง., อป.2)" แบบเดียวกัน (`domains.py` expense 3 คอลัมน์, sales 1, ebt 1) — ทำแบบ COLDESC ได้
- eval: oracle ของ `sub_product_key` (และมิติที่ไม่ใช่คีย์เดี่ยวอื่น) ไม่มีความหมาย · free SQL หลัง mapping กลาง (`กรรมการผู้จัดการใหญ่` 8, `1.1`, `1.hard infrastructure`) ยังเป็นงาน (2) ของ §C.6
- ยังไม่ได้รันครบ 792 ข้อ (1 ต่อชั้นเท่านั้น) · server ซ้อม 8006 (`./.ai/db/cmeta/serve.sh <tag>`) หยุดหลังวัด
