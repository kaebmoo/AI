# RESULT — ความรู้ที่ไม่ผูก context ถึงเฉพาะ context ที่มีคอลัมน์ที่มันอ้าง (2026-10-22)

**สถานะ:** ✅ **ขึ้นของจริงแล้ว 2026-10-22 16:26** (นำเข้า working tree ของ `main` → `uvicorn --reload` โหลดเอง) · **ยังไม่ commit** (รอเจ้าของสั่ง)
**ที่มา:** คำถาม "ebt ของ น่าน" จาก NT-Report กรองผิดชั้น + เจ้าของสั่ง "ทำให้ general รองรับข้อมูลใดก็ได้" (2026-10-22)
**ต่อเนื่อง (§9, ขึ้นของจริง 2026-10-23 22:18):** scope หลายชื่อต่อ key + สูตร EBT ทุกระดับหน่วยงาน (contract expense 1.2.4 / ebt 1.4.4) — คำถามน่านทั้ง 4 โดเมนตอบถูก, portal 41/38 → **42/43**
**ต่อเนื่อง (§8, ขึ้นของจริง 18:04):** keyword index จากทุกตารางของ context + ค่าที่ค้นเจอถึง pass 1 + retry ผล NULL — portal 36/37 → **43** จาก 55, legacy 8 → 9/37
**แผน:** `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md` — งานนี้เป็นชิ้นที่อ่านอย่างเดียวก่อน 8.2; ส่วนอัตโนมัติ (เติมความรู้เมื่อข้อมูลใหม่เข้า) ยังเป็นงานของ 8.2 (§7 ข้างล่าง)

| | ก่อน | หลัง |
|---|---|---|
| คำถาม portal 5 ชุด 55 ข้อ — รอบ 1 | 35/55 | **39/55** |
| คำถาม portal 5 ชุด 55 ข้อ — รอบ 2 | 32/55 | **36/55** |
| legacy eval (`run_eval.py --legacy`, 37 ข้อที่ให้คะแนนได้) | 10/37 | **10/37 — 0 ข้อเปลี่ยนคะแนน** |
| system prompt ของ `feed_ebt` | 37,906 ตัวอักษร | **20,613** |
| การอ้างคอลัมน์ที่ context นั้นไม่มี ใน prompt ของ `feed_ebt` | 363 ครั้ง | **98** |
| pytest (สำเนา DB, python 3.14) | — | **1233 passed, 3 skipped** · ruff ผ่าน |

---

## 1. ปัญหา + หลักฐาน

- `schema_business_rules` ที่ `table_name` ว่าง / `ALL` มี **50 แถว** และ `schema_semantic_mapping` ที่ `context_name` NULL มี **188 แถว** — เขียนให้ view ของ legacy
  (`revenue_search` ฯลฯ) แต่ถึง prompt ของ**ทุก** context รวม `feed_*` ที่ไม่มีคอลัมน์เหล่านั้นเลย
- prompt ของ `feed_ebt` ยาว 37,906 ตัวอักษร มี `department_abbr` 103 ครั้ง และกฎ "จังหวัดให้ใช้ `"section"`" (id 13) — ไม่มีตารางใดของ `feed_ebt` มีคอลัมน์ทั้งสอง
- ผลจริง: "ebt ของ น่าน" ผ่าน NT-Report → โมเดลกรองตามกฎของ legacy (ชั้นผิด) → 0 แถว → ช่องทางขาออกส่ง SQL กลับไปในข้อความ
  (ตัวรั่ว SQL ปิดแล้ววันเดียวกัน — `outbound.carries_data`, §6)

## 2. การออกแบบ — general, อ่านจาก registry, ไม่แก้แถว

`app/services/schema/knowledge_scope.py`:

- **กฎข้อเดียว:** ความรู้ที่ไม่ผูก context ถึง context หนึ่ง **ยกเว้น** มันอ้างคอลัมน์ที่ "มีใน context อื่น แต่ไม่มีใน context นี้"
  ความรู้ที่ไม่อ้างคอลัมน์ใดเลย ("สร้าง SQL เพียง query เดียว") ถึงทุก context เหมือนเดิม
- **ทั้งสองฝั่งอ่านจาก registry** ไม่มีชื่อ context / ตาราง / คอลัมน์ใน code:
  file source (`duckdb_file`) = คอลัมน์ของ**ทุกตาราง**ใน `source_tables` ของ source นั้น (ไม่ใช่แค่ main view — คำถามข้ามตารางของ source เดียวกันได้),
  legacy = คอลัมน์ของ view จาก inspector + `schema_metadata` ของ view → **data set ที่ลงทะเบียนพรุ่งนี้ก็เข้าเกณฑ์เอง**
