งานเปิดใช้จริง: NT-Report portal ถามตอบผ่าน AI (ผู้ใช้รายแรกของ Plan 7) — repo /Users/seal/Documents/GitHub/AI, branch main
ไม่ใช่ phase ใหม่ของแผน — คือการเอาของที่ Phase 1–6 สร้างไว้ (ทั้งหมดวัดบน**สำเนา** DB) ไปเปิดบนของจริง แล้วพิสูจน์ปลายทางถึงปลายทางผ่าน portal
ตรวจ `git status -sb` ก่อนเริ่ม (ตอนเขียน prompt: origin/main = 52c3ee8, local นำอยู่ด้วยงาน Phase 6 + prompt นี้); commit ใหม่ห้าม push จนกว่าจะสั่ง; ห้าม rebase / force-push; ถ้า main มี commit ใหม่จาก session อื่น ให้ทำต่อบนนั้น
repo NT-Report (/Users/seal/Documents/GitHub/NT-Report) = **อ่านอย่างเดียว** — งานฝั่งนั้นอยู่ใน plan/PROMPT_NT_REPORT_GOLIVE.md (session คู่ขนานใน repo NT-Report); ถ้า NT-Report มี commit ใหม่ของงานนั้น ให้อ่านไฟล์ผลของเขาก่อนทำข้อ 1d / 6 / 7

## อ่านก่อน (บังคับ)
- plan/PLAN_7_DATA_SOURCE_SERVICE.md — หัวสถานะ, §6.2–6.4 (ห้าชั้นของสิทธิ; กรณี NT-Report: "ถามได้เท่ากับข้อมูลของรายงานที่เปิดได้", ไม่มี config = ไม่แสดงปุ่ม), §8 (หน้าที่ที่เหลือของ NT-Report), §11.2–11.3 (**งานค้างจาก F11 ก่อนเปิดใช้จริง: key จริง, E2E ผ่าน PB, เทียบ 10 คำถาม vs dashboard → RESULT_F11.md**)
- plan/archive/RESULT_P7_PHASE6.md §9 (ข้อค้างก่อนเปิดกับ DB จริง + **ข้อบกพร่องของ REST ที่ portal ได้รับอยู่วันนี้**), RESULT_P7_PHASE5.md §8–9, RESULT_P7_PHASE45.md §5–6 (migration ยังไม่ได้รันบน DB จริง; job retention รอบแรกล้างผลลัพธ์เก่า ~1,285 แถว), RESULT_P7_PHASE4.md, RESULT_P7_PHASE3.md (scope), plan/archive/PLAN_F11_DASHBOARD_EMBED.md
- plan/PROMPT_NT_REPORT_P7.md (ทั้งไฟล์ — สิ่งที่ขอ NT-Report ไปแล้ว, สถานะ, ข้อเสนอจาก Phase 5 ท้ายไฟล์), plan/FIX_NOTES.md หัวข้อ F11 + Plan 7 Phase 3 / 4 / 4.5 / 5 / 6
- docs/PORTAL_INTEGRATION.md, docs/DEPLOYMENT_SECURITY.md, docs/DATAFEED_INTEGRATION.md, docs/manuals/manual_api_keys.md
- ฝั่ง portal (อ่านอย่างเดียว): NT-Report/pocketbase_0/pb_hooks/assistant.pb.js (ทั้งไฟล์), pocketbase_0/docs/ASSISTANT.md, pocketbase_0/.env.example, pb_hooks/report_types.pb.js, docs/PERMISSIONS.md
- code ฝั่ง AI: app/api/v1/query.py (+ ตัวที่ Phase 6 แยกออกมา: `run_simple_query`, `contexts_for`), app/api/deps.py, app/services/api_key_service.py, app/services/workspaces.py, app/services/data_sources.py, app/services/retention.py + app/services/scheduler.py (job `result_retention`), app/services/query_audit.py, scripts/migrate_data_sources.py, scripts/migrate_workspaces.py, app/api/v1/admin/sources.py (`GET /admin/sources/{name}/status`)

