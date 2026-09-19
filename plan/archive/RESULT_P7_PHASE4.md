# RESULT Plan 7 Phase 4 — Workspace + scoped API key + admin (+ REMAIN-9.6, REMAIN-9.9)

**วันที่:** 2026-09-19 | **Branch:** `main` (ยังไม่ push) | **Provider:** admin default (matcha, gpt-4.1)
**Interpreter:** `venv/bin/python3.14` (ทดสอบ Vanna/Chroma ด้วย `venv/bin/python3.10`) | **แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 4

## สรุป

| Exit criterion | ผล | ผ่าน? |
|---|---|---|
| 4a — key ของ workspace A เรียก context ของ B ได้ 403 (ระบุชื่อ + auto-route), key/test เดิมไม่พัง | unit test 44 ข้อ + E2E บน DB จริง: `revenue` → **403**, `'Feed_Revenue '` → ตอบจาก `feed_revenue`, auto-route "รายได้…แยกตามสายงาน" → `feed_revenue` (ไม่ใช่ legacy `revenue`), นอก `/api/v1/query` → **403**; test เดิมของ API key (ตาราง pre-Phase-4) ผ่านโดยไม่แก้ | ✅ |
| 4b — retrieval ของ workspace A ไม่คืน golden/doc ของ B | sync จริงด้วย python3.10 บนสำเนา: brain `default` sql=40 doc=273 ddl=4 **ไม่มีรายการ feed เลย**; `nt-report` sql=62 (feed ทั้งหมด) doc=66 ddl=1; ถามเรื่องของอีก workspace → ได้รายการของอีกฝั่ง **0** | ✅ |
| 4c — ลงทะเบียนผ่าน API = script; gate ล้ม registry ไม่เปลี่ยน | test เทียบ registry ทุกแถวเท่ากัน; gate ล้ม / contract เสีย = **400** registry เท่าเดิม; path ใหม่นอก `DATA_SOURCE_ALLOWED_ROOTS` = 400 โดยไม่อ่านไฟล์; symlink ออกนอก root ไม่ผ่าน | ✅ |
| 4d — `feed_*` ในหน้า admin เห็นไฟล์ ไม่ใช่สำเนาเก่า | schema browser / dimension families อ่านผ่าน source; onboarding ปฏิเสธตารางที่มาจาก contract; DDL ของ brain มาจาก registry | ✅ |
| review อิสระ (งานแตะ auth/gate/scope) | รอบ 1 พบ **critical 1 ข้อ** (แก้แล้ว `f07439d`), รอบ 2 ตรวจ 6 หัวข้อ **ไม่พบช่องโหว่** | ✅ |
| pytest | 813 (หลังลบ dead code) → **885 passed**, 3 skipped — test ใหม่ทุกกลุ่ม fail บน code เดิม | ✅ |

## สิ่งที่ทำ

### REMAIN-9.9 dead code (`a430180`)
ลบ `matcha_examples.py` + script ของมัน, `business_db.py` + test 6 ข้อ, adapter SQLite/PostgreSQL/MSSQL + factory (−1,308 บรรทัด ไม่มี caller) — SQL source ในอนาคตสร้าง adapter ตามสัญญาเดียวกับ `DuckDBFileAdapter`

### 4a Workspace + scoped API key (`f11f0d8`, `f07439d`, `b85dac4`)
- config: `workspaces`, `schema_contexts.workspace_id` (ของเดิม → `default`; NULL = `default` ทุกจุดที่ตัดสินสิทธิ์) · app: `api_keys.workspace_id`, `allowed_contexts` (JSON) — ทั้งคู่ NULL = ไม่จำกัด (key เดิม + ผู้ใช้ session เหมือนเดิม)
- สิทธิ์ของ key = contexts ของ workspace ∩ allowlist (แคบลงได้อย่างเดียว); อ่านไม่ได้/JSON เสีย/config ล่ม = **เซตว่าง** (fail closed)
- `QueryEngine`: ชื่อ context ที่ผู้เรียกส่งมาถูกแปลงเป็น**ชื่อจริงใน DB** ก่อน cache/dedup/ทุกอย่าง หรือ 403; auto-route + fallback + cache key อยู่ใน allowlist
- key ที่ถูกจำกัดใช้ได้เฉพาะ `/api/v1/query*` (chat/admin รับ context ได้แต่ไม่รู้จัก allowlist) — 403 ไม่ถูกกลืนโดย fall-through ไป session auth
- `request_pinned` (ContextVar แบบเดียวกับ scope): context ที่ resolve ไม่ได้ = ปฏิเสธ (ไม่ตกไป legacy DB); context แบบ legacy อ่านผ่านกลไก Phase 3 (TEMP view shadow ทุกตาราง + gate) → อ่านได้เฉพาะ main view ของ context — **เดิมมีแค่ prompt ที่กัน**
- app เติมคอลัมน์ `api_keys` เองตอนใช้ครั้งแรก (model select คอลัมน์ใหม่ — deploy ที่ลืม migrate จะล็อก API caller ทุกคน)
- admin: `/admin/workspaces` (list/create/move contexts/soft delete), ออก key พร้อม `workspace` + `allowed_contexts` (binding ที่เป็นไปไม่ได้ = 400 ตอนออก key)

