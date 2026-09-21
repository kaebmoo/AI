# RESULT — เปิดใช้จริง: NT-Report portal ถามตอบผ่าน AI (ผู้ใช้รายแรกของ Plan 7)

**สถานะ:** 🟡 ฝั่ง AI **เปิดแล้ว** (migrate ✅ · server รัน ✅ · key จริงออกแล้ว ✅ · allowlist = matcha ✅)
— อัปเดต 2026-09-21: **ปุ่มเปิดเฉพาะ `revenue`** (2026-09-20 ดึก — `ASSISTANT_CONTEXT_MAP=revenue=feed_revenue` ใน `pocketbase_0/.env`, PB restart ด้วย `scripts/serve.sh`) และมีผู้ใช้จริงถามแล้ว; expense / sales / ebt ยังไม่เปิด (`RESULT_F11.md` §7–§8)
§1 วัดจาก**สำเนาสด**ของ DB จริง · §5 คือสิ่งที่ทำบนของจริง · §6 คือสิ่งที่เกิดหลังเปิดปุ่ม
**วันที่:** 2026-09-20 | **Branch:** `main` (ahead 2 ตอนเริ่ม: `345c661`, `3a74bcf`) | **คู่กับ:** session ฝั่ง NT-Report
(`plan/PROMPT_NT_REPORT_GOLIVE.md` → ผลอยู่ที่ `NT-Report/pocketbase_0/docs/ASSISTANT_GOLIVE.md`)

---

## 0. Baseline และสำรองข้อมูล

| ของ | ค่า |
|---|---|
| pytest (สำเนา) | **1078 passed, 3 skipped** — `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` โดยชี้ `CONFIG_DB_URL` / `DATABASE_URL` / `DATA_SOURCE_CACHE_DIR` ไปสำเนา |
| SHA-256 `config.db` จริง | `1c91c756…` — **เท่าเดิมก่อนและหลัง** ทุกขั้นของงานนี้ |
| SHA-256 `app.db` จริง | `af348bbb…` — เท่าเดิม |
| `PRAGMA quick_check` | `ok` ทั้งสองไฟล์ |

**Backup ของวันนี้:** `<scratchpad>/golive/backup/{config.db,app.db}` (backup API จาก connection `mode=ro`;
สำเนาสำหรับทดลองอยู่ที่ `golive/test/` = pytest และ `golive/live/` = server ซ้อม). ของเดิมก่อน migrate ยังอยู่ที่
`~/nt-ai-backups/pre-migrate-20260920/`. **ไม่มี DB / key / log อยู่ใน commit**

---

## 1. ของจริงตอนนี้ vs ที่ต้องเป็น

### a. DB จริงเทียบกับ migration — ✅ ไม่มีอะไรค้าง

`config.db` จริง migrate แล้ว (ตามที่ RESULT_P7_PHASE6 §11 บันทึก) — ยืนยันซ้ำด้วยการรัน migration ทั้งสองตัว
บนสำเนาสดแล้ว diff ของ `.dump` ก่อน/หลัง:

```
config.db: ต่างกัน 2 บรรทัด — sqlite_sequence ของ data_sources 39→40, workspaces 5→6
app.db   : ไม่มีบรรทัดต่าง
```

คือ INSERT ที่ถูก rollback ขยับตัวนับ autoincrement เท่านั้น — **ไม่มีแถว/คอลัมน์/ค่าใดเปลี่ยน**

| สิ่งที่ migration ประกาศ | มีอยู่จริงไหม |
|---|---|
| `data_sources.llm_data_policy` | ✅ = `full` ทั้ง 5 source |
| `data_sources.llm_provider_allowlist` | ✅ (ค่า `NULL` ทั้งหมด = provider ใดก็ได้) |
| `workspaces.result_retention_days` / `store_result_data` | ✅ (ค่า `NULL` ทั้งคู่ = ใช้ค่ากลาง) |
| `schema_contexts.source_id` / `scope_columns` / `workspace_id` | ✅ ครบทั้ง 4 context ของ `nt-report` |
| `query_audit` | ⚠️ **ยังไม่มีตารางใน `app.db` จริง** — ไม่ต้อง migrate: `query_audit.ensure_table()` สร้างเองครั้งแรกที่ใช้ (idempotent) ยืนยันแล้วบนสำเนา (เขียน 19 แถวระหว่างซ้อม) |

