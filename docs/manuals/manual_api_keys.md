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

## Key ที่ผูก workspace / จำกัด context (Plan 7 Phase 4)

Workspace = การแบ่ง context ภายใน deployment เดียว (เช่น `nt-report` = `feed_*`, `default` = context เดิม) — จัดการที่ `/api/v1/admin/workspaces`

สร้าง key ผ่าน API พร้อม `workspace` และ/หรือ `allowed_contexts`:

```json
POST /api/v1/admin/api-keys
{"name": "nt-report-portal", "workspace": "nt-report", "allowed_contexts": ["feed_revenue", "feed_sales"],
 "rate_limit_per_minute": 20, "rate_limit_per_day": 2000}
```

| ตั้งค่า | key ใช้ได้ |
|---|---|
| ไม่ระบุทั้งสอง | ทุก context — เหมือน key ก่อน Phase 4 ทุกอย่าง |
| `workspace` | context ที่ active ของ workspace นั้น (context ที่ย้ายออก/ปิด หายจากสิทธิ์ทันที) |
| `workspace` + `allowed_contexts` | ส่วนที่ทับกัน — allowlist ทำให้แคบลงได้อย่างเดียว |
| `allowed_contexts` อย่างเดียว | เฉพาะที่ระบุ |

- binding ที่เป็นไปไม่ได้ (workspace ไม่มี/ปิด, context ไม่มี, context ของ workspace อื่น, list ว่าง) = **400 ตอนสร้าง key**
- context นอกสิทธิ์ = **HTTP 403** ทั้งที่ระบุ `context` เองและที่ระบบเลือกให้ — ไม่มีการสลับไป context อื่นเงียบ ๆ; ไม่ส่ง `context` = ระบบเลือกภายในสิทธิ์ของ key
- key แบบนี้ใช้ได้เฉพาะ `/api/v1/query` และ `/api/v1/query/contexts` (endpoint อื่น = 403 แม้เจ้าของ key เป็น admin)
- context แบบ legacy (business DB เดิม) ของ key ที่ถูกจำกัด: SQL อ่านได้เฉพาะ main view ของ context นั้น — ตาราง/ view อื่นถูกปฏิเสธที่ชั้น SQL
- อ่านค่าไม่ได้ (JSON เสีย, config DB ล่ม) = ใช้ context ใดไม่ได้เลย (fail closed)
- หน้า admin UI ยังไม่มีช่อง workspace — ใช้ API หรือ `docs/PORTAL_INTEGRATION.md`

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
| GET / POST | `/api/v1/admin/workspaces` | ดู workspace + context ที่อยู่ในแต่ละตัว / สร้าง (ชื่อเป็น slug `a-z0-9_-`) |
| PUT | `/api/v1/admin/workspaces/{id}/contexts` | ย้าย context เข้า workspace (context อยู่ได้ workspace เดียว — key ของ workspace เดิมเสียสิทธิ์ทันที) |
| DELETE | `/api/v1/admin/workspaces/{id}` | ปิด workspace (soft) — key ที่ผูกอยู่ใช้อะไรไม่ได้จนกว่าจะเปิดคืน; ปิด `default` ไม่ได้ |
| PUT | `/api/v1/admin/workspaces/{id}/retention` | (Phase 4.5) override ของ workspace: `result_retention_days` (null = ค่ากลาง, 0 = ไม่ลบ), `store_result_data` (false = ไม่เก็บแถวผลลัพธ์) |
| GET | `/api/v1/admin/query-audit` | (Phase 4.5) audit ของทุกคำถาม — filter `api_key_id`, `user_id`, `workspace`, `context`, `date_from/to`, `has_error`, `q`; `format=csv` = export |

## Audit ของคำถามที่มาจาก API key (Plan 7 Phase 4.5)

ทุกคำถามผ่าน `/api/v1/query` ถูกบันทึกใน `query_audit`: key ไหน (`api_key_id`), ระบบไหน (`channel` = ค่า `source` ที่ผู้เรียกส่งมา หรือ `api`), workspace, context, `scope` ที่ส่งมา, คำถาม, SQL ที่รัน, ชื่อคอลัมน์และจำนวนแถวที่คืน, provider, `llm_policy`, และ error — **รวมคำขอที่ถูกปฏิเสธ** (scope ที่บังคับไม่ได้ = `ScopeError`, context นอกสิทธิ์ = `ContextNotAllowed`, ขัด policy ของ source = `LLMPolicyError`). ไม่เก็บค่าผลลัพธ์.

```bash
# ทุกคำถามของ key 3 ในเดือน ก.ย. เป็น CSV (เปิดใน Excel ได้ — UTF-8 BOM)
curl -H "Authorization: Bearer <ADMIN_TOKEN>" \
  "http://localhost:8000/api/v1/admin/query-audit?api_key_id=3&date_from=2026-09-01&date_to=2026-09-30&format=csv&limit=5000" -o audit.csv
```

ฝั่งผู้เรียก (เช่น portal) ยังต้องบันทึกเองว่า **ผู้ใช้คนไหน** ถามจากสิทธิอะไร — ฝั่ง AI เห็นแค่ key (PLAN_7 §6.2 ชั้น 5).

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
