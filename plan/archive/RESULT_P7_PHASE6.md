# RESULT Plan 7 Phase 6 — MCP สำหรับผู้เรียกภายนอก

**สถานะ:** สำรวจก่อนออกแบบ — ยังไม่เปิด endpoint; รอเจ้าของระบุผู้ใช้/client รายแรกตามข้อ 2 ของ prompt
**วันที่:** 2026-09-19 | **Branch:** `main` | **เริ่มจาก:** `c11df30` (`origin/main` ในเครื่อง = `52c3ee8`; ahead 2 เป็น commit เอกสาร prompt)
**แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 6; รวม Plan 1B-C / REMAIN-8 เมื่อผ่าน exit จริง

## 0. Baseline และสำรองข้อมูล

- Working tree สะอาดก่อนเริ่ม; ทำต่อบน `main` ตามคำสั่ง ไม่มี rebase / force-push / push
- Backup ด้วย SQLite backup API จาก connection `mode=ro`: `config.db` และ `app.db`; `PRAGMA quick_check` = `ok` ทั้งคู่
- Scratchpad: `/private/tmp/nt-ai-p7-phase6-612hskar/` — `backup/` = snapshot ก่อนงาน, `test/` = สำเนาที่ใช้ทดลอง, `manifest.json` = hash ก่อน/หลัง; **ไม่ commit DB/secret/log ทดสอบ**
- สำเนารัน `scripts/migrate_data_sources.py` + `scripts/migrate_workspaces.py` ก่อน baseline; เพิ่มคอลัมน์ Phase 4.5 เฉพาะสำเนา
- คำสั่ง baseline (export `CONFIG_DB_URL`, `DATABASE_URL`, `DATA_SOURCE_CACHE_DIR` ไป scratchpad ก่อน):

  ```bash
  venv/bin/python3.14 -m pytest -q -p no:cacheprovider
  ```

- **997 passed, 3 skipped in 12.05s**; log: `/private/tmp/nt-ai-p7-phase6-612hskar/baseline-pytest.log`
- SHA-256 ของไฟล์ DB จริงก่อน/หลัง baseline เท่ากันทั้งสองไฟล์ — หลีกเลี่ยง side effect เดิม `last_brain_relevant_change_at` ด้วยการชี้ config DB ไปสำเนา
- ยังไม่ migrate DB จริง / ออก key จริง / เปิด multi-context / รัน eval ด้วย LLM จริง

## 1. สำรวจ

กำลังรวบรวมรายการ tool ภายใน, หลักฐาน SDK/client ที่ติดตั้ง และเส้นทาง auth ก่อนเสนอแผนย่อย
