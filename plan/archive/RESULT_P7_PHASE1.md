# RESULT Plan 7 Phase 1 — Source registry + DuckDB file source (zero-import)

**วันที่:** 2026-09-18 | **Branch:** `plan7-phase1` (ยังไม่ push/merge) | **Provider:** admin default (matcha, gpt-4.1)
**Interpreter:** `venv/bin/python3.14` (ตัวเดียวกับที่รัน pytest) | **DuckDB:** 1.5.5, duckdb-engine 0.17.0
**แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 1 | **ข้อสังเกต/bug เดิมที่พบ:** `plan/FIX_NOTES.md` (Plan 7 Phase 1)

## สรุป

`feed_revenue` อ่านไฟล์ CSV ใน `NT-Report/DataFeed/dist/revenue/latest/` **ในที่เดิม** ผ่าน DuckDB — ไม่มีการ import แม้แต่แถวเดียว
context อื่นทั้งหมด (revenue, expense, transfer price, pl_costtype) ผูกกับ source `legacy` = business DB เดิม พฤติกรรมไม่เปลี่ยน

| Exit criterion | ผล | ผ่าน? |
|---|---|---|
| pytest ไม่มี test เดิมพัง | 635 passed → **694 passed**, 3 skipped (+59 test ใหม่, test เดิมไม่ถูกแก้) | ✅ |
| eval `feed_revenue` จาก file source value match 14/14 เท่า F10 | **13/14** — เท่ากับ legacy วันเดียวกันทุกรอบ; ข้อที่ตก (#64) ตกเหมือนกันทั้ง 2 source | ⚠️ ไม่ถึง 14/14 (ไม่ใช่ผลของ source — ดูด้านล่าง) |
| latency P50 ไม่แย่กว่า 10.5 s เกิน 20% (≤ 12.6 s) | **5.88–6.27 s** (legacy วันเดียวกัน 6.16–6.26 s) | ✅ |
| test: resolver เลือก engine ถูก / legacy ใช้ DB เดิม / อ่านนอก root ไม่ได้ / SQL เขียนถูกปฏิเสธ | มีครบ (`tests/unit/test_data_sources.py`, `tests/unit/test_duckdb_file_adapter.py`) | ✅ |
| พิสูจน์ zero-import: งวดล่าสุด = งวดของไฟล์ ตรง control_totals | ตอบ **202608** = 3,434,072,699.62 บาท ตรง `control_totals.csv` (`__ALL__`) — สำเนาที่ import ค้าง 202605 | ✅ |

## Eval (`python -m scripts.eval.run_eval --context feed_revenue`, 14 golden จาก F10 ไม่ได้ regen)

golden SQL รันกับ source ของ context (file source → DuckDB) ส่วน SQL ที่โมเดลสร้างรันผ่าน QueryEngine ตามปกติ
P50 = median, P95 = nearest-rank; ทุกรอบ strict exact_match = 0 เพราะ alias ภาษาไทยไม่ตรง golden (เหมือน F10)

| รอบ | ไฟล์ผล (`eval_results/`, gitignored) | Source | โค้ด | value_match | ข้อที่ตก | P50 | P95 |
|---|---|---|---|---|---|---|---|
| F10 อ้างอิง | `eval_20260711_2018` | legacy import | ก่อน Plan 7 | 13 exact + 1 | — | 10.31 s | 17.49 s |
| F10 อ้างอิง | `eval_20260711_2149` | legacy import | ก่อน Plan 7 | **14/14** | — | 11.30 s | 17.05 s |
| ก่อน #1 | `eval_20260918_1305` | legacy import | ก่อน migrate | 13/14 | #64 | 6.26 s | 10.99 s |
| หลัง #1 | `eval_20260918_1310` | **file** | ก่อนแก้ LIKE | 10/14 | #52 #55 #61 #64 | 6.54 s | 7.93 s |
| หลัง #2 | `eval_20260918_1312` | **file** | + LIKE→ILIKE | 13/14 | #64 | 6.27 s | 10.85 s |
| ก่อน #2 | `eval_20260918_1314` | legacy (สลับด้วย `--legacy`) | เดียวกับหลัง #2 | 13/14 | #64 | 6.16 s | 8.15 s |
| หลัง #3 | `eval_20260918_1315` | **file** | เดียวกับหลัง #2 | 13/14 | #64 | 6.06 s | 7.36 s |
| **หลัง final** | `eval_20260918_1323` | **file** | final (query gate, bind by name) | **13/14** | #64 | **5.88 s** | **8.27 s** |

**สิ่งที่พบ:**
- **หลัง #1 ตก 3 ข้อเพราะ source จริง:** โมเดลเขียน `bu LIKE '%HARD INFRA%'` — SQLite LIKE ไม่สนตัวพิมพ์ (ได้ค่า) แต่ DuckDB สน (0 แถว) → แก้ให้ file source รัน `LIKE` เป็น `ILIKE` (นอก literal) = พฤติกรรม SQLite → หายทั้ง 3 ข้อ
- **#64 ตกทั้งสอง source ทุกรอบวันนี้:** "รายได้สะสมทั้งบริษัทตั้งแต่ต้นปีถึงเดือนพฤษภาคม 2569" — โมเดลเขียน
  `SELECT SUM(revenue_ytd) FROM feed_revenue_fact_bu_monthly WHERE year = 2026 AND CAST(month AS INTEGER) <= 5`
  (รวม YTD ข้ามงวด = ผิดกฎ point-in-time) ขณะที่ F10 (ก.ค.) เขียน `= 5` → พฤติกรรมโมเดล/gateway เปลี่ยน ไม่เกี่ยวกับ source;
  กฎ `bg8_ytd_not_summable` ใน contract ห้ามแค่ "sum revenue รายเดือน" ไม่ได้ห้าม sum `revenue_ytd` ข้ามงวดตรง ๆ → **รอเจ้าของตัดสิน** (PLAN_7 §11.7)
- latency วันนี้ต่ำกว่า F10 ทั้งสอง source (gateway เร็วขึ้น) — จึงเทียบกับ legacy วันเดียวกันเป็นหลัก: file source ต่างจาก legacy −4% ถึง +2%
- หลังเพิ่มกฎ DuckDB "ห้ามเทียบหลายคอลัมน์กับ subquery" โมเดลเขียน `year_month = (SELECT MAX(year_month) ...)` — ไม่มี DuckDB Binder/Catalog error ใน log ของรอบหลัง ๆ เลย

## พิสูจน์ zero-import (ถามผ่าน QueryEngine เต็มเส้นทาง, context = feed_revenue, โค้ด final)

| | ค่า |
|---|---|
| `MAX(year_month)` ใน file source | **202608** |
| `MAX(year_month)` ในสำเนาที่ import ไว้ (`nt_fi_report.sqlite`) | 202605 (ไม่ถูกแตะ — `feed_import_log` ยังมี 1 แถวของ 2026-07-11) |
| `control_totals.csv` ล่าสุด | `__ALL__` 202608 = 3,434,072,699.62 / `3.Mobile` 202608 = 162,334,872.01 |

| คำถาม | SQL ที่โมเดลสร้าง (ย่อ) | คำตอบ | ตรง control_totals |
|---|---|---|---|
| รายได้รวมทั้งบริษัทเดือนล่าสุดที่มีข้อมูลเท่าไร | `SUM(revenue) … WHERE year_month = (SELECT MAX(year_month) …)` | 3,434,072,699.62 | ✅ |
| งวดล่าสุดที่มีข้อมูลรายได้คือเดือนอะไร | `ORDER BY year DESC, month DESC LIMIT 1` | 2026 / 8 | ✅ |
| รายได้ของกลุ่มธุรกิจ 3.Mobile เดือนล่าสุดเท่าไร | `bu LIKE '%3.Mobile%' AND year_month = (SELECT MAX …)` | 162,334,872.01 | ✅ |

## ลงทะเบียน source (`python -m scripts.datafeed.register_file_source --domain revenue --source …/DataFeed/dist`)

```
Domain revenue: schema 2.0.0, period 202608, root …/NT-Report/DataFeed/dist/revenue/latest
Integrity pre-check OK (16 files)            ← reconcile.ok + sha256 ทุกไฟล์ที่ใช้
Row counts OK (15 views)                     ← นับผ่าน view ตรง manifest.row_counts
Control totals OK (576 rows within tolerance) ← ผ่าน view ตรง control_totals.csv
Registered source 'datafeed_revenue' (15 views) → feed_revenue in 4.8s — no rows imported
```
- สลับกลับ legacy ด้วย `--legacy` แล้วลงทะเบียนใหม่ — ทดสอบจริงระหว่างรอบ eval "ก่อน #2"/"หลัง #3" ✅
- `import_datafeed.py` ไม่ถูกแก้ (fallback) — ตาราง `feed_revenue_*` ใน business DB ยังอยู่ครบ
- view definition อยู่ใน `.source_cache/datafeed_revenue-<fingerprint>.duckdb` (~270 KB, ไม่มีข้อมูล)
- knowledge/golden ของ F10 ใช้ต่อได้โดยไม่ regen — ชื่อ view = ชื่อตาราง F10 และ**ชุดคอลัมน์** ของ contract 2.0.0 ตรงกับตาราง F10 (1.0.0) และ `schema_metadata` ครบ 15/15 ตาราง (ตรวจแล้ว); แต่**ลำดับคอลัมน์เปลี่ยน** 2 ตาราง (`dim_product`, `dim_sub_product`) — ยืนยันว่าต้องผูกคอลัมน์ตามชื่อ ไม่ใช่ตำแหน่ง

## ความปลอดภัย (DuckDB 1.5.5 — ตรวจจริง)

| ชั้น | กันอะไร | test |
|---|---|---|
| F4 validator (+ กฎ file access เฉพาะ file source) | non-SELECT, หลาย statement, `read_*`/`glob`/`*_scan` | `TestValidator` |
| query gate (parse ด้วย `json_serialize_sql` ของ DuckDB) | SELECT เดียวที่อ้างเฉพาะ view ที่ลงทะเบียน/CTE — ห้าม table function (`enable_logging`, `query`, `read_*` …) และ system view | `TestQueryGate` |
| engine lock: read_only + `allowed_paths` (เฉพาะไฟล์ที่ลงทะเบียน) + `enable_external_access=false` + `lock_configuration=true` | อ่านไฟล์นอก allowlist (รวมไฟล์อื่นใน root), COPY/ATTACH/INSTALL/LOAD/http, SET กลับ | `TestEngineLock` (ใช้ raw cursor — ข้าม gate/validator เพื่อพิสูจน์ชั้นนี้แยก) |
| cursor ใหม่ทุก query | TEMP view ทับชื่อ view ข้าม query | `test_temp_view_cannot_poison_later_queries` |
| registry | `file_name` หลุด root (`..`/symlink), ชนิดคอลัมน์นอก allowlist | `test_registry_path_escaping_root_rejected` |

**Security review พบ (แก้แล้ว):** `lock_configuration` ไม่กัน `enable_logging()` — แบบ file ทำ process ล่ม (reproduce แล้ว: libc++abi terminate), แบบ memory เปิดให้อ่าน SQL ของผู้ใช้อื่นผ่าน `duckdb_logs` → เป็นเหตุผลของ query gate
gate ตรวจกับ SQL จริง 58 แบบ (SQL ที่โมเดลสร้างใน eval ทุกรอบ + golden + proof + probe ของ ValueVerifier/WarningDetector): **ไม่ปฏิเสธผิดเลย**

## Review อิสระ (workflow 5 มิติ: security / legacy regression / correctness / concurrency / silent-wrong-DB + ผู้พยายามหักล้างต่อ finding)

| Finding | ความรุนแรง | ผล |
|---|---|---|
| `enable_logging()` ข้าม lock → process ล่ม / log รั่ว | high | แก้ — query gate (`6f42841`) |
| resolver จับชื่อ context ตรงตัว แต่ `get_context_info` รับ `feed revenue` → prompt ของ file แต่ข้อมูล legacy | high | แก้ (`b2e7ac7`) |
| อ่าน CSV ด้วย `columns=` = ผูกตามตำแหน่ง → publish ที่สลับคอลัมน์ทำค่าสลับเงียบ | medium | แก้ — ผูกตามชื่อ header (`7084f3e`) |
| หารศูนย์ได้ inf/nan (SQLite ได้ NULL) → JSON ผิด คำตอบ SSE หาย | medium | แก้ (`7084f3e`) |
| query cache ไม่รู้จัก source → เปลี่ยน source แล้วตอบจาก source เดิมได้ 30 นาที | medium/low | แก้ (`e4b2f69`) |
| `latest/` เป็น symlink แล้วถูกชี้ใหม่ → permission error จน restart | low | แก้ — realpath ใน fingerprint (`6f42841`) |
| COPY/EXPORT ลง temp dir ของ DuckDB ได้ถ้า SQL ข้าม validator | low | ปิดด้วย query gate |
| กฎ file access ใน validator กระทบ SQLite `glob()` ของ legacy | low | แก้ — ใช้เฉพาะ file source (`b2e7ac7`) |
| export 0 แถวไม่มีหัวคอลัมน์ | low | แก้ (`d9f7443`) |

## Commits (branch `plan7-phase1`)

```
ad39bb7 feat(P7-1): data source registry migration + read-only DuckDB file adapter
8455d7c feat(P7-1): SourceResolver — engine per request from context → source
8823cee feat(P7-1): register DataFeed bundle as DuckDB file source (zero-import)
b2e7ac7 fix(P7-1): SQLite parity on the file source + resolver/validator fixes
e4b2f69 fix(P7-1): query cache hit must come from the context's current source
6f42841 fix(P7-1): parser-based query gate on file sources; follow symlinked roots
7084f3e fix(P7-1): bind CSV columns by header name; x/0 returns NULL like SQLite
d9f7443 fix(P7-1): zero-row file-source export keeps its header row
```

## สถานะ DB หลังจบงาน (local — ไม่อยู่ใน git)

- `config.db`: migrate แล้ว (`data_sources`, `source_tables`, `schema_contexts.source_id`) — backup ก่อน migrate อยู่ที่ scratchpad ของ session
- `feed_revenue` → `datafeed_revenue` (file); context อื่น 5 ตัว → `legacy`
- `nt_fi_report.sqlite`, NT-Report `DataFeed/` — ไม่ถูกแก้
