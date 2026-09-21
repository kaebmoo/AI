# RESULT Plan 8 Phase 8.1 — โมเดลความรู้: ที่มา + ความมั่นใจ + สถานะ

**สถานะ (2026-09-21):** ข้อ 7 ✅ (เจ้าของตัดสิน §7.6 แล้ว) · ข้อ 8 migration ซ้อมบนสำเนาแล้ว (§8) — ของจริงยังไม่รัน · ของจริงไม่ถูกแตะ
**prompt:** `plan/PROMPT_P8_PHASE1.md` · **แผน:** `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md` §3, §5 8.1

---

## 0. Baseline + backup

- `main` ahead 9 (ยังไม่ push) สะอาด · server จริง port 8000 (PID 38769) ไม่แตะ
- backup สด `~/nt-ai-backups/p8-1-20260921-180246/` — backup API จาก connection `mode=ro`, `quick_check = ok` ทั้งสองไฟล์,
  SHA-256 ของจริงก่อน/หลัง backup เท่ากัน (`config.db 53b26063…`, `app.db a5df3bd0…`)
- ตัวเลขใน §7 นับจากของจริงแบบ `mode=ro` / จาก backup นี้ · ตัวเขียน/ตัวอ่านไล่จาก code ที่ HEAD `0078dcf`

---

## 7. สำรวจ 7 ตาราง (+ `vanna_documentation`) — ข้อ 7

### 7.1 มีอะไรอยู่แล้ว

| ตาราง | แถว | UNIQUE ในตัวตาราง | `source` | `status` | `confidence` | `is_active` | ORM |
|---|---:|---|---|---|---|---|---|
| `schema_contexts` | 9 (ปิด 1) | `name` | — | — | — | ✅ | ไม่มี (raw SQL) |
| `schema_metadata` | 507 | `(table_name, column_name)` | — | — | — | **ไม่มี** | ✅ |
| `schema_business_rules` | 72 | `rule_code` | — | — | — | ✅ | ✅ (ขาด 4 คอลัมน์ที่ ALTER ภายหลัง) |
| `golden_examples` | 132 (ปิด 1) | **ไม่มี** | — (`added_by` = user id / `'golive-F11-review'` / ว่าง) | — | — | ✅ | ✅ |
| `schema_semantic_mapping` | 192 | `keyword` — **ทั้งระบบ** ไม่ใช่ต่อ context | — | — | — | ✅ | ✅ |
| `master_hierarchy` | 22 | `(context_name, level)` | ✅ `auto` 11 · `manual` 11 (DEFAULT `'auto'`) | — | — | ✅ | ไม่มี |
| `master_hierarchy_values` | 3,690 | `(context_name, level, value)` | ✅ `auto` 1,444 · `manual` 2,246 | — | — | ✅ | ไม่มี |
| `data_warnings` | 1 | `code` | — | — | — | ✅ | ✅ |
| `vanna_documentation` | 76 | `doc_key` | — | — | — | ✅ | ✅ |

ข้างเคียงใน app.db: `suggested_fixes` มี `status` (`pending / approved / rejected / auto_applied`) + `confidence` = คิวของตัวเรียนรู้ที่ออกแบบไว้แล้ว —
**0 แถว และไม่มี code ใดเขียน** (`AutoAnalyzer.save_suggested_fixes` ไม่มีผู้เรียก) · `config_audit_log.source` (`manual / admin_agent / auto_analyzer / onboarding / api`) — **0 แถว**

**`database/migrations/*.sql` ไม่ตรงกับของจริง:** ของจริงมี `master_hierarchy.parent_column / source_view`, `schema_business_rules.rule_category / inject_mode`
ที่ไม่มีไฟล์ migration ใดสร้าง → migration ของ 8.1 ต้องตรวจคอลัมน์จริงก่อน ALTER (แบบ `scripts/migrate_workspaces.py`) ไม่ใช่ไฟล์ `.sql`

### 7.2 ที่มาจริงของแถวที่มีอยู่