## สถานะตอนนี้ (2026-09-20)
- Phase 1–6 ✅ บน code | pytest: **1035 passed, 3 skipped** — รันโดยชี้ `CONFIG_DB_URL` / `DATABASE_URL` / `DATA_SOURCE_CACHE_DIR` ไปสำเนา (full pytest บน DB จริงขยับ `admin_config.last_brain_relevant_change_at` — FIX_NOTES Phase 5); `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` (python3.10 ใน venv ไม่มี pytest; server จริงรันด้วย interpreter ไหน — **ตรวจในข้อ 1**)
- ⚠️ **อัปเดต 2026-09-20 เย็น:** `config.db` จริง **migrate แล้ว** (RESULT_P7_PHASE6 §11; backup `~/nt-ai-backups/pre-migrate-20260920/`) — ข้อ 1a / 4 เหลือแค่ตรวจยืนยัน; ข้อบกพร่องของ REST + `/query/contexts` เจ้าของตัดสินแล้ว และทำใน `plan/PROMPT_P7_HARDENING.md` **ก่อน** งานนี้ (ข้อ 3 ของ prompt นี้ = ตรวจว่างานนั้นจบ); retention รอบแรก = ปล่อยล้างตาม 30 วัน (มี backup)
- **ของจริงยังไม่ได้เปิดอะไรเลย:** `config.db` / `app.db` จริงยังไม่ได้รัน migration ของ Phase 4.5 (ไม่มี `data_sources.llm_data_policy` ฯลฯ); ยังไม่มี API key จริงของ portal; multi-context ปิดทุก workspace; MCP ภายนอก (`mcp_external_enabled`) ปิด; Redis ไม่ได้รัน → limit รายนาที fail-open (เพดานรายวันใน DB เท่านั้นที่บังคับจริง)
- config.db จริง: workspace `nt-report` = feed_revenue 2.3.0, feed_expense 1.2.0, feed_sales 1.3.0, feed_ebt 1.4.0 (file source → NT-Report/DataFeed/dist/<d>/latest); งวด: revenue / expense / sales 202608, ebt 202607 (ตรวจใหม่ด้วย source status — NT-Report publish เอง)
- eval ล่าสุด (สำเนา): revenue 14/14, expense 12/12, sales 12/12, ebt 35/36; ข้ามโดเมน 8–9/10
- ฝั่ง portal (อ่านจาก code 2026-09-20): hook ส่ง `context` **เสมอ** (จาก `ASSISTANT_CONTEXT_MAP`: report_type → context เดียว) + `scope` = `{year_month: งวดของรายงาน, org_code?}` + `source`; ปุ่มแสดงเมื่อมี `ASSISTANT_API_URL` + `ASSISTANT_API_KEY`; **hook ปฏิเสธ response ที่ไม่มี `data_as_of` ที่ถูกต้อง** และเตือนเมื่อ `data_as_of.period` ≠ งวดของรายงาน; 400 จาก AI = ไม่ตอบ (ไม่ลองใหม่แบบไม่มี scope)
  → ผลตามมา: **multi-context ไม่มีทางทำงานจาก portal ตอนนี้** (ระบุ context = เส้นทาง context เดียวเสมอ และคำตอบหลาย context มี `data_as_of` ระดับบน = null ซึ่ง hook จะปฏิเสธ) — go-live รอบแรก = context เดียวต่อรายงาน

## คำสั่งที่ใช้บ่อย
- สำเนาสำหรับทดลอง: backup ด้วย SQLite backup API จาก connection `mode=ro` + `PRAGMA quick_check` + SHA-256 ก่อน/หลัง (แบบที่ Phase 6 ทำ — RESULT_P7_PHASE6 §0); สำเนาต้องรัน migrate สองตัวก่อนใช้
- สถานะ source: `GET /api/v1/admin/sources/{name}/status`; ลงทะเบียนใหม่เมื่อ contract เพิ่มตาราง/คอลัมน์: `python -m scripts.datafeed.register_file_source --domain <d> --source /Users/seal/Documents/GitHub/NT-Report/DataFeed/dist`
- ออก key: snippet ใน docs/PORTAL_INTEGRATION.md หรือ `POST /api/v1/admin/api-keys {"name":"nt-report-portal","workspace":"nt-report",…}`
- audit: `GET /api/v1/admin/query-audit?api_key_id=…&channel=portal` (+ `format=csv`)

