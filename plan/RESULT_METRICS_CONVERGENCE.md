# RESULT — Metrics convergence (`plan/PLAN_METRICS_CONVERGENCE.md`)

> ไฟล์นี้เติมท้ายทุก run ของแผน (§8): A → D → E → B → C-0b → C-00/C-01 · หนึ่งหัวข้อต่อ phase

| Phase | สถานะ | วันที่ | commit (AI) |
|---|---|---|---|
| **A** มองเห็นเส้นทางของทุกคำถาม | ✅ **ขึ้นของจริงแล้ว** + push (CI เขียว run 40091378614) | 2026-10-24 | `34845de`, `655faeb` |
| D eval ที่สร้างเองจากคำประกาศ | ⬜ ยังไม่ทำ | | |
| E คำอธิบายคอลัมน์ feed อัตโนมัติ | ⬜ ยังไม่ทำ | | |
| B ตัวตรวจ SQL ของ pass 2 | ⬜ ยังไม่ทำ | | |
| C-0b คำศัพท์ระดับหน่วยงานทุกโดเมน | ⬜ ยังไม่ทำ (ระหว่างนี้ feed_ebt + feed_expense เป็นแถว `manual` — §A.6) | | |
| C-00/C-01 metrics ของ revenue / sales | ⬜ ยังไม่ทำ | | |
| C-0c ratio จัดอันดับอย่างมีความหมาย | ✅ ทำก่อนแผนนี้ (`941cd0a`, ebt 1.6.0) | 2026-10-24 | |

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
