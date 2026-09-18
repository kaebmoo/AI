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
  (re-sync อัตโนมัติ); ตอนนี้ตั้งไว้: `feed_revenue` / `feed_expense` → `year_month` (expense map ไป `time_key`)
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
"data_as_of": {"period": 202608, "built_at": "2026-09-11T01:37:35+00:00", "build_id": null}
```
- `period` = งวดล่าสุดใน bundle (YYYYMM ค.ศ.), `built_at` = เวลา build (UTC), `build_id` = id ของ build
  (มีเมื่อ NT-Report publish แบบ atomic — `builds/<id>` + symlink `latest`; ก่อนหน้านั้นเป็น `null`)
- `null` = context ที่อ่าน business DB เดิม (legacy) หรือ error ก่อนอ่านข้อมูล
- portal ควรแสดงให้ผู้ใช้เห็น และเตือนเองเมื่อ `period` ไม่ตรงงวดของรายงานที่เปิดอยู่
- ระหว่าง publish (แบบเดิมที่ไม่ atomic) คำถามได้ `error` "ข้อมูลกำลังถูก publish — กรุณาถามใหม่" ไม่ใช่คำตอบจากไฟล์ครึ่งไฟล์

## ออก API key ให้ portal

```python
# python -c จาก project root (ใช้ venv เดียวกับ backend)
from app.db.session import SessionLocal
from app.services.api_key_service import APIKeyService

db = SessionLocal()
raw_key, record = APIKeyService(db).create_key(
    user_id=<admin_user_id>, name="nt-report-portal",
    scopes="query", rate_limit_per_minute=20, rate_limit_per_day=2000,
)
print(raw_key)  # เก็บใส่ .env ของ pocketbase_0 (ASSISTANT_API_KEY) — แสดงครั้งเดียว
```

- per-minute limit enforce ผ่าน Redis (F4.4) — Redis ล่ม = fail-open + warning
- **ไม่เปิด CORS** — portal เรียกผ่าน PB hook proxy (same-origin) เท่านั้น