**ช่องโหว่ที่ review รอบ 1 พบ (critical, แก้แล้ว):** allowlist ตรวจด้วยชื่อที่ normalize (`'feed_expense '` / `'Feed_Expense'` ผ่าน) แต่ส่งชื่อดิบต่อ → resolve แบบ exact ไม่เจอ → ตกไป legacy DB ทั้งก้อนพร้อม system prompt เปล่า (ทำซ้ำได้จริง) → แก้ด้วยชื่อจริง + `request_pinned` ข้างบน

### 4b Vanna แยกต่อ workspace (`05759af`)
Chroma directory ต่อ workspace (`<VANNA_CHROMA_PATH>__<workspace>`; `default` ใช้ path เดิม), คำถามดึงจาก brain ของ workspace ที่ context นั้นอยู่; `BrainFilter`: workspace ที่ตั้งชื่อ = ของตัวเองเท่านั้น, `default` = ทุกอย่างที่ไม่มี workspace อื่นเป็นเจ้าของ (ยังไม่มี workspace อื่น = เหมือนเดิมทุกอย่าง); Sync Brain สร้างทีละ workspace — หมายเหตุ: `rag_enabled=false` ใน config จริง และ vanna import ไม่ได้บน python3.14

### 4c Admin API ของ source (`f1b4db5`)
gate + การลงทะเบียนย้ายเข้า `app/services/source_registration.py` (CLI สองตัวเป็น wrapper แปลง `GateError` → `SystemExit`; test เดิมไม่แตะ); `GET /admin/sources`, `GET /admin/sources/{name}/status` (resolve แบบเดียวกับคำถามจริง → ok / `data_as_of` / schema_version), `POST /admin/sources/register` (ไม่ส่ง path = ลงทะเบียนซ้ำจากที่เดิม; path ใหม่ต้องอยู่ใต้ `DATA_SOURCE_ALLOWED_ROOTS` ใน .env — ว่างเป็นค่าเริ่มต้น)

### 4d REMAIN-9.6 (`5428bb3`)
`data_sources.registered_tables()` เป็นจุดถามแรกของทุกที่ที่ inspect ตารางด้วยชื่อ (business DB ยังมีสำเนา F10 ชื่อเดียวกัน)

### ตาม contract ใหม่ของ NT-Report ระหว่างงาน (`97f5081`)
revenue 2.2.0→**2.3.0** (ตารางเป้า 2 ตาราง, `cost_center` ใน fact_org_product*/subproduct*, `is_divested`), sales **1.3.0** (ตารางเป้าเต็มปี), ebt **1.4.0** (`fact_ebt_division_monthly` + control totals ราย division):
- instruction ของ feed context แสดง**ทุกตาราง**ของ contract (ชื่อเต็ม + grain + คอลัมน์) — เดิม prompt รู้จักแค่ main view; แทนบรรทัดเฉพาะ ebt เดิม
- golden: source แบบมีกลุ่มที่มีหลาย measure ถามทุก measure (ยอดรวมทุกงวด + รายกลุ่มงวดล่าสุด) → ebt 36 ข้อ
- ถามจริง: เป้ารายได้ 3.Mobile ก.ค. 69 → `fact_bu_target_monthly`; เป้ายอดขายเต็มปี 2569 = **40,100.09 MB** (ตรงที่ NT-Report แจ้ง) → `fact_sales_target_monthly`; ยอดขายจริงไม่เพี้ยน

## Eval (contract + prompt ใหม่)