**สถานะ config จริง:** workspace `nt-report` (id 2, active) → `feed_revenue` / `feed_expense` / `feed_sales` / `feed_ebt`
ผูก source `datafeed_*` (duckdb_file) ชี้ `NT-Report/DataFeed/dist/<d>/latest`; ทุก context `is_active=1`;
`scope_columns` ครบทั้ง 4 (`year_month` → `year_month`/`time_key`, `org_code` → `cost_center`)

**bundle ที่ publish อยู่ (NT-Report publish ใหม่ 2026-09-20 13:0x UTC — contract PATCH):**

| โดเมน | build_id | period | schema | reconcile |
|---|---|---|---|---|
| revenue | `20260920T130347Z` | 202608 | **2.3.1** | ok |
| expense | `20260920T130407Z` | 202608 | **1.2.1** | ok |
| sales | `20260920T130417Z` | 202608 | **1.3.1** | ok |
| ebt | `20260920T130423Z` | **202607** | **1.4.1** | ok |

schema_version ขยับจากที่ config.db จำไว้ (2.3.0 / 1.2.0 / 1.3.0 / 1.4.0) → knowledge re-sync เองเมื่อมีคำถามแรก
ของแต่ละ context **ยืนยันแล้ว**: หลังถาม `feed_revenue` หนึ่งคำถามบนสำเนา `schema_contexts.description` เปลี่ยนจาก
`NT Revenue Data Feed` เป็นประโยคไทยของ contract ("รายได้ตามรายงานรายได้ของ NT รายเดือน — … ไม่ใช่ยอดขายจาก Sales DW…")
= commit `345c661` ทำงานบนข้อมูลจริง. คอลัมน์ไม่เปลี่ยน → **ไม่ต้องลงทะเบียน source ใหม่**

### b. job `result_retention` รอบแรก — วัดจากการรันจริงบนสำเนา

รันครั้งแรก **30 วินาทีหลัง server start** แล้วทุก 24 ชม. (`scheduler.py:18,52` + `_run_periodic` sleep 30)
ค่าที่ใช้: `result_retention_days` ไม่มีใน `admin_config` → **default 30 วัน**; workspace override = `NULL` ทั้งคู่

ผลจริงบนสำเนาสดของ `app.db` (log: `[ResultRetention] purged {...}`):

| ตาราง | ผล | ย้อนกลับได้ไหม |
|---|---|---|
| `chat_history` | **1,513 แถว** — `result_data` (2) และ `sql_result_summary` (1,285) เป็น `NULL`, `ai_response` ทั้ง 1,513 กลายเป็นข้อความ "คำตอบหมดอายุ…" | ❌ **ไม่ได้** (มี backup) |
| `chat_session_data` | **55 แถว ถูกลบทั้งหมด** | ❌ ไม่ได้ |
| `query_correction_log` | 0 (ไม่มีตาราง) | — |
| ไฟล์ export ชั่วคราว | 0 | — |
| **คำถาม / SQL ที่เก็บไว้** | **1,513 / 1,511 — อยู่ครบ** | — |

แถวใหม่สุดใน `chat_history` = `2026-07-14` → เก่ากว่า 30 วันทั้งหมด จึงโดนทั้งก้อนในรอบเดียว
ตั้งก่อน start ได้: `admin_config.result_retention_days = 0` (= ไม่ลบเลย) หรือ override ต่อ workspace
(`workspaces.result_retention_days`) — **ต้องตั้งก่อน start เท่านั้น** เพราะรอบแรกมาใน 30 วินาที

> พบระหว่างทาง (ไม่เกี่ยวกับ go-live): job `export_cleanup` **ล้มทุกรอบ** บน `app.db` จริง —
> `no such table: report_exports` (F6 สร้างตารางไม่ทัน DB นี้) เขียน ERROR ลง log ทุกครั้ง ไม่กระทบคำตอบ

### c. ของจริงรันอย่างไร

