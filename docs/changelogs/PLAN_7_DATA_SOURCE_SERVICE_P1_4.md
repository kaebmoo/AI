# Plan 7 Phase 1–4 — Data Source as a Service (2026-09-18 → 2026-09-19)

แผน: `plan/PLAN_7_DATA_SOURCE_SERVICE.md` · ผลรายเฟส: `plan/archive/RESULT_P7_PHASE{1,2,3,4}.md` · ข้อสังเกต/การตัดสินใจ: `plan/FIX_NOTES.md`

## สิ่งที่เปลี่ยนสำหรับผู้ใช้ / ผู้ดูแล

| เรื่อง | ก่อน | หลัง |
|---|---|---|
| ข้อมูล DataFeed ของ NT-Report | ต้อง import เข้า business DB ด้วยมือ (ค้างงวดเก่า) | อ่านไฟล์ในที่เดิมผ่าน DuckDB — publish build ใหม่แล้วคำถามถัดไปเห็นเอง; คำตอบมี `data_as_of` |
| ความรู้ของ context `feed_*` | รัน script gen docs เอง | สร้างจาก contract และ re-sync เองเมื่อ contract/schema_version เปลี่ยน; instruction แสดงทุกตารางของ contract |
| โดเมน | revenue | revenue, expense, sales, ebt (eval 14/14, 12/12, 12/12, 35/36) |
| ขอบเขตข้อมูลของผู้เรียก | `pinned_filters` = log อย่างเดียว | `scope` บังคับที่ชั้น SQL (file + legacy); key ที่ไม่ประกาศ = 400 |
| API key | เห็นทุก context | ผูก workspace / allowlist ได้ → นอกสิทธิ์ 403, ใช้ได้เฉพาะ `/api/v1/query*`; key เดิมไม่เปลี่ยน |
| Vanna brain | ก้อนเดียว ทุก context ปนกัน | แยกต่อ workspace (`<VANNA_CHROMA_PATH>__<workspace>`) |
| ลงทะเบียน source | CLI เท่านั้น | + `POST /admin/sources/register`, `GET /admin/sources`, `/sources/{name}/status` |
| หน้า admin กับตาราง `feed_*` | เห็นสำเนาเก่าใน business DB | อ่านจากไฟล์จริง; onboarding ปฏิเสธตารางที่มาจาก contract |
| eval harness | คอลัมน์ label เพิ่ม = mismatch | = value_match (ตัวเลขเกิน/คอลัมน์ขาด ยัง mismatch) |

## ไฟล์หลัก
- `app/services/data_sources.py` — `SourceResolver`, `request_scope`, `request_pinned`, `registered_tables`
- `app/services/database_adapter.py` — `DuckDBFileAdapter`, `ScopedDuckDB`, `ScopedSQLite`, query gate `check_select`
- `app/services/datafeed_knowledge.py` — knowledge จาก contract + `ensure_current`
- `app/services/source_registration.py` — gate + การลงทะเบียน (CLI และ admin API ใช้ร่วมกัน)
- `app/services/workspaces.py` — allowlist ของ key, `canonical_context`, `BrainFilter`
- `app/api/v1/admin/{sources,workspaces}.py`, `app/api/v1/query.py` (`scope`, `data_as_of`, 403)
- `scripts/migrate_data_sources.py`, `scripts/migrate_workspaces.py`, `scripts/datafeed/*`

## Upgrade
```bash
python scripts/migrate_data_sources.py
python scripts/migrate_workspaces.py
python -m scripts.datafeed.register_file_source --domain <d> --source <DataFeed/dist>   # ต่อโดเมน; ซ้ำเมื่อ contract เพิ่มตาราง/คอลัมน์
```

## ความปลอดภัย (review อิสระ)
- Phase 1: gate ของ DuckDB (parse ด้วย DuckDB เอง) หลังพบว่า `lock_configuration` ไม่กัน `enable_logging()`
- Phase 3: bypass ผ่าน CTE scoping — แก้ `525c5b6`
- Phase 4: allowlist ตรวจชื่อ normalize แต่ส่งชื่อดิบต่อ → ตกไป legacy DB — แก้ `f07439d` (ชื่อจริงเท่านั้น + `request_pinned`); review รอบสองไม่พบช่องโหว่

## ลบออก (REMAIN-9.9)
`matcha_examples.py`, `business_db.py`, adapter SQLite/PostgreSQL/MSSQL + `create_adapter` — ไม่มี caller

## ยังไม่ทำ
Admin UI ของ workspaces/sources · Phase 4.5 data protection (`llm_data_policy`, retention, DSR) · Phase 5 ถามข้าม context · Phase 6 MCP SSE · S3/HTTPS source