| กลุ่ม | แถว | หลักฐาน | ที่มาตามความจริง |
|---|---:|---|---|
| context / metadata / vanna doc ของ `feed_*` | 4 / 348 / 71 | `datafeed_knowledge` เขียนจาก contract (2026-09-21 01:17) | **contract** |
| golden id 51–124 (`feed_*`) | 74 | `gen_golden_from_controls.py` จาก control totals ของ contract | **contract** |
| golden id 125–132 (`added_by = 'golive-F11-review'`) | 8 | ใส่ระหว่าง go-live F11 (`RESULT_F11` §7 ข้อ B) | **เครื่องเสนอ เจ้าของรับ** |
| hierarchy `feed_revenue` 3 ระดับ | 3 | คำสั่งของ `RESULT_P8_PHASE0` §3.3 ที่เจ้าของรันเอง 14:51 (`source='auto'`) | **เครื่องเสนอ เจ้าของรับ** |
| hierarchy ระดับ `auto` ของ legacy (`pl_costtype` 3, `expense_org` 3, `transfer price` 2) | 8 | เนื้อหาตรงกับ `HIERARCHY_DEFS` ใน `extract_hierarchy.py` ทุกตัว — ค่าคงที่ที่คนเขียน, `extract` ติดป้าย `auto` ให้เสมอ | **คน** (ป้ายผิด) |
| hierarchy ระดับ `manual` (`revenue`, `revenue_gl`, `revenue_org`, `expense`) | 11 | UI / `import_master_data.py` | คน |
| hierarchy values `auto` (รวม `feed_revenue` 215) | 1,444 | `extract_hierarchy.py` ดึง DISTINCT จากข้อมูล | **อนุมานจากข้อมูล** |
| hierarchy values `manual` | 2,246 | UI / นำเข้า CSV master data | คน |
| context / metadata / rules / golden / mapping / warning / doc ของ legacy | 5 / 159 / 72 / 50 / 192 / 1 / 5 | migration seed, admin UI, สคริปต์ที่คนเขียนค่า — ทุกแถวเก่ากว่า onboarding (2026-03-18) หรือไม่ได้มาจากมัน | คน |
| ตัวเรียนรู้ | **0** | `config_audit_log` 0 แถว · ทางเขียนของมันไม่เคยทำงาน (§7.3) | — |

⚠ **ของทดสอบค้างในของจริง:** golden id 41–50 (10 แถว, `category='test'`, active) = "รายได้รวม" → `SELECT SUM(revenue_value) FROM test_revenue`
(ตารางที่ไม่มีอยู่จริง) และกฎ `TEST_001` (`table_name='test_revenue'`, 2026-03-21) — golden ชุดนี้ถูก train เข้า brain ของ workspace `default`
(`BrainFilter` เก็บ category ที่ไม่ใช่ context ไว้ใน default) และ "รายได้รวม" คือคำถามจริง P01 → **เสนอเอาออกเป็นงานแยก** (กระทบ RAG ของ legacy — วัด legacy ก่อน/หลัง)

### 7.3 ตัวเขียน — ทุกตัว (app, admin API, admin tools, ตัวเรียนรู้, scripts)