| ส่วน | สถานะวันนี้ |
|---|---|
| AI server | **ไม่ได้รัน** — `.claude/launch.json` และ README ใช้ `venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`; `venv/bin/python` = **3.10.11** (pytest มีเฉพาะใน `python3.14`) |
| `.env` ที่ใช้ | `DATABASE_URL=./app.db`, `CONFIG_DB_URL=./config.db`, `BUSINESS_DB_PATH=./nt_fi_report.sqlite`, `REDIS_URL=redis://localhost:6379/0`, `AI_PROVIDER=gemini` (แต่ `admin_config.default_ai_provider` = **matcha** ชนะ), `CORS_ORIGINS` = 5 origin ของ localhost; **ไม่ได้ตั้ง** `DATA_SOURCE_ALLOWED_ROOTS` (= admin API ลงทะเบียน path ใหม่ไม่ได้ — CLI ไม่ถูกจำกัด), `DATA_SOURCE_CACHE_DIR` (default `./.source_cache`), `MCP_ALLOWED_HOSTS` (default localhost), `ENVIRONMENT` (default `development` → CORS รับทุก origin ของ localhost) |
| **Redis** | ✅ **รันอยู่** (`redis-server *:6379`) → limit รายนาทีบังคับได้จริง ไม่ fail-open |
| Portal (PocketBase) | ✅ รันอยู่ `127.0.0.1:8090` — **แต่ start ตั้งแต่ Sep 15 11:50** ขณะที่ `assistant.pb.js` แก้ล่าสุด Sep 20 19:17 → **process ที่รันอยู่ใช้ hook ตัวเก่า** (scope เดือนเดียว, เตือนงวดแบบ `!==`, ไม่แยก 429) → **ต้อง restart PB ก่อน E2E** |
| `pocketbase_0/.env` | มีไฟล์ แต่ **ไม่มี `ASSISTANT_*` สักตัว** → `GET /api/nt/assistant/status` คืน `enabled:false` = ปุ่มไม่แสดง (default deny ทำงานถูก) |
| เครื่อง | AI กับ NT-Report อยู่**เครื่องเดียวกัน** (D1) — source ชี้ path ในเครื่องได้ตรง |

### d. สัญญาระหว่าง hook กับ AI — ตรงกันทุก field ยกเว้น 1 ข้อ

**Request** (`assistant.pb.js` → `SimpleQueryRequest`): ตรงทุก field

| hook ส่ง | AI รับ | ตรงไหม |
|---|---|---|
| `question` (≤500 ตัวอักษร) | `str, min_length=1` | ✅ |
| `context` (ส่ง**เสมอ** จาก `ASSISTANT_CONTEXT_MAP`) | `Optional[str]` | ✅ |
| `include_sql` = `callerIsAdmin` | `bool` | ✅ |
| `include_data: true`, `max_rows: 20` | `bool`, `int ge=1 le=1000` | ✅ |
| `source: "portal"` | `Optional[str]` → `query_audit.channel` = `portal` | ✅ (ไม่ขึ้นต้นด้วย `mcp` จึงไม่ถูกเติม prefix) |
| `scope.year_month` = **list 13–24 เดือน** (ม.ค. ปีก่อน → งวดรายงาน) | list 1–1000 ค่า = `IN` | ✅ **ยิงจริงแล้ว** 20 ค่า ผ่าน |
| `scope.org_code` = string หรือ array | เหมือนกัน | ✅ |

**Response** (`SimpleQueryResponse` → hook): hook อ่าน `answer` / `data` / `row_count` / `sql` / `data_as_of` / `error` — มีครบ;
`parts` / `computed` = `null` สำหรับคำตอบ context เดียว และ hook ไม่แตะ ✅

**Status code — ยิงจริงบนสำเนาครบทุกแถว:**

| สถานการณ์ | AI คืนจริง | hook แปลงเป็น | ถูกไหม |
|---|---|---|---|
| ตอบได้ | 200, `error=null`, มี `data_as_of` | 200 + คำตอบ | ✅ |
| 0 แถว | 200, `answer` = `ไม่พบข้อมูลที่ตรงกับเงื่อนไข`, **ไม่มี SQL** | 200 | ✅ |
| `scope` key ที่ไม่ประกาศ / ค่าผิดชนิด | **400** + ข้อความตายตัว | 400 `scope_invalid` | ✅ |
| context นอก workspace / ไม่มีอยู่ | **403** ข้อความเดียวกันทั้งสองกรณี | 502 `upstream_forbidden` + "การตั้งค่าไม่ถูกต้อง" | ✅ |
| ไม่มี key / key ผิด | **401** | 502 `upstream_unauthorized` | ✅ |
| เกินโควตารายวัน | **429** (ยืนยัน: key `rate_limit_per_day=1` ยิงครั้งที่ 2) | 429 "มีผู้ใช้งานจำนวนมาก" | ✅ |
| `query_audit` เขียนไม่ได้ | 503 | 502 ทั่วไป "ลองใหม่ภายหลัง" | 🟡 ข้อความพอใช้ได้ แต่ audit เป็น `upstream_503` |
| คำถามซ้ำใน 5 วิ | 200, `error` = `duplicate_request` | 409 "มีคำถามเดียวกันกำลังประมวลผล" | ✅ |
| **source กำลัง publish** | 200, `error` = **`source_unavailable`** | **502 "ตอบคำถามนี้ไม่ได้ กรุณาถามใหม่ด้วยถ้อยคำอื่น"** | ❌ **ผิด** |

