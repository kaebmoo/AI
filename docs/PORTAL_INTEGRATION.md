# Portal Integration (F11 Phase A — AI side)

## API สำหรับ NT-Report portal

Endpoint: `POST /api/v1/query/` (stateless) — auth ด้วย `X-API-Key`

Request เพิ่มเติมสำหรับ portal (optional ทั้งหมด — contract เดิมไม่เปลี่ยน):
- `scope` (dict) — **ขอบเขตข้อมูลที่บังคับที่ชั้น SQL** (Plan 7 Phase 3) เช่น `{"year_month": 202607}` หรือ `{"org_code": ["1L00201"]}`
- `pinned_filters` (dict) — log เพื่อ audit เท่านั้น ไม่มีผลกับคำตอบ (ช่วงเปลี่ยนผ่าน — ใช้ `scope` แทน)
- `source` (str) — เช่น `"portal"` สำหรับ audit trail

ตัวอย่าง:
```json
{"question": "รายได้รวมเดือนล่าสุด", "context": "feed_revenue",
 "include_sql": true, "include_data": true, "source": "portal",
 "scope": {"year_month": 202607}}
```

### `scope` — ทำงานอย่างไร
- key ที่ใช้ได้ต่อ context = `schema_contexts.scope_columns` (`{key: column}`) — context `feed_*` ได้จาก `scope_columns` ใน contract
  (re-sync อัตโนมัติ); ตอนนี้ (contract 2026-09-19) ทุกโดเมนประกาศ `year_month` (expense/ebt map ไป `time_key`) และ
  `org_code` → `cost_center` — ไม่มี `scope_exempt`: dataset ที่ไม่มี `cost_center` (เช่น revenue `fact_bu_monthly`,
  ebt `fact_ebt_total_monthly`, dim ที่ไม่มีงวด) ใช้ไม่ได้เมื่อ scope มี key นั้น
- ค่า: จำนวนเต็มหรือข้อความ หรือ list ของค่าเหล่านั้น (1–1000 ค่า = `IN`); หลาย key = AND
- **key ที่ context ไม่ประกาศ / ค่าผิดชนิด → HTTP 400** — ไม่มีทางตอบแบบไม่กรอง
- ระบบห่อทุกตารางของ context ด้วย TEMP view ต่อ query: ตารางที่มีคอลัมน์ครบ = กรองตาม scope, ตารางที่ไม่มี = ใช้ไม่ได้;
  SQL ของโมเดลถูกตรวจด้วย parser ให้อ้างได้เฉพาะตารางที่กรองแล้ว แบบไม่มี schema นำหน้า — prompt (ช่วงข้อมูล, ค่าตัวอย่าง, value lookup)
  เห็นข้อมูลชุดเดียวกัน → "เดือนล่าสุด" ภายใต้ `{"year_month": 202607}` = 202607
- context legacy (business DB เดิม) ใช้ scope ได้ถ้า admin ตั้ง `scope_columns` — query ที่มี scope รันใน process บน connection read-only
  ใหม่ต่อ query (ไม่ผ่าน MCP) และอ่านได้เฉพาะ main view ของ context
- cache คำตอบแยกตาม scope

Response มี `data_as_of` (Plan 7 Phase 2) — ความสดของข้อมูลที่ใช้ตอบ มาจาก `manifest.json` ของ build ที่ AI ตรวจแล้ว
(reconcile.ok + sha256) และเป็น build เดียวกับที่ SQL อ่านจริง (คำตอบจาก cache ก็เป็น build เดียวกัน เพราะ cache ผูก build):
```json
"data_as_of": {"period": 202608, "built_at": "2026-09-18T23:54:11+00:00", "build_id": "20260918T235411Z"}
```
- `period` = งวดล่าสุดใน bundle (YYYYMM ค.ศ.), `built_at` = เวลา build (UTC), `build_id` = id ของ build
  (มีเมื่อ NT-Report publish แบบ atomic — `builds/<id>` + symlink `latest`; ก่อนหน้านั้นเป็น `null`)
- `null` = context ที่อ่าน business DB เดิม (legacy) หรือ error ก่อนอ่านข้อมูล
- portal ควรแสดงให้ผู้ใช้เห็น และเตือนเองเมื่อ `period` ไม่ตรงงวดของรายงานที่เปิดอยู่
- ระหว่าง publish (แบบเดิมที่ไม่ atomic) คำถามได้ `error` "ข้อมูลกำลังถูก publish — กรุณาถามใหม่" ไม่ใช่คำตอบจากไฟล์ครึ่งไฟล์

## คำถามข้ามหลาย context (Plan 7 Phase 5)

ปิดเป็นค่าเริ่มต้น — เปิดต่อ workspace: `PUT /api/v1/admin/workspaces/{id}/multi-context` `{"enabled": true}` (เก็บใน `admin_config.multi_context_workspaces` = JSON list ของชื่อ workspace)

เมื่อเปิด และ**ไม่ได้ส่ง `context`**: คำถามที่มีคำเฉพาะของ context มากกว่าหนึ่งตัว (ใน workspace เดียวกัน และในสิทธิ์ของ key) เช่น
"รายได้และค่าใช้จ่ายเดือนกรกฎาคม 2569" จะถูกแตกเป็นคำถามย่อยต่อ context → แต่ละข้อรันผ่าน pipeline เดิม (scope / allowlist / policy / audit ของตัวเอง) → รวมคำตอบด้วย template ใน code (ไม่มี LLM ในขั้นรวม, ไม่ JOIN ข้าม source)