## งานตามลำดับ (commit เป็นก้อนต่อข้อ; **ทุกการเขียน DB จริง / ออก key / แตะ env ของ portal ต้องได้คำสั่งจากเจ้าของต่อครั้ง**)
0. baseline pytest บนสำเนา; backup `config.db` + `app.db` จริง (backup API + quick_check + SHA-256) ลง scratchpad และบอก path ให้เจ้าของ
1. **สำรวจก่อนลงมือ (อ่านอย่างเดียว, ห้ามข้าม) → ตาราง "ของจริงตอนนี้ vs ที่ต้องเป็น" ใน plan/archive/RESULT_P7_GOLIVE.md:**
   a. DB จริงขาดอะไรเทียบกับ migration (คอลัมน์/ตาราง/ค่า default), รัน migrate บน**สำเนาสด**ของ DB จริงแล้ว diff ของ dump ก่อน/หลัง — ต้องไม่มีอะไรเปลี่ยนนอกจากที่ migration ประกาศ
   b. job `result_retention` รอบแรกจะล้างอะไรบ้าง (นับแถวจริงวันนี้ตามตาราง), รันเมื่อไรหลัง start, ตั้งค่าอะไรไว้ก่อนได้บ้าง (`result_retention_days`, override ต่อ workspace)
   c. server จริงรันอย่างไร (คำสั่ง / interpreter / port / ใครเป็นคน start / .env ที่ใช้: `DATA_SOURCE_ALLOWED_ROOTS`, `DATA_SOURCE_CACHE_DIR`, `MCP_ALLOWED_HOSTS`, provider keys, `REDIS_URL`), portal (PocketBase) รันที่ไหน เรียก AI ด้วย URL อะไร
   d. **สัญญาระหว่าง hook กับ AI ตรงกันทุก field ไหม:** request ที่ hook ส่ง vs `SimpleQueryRequest`; field ที่ hook อ่าน/บังคับ vs `SimpleQueryResponse` (รวม field ใหม่ `parts` / `computed` = null); status code ที่ hook แยกแยะ (400 / 403 / 401 / 429 / 5xx) vs ที่ AI คืนจริง — Phase 6 พบว่า **เกินโควตา = 401 ไม่ใช่ 429**
   e. report_type ทั้งหมดของ portal (ebt / expense / revenue / sales / presentation) → context ไหน; type ที่ไม่มี context (presentation) = ไม่แสดงปุ่ม; รายงานที่จำกัดหน่วยงานส่ง `org_code` แบบไหน และตารางหลักของแต่ละ context มี `cost_center` ไหม (ไม่มี = ใช้ไม่ได้ภายใต้ scope นั้น — Phase 3)
   f. ข้อบกพร่องของ REST ที่ portal จะได้รับ (RESULT_P7_PHASE6 §9 "ของเดิมที่พบ"): SQL ในข้อความคำตอบเมื่อได้ 0 แถวแม้ `include_sql=false`, ข้อความ exception ใน `answer` / `error`, `str(dict)` เมื่อ explanation เป็น dict, `GET /query/contexts` เป็น public (key ผิด = เห็นทุก context), CORS เปิดทั้งแอปขณะที่เอกสารเขียนว่าไม่เปิด — ยืนยันแต่ละข้อด้วยการยิงจริงบนสำเนา และดูว่า hook ส่งต่ออะไรถึงผู้ใช้ portal
