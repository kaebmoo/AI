# Plan 7: Data Source as a Service — ถามข้อมูลจากแหล่งที่ผู้ใช้กำหนด โดยไม่ต้อง import

**สถานะ:** 🟡 Phase 1 ✅ DONE (2026-09-18) — Phase 2 ✅ DONE (2026-09-19 — exit ครบ 4/4 โดเมน: revenue 14/14, expense 12/12, sales 12/12, ebt 22/24 บน contract 1.3.1) — Phase 3 ✅ DONE (2026-09-19) — Phase 4 ✅ DONE (2026-09-19; API ครบ, admin UI ยังไม่ทำ) — Phase 4.5 ✅ DONE (2026-09-19; `llm_data_policy` + provider allowlist ต่อ source, retention, DSR, audit ของคำถาม — API ครบ, admin UI ยังไม่ทำ, classification ต่อคอลัมน์เลื่อน) — Phase 5 ✅ DONE (2026-09-19; orchestrator หลัง flag ต่อ workspace ที่ `/api/v1/query`, eval ข้ามโดเมน 8–9/10 จาก baseline 0/10) — Phase 6 ✅ DONE (2026-09-20; MCP facade `/api/v1/mcp` หลัง flag `mcp_external_enabled` ปิดเป็นค่าเริ่มต้น, ต่อ Claude Code จริงผ่านแล้วบนสำเนา DB — **ยังไม่เปิดบน DB จริง / ยังไม่ออก key จริง**, widget ไม่ทำ) — Phase 7 ยังไม่เริ่ม | ผล: `plan/archive/RESULT_P7_PHASE{1,2,3,4,45,5,6}.md` | งานฝั่ง NT-Report: `plan/PROMPT_NT_REPORT_P7.md`
**ความสัมพันธ์กับแผนเดิม:** ต่อยอด/แทนที่บางส่วนของ `PLAN_6_SAAS.md` (ดู §9), รวม Plan 1B-C (MCP SSE + API key) ไว้ใน Phase 6
**ผู้ใช้รายแรก:** NT-Report portal (F11 dashboard Q&A) — **go-live 2026-09-20: ฝั่ง AI เปิดแล้ว** (config.db migrate, server รัน, key จริงผูก workspace `nt-report` ออกแล้ว, `llm_provider_allowlist` = `["matcha"]`, ทุก source ok ที่ contract 2.3.1 / 1.2.1 / 1.3.1 / 1.4.1) — **ปุ่มฝั่ง portal ยังไม่เปิด**: เทียบ 10 คำถามต่อ report_type ได้ 8 / 8 / 8 / 5 ยังไม่ถึงเกณฑ์ 9/10 · ผล: `plan/archive/RESULT_P7_GOLIVE.md`, `plan/archive/RESULT_F11.md`

---

## 1. ปัญหาของสถาปัตยกรรมปัจจุบัน

```
web chat / API ──► QueryEngine ──► LLM (Vanna) ──► SQL ──► business DB ก้อนเดียว (nt_fi_report.sqlite)
                                                              ▲
                                  ข้อมูลผู้ใช้ต้อง "import" เข้ามาก่อน (F10: import_datafeed.py)
```

ข้อเท็จจริงจาก code (ตรวจ 2026-09-18):

| จุด | สภาพปัจจุบัน | ผลกระทบ |
|---|---|---|
| `app/db/session.py` | `business_engine` เป็น **global ตัวเดียว** จาก `BUSINESS_DB_PATH` | ต่อได้ทีละ 1 database ทั้งระบบ |
| `app/services/database_adapter.py`, `business_db.py` | มี adapter SQLite / PostgreSQL / MSSQL แล้ว | ✅ ฐานดี — แต่เลือกจาก settings ไม่ใช่ต่อ request |
| `app/services/context_onboarding.py` | ใช้ `sqlite3.connect` ตรง ๆ | onboarding ได้เฉพาะ SQLite |
| `schema_contexts` | ไม่มีคอลัมน์บอกว่า context นี้อยู่ใน data source ไหน | context ผูกกับ DB ก้อนเดียวโดยปริยาย |
| `ContextRouter` / `/api/v1/query/` | 1 คำถาม = 1 context | ถามข้ามโดเมน (รายได้ + ค่าใช้จ่าย) ไม่ได้ |
| `pinned_filters` (F11-A) | log อย่างเดียว | ผู้เรียกกำหนดงวด/ขอบเขตข้อมูลไม่ได้จริง |
| API key (`api_key_service.py`) | scope = `query/admin/full` ต่อ user | ไม่จำกัดว่า key นี้เห็น context/แหล่งข้อมูลไหน |
| Vanna/Chroma | collection เดียวที่ `./chroma_db` | training ของทุกแหล่งปนกัน |
| ข้อมูล NT-Report ใน AI | มีแค่ `feed_revenue` 202605 (import 2026-07-11) ขณะที่ DataFeed มี revenue/expense 202608, sales/ebt 202607 | **import ด้วยมือ = ข้อมูลเก่าเสมอ** |

ต้นเหตุหลัก: ระบบถูกออกแบบให้ "ข้อมูลต้องย้ายเข้ามาอยู่ใน AI" ทุกครั้งที่ข้อมูลต้นทางเปลี่ยน ต้องมีคน import ใหม่

## 2. เป้าหมาย

AI Project เป็น **บริการถามข้อมูล (Q&A service)** ที่:

1. **ไปอ่านข้อมูล ณ ที่ที่ข้อมูลอยู่** — ไม่ copy เข้ามาเก็บ (zero-import)
2. เจ้าของข้อมูล (เช่น NT-Report) **ลงทะเบียนแค่ "ข้อมูลอยู่ที่ไหน + ความหมายของข้อมูล"** แล้วได้ API key
3. ผู้เรียก **กำหนดขอบเขตได้จริง** (งวด, หน่วยงาน) — บังคับที่ชั้น SQL ไม่ใช่ขอร้อง LLM
4. ใช้ได้หลายช่องทาง: REST API (มีแล้ว), web chat ของ AI เอง, MCP, หรือ UI ที่ผู้เรียกสร้างเอง
5. ถามข้ามหลายแหล่งในคำถามเดียวได้ (Phase ท้าย)

**ไม่ใช่เป้าหมาย (ตอนนี้):** billing, self-signup, tenant ภายนอกองค์กร — ทำเมื่อมีผู้ใช้จริงนอก NT (ดู §9)

### ข้อสังเกตสำคัญ: "ไม่ import ข้อมูล" ≠ "ไม่ต้อง onboard"

สิ่งที่ทำให้ AI ตอบถูกไม่ใช่ตัวข้อมูล แต่คือ **ความรู้เกี่ยวกับข้อมูล**: คอลัมน์หมายถึงอะไร หน่วยอะไร อะไร sum ได้/ไม่ได้ (เช่น `bg8_ytd_not_summable`, `sales_is_not_revenue`, EBT sum ได้เฉพาะ `ADDITIVE`) — F10 พิสูจน์แล้วว่า knowledge จาก contract ทำให้ได้ value match 14/14
→ แผนนี้เลิก copy **ข้อมูล** แต่ยังต้องลงทะเบียน **ความรู้** (contract) ซึ่งเบาและเปลี่ยนไม่บ่อย

## 3. สถาปัตยกรรมเป้าหมาย

```
┌──────────────── ผู้เรียก (client) ─────────────────┐
│ NT-Report PB hook │ AI web chat │ MCP client │ อื่น ๆ │
└─────────┬──────────────────────────────────────────┘
          │ X-API-Key (ผูก workspace + allowlist ของ context)
          │ {question, contexts?, scope: {year_month, org...}}
          ▼
┌──────────────── AI Service ─────────────────────────┐
│ Auth → Resolve workspace → Context router (ใน allowlist)│
│   → Knowledge (per context, จาก contract/onboarding)  │
│   → LLM → SQL → Validator (F4) → Scope enforcer       │
│   → Source resolver ──► Engine ตาม source type        │
└─────────┬───────────────────────┬───────────────────┘
          ▼                       ▼
  [SQL source]               [File source — DuckDB]
  PostgreSQL / MSSQL /       CSV / Parquet ที่ path / HTTPS / S3
  SQLite (read-only)         เช่น NT-Report/DataFeed/dist/<domain>/latest/
```

### 3.1 แนวคิดหลัก (data model)

| Entity | คืออะไร | ตัวอย่าง |
|---|---|---|
| **Workspace** | ขอบเขตการแยกข้อมูล/ความรู้ (tenant แบบเบา) | `nt-report` |
| **Data Source** | ที่อยู่ของข้อมูล + วิธีเชื่อม + credential (เข้ารหัส) | `file://…/DataFeed/dist/revenue/latest/`, `mssql://dw/…` |
| **Dataset / Table** | ตาราง/ไฟล์ใน source ที่อนุญาตให้ query (allowlist) | `fact_bu_monthly.csv` |
| **Context** | ชุดความรู้สำหรับถามตอบ ผูกกับ source 1 ตัว | `feed_revenue`, `feed_expense`, `feed_ebt` |
| **Contract** | คำอธิบายข้อมูลที่เจ้าของส่งมา (ความหมาย, หน่วย, grain, keys, business rules, control totals) | `DataFeed/contracts/revenue.yaml` |
| **API key** | ผูก workspace + รายการ context ที่เรียกได้ + rate limit | key ของ portal เห็นเฉพาะ `feed_*` |

### 3.2 ทำไมใช้ DuckDB สำหรับ file source