| Context | schema | บนสำเนา | บน config จริง |
|---|---|---|---|
| feed_revenue | 2.3.0 | 14/14 (`eval_20260919_1004`, ลงทะเบียน 2.2.0) | 13/14 = 92.9% (`1011`, ลงทะเบียน 2.3.0) |
| feed_expense | 1.2.0 | 12/12 (`1006`) | — |
| feed_sales | 1.3.0 | 12/12 (`1003`) | 12/12 (`1017`) |
| feed_ebt | 1.4.0 | 33/36 = 91.7% (`1002`) | **32/36 = 88.9%** (`1015`) |

ไม่มี retry / guard ยิง 0 ครั้งทุกชุด.

⚠️ **ebt บน config จริงได้ 88.9% (ต่ำกว่าเกณฑ์ 90% หนึ่งข้อ; บนสำเนา 91.7%)** — ข้อที่พลาดทั้งสองรอบเป็นแบบเดียวกัน: แปลง พ.ศ. 2568 → 2026 หนึ่งข้อ, ที่เหลือ (2–3 ข้อ) โมเดลเขียน `SELECT division, ebt …` = **ค่าถูก** แต่มีคอลัมน์ชื่อสายงานเพิ่ม → harness นับ mismatch เพราะจำนวนคอลัมน์ไม่เท่า golden (revenue ข้อที่ตกก็แบบเดียวกัน: `SELECT bu, SUM(revenue_ytd)`). ถ้า harness ยอมให้มีคอลัมน์ label เพิ่ม ebt = 35/36, revenue = 14/14 — **ไม่ได้แก้เกณฑ์ของ harness เอง** (รอเจ้าของตัดสิน); `feed_ebt` ยังเปิดอยู่เพราะความหมายของคำตอบถูก

## สถานะ DB จริงหลังจบงาน (ไม่อยู่ใน git — backup ใน scratchpad ของ session)
- `config.db`: `workspaces` = `default` (revenue, expense, transfer price, pl_costtype), **`nt-report`** (feed_revenue, feed_expense, feed_sales, feed_ebt); 4 โดเมนลงทะเบียนใหม่ (revenue 2.3.0 17 views, sales 1.3.0 4 views, ebt 1.4.0 3 views, expense 1.2.0 8 views); golden ebt 36 ข้อ
- `app.db`: `api_keys` มีคอลัมน์ใหม่; key ทดสอบ E2E 3 ตัวถูก revoke แล้ว (`phase4-e2e-test*`)

## ค้าง / ข้อสังเกต
- **ออก key จริงให้ portal** (เจ้าของทำ — raw key แสดงครั้งเดียว): `docs/PORTAL_INTEGRATION.md`
- Admin **UI** (frontend-admin) ของ workspaces / sources ยังไม่ได้ทำ — มีแต่ API
- ผู้เรียกที่ไม่ถูกจำกัด: context ที่ไม่มีอยู่จริงยังตกไป legacy DB พร้อม prompt เปล่า (พฤติกรรมเดิม — reviewer แนะนำให้เป็น 400/404 สำหรับทุกคน; ยังไม่เปลี่ยนเพราะเป็นพฤติกรรม legacy)
- คำถามหลอก ("ขอข้อมูลจาก revenue_search" ผ่าน `feed_sales`) ไม่หลุดตาราง แต่โมเดลตอบ `SUM(amount)` โดยไม่กรอง `metric='actual'` — เป็นเรื่องความแม่นของคำตอบ ไม่ใช่สิทธิ์
- ตารางเป้า (revenue/sales) ยังไม่มี control totals → ยังไม่มี golden ของเป้า
- `resolve_key_binding` ใช้ชื่อ normalize ตอนตรวจ: context สองตัวต่าง workspace ที่ชื่อ normalize ชนกันอาจตรวจผิดตอน**ออก key** (ไม่กระทบการบังคับใช้ตอน query)

## Commits
```
a430180 chore(REMAIN-9.9): remove dead code that pointed at the wrong DB
f11f0d8 feat(P7-4a): workspaces and API keys scoped to them
05759af feat(P7-4b): one Vanna brain per workspace
f1b4db5 feat(P7-4c): sources through the admin API - list, status, register
f07439d fix(P7-4a): an allowlisted name must be the stored name; restricted keys are pinned to the context's tables
5428bb3 feat(P7-4d): admin pages read a file-source table from its files (REMAIN-9.6)
97f5081 feat(P7): feed instruction lists every table of the contract; golden per measure for grouped sources
b85dac4 fix(P7-4a): a refusal raised inside the endpoint's own MCP session is still 400/403
```
