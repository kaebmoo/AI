# PLAN F11 — ฝัง Assistant เข้า NT Report Portal (dashboard Q&A)

**Prerequisite:** PLAN_F10 เสร็จ (context `feed_*` + baseline) และ PLAN_F4.4 (per-minute rate limit) และ PLAN_F1
**ประมาณเวลา:** 2-3 วัน (pilot: รายงาน revenue)
**Decision ที่บันทึกแล้ว (2026-07-04):** โหมด dashboard ตอบจากตาราง `feed_*` ชุดเดียวกับที่ใช้ build dashboard — เลขที่ assistant ตอบต้อง reconcile กับเลขบนจอได้เสมอ
**งานคร่อมสอง repo:** ทุก task ระบุ repo กำกับ — commit แยก repo, ฝั่ง NT-Report ทำตาม convention ของ NT-Report

## สถาปัตยกรรมที่เลือก (พร้อมเหตุผล)

ฝัง **chat panel ที่ `viewer.html` ของ portal** — ไม่ inject widget ลงไฟล์ dashboard แต่ละตัว เพราะ:
1. viewer เป็นหน้าที่ portal เป็นเจ้าของ มี PocketBase SDK + auth token อยู่แล้ว (dashboard HTML เป็น artifact ที่ upload — แก้ทีละ pipeline แพงและ auth ไม่มี)
2. viewer รู้อยู่แล้วว่ากำลังแสดง report ไหน (`report_type`, งวด) จาก record → ได้ context pinning ฟรีระดับรายงาน
3. Rollout/rollback จุดเดียว

Flow: `viewer.html (panel) → POST /api/nt/assistant/ask (PB hook, same-origin) → ตรวจ auth + สิทธิ์รายงาน → $http.send → NT AI Assistant API (context=feed_<domain>) → คำตอบกลับ` — browser ไม่เคยเห็น API key, ไม่ต้องเปิด CORS ฝั่ง assistant

## ข้อเท็จจริงที่ตรวจแล้ว (จาก pocketbase_0/README.md, 2026-07-04)

- PB v0.38, custom routes convention `/api/nt/*` มีอยู่แล้วหลายเส้น (`main.pb.js`, `notifications.pb.js`, `permissions.pb.js`)
- `pb_hooks/utils.js` มี `canAccessReport`, `writeAudit`, `isEmailAllowed`, `forwardedPrefix` — **reuse ห้ามเขียนซ้ำ**
- users มี field `active` ที่ `canAccessReport` เช็คอยู่แล้ว; JWT TTL 8 ชม.; roles: admin / uploader / viewer
- `viewer.html` = inline viewer (iframe + header bar); frontend ใช้ dynamic `<base>` เพราะ prod อยู่ใต้ subpath `/fi-report/` — โค้ดใหม่ทุกจุดต้องใช้ pattern path เดียวกับของเดิม
- Vendor policy: JS ทุกตัว self-host ใต้ `pb_public/assets/vendor/` — ห้ามดึง CDN

## READ FIRST

ฝั่ง NT-Report:
- `pocketbase_0/pb_hooks/utils.js` ทั้งไฟล์ (signature จริงของ canAccessReport/writeAudit)
- `pocketbase_0/pb_hooks/main.pb.js` (pattern การประกาศ route + auth + viewer routes)
- `pocketbase_0/pb_public/viewer.html` + `pb_public/assets/app.js` (โครง UI, วิธีได้ report record ปัจจุบัน, Alpine pattern)
- `pocketbase_0/DEPLOY_NOTES.md` (CSP! — inline script/connect-src อาจถูกคุม, subpath, nginx)
- `.gitignore` ที่ root NT-Report — **blanket ignore `*.js` ทั้ง repo**: ตรวจว่า pb_hooks/pb_public ถูก un-ignore ด้วย pattern ไหน แล้วยืนยันไฟล์ใหม่ทุกไฟล์ด้วย `git check-ignore -v` ก่อน commit (พลาดข้อนี้ = โค้ดหาย)
- PB v0.38 JSVM docs: `$http.send` (มีจริงไหม, signature, timeout สูงสุด) — **ถ้าไม่มีหรือใช้ไม่ได้ ให้หยุดและถามเจ้าของโปรเจกต์** (ทางสำรองเช่น nginx auth_request เป็น decision แยก ห้ามตัดสินใจเอง)

ฝั่ง AI:
- `app/api/v1/query.py` ทั้งไฟล์ (stateless API: auth แบบไหน, request/response shape จริง, รองรับ context param ไหม)
- `app/services/api_key_service.py` (การออก key + limit ต่อ key)

---

## Phase A (AI repo) — เตรียม API สำหรับ portal

1. อ่าน query.py แล้วยืนยัน/เพิ่มให้ครบ: รับ `context` (จะส่ง `feed_revenue`), optional `pinned_filters: dict` (v1 อาจยังไม่ใช้ — รับไว้ก่อนเพื่อไม่ต้องแก้ contract ทีหลัง ถ้าเพิ่ม field ต้อง optional เสมอ), optional `source: str` สำหรับ audit
2. `pinned_filters` ถ้า implement: inject เป็นเงื่อนไขใน prompt/intent (เส้นทางเดียวกับ hierarchy filter ที่มี — อ่านก่อน อย่าสร้างกลไกใหม่) — ถ้าซับซ้อนเกิน 0.5 วัน ให้รับ-เก็บ-log อย่างเดียวใน v1 แล้วจด
3. ออก API key เฉพาะ portal: rate_limit_per_minute ต่ำ (เช่น 20) + daily ตามเหมาะ; บันทึกวิธีออก key ลง docs
4. Response ต่อ portal: ใช้ shape เดิม — ยืนยันว่ามี explanation (str/dict), data rows, generated_sql; **ไม่เปิด CORS** (proxy same-origin อยู่แล้ว)