> ❌ **ข้อเดียวที่ไม่ตรง — regression จาก hardening.** `mapUpstreamError()` ของ hook ทดสอบ `/publish/i`
> กับ `payload.error` ซึ่ง**เคย**เป็นข้อความไทยที่มีคำว่า "publish" อยู่ — ตั้งแต่ hardening `error` เป็น **รหัส**
> `source_unavailable` และคำว่า publish เหลืออยู่ใน `answer` ซึ่ง hook ตั้งใจไม่อ่าน
> **ยืนยันด้วย code ของ hook เอง** (รัน `mapUpstreamError` กับรหัสจริงทั้ง 4 ตัว) และ**ยิงจริง**บนสำเนา
> (ชี้ source ของ sales ไปโฟลเดอร์ว่าง = สิ่งที่ reader เห็นระหว่าง publish) →
> ผู้ใช้ระหว่าง publish จะได้คำแนะนำผิด ("ถามใหม่ด้วยถ้อยคำอื่น") แทน "ข้อมูลกำลังอัปเดต รอสักครู่"
> **แก้ 1 บรรทัดฝั่ง hook** (repo NT-Report = อ่านอย่างเดียวสำหรับ session นี้) →
> ข้อเสนอใน §4; เป็นเงื่อนไขของ exit criteria ข้อ "ระหว่าง publish"

**`GET /api/v1/query/contexts`** ต้องมี key แล้ว (ไม่มี = 401) — hook ไม่ได้เรียก endpoint นี้ จึงไม่กระทบ

### e. report_type → context, และ scope ที่ส่งจริง

`report_type` มาจาก select field ของ collection `reports` (ไม่ hardcode): **ebt / expense / revenue / sales / presentation**
`presentation` ไม่มี context = ไม่แสดงปุ่ม (ตั้งใจ) ✅

| report_type | รายงานที่ published | งวดล่าสุด | context | งวดของ feed | เตือนไหม |
|---|---|---|---|---|---|
| revenue | 5 | **2026-08** | `feed_revenue` | 202608 | ไม่ (เท่ากัน) |
| sales | 6 (รวม `2000-01` ที่เป็น TEST) | **2026-08** | `feed_sales` | 202608 | ไม่ |
| expense | 2 | **2026-04** | `feed_expense` | 202608 | ไม่ (build ใหม่กว่า = ปกติ) |
| ebt | 1 | **2026-03** | `feed_ebt` | 202607 | ไม่ |
| presentation | 1 | 2026-04 | — | — | ไม่มีปุ่ม |

- ทุกงวดของรายงานอยู่ใน feed: revenue มี 202401–202608, expense / sales 202501–202608, ebt 202501–**202607**
  → scope ของทุกรายงานที่ published มีข้อมูลรองรับ **ไม่มีรายงานไหนที่ build ยังไปไม่ถึง** (คำเตือนงวดจะไม่ขึ้นเลยวันนี้)
- ⚠️ รายงาน sales `TEST — Univer workbook viewer` **งวด `2000-01`** → scope = 199901–200001 → **ทุกคำถามได้ 0 แถว**
  (ไม่ใช่ข้อผิดพลาด แต่ผู้ใช้ที่เปิดรายงานนี้จะเห็น "ไม่พบข้อมูล" เสมอ) — เสนอให้ฝั่ง portal unpublish หรือยอมรับ
- **`allowed_units` ของทุกรายงาน = `[]`** → hook **ไม่ส่ง `scope.org_code` เลยวันนี้** → ปัญหา "ตารางที่ไม่มี
  `cost_center` ใช้ไม่ได้" **ไม่กระทบ go-live รอบนี้**

  วัดไว้ล่วงหน้าเผื่อเปิดรายงานจำกัดหน่วยงานภายหลัง (ยิงจริงด้วย `org_code=1B00000`):

  | context | main_view มี `cost_center` ไหม | เกิดอะไรขึ้นจริง |
  |---|---|---|
  | `feed_revenue` | ❌ `fact_bu_monthly` ไม่มี | router เลือก `fact_org_monthly` (มี) เอง → ตอบถูก (cost center นี้รายได้ = 0 จริง) |
  | `feed_ebt` | ❌ `fact_ebt_division_monthly` ไม่มี | ใช้ `fact_ebt` (มี) → ตอบถูก −0.97 ล้านบาท |
  | `feed_expense` / `feed_sales` | ✅ `fact_expense` / `fact_sales` | ใช้ตารางเดิม |

  → การตกไปตารางรายละเอียด **ทำงานอัตโนมัติ** ไม่ต้องแก้ config; แต่ต้องวัดตัวเลขแยกต่างหากถ้าจะเปิด
