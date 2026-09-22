# PLAN F6 — Reports / Export (ช่องว่างหลักตาม IMPLEMENTATION_STATUS: 10%)

> **ตรวจ source ซ้ำ 2026-09-21:** แผนนี้มี implementation แล้ว ไม่ต้อง execute ซ้ำ; สถานะรายข้อ หลักฐาน และ acceptance ที่ยังค้างดู [รายงาน F1–F8](../REVIEW_F1_F8_2026-09-21.md) ข้อความและ checklist ด้านล่างคงไว้เป็นแผนในอดีต

**Prerequisite:** PLAN_F1 (ห้ามใช้ query cache/ข้อมูล truncate เป็นแหล่ง export) และ PLAN_F4 (read-only connection)
**ประมาณเวลา:** 2-3 วัน
**ขอบเขต:** Backend เท่านั้น — ส่งมอบ API contract ให้ frontend/admin ทำปุ่มภายหลัง

## READ FIRST

- `app/tools/report_export.py` ← ยังไม่เคย review — อาจมีของใช้ได้อยู่แล้ว อ่านก่อนตัดสินใจสร้างใหม่
- `app/services/database_adapter.py` ← ยังไม่เคย review — น่าจะ reuse เป็น connection layer สำหรับ export ได้
- `app/celery.py`, `app/workers/email_worker.py` (pattern การประกาศ task)
- `app/services/scheduler.py` ← ยังไม่เคย review — สำหรับ cleanup job
- `app/services/audit_service.py` ← ยังไม่เคย review — interface การ log
- `app/models/chat.py` (ChatHistory: `generated_sql`, ownership fields)
- `app/db/base_class.py`, ตัวอย่าง model ใน `app/models/`
- `docker/docker-compose.yml` — ยืนยันว่า Celery worker + Redis รันยังไงใน dev

## หลักการออกแบบ (ตัดสินใจแล้ว)

1. **Export = รัน SQL ใหม่เสมอ** จาก `generated_sql` ที่บันทึกใน ChatHistory ของ user เอง — **ห้าม** export จาก `result.data` ใน session (ถูก truncate 1,000 แถว) และห้ามผ่าน query cache
2. Row cap ของ export: 100,000 แถว (config ผ่าน admin_config key `export_max_rows` ตามหลัก 3-tier) — เกิน cap ให้ตัดพร้อม flag `truncated` ใน metadata sheet
3. รันผ่าน read-only connection (จาก F4) + `ValidationService.validate_sql` ก่อน execute ทุกครั้ง (SQL มาจาก DB ก็จริง แต่ defense in depth)
4. ไฟล์เก็บใน `data/exports/` ชื่อ `{uuid4}.xlsx` — ไม่มีชื่อเดาได้; download ต้อง auth + ownership
5. Retention 7 วัน (config key `export_retention_days`) — cleanup job ลบไฟล์+แถว DB

---

## Phase 1 — Model + Sync export path

### 1.1 Model ใหม่ `app/models/report_export.py` (inherit `Base` — app DB)

```
report_exports:
  id            TEXT PK (uuid4)
  user_id       INT FK users
  chat_history_id INT FK chat_history (nullable — เผื่ออนาคต export จากแหล่งอื่น)
  question      TEXT
  sql_text      TEXT
  status        TEXT  -- pending | running | done | failed
  file_path     TEXT NULL
  row_count     INT NULL
  truncated     BOOLEAN DEFAULT 0
  error         TEXT NULL
  created_at / completed_at / expires_at  DATETIME
```

สร้างตารางตามกลไก migration ที่โปรเจกต์ใช้จริง (เช็คว่า alembic ถูกใช้จริงหรือ init script — ดู `scripts/` ก่อน แล้วทำตามแบบเดิม)

### 1.2 Service `app/services/report_service.py`

