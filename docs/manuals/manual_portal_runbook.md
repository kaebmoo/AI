# Runbook — NT-Report portal ถามตอบผ่าน AI

ใช้ตอนเปิด/ปิด/ดูแลช่องทาง "ถามข้อมูลรายงานนี้" ของ portal (Plan 7 ผู้ใช้รายแรก)
สัญญาของ API อยู่ที่ [PORTAL_INTEGRATION.md](../PORTAL_INTEGRATION.md) · ความปลอดภัย: [DEPLOYMENT_SECURITY.md](../DEPLOYMENT_SECURITY.md)
· คู่มือ key: [manual_api_keys.md](manual_api_keys.md) · ฝั่ง portal: `NT-Report/pocketbase_0/docs/ASSISTANT.md`

> **สถานะวันนี้ (2026-09-20): ยังไม่เปิดปุ่ม** — ตัวเลขยังไม่ผ่านเกณฑ์ 9/10 ต่อ report_type
> (`plan/archive/RESULT_F11.md`). key ออกแล้ว แต่ `pocketbase_0/.env` ยังไม่ได้ตั้ง

---

## 1. Start / stop

```bash
# AI (จาก project root; .env ของ repo)
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# PocketBase (จาก NT-Report/pocketbase_0)
./pocketbase serve --http=127.0.0.1:8090
```

- interpreter ของ server = `venv/bin/python` (**3.10**); pytest อยู่ใน `venv/bin/python3.14` เท่านั้น
- Redis (`redis://localhost:6379/0`) ต้องรัน ไม่งั้น limit **รายนาที** fail-open (เพดานรายวันยังบังคับ)
- **start ครั้งแรกของวัน = job `result_retention` รันใน 30 วินาที** แล้วทุก 24 ชม.
- ⚠️ **แก้ `pb_hooks/*.js` หรือ `.env` ของ PB ต้อง restart PocketBase** — process เดิมยังใช้ไฟล์เก่า
- ทุกครั้งที่ deploy code ใหม่: restart (query cache 30 นาทีไม่ได้ผูกกับเวอร์ชันของ code)

## 2. ตรวจสุขภาพ

```bash
# ทุก source ต้อง ok + งวดตรงกับ bundle ที่ publish อยู่ (ต้องมี session ของ admin)
curl -s -H "Cookie: <admin session>" localhost:8000/api/v1/admin/sources/datafeed_revenue/status
```

| ตรวจ | ปกติคือ |
|---|---|
| `GET /admin/sources/{name}/status` ทั้ง 4 | `ok: true`, `schema_version` ตรง `DataFeed/dist/<d>/latest/manifest.json`, `data_as_of.build_id` ตรง symlink |
| `GET /admin/query-audit?api_key_id=<id>&channel=portal` | ทุกคำถามมีแถว; `error` ว่าง |
| log ของ server | `[ResultRetention] purged {...}` วันละครั้ง |
| `GET /api/nt/assistant/status` (PB, ต้อง login) | `{"enabled": true}` เมื่อมี `ASSISTANT_API_URL` + `ASSISTANT_API_KEY` |

> **เสียงรบกวนที่รู้แล้ว:** job `export_cleanup` ล้มทุกรอบด้วย `no such table: report_exports`
> (ตาราง F6 ไม่มีใน `app.db` นี้) — ไม่กระทบคำตอบ

## 3. publish ล้ม / `reconcile.ok = false`

- ระหว่าง publish ผู้เรียกได้ **200 + `error: "source_unavailable"`** (ข้อความ "ข้อมูลอาจกำลังถูก publish")
  — ไม่ใช่คำตอบจากไฟล์ครึ่งไฟล์ ปล่อยให้ผู้ใช้ถามใหม่
- build ที่ `reconcile.ok = false` **ถูกปฏิเสธ** — context นั้นตอบไม่ได้จนกว่า NT-Report จะ publish build ที่ผ่าน
- ตรวจ: `cat NT-Report/DataFeed/dist/<domain>/latest/manifest.json` → `reconcile.ok`, `build_id`, `period`

## 4. contract เปลี่ยน

