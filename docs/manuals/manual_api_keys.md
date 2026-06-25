# API Keys — คู่มือการจัดการ

## เข้าถึง

- **URL:** http://localhost:5173/api-keys
- **สิทธิ์:** Admin only

## ภาพรวม

ระบบ API Keys ช่วยให้ระบบภายนอก (เช่น OpenMiniCrew, custom scripts) สามารถเรียกใช้ AI Assistant ได้โดยไม่ต้องผ่าน session-based authentication โดยใช้ stateless API key

## สร้าง API Key

1. เข้าหน้า API Keys
2. กด **"Create New Key"**
3. ตั้งชื่อ key (เช่น "OpenMiniCrew Production")
4. เลือก scope:
   - `query` (default) — เรียกใช้ /query/ endpoint เท่านั้น
   - `admin` — เข้าถึง admin endpoints
   - `full` — เข้าถึงทุก endpoint
5. ตั้ง rate limit:
   - Per-minute: 30 requests (default)
   - Per-day: 1000 requests (default)
6. กด **Create**
7. **สำคัญ:** raw key จะแสดงครั้งเดียวเท่านั้น — คัดลอกเก็บไว้ทันที

## ใช้งาน API Key

ส่ง key ผ่าน HTTP header:

```
X-API-Key: <API_KEY>
```

### POST /api/v1/query/

Stateless query endpoint — ถามคำถามและรับคำตอบโดยไม่ต้องมี conversation

```json
{
  "question": "รายได้รวมปี 2568",
  "context": "revenue",
  "include_sql": true,
  "include_data": true,
  "max_rows": 10
}
```

**Response:**

```json
{
  "answer": "รายได้รวมปี 2568 เท่ากับ ...",
  "sql": "SELECT SUM(REVENUE_VALUE) FROM revenue WHERE YEAR = 2025",
  "data": [...],
  "context": "revenue"
}
```

### GET /api/v1/query/contexts

Public endpoint — ไม่ต้อง auth

```json
[
  {
    "name": "revenue",
    "display_name": "รายได้"
  },
  {
    "name": "expense",
    "display_name": "ค่าใช้จ่าย"
  }
]
```

## Authentication Priority

เมื่อมี request เข้ามา ระบบจะตรวจสอบตามลำดับ:

1. **X-API-Key header** — ถ้ามี ใช้ API key auth
2. **Session cookie** — ถ้ามี ใช้ session auth
3. **Bearer token** — ถ้ามี ใช้ token auth

## Revoke API Key

1. เข้าหน้า API Keys
2. หา key ที่ต้องการ revoke
3. กด **Revoke**
4. Key จะถูกปิดทันที — ใช้ต่อไม่ได้

## Rate Limiting

| Limit | Default | หมายเหตุ |
|-------|---------|----------|
| Per-minute | 30 requests | ตั้งค่าได้ตอนสร้าง key |
| Per-day | 1000 requests | ตั้งค่าได้ตอนสร้าง key |

เมื่อเกิน limit จะได้รับ response:

```
HTTP 429 Too Many Requests
```

## ดู Usage Statistics

- เข้าหน้า API Keys
- กดที่ key เพื่อดูสถิติการใช้งาน
- API: `GET /api/v1/admin/api-keys/{id}/usage`

## Admin API Endpoints

| Method | Path | คำอธิบาย |
|--------|------|----------|
| POST | `/api/v1/admin/api-keys` | สร้าง key ใหม่ |
| GET | `/api/v1/admin/api-keys` | ดู keys ทั้งหมด |
| DELETE | `/api/v1/admin/api-keys/{id}` | Revoke key |
| GET | `/api/v1/admin/api-keys/{id}/usage` | ดูสถิติการใช้งาน |

## Integration กับ OpenMiniCrew

ตั้งค่าใน `.env` ของ OpenMiniCrew:

```env
NT_AI_API_URL=http://localhost:8000/api/v1/query/
NT_AI_API_KEY=<API_KEY>
```

## Security Notes

- API key ถูกเก็บเป็น hash ในฐานข้อมูล (ไม่เก็บ plaintext)
- แสดง prefix เท่านั้นในหน้า admin (เช่น `ntai_abc...`)
- Key ที่ถูก revoke จะไม่สามารถใช้ได้อีก
- Rate limit ตรวจสอบทั้ง per-minute และ per-day