- `create_export(db, user, chat_history_id) -> ReportExport` — ตรวจ ownership (chat_history.user_id == user.id หรือ user เป็น admin), มี `generated_sql` ไม่ว่าง, validate_sql ผ่าน → สร้าง record status=pending
- `run_export(export_id)` — ฟังก์ชัน sync ล้วน (เรียกได้ทั้งจาก Celery และ inline):
  1. โหลด record, set running
  2. เปิด read-only connection ผ่าน adapter (reuse จากไฟล์ที่อ่านใน READ FIRST — ถ้าไม่มีของ reuse ได้ ให้ import `QueryDatabaseAdapter` pattern จาก `mcp_servers/nt_query_mcp.py` มาไว้ใน service โดยไม่ duplicate: ย้าย class ไป module กลางแล้วให้ MCP server import — ตัดสินใจตามสภาพโค้ดจริง จดเหตุผล)
  3. execute ด้วย `max_rows = export_max_rows + 1` → truncated flag
  4. เขียน xlsx ด้วย pandas + openpyxl: Sheet "Data" (header = ชื่อ column ตามจริง รวมภาษาไทย), Sheet "Info" (question, SQL, generated_at เวลาไทย, row_count, truncated, ผู้ขอ)
  5. เขียนไฟล์ `data/exports/{id}.xlsx` (สร้าง dir ถ้าไม่มี), set done + expires_at = now + retention
  6. exception → status=failed + error (truncate 500 ตัวอักษร) — ห้ามทิ้งไฟล์ครึ่ง ๆ (เขียนลง temp แล้ว rename)
- audit: เรียก audit_service ตาม interface จริง (event: report_export_created / downloaded)

### 1.3 API `app/api/v1/reports.py` (mount ใน main.py prefix `/api/v1/reports`)

- `POST /` body `{chat_history_id}` → สร้าง + **ถ้า Celery พร้อม (REDIS_URL set): enqueue task แล้วตอบ `{id, status: "pending"}`; ถ้าไม่: รัน inline (ยอมบล็อก request) แล้วตอบ done** — ตรวจ Celery availability ครั้งเดียวตอน startup ไม่ใช่ per-request
- `GET /{id}` → status record (owner หรือ admin)
- `GET /{id}/download` → `FileResponse` (owner หรือ admin, status=done, ยังไม่ expire) + filename สวย: `nt-report-{created_date}.xlsx`
- `GET /` → list ของ user (paginate skip/limit)

Rate limit: ใช้ limiter ที่มีอยู่ (`API_RATE_LIMIT`) — export หนัก อาจเพิ่ม limit เฉพาะ `POST /` = "10/hour" ผ่าน slowapi decorator

## Phase 2 — Celery task + notify

- `app/workers/report_worker.py`: task `generate_report(export_id)` เรียก `run_export` — ตาม pattern ของ email_worker; ระวัง: worker process ไม่มี MCP client (ไม่ต้องใช้ — เราต่อ DB ตรง)
- Telegram notify (optional, ทำถ้า chat_history ผูก user ที่มี telegram): ข้ามได้ในรอบแรก — จดเป็น TODO ใน code
- SSE ไม่ต้อง — frontend poll `GET /{id}` พอ (ระบุใน API contract)

## Phase 3 — Cleanup + contract doc

- Job ใน BackgroundScheduler (ตาม pattern ไฟล์ scheduler จริง): รายวัน ลบ record ที่ `expires_at < now` + ลบไฟล์ (ไฟล์หายแต่ record อยู่ → ลบ record ด้วย, record หายแต่ไฟล์อยู่ → ลบไฟล์ orphan ใน dir)
- เขียน `docs/API_REPORTS.md` สั้น ๆ: endpoint, payload, status flow, ตัวอย่าง curl — สำหรับทีม frontend

## การทดสอบ

- `tests/unit/test_report_service.py`: create_export ownership ผิด → 403/ValueError; SQL อันตราย → reject; run_export กับ sqlite temp จริง 20 แถว → ไฟล์ xlsx เปิดได้ (openpyxl load) แถวครบ + Info sheet ถูก; cap 5 → truncated=true
- `tests/integration/test_reports_api.py`: POST→GET→download ครบ flow (inline mode); download ของคนอื่น → 403; expired → 410 หรือ 404 (เลือกแล้วคงเส้นคงวา)
- Cleanup: record expired + ไฟล์ → หายทั้งคู่

## Acceptance Criteria

- [ ] pytest ผ่านทั้งหมด
- [ ] Manual: ถามคำถามใน chat → เอา chat_history id มา POST export → download ได้ไฟล์เปิดใน Excel ภาษาไทยไม่เพี้ยน
- [ ] Export ของ query ที่เคยโดน truncate 1,000 แถวใน chat → ไฟล์มีแถวเต็มจริง (พิสูจน์ว่าไม่ได้ export จาก session data)
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md` (Reports: จาก 10% → ระบุสถานะจริง) + `PLAN_ROADMAP_MASTER.md` ถ้ากระทบ