- ผลข้างเคียงของ `scope.year_month` ที่ส่งทุกครั้ง: ตาราง dim ที่ไม่มีคอลัมน์งวด (revenue `dim_bu` / `dim_product` /
  `dim_service_group` / `dim_sub_product` / `dim_org*`, expense `dim_gl` / `dim_expense_category` / `dim_org_snapshot`,
  sales `dim_org` / `dim_product`) **ใช้ไม่ได้ภายใต้ scope** — ไม่กระทบเพราะ fact ทุกตัว **denormalize ชื่อไว้แล้ว**
  (`division_name`, `expense_group_name`, `product_name`, `unit_fname`) ยืนยันด้วย smoke ทั้ง 4 context ที่ตอบถูก

### f. ข้อบกพร่องของ REST — ปิดแล้ว ยืนยันด้วยการยิงจริง

งาน hardening (`plan/archive/RESULT_P7_HARDENING.md`, commit `eafc2e5`…`ca71357`) อยู่ครบใน working tree
(`ca71357` อยู่ใน log) และ pytest **1078 passed / 3 skipped**. ยิงจริงบนสำเนาแล้วตามตารางใน §1d — ครบทุกแถว

**ยังค้างจริง (ไม่ได้แก้ในงานนี้ รอตัดสิน):**
- `app/main.py` เปิด CORS ทั้งแอปตาม `CORS_ORIGINS` + รับทุก origin ของ localhost เมื่อ `ENVIRONMENT=development`
  ขณะที่ `docs/PORTAL_INTEGRATION.md` เขียนว่า "portal ไม่ได้อาศัย CORS" — portal ไม่ได้อาศัยจริง (เรียกผ่าน PB proxy)
  แต่ประโยคในเอกสารกับพฤติกรรมของแอปไม่ตรงกัน
- REST ไม่ตรวจ `has_scope('query')` (MCP ตรวจ) — key ที่ scope `admin` ใช้ `/api/v1/query` ได้
- dedup 5 วินาทีผูก user + คำถาม: **ยืนยันแล้วว่าเกิดจริง** — ยิงคำถามเดียวกันสองครั้งห่าง 0.3 วิ คนที่สองได้
  `duplicate_request`; ผู้ใช้ portal ทุกคนมาในชื่อ user เดียวของ key → **สองคนถามคำถามเดียวกันพร้อมกัน คนที่สองโดน**
  (hook แปลงเป็น 409 + ข้อความที่ถูกต้องแล้ว จึงไม่ใช่ข้อบกพร่องที่ผู้ใช้เข้าใจผิด แต่เป็นข้อจำกัดที่ต้องรู้)

---

## 2. Checklist เปิดใช้ + แผนถอยกลับ + exit criteria

ทุกขั้น **ต้องได้คำสั่งจากเจ้าของก่อน**; ขั้นที่ย้อนกลับไม่ได้ทำเครื่องหมาย ❌ ไว้

| # | ขั้น | ถอยกลับ | ย้อนได้ไหม |
|---|---|---|---|
| 1 | backup สด `config.db` + `app.db` (backup API + quick_check + SHA-256) | — | — |
| 2 | **ตัดสิน retention ก่อน start**: ปล่อย 30 วัน / ตั้ง `result_retention_days=0` / export ก่อน | ตั้งค่าใน `admin_config` แก้ได้ตลอด — แต่แถวที่ล้างแล้วไม่คืน | ❌ (ถ้าปล่อยล้าง) |
| 3 | start AI server (`venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`) | `kill` process | ✅ |
| 4 | ตรวจ `GET /admin/sources/{name}/status` ครบ 4 = ok + งวดตรงตาราง §1a | — | ✅ |
| 5 | smoke 1 คำถาม/context ด้วย session ของ admin | — | ✅ |
| 6 | **ออก key จริง** ผูก workspace `nt-report` (+ rate limit) — raw key แสดงครั้งเดียว | `PUT /admin/api-keys/{id}` → `is_active=0` (เพิกถอนทันที) | ✅ |
| 7 | เจ้าของใส่ `ASSISTANT_API_URL` / `_KEY` / `_CONTEXT_MAP` ใน `pocketbase_0/.env` | ลบ `ASSISTANT_API_KEY` | ✅ |
| 8 | **restart PocketBase** (บังคับ — process ที่รันอยู่ใช้ hook เก่า) | restart กลับด้วย env เดิม | ✅ |
| 9 | E2E ตาม exit criteria ข้อ 6 | ปิดปุ่ม = ลบ env + restart | ✅ |
| 10 | เทียบตัวเลข 10 คำถาม/report_type (ข้อ 7) | ตัด type ที่ไม่ผ่านออกจาก context map | ✅ |