**Test:** integration ยิง stateless API ด้วย key + context=feed_revenue → ได้คำตอบ; key เกิน per-minute → 429/None ตาม F4.4

## Phase B (NT-Report) — PB hook proxy

ไฟล์ใหม่ `pocketbase_0/pb_hooks/assistant.pb.js` — route `POST /api/nt/assistant/ask`:
1. requireAuth (pattern เดียวกับ route อื่นใน repo)
2. body: `{report_id, question}` — โหลด report record → `canAccessReport(user, report)` → ไม่ผ่าน = 403 (**ก่อน**ถึง assistant เสมอ)
3. map `report.report_type` → assistant context ผ่าน config (`.env`: `ASSISTANT_API_URL`, `ASSISTANT_API_KEY`, `ASSISTANT_CONTEXT_MAP` เช่น `revenue=feed_revenue`) — type ที่ไม่มีใน map = 400 "รายงานนี้ยังไม่รองรับการถามตอบ"
4. `$http.send` POST (timeout 60s) พร้อม question + context + source="portal" + งวดของ report (จาก record) ใน pinned_filters
5. `writeAudit`: action `assistant_ask`, report id, user, IP/UA, คำถาม 200 ตัวอักษรแรก, สถานะ
6. Error mapping เป็นไทย: timeout → "ระบบใช้เวลานานเกินไป ลองใหม่หรือถามสั้นลง", 4xx/5xx → ข้อความกลาง + log รายละเอียดฝั่ง server เท่านั้น (อย่า leak error ดิบไป browser)
7. ค่า secret ทั้งหมดอยู่ `.env` ของ pocketbase_0 → อัปเดต `.env.example` + `DEPLOY_NOTES.md`

**Test:** manual ผ่าน local PB — user ไม่มีสิทธิ์ report → 403 และไม่มี call ออก; user มีสิทธิ์ → ได้คำตอบ; audit record เกิดครบ

## Phase C (NT-Report) — Panel ใน viewer.html

1. ปุ่ม "ถามข้อมูลรายงานนี้" ใน header bar ของ viewer → เปิด side panel (Alpine ที่มีอยู่ ไม่เพิ่ม JS dependency; ไฟล์ใหม่ถ้าจำเป็นวางตาม vendor/asset policy เดิม)
2. Panel: ช่องถาม + ประวัติใน session (ไม่ persist), spinner ระหว่างรอ (คาด 5-30 วิ — v1 ไม่ stream), แสดงคำตอบ: ข้อความ + ตารางถ้ามี data (≤ 20 แถวแรก + บอกจำนวนเต็ม); **ยังไม่ render กราฟใน v1** (จด backlog)
3. **Provenance บังคับทุกคำตอบ:** "ตอบจากชุดข้อมูลเดียวกับรายงานนี้ (งวดข้อมูล <period>)" — นี่คือสัญญา consistency ต่อ user
4. เคารพ CSP + dynamic base ตาม DEPLOY_NOTES (จุดพังคลาสสิกของ repo นี้ตาม README)

**Manual test (บังคับ, local PB + assistant dev):** login viewer ที่มีสิทธิ์ revenue → ถาม 3 คำถาม → ได้คำตอบ; viewer ที่ไม่มีสิทธิ์ → panel แจ้งไม่มีสิทธิ์

## Phase D (deferred — ทำหลัง pilot ผ่านและมี demand จริง)

- postMessage contract: dashboard ส่ง filter state ปัจจุบัน (`{type:'nt-dashboard-state', filters}`) → viewer แนบเป็น pinned_filters — ต้องแก้ template ต่อ dashboard จึงทำเฉพาะตัวนำร่อง เป็น decision แยก
- Streaming/direct-call mode (CORS + short-lived token ที่ PB มินท์) — เฉพาะถ้า latency ผ่าน proxy ไม่พอหลังเปิด F9

## Acceptance Criteria

- [ ] Pilot รายงาน revenue: ถาม 10 คำถามที่คำตอบมองเห็นบน dashboard → ตัวเลขตรงทุกข้อ (ยอมต่างเฉพาะการปัด MB ที่ dashboard ทำเอง) — บันทึกตารางเทียบใน `plan/RESULT_F11.md`
- [ ] ผู้ไม่มีสิทธิ์ report ถูกปฏิเสธก่อน request ออกจาก PB (พิสูจน์จาก log)
- [ ] Audit: ทุกคำถามมี record ใน audit log ของ portal
- [ ] API key ของ portal โดน rate limit จริงเมื่อยิงเกิน (ทดสอบ)
- [ ] ไม่มีไฟล์ใหม่ถูก `.gitignore` กิน (ตรวจ `git status` + `git check-ignore -v` ทั้งสอง repo)
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md` (AI repo) + README/DEPLOY_NOTES (pocketbase_0) ตามที่แตะจริง