| ตัวเขียน · ทางเข้า | ผู้ประพันธ์ | ตาราง · วิธีเขียน | ดูของเดิมก่อนทับ | ขัดหลัก "คนชนะเครื่อง" ตรงไหน |
|---|---|---|---|---|
| admin API CRUD (`admin/{contexts,schema,rules,golden_examples,mappings,warnings,vanna_docs,hierarchy,workspaces}.py`, `context_store`, `hierarchy_service` CRUD) · admin | คน | ทุกตาราง · insert / update; **ลบจริง** ใน contexts, schema, rules, golden, mappings, warnings, vanna-docs; hierarchy = soft delete; hierarchy บังคับ `source='manual'` ทุกครั้ง | ไม่ต้อง | ลบจริง = การตัดสินหายไม่มีร่องรอย; ค่า hierarchy ที่ admin ลบยังติดป้าย `auto`; ลบ context ไม่ cascade → ความรู้กำพร้า |
| admin agent `AddMapping / AddRule / AddExample` · admin ยืนยันในแชท | คน | mapping / rules / golden · insert อย่างเดียว (dedup ก่อน) | — | ไม่ทับ ✅ (AddRule ทิ้ง `context_name` เสมอ; AddExample ไม่ล้าง cache) |
| `datafeed_knowledge` · `register_file_source`, `POST /admin/sources/register`, `gen_docs_from_contract.py`, **`ensure_current()` ในทุกคำขอเมื่อ contract / schema_version เปลี่ยน** | contract | contexts: UPDATE `main_view / description / instruction_th / scope_columns` **+ `is_active=1`** (keywords / priority ใส่ครั้งแรกเท่านั้น) · metadata: **ลบทั้งตารางแล้วใส่ใหม่** · vanna doc: ลบตาม prefix แล้วใส่ใหม่ | ไม่ | admin แก้ metadata / doc ของ `feed_*` → หายรอบ re-sync ถัดไป; admin ปิด context → ถูกเปิดกลับ |
| `scripts/datafeed/gen_golden_from_controls.py` · คนรัน | contract | golden · **ลบทั้ง category `feed_<domain>` แล้วใส่ใหม่** | ไม่ | **รันกับ revenue = ลบ golden 8 ข้อที่เจ้าของรับตอน F11 (id 125–132) ไปด้วย** |
| context onboarding · `POST /admin/contexts/onboard[/apply-sql]`, tool `RunOnboarding`, `onboard_context.py` | LLM เสนอ → admin กด apply ทั้งชุด | contexts **INSERT OR REPLACE** (แถวใหม่: `workspace_id / source_id / scope_columns / priority` หาย) · metadata INSERT OR REPLACE (ช่องที่ไม่ระบุกลายเป็น NULL) · rules INSERT (ชน = error) · golden INSERT (**ซ้ำทุกรอบ**) · mapping INSERT OR IGNORE (ชน = หายเงียบ) · hierarchy INSERT OR REPLACE (**ล้มทุกครั้ง** — ไม่ใส่ `level_label_en` ที่ NOT NULL) · warnings INSERT (**ล้มทุกครั้ง** — ไม่ใส่ `keywords / columns_to_check` ที่ NOT NULL) | ไม่ | ทับของคนใน contexts / metadata; ไม่มี audit |
| `hierarchy_service.bootstrap_from_view` · admin | heuristic | levels · ON CONFLICT ทับ `level_columns / detection_keywords / parent_column / source_view` โดยไม่เปลี่ยน `source` | ไม่ | แถว `manual` ได้เนื้อหาของเครื่องแต่ยังติดป้าย `manual` (8.0 §3.4) |
| `scripts/extract_hierarchy.py` · `auto_extract`, หลัง bootstrap | อนุมานจากข้อมูล | levels: ทับ label ทุกครั้ง, columns / keywords เว้น `manual`, `updated_at` ทุกครั้ง · values: insert `auto`, ชน = เว้น `manual` | บางช่อง ✅ | label + `updated_at` ของแถว `manual` เปลี่ยนทุกรอบ (Exit 8.1 ต้อง "ไม่เปลี่ยนแม้แต่ตัวเดียว"); ค่าที่หายจากข้อมูลไม่ถูกปิด |
| `view_manager.propagate_metadata_to_view` · admin (สร้าง view / ปุ่ม propagate) | คัดลอก metadata ของตารางต้นทาง | metadata · เติมเมื่อ `display_name_th` ว่าง ไม่งั้นข้าม | ใช้ "ช่องว่าง" แทนป้าย | ส่วนใหญ่ไม่ทับ |
| `POST /admin/analyzer/analyze/import` (`schema_analyzer.py`) · admin ส่ง JSON ที่ LLM แนะนำ | LLM | metadata **ทับทุกครั้ง** · mapping / rules ใส่เมื่อยังไม่มี | ไม่ (metadata) | ทับ metadata ของคน; ไม่ล้าง query cache / ไม่ mark brain |
| `POST /admin/schema/dimension-families/auto-populate` · admin | heuristic | metadata.`dimension_group` · ทับเมื่อ `overwrite` หรือช่องว่าง | ใช้ช่องว่าง | `overwrite=true` ทับของคน |
| ตัวเรียนรู้ `scheduler._job_auto_analyze → _apply_high_confidence_fixes` · ทุก 6 ชม. ไม่มี flag | จากคำถามจริง | mapping · insert `is_active=True` | ไม่ | **ไม่เคยเขียนได้จริง:** heuristic ให้ความมั่นใจสูงสุด 0.5 < เกณฑ์ 0.8 (ตายตัว 2 ที่) และ `_keyword_not_mapped` query ตาราง config ผ่าน session ของ app.db ซึ่งไม่มีตารางนั้น |
| `POST /chat/train` · **user ใดก็ได้** (ปุ่มแก้ SQL ใน chat) | admin = คน · user = จากการใช้งาน | golden · ถ้าคำถามตรงกัน UPDATE (`is_active = is_admin`) ไม่งั้น insert | ไม่ | **ล้มทุกครั้ง** — ใช้ session ของ app.db กับตารางของ config.db; ถ้าแก้ session โดยไม่แก้กฎ user ทั่วไปจะปิด / ทับ golden ของ admin ได้ |
| `POST /feedback/{id}/review` (`feedback_service.review_feedback`) · admin | คน | golden · insert เมื่อยังไม่มี | — | **ล้มทุกครั้ง** — session ของ app.db เช่นกัน |
| thumbs-up ของ admin (`feedback.py:195`) | คน | **train Vanna ตรง ไม่มีแถว golden** — หายเมื่อ sync brain เต็มครั้งถัดไป | — | ความรู้ที่ไม่มีที่มา / สถานะ |
| `scripts/import_master_data.py` · คน (CSV master data) | คน | levels / values · upsert `source='manual'` | ทับได้ (ตั้งใจ) | **ชี้ business DB โดยค่าเริ่มต้น** — ตารางอยู่ config.db |
| `migrate_workspaces.py`, `migrate_data_sources.py`, `source_registration.register` | โครงสร้าง | contexts.`workspace_id / source_id` | — | ผูกโครงสร้าง ไม่ใช่ความรู้ |
| scripts legacy 11 ตัว (`populate_schema_metadata`, `setup_multicontext_db`, `migrate_context_instructions`, `insert_golden_example`, `fix_abbreviations`, `add_mobile_mapping`, `add_mapping`, `add_context_keywords`, `setup_rules_db`, `clear_abbreviations`, `migrate_config_to_separate_db`) | — | ชี้ `nt_fi_report.sqlite` ก่อนแยก DB / ใช้ครั้งเดียวไปแล้ว | — | ไม่อยู่ในกฎ · `setup_rules_db.py` ถ้ารันกับ business DB จะแทน view `revenue_search` ด้วยนิยามเก่า 10 คอลัมน์ · `migrate_config_to_separate_db.py` รันซ้ำ = DROP ตาราง config แล้วคัดลอกของเก่ามาทับ |