2. เสนอ **checklist เปิดใช้ + แผนถอยกลับ (rollback) ต่อขั้น** + exit criteria แล้ว **หยุดถามเจ้าของ** (ข้างล่าง); ส่วนที่ไม่ขึ้นกับคำตอบทำต่อได้
3. แก้ข้อบกพร่องของ REST ตามที่เจ้าของเลือกในข้อ 2 (test ที่ fail บน code เดิม; ช่องทาง MCP ที่ Phase 6 ทำไว้ต้องไม่ถอยหลัง) — eval รายโดเมนต้องไม่ลด
4. **migrate DB จริง** (หลังเจ้าของสั่ง): backup สด → ตั้งค่า retention ตามที่ตัดสิน**ก่อน** start → รัน migrate สองตัว → รันซ้ำ = ไม่มีอะไรเปลี่ยน → diff ของ dump ตรงกับที่วัดในข้อ 1a → start server → ทุก source `status` ok → คำถามควันหลง (smoke) 1 ข้อต่อ context ผ่าน `/api/v1/query` ด้วย session ของ admin
5. **ออก key จริงของ portal** (หลังเจ้าของสั่ง): ผูก workspace `nt-report` (+ allowlist / rate limit ตามที่ตัดสิน); raw key แสดงครั้งเดียว — **ส่งให้เจ้าของทาง terminal เท่านั้น ห้ามลงไฟล์ / log / commit / RESULT / prompt**; ใส่ `.env` ของ pocketbase_0 เฉพาะเมื่อเจ้าของสั่งให้ทำแทน
6. **E2E ผ่าน PocketBase จริง** (ปิด PLAN_7 §11.3):
   - ผู้ใช้ไม่มีสิทธิ์เปิดรายงาน → 403 จาก PB และ**ไม่มี call ออกไป AI** (ตรวจจาก `query_audit` ว่าไม่มีแถว)
   - ผู้ใช้มีสิทธิ์: คำตอบ + `data_as_of` แสดง; "เดือนล่าสุด" ภายใต้รายงานงวด 202607 = 202607 (ไม่ใช่ 202608); รายงานที่จำกัดหน่วยงาน A ถามถึง B = 0 แถว / ปฏิเสธ
   - `ASSISTANT_CONTEXT_MAP` ชี้ context นอก workspace → 403 ที่อ่านออก; งวดรายงาน ≠ `data_as_of.period` (เช่น รายงาน 202608 ถาม ebt ที่ 202607) → คำเตือนแสดง
   - audit ครบสองฝั่ง: PB `audit_logs.action = assistant_ask`; AI `query_audit` มี `api_key_id`, `channel`, `scope`, SQL, จำนวนแถว — ไม่มีค่าผลลัพธ์
   - rate limit ทำงานจริง (รายวัน; รายนาทีถ้ามี Redis); ระหว่าง NT-Report publish → ผู้ใช้เห็น "ข้อมูลกำลังถูก publish" ไม่ใช่คำตอบผิด
7. **เทียบตัวเลข 10 คำถามต่อ dashboard จริง** (ปิด F11): คำถามที่ผู้ใช้ portal จะถามจริงต่อ report_type, ถามผ่าน hook (scope จริงของรายงาน) เทียบกับตัวเลขบนหน้า dashboard ของรายงานนั้น → plan/archive/RESULT_F11.md; **Exit: ถูก ≥ 9/10 ต่อ report_type ที่เปิด; ข้อที่ผิดต้องรู้สาเหตุ (contract / scope / โมเดล)** — report_type ที่ไม่ผ่าน = ไม่เปิดปุ่ม (ตัดออกจาก context map)
8. Runbook สั้น (docs/): ลำดับ start/stop, ตรวจสุขภาพ (source status, query-audit `has_error`), publish ล้ม / `reconcile.ok=false`, contract เพิ่มตาราง (ลงทะเบียนใหม่), หมุน/เพิกถอน key, อ่าน audit เมื่อมีข้อร้องเรียน, ถอยกลับ (ปิดปุ่ม = ลบ env ฝั่ง PB; เพิกถอน key); สิ่งที่ต้องดูสัปดาห์แรก (export `query_audit` ของ key นี้ → คำถามที่ผิด/ถูกปฏิเสธ → golden / ข้อเสนอ contract)
9. prompt ฝั่ง NT-Report: **มีแล้วที่ plan/PROMPT_NT_REPORT_GOLIVE.md** (เจ้าของเปิด session คู่ขนานใน repo NT-Report ด้วยไฟล์นั้น — อ่านก่อนเริ่มข้อ 1d; ข้อสังเกต 1–7 ในไฟล์นั้นคือสิ่งที่ hook ทำกับ response ของ AI) — อัปเดตไฟล์นั้นตามผลจริงของงานนี้ (status code ที่เปลี่ยน, context map ที่ตกลง) และบันทึกสรุปต่อท้าย plan/PROMPT_NT_REPORT_P7.md: env + context map ที่ตกลง, ตาราง error ตาม status code จริง, ข้อเสนอ contract ที่ค้าง (Phase 5 ข้อ 1 "ebt ไม่ใช่ทั้งบริษัท" ฯลฯ), และ (ถ้าเจ้าของต้องการ multi-context ใน portal ภายหลัง) สิ่งที่ hook ต้องรองรับ: ไม่ส่ง `context`, อ่าน `parts[].data_as_of` แทนระดับบน
10. อัปเดต RESULT_P7_GOLIVE.md, RESULT_F11.md, PLAN_7 (§8, §11.2–11.4, หัวสถานะ "ผู้ใช้รายแรก"), ROADMAP, FIX_NOTES, docs (PORTAL_INTEGRATION ให้ตรงของจริง, DEPLOYMENT_SECURITY, runbook), docs/changelogs; CLAUDE.md + AGENTS.md (sync กัน, gitignored); แล้วหยุด
    (ถ้า context ใกล้เต็มก่อนถึงข้อนี้ ให้หยุดแล้วเขียน prompt ส่งต่อ session ถัดไป)