- **ตัวที่นับว่าเป็นชื่อคอลัมน์ (`named`)** = คำในเครื่องหมายคำพูด (`"section"`, `"กลุ่มธุรกิจ"`) หรือคำที่มีขีดล่าง (`department_abbr`, `time_key`) + `target_column` ของ mapping
  - **ทำไมไม่นับคำเดี่ยว:** รุ่นแรกนับทุก identifier → ตัดกฎ global ของ `revenue` เอง 24 ใน 50 ข้อ เพราะคำอย่าง `GROUP BY`, "division by zero",
    placeholder `AMOUNT` / `YEAR` / `table` เป็นคำก่อนเป็นชื่อคอลัมน์ — รุ่นนี้ `revenue` เก็บ 45/50
  - **เพดานที่รู้ (`ponytail:` ใน code):** กฎที่อ้างคอลัมน์ของ context อื่นเป็นคำเดี่ยวไม่มีเครื่องหมายคำพูด ยังถึงทุก context เหมือนเดิม —
    ทางขยาย: แยก column reference จาก SQL ตัวอย่างของกฎด้วย parser (`database_adapter.check_select` ใช้ `json_serialize_sql` อยู่แล้ว)
- **อ่านอย่างเดียว:** ไม่มีแถวใดถูกแก้ ความรู้ของคน (`manual` / `declared`) ไม่ถูกเขียนทับ แค่ไม่ถูกแสดงที่ที่คอลัมน์ของมันไม่มี
- **fail open:** context ไม่รู้จัก / registry อ่านไม่ได้ / ไม่รู้คอลัมน์ของ context = เก็บทุกแถว (พฤติกรรมเดิม)
- กฎที่**คน**ผูกตาราง (`table_name` = ตารางจริง) แสดงที่ที่ผูกไว้เสมอ ไม่ผ่านตัวกรอง
- กฎทั้งหมดของ context ถูกกรองออก → ส่วน "business rules" **ว่าง** ไม่ใช่ข้อความ fallback ที่ hardcode (ซึ่งพูดถึงคอลัมน์ `DATE` แบบ Unix ms ที่ feed ไม่มี)
- ไม่ต้องมี field dialect: กฎของ SQLite ที่ถึง file source ใช้กับ DuckDB ได้

ตัวอ่านที่ผ่านตัวนี้: `prompt_builder.scoped_rules` (ใช้ใน `build_business_rules_text` + `SchemaService.build_instruction_rules_text`)
และ `prompt_builder.build_semantic_mapping_text` — **ตัวอ่านใหม่ที่ส่ง rules / mappings ให้ LLM ต้องผ่านตัวนี้** (บันทึกใน CLAUDE.md / AGENTS.md)

## 3. ไฟล์

| ไฟล์ | |
|---|---|
| `app/services/schema/knowledge_scope.py` | ใหม่ — `named`, `ColumnScope.applies`, `scope_for` |
| `app/services/schema/prompt_builder.py` | `scoped_rules`; `build_business_rules_text` / `build_semantic_mapping_text` รับ `context_name`; ทุกจุดเรียกส่ง context |
| `app/services/schema/service.py` | `build_instruction_rules_text(main_view, context_name)`, `build_business_rules_text(table_name, context_name)` |
| `tests/unit/test_knowledge_scope.py` | ใหม่ — registry จำลอง: legacy view + file source สองตาราง, fail open, ส่วนว่างแทน fallback |
| `tests/unit/test_prompt_date_instructions.py`, `test_schema_service_prompt_builder.py` | test double รับ `context_name=None` |

## 4. ผลวัด (บนสำเนา — ไม่แตะของจริง)

**วิธี:** worktree สองชุดจาก working tree เดียวกัน (ก่อน = snapshot, หลัง = + patch) · server ซ้อม port 8001 / 8002 บนสำเนา `config.db` / `app.db` / Chroma
· key ซ้อม id 5 (มีเฉพาะในสำเนา) · `scripts/eval/run_portal_questions.py` 5 ชุด × 2 รอบต่อฝั่ง · legacy `run_eval.py --legacy` ด้วย `venv/bin/python` (3.10, มี RAG)

### 4.1 ขนาด prompt (system prompt ของ matcha, `rag_enabled`)