อ่านอย่างเดียว (ยืนยันแล้ว): `config_gc` (แจ้งอย่างเดียว ไม่ปิด/ลบ), `dedup_engine`, `warning_detector`, `validation_service`, `keyword_index` (เขียน `keyword_value_index` เท่านั้น), `retention`, `user_data`, `mcp_servers/*` (`mode=ro`), `query.py`, `mcp_facade.py` (แต่เรียก `ensure_current()` ทางอ้อม)

### 7.4 ตัวอ่านที่ถึง prompt / RAG / routing — 56 จุด

ส่วนใหญ่กรอง `is_active = 1` อยู่แล้ว → การกรอง `status = 'active'` = แก้ WHERE · ที่ต้องระวัง:

1. **ตัวอ่านซ้ำของตารางเดียวกัน 2–4 ที่:** hierarchy 3 ที่ (`schema/service.build_hierarchy_rule_text`, `ai/hierarchy_context.load_hierarchies_from_db`,
   `hybrid_flow.load_execution_metadata`), business rules 4 ที่ (`schema/service`, `validation_service`, `vanna_service`, MCP), mapping 3 ที่, golden 2 ที่ —
   และ **`mcp_servers/nt_metadata_mcp.py` เป็น process แยกที่ใช้ raw SQL ของตัวเอง** (ลืมง่ายที่สุด)
2. `schema_metadata` ไม่มีตัวเปิด/ปิดเลย — ตัวอ่าน 7 ที่ต้องเพิ่มเงื่อนไขใหม่ ไม่ใช่แก้ของเดิม
3. ไม่กรองแม้แต่ `is_active`: `workspaces.workspace_of_context`, `BrainFilter`, MCP `get_schema_for_context` / `get_column_info` (อ่าน `schema_contexts`)
4. **Vanna:** `sync_brain` ล้าง collection แล้วสร้างใหม่จาก DB (กรองที่ SELECT ก็พอ) แต่มีการ train ทีละข้อ 3 ทางที่ไม่ผ่าน SELECT —
   admin golden create / update (`if is_active`), `/chat/train` (`if is_admin`), thumbs-up ของ admin (ไม่มีแถว) → ต้องเปลี่ยนประตูเป็น `status == 'active'` พร้อมกัน
5. `get_known_terms` อ่าน hierarchy values **โดยไม่ join ระดับ** → ค่าของระดับที่ยังไม่ active จะเข้าพจนานุกรมคำ → ค่าต้องมีสถานะของตัวเอง (ตามระดับ)
6. cache: system prompt 6 ชม. (`refresh_cache`), `_HIERARCHY_CACHE` / known terms / warnings 1 ชม., query cache 30 นาที; RAG เปลี่ยนเมื่อกด sync brain เท่านั้น
   (`hierarchy_service.create_value / update_value / delete_value` ไม่ล้าง `_HIERARCHY_CACHE` อยู่แล้ววันนี้)