| เปลี่ยนอะไร | ต้องทำอะไรฝั่ง AI |
|---|---|
| คำอธิบาย / business rule / `description` (PATCH) | **ไม่ต้องทำอะไร** — knowledge re-sync เองเมื่อเห็น `schema_version` ใหม่ ในคำถามถัดไป |
| เพิ่ม/ลบ **ตารางหรือคอลัมน์** (MINOR) | ต้องลงทะเบียนใหม่: `python -m scripts.datafeed.register_file_source --domain <d> --source /Users/seal/Documents/GitHub/NT-Report/DataFeed/dist` |

⚠️ `register_file_source` ตั้ง `is_active=1` ให้ context ทุกครั้ง — context ที่ admin ปิดไว้จะถูกเปิดคืน

## 5. key: ออก / หมุน / เพิกถอน

ออก key ใหม่: snippet ใน [PORTAL_INTEGRATION.md](../PORTAL_INTEGRATION.md#ออก-api-key-ให้-portal)
(ผูก workspace `nt-report` เสมอ — **ห้ามออก key ที่ไม่ผูก workspace ให้ portal**)

```python
# เพิกถอน (มีผลกับคำขอถัดไปทันที)
from app.db.session import SessionLocal
from app.models.api_key import APIKey
db = SessionLocal(); k = db.query(APIKey).filter(APIKey.name == "nt-report-portal").first()
k.is_active = False; db.commit()
```

หมุน key: ออกตัวใหม่ → ใส่ `.env` ของ PB → restart PB → เพิกถอนตัวเก่า (อย่าเพิกถอนก่อน)
**raw key แสดงครั้งเดียว** — อยู่ใน `pocketbase_0/.env` เท่านั้น ห้ามอยู่ใน commit / log / เอกสาร

## 6. อ่าน audit เมื่อมีข้อร้องเรียน

```
GET /api/v1/admin/query-audit?api_key_id=<id>&channel=portal            # + format=csv
```
แต่ละแถวมี: เวลา, key, channel, workspace, context, **scope เต็ม**, คำถาม, **SQL ที่รันจริง**, จำนวนแถว,
provider, `llm_policy`, `cache_hit`, `error` — **ไม่มีค่าผลลัพธ์**
ฝั่ง PB: `audit_logs.action = "assistant_ask"` (user, report, ip, `meta.status`)

เทียบสองฝั่งด้วยเวลา + คำถาม; `meta.status` ของ PB บอกว่าผู้ใช้เห็นอะไร (`ok` / `answer_publishing` /
`answer_duplicate` / `answer_failed` / `upstream_forbidden` / `upstream_rate_limited` / `scope_invalid`)

## 7. ถอยกลับ

| ต้องการ | ทำ |
|---|---|
| ปิดปุ่มทั้งหมด (เร็วสุด) | ลบ `ASSISTANT_API_KEY` จาก `pocketbase_0/.env` → restart PB → ปุ่มหาย (ไม่ต้องแตะฝั่ง AI) |
| ปิดเฉพาะ report_type | เอา type นั้นออกจาก `ASSISTANT_CONTEXT_MAP` → restart PB |
| สงสัยว่า key รั่ว | เพิกถอน key (§5) — คำขอถัดไป 401 |
| ย้อน config ของ AI | `~/nt-ai-backups/` + สำเนาที่ทำก่อนทุกขั้น (backup API + `quick_check` + SHA-256) |

## 8. สัปดาห์แรก — ดูอะไร

1. `GET /admin/query-audit?api_key_id=<id>&format=csv` ทุกวัน → คำถามที่ `error` ไม่ว่าง และคำถามที่ได้ 0 แถว
2. คำถามที่ตอบผิด → ดู SQL ในแถว audit แล้วแยกสาเหตุ: **contract** (ความหมาย/กฎ) · **scope**
   (งวด/หน่วยงาน) · **โมเดล** (เลือกคอลัมน์/ตารางผิด) → contract = ข้อเสนอกลับ NT-Report,
   โมเดล = golden example (`POST /admin/examples`) แล้ว `POST /admin/sync-brain`
3. โควตา: ถ้าชน 2,000/วัน บ่อย = ปรับ `rate_limit_per_day` ไม่ใช่ปิด audit
4. หลังเพิ่ม golden / แก้ contract: รัน `python scripts/eval/run_eval.py` และวัดซ้ำ 10 คำถามต่อ report_type
   (`plan/archive/RESULT_F11.md` มีชุดคำถามและ oracle)