## ข้อค้างที่รอเจ้าของตัดสิน (อย่าตัดสินเอง — ถามตอนข้อ 2)
- **"ของจริง" คือเครื่องไหน:** เครื่องนี้ (D1 = เครื่องเดียวกับ NT-Report) หรือ server อื่น — ถ้าเป็นเครื่องอื่น session นี้ทำได้แค่ checklist + ซ้อมบนสำเนา
- **retention รอบแรก:** ยอมให้ล้างผลลัพธ์ในประวัติแชทที่เก่ากว่า 30 วัน (~1,285 แถว; คำถาม / SQL / ข้อความคำตอบยังอยู่) / ตั้ง `result_retention_days=0` ไว้ก่อนแล้วค่อยตัดสิน / export ก่อนล้าง
- **ข้อบกพร่องของ REST ข้อไหนแก้ก่อนเปิด** (เปลี่ยนพฤติกรรมของช่องทางเดิม จึงต้องสั่ง): ข้อเสนอ = แก้ SQL ในคำตอบ 0 แถว + ข้อความ exception + `str(dict)` + เกินโควตาเป็น 429 ก่อนเปิด; `GET /query/contexts` public และ CORS = ตัดสินแยก
- **key ของ portal:** context ทั้ง 4 หรือเริ่มเฉพาะที่ผ่านข้อ 7; rate limit (ข้อเสนอเดิม 20/นาที, 2,000/วัน); ผูกกับ user ไหน
- **Redis:** รันจริง (limit รายนาทีบังคับได้) หรือรับ fail-open ไปก่อน
- **`llm_provider_allowlist` ของ source `datafeed_*`:** ตั้ง `["matcha"]` ตาม D4 เลยไหม (ตอนนี้ NULL = provider ใดก็ได้ตามค่ากลาง); `llm_data_policy` คง `full`
- **multi-context ใน portal:** ข้อเสนอ = ไม่อยู่ใน go-live รอบแรก (hook ส่ง context เสมอ + ต้องแก้ hook ให้รับ `parts`); เปิดหลัง NT-Report รับกฎ "ebt ไม่ใช่ทั้งบริษัท"
- **ใครเป็นคนใส่ key ใน `.env` ของ pocketbase_0 และ restart PB** (ค่าเริ่มต้น: เจ้าของทำเอง)
- เกณฑ์เลิกโหมด import (D6) และ entitlement token v2 (D7) — ยังไม่ต้องตัดสินเพื่อ go-live; บันทึกไว้
- ⚖️ D4 / §6.6 ข้อ 8 ยังรอ DPO — ผู้ใช้รายแรกเป็นหน่วยงานภายใน NT (Tier 1) จึงไม่บล็อก แต่ต้องเขียนไว้ใน RESULT ว่าเปิดภายใต้ข้อสมมตินี้