**ค่าคงที่ใน prompt path** (ข้อ 3 ของ "ที่ 8.0 เจอ"): ยืนยัน `prompt_builder.py:365` (ไทย) / `:415` (อังกฤษ) "ใช้ `year` และ `month`" + `CAST(month AS INTEGER)`
อยู่ใน prompt เดียวกับ `build_date_instructions` ที่บอกคอลัมน์ของแต่ละ context — สองคำสั่งขัดกันสำหรับ `feed_ebt` / `feed_expense` / `pl_costtype` ·
พบเพิ่ม: `chart_postprocessor.py:348` ("เดือนมกราคม 2568"), `:365` ("Q1/2567"), `hybrid_flow.py:183` ("ปี 2569" ใน `scope_note`),
`datafeed_knowledge.py:76–77` (ตัวอย่าง พ.ศ. 2568 → `202501` ที่เขียนลง `instruction_th` ของ `feed_*` ทุก context)

### 7.5 มี / ต้องเพิ่ม — ข้อเสนอสำหรับข้อ 8

**ชุดค่า = PLAN_8 §3 ข้อ 2 ตรงทุกตัว** — `source` ∈ `declared / manual / inferred / learned` · `status` ∈ `active / proposed / rejected` · `confidence` REAL 0–1 (NULL = ไม่ได้บันทึก)
· `auto` เลิกใช้ (แปลงตามที่มาจริง §7.2) · `is_active` คงไว้เป็นสวิตช์เปิด/ปิดของ admin แยกจาก `status`

| ตาราง | ต้องเพิ่ม | ค่าของแถวที่มีอยู่ |
|---|---|---|
| `schema_contexts` | `source`, `status`, `confidence` | `feed_*` 4 = declared · อื่น 5 = manual |
| `schema_metadata` | `source`, `status`, `confidence` (`status` = ตัวเปิด/ปิดตัวแรกของตารางนี้) | ตาราง `feed_*` 348 = declared · อื่น 159 = manual |
| `schema_business_rules` | `source`, `status`, `confidence` | 72 = manual |
| `golden_examples` | `source`, `status`, `confidence` | id 51–124 (74) = declared · id 125–132 (8) = manual · id 1–50 = manual |
| `schema_semantic_mapping` | `source`, `status`, `confidence` | 192 = manual |
| `master_hierarchy` | `status`, `confidence` · แปลง `auto` | 22 = manual |
| `master_hierarchy_values` | `status`, `confidence` · แปลง `auto` | `manual` 2,246 = manual · `auto` 1,444 = inferred |
| `data_warnings` | `source`, `status`, `confidence` | 1 = manual |
| `vanna_documentation` (เสนอรวม — ตัวเขียนเดียวกับ metadata) | `source`, `status`, `confidence` | `datafeed_*` 71 = declared · 5 = manual |
| **ทุกแถว** | | `status = active` (prompt เดิมทุกไบต์) · `confidence = NULL` · `learned` = 0 แถว |

**เหตุผลของค่าที่เลือก (ตามที่ prompt ให้บอก):**
- **hierarchy `feed_revenue` 3 ระดับ = `manual` / `active`** — เครื่องเสนอ (8.0 §3.2) แล้วเจ้าของรับและรันเอง; PLAN §5 8.3 "รับ / แก้ / ปฏิเสธ → กลายเป็น manual" → ป้าย `manual`
  ทำให้ bootstrap / extract รอบหน้าทับไม่ได้ · **ค่า 215 ตัว = `inferred`** — เป็น DISTINCT ที่ดึงจากข้อมูล ไม่ได้ตรวจทีละตัว; ถ้าเป็น `manual` extract จะตามข้อมูลไม่ได้อีก
- **golden 8 ข้อของ F11 = `manual`** — เหตุผลเดียวกัน (เครื่องเสนอ เจ้าของรับ) และกัน `gen_golden_from_controls.py` ลบทิ้ง
- **golden 74 ข้อจาก control totals = `declared`** — สร้างแบบ deterministic จากตัวเลขที่เจ้าของประกาศใน contract
- **ระดับ `auto` ของ legacy 8 ระดับ = `manual`** — เนื้อหาคือค่าคงที่ที่คนเขียนใน `HIERARCHY_DEFS`; ป้าย `auto` มาจาก extract ติดให้เสมอ ไม่ได้บอกที่มาจริง
  (รวมระดับที่มี "กลุ่ม" เดี่ยว ๆ — เป็นของคน: เสนอ ไม่แก้เอง ตามที่ prompt ระบุ)