| context | ก่อน | หลัง | อ้างคอลัมน์ที่ไม่มี: ก่อน → หลัง |
|---|---:|---:|---|
| revenue | 36,415 | 34,852 | 98 → 75 |
| expense | 32,802 | 27,660 | 139 → 60 |
| transfer price | 33,576 | 16,866 | 331 → 72 |
| pl_costtype | 46,126 | 31,882 | 389 → 168 |
| feed_revenue | 37,196 | 30,311 | 137 → 54 |
| feed_expense | 36,101 | 18,950 | 390 → 130 |
| feed_sales | 36,133 | 22,334 | 334 → 122 |
| feed_ebt | 37,906 | 20,613 | 363 → 98 |

ที่ยังเหลือ = ตัวอย่าง RAG / golden ที่อ้างคอลัมน์ของ context อื่น + คำเดี่ยว (§2 เพดาน)

### 4.2 คำถาม portal — ถูกครบ (ตัวเลข + ยอดในข้อความ + ปี + ฐาน)

| ชุด | ก่อน r1 | หลัง r1 | ก่อน r2 | หลัง r2 |
|---|---:|---:|---:|---:|
| คำถามจริง (15) | 8 | 9 | 7 | 7 |
| revenue (10) | 8 | 9 | 7 | 9 |
| expense (10) | 5 | 5 | 5 | 5 |
| sales (10) | 7 | 9 | 8 | 9 |
| ebt (10) | 7 | 7 | 5 | 6 |
| **รวม (55)** | **35** | **39** | **32** | **36** |

ทีละข้อ (ข้อที่ผลไม่เท่ากันทั้ง 4 รอบ):

| ข้อ | ก่อน r1 / r2 | หลัง r1 / r2 | อ่านว่า |
|---|---|---|---|
| revenue P07 "Digital กับ ICT Solution รวมกัน" | ✗ ✗ | ✓ ✓ | ดีขึ้นจริง |
| sales P07 "กันยายนเทียบสิงหาคม" | ✗ ✓ | ✓ ✓ | ดีขึ้น |
| sales P02 "สะสม ม.ค.–ก.ย." | ✗ ✓ | ✓ ✓ | ดีขึ้น |
| คำถามจริง P07 "บริการ 102020019 ปี 69" | ✗ ✓ | ✓ ✓ | ดีขึ้น |
| revenue P02, คำถามจริง P05, ebt P03 | ✓ ✗ | ✓ ✓ | ฝั่งก่อนพลาดหนึ่งรอบ |
| คำถามจริง P13 "cctv รายเดือน" | ✓ ✗ | ✗ ✗ | ทั้งสองฝั่งในรอบ 2 ได้ SQL แบบเดียวกัน (ยอดสะสมแถวเดียวแทนรายเดือน) — ความแปรปรวนของ LLM |
| คำถามจริง P09 "บริการ 10 อันดับแรก" | ✓ ✓ | ✓ ✗ | รอบ 2 SUM ข้ามช่วง 2025–2026 ของ scope — เรื่องงวด ไม่เกี่ยวกับตัวกรองนี้ |
| ebt P04 "EBT Margin สะสม" | ✓ ✗ | ✓ ✗ | พลาดทั้งสองฝั่งในรอบ 2; ฝั่งหลังเติม `division LIKE '%สายงาน%'` จาก mapping id 57 (§7 ข้อ 2) |
| sales P06 "Digital", P08, คำถามจริง P10 | สลับไปมา | สลับไปมา | ไม่มีทิศทาง |

**ไม่มีข้อใดที่ผิดทั้งสองรอบหลังแก้ แต่ถูกทั้งสองรอบก่อนแก้** · รวมสองรอบ ก่อน 67/110 → หลัง 75/110

### 4.3 legacy eval

ก่อน 10/37 = 0.2703 · หลัง 10/37 = 0.2703 · ข้อเดียวที่สถานะเปลี่ยน: #2 `mismatch` → `generation_failed` (ผิดทั้งสองฝั่ง)

## 5. ขึ้นของจริง

- นำ patch 6 ไฟล์เข้า working tree ของ `main` 16:26 — ตรงกับชุดที่วัดทุกไบต์ (`cmp`) · server จริง (`--reload`) โหลดใหม่ ตอบ HTTP 200
- ตรวจบน config จริงหลังขึ้น (อ่านอย่างเดียว): กฎ id 13 "ใช้ section สำหรับจังหวัด" และ id 14 "ไม่มี column province" **ไม่ถึง** `feed_ebt` แล้ว แต่**ยังถึง** `revenue`
- pytest บนสำเนา DB: **1233 passed, 3 skipped** · `ruff check app mcp_servers --select E9,F63,F7,F82` ผ่าน
- ถอยกลับ: ลบ `knowledge_scope.py` + `git checkout` สามไฟล์ใน §3 (ไม่มี migration, ไม่มีแถวถูกแก้)