## กติกา
- **ของจริงแตะได้เฉพาะเมื่อเจ้าของสั่งต่อขั้น** (migrate, ตั้ง config, ออก key, เปิด flag, แตะ env ของ portal) — ก่อนทุกขั้นมี backup สดที่ตรวจแล้ว + บอกวิธีถอยกลับ; ขั้นที่ถอยกลับไม่ได้ (retention ล้างแถว) ต้องบอกชัดก่อนทำ
- **secret:** raw key, provider key, เนื้อหา `.env` ห้ามอยู่ใน commit / log / RESULT / ข้อความสรุป / prompt ต่อท้าย; ห้ามพิมพ์ key ลง URL; ตรวจ `git diff --cached` ก่อน commit ทุกครั้งในงานนี้
- พฤติกรรมของช่องทางเดิมเปลี่ยนได้เฉพาะข้อที่เจ้าของเลือกในข้อ 2; test เดิมต้องไม่พัง; ทุกการแก้มี test ที่ fail บน code เดิม
- ห้ามผ่อน: lock ของ DuckDB, gate `check_select`, scope / allowlist / `request_pinned` / `llm_data_policy`, `enforce_key_surface`; key ของ portal = ผูก workspace เสมอ (ห้ามออก key ไม่จำกัดเพื่อ "ให้ผ่านก่อน")
- ปัญหาที่ต้นเหตุอยู่ใน contract / ข้อมูลของ NT-Report → เขียนเป็นข้อเสนอ ไม่คำนวณ/แก้เองฝั่ง AI; report_type ที่ตัวเลขไม่ผ่านเกณฑ์ = ยังไม่เปิด ไม่ใช่เปิดพร้อมคำเตือน
- งานที่แตะ auth / ขอบเขตของ key / สิ่งที่ REST คืนให้ผู้เรียก ให้ขอ review อิสระ (agent แยก, อ่านอย่างเดียว) ก่อนปิดงาน
- fail closed: อ่าน key / allowlist / scope / policy ไม่ได้ = ปฏิเสธ
- ข้อควรรู้ที่เจอมาแล้ว:
  - full pytest บน DB จริงเขียน `admin_config.last_brain_relevant_change_at` — รัน test โดยชี้ env ไปสำเนาเสมอ
  - registry ที่ยังไม่ migrate: REST ถือ policy = `full`, **MCP ปฏิเสธทุก context** (Phase 6) — หลัง migrate ต้องตรวจทั้งสองช่องทาง
  - `register_file_source` ตั้ง `is_active=1` ให้ context ทุกครั้ง (context ที่ admin ปิดไว้จะถูกเปิดคืน); schema เพิ่ม/ลบคอลัมน์ต้องลงทะเบียนใหม่ (knowledge re-sync เอง แต่ view ไม่)
  - ตารางที่ไม่มีคอลัมน์ของ scope key = ใช้ไม่ได้ภายใต้ scope นั้น (revenue `fact_bu_monthly` และ ebt `fact_ebt_total_monthly` ไม่มี `cost_center`) → รายงานที่ส่ง `org_code` ได้คำตอบจากตารางรายละเอียดเท่านั้น — วัดในข้อ 7 แยกจากรายงานทั้งองค์กร
  - `SourceUnavailable` (กำลัง publish) ต้องไปถึงผู้ใช้ทั้งก้อน; anyio TaskGroup ห่อ exception เป็น ExceptionGroup (`_find_refusal`)
  - request dedup 5 วินาทีต่อ user + คำถาม — ผู้ใช้ portal ทุกคนมาใน user เดียวของ key: **สองคนถามคำถามเดียวกันพร้อมกันจะโดน "คำถามซ้ำ"** → ตรวจในข้อ 6 และเสนอทางแก้ถ้าเกิดจริง
  - query cache 30 นาทีผูก scope + allowlist + build + policy; ไม่รวมเวอร์ชัน code (`clear_query_cache()` หลัง deploy code ใหม่ = restart ก็พอ)
  - "กำไรของทั้งบริษัท" → `feed_ebt` ตอบยอดของ 2 สายงานขายเป็นของทั้งบริษัท (รอ contract) — ใส่ในชุด 10 คำถามของ ebt เพื่อให้เห็นสถานะจริง
  - test ที่สร้าง provider จริงต้อง patch `_build_provider_kwargs` (เครื่องนี้มี ANTHROPIC_API_KEY จริง); app ห้าม import จาก scripts/; ruff มี error เดิมหลายไฟล์ที่ไม่ใช่ของเรา; CLAUDE.md / AGENTS.md ถูก gitignore (sync กัน)
- commit เป็นก้อนต่อข้อ; ข้อความ commit ห้ามมีชื่อโมเดลหรือ emoji; ลงท้าย Co-Authored-By: Claude <noreply@anthropic.com>
- ถ้าเจอสิ่งที่ขัดกับแผน ให้หยุดและรายงานพร้อมทางเลือก ไม่ตัดสินใจเองเงียบ ๆ
- จบแต่ละข้อสรุป: ทำอะไร, ตัวเลข exit criteria, สถานะของจริง (อะไรเปิดแล้ว / ยัง), commit list, ข้อค้างที่ต้องให้ผมตัดสิน