**migration (ข้อ 8):** สคริปต์ Python idempotent แบบ `migrate_workspaces.py` (ตรวจคอลัมน์จริงก่อน ALTER ADD COLUMN) → ADD COLUMN อย่างเดียว =
code เก่ายังทำงานได้ (ถอย code ไม่ต้องถอย DB) · DEFAULT ของ `master_hierarchy*.source` เดิม (`'auto'`) แก้ไม่ได้ถ้าไม่สร้างตารางใหม่ →
code ใหม่ต้องเขียน `source` เองทุกครั้ง, ตัวอ่านถือ `auto` = `inferred`, และรัน migration ซ้ำหลัง restart เพื่อเก็บแถวที่ code เก่าเขียนระหว่างนั้น

### 7.6 ต้องตัดสินก่อนข้อ 8 — **เจ้าของตัดสินแล้ว 2026-09-21: ข้อ 1 = ก · ข้อ 2 = ก · ข้อ 3 = ก**

(และ: ทำต่อได้ แต่รอ session อื่นที่แก้ `prompt_builder.py` / `hybrid_flow.py` / `hierarchy_context.py` / `thai_year.py` ค้างไว้ commit ก่อนถึงข้อ 10)

1. **ข้อเสนอที่ชนแถวเดิมอยู่ที่ไหน** — PLAN §3.2–3.3 ให้ทุกแถวมี `status` และ "ขัดกัน = `proposed` เข้าคิว ระหว่างรอแถว `active` ใช้ต่อ"
   แต่ 8 ใน 9 ตารางมี UNIQUE ของคีย์ในตัวตาราง (§7.1) → แถว `proposed` ที่คีย์ซ้ำกับแถว `active` ใส่ตารางเดียวกันไม่ได้ (SQLite ถอด UNIQUE ไม่ได้ถ้าไม่สร้างตารางใหม่)
   - **ก (ข้อเสนอ)** เพิ่มคอลัมน์ + ตารางคิว `knowledge_proposals` (config.db) สำหรับข้อเสนอที่ชนแถวเดิม — เก็บตาราง / คีย์ / เนื้อหาที่เสนอ / source / confidence / เหตุผล / สถานะ;
     ความรู้ใหม่ที่ยังไม่มีแถวและเครื่องไม่แน่ใจ = แถว `status='proposed'` ในตารางเดิม (หน้า admin เดิมแสดง/แก้ได้); ตัวอ่านทุกจุดกรอง `status='active'`
   - ข สร้าง 8 ตารางใหม่ให้คีย์ซ้ำได้เฉพาะแถวที่ไม่ active (partial unique index) — ข้อเสนอทุกแบบอยู่ในตารางเดิม แต่ต้อง rebuild ตารางจริง 8 ตาราง
     และทุกจุดที่อ่านด้วยคีย์ต้องกรอง `status` (`schema_contexts` อย่างเดียวถูกอ้าง 66 บรรทัดใน 25 ไฟล์ + MCP server) — พลาดจุดเดียว = ใช้แถว proposed เป็นของจริง
   - ค ข้อเสนอทุกแบบอยู่ในตารางคิว ตารางเดิมมีแต่ของที่ตัดสินแล้ว — ตัวอ่านไม่ต้องกันข้อเสนอเลย แต่ `status='proposed'` ในตารางเดิมไม่เกิด
     (ต่างจาก §3.2 ตามตัวอักษร) และคิวต้องแสดงข้อเสนอของทุกตารางจาก JSON
2. **contract ฉบับใหม่ทับแถว `declared` ของตัวเองได้ไหม** — D-C ตัดสิน "contract กับ admin ขัดกัน = เข้าคิว" ไม่ได้พูดถึง contract ฉบับใหม่กับฉบับเก่า
   - **ก (ข้อเสนอ)** ทับได้ (ช่องทางเดียวกันแก้การประกาศของตัวเอง) — เข้าคิวเมื่อแถวเป็น `manual` (admin แก้ช่องที่ contract ประกาศ) ตาม D-C ·
     ช่องที่ contract ไม่ประกาศ (keywords, priority, workspace, เปิด/ปิด) เป็นของ admin — contract ไม่แตะ (เลิกตั้ง `is_active=1` กลับ)
   - ข เข้าคิวทุกครั้งที่ contract เปลี่ยน — `feed_*` จะไม่ตาม contract เองอีก (Plan 7 ออกแบบให้ตามเองโดยไม่มีใครรันอะไร); contract ฉบับหนึ่งเปลี่ยนได้หลายร้อยแถว