## 6. งานอื่นที่ขึ้นในวันเดียวกัน (อยู่ใน working tree ของ `main` เช่นกัน — ยังไม่ commit)

- **งวดอ้างอิงเมื่อไม่มี scope** (chat / Telegram): file source = `period` ของ manifest, legacy = MAX(ปี×100+เดือน) จาก view (`data_sources.legacy_data_period`) → `request_data_period`
- **ตัวกันยอดสะสม:** `hybrid_flow.cumulative_sum_error()` ปฏิเสธ SUM คอลัมน์สะสมข้ามงวด แล้ว retry
- **chat บอกแหล่งที่ตอบ:** `source` ใน response + ปุ่มถามซ้ำจาก context อื่น; `context_mismatch` + `request_prompt_note` ทุกขั้นรวมขั้นอธิบาย
- **ไม่มีข้อมูลของงวด:** ข้อความบอกงวดล่าสุดที่มี (`thai_year.period_th`)
- **SQL รั่วไป portal เมื่อผลมีแต่แถว NULL:** `outbound.carries_data` ใช้ร่วมใน `safe_answer` และ `hybrid_flow.is_empty_result`
- **admin web ไม่ force logout เมื่อ 401:** interceptor บน instance `api` และ `axios` ส่วนกลาง (`frontend-admin/src/services/api.ts`)
- **startup script:** `start_services.sh` (start / stop / status / setup; Redis เริ่มเองแยก) + `.vscode/tasks.json`

## 7. ที่ยังค้าง

1. **ความรู้อัตโนมัติเมื่อมีข้อมูลใหม่ (Plan 8.2)** — เจ้าของตัดสิน 2026-10-22: ระบบต้องเติมความรู้เองเมื่อข้อมูลใหม่เข้า, ปุ่มใน admin web มีไว้ซ่อมแบบ manual —
   สถานะเครื่องมือและขั้นที่เสนอ: `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md` §2.1
2. **mapping id 57 "สายงาน" → `DIVISION LIKE '%สายงาน%'`** (global) — ถึง `feed_ebt` ถูกต้องตามกฎ เพราะ `feed_ebt` มี `division` จริง แต่ตัว mapping จับ*คำทั่วไป*
   ("สายงานไหน…" = ชั้นของหน่วยงาน ไม่ใช่ค่า) → ebt P04 รอบ 2 เติมตัวกรองนี้ — เป็นความรู้ของคน ต้องให้ admin ตัดสิน (ปิด / ผูก context / แก้เงื่อนไข)
3. ~~ต้นเหตุของ "ebt ของ น่าน"~~ → แก้แล้ววันเดียวกัน (§8)
4. เพดานคำเดี่ยว (§2) — ทำเมื่อพบกฎจริงที่อ้างคอลัมน์ของ context อื่นแบบไม่มีเครื่องหมายคำพูดแล้วทำให้ตอบผิด
5. นอกขอบเขต (แจ้งเจ้าของแล้ว): ปิด `gpt-5-mini` ใน Admin → Models (matcha ตอบ 403) · คำอธิบายของ `pl_costtype` ยังเขียน "ปี 2567, 2568" ขณะที่ข้อมูลถึง 2569/02

## 8. ต่อเนื่อง: ค่าจริงจากทุกตารางของ context — ต้นเหตุของ "น่าน" (2026-10-22 เย็น)

