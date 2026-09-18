# Portal Integration (F11 Phase A — AI side)

## API สำหรับ NT-Report portal

Endpoint: `POST /api/v1/query/` (stateless) — auth ด้วย `X-API-Key`

Request เพิ่มเติมสำหรับ portal (optional ทั้งคู่ — contract เดิมไม่เปลี่ยน):
- `pinned_filters` (dict) — filter จาก dashboard เช่น `{"year_month": 202605}` — **v1: log เพื่อ audit เท่านั้น ยังไม่ inject เข้า query**
- `source` (str) — เช่น `"portal"` สำหรับ audit trail

ตัวอย่าง:
```json
{"question": "รายได้รวมเดือนพฤษภาคม 2569", "context": "feed_revenue",
 "include_sql": true, "include_data": true, "source": "portal",
 "pinned_filters": {"year_month": 202605}}
```

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