**ถอยกลับเร็วที่สุด (ทุกกรณี):** ลบ `ASSISTANT_API_KEY` จาก `pocketbase_0/.env` → restart PB → ปุ่มหายทันที
(ไม่ต้องแตะฝั่ง AI). ถ้าสงสัยว่า key รั่ว: `is_active=0` ที่ฝั่ง AI ด้วย — คำขอถัดไปได้ 401 ทันที

**Exit criteria**

| ข้อ | เกณฑ์ |
|---|---|
| E1 | ทุก source `status` = ok, งวดตรงกับ manifest, `reconcile.ok` |
| E2 | smoke 4 context ผ่าน (ทำบนสำเนาแล้ว — ต้องซ้ำบนของจริง) |
| E3 | ผู้ใช้ไม่มีสิทธิ์เปิดรายงาน → 403 จาก PB และ **`query_audit` ไม่มีแถวเพิ่ม** |
| E4 | ผู้ใช้มีสิทธิ์ → คำตอบ + `data_as_of` แสดง; "เดือนล่าสุด" ในรายงานงวด 2026-07 = 202607 |
| E5 | context map ชี้นอก workspace → ข้อความ "การตั้งค่าไม่ถูกต้อง" (ไม่ใช่ "ระบบล่ม") |
| E6 | ระหว่าง publish → ผู้ใช้เห็น "ข้อมูลกำลังอัปเดต" (**ต้องแก้ hook ก่อน** — §1d) |
| E7 | audit ครบสองฝั่ง: PB `assistant_ask` + AI `query_audit` (key / channel / scope / SQL / row_count, ไม่มีค่าผลลัพธ์) |
| E8 | rate limit ทำงาน: รายวัน (ยืนยันแล้ว = 429) และรายนาที (Redis รันอยู่) |
| E9 | **ถูก ≥ 9/10 ต่อ report_type** เทียบ dashboard — type ที่ไม่ผ่าน = ไม่ใส่ใน context map |

**หลักฐานที่มีแล้ว (ซ้อมบนสำเนา):** E2 ✅, E7 ✅ (`query_audit` มี `api_key_id` / `channel=portal` /
`workspace=nt-report` / scope เต็ม / SQL / row_count และ**ไม่มีค่าผลลัพธ์**), E8 รายวัน ✅

---

## 3. ข้อค้างที่รอเจ้าของตัดสิน

| # | เรื่อง | ข้อเสนอ |
|---|---|---|
| 1 | "ของจริง" = เครื่องนี้ใช่ไหม | ใช่ (AI + NT-Report + PB + Redis อยู่เครื่องเดียวกัน) |
| 2 | **retention รอบแรก** | ปล่อยล้างตาม 30 วัน (มี backup) — กระทบ 1,513 คำตอบ + ลบ `chat_session_data` 55 แถว; คำถาม/SQL อยู่ครบ |
| 3 | key ของ portal | ทั้ง 4 context, 20/นาที 2,000/วัน, ผูก user `admin@ntplc.co.th` (id 37) |
| 4 | Redis | ✅ รันอยู่แล้ว — ไม่ต้องตัดสิน |
| 5 | `llm_provider_allowlist` ของ `datafeed_*` | ตั้ง `["matcha"]` ตาม D4 หรือคง `NULL` |
| 6 | CORS + `has_scope('query')` | ไม่บล็อก go-live — ตัดสินแยก |
| 7 | multi-context ใน portal | ไม่อยู่ในรอบแรก (hook ส่ง `context` เสมอ) |
| 8 | รายงาน sales งวด `2000-01` (TEST) | ให้ฝั่ง portal unpublish |

⚖️ เปิดภายใต้ข้อสมมติ: ผู้ใช้รายแรกเป็นหน่วยงานภายใน NT (Tier 1) — D4 / §6.6 ข้อ 8 ยังรอ DPO

---

## 4. ข้อเสนอกลับไปฝั่ง NT-Report

1. **(บล็อก E6) `mapUpstreamError` ไม่รู้จักรหัสใหม่** — `payload.error` เป็นรหัสคงที่แล้ว ไม่ใช่ข้อความ
   → `/publish/i` ไม่ match `source_unavailable`. แก้โดยเทียบรหัสตรง ๆ:
   `source_unavailable` → 503 "ข้อมูลกำลังอัปเดต…", `duplicate_request` → 409 (ทำงานอยู่แล้ว),
   `query_failed` / `internal_error` → 502. ชุดรหัสทั้งหมดอยู่ใน `app/core/outbound.py`