**อาการ (หลังขึ้น §5):** "ebt ของ น่าน" (chat, audit #369) และ "ค่าใช้จ่ายของน่าน" (portal, #370) ยังได้ 0 แถว — กฎผิดชั้นหายแล้ว แต่โมเดลยังเดาคอลัมน์:
`division LIKE '%น่าน%'` / `cost_center LIKE '%น่าน%'` / `geo_region_broad` (sales) / `division_name` (revenue)

**ต้นเหตุ (สามชั้น):**
1. `keyword_value_index` สร้างจาก **main view เท่านั้น** — "น่าน" อยู่ที่ `feed_ebt_fact_ebt.sub_unit(_fname)`, `feed_expense_dim_org_snapshot.sub_unit_fname`,
   `feed_revenue_fact_org_*.sub_unit_name` — ไม่ใช่ตารางหลักของ context ใด (`feed_ebt` มี 0 แถวใน index) → ระบบไม่รู้จักคำนี้เลย
2. **pass 1 ไม่เคยเห็น value lookup** — pass 1 เป็นที่เลือกคอลัมน์ของ filter แต่ได้แค่รายชื่อคอลัมน์ของตารางอื่น (`intent_table_hint`);
   pass 2 เห็น match เฉพาะคอลัมน์ที่ pass 1 เลือกแล้ว → sales มี "น่าน" ใน**ตารางหลัก**อยู่แล้ว (`sub_unit_fname`) ก็ยังตอบผิด
3. ข้อความ "Actual Values Found" บอกคอลัมน์ ไม่บอกตาราง

**แก้ (code — general ไม่มีชื่อ context / ตาราง / คอลัมน์):**
| ไฟล์ | |
|---|---|
| `schema/keyword_index.py` | `context_tables` + `build_context_index`: main view + ทุกตารางของ file source (legacy = view เดียว); ลบแถวของตารางที่ context ไม่มีแล้ว; **ไม่ index คอลัมน์เวลา** (`is_time_column`) — ตารางที่มีแต่คอลัมน์เวลา = ล้าง |
| `api/v1/admin/config.py` | ปุ่ม rebuild ใช้ `build_context_index` |
| `ai/hierarchy_context.py` | ค้น 20 แล้วตัดเหลือ 5 ต่อคำ: ตารางหลักมีค่านั้น → ใช้ตารางหลักเท่านั้น; ค่าที่อยู่เฉพาะตารางอื่น → `other_table` + ข้อความ "ของตาราง `t` (ไม่มีในตารางหลัก)" |
| `ai/hybrid_flow.py` | `value_note` → pass 1 (สรุปต่อคอลัมน์ + จำนวนค่า, ไม่ส่งคอลัมน์เวลา); `null_arithmetic_error` / `zeros_after_null_retry` (ด้านล่าง) |
| `tests/unit/test_value_lookup_tables.py` | ใหม่ — 5 test |

**สิ่งที่ลองแล้วทิ้ง (วัดแล้ว):**
- *note ใน pass 1 แบบรายค่า* — "แบบ" ตรง 15 ค่า, "CCTV" ตรงหลายสินค้า → real P15 ทิ้ง SUM (✓✓ → ✗✗) → เปลี่ยนเป็นสรุปต่อคอลัมน์ "`product_name = 'บริการ CCTV' (+N ค่า)`" → P15 กลับมา
- *index คอลัมน์เวลา* — `fact_ebt.month_year_th = 'กันยายน 2569'` → pass 1 กรองงวดเป็นข้อความบนตารางอื่น → ตัวกัน dropped-filter ปฏิเสธ SQL ที่ถูก 4 ครั้ง → ebt P03 query_failed
- *กฎ `SQL_SAFE_SUM_ARITHMETIC` (COALESCE(SUM(...),0)) เป็น business rule* — แก้ NULL ของ "ebt ของ น่าน" ได้ แต่ ebt P03/P04 ผิด **3/3** (ไม่มีกฎ: ถูก 3/3) ทั้งข้อความยาวและแบบแคบ
  → ไม่ใส่ในของจริง; แทนด้วย **ตัวกันที่ผลลัพธ์**: แถวเดียวที่เป็น NULL ทั้งแถวจาก SQL ที่มี aggregate ≥ 2 → retry ครั้งเดียวพร้อมคำแนะนำ COALESCE;
  ผลหลัง retry เป็น 0 ล้วน = คืนแถว NULL (ตอบ "ไม่มีข้อมูล" และช่องทางขาออกยังกันข้อความที่มี SQL ได้) — คำถามที่ได้ตัวเลขไม่ผ่านตัวนี้เลย
  (ในชุดวัดไม่มีคำตอบใดเข้าเงื่อนไข จึงไม่กระทบตัวเลขข้างล่าง)

**วัด (สำเนา, server ซ้อม port 8001–8004, key ซ้อม):**

| ชุด | ก่อน r1 | ก่อน r2 | v1 (มีกฎ, note รายค่า) r1 / r2 | v2 (มีกฎ) r1 / r2 | **ที่ขึ้นจริง** |
|---|---:|---:|---|---|---:|
| คำถามจริง (15) | 9 | 8 | 10 / 9 | 10 / 10 | **10** |
| revenue (10) | 9 | 9 | 8 / 9 | 9 / 9 | **9** |
| expense (10) | 5 | 5 | 9 / 9 | 10 / 10 | **9** |
| sales (10) | 7 | 8 | 9 / 9 | 8 / 9 | **8** |
| ebt (10) | 6 | 7 | 5 / 5 | 5 / 5 | **7** |
| **รวม (55)** | **36** | **37** | 41 / 41 | 42 / 43 | **43** |
| legacy (37) | 8 | — | 7 | 8 | **9** (#33 ✗→✓, #23 → value_match, #1 ผิดทั้งสองฝั่ง) |

ดีขึ้นทุกรอบ: expense P06/P07/P09/P10 (ชื่อกลุ่มค่าใช้จ่ายเป็นค่าจริงที่ pass 1 เห็น), sales P06 · ไม่มีข้อที่ถูกสองรอบก่อนแก้แล้วผิดในรอบที่ขึ้นจริง

**คำถาม "น่าน" (สำเนา → ของจริงใช้ code + index ชุดเดียวกัน):**

| | ก่อน | หลัง | ค่าที่ถูก (อ่านจากไฟล์) |
|---|---|---|---|
| revenue | NULL (`division_name`) | **88,204,263.33** (`fact_org_monthly.sub_unit_name`) | 88,204,263.33 สะสม ก.ย. 69 ✓ |
| sales | NULL (`geo_region_broad`) | **96,405,275.59** (`sub_unit_fname`) | 96,405,275.59 actual ม.ค.–ก.ย. 69 ✓ |
| ebt | NULL (`division`) | `fact_ebt.sub_unit` ถูกตาราง ถูกคอลัมน์ — ได้ 24,410,200.83 (สองรอบที่มีกฎ) / 25,083,533.73 / NULL | สูตร contract: 95,820,451.26 − 673,332.90 − 70,736,917.53 = **24,410,200.83** |
| expense | 0 แถว (`cost_center`) | โมเดลเขียน JOIN `fact_expense` × `dim_org_snapshot` **ถูก** แต่ scope ปฏิเสธตาราง | 70,736,917.53 ม.ค.–ก.ย. 69 |

**ขึ้นของจริง 18:04:** backup `~/nt-ai-backups/k2-value-index-20261022-180419/config.db` (quick_check ok) → `build_context_index` ของ `feed_*` บน config จริง
(feed_revenue 16 ตาราง 35,122 แถว · feed_expense 7 / 13,795 · feed_sales 4 / 9,808 · feed_ebt 2 / 4,569; legacy ไม่แตะ) → นำ code เข้า working tree
(ตรงกับชุดที่วัดทุกไบต์) → reload 18:04:57 → ตรวจแบบอ่านอย่างเดียว: pass 1 ของทั้ง 3 คำถามได้ตาราง.คอลัมน์ของ "น่าน" ถูก · pytest 1238 passed, 3 skipped · ruff ผ่าน
· ถอยกลับ: คืน config.db จาก backup (หรือแค่ `DELETE FROM keyword_value_index WHERE context_name LIKE 'feed_%' AND table_name NOT IN (main view)`) + `git checkout` 5 ไฟล์

### 8.1 ที่ยังค้าง — ต้องให้เจ้าของตัดสิน

1. ✅ **แก้แล้ว §9** — **"ค่าใช้จ่ายของน่าน" จาก portal** — `scope_columns` ใช้ชื่อคอลัมน์เดียวต่อ key (`year_month: time_key`) และ `scope_filters` ปิดทุกตารางที่ไม่มีคอลัมน์นั้น →
   `dim_org_snapshot` (`effective_month`) ใช้ไม่ได้ภายใต้ scope. ข้อเสนอ: `scope_columns` รับ**หลายชื่อต่อ key** (`{"year_month": ["time_key", "effective_month"]}`),
   ตารางผ่านถ้ามีชื่อใดชื่อหนึ่ง และถูกกรองด้วยคอลัมน์ที่ตัวเองมี — แก้ contract ของ NT-Report + `data_sources.scope_filters` และผู้อ่าน `scope_columns` อีก 5 จุด
   (`prompt_builder.build_date_instructions`, `hybrid_flow._period_columns` / `scope_note`, `contract_draft`, `thai_year`) — เป็นโค้ดบังคับสิทธิ์ จึงไม่ทำโดยไม่ถาม.
   chat (ไม่มี scope) ใช้ JOIN นี้ได้แล้ววันนี้
2. ✅ **แก้แล้ว §9** — **EBT ระดับส่วนงานย่อย** — กฎ `ebt_dimension_breakdown` ใน contract ของ NT-Report บอกสูตรสำหรับ division / cost_center เท่านั้น → ที่ `sub_unit` โมเดลใช้สูตรไม่ครบ
   (ลืมหัก 08.รายได้อื่น หรือใช้แถว COMPUTED 3.1) — ข้อเสนอ: ขยายกฎใน contract ให้ครอบคลุม "ทุกระดับหน่วยงาน (division … sub_unit, cost_center)" และเขียน
   `COALESCE(SUM(...), 0)` ต่อก้อน + golden ตัวอย่างหนึ่งข้อจาก control totals — แก้ที่ความรู้ของเจ้าของข้อมูล ไม่ใช่ prompt กลาง (กฎกลางทำ ebt P03/P04 เสีย §8)
3. **ยังต้องกด rebuild เอง** เมื่อข้อมูลเปลี่ยน — ขั้นอัตโนมัติ = Plan 8 §2.1 (hook ที่ `datafeed_knowledge.ensure_current`)
4. คำทั่วไปเป็น known term ("ค่า" → `cat_l2_th`, "แบบ") — note ของ pass 1 สรุปต่อคอลัมน์แล้ว ชุดวัดไม่เสีย; ถ้าพบคำตอบผิดเพราะคำทั่วไป ให้ตัดคำสั้น/คำที่ตรงค่ามากเกินไปออกจาก known terms

## 9. scope หลายชื่อต่อ key + สูตร EBT ทุกระดับหน่วยงาน (2026-10-22 → ขึ้นของจริง 2026-10-23 22:18)

เจ้าของสั่ง "ทำทั้งสองข้อ" ของ §8.1 — แก้สอง repo:

**AI (`app/`):**
| ไฟล์ | |
|---|---|
| `services/data_sources.py` | `scope_column_names` — ค่าใน `scope_columns` เป็น column หรือ `[column, ...]` (ชื่อแรก = ของ main view); `scope_filters` กรองแต่ละตารางด้วยชื่อแรกที่ตารางนั้นมี, ตารางที่ไม่มีชื่อใดเลยยังปิดเหมือนเดิม, ค่าที่ไม่ใช่ string / list ว่าง = `ScopeError`; `request_scope_columns` เก็บชื่อแรก (ผู้อ่านเดิมไม่ต้องรู้) |
| `ai/hybrid_flow.py` | `_period_columns` รวมทุกชื่อที่เป็นคอลัมน์เวลา · `unfilterable_columns.asked` นับ filter ว่า "ถาม" ถ้าค่าทั้งก้อน**หรือคำหนึ่งของค่า**อยู่ในคำถาม (ด้านล่าง) |
| `schema/prompt_builder.py` | `build_date_instructions` ใช้ชื่อแรกของ key เวลา |
| `services/contract_draft.py` | อ่าน `org_code` ผ่าน `scope_column_names` |
| tests | `test_scope.py` +1 (JOIN fact × snapshot ภายใต้ scope, org อื่น = NULL, ตารางที่ไม่มีชื่อ = ปิด, ประกาศผิดรูป = ScopeError), `test_value_lookup_tables.py` +1 |

**NT-Report (`tools/feed/`, `DataFeed/contracts/`):** expense **1.2.4** `scope_columns.year_month: [time_key, effective_month]` ·
ebt **1.4.4** `ebt_dimension_breakdown` ครอบทุกระดับหน่วยงาน (division, sub_division, unit, sub_unit, `*_fname`, cost_center) +
"ใช้ครบทั้ง 4 ก้อนเสมอ ไม่ใช้แถว COMPUTED 3.1 แทน" · `feed.py` SCHEMA.md แสดงหลายชื่อ · test 32 passed · contract-only (ไม่ rebuild dist)

**ระหว่างวัด พบและแก้ (ไม่ได้อยู่ในแผนตอนเริ่ม):**
- *เขียน `COALESCE(SUM(...), 0)` ไว้ในกฎ ebt ของ contract* → ฝั่ง AI ครอบ COALESCE แม้กรองผิด (`division LIKE '%น่าน%'` บนตารางหลัก) และตอบ
  **"EBT ของน่าน = 0 บาท"** — แย่กว่า "ไม่มีข้อมูล" → ตัดออกจาก contract (บทเรียนเดียวกับกฎกลางใน §8: คำแนะนำ SQL ทั่วไปใน prompt ย้ายคำตอบที่ไม่เกี่ยว)
- *ตัวกัน dropped-filter ไม่ทำงานกับค่าจาก value lookup* — pass 1 กรองด้วยค่าเต็มที่ lookup พบ (`'ส่วนขายและบริการลูกค้า น่าน'`) ซึ่งคำถามไม่มีทั้งก้อน
  → filter ไม่ถูกนับว่า "ถาม" → retry ย้ายกลับตารางหลักโดยทิ้ง `sub_unit` ผ่านไปได้ → `asked()` นับคำของค่าด้วย (คำ ≥ 2 ตัวอักษร)

**วัด (สำเนา, server ซ้อม, key ซ้อม; ฝั่งก่อน = ของจริงหลัง §8):**

| ชุด | ก่อน r1 | ก่อน r2 | หลัง r1 | หลัง r2 |
|---|---:|---:|---:|---:|
| คำถามจริง (15) | 9 | 9 | 10 | 11 |
| revenue (10) | 9 | 9 | 9 | 9 |
| expense (10) | 8 | 8 | 9 | 9 |
| sales (10) | 8 | 7 | 8 | 7 |
| ebt (10) | 7 | 5 | 6 | 7 |
| **รวม (55)** | **41** | **38** | **42** | **43** |

(รอบสองของฝั่งก่อน 4 ชุดรันใหม่หลังเครื่อง sleep — รอบที่ค้างตอนหลับได้ `llm_unavailable` ทุกข้อ จึงทิ้ง) · ไม่มีข้อที่ถูกสองรอบก่อนแก้แล้วผิดสองรอบหลังแก้ ·
prompt ของ `feed_revenue` เหมือนกันทุกไบต์ระหว่างสองฝั่ง (code ใหม่ไม่เปลี่ยน prompt ใด; ที่ต่างคือข้อความกฎ ebt + รายชื่อตารางภายใต้ scope ของ expense) ·
legacy 9/37 (เท่ารอบ §8 — ตัวกัน `asked` ทำงานเฉพาะ file source)

**คำถาม "น่าน" ฝั่งหลัง สองรอบ:**

| | รอบ 1 | รอบ 2 | ค่าที่ถูก |
|---|---|---|---|
| ebt | 24,410,200.83 | 24,410,200.83 | 24,410,200.83 (สูตร contract) ✓ |
| expense (portal scope) | 70,736,917.53 | 70,736,917.53 | 70,736,917.53 ✓ — ฝั่งก่อน: query_failed ทั้งสองรอบ |
| sales | 96,405,275.59 | 96,405,275.59 | ✓ |
| revenue | 9,896,952.92 (ยอด ก.ย.) | 88,204,263.33 (สะสม) | สะสม 88,204,263.33 — prompt เท่าเดิม: ความแปรปรวนของ LLM |

**ขึ้นของจริง (2026-10-23):** code เข้า working tree 22:18:32 (ตรงกับชุดที่วัดทุกไบต์) → reload 22:18:37 → backup
`~/nt-ai-backups/k3-scope-names-20261023-221846/` (config.db + contract เดิมสองไฟล์) → contract ใหม่เข้า `NT-Report/DataFeed/contracts/` →
re-sync: `feed_expense.scope_columns = {"year_month": ["time_key", "effective_month"], ...}`, กฎ ebt ฉบับใหม่อยู่ใน `vanna_documentation` →
ตรวจแบบไม่เรียก LLM: JOIN ของน่านภายใต้ scope ม.ค.–ก.ย. 69 บนของจริง = **70,736,917.53** · pytest 1240 passed, 3 skipped · ruff ผ่าน
· ถอยกลับ: คืน contract สองไฟล์จาก backup (AI re-sync เอง) — code ใหม่อ่าน contract เก่าได้ (string = ชื่อเดียว); ลำดับขึ้นต้องเป็น code ก่อน contract
เสมอ เพราะ code เก่าปฏิเสธ `scope_columns` แบบ list (`ScopeError` → portal ได้ 400 ทุกคำถามของ expense)

**ยังค้าง:** dim ที่ไม่มีคอลัมน์งวดเลย (revenue/sales `dim_org*`, expense `dim_gl` ฯลฯ) ยังปิดภายใต้ scope ปีเดือน — ตารางมิติที่ไม่มีงวดอาจต้องมีวิธีประกาศ
"ไม่ผูกงวด" แยก (ระวัง: scope คือสิทธิ์ ไม่ใช่แค่ตัวกรอง — ต้องให้เจ้าของตัดสิน) · ขั้นอัตโนมัติของ index = Plan 8.2