- query CSV/Parquet **ในที่เดิม** ได้ด้วย SQL (`read_csv_auto`, `read_parquet`) ทั้ง local path, HTTPS, S3
- DataFeed ของ NT-Report เป็น CSV + `manifest.json` อยู่แล้ว → ต่อได้ทันทีโดยไม่ต้องให้ NT-Report ทำ DB
- เร็วพอสำหรับขนาดนี้ (revenue feed ≈ 255k แถว) — ถ้าช้าค่อยแปลงเป็น Parquet cache (ดู §7)
- ข้อดีเรื่อง freshness: ชี้ที่ `latest/` → รอบใหม่ของ NT-Report publish เมื่อไร AI เห็นทันที ไม่มีขั้น import

View ที่ AI สร้างตอน query (ชื่อตารางเดิมที่ LLM รู้จัก → ไฟล์จริง):
```sql
CREATE VIEW feed_revenue_fact_bu_monthly AS
  SELECT * FROM read_csv_auto('<source_root>/fact_bu_monthly.csv');
```
→ knowledge/golden เดิมจาก F10 ใช้ต่อได้เกือบทั้งหมด เพราะชื่อตารางไม่เปลี่ยน

### 3.3 Scope enforcement (แทน `pinned_filters` แบบ log อย่างเดียว)

ผู้เรียกส่ง `scope` เช่น `{"year_month": 202608}` หรือ `{"org_code": ["..."]}`:
- AI **ห่อทุก view ด้วย WHERE** ตาม scope ก่อนส่งให้ SQL ที่ LLM สร้างรัน (row-level filter ที่ชั้น engine)
- LLM ไม่มีทางหลุด scope เพราะมองเห็นแค่ view ที่ถูกกรองแล้ว
- คอลัมน์ที่ใช้เป็น scope ต้องประกาศใน contract (`scope_columns`) — scope ที่ไม่รู้จัก = 400 ไม่ใช่ข้ามเฉย ๆ

ใช้แก้ 2 ปัญหาของ F11 ในคราวเดียว: (1) ตอบตรงงวดของรายงานที่เปิดอยู่ (2) รายงานที่จำกัดหน่วยงาน ไม่รั่วข้อมูลหน่วยงานอื่น

### 3.4 Freshness ในทุกคำตอบ

Response เพิ่ม `data_as_of` ต่อ context ที่ใช้ (จาก `manifest.period` / `built_at`) — client แสดงให้ผู้ใช้เห็น และปฏิเสธ/เตือนเองได้เมื่อไม่ตรงกับงวดของรายงาน

## 4. สิ่งที่ต้องแก้ใน code (ภาพรวม)

| ไฟล์/ส่วน | เปลี่ยนอย่างไร |
|---|---|
| `app/db/session.py` | เลิกใช้ `business_engine` global ใน query path → `SourceResolver.get_engine(context)` ต่อ request (cache connection ต่อ source) |
| `app/services/database_adapter.py` | เพิ่ม `DuckDBFileAdapter` (สร้าง view จาก manifest/allowlist, read-only, จำกัด path) |
| `context_onboarding.py` | เปลี่ยนจาก `sqlite3.connect` เป็นใช้ adapter → onboarding ได้ทุก source type |
| `schema_contexts` + migration | เพิ่ม `workspace_id`, `source_id`; ตารางใหม่ `workspaces`, `data_sources`, `source_tables` |
| `scripts/datafeed/gen_docs_from_contract.py` | ยกเป็น service: รับ contract ตอนลงทะเบียน source, re-sync อัตโนมัติเมื่อ contract hash เปลี่ยน |
| `api_key_service.py` + `APIKey` model | เพิ่ม `workspace_id`, `allowed_contexts` |
| `ContextRouter` | เลือกเฉพาะใน allowlist ของ key; รับ `contexts` จากผู้เรียกเป็น hint/บังคับ |
| `vanna_service.py` | แยก Chroma collection ต่อ workspace (หรือ metadata filter) |
| `/api/v1/query/` | `pinned_filters` → `scope` (บังคับจริง); response เพิ่ม `data_as_of` |
| `scripts/datafeed/import_datafeed.py` | คงไว้เป็น fallback (โหมด import) จนกว่า Phase 1 ผ่าน แล้วค่อยพิจารณาเลิก |

## 5. Phases

แต่ละ phase ต้องผ่าน exit criteria ก่อนไป phase ถัดไป

### Phase 0 — ตัดสินใจ (0.5 วัน)
> ตัดสินครบแล้ว 2026-09-18 (ดู §11.1)
- [x] D1 ที่อยู่ของข้อมูล: (ก) **เครื่องเดียวกัน — local path** (ใช้อยู่แล้ว) และ**ต้องออกแบบให้เพิ่มได้**: (ค) object storage S3/MinIO และ (ง) HTTPS + token สำหรับลูกค้าที่ไม่มี (ค) — ไม่เขียน code ล่วงหน้า (ดู §13)
- [x] D2 ใช้ DuckDB (+ `duckdb-engine` สำหรับ SchemaService) สำหรับ file source
- [x] D3 ชื่อ field: **A** — field ใหม่ `scope` = บังคับจริงที่ชั้น SQL (Phase 3), `pinned_filters` รับต่อแบบ log อย่างเดียวช่วงเปลี่ยนผ่าน แล้วค่อยเลิก; NT-Report เปลี่ยนไปส่ง `scope` เมื่อ Phase 3 พร้อม