2. **503 จาก AI** (`audit_unavailable`) ตกเข้าสาขา default → audit เป็น `upstream_503`; ข้อความ "ลองใหม่ภายหลัง"
   ถูกอยู่แล้ว แต่แยก audit ให้อ่านออกจะดีกว่า
3. **รายงาน sales งวด `2000-01`** (TEST — Univer workbook viewer) ยัง published → ผู้ใช้ที่เปิดจะได้ "ไม่พบข้อมูล"
   ทุกคำถาม (scope = 199901–200001)
4. **ต้อง restart PocketBase** ก่อน E2E — process ที่รันอยู่ start ตั้งแต่ 2026-09-15 จึงยังใช้ hook ก่อนแก้

---

## 5. ทำอะไรไปแล้วบนของจริง (ตามคำสั่งของเจ้าของ 2026-09-20)

ข้อตัดสิน 4 ข้อ: retention = ปล่อยล้างตาม 30 วัน · key = ทั้ง 4 context 20/นาที 2,000/วัน ·
`.env` ของ PB = เจ้าของทำเอง · `llm_provider_allowlist` = `["matcha"]`

| ขั้น | ทำ | หลักฐาน |
|---|---|---|
| backup สด | `<scratchpad>/golive/backup-prestart-20260920-205751/` | `quick_check=ok`, SHA-256 ของต้นฉบับเท่าเดิมก่อน/หลัง |
| allowlist | `UPDATE data_sources SET llm_provider_allowlist='["matcha"]' WHERE source_type='duckdb_file'` (SQL + รูป JSON เดียวกับที่ `PUT /admin/sources/{name}/policy` เขียน; server หยุดอยู่ จึงไม่มี cache ให้ invalidate) | 4 แถว; `llm_data_policy` ยังเป็น `full` |
| migrate | **ไม่ต้องทำ** — ทำไว้แล้ว (§1a) | diff ของ dump = เฉพาะ `sqlite_sequence` |
| start server | `venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000` | — |
| **retention รอบแรก** | รันเอง 30 วิหลัง start: `purged {'chat_history': 1513, 'chat_session_data': 55, …}` | **ตรงกับที่วัดบนสำเนาทุกตัวเลข** |
| source status | ทั้ง 4 `ok=True` + schema ใหม่ (2.3.1 / 1.2.1 / 1.3.1 / 1.4.1) + `build_id` ตรง symlink | re-sync ของ contract ทำงาน: `feed_revenue.description` เปลี่ยนเป็นประโยคไทยของ contract เอง |
| smoke | 1 คำถาม/context ผ่านครบ (revenue 3,434.07 · expense 3,060.28 · sales 3,480.99 · ebt 39.72 ล้านบาท) | ตรง control totals |
| **ออก key จริง** | `nt-report-portal` id 4 · scope `query` · workspace 2 (`nt-report`) · `allowed_contexts=None` (= ทั้ง workspace) · 20/นาที 2,000/วัน · user 37 | raw key ส่งให้เจ้าของทาง terminal **ครั้งเดียว — ไม่มีในไฟล์ / log / commit ใด** |
| เทียบตัวเลข 80 ครั้ง | ด้วย key จริง body รูปเดียวกับ hook | `RESULT_F11.md` |
| แก้ต้นเหตุของ scope กว้าง | `308acb1` — prompt บอกขอบเขต + งวดอ้างอิง (4 จุด รวม pass 1 ของ two-pass) | pytest **1084 passed, 3 skipped** (baseline 1078); +6 test ที่ fail บน code เดิม |

**ยังไม่ทำ (ของเจ้าของ / รอเกณฑ์ผ่าน):** ใส่ `ASSISTANT_*` ใน `pocketbase_0/.env` · restart PocketBase ·
E2E ผ่าน PB จริง (ข้อ 6 ของ prompt) · เปิด multi-context · เปิด `mcp_external_enabled`

### Exit criteria — สถานะ