Response ของคำถามแบบนี้:
```json
{"answer": "คำถามนี้ใช้ข้อมูลจาก 2 แหล่ง — … **1. DataFeed revenue (`feed_revenue`) — ข้อมูลถึงงวด 202608** …",
 "context": "feed_revenue+feed_expense", "row_count": 2, "data_as_of": null,
 "parts": [{"context": "feed_revenue", "question": "รายได้เดือนสิงหาคม 2569", "answer": "…", "row_count": 1,
            "error": null, "data_as_of": {"period": 202608, "built_at": "…", "build_id": "…"}, "sql": "…", "data": [...]},
           {"context": "feed_expense", "…": "…"}],
 "computed": {"operation": "ratio", "operands": ["feed_revenue", "feed_expense"],
              "values": [3434072699.62, 3690470021.65], "value": 0.9305}}
```
- `parts` = ที่มาของตัวเลขแต่ละตัว (`sql` / `data` มีเมื่อขอ `include_sql` / `include_data`; `max_rows` ต่อส่วน); `data_as_of` ระดับบน = `null` — ความสดอยู่ต่อส่วน; คำตอบ context เดียว: `parts` = `computed` = `null` (field อื่นเหมือนเดิม)
- `computed` = อัตราส่วน / ส่วนต่าง ที่**คำนวณใน code** เมื่อคำถามขอ, ทุกส่วนได้ค่าเดียว และงวดล่าสุดของ source เท่ากัน; ส่วนต่างระหว่างสอง source ติดป้าย "ไม่ใช่กำไร / EBT ทางการ" (กำไรทางการมาจาก `feed_ebt`)
- งวดล่าสุดของ source ไม่เท่ากัน (เช่น revenue 202608, ebt 202607) → คำตอบมีบรรทัดเตือน + งวดของแต่ละส่วน และ**ไม่คำนวณ**ข้ามส่วน
- ส่วนใดตอบไม่ได้ → `parts[].error` + `error` ระดับบน + ข้อความ "ตอบได้ k จาก n ส่วน" — ไม่มีการเดาตัวเลข
- `scope` ใช้กับทุกคำถามย่อย; context ใดในชุดไม่ประกาศ key นั้น → **400 ทั้งคำถาม**; context นอกสิทธิ์ของ key ไม่ถูกพิจารณาเลย และ 403 ของข้อย่อย = 403 ทั้งคำถาม; ไม่ข้าม workspace
- latency ≈ 1 call แตกคำถาม + คำถามย่อยรันขนาน (วัด 2026-09-19: P50 ~9 s)
- audit: แถวแม่ (`context_name` = `a+b`) + แถวของคำถามย่อย ใช้ `request_group` เดียวกัน (`GET /admin/query-audit?request_group=…`)
- ช่องทาง: `/api/v1/query` เท่านั้น (chat / telegram ยังเป็น context เดียว)

## ออก API key ให้ portal

```python
# python -c จาก project root (ใช้ venv เดียวกับ backend)
from app.db.session import SessionLocal
from app.services.api_key_service import APIKeyService

db = SessionLocal()
from app.services.workspaces import resolve_key_binding

workspace_id, allowed = resolve_key_binding("nt-report", None)  # หรือ ["feed_revenue", ...] เพื่อจำกัดแคบลงอีก
raw_key, record = APIKeyService(db).create_key(
    user_id=<admin_user_id>, name="nt-report-portal",
    scopes="query", rate_limit_per_minute=20, rate_limit_per_day=2000,
    workspace_id=workspace_id, allowed_contexts=allowed,
)
print(raw_key)  # เก็บใส่ .env ของ pocketbase_0 (ASSISTANT_API_KEY) — แสดงครั้งเดียว
```
หรือผ่าน admin API: `POST /api/v1/admin/api-keys` `{"name": "nt-report-portal", "workspace": "nt-report", "rate_limit_per_minute": 20, "rate_limit_per_day": 2000}`

### Key ที่ผูก workspace (Plan 7 Phase 4)
- เห็นเฉพาะ context ของ workspace นั้น (config ปัจจุบัน: `nt-report` = `feed_revenue`, `feed_expense`, `feed_sales`, `feed_ebt`); `allowed_contexts` ทำให้แคบลงได้อีก ไม่มีทางกว้างขึ้น
- context นอกสิทธิ์ → **HTTP 403** (ทั้งที่ระบุชื่อเองและที่ระบบเลือกให้) — ห้าม retry โดยเปลี่ยน context เอง; ไม่ส่ง `context` = ระบบเลือกภายในสิทธิ์ของ key
- ใช้ได้เฉพาะ `/api/v1/query` และ `/api/v1/query/contexts` (endpoint อื่น = 403); `GET /query/contexts` พร้อม key จะแสดงเฉพาะ context ที่ key ใช้ได้
- key เดิมที่ไม่ผูก workspace ทำงานเหมือนเดิมทุกอย่าง

- per-minute limit enforce ผ่าน Redis (F4.4) — Redis ล่ม = fail-open + warning
- **ไม่เปิด CORS** — portal เรียกผ่าน PB hook proxy (same-origin) เท่านั้น