### Phase 1 — Source registry + DuckDB file source (3–4 วัน) — ✅ DONE 2026-09-18
> ผล (รายละเอียด `plan/archive/RESULT_P7_PHASE1.md`): `feed_revenue` อ่าน `DataFeed/dist/revenue/latest/` ตรง (0 แถว import) —
> ตอบงวดล่าสุด **202608** ตรง `control_totals.csv` ขณะที่สำเนาที่ import ไว้ค้าง 202605;
> eval file source **14/14 value_match** (2 รอบ, P50 6.7–6.8 s) หลัง NT-Report เพิ่มกฎ `ytd_point_in_time` ใน contract 2.0.1 และ regen knowledge (2026-09-18) — ก่อนหน้านั้น 13/14 เท่ากับ legacy (ข้อ #64 โมเดล SUM `revenue_ytd` ข้ามเดือน) → **exit criterion ครบ**;
> latency P50 ≈ 6.1–6.3 s (legacy วันเดียวกัน 6.2–6.3 s, F10 10.5 s); pytest 635 → 695 passed (+60, ไม่มี test เดิมพัง)
- ตาราง `data_sources`, `source_tables`; `schema_contexts.source_id` (context เดิมทั้งหมด → source "legacy" = business DB เดิม → ไม่มีอะไรพัง)
- `DuckDBFileAdapter` + `SourceResolver` ต่อ request
- ลงทะเบียน `feed_revenue` ใหม่เป็น file source ชี้ `DataFeed/dist/revenue/latest/`
- **Exit:** eval `feed_revenue` จาก file source ได้ value match เท่า F10 (14/14) โดยไม่ import; latency P50 ไม่แย่กว่า F10 (10.5s) เกิน 20%; context เดิม (non-feed) ยังผ่าน test suite เดิมทั้งหมด

### Phase 2 — Contract-driven knowledge + freshness (2–3 วัน) — ✅ DONE 2026-09-19 (exit 4/4 โดเมน)
> ผล (`plan/archive/RESULT_P7_PHASE2.md`): `data_as_of` ใน `/api/v1/query` (`deb0a7e`); knowledge จาก contract เป็น service
> + re-sync อัตโนมัติเมื่อ contract/schema_version เปลี่ยน (`38ab63d`); ลงทะเบียน expense/sales/ebt + gate/golden อ่านจาก contract +
> pin CSV dialect (`a2b8568`) — eval revenue **14/14**, expense **12/12**; publish build ใหม่แล้ว AI เห็นเอง (พิสูจน์บนสำเนา layout `builds/<id>`)
> — **sales/ebt ตอบเลขผิดความหมาย** (sales รวม actual+target, ebt บวกรายได้กับค่าใช้จ่าย) เพราะ contract ไม่มีกฎ/control totals ที่จำเป็น → context ปิดไว้ รอตัดสิน (§11.7)
> **อัปเดต 2026-09-19:** NT-Report แก้ contract แล้ว → ฝั่ง AI รองรับ `control_totals.filter` + source ยอดรวมอย่างเดียว (`dfce5d5`), instruction บอกวิธีกรองงวด (`9ec6666`);
> `feed_sales` เปิดแล้ว eval **12/12**; `scope_columns` จาก contract ทับค่าตั้งมือเอง; publish atomic จริง + AI เห็น build ใหม่เองระหว่างงาน —
> **ebt ยังปิด**: NT-Report `90fd787` (ebt 1.2.1) เปลี่ยนยอดรวมเป็น YTD ของ 2 สายงานขาย (+417.33 MB) ≠ นิยามที่เจ้าของให้ไว้ (−1,088 M รายเดือนทั้งบริษัท) และ AI ตอบยอดสะสมเป็นยอดเดือน
> ทำไปแล้วบางส่วนตอนแก้ publish race (2026-09-18, `820052e`): ตรวจ manifest ต่อ build (reconcile.ok + sha256) + ปฏิเสธเมื่อไม่ตรง + query cache ผูก build
> เพิ่มจาก Phase 1 (✅ ทำแล้ว 2026-09-18): regen knowledge ด้วย contract 2.0.1 + กฎ `revenue_ytd` ห้าม SUM ข้ามงวด → eval 14/14
- ลงทะเบียน source พร้อม contract → gen knowledge + golden อัตโนมัติ (ยกจาก `gen_docs_from_contract` / `gen_golden_from_controls`)
- ตรวจ `manifest.json` ทุก query (หรือ cache ตาม mtime/sha): ถ้า contract/schema_version เปลี่ยน → re-sync knowledge + `mark_brain_dirty()`
- ถ้า `manifest.reconcile.ok = false` → ปฏิเสธตอบพร้อมเหตุผล (ไม่ตอบจากข้อมูลที่ไม่ผ่านการกระทบยอด)
- response มี `data_as_of`
- ขยายไป `feed_expense`, `feed_sales`, `feed_ebt`
- **Exit:** 4 โดเมนตอบได้, eval แต่ละโดเมนเทียบ control_totals ผ่านเกณฑ์ value match ≥ 90%; publish รอบใหม่ของ NT-Report แล้ว AI เห็นงวดใหม่โดยไม่ต้องรันอะไร

### Phase 3 — Scope enforcement (2 วัน) — ✅ DONE 2026-09-19
> ผล (`plan/archive/RESULT_P7_PHASE3.md`): `scope` บังคับที่ชั้น SQL ทั้ง file source และ legacy (TEMP view shadow ทุกตาราง + gate อ้างได้เฉพาะตารางที่กรองแล้ว),
> `schema_contexts.scope_columns` (จาก contract หรือ admin), key ที่ไม่ประกาศ = 400, cache/dedup รวม scope — ครบ 3 exit ทั้ง unit test และถามจริง;
> review อิสระพบ bypass ระดับ high ใน gate (CTE scoping) — แก้แล้ว `525c5b6`. เหลือฝั่ง NT-Report: `scope_columns` ใน contract + PB hook ส่ง `scope`
- `scope` → ห่อ view ด้วย WHERE; `scope_columns` ใน contract
- **Exit:** test: scope `year_month=202607` แล้วถาม "เดือนล่าสุด" ได้ 202607 ไม่ใช่ 202608; scope หน่วยงาน A ถามถึงหน่วยงาน B ได้ 0 แถว/ปฏิเสธ; scope คอลัมน์ที่ไม่ประกาศ = 400

### Phase 4 — Workspace + scoped API key + admin (3 วัน) — ✅ DONE 2026-09-19
> ผล (`plan/archive/RESULT_P7_PHASE4.md`): key ผูก workspace/allowlist → นอกสิทธิ์ = **403** (ระบุชื่อ, auto-route, cache) และใช้ได้เฉพาะ `/api/v1/query`;
> context แบบ legacy ของ key ที่ถูกจำกัดอ่านได้เฉพาะ main view (กลไก Phase 3); brain ของ Vanna แยกต่อ workspace; admin API: workspaces, sources (list/status/register ผ่าน gate เดียวกับ CLI);
> REMAIN-9.6 ปิด; review อิสระ 2 รอบ (รอบแรกพบ critical 1 ข้อ — แก้แล้ว `f07439d`); config จริง: workspace `nt-report` = `feed_*`. เหลือ: admin **UI**, ออก key จริงให้ portal (§11.3)
- `workspaces`, `APIKey.workspace_id/allowed_contexts`, Chroma แยกต่อ workspace
- Admin API/UI: ลงทะเบียน source, ทดสอบการเชื่อมต่อ, ดู freshness, ออก key
- **Exit:** key ของ workspace A เรียก context ของ B ไม่ได้ (403) — มี test คุม
- ตาม D8 (§12): workspace = การแบ่ง**ภายใน deployment เดียว** (หน่วยงานของ NT / หน่วยงานของลูกค้าหนึ่งราย) ไม่ใช่การแยกลูกค้าต่างองค์กร — query worker นอก process จึง**ไม่บังคับ** (ความเสียหายจำกัดใน deployment เดียว)

### Phase 5 — ถามข้ามหลาย context (4–5 วัน) — ✅ DONE 2026-09-19
> ผล (`plan/archive/RESULT_P7_PHASE5.md`): สำรวจก่อน — คำถามข้ามโดเมนจริงของผู้ใช้เกือบทั้งหมดเป็น "ผลดำเนินงานรายกลุ่มธุรกิจ" ซึ่ง `pl_costtype` (ชุดที่รวมมาแล้ว) ตอบอยู่แล้ว = ทางเลือก 1;
> dashboard ของ NT-Report ที่ข้ามโดเมนจริง (Forecast, OrgReport) **วางตัวเลขข้างกัน + หารกัน** ไม่มีหน้าใดเอารายได้ลบค่าใช้จ่ายข้ามโดเมนมาเรียกว่ากำไร → **ทางเลือก 2** `app/services/multi_context.py`:
> ผู้สมัครแบบ deterministic (keyword เฉพาะตัว, workspace เดียว, ในสิทธิ์ของ key) → LLM แตกคำถาม 1 call (ตรวจผลใน code) → คำถามย่อยผ่าน `QueryEngine.query` เดิม → **รวมด้วย template ไม่มี LLM** + ratio/ส่วนต่างคำนวณใน code;
> ปิดเป็นค่าเริ่มต้น เปิดต่อ workspace (`PUT /admin/workspaces/{id}/multi-context`), `/api/v1/query` เท่านั้น — eval 10 ข้อ: baseline **0/10** → **8/10, 8/10, 9/10** (P50 7.8–9.2 s, P95 ~12 s); eval รายโดเมนเท่าเดิม (14/12/12/35); review อิสระไม่พบ critical/high; ข้อ "กำไรทั้งบริษัท" ยังถูกตอบด้วยยอด 2 สายงานขาย (pipeline context เดียว + contract ไม่มีกฎ → ข้อเสนอใน `PROMPT_NT_REPORT_P7.md`);
> ทางเลือก 1 ที่ชั้น router (เลิกนับ keyword ซ้อน) วัดกับคำถามจริง 989 ข้อแล้ว**แย่ลง** → ไม่ทำ. เหลือ: chat / telegram, keyword ของ workspace `default`
- ทางเลือกตามลำดับความง่าย:
  1. **ใช้ context ที่รวมมาแล้วจากต้นทาง** (เช่น `feed_ebt` = รายได้ − ค่าใช้จ่ายระดับหน่วยงาน) — ไม่ต้องเขียน code แค่ router เลือกถูก
  2. **Orchestrator:** แตกคำถามเป็นคำถามย่อยต่อ context → รันแยก → LLM รวมคำตอบ (ไม่ JOIN ข้าม source ใน SQL เพราะ key ของแต่ละโดเมนไม่ตรงกัน)
- **Exit:** ชุดคำถามข้ามโดเมน 10 ข้อ เทียบตัวเลขกับ dashboard ถูก ≥ 8 ข้อ; ข้อที่ตอบไม่ได้ต้องบอกว่าไม่ได้ ไม่เดาตัวเลข

### Phase 6 — ช่องทางใช้งาน (2–3 วัน) — ✅ DONE 2026-09-20 (ยังไม่เปิดบน DB จริง)
> ผล ([`archive/RESULT_P7_PHASE6.md`](archive/RESULT_P7_PHASE6.md)): สำรวจก่อน — MCP ภายใน 35 tools (metadata 13 / query 5 / validation 4 / admin 13) **ห้ามเปิดตรง** (SQL ดิบ, sample values, เขียน config; ไม่มี key / allowlist / scope / audit) → สร้าง **facade ไฟล์เดียว** `app/api/v1/mcp_facade.py` ที่ `/api/v1/mcp`:
> stateless Streamable HTTP ใน FastAPI เดิม, `X-API-Key` **ทุก request** (gate หน้า transport; ไม่ผ่าน = 401), 3 tools `ask` / `list_contexts` / `source_status` ผ่าน `run_simple_query` ตัวเดียวกับ `POST /api/v1/query` → `multi_context.ask` → `QueryEngine.query`;
> ขาออกไม่มี SQL / ข้อความ exception / path — refusal เป็น tool error (code + ข้อความตายตัว + `request_id`); ปิดเป็นค่าเริ่มต้น (`admin_config.mcp_external_enabled`, ปิด = 404).
> Exit: pytest **1035 passed / 3 skipped** (+38 ใน `tests/unit/test_mcp_facade.py`, SDK client จริงผ่าน ASGI; test เดิมของ `/api/v1/query` 71 ข้อผ่านโดยไม่แก้); **Claude Code 2.1.270** ต่อจริงบนสำเนา DB ครบ 3 tools + refusal, audit `channel = mcp:claude-code/2.1.270`; overhead เส้นทาง cache (n=12) +6.6 ms P50 / +11.4 ms P95 (เป้า ≤100 ms); review อิสระ: high 2 / medium 2 / low 4 แก้ครบใน `69d896a` (low 1 ข้อบันทึกไว้ไม่แก้).
> **ก่อนเปิดกับ DB จริง (ยังไม่ได้ทำ — RESULT §9):** รัน `migrate_data_sources.py` + `migrate_workspaces.py` บน `config.db` จริง (ไม่มีคอลัมน์ `llm_data_policy` = MCP ปฏิเสธทุก context), เปิด flag + ออก key จริงที่ผูก workspace + ตั้ง `MCP_ALLOWED_HOSTS`, รัน Redis (limit รายนาที fail-open อยู่). คู่มือ: `docs/manuals/manual_mcp_external.md`
- เจ้าของตัดสิน (2026-09-20): client รายแรก = **Claude Code บนเครื่องนี้ + สำเนา DB** และตัวอย่าง client ใน repo (`scripts/mcp_client_example.py`); transport = stateless Streamable HTTP ที่ `/api/v1/mcp` — **ไม่ทำ legacy SSE**, ไม่แยก process; history = stateless เหมือน `/api/v1/query`
- tools 3 ตัวเท่านั้น; `ask` มี `include_data` (แถวถูก cap ที่ `MCP_MAX_ROWS`) — **ไม่มี `include_sql`, ไม่คืน SQL**
- สิทธิของ key = workspace / allowlist เท่านั้น — `scope` ที่ client ส่งกรองให้แคบลงได้ แต่**ไม่ใช่สิทธิระดับแถว** (ผู้ถือ key อ่านได้ทุกแถวของ context ที่ key เห็น; สิทธิระดับแถว = entitlement v2, D7)
- source ที่ policy ≠ `full` **ถูกปฏิเสธบนช่องทางนี้**; อ่าน policy ไม่ได้ / registry ยังไม่ migrate = ปฏิเสธ (ตัวอ่านแบบเข้มของ facade — ไม่ใช้ `policy_for_context` ที่ fail open)
- ที่เลือกเข้มกว่า REST (ผ่อนได้ถ้าเจ้าของต้องการ): รับเฉพาะ key ที่ผูก workspace / allowlist + scope `query` / `full`; 1 tool call = 1 usage (handshake ไม่นับ, ตัวนับเดียวกับ REST); ชื่อ client อยู่ใน `channel` (`mcp:<user-agent>`) ไม่เพิ่มคอลัมน์ใน `query_audit`
- Plan 1B-C / REMAIN-8 **ปิดด้วย phase นี้**; MCP ภายในยังเป็น stdio หลัง pipeline เดิม ไม่มี passthrough
- embeddable chat widget — **ไม่ทำ**: ไม่มี client ที่ 2 ที่ต้องการ; NT-Report ใช้ panel + PB proxy ของตัวเอง — เพิ่มเมื่อเจ้าของยืนยัน use case จริง

### Phase 7 — เปิดให้ภายนอก = private deployment ต่อลูกค้า (อนาคต — ปรับตาม D8 2026-09-18)
- เงื่อนไขเริ่ม: มีลูกค้าจริงนอก NT อย่างน้อย 1 ราย
- **ไม่ใช่ multi-tenant** — เป็นงาน packaging ให้ติดตั้งระบบทั้งชุดแยกต่อลูกค้าได้ซ้ำ ๆ (รายการใน §12)
- ส่วน multi-tenant ของ Plan 6 (self-service, quota/billing, config DB ต่อ tenant) = Tier 3 — ทำเมื่อถึง trigger ใน §12 เท่านั้น

## 6. Security & Access Model (ห้ามตัด)

### 6.1 หลักการ
**เจ้าของข้อมูล (หรือแอปของเขา) เป็นคนตัดสินว่าใครเห็นอะไร — AI เป็นคนบังคับใช้ทางเทคนิค และไม่มีวันขยายสิทธิเกินที่ได้รับ**
AI ไม่เก็บสำเนาทะเบียนผู้ใช้/สิทธิของลูกค้าแยกเอง (สองชุด = drift) — ยกเว้นกรณีผู้ใช้เข้าผ่าน web chat ของ AI ตรง (§6.5 แบบ B)

### 6.2 ห้าชั้นของสิทธิ (กว้าง → แคบ)

| ชั้น | ใครตัดสิน / บังคับ | คุมอะไร | อยู่ที่ไหน |
|---|---|---|---|
| **1. แหล่งข้อมูล** | เจ้าของข้อมูล | account/folder ที่ AI ใช้ **read-only** และเห็นเฉพาะตาราง/view/ไฟล์ที่ตั้งใจเปิด; คอลัมน์อ่อนไหวตัดหรือ mask ตั้งแต่ต้นทาง | credential / DB grant / file permission |
| **2. แอปที่เรียก** | AI | API key ผูก workspace + **allowlist ของ context/คอลัมน์** + rate limit = เพดาน ต่อให้ key หลุดก็ได้แค่นี้ | `APIKey.workspace_id / allowed_contexts` (Phase 4) |
| **3. ผู้ใช้** | แอปผู้เรียก (เช่น PocketBase) ตัดสิน | คนนี้มีสิทธิอะไร → แปลงเป็น **entitlement** (contexts + scope) แนบไปกับการเรียก | ฝั่งผู้เรียก |
| **4. แถว/คอลัมน์** | AI บังคับ | `scope` ห่อ view ด้วย WHERE ก่อน LLM เห็น; คอลัมน์ต้องห้ามไม่อยู่ใน view — **ไม่พึ่ง prompt** | scope enforcer (Phase 3) |
| **5. Audit** | ทั้งสองฝั่ง | ผู้เรียกบันทึก "ใครถามจากสิทธิอะไร"; AI บันทึก key / scope / SQL / คอลัมน์ / จำนวนแถวที่คืน | audit log / query log |

**กฎ:** สิทธิที่ใช้จริง = **เพดานของ key ∩ entitlement ที่ผู้เรียกส่งมา** — scope แคบลงได้อย่างเดียว; ขอ context นอก allowlist = 403 (ไม่ตัดทิ้งเงียบ ๆ)

### 6.3 ความน่าเชื่อถือของ entitlement
- **v1 (server-to-server):** key อยู่ฝั่ง server ของผู้เรียกเท่านั้น browser ไม่เรียก AI ตรง → เชื่อ scope ใน body ได้ (NT-Report ทำแบบนี้อยู่แล้ว)
- **v2 (ผู้เรียกหลายราย / ภายนอก):** ผู้เรียกเซ็น **entitlement token อายุสั้น (~5 นาที)** มี `sub` (user), `resource` (เช่น report_id), `contexts`, `scope`; AI ตรวจลายเซ็นด้วย public key ที่ลงทะเบียนไว้ต่อ workspace → scope ปลอมไม่ได้แม้ key หลุด, audit ของ AI เห็นตัวคนจริง, revoke ผู้ใช้มีผลทันที

### 6.4 กรณี NT-Report
- สิทธิปัจจุบันเป็นระดับ "รายงาน" (`canAccessReport`: role / `allowed_users` / `allowed_groups` / published) — ไม่มีสิทธิระดับแถว
- หลัก: **ถามได้เท่ากับข้อมูลของรายงานที่เปิดได้**
- เพิ่ม "assistant config" ต่อรายงานหรือ report_type: `contexts` + scope template
  - รายงานทั้งองค์กร: `contexts=[feed_revenue]`, `scope={year_month: <period ของรายงาน>}`
  - รายงานจำกัดกลุ่ม/หน่วยงาน (เช่น `grp_mcgroup`, variant พิเศษ): scope เพิ่ม `org_code`
  - variant admin: contexts/คอลัมน์มากกว่า — กำหนดชัดต่อรายงาน
  - ไม่มี config = ไม่แสดงปุ่ม (default deny)
- disable ผู้ใช้ใน PB มีผลทันที เพราะ PB ตรวจทุกครั้งและ AI ไม่ถือ session ผู้ใช้

### 6.5 กรณีลูกค้าภายนอก (ตัวอย่าง: ลูกค้ามี MSSQL)

**ชั้น 1 — ฝั่งฐานข้อมูลลูกค้า (ลูกค้าคุมเอง, แนะนำให้ทำเป็นเงื่อนไขการ onboard):**
```sql
-- สร้าง login เฉพาะ AI, เห็นแค่ schema ของ view ที่ตั้งใจเปิด
CREATE LOGIN ai_reader WITH PASSWORD = '...';
CREATE USER ai_reader FOR LOGIN ai_reader;
CREATE SCHEMA ai;                       -- view ที่เลือกคอลัมน์/รวมยอดแล้ว
GRANT SELECT ON SCHEMA::ai TO ai_reader;
DENY SELECT ON SCHEMA::dbo TO ai_reader; -- ตารางจริงห้ามแตะ
```
- ถ้าลูกค้ามี **Row-Level Security** อยู่แล้ว: AI ส่ง scope ของผู้ใช้ผ่าน `sp_set_session_context` ก่อนรันทุก query → **policy ของลูกค้าเองทำงาน** (ลูกค้าไม่ต้องไว้ใจ scope enforcer ของเราอย่างเดียว — defense in depth)
- คอลัมน์อ่อนไหว: ตัดออกจาก view หรือใช้ Dynamic Data Masking
- ชี้ **read replica** ไม่ใช่ production (กัน query หนักกระทบระบบลูกค้า) + timeout/row cap/cost limit ฝั่ง AI

**การเชื่อมต่อ (เลือกตามระดับความเข้มงวดของลูกค้า):**

| แบบ | ลักษณะ | เหมาะกับ |
|---|---|---|
| Direct | AI ต่อ MSSQL ตรง, TLS (`Encrypt=yes`), ลูกค้า allowlist IP ของ AI | ลูกค้าที่เปิด port ได้ |
| Connector agent | ติดตัว agent เล็ก ๆ ในเครือข่ายลูกค้า ต่อ **ขาออก** มาที่ AI (ไม่ต้องเปิด inbound) รันเฉพาะ SELECT ที่ผ่าน validator | enterprise ที่ห้ามเปิด port |
| Private deployment | ติดตั้ง AI ทั้งชุดในเครือข่ายลูกค้า + LLM ที่ลูกค้าอนุมัติ | ข้อมูลออกนอกองค์กรไม่ได้เลย (การเงิน/ราชการ) |

**ชั้น 2–4 — ใครตัดสินสิทธิผู้ใช้:**
- **แบบ A — ลูกค้าเรียกผ่านแอปของตัวเอง** (เหมือน NT-Report): แอปลูกค้าตัดสิน → ส่ง entitlement (แนะนำ v2 token สำหรับลูกค้าภายนอก)
- **แบบ B — ผู้ใช้ลูกค้าใช้ web chat ของ AI ตรง:** AI เป็นผู้ตัดสิน — login ผ่าน IdP ของลูกค้า (OIDC/SAML/Entra ID) แล้ว map **กลุ่มจาก IdP → policy** (contexts, คอลัมน์, row filter) ที่ admin ของลูกค้าตั้งเองใน workspace; ไม่สร้าง user/รหัสผ่านแยกในระบบเรา

**Credential ของลูกค้า:** เก็บเข้ารหัส (KMS/secret store), ไม่อยู่ใน log/prompt/API response, rotate ได้, ลูกค้า revoke ได้ทันทีด้วยการ disable login ฝั่งตัวเอง

### 6.6 ข้อมูลอ่อนไหว (PDPA / ข้อมูลการเงินของลูกค้า)

**สถานะปัจจุบันของ AI Project (ตรวจ code 2026-09-18; อัปเดตหลัง Phase 4.5 2026-09-19 — ตารางสำรวจครบทุกจุด: `plan/archive/RESULT_P7_PHASE45.md` §1):**

| เรื่อง | สถานะ | หลักฐาน |
|---|---|---|
| ลบ PII ออกจาก log (email, เบอร์ 10 หลัก, เลขบัตร 13 หลัก, password/token/otp) | ✅ | `app/core/logging.py` `PIIRedactingFormatter` (regex — ไม่ครอบคลุมชื่อคน/ที่อยู่/เลขบัญชี) |
| API key เก็บเป็น hash | ✅ | `api_key_service.py` (sha256) |
| ไฟล์ export หมดอายุ | ✅ | `report_service.py` 7 วัน |
| **ส่งแถวผลลัพธ์ / ค่าตัวอย่างให้ LLM ภายนอก** | ✅ คุมได้ต่อ source (Phase 4.5) — default `full` = ยังส่งเหมือนเดิมจนกว่า admin จะตั้ง | `data_sources.llm_data_policy` + `llm_provider_allowlist`; บังคับที่ชั้น provider (`app/core/llm_policy.py`) + ต้นทางของค่า; test ดัก sentinel `tests/unit/test_llm_data_policy.py` |
| **เก็บผลลัพธ์ในประวัติแชท** | ✅ หมดอายุ 30 วัน (ตั้งได้, ต่อ workspace ได้) + โหมดไม่เก็บ | `app/services/retention.py` + scheduler; ข้อความคำตอบ (`ai_response`) ไม่หมดอายุ |
| Audit ของคำถามทุกช่องทาง | ✅ (Phase 4.5) — เดิม `/api/v1/query` + telegram ไม่มีร่องรอย | `query_audit` + `GET /admin/query-audit` (+ CSV) |
| ลบข้อมูลตามคำขอ (DSR) | ✅ (Phase 4.5) | `DELETE /admin/users/{id}/data` |
| จัดชั้นความลับของข้อมูล (classification) | ❌ เลื่อน (D5, 2026-09-19) | — |
| mask/aggregate ข้อมูลส่วนบุคคลในผลลัพธ์ (k ≥ 5) | ❌ ไปกับ classification — `aggregated_only` ตอนนี้ตรวจจากข้อความ SQL เท่านั้น | — |
| ROPA, DPA template, breach process | ❌ ไม่มี (Phase 7 / DPO) | — |

**มาตรการที่ต้องเพิ่ม:**

1. **Data classification ต่อคอลัมน์** (ใน contract หรือ onboarding, admin ลูกค้ายืนยัน): `public / internal / confidential / personal / sensitive_personal` (ข้อมูลอ่อนไหวตาม PDPA ม.26 เช่น สุขภาพ ศาสนา ประวัติอาชญากรรม) — **ไม่ระบุ = confidential**
2. **Policy ตามชั้น (บังคับที่ view ไม่ใช่ prompt):**
   - `sensitive_personal` → ไม่อยู่ใน view เลย เว้นแต่เปิดชัดแจ้ง
   - `personal` → ตอบได้เฉพาะแบบรวมยอด + **กลุ่มขั้นต่ำ (k ≥ 5)** กันระบุตัวตนย้อนกลับ; ไม่คืนค่าดิบ
   - `confidential` (เช่น ข้อมูลการเงินรายลูกค้า) → คืนได้ตามสิทธิ แต่ไม่ส่งค่าให้ LLM ภายนอก (ข้อ 3)
3. **LLM data policy ต่อ source** — `llm_data_policy`:
   - `schema_only`: LLM เห็นแค่ schema + คำถาม เพื่อสร้าง SQL; คำอธิบายผลใช้ template หรือ LLM ภายใน → **ตัวเลขไม่ออกนอกระบบ**
   - `aggregated_only`: ส่งเฉพาะผลที่รวมยอดแล้ว
   - `full`: ส่งผลลัพธ์ได้ (ข้อมูล public/internal)
   - ควบคู่ `llm_provider_allowlist` ต่อ source + ใช้ enterprise terms แบบ zero data retention / ไม่นำไป train; onboarding ต้องเคารพ policy เดียวกัน (ไม่ส่ง sample values ของคอลัมน์ personal/confidential)
4. **Retention ตั้งค่าได้ต่อ workspace:** purge `result_data` หลัง N วัน หรือโหมด "ไม่เก็บผลลัพธ์เลย" (เก็บแค่ SQL + metadata); Vanna/golden ห้ามมีค่าจริงจาก scope ที่จำกัด; cache key ต้องรวม scope
5. **แยกข้ามลูกค้าเด็ดขาด:** vector store / golden / feedback ต่อ workspace — ไม่เอาคำถาม/SQL ของลูกค้า A ไปเป็นตัวอย่างให้ B
6. **Encryption:** TLS ทุกเส้นทาง, credential เข้ารหัส, app DB เข้ารหัส at-rest
7. **Audit สำหรับข้อมูลการเงิน:** ใคร / ถามอะไร / คอลัมน์ไหน / กี่แถว / scope อะไร — ค้นและ export ให้ลูกค้าตรวจได้
8. **ฝั่งสัญญา/กระบวนการ (PDPA):** ลูกค้า = ผู้ควบคุมข้อมูล (controller), เรา = ผู้ประมวลผลข้อมูล (processor) → ต้องมี DPA, บันทึกกิจกรรมการประมวลผล (ม.40), แจ้งเหตุละเมิดภายใน 72 ชม. (ม.37(4)), การส่งข้อมูลไป LLM provider ต่างประเทศ (ม.28–29) ต้องมีมาตรการคุ้มครองเพียงพอ หรือเลือก region/LLM ในประเทศ
   - DSR (ขอลบ/ขอเข้าถึง): เพราะ zero-import ข้อมูลหลักอยู่ที่ลูกค้า — ฝั่งเราต้องลบได้แค่ history/log/cache ของผู้ใช้นั้น → ทำ endpoint ลบตาม user
   - ⚖️ ประเด็นกฎหมายข้างต้นเป็นกรอบทางเทคนิค ต้องให้ DPO/ฝ่ายกฎหมายทบทวนก่อนเปิดให้ลูกค้าภายนอก

### 6.7 มาตรการพื้นฐาน (ทุก source)

| ความเสี่ยง | มาตรการ |
|---|---|
| เขียน/ลบข้อมูลต้นทาง | connection read-only + SQL validator (F4) + DuckDB ไม่ attach แบบเขียนได้ |
| SSRF / อ่านไฟล์อื่นในเครื่อง | allowlist root path/host ต่อ source; DuckDB จำกัด path + lock config หลัง setup (ตรวจ option ของเวอร์ชันที่ใช้ใน Phase 1) |
| query หนักทำระบบลูกค้าล่ม | timeout, row cap, ชี้ replica |
| ผลลัพธ์รั่วเกิน | `max_rows` ฝั่ง server, audit ทุกคำถาม |
| ต้นทางล่ม/ช้า | timeout ต่อ source + ข้อความชัด (ไม่ตอบจาก cache เก่าเงียบ ๆ) |

### 6.8 Phase ที่เพิ่ม/เปลี่ยนเพราะหัวข้อนี้
- Phase 3 (scope) เพิ่ม: column allowlist + classification policy ที่ view
- Phase 4 (workspace) เพิ่ม: entitlement token v2, IdP group → policy mapping (แบบ B)
- **Phase 4.5 (ใหม่, 3–4 วัน) — Data protection — ✅ DONE 2026-09-19** (`plan/archive/RESULT_P7_PHASE45.md`; exit ครบ; review อิสระ 2 รอบ)**:** `llm_data_policy` + provider allowlist, retention/purge job ของ `chat_history.result_data`, ลบตาม user (DSR), audit export, onboarding ไม่ส่ง sample ของคอลัมน์ต้องห้าม
  - **Exit:** source ที่ตั้ง `schema_only` → ตรวจ request ที่ออกไปยัง provider ไม่มีค่าจากผลลัพธ์เลย (test ดักที่ provider layer); purge job ลบ `result_data` เกินกำหนดจริง
- Phase 7 (ภายนอก) ต้องมีก่อนเปิด: DPA template, ROPA, breach runbook, connector agent หรือ private deployment

## 7. Risks / trade-offs

| เรื่อง | ผลกระทบ | ทางออก |
|---|---|---|
| CSV scan ทุก query ช้า | latency | Phase 1 วัดจริงก่อน; ถ้าเกินเกณฑ์ → cache เป็น Parquet ต่อ manifest sha256 (ยังนับเป็น zero-import เพราะ invalidate อัตโนมัติ) |
| ต้นทางไม่มี contract | knowledge ต่ำ ตอบผิด | fallback เป็น auto-onboarding (context_onboarding ผ่าน adapter) + ติดป้ายว่า "ความแม่นยำยังไม่ผ่าน eval" |
| AI server เข้าถึงที่เก็บข้อมูลไม่ได้ | ใช้ไม่ได้เลย | Phase 0 ต้องตัดสินเรื่องที่ตั้งข้อมูลก่อน |
| คำถามข้ามโดเมนตอบผิดแบบมั่นใจ | ความน่าเชื่อถือ | Phase 5 เริ่มจาก context ที่รวมมาแล้ว; orchestrator ต้องแสดงที่มาของแต่ละตัวเลข — ✅ ทำแล้ว (ที่มา + งวดต่อส่วน, คำนวณใน code); เหลือ: คำถาม "ทั้งบริษัท" ที่ `feed_ebt` ตอบด้วยยอด 2 สายงานขาย (รอ contract) |
| สองโหมด (import + file) อยู่คู่กัน | ดูแลยาก | ตั้งเกณฑ์เลิกโหมด import หลัง Phase 2 ผ่าน 2 รอบปิดงวด |

## 8. ผลต่อ NT-Report (ผู้เรียกรายแรก)

NT-Report ไม่ต้อง import อะไรเข้า AI อีก หน้าที่เหลือแค่:
1. publish DataFeed ไปที่ที่ AI อ่านได้ (ตาม Phase 0) — `run_all --feed` ทำอยู่แล้ว
2. ลงทะเบียน 4 source + contract ครั้งเดียว, ได้ API key ที่เห็นเฉพาะ `feed_*`
3. เพิ่ม **assistant config ต่อรายงาน/report_type** (contexts + scope template, ดู §6.4) — ไม่มี config = ไม่แสดงปุ่ม; แทนที่ `ASSISTANT_CONTEXT_MAP` ใน env ที่ map ได้แค่ report_type → context เดียว
4. PB hook (`pocketbase_0/pb_hooks/assistant.pb.js`) สร้าง entitlement จาก `canAccessReport` + config ข้อ 3 → ส่ง `contexts` + `scope` (อย่างน้อย `year_month` = งวดรายงาน, เพิ่ม `org_code` สำหรับรายงานจำกัดหน่วยงาน) แล้วแสดง `data_as_of`; ภายหลังเปลี่ยนเป็น entitlement token v2 (§6.3)
5. งานค้างฝั่ง portal ที่แก้ได้เลยโดยไม่รอแผนนี้: audit action `assistant_ask` ยังไม่อยู่ใน select values ของ `audit_logs.action` (เขียน audit ไม่ติด), field `period` ≠ `year_month`

## 9. ความสัมพันธ์กับ Plan 6 (SaaS)

| Plan 6 | ในแผนนี้ |
|---|---|
| Model A (API as a Service) | = Phase 1–4 (ทำจริง) |
| Model B (Upload CSV → SQLite) | **ไม่ทำเป็นค่าเริ่มต้น** — ขัดกับหลัก zero-import; file source ครอบคลุมกรณีนี้โดยชี้ไปที่ไฟล์แทน |
| Model C (Connect DB) | = SQL source ใน Phase 1 (adapter มีแล้ว) |
| Model D (MCP) | = Phase 6 |
| Config DB ต่อ tenant, billing, quota | เลื่อนไป Phase 7 — ตอนนี้ใช้ `workspace_id` ใน config DB เดียว พอสำหรับผู้ใช้ภายใน |

## 10. ไฟล์ที่ต้องอ่านก่อนเริ่ม
- `app/db/session.py`, `app/config.py` — business engine global
- `app/services/database_adapter.py`, `app/services/business_db.py` — adapter ที่มีอยู่
- `app/services/query_engine.py`, `app/services/context_router.py` — query path
- `app/services/context_onboarding.py` — onboarding (sqlite-only)
- `app/api/v1/query.py` — `SimpleQueryRequest` (`pinned_filters`, `source`)
- `scripts/datafeed/*` + `docs/DATAFEED_INTEGRATION.md` — contract → knowledge
- `docs/PORTAL_INTEGRATION.md`, `plan/archive/PLAN_F11_DASHBOARD_EMBED.md`
- NT-Report: `DataFeed/README.md`, `DataFeed/SPEC.md`, `DataFeed/contracts/*.yaml`

## 11. ประเด็นค้าง (Open items — อัปเดต 2026-09-18)

### 11.1 ต้องตัดสินใจก่อนเริ่ม (Phase 0)
| # | ประเด็น | ผู้ตัดสิน | ผลต่อแผน |
|---|---|---|---|
| D1 | AI server รันที่ไหน และอ่าน DataFeed ของ NT-Report ทางใด — ✅ **ตัดสิน 2026-09-18:** (ก) **เครื่องเดียวกัน — local path** (ใช้อยู่แล้ว) และ**ต้องออกแบบให้เพิ่มได้**: (ค) object storage S3/MinIO และ (ง) HTTPS + token สำหรับลูกค้าที่ไม่มี (ค) — ไม่เขียน code ล่วงหน้า (ดู §13) | เจ้าของโครงการ | §6.7, §13 |
| D2 | ใช้ DuckDB เป็น engine ของ file source — ✅ ใช้แล้ว (Phase 1; `duckdb==1.5.5`, `duckdb-engine==0.17.0` ติดตั้งทั้ง python3.10 และ 3.14) | ทีมพัฒนา | Phase 1 |
| D3 | ชื่อ field ขอบเขตข้อมูลใน `/api/v1/query` — ✅ **ตัดสิน 2026-09-18:** **A** — field ใหม่ `scope` = บังคับจริงที่ชั้น SQL (Phase 3), `pinned_filters` รับต่อแบบ log อย่างเดียวช่วงเปลี่ยนผ่าน แล้วค่อยเลิก; NT-Report เปลี่ยนไปส่ง `scope` เมื่อ Phase 3 พร้อม | ทีมพัฒนา | Phase 3, API contract กับ NT-Report |
| D4 | LLM ที่อนุญาตสำหรับข้อมูล confidential/personal — ✅ **ตัดสิน 2026-09-19: Matcha (NT Gateway) ใช้ได้** → source อ่อนไหวตั้ง `llm_provider_allowlist=["matcha"]` (code คุมชื่อ provider; gateway ส่งต่อไปโมเดลใดเป็นเรื่องของสัญญากับ gateway — DPO ยังต้องยืนยัน) | เจ้าของโครงการ + DPO | Phase 4.5 |
| D5 | ใครเป็นคนกำหนด data classification ต่อคอลัมน์ — ⏸ **ตัดสิน 2026-09-19: เลื่อน** — Phase 4.5 ทำ policy ต่อ source เท่านั้น ("ไม่ระบุ = confidential" จะเปลี่ยนพฤติกรรมทุก context ทันที); ทำเมื่อมี source ที่มีข้อมูลบุคคลจริง, ผู้กำหนดที่เสนอ = เจ้าของข้อมูลผ่าน contract | เจ้าของโครงการ | §6.6 ข้อ 1–2 (k ≥ 5, mask) รอข้อนี้ |
| D6 | เกณฑ์เลิกโหมด import (`import_datafeed.py`) — เสนอ: หลัง Phase 2 ผ่าน 2 รอบปิดงวด | เจ้าของโครงการ | §7 |
| D7 | จังหวะเปลี่ยนไป entitlement token v2 — เสนอ: เมื่อมีผู้เรียกรายที่ 2 หรือก่อน Phase 7 | เจ้าของโครงการ | §6.3 |
| D8 | รูปแบบให้บริการ: private deployment ต่อลูกค้า vs multi-tenant (API ร่วม) — ✅ **ตัดสินแล้ว 2026-09-18: แบบผสม** | เจ้าของโครงการ | §12 — Phase 4, Phase 7, Plan 6 |

**ค่า default ที่ Phase 1 ใช้ระหว่างรอ D1–D3 (2026-09-18 — ตอนนี้ตัดสินแล้ว ตรงกับที่ใช้):**
- D1 → file source = **local path ต่อ source** (`data_sources.root_path`) — ยังไม่ทำ S3/HTTPS; interface (`source_type` + adapter ต่อชนิด) เพิ่ม scheme อื่นได้ภายหลังโดยไม่มี code ล่วงหน้า
- D2 → **DuckDB** (`duckdb>=1.5`) + `duckdb-engine` (SQLAlchemy dialect ให้ SchemaService inspect view ได้)
- D3 → **ไม่แตะ** `pinned_filters` / `scope` (Phase 3)

### 11.2 งานฝั่ง NT-Report ที่ทำได้เลย (ไม่รอแผนนี้)
- [x] migration เพิ่ม `assistant_ask` ใน select values ของ `audit_logs.action` — ตอนนี้ `writeAudit` fail validation แบบเงียบ ไม่มี audit ของคำถามเลย — ✅ NT-Report `1440672`
- [x] `assistant.pb.js` ส่ง `pinned_filters.period` แต่ฝั่ง AI คาด `year_month` — แก้ชื่อให้ตรง — ✅ NT-Report `1440672`
- [ ] เอกสารรวมของ assistant ฝั่ง portal (ตอนนี้กระจายอยู่ใน `.env.example`, `DEPLOY_NOTES.md`, `CHANGELOG.md`)
- [ ] (หลัง Phase 3) assistant config ต่อรายงาน แทน `ASSISTANT_CONTEXT_MAP` — §8 ข้อ 3–4

### 11.3 งานค้างจาก F11 (อัปเดต 2026-09-20)
- [x] ออก API key จริงให้ portal — `nt-report-portal` ผูก workspace `nt-report`, 20/นาที 2,000/วัน (2026-09-20)
- [~] E2E ผ่าน PB: ฝั่ง AI ครบ (403 นอกสิทธิ, audit ครบทุกคำถาม, rate limit รายวัน **และรายนาทีผ่าน Redis**);
      ส่วนที่ต้องผ่าน PocketBase ยังไม่ทำ — เจ้าของเป็นผู้ใส่ `ASSISTANT_*` ใน `pocketbase_0/.env` + restart PB
      (process ที่รันอยู่เก่ากว่าการแก้ hook ของ 2026-09-20)
- [x] เทียบตัวเลข 10 คำถาม vs dashboard → `plan/archive/RESULT_F11.md` — **ไม่ผ่าน**: revenue 8 · expense 8 ·
      ebt 8 · sales 5 (ก่อนแก้ 4 / 3 / 4 / 3). ต้นเหตุหลักคือ scope 13–24 เดือนที่ไม่มีงวดยึด — แก้แล้ว
      (`308acb1`: prompt บอกขอบเขต + งวดอ้างอิง) ที่เหลือเป็นความรู้รายโดเมน ไม่ใช่เรื่อง scope อีก
- [ ] **ก่อนเปิดปุ่ม:** แก้ `mapUpstreamError` ฝั่ง hook (รหัส `source_unavailable` ไม่ match `/publish/i` อีกแล้ว),
      ปิดช่องว่างที่เหลือ 11 ข้อ แล้ววัดซ้ำ **มากกว่าหนึ่งรอบ** (เห็นความผันผวนของโมเดล ±1 ข้อ)

### 11.4 สถานะข้อมูล ณ วันที่เขียนแผน
- business DB ของ AI มีแค่ `feed_revenue` 202605 (import 2026-07-11) ขณะที่ DataFeed มี revenue/expense 202608, sales/ebt 202607 — ถ้าต้องการเปิดใช้ก่อน Phase 1 เสร็จ ต้อง import ด้วยมือ (โหมดเดิม) ไปก่อน
- **อัปเดต 2026-09-18 (Phase 2):** ลงทะเบียนครบ 4 โดเมนเป็น file source (revenue/expense 202608, sales/ebt 202607) — `feed_sales`/`feed_ebt` ปิดไว้ (`is_active=0`) จนกว่า contract จะมีกฎ actual/target และวิธีคำนวณ EBT
- **อัปเดต 2026-09-18 (Phase 1):** `feed_revenue` ผูกกับ source `datafeed_revenue` (DuckDB file) แล้ว → เห็น revenue **202608** โดยไม่ import (schema 2.0.0); ตาราง `feed_revenue_*` ใน `nt_fi_report.sqlite` ยังอยู่เป็น fallback (`register_file_source --legacy`) — expense/sales/ebt ยังไม่ลงทะเบียน (Phase 2)

### 11.5 ต้องตรวจทางเทคนิคระหว่างทำ
- [x] option ของ DuckDB สำหรับจำกัด path/ปิด external access และ lock config — ยืนยันกับ **1.5.5**: `allowed_paths` (ต้อง SET หลัง connect และก่อนปิด external access) + `enable_external_access=false` + `lock_configuration=true` ใช้ได้; **แต่ lock ไม่กัน table function `enable_logging()`** (ทำ process ล่ม/อ่าน SQL ผู้อื่นได้) → เพิ่ม query gate ที่ parse ด้วย DuckDB เอง (รายละเอียด `FIX_NOTES.md` Plan 7 Phase 1) ✅ Phase 1
- [x] latency ของ CSV scan เทียบ F10 (10.5s P50) — P50 6.1–6.3 s ไม่เกินเกณฑ์ → **ไม่ทำ Parquet cache** (ถ้าต้องการ: bundle มี `.parquet` + sha256 ใน manifest อยู่แล้ว อ่านตรงได้เลย เร็วกว่า CSV 50–100×) ✅ Phase 1
- [x] `PIIRedactingFormatter` เป็น regex — ✅ ประเมินแล้ว (Phase 4.5): **ไม่เพิ่ม regex** — regex รู้จักรูปแบบ (email/เบอร์/บัตร) ไม่รู้จักค่าธุรกิจ; ลดที่ต้นทางแทน (source ที่เข้ม: verifier/lookup ไม่ทำงาน = ไม่มี log ของค่า); ที่เหลือคือ literal ใน SQL ที่ log ระดับ INFO — ทบทวนพร้อม classification (D5)
- [x] ทุกจุดที่ส่งข้อมูลให้ provider — ✅ ไล่ครบ 15 จุด + จุดเก็บ/ส่งออก 17 จุด: `plan/archive/RESULT_P7_PHASE45.md` §1 (review อิสระเจอเพิ่ม 1: RAG/golden ที่สร้างจาก control totals)

### 11.7 ข้อค้างใหม่จาก Phase 1 (2026-09-18)
**รอเจ้าของตัดสิน:**
- [x] **Exit criterion value match 14/14** — ✅ ครบ 2026-09-18: NT-Report เพิ่มกฎ `ytd_point_in_time` (contract 2.0.1, `2b64841`) + AI regen knowledge → eval file source 14/14 สองรอบ (#64 เขียน `month = 5` แล้ว)
- [ ] merge branch `plan7-phase1` เข้า main (ยังไม่ push ตามคำสั่ง)
- [x] ยืนยัน D1–D3 ที่ใช้ค่า default (§11.1) + การเพิ่ม `duckdb-engine` — ตัดสินแล้ว 2026-09-18
- [x] **publish race** — ✅ ฝั่ง AI `820052e` (replay: ตอบผิดเงียบ 181 → 0) · ✅ ฝั่ง NT-Report code แล้ว (`7d639b0` versioned build + symlink `latest`) — replay layout ใหม่กับฝั่ง AI: 2,978 คำตอบถูก, **0 error, 0 ผิด** ระหว่างสลับ build ต่อเนื่อง · ⬜ เหลือ: NT-Report รัน publish จริงครั้งแรก (ย้าย `latest/` เข้า `builds/` + สร้าง symlink) — ฝั่ง AI ไม่ต้องลงทะเบียนใหม่ (resolver ตาม realpath เอง)
- [x] ⚠️ bug เดิม: `POST /admin/config/rebuild-keyword-index` ลบ keyword index ทิ้งหมด — แก้ในงานแยก `0f3aaa7` ซึ่ง commit อยู่บน branch `plan7-phase1` (ไม่ใช่งาน Plan 7) — ทำให้ value lookup ของ legacy context คืนค่าจริงแล้ว = พฤติกรรม legacy เปลี่ยน ตัดสินตอน merge ว่าจะแยก merge หรือไม่

**ส่งต่อ Phase 2+:**
- [x] runtime ตรวจ manifest ต่อ build (reconcile + sha256) + query cache ผูก build — `820052e` | [x] re-sync knowledge อัตโนมัติ (`38ab63d`) + `data_as_of` (`deb0a7e`) — Phase 2
- [x] ลงทะเบียน expense/sales/ebt (`a2b8568`) — sales/ebt ตอบเลขผิดความหมาย เพราะ contract ขาดกฎ → ✅ **ตัดสิน 2026-09-19: ทางเลือก A** (แก้ contract ที่ NT-Report; เจ้าของกำหนด **EBT = ยอดขาย − ค่าใช้จ่าย** — ยอดขาย = กลุ่ม `01.รายได้` ใน fact_ebt = รายได้ฐานยอดขาย ซึ่ง**ไม่เท่ากับ**รายได้ในรายงานรายได้ เช่น รวมยอดขายบัตร prepaid ไม่ได้คิดจาก usage อย่างเดียว) และไป Phase 3 ได้เลย — [x] NT-Report ทำตาม `plan/PROMPT_NT_REPORT_P7.md` แล้ว; ฝั่ง AI: `control_totals.filter` + total-only ใน gate/golden (`dfce5d5`) → `feed_sales` เปิด, eval 12/12 (2026-09-19)
- [x] **ebt ปิดแล้ว 2026-09-19:** เจ้าของเลือกมีทั้งสองฐาน → ebt 1.3.0 (`*_month` + สะสม) → 1.3.1 (`73ddc96`: สะสมเป็น `point_in_time`, กฎห้าม SUM/BETWEEN ข้ามงวด, สูตรรายสายงาน/ศูนย์ต้นทุน); ฝั่ง AI `c6e7cca`, `a458cda`, `ff34aab` → `feed_ebt` เปิด, eval 22/24 — ประวัติ: **ebt — รอเจ้าของตัดสิน (2026-09-19):** ebt 1.2.1 (`90fd787`) เปลี่ยน `fact_ebt_total_monthly` เป็นฐานรายงาน EBT (YTD, 2 สายงานขาย, ก.ค. 69 = +417.33 MB) ขัดกับ −1,088,133,452.03 ที่กำหนดไว้; AI ตอบยอดสะสมเป็น "ยอดเดือน" และตอบยอดรวมเมื่อถามรายสายงาน (main view = ตารางยอดรวม) → `feed_ebt` ปิดไว้ — ทางเลือก A/B/C ใน `plan/archive/RESULT_P7_PHASE2.md`
  - ✅ ตัดสินแล้ว (2026-09-19 บ่าย): มีทั้งสองฐาน — ebt **1.3.0** (`*_month` = รายเดือน, ไม่มี suffix = สะสม); ฝั่ง AI `c6e7cca`; eval **18/24** (SUM คอลัมน์สะสมข้ามงวด 4, ใช้คอลัมน์สะสมตอบรายเดือน 2) → ยังปิด รอ NT-Report เพิ่ม `agg: point_in_time` + กฎของตารางยอดรวม
- [x] NT-Report รัน publish แบบ atomic จริงแล้ว (ตรวจ 2026-09-19: `latest` → `builds/<id>`, manifest มี `build_id`) — ฝั่ง AI ไม่ได้ลงทะเบียนใหม่ revenue/expense; build ใหม่ 06:54 ถูกเห็นเอง
- [ ] schema เปลี่ยนแบบเพิ่ม/ลบคอลัมน์: knowledge re-sync เอง แต่ view (`source_tables`) ยังเป็นชุดคอลัมน์ตอนลงทะเบียน → ต้องรัน `register_file_source` ใหม่
- [ ] (ภายใต้ D8 แบบผสม: ไม่บังคับ — พิจารณาเมื่อ workspace ใน deployment เดียวมีความลับต่างระดับกันมาก หรือถ้าไปถึง Tier 3) พิจารณารัน SQL ของ file source **นอก process** (แบบ MCP subprocess ของ legacy) — DuckDB รันใน API process: bug/abort ของ DuckDB ในอนาคต (แบบ `enable_logging` ที่ปิดด้วย query gate แล้ว) จะล้มทั้ง API; gate ตรวจแล้วกับทุก vector ที่ reviewer เสนอ (`query()`, `json_execute_serialized_sql`, `FROM '/path'`, comment/quote tricks, subquery) — เหลือ scalar ที่ผ่านได้แค่ตัวอ่านอย่างเดียว/no-op (`current_setting`, `getvariable`, `write_log` ขณะ logging ปิด)
- [ ] tool-loop `get_sample_values`/`get_table_stats` บน DuckDB (ตอนนี้ fail closed)
- [x] admin endpoint (schema browser, onboarding, sync-brain DDL) เห็น file source แล้ว — Phase 4d `5428bb3` (keyword index แก้ไปก่อนแล้ว `0f3aaa7`); ฝั่ง UI (frontend-admin) ของ workspaces/sources ยังไม่ทำ
- [ ] `/chat/train` validate SQL ตาม source ของ context
- [ ] ลบ `.source_cache/*.duckdb` ของ fingerprint เก่า

### 11.6 ต้องทบทวนโดยฝ่ายอื่น
- [ ] DPO / ฝ่ายกฎหมาย ทบทวน §6.6 ข้อ 8 (controller/processor, DPA, ROPA ม.40, แจ้งเหตุ ม.37(4), ส่งข้อมูลต่างประเทศ ม.28–29) — **บังคับก่อน Phase 7**
- [ ] IT/security ทบทวนรูปแบบการเชื่อมต่อลูกค้า (§6.5) และ connector agent

## 12. รูปแบบการให้บริการ (Deployment model) — ตัดสิน 2026-09-18: แบบผสม (D8)

| กลุ่ม | รูปแบบ | ใครดูแล | แยกกันด้วยอะไร |
|---|---|---|---|
| **Tier 1 — หน่วยงานภายใน NT** | deployment เดียวของ NT แบ่งเป็นหลาย **workspace** (เช่น `nt-report`, `finance`) | NT | workspace_id + API key ที่จำกัด context + Chroma ต่อ workspace (Phase 4) — process/DB ใช้ร่วม เพราะอยู่ในองค์กรเดียวกัน |
| **Tier 2 — ลูกค้าภายนอก** | **private deployment ต่อราย** — ระบบทั้งชุดแยก (API, web, MCP, app/config DB, Chroma, cache) | 2a: NT host ให้ (VM/namespace แยกต่อราย) · 2b: ติดตั้งในเครือข่ายลูกค้า (ข้อมูลออกนอกองค์กรไม่ได้) | แยกทุกอย่าง: ข้อมูล, ประวัติคำถาม, knowledge/golden, key, credential, LLM |
| **Tier 3 — multi-tenant ใช้ API ร่วม (Plan 6)** | ยังไม่ทำ | — | **trigger:** มีลูกค้าภายนอกรายเล็กจำนวนมาก (~10–20 ราย) ที่ต้องการสมัครใช้เอง จนการดูแลหลาย deployment เป็นคอขวด |

**หลักการ**
- **โค้ดชุดเดียว image เดียว** ทุก deployment — ต่างกันแค่ config (env + config.db); ห้ามมี branch/โค้ดเฉพาะลูกค้า
- ข้าม deployment ใช้ร่วมได้เฉพาะ: image, release, migration script, เอกสาร/runbook และ metrics สุขภาพระบบ (latency/error) — **ห้ามมีคำถาม, SQL หรือข้อมูลของลูกค้าออกมานอก deployment**
- ใน deployment ของลูกค้าเองก็แบ่ง workspace ได้ (หน่วยงานของลูกค้า) ด้วยกลไก Phase 4 เดียวกัน
- LLM เลือกต่อ deployment ตามสัญญา/D4 (LLM ในประเทศ, gateway ของลูกค้า หรือ provider แบบ zero data retention)
- เอกสาร PDPA ต่อราย (DPA, ROPA, breach process — §6.6 ข้อ 8) ขอบเขตอยู่ที่ deployment ของลูกค้านั้น

**ผลต่อ phase:** Phase 1–3 ไม่เปลี่ยน · Phase 4 = workspace ภายใน deployment (query worker ไม่บังคับ) · Phase 4.5 = policy ต่อ deployment + ต่อ workspace · Phase 7 = packaging ด้านล่าง · Plan 6 = Tier 3 (เลื่อนจนถึง trigger)

**งาน packaging สำหรับ Tier 2 (Phase 7) — ยังไม่มีใน repo (ไม่มี Dockerfile/compose)**
- [ ] Docker image เดียว (API + frontend + MCP servers) มี version + docker-compose (หรือ Helm) ต่อ deployment
- [ ] env template + secrets (LLM keys, credential ของ source ลูกค้า) — ไม่ฝังใน image
- [ ] bootstrap deployment ใหม่: init DB + `scripts/migrate_*.py` (รันซ้ำได้อยู่แล้ว) + สร้าง admin + context แรก + ลงทะเบียน source
- [ ] backup/restore ต่อ deployment, upgrade หนึ่งคำสั่งต่อราย + rollback
- [ ] ตัวเลือก Postgres สำหรับ app/config DB เมื่อใช้งานหนัก
- [ ] monitoring รวมศูนย์ (เฉพาะ health/latency/error) + ทะเบียน deployment (ลูกค้า, version, ผู้ติดต่อ, วันหมดสัญญา)
- [ ] 2b on-prem: runbook ติดตั้งในเครือข่ายลูกค้า + วิธีส่ง update แบบ offline

## 13. แหล่งไฟล์ชนิดอื่น (D1: ต้องเพิ่มได้ภายหลัง — ยังไม่ทำ)

ตอนนี้มีแค่ `duckdb_file` = local path (D1 ก) — เมื่อมีลูกค้า/deployment ที่ต้องการ ให้เพิ่มเป็น `source_type` ใหม่
ข้างเคียงกัน (ไม่แก้ของเดิม) โดยคงสัญญาเดียวกับ local: **อ่านเฉพาะ build ที่ตรวจแล้ว, pin ต่อ build, ปฏิเสธชัด ๆ ระหว่าง publish**

| | (ก) local path — มีแล้ว | (ค) S3 / MinIO | (ง) HTTPS + token |
|---|---|---|---|
| ชี้ build ล่าสุด | symlink `latest` → `builds/<id>` (NT-Report `7d639b0`) | ไม่มี symlink → pointer object เช่น `latest.json` = `{build_id}` เขียนหลัง build ครบ | pointer เดียวกันผ่าน URL |
| pin ต่อ build | realpath ใน fingerprint ของ resolver | build_id จาก pointer ใน fingerprint | เหมือน (ค) |
| ตรวจ build | manifest + sha256 ทุกไฟล์ (~1 วินาที/publish) | manifest + ขนาด/ETag ต่อ object (hash ทั้งก้อนแพงกว่าเพราะต้องดาวน์โหลด) | เหมือน (ค) — ต้องมี endpoint ให้ขนาด/ETag |
| ตรวจต่อ query | stat inode/size/mtime | ไม่ต้อง — prefix ของ build immutable; อ่าน pointer เป็นระยะ | เหมือน (ค) |
| DuckDB | ปิด extension ทั้งหมด | ต้องโหลด `httpfs` + secret (credential) **ก่อน** `lock_configuration`; `allowed_paths`/`allowed_directories` เป็น prefix `s3://bucket/<build>/` | `httpfs` + header token; allow เฉพาะ prefix ของ build |
| รูปแบบไฟล์ | CSV (ผ่านเกณฑ์) | **Parquet** (CSV ผ่านเครือข่ายช้า; bundle มี `.parquet` + sha อยู่แล้ว) | Parquet |
| ฝั่ง NT-Report/ลูกค้า | — | publish ขึ้น bucket + เขียน pointer ท้ายสุด; key read-only ต่อ prefix | ให้บริการไฟล์ผ่าน HTTPS + token + range request |

จุดที่ code ต้องแยกเมื่อทำจริง: การหา root/build (symlink vs pointer), การตรวจ build (sha vs ETag), การตั้งค่า DuckDB ก่อน lock —
ส่วน view/query gate/validator/resolver/cache ใช้ร่วมกันได้ทั้งหมด