| | ผล |
|---|---|
| E1 source status | ✅ ทั้ง 4 ok, งวด + schema ตรง manifest |
| E2 smoke 4 context | ✅ บนของจริง |
| E3 ไม่มีสิทธิ์ → ไม่มี call ออก | ⏳ ต้องผ่าน PB (ต้องตั้ง `.env` + restart ก่อน) |
| E4 คำตอบ + `data_as_of` | ✅ ฝั่ง AI (`data_as_of` มาครบทุกคำตอบที่สำเร็จ); ส่วนที่ผู้ใช้เห็นรอ PB |
| E5 context นอก workspace → อ่านออก | ✅ 403 ข้อความตายตัว (ยิงจริง) |
| E6 ระหว่าง publish | ⚠️ ฝั่ง AI ถูก (`source_unavailable`) แต่ **hook แปลผิด** → ต้องแก้ hook ก่อน |
| E7 audit สองฝั่ง | ✅ ฝั่ง AI ครบ (key / channel `portal` / workspace / scope เต็ม / SQL / row_count, ไม่มีค่าผลลัพธ์); ฝั่ง PB รอ E2E |
| E8 rate limit | ✅ รายวัน (429 ยืนยันแล้ว) และ **รายนาทีผ่าน Redis** (ยืนยันโดยบังเอิญตอนวัดรอบสอง) |
| **E9 ≥ 9/10 ต่อ report_type** | ❌ **8 / 8 / 8 / 5** → ไม่เปิด type ใด |

---

## 6. หลังเปิดปุ่ม `revenue` (2026-09-20 ดึก → 2026-09-21)

| เวลา | เหตุการณ์ | หลักฐาน |
|---|---|---|
| 09-20 22:0x | เขียน `ASSISTANT_*` ลง `pocketbase_0/.env` (ใช้ key id 4 ใบเดิม — ตามที่เจ้าของสั่ง) · restart PB ด้วย `scripts/serve.sh` | env ทั้ง 3 ตัวอยู่ใน process ของ PB; ยิงด้วย key จากไฟล์ได้ 200 |
| 09-20 22:12–22:23 | ผู้ใช้กดถาม → **`ReferenceError: scopeMonths is not defined`** ×3 — PB รัน handler ใน goja runtime แยกที่มองไม่เห็น function ระดับไฟล์; test ของ hook เป็น node จึงไม่เคยดักได้ | `pb_data/auxiliary.db` `_logs` |
| 09-20 22:31 | NT-Report แก้ (`adf9da6` helper ใน handler, `407eb81` map รหัส error ตรง ๆ, `83fad4e` บังคับ smoke test ผ่าน PB) | commit ฝั่ง NT-Report |
| 09-20 22:33 → 23:01 | **ผู้ใช้จริงถาม 12 คำถาม** — ถูก 4/12 → แก้ฝั่ง AI 3 สาเหตุ → ตัวเลขถูก 9–10/12 · **แต่ปี พ.ศ. ในข้อความผิด 7/12 → ถูกครบ 4/12** (`RESULT_F11` §9) | `RESULT_F11.md` §7 |
| 09-21 | NT-Report publish contract PATCH (`agg` ต่อคอลัมน์, ถ้อยคำ ebt, เกณฑ์ EBT9 = ตอบพร้อมป้าย) · ฝั่ง AI แก้ 4 จุดที่ไม่อ่านคำอธิบายข้อมูล | `RESULT_F11.md` §8 |

**Exit criteria — อัปเดตจาก §5:** E3 / E4 / E7 **ผ่านบนของจริง** (คำถามจริงลง audit ครบทั้ง PB `assistant_ask` = `ok`
และ AI `query_audit` channel `portal` พร้อม scope 20 งวด) · E6 ฝั่ง hook แก้แล้ว (`407eb81`) ยังไม่ได้ยิงจริงระหว่าง publish ·
E8 รายนาที: Redis หยุดไปช่วงหนึ่ง (fail-open) → **เจ้าของ start กลับแล้ว 2026-09-21**; ตัวนับเปิด client ใหม่ทุกคำขอ จึงกลับมาบังคับเองโดยไม่ต้อง restart — ตรวจผ่าน `CacheService` ของแอป: ping ได้ และเห็นตัวนับของคำขอจริง · E9: **ยังไม่ผ่าน** — คำถามจริงถูกครบทั้งตัวเลขและปีแค่ 4/12 (ตัวเลข 9/12, ปีในข้อความผิด 7/12), ชุดของทีม 8/10

**ค้าง:** ~~Redis~~ (start แล้ว) · ~~OpenAPI เต็มเปิดโดยไม่ต้อง login~~ (**ปิดแล้ว** `cabbdcd` — 404 บนของจริง) · commit ฝั่ง AI ยังไม่ push ·
คุณภาพ 4 ข้อ (`RESULT_F11` §7–§8) → ย้ายไปเป็น `PLAN_8` Phase 8.0
