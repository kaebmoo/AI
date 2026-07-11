# Reports / Export API (F6)

Export ผลลัพธ์คำถามเป็น xlsx โดย**รัน SQL ที่บันทึกไว้ใหม่ทั้งหมด** (ไม่ใช่ข้อมูล session ที่ถูกตัด 1,000 แถว)

Base: `/api/v1/reports` — ทุก endpoint ต้อง auth (session token หรือ API key)

## Flow

1. `POST /api/v1/reports/` body `{"chat_history_id": 123}` → `{"id": "<uuid>", "status": "pending"|"done", ...}`
   - มี Celery/Redis: ตอบ `pending` ทันที แล้ว worker ประมวลผล
   - ไม่มี: รัน inline (request ช้าแต่จบใน call เดียว) ตอบ `done`
   - Rate limit: 10 ครั้ง/ชั่วโมง/ผู้ใช้
2. Poll `GET /api/v1/reports/{id}` จน `status = done` (ไม่มี SSE — poll เอา)
3. `GET /api/v1/reports/{id}/download` → ไฟล์ `nt-report-YYYYMMDD.xlsx`
   - Sheet "Data": ข้อมูลเต็ม (cap 100,000 แถว — เกินจะมี `truncated: true`)
   - Sheet "Info": question, SQL, เวลาสร้าง (เวลาไทย), row_count, truncated, ผู้ขอ

`GET /api/v1/reports/` → list export ของตัวเอง (`?skip=&limit=`)

## Status flow

`pending → running → done | failed` (`failed` มี `error`)

## Errors

| Code | เมื่อไร |
|------|---------|
| 400 | chat ไม่มี SQL / SQL ไม่ผ่าน validation / export ยังไม่ done ตอน download |
| 403 | ไม่ใช่เจ้าของ (admin ดูได้ทุกอัน) |
| 404 | ไม่พบ export id |
| 410 | ไฟล์หมดอายุ (retention 7 วัน — config `export_retention_days`) หรือถูกลบแล้ว |

## Config (admin_config)

- `export_max_rows` (default 100000)
- `export_retention_days` (default 7)

## ตัวอย่าง

```bash
curl -X POST -H "X-Session-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"chat_history_id": 123}' http://localhost:8000/api/v1/reports/
curl -H "X-Session-Token: $TOKEN" http://localhost:8000/api/v1/reports/<id>
curl -OJ -H "X-Session-Token: $TOKEN" http://localhost:8000/api/v1/reports/<id>/download
```