3. **ตัวเขียนที่ไม่เคยทำงานจริง** (`/chat/train` ที่ปุ่มใน chat เรียก, `/feedback/{id}/review` ที่หน้า admin เรียก, auto-apply ของตัวเรียนรู้)
   - **ก (ข้อเสนอ)** เข้ากฎ + แก้ session ให้ชี้ config.db (commit แยก): admin = `manual` / `active` · user ทั่วไป + ตัวเรียนรู้ = `learned` / `proposed`
     (ไม่เข้า prompt / RAG จนกว่าคนรับ) · ตัวเรียนรู้เลิก auto-apply
   - ข เข้ากฎอย่างเดียว ปล่อย session ผิด (endpoint ล้มเหมือนเดิม) แล้วแยกงาน
   - ค ลบ auto-apply ของตัวเรียนรู้ + ปิด `/chat/train` ของ user ทั่วไป

### 7.7 ที่เจอระหว่างสำรวจ — นอกขอบเขต 8.1 (เสนอ ไม่แก้เอง)

- ของทดสอบค้างในของจริง (golden id 41–50 + กฎ `TEST_001`) — §7.2
- onboarding: hierarchy และ warnings ล้มทุกครั้ง (NOT NULL), golden ซ้ำทุกรอบ — ของ 8.2 (ตัวเขียนตัวนี้ถูกเขียนใหม่ที่นั่น)
- tool `RunOnboarding` ใช้ `dry_run` ค่าเริ่มต้น `False` ขณะที่ REST ใช้ `True` — ข้อความยืนยันที่ admin เห็นไม่บอกว่าจะเขียนจริง
- `import_master_data.py` ชี้ business DB โดยค่าเริ่มต้น (ตาราง hierarchy อยู่ config.db)
- admin API ลบจริง 7 ตาราง (ขัดหลัก soft delete ของ `CLAUDE.md`); ลบ context ไม่ cascade
- dead code: `context_router.py`, `vanna_service_draft.py`, `check_rule_violation` (อ่านกฎแล้วไม่ใช้)
- scripts legacy ที่อันตรายถ้ารัน (`setup_rules_db.py`, `migrate_config_to_separate_db.py`) — §7.3

---

## 8. Migration — ข้อ 8 (ซ้อมบนสำเนาแล้ว · ของจริงยังไม่รัน)

`scripts/migrate_knowledge_provenance.py` — idempotent, ตรวจคอลัมน์จริงก่อน ALTER (แบบ `migrate_workspaces.py`):
- 9 ตารางได้ `source` / `status` (`NOT NULL DEFAULT 'active'`) / `confidence` — `master_hierarchy*` มี `source` อยู่แล้วจึงได้ 2 คอลัมน์ · **ADD COLUMN อย่างเดียว**
- เติม `source` เฉพาะแถวที่ยังไม่รู้ที่มา (NULL / `auto`) ตาม §7.5 ด้วยกฎที่อ่านจาก registry — ไม่มีชื่อ context ในสคริปต์:
  context ที่ผูก source ซึ่งมี contract = `declared` · metadata ของตารางที่ contract ลงทะเบียน = `declared` ·
  doc `category='datafeed'` ของ context นั้น = `declared` · golden ที่ `added_by` ว่างใน category ของ context นั้น = `declared` ·
  ระดับ hierarchy = `manual` · ค่า hierarchy `auto` = `inferred` · ที่เหลือ = `manual`
- ตารางคิว `knowledge_proposals` (`table_name`, `row_key` JSON, `proposed` JSON, `source`, `confidence`, `reason`, `status`, `created_at`)
  + unique index บางส่วน **หนึ่งข้อเสนอที่รออยู่ต่อคีย์ต่อผู้เสนอ** (`WHERE status = 'proposed'`)
- test: `tests/unit/test_migrate_knowledge_provenance.py` (3 ข้อ — ค่าของแต่ละกลุ่ม, รันซ้ำไม่เปลี่ยน + trigger, คิวรับหนึ่งข้อเสนอต่อคีย์ต่อผู้เสนอ)

### 8.1 ซ้อมบนสำเนาสด (จาก backup §0)

| | ผล |
|---|---|
| รอบ 1 | +25 คอลัมน์ · ติดป้าย 2,444 แถว · ทุกแถว `active`, `confidence` NULL · คิว 0 แถว |
| ค่าที่ได้ | contexts declared 4 / manual 5 · metadata declared 348 / manual 159 · rules manual 72 · golden declared 74 / manual 58 · mapping manual 192 · hierarchy manual 22 · values inferred 1,444 / manual 2,246 · warnings manual 1 · docs declared 71 / manual 5 |
| รอบ 2 | ติดป้าย 0 แถว · dump ทั้งไฟล์เท่ากับหลังรอบ 1 |
| เทียบก่อน/หลังทีละตาราง ทีละแถว | ทุกคอลัมน์เดิมของทุกแถวเท่าเดิม (รวม `updated_at`) — ต่างเฉพาะ `source` ของ hierarchy ตามที่ประกาศ (`auto`→`manual` 11, `auto`→`inferred` 1,444) · schema ต่างเฉพาะคอลัมน์ใหม่ + ตารางคิว + index · ตารางอื่นเท่าเดิมทุกแถว · `integrity_check` ok |

**ที่เจอระหว่างซ้อมแล้วแก้:** `vanna_documentation` มี trigger ที่ตั้ง `updated_at` ใหม่ทุกครั้งที่ UPDATE → รุ่นแรกทำให้ `updated_at` ของ doc 76 แถวเปลี่ยน
(ตัวตรวจจับได้) → migration ถอด trigger ระหว่างติดป้ายแล้วใส่กลับด้วย SQL เดิมใน transaction เดียวกัน (SQL ของ trigger เท่าเดิม, การแก้จริงยังประทับเวลา — มี test)

### 8.2 code ที่รันอยู่ + DB ที่ migrate แล้ว = prompt เท่าเดิมทุกไบต์

รัน `QueryEngine.query` จริงแบบ in-process (code ของ HEAD ใน worktree แยก = code บนของจริง) บนสำเนา — ดักที่ `httpx.AsyncClient.post`
(ทางเดียวที่ provider ส่งออก) เก็บ body ที่จะส่งให้ LLM ทุกครั้ง แล้วตอบด้วยค่าตายตัว: คำถามจริงของ portal 15 ข้อ (scope ตาม hook) + golden legacy 49 ข้อ
= **64 คำถาม / 159 LLM calls** (pass 1, pass 2, อธิบายผล) → **ก่อน vs หลัง migrate: 64/64 เท่ากันทุกไบต์** · รันซ้ำ DB เดิม: 64/64

→ migration ขึ้นของจริงก่อน code ได้โดยคำตอบไม่เปลี่ยน · ถอย code ของ 8.1 **ไม่ต้องถอย DB**

**บทเรียนการวัด — RAG ไม่นิ่งเอง:** Chroma ดึงเอกสารไม่เหมือนกันระหว่างรอบแม้ DB และ store เดียวกัน (golden legacy 4–6 ใน 14 ข้อได้ "Relevant Rules & Dictionary"
ต่างกัน — ลำดับ/เอกสารที่ขอบ top-10 / threshold) → การเทียบรอบแรกโดยไม่ตรึง RAG เห็น "ต่าง" 14/64 ซึ่งเป็นเสียงรบกวนทั้งหมด ·
วิธีเทียบ: บันทึกข้อความ RAG รอบแรก (คีย์ = brain ของ workspace + คำถาม — คำถาม "รายได้รวม" มีทั้งใน brain `nt-report` และ `default`) แล้วเล่นซ้ำในรอบถัดไป ·
ข้อนี้ใช้กับ Exit ข้อ 11 ด้วย และอธิบายส่วนหนึ่งของ "โมเดลผันผวน ±1 ข้อ" ในการวัดคำถามจริง / legacy

### 8.3 ของจริง — คำสั่งให้เจ้าของรัน (ยังไม่รัน)

```bash
cd /Users/seal/Documents/GitHub/AI
D=~/nt-ai-backups/p8-1-migrate-$(date +%Y%m%d-%H%M%S) && mkdir -p $D && sqlite3 "file:config.db?mode=ro" ".backup $D/config.db" && sqlite3 $D/config.db "PRAGMA quick_check" && echo $D
venv/bin/python scripts/migrate_knowledge_provenance.py
sqlite3 "file:config.db?mode=ro" "PRAGMA quick_check; SELECT source, status, COUNT(*) FROM master_hierarchy_values GROUP BY 1, 2;"
```
- ผลที่ควรเห็น = ตัวเลข §8.1 (ถ้า config ไม่ได้เปลี่ยนตั้งแต่ 18:02) · ไม่ต้อง restart เพื่อ migration อย่างเดียว (code ที่รันอยู่ไม่อ่านคอลัมน์ใหม่ — §8.2)
- รันซ้ำหลัง restart ด้วย code ของ 8.1 เพื่อติดป้ายแถวที่ code เก่าเขียนระหว่างนั้น (idempotent) · ถ้าเจอ `database is locked` (server กำลังเขียน) = รันซ้ำได้
- **ถอยกลับ:** ถอย code ไม่ต้องถอย DB · ถ้าจำเป็นต้องถอย DB จริง: หยุด server → `cp $D/config.db config.db` (เสียการแก้ config หลัง backup) → start server
