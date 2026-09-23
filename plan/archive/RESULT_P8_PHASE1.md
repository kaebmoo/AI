# RESULT Plan 8 Phase 8.1 — โมเดลความรู้: ที่มา + ความมั่นใจ + สถานะ

**สถานะ (2026-09-21 ดึก):** ข้อ 7–11 ✅ บนสำเนา (Exit §11 — legacy 7–8/37 เท่ากับ base วันเดียวกัน) · ยังไม่ push ·
**✅ ขึ้นของจริงแล้ว 22:06** (เจ้าของทำเองตาม §12.2 — §12.5) · ช่วง 19:57–22:06 server รัน 8.1 ครึ่งหนึ่งบน DB ที่ยังไม่ migrate (§12.1) ·
**ตรวจโดย Codex 2026-09-22: 9 ข้อ แก้ครบ (§14)** — ถึงของจริงเมื่อ start server ครั้งถัดไป (ไม่ต้อง migrate)
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

### 8.3 ของจริง — คำสั่งให้เจ้าของรัน (ยังไม่รัน) — **ใช้ §12.2 แทน**

> เขียนตอน server ยังรัน code ก่อน 8.1 · ตั้งแต่ 19:57 server รัน `4eb2bbf` ซึ่ง ORM อ่านคอลัมน์ใหม่แล้ว — ข้อ "ไม่ต้อง restart / code ที่รันอยู่ไม่อ่านคอลัมน์ใหม่" ข้างล่างจึงไม่จริงอีก (§12.1)

```bash
cd /Users/seal/Documents/GitHub/AI
D=~/nt-ai-backups/p8-1-migrate-$(date +%Y%m%d-%H%M%S) && mkdir -p $D && sqlite3 "file:config.db?mode=ro" ".backup $D/config.db" && sqlite3 $D/config.db "PRAGMA quick_check" && echo $D
venv/bin/python scripts/migrate_knowledge_provenance.py
sqlite3 "file:config.db?mode=ro" "PRAGMA quick_check; SELECT source, status, COUNT(*) FROM master_hierarchy_values GROUP BY 1, 2;"
```
- ผลที่ควรเห็น = ตัวเลข §8.1 (ถ้า config ไม่ได้เปลี่ยนตั้งแต่ 18:02) · ไม่ต้อง restart เพื่อ migration อย่างเดียว (code ที่รันอยู่ไม่อ่านคอลัมน์ใหม่ — §8.2)
- รันซ้ำหลัง restart ด้วย code ของ 8.1 เพื่อติดป้ายแถวที่ code เก่าเขียนระหว่างนั้น (idempotent) · ถ้าเจอ `database is locked` (server กำลังเขียน) = รันซ้ำได้
- **ถอยกลับ:** ถอย code ไม่ต้องถอย DB · ถ้าจำเป็นต้องถอย DB จริง: หยุด server → `cp $D/config.db config.db` (เสียการแก้ config หลัง backup) → start server

---

## 9. กฎเดียวของตัวเขียนทุกตัว — ข้อ 9 (`ae1b1ad`, `fa37c24`, `c4dcce3`, `0a05000`)

`app/services/provenance.py` — กฎเดียวที่ตัวเขียนทุกตัวเรียก:

| ผู้เขียน | เปลี่ยนแถวที่มีอยู่ได้เมื่อ | ไม่ได้ = |
|---|---|---|
| คน (`manual`) | เสมอ — แถวเป็นของคนนั้น (แก้เฉพาะช่องที่ contract ไม่ประกาศ เช่น keywords / priority / กลุ่มคอลัมน์ = แถว `declared` ยังเป็น `declared`) | — |
| contract (`declared`) | แถว `declared` ของตัวเอง หรือแถวของเครื่อง | ข้อเสนอเข้าคิว (D-C) — แถวของคนใช้ต่อ |
| เครื่อง (`inferred` / `learned`) | แถวของเครื่องเท่านั้น | ข้อเสนอเข้าคิว |
| ทุกคนยกเว้นคน | ไม่แตะแถว `rejected` | — |

ที่มาไม่รู้ (NULL / `auto` เดิม) = ของคน · คิว `knowledge_proposals`: หนึ่งข้อเสนอที่รออยู่ต่อคีย์ต่อผู้เสนอ — ข้อเสนอใหม่**รวมทีละช่อง**เข้ากับที่รออยู่
(ตัวเขียนของเครื่องสองตัวเสนอคนละช่องของแถวเดียวกันได้ — analyzer กับตัวตรวจกลุ่มคอลัมน์) · ข้อเสนอที่คนปฏิเสธแล้ว หรือที่รออยู่ด้วยเนื้อหาเดิม = ไม่เขียนซ้ำ

| ตัวเขียน | ก่อน | หลัง |
|---|---|---|
| admin API ทุกตาราง, admin agent tools, hierarchy CRUD, context CRUD | ไม่บอกที่มา (hierarchy บังคับ `manual`) | `manual` / `active` · สร้าง keyword ที่เครื่องแค่เสนอไว้ = คนรับไป · รับระดับที่รออยู่ = ค่าที่ extract ไว้ใช้ได้ด้วย |
| `datafeed_knowledge` (3 ฟังก์ชัน) | ลบแล้วใส่ใหม่ทุกครั้ง, ตั้ง `is_active=1` กลับ | `declared` ตามกฎ · ค่าไม่เปลี่ยน = ไม่เขียน (re-sync contract เดิมไม่เปลี่ยนแม้แต่เวลา) · ช่องของ admin ไม่แตะ · ที่ contract เลิกประกาศ = ลบเฉพาะแถวของ contract |
| `gen_golden_from_controls.py` | ลบทั้ง category | `save_examples` — แถวของคนในหมวดเดียวกันอยู่ต่อ (golden 8 ข้อของ F11) |
| `bootstrap_from_view` | ทับ level ของคนโดยไม่เปลี่ยนป้าย | `inferred` / **`proposed`** — รอคนรับ; ระดับของคน = ข้อเสนอ |
| `extract_hierarchy.py` | เขียน label + `updated_at` ของ level ทุกรอบ | level: ใส่เมื่อยังไม่มีเท่านั้น · value: `inferred` ตามสถานะของ level; ของคนไม่แตะ |
| context onboarding | `INSERT OR REPLACE` (แถวใหม่ — `workspace_id` / `source_id` หาย), golden ซ้ำทุกรอบ | upsert ที่แก้ได้เฉพาะแถวของเครื่อง + คำสั่งเสนอเข้าคิวเมื่อแถวเป็นของคน (ยังเป็นข้อความ SQL — หน้า admin preview แล้วส่งกลับ) · golden ใช้คำถามเป็นคีย์ · hierarchy / warnings ยังล้มด้วย NOT NULL เหมือนเดิม (8.2 เขียนใหม่) |
| metadata propagation, analyzer import, กลุ่มคอลัมน์อัตโนมัติ | เติม / ทับ | แถวของเครื่องเติมได้, แถวของคน = ข้อเสนอ · analyzer import ย้ายไป session ของ config.db (ล้มมาตั้งแต่แยก DB) |
| ตัวเรียนรู้ (scheduler) | auto-apply ≥ 0.8 (ไม่เคยถึง) + session ผิด DB | ไม่ auto-apply แล้ว: keyword ใหม่ = แถว `learned` / `proposed`; keyword ของคน = ข้อเสนอ |
| `/chat/train` | session ผิด DB; user ทั่วไปปิด + ทับ golden ของ admin ได้ | config.db · admin = `manual` / `active` · user = `learned` / `proposed` ไม่แตะของคนอื่น |
| feedback review, thumbs-up ของ admin | session ผิด DB, อ่าน `chat.sql_query` ที่ไม่มี / train โดยไม่มีแถว | config.db, `generated_sql` / สร้างแถว golden `manual` ก่อน train (อยู่รอด Sync Brain) |

**ทำไม extract ไม่เสนอเมื่อค่าแม่ในข้อมูลไม่ตรงกับของคน** (ข้อความใน `scripts/extract_hierarchy.py` อ้างหมวดนี้): รุ่นแรกเสนอ — บนสำเนาของจริงได้ 123 ข้อเสนอ
ใน `revenue_org` / `revenue` ซึ่ง **122 ข้อเป็นขยะ**: `parent_column` ของ `revenue_org` คือ `"GROUP"` ที่ `revenue_search` ไม่มี — SQLite อ่านชื่อในเครื่องหมายคำพูดที่ไม่ใช่คอลัมน์
เป็น**ข้อความ** จึงได้ค่าแม่ `'GROUP'` ทุกแถว; ที่เหลือคือค่าที่มีหลายค่าแม่ในข้อมูล (ข้อมูลอ่านได้แถวละหนึ่งคู่) → ค่าแม่ที่อ่านจากข้อมูลไม่ใช่ข้อเท็จจริงแบบที่คนตัดสิน
จึงไม่เสนอ (คิวที่ยาวด้วยขยะ = ไม่มีคิว, PLAN_8 §7) · **`parent_column = "GROUP"` ของ `revenue_org` เป็นบั๊กของข้อมูล config เดิม — เสนอแก้แยก**

**test:** `tests/unit/test_provenance_{people,contract,machines,learner}.py` — ตัวเขียนแต่ละตัวรันซ้ำแล้วแถวของคน/contract เท่าเดิมทุกคอลัมน์

## 10. ตัวอ่านใช้เฉพาะ `active` — ข้อ 10 (`c75af27`, `38b69c8`)

- **กรอง `status = 'active'` เพิ่มจาก `is_active`:** ส่วนของ system prompt (metadata, กฎ, mapping, กฎลำดับชั้น), การตรวจระดับชั้น + ชื่อที่ระดับอื่นถือ
  (ตัวอ่านใหม่ของ `e05b0f6`), value lookup, พจนานุกรมคำ, ตารางที่ context ใช้ได้, กฎตรวจ SQL, คำเตือนข้อมูล, Sync Brain (กฎ, mapping, doc, golden,
  สรุปลำดับชั้นต่อ context), สิทธิ์ของ key (`allowed_contexts`, การผูก key, `GET /query/contexts`, allowlist ของ MCP facade), MCP metadata server (11 จุด)
- **ไม่กรอง:** หน้า admin (ต้องเห็นข้อเสนอ — hierarchy คืน `status` ด้วยแล้ว), การผูก source / retention / workspace ของ context, dedup, config GC
- **ด่านตอนเริ่ม server:** config DB ที่ยังไม่มีคอลัมน์ = ไม่ยอมเริ่ม พร้อมบอกคำสั่ง migrate — ตัวอ่านหลายตัวกลืน error แล้วคืนค่าว่าง
  (ถ้าไม่มีด่าน DB ที่ลืม migrate จะทำให้ prompt ขาด schema / กฎ / mapping แบบเงียบ)
- **ค่าคงที่ใน prompt path** (`38b69c8`): กฎข้อ 5 "ใช้ `year` และ `month` … `CAST(month AS INTEGER)`" (ไทย) / ข้อ 4 (อังกฤษ) → ชี้ไปที่หัวข้อ Date Handling
  ที่บอกคอลัมน์เวลาของตารางนั้นเอง + คงวินัย CAST แบบทั่วไป — prompt ทุก context เปลี่ยน จึงวัดคำถามจริง + legacy ก่อน/หลัง (§11)
- **ตัวอย่าง "เดือนมกราคม 2568" / "Q1/2567" ใน prompt อธิบายผล — แก้แล้วถอยกลับ (`d06d497`):** เอาปีออกแล้ว P11 ("บริการใดมีการเติบโตมากสุด") ไม่บอกงวดที่เทียบ
  2 รอบจาก 2 · คงตัวอย่างเดิมผ่าน 4 จาก 4 (§11.1) → ยังเป็นค่าคงที่ใน prompt path — ค้าง (§13 ข้อ 2)
- **test ที่ล้มบน code เดิม:** `tests/unit/test_provenance_readers.py` (ตัวอ่านทุกกลุ่มกับแถว active / proposed / rejected — ล้ม 4/4 บน `4eb2bbf`, ผ่านหลังแก้)
  · `test_prompt_date_instructions.py` +1 (ล้มบน code เดิม)

---

## 11. Exit 8.1 — วัดบนสำเนา (`d06d497` + test `7e929c0`)

| เกณฑ์ | ผล |
|---|---|
| ตัวเติมทุกตัวรันซ้ำสองรอบ → แถว `declared` / `manual` ไม่เปลี่ยนแม้แต่ตัวเดียว | ✅ test ของตัวเติม 10 ตัว: contract (`sync_knowledge` — dump ทั้งไฟล์หลังรอบสองเท่ารอบแรก ไม่เปลี่ยนแม้แต่เวลา), `save_examples` (รอบสอง = 0 / 0 / 0), bootstrap, extract, onboarding, คัดลอก metadata ไป view, analyzer import, กลุ่มคอลัมน์อัตโนมัติ, ตัวเรียนรู้, `/chat/train` ของ user → แถวของคน / contract เท่าเดิมทุกคอลัมน์ (`tests/unit/test_provenance_{contract,machines,learner}.py` — 3 ตัวที่เดิมรันรอบเดียวได้รอบสองใน `7e929c0`) |
| prompt ของคำขอเดิมเท่าเดิมทุกไบต์เมื่อทุกแถว `active` | ✅ วิธี §8.2 (in-process, ดักที่ `httpx`, RAG ตรึงด้วยบันทึก/เล่นซ้ำ) 64 คำถาม / 159 calls บน DB ที่ migrate แล้ว: code เดิมสองรอบ 64/64 · **ตัวอ่าน `c75af27` เทียบ `4eb2bbf` 64/64 เท่ากันทุกไบต์** · **`d06d497` เทียบ `4eb2bbf`: ต่างเฉพาะ 2 บรรทัดของกฎข้อ 5 (ไทย) ใน 106 จาก 159 calls** — ที่เหลือรวม prompt อธิบายผลเท่าเดิมทุกไบต์ (prompt อังกฤษไม่อยู่ในเส้นทางของ provider ที่ใช้ — ไม่มีใน 159 calls) |
| pytest ผ่าน | ✅ **1161 passed, 3 skipped** (1110 ก่อน 8.1) · lint ของ CI (`ruff check app mcp_servers --select E9,F63,F7,F82`) ผ่าน · unused import ในไฟล์ที่ 8.1 แตะไม่เพิ่มแม้แต่ตัวเดียว |
| คำถามจริงไม่ต่ำกว่า 8/12 | ✅ `d06d497` **8/12 · 10/15 ทั้งสองรอบ** (F3, F4) + บนสำเนาของจริงหลังซ้อมขึ้น 8/12 · 10/15 (L1) · code เดียวกันก่อน commit 7, 7 (F1, F2 — ข้อที่หลุดเป็นข้อความอธิบายผล §11.1) · base วันเดียวกัน 9, 8, 7, 8 |
| legacy ไม่ต่ำกว่า 8/37 | ⚠ **7/37, 8/37** — base บนสำเนาเดียวกันวันเดียวกัน **7/37, 7/37** · ข้อที่ผ่านชุดเดียวกันทุกรอบ (#25 #26 #29 #30 #32 #35 #38) + #27 ผ่านหนึ่งรอบของ 8.1 → ไม่มี regression; 8/37 ของ 8.0 อยู่ในช่วงผันผวน ±1 ของ base (§11.2) |

### 11.1 คำถามจริง — ทุกรอบ (server ซ้อม restart ก่อนทุกรอบ · สำเนาที่ migrate แล้ว · key ซ้อม)

B = base (`0078dcf` + fix 8.0 สาม commit = branch `p8.0-without-8.1`) · X = `38b69c8` (กฎข้อ 5 + ตัวอย่างไม่มีปี) · F1–F2 = code ของ `d06d497` ก่อน commit ·
F3–F4 = `d06d497` · L0 / L1 / R1 / R2 = รอบบนสำเนาของจริง §12 (L0 = สภาพของจริงตอนนี้ · L1 = หลังซ้อมขึ้น · R1 / R2 = ถอยกลับระดับ 1 / 2)

| ข้อ | B1 | B2 | B3 | B4 | X1 | X2 | F1 | F2 | F3 | F4 | L0 | L1 | R1 | R2 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| P01 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P02 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| P03 | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| P04 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P05 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P06 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P07 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P08 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| P09 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P10 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| P11 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| P12 | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| P13 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| P14 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| P15 | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **P01–P12** | **9** | **8** | **7** | **8** | **7** | **7** | **7** | **7** | **8** | **8** | **8** | **8** | **6** | **9** |
| ทั้ง 15 | 11 | 10 | 9 | 9 | 9 | 9 | 9 | 9 | 10 | 10 | 10 | 10 | 8 | 11 |

- **หลุดทุกรอบทุก code:** P02, P08, P10, P14 (ข้อค้างจาก 8.0)
- **P11** หลุดเฉพาะ X (2/2) — "ไม่บอกฐาน (ราย product ส.ค. 2569 เทียบ ส.ค. 2568)" = ตัวอย่างที่เอาปีออกทำให้ข้อความไม่บอกงวดที่เทียบ → ถอย (`d06d497`) ·
  R1 หลุดด้วยเหตุอื่น: โมเดลจัดอันดับด้วยยอดเพิ่ม (บาท) แทนอัตรา %
- **P03 / P04** หลุดที่ข้อความเท่านั้น — SQL และตัวเลขเหมือนรอบที่ผ่าน: P03 เขียน "ปี 2566" หนึ่งประโยคขณะที่ทุกเดือนเขียน 2569 (เกิดบน base ด้วย: B3, B4),
  P04 เขียน "ประมาณ 6,630 ล้านบาท" แทน 6,630.81
- **P12 "ค่าใช้จ่ายมีไหม"** (`feed_revenue` ไม่มีค่าใช้จ่าย): ผ่านเมื่อโมเดลเขียน `SELECT NULL AS "ค่าใช้จ่าย"`, หลุดเมื่อรวมรายได้แล้วบอกว่าไม่มีข้อมูลค่าใช้จ่าย
  ("ปฏิเสธแต่มีตัวเลข") · **code ที่ไม่มีกฎข้อ 5 ใหม่ 3/7 · มี 0/7** (Fisher ด้านเดียว p ≈ 0.10) — กับกฎใหม่ SQL ใช้ `year_month = 202608` แทน
  `year = 2026 AND CAST(month AS INTEGER) = 8` · 8.0 วัดข้อนี้บนของจริงได้ 0/5 และเป็นข้อค้างของเจ้าของ ("ต้องเป็นกฎของ context") → §13 ข้อ 1

### 11.2 legacy eval (`run_eval --legacy`, in-process บนสำเนาสดแยกรอบ, สลับ base / 8.1)

| รอบ | code | exact | value | รวม / 37 | golden_broken |
|---|---|---:|---:|---:|---:|
| lb1 | base | 5 | 2 | 7 | 12 |
| la1 | `38b69c8` | 5 | 2 | 7 | 12 |
| lb2 | base | 5 | 2 | 7 | 12 |
| la2 | `38b69c8` | 6 | 2 | 8 | 12 |

prompt SQL ของ `38b69c8` = ของ `d06d497` (ต่างกันเฉพาะ prompt อธิบายผล ซึ่ง legacy ไม่ให้คะแนน) · ข้อที่เปลี่ยนแบบของความผิด (ผิดทั้งสองฝั่ง):
#2 `generation_failed` (UNION ที่มี ORDER BY / LIMIT ในแต่ละส่วน — คำถามไม่มีเวลา), #39 `execution_failed` (provider `ReadTimeout`)

---

## 12. ของจริง — สถานะ + คำสั่ง (ซ้อมครบลำดับบนสำเนาของสภาพจริงแล้ว)

### 12.1 สภาพตอนนี้ — server รัน 8.1 ข้อ 8–9 บน config DB ที่ยังไม่ migrate

| เวลา | |
|---|---|
| 19:02–19:21 | 8.1 ข้อ 8–9 ลง `main` (`c574cf9` … `0a05000`) — ORM ของ 6 ตารางประกาศ `source` / `status` / `confidence`, ตัวเขียนเขียนคอลัมน์ใหม่ |
| 19:38 | session 8.0 commit fix หลังขึ้นของจริงต่อท้าย (`3b216ab`, `e05b0f6`, `d273529`, `4eb2bbf`) — คำสั่งขึ้นใน `RESULT_P8_PHASE0` §10 = "ไม่มีการเขียน DB — restart แบบเดิม" |
| 19:57:32 | เจ้าของ restart port 8000 (PID 74986) → โหลด **`4eb2bbf` = fix 8.0 + 8.1 ข้อ 8–9** บน config DB **ที่ยังไม่ migrate** · ไม่มี app ที่แก้ค้างในไฟล์ขณะนั้น (แก้ตัวอ่านเริ่ม 20:01) |
| 14:53 → ตอนเขียน | ไม่มีคำถามจริงเข้ามา (`query_audit` ล่าสุด #281) |

**ผลกระทบ — วัดบนสำเนาที่จำลองสภาพนี้:** server `4eb2bbf` + config DB ของจริง (backup แบบ `mode=ro` 21:04) + สลับไฟล์เป็น `d06d497` ใต้ server ที่รันอยู่ (= ไฟล์บนดิสก์ของจริงตอนนี้)
- **คำถามของ portal ปกติ** — 15/15 ตอบ ไม่มี error, 8/12 · 10/15 (L0) · ทุก module ในเส้นทางคำถามโหลดตอนเริ่ม server (ตรวจ `sys.modules` หลัง startup) = code ของ `4eb2bbf`
- **เสีย:** ทุกทางที่อ่าน/เขียน 6 ตารางผ่าน ORM → `no such column` — หน้า admin ของ mappings / rules / golden / warnings / vanna docs / schema columns,
  ปุ่มแก้ SQL ใน chat, review feedback, thumbs-up ของ admin · config GC (log WARNING) · ตัวเรียนรู้ (log, ไม่เขียนอะไร) ·
  คำเตือนข้อมูล: ตัวโหลดกลืน error แล้วใช้ชุดตายตัว ซึ่งเท่ากับชุดใน DB (`OTHER_REVENUE_NOT_NET` ตัวเดียว) → คำตอบไม่ต่าง
- **จะเสียเมื่อถูกเรียกครั้งแรก:** onboarding (`context_onboarding` โหลดตอนใช้ = ไฟล์ของ `d06d497`) · MCP metadata server ถ้า process ลูกเริ่มใหม่
- **ไม่มีข้อมูลเสีย** — ทุกทางที่เสียคือ error ไม่ใช่การเขียนผิด
- **สาเหตุ:** server รันจาก working tree ของ `main` → restart = ขึ้นทุก commit บน `main` · commit ที่ต้อง migrate ก่อนลง `main` ก่อน migrate ของจริง
  และคำสั่ง restart ของอีกงานไม่ได้ไล่ `git log <code ที่รันอยู่>..HEAD` (บทเรียน — `FIX_NOTES`)

### 12.2 ขึ้นของจริง — คำสั่งให้เจ้าของรัน

```bash
cd /Users/seal/Documents/GitHub/AI
# 1. backup สด (อ่านผ่าน connection mode=ro) + ตรวจ
D=~/nt-ai-backups/p8-1-golive-$(date +%Y%m%d-%H%M%S) && mkdir -p $D && sqlite3 "file:config.db?mode=ro" ".backup $D/config.db" && sqlite3 "file:app.db?mode=ro" ".backup $D/app.db" && sqlite3 $D/config.db "PRAGMA quick_check" && sqlite3 $D/app.db "PRAGMA quick_check" && echo $D
# 2. migrate — ขณะ server เดิมยังรัน (หน้า admin ของ code ที่รันอยู่กลับมาใช้ได้ทันที)
venv/bin/python scripts/migrate_knowledge_provenance.py
# 3. restart port 8000 แบบเดิม: Ctrl-C ใน terminal ของมัน แล้ว
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
# 4. หลัง server ขึ้น (terminal อื่น) — ติดป้ายแถวที่ code เดิมเขียนระหว่างข้อ 2–3 (idempotent)
venv/bin/python scripts/migrate_knowledge_provenance.py
```
- **ที่ควรเห็น** (สำเนาของจริง 21:04): ข้อ 2 = `Added …` + `Labelled 2444 row(s) whose source was unknown` + contexts declared 4 / manual 5 · metadata declared 348 / manual 159 ·
  rules manual 72 · golden declared 74 / manual 58 · mapping manual 192 · hierarchy manual 22 · values inferred 1,444 / manual 2,246 · warnings manual 1 ·
  docs declared 71 / manual 5 (ตรงกับ §8.1 ทุกตัว) · ข้อ 4 = `Labelled 0 row(s)` (มากกว่า 0 ได้ถ้ามีคนแก้ config ระหว่างข้อ 2–3)
- **ตรวจหลัง restart:** log มี `Application startup complete` — ถ้าข้อ 2 ไม่ได้รัน server จะไม่เริ่มและบอก
  `config DB has no provenance columns on … — run: venv/bin/python scripts/migrate_knowledge_provenance.py` ·
  คำถามจริงถัดไป `sqlite3 "file:app.db?mode=ro" "SELECT id, created_at, context_name, row_count, error FROM query_audit ORDER BY id DESC LIMIT 3"` → `error` ว่าง · หน้า admin mappings เปิดได้
- **ผลที่ซ้อมได้ (ลำดับเดียวกันบนสำเนา):** ข้อ 2 ขณะ server `4eb2bbf` รัน → คำถามใหม่ 3 ข้อที่ไม่อยู่ใน cache ตอบ 200 · ข้อ 3 ด่านเริ่ม server ผ่าน ·
  ข้อ 4 ติดป้าย 0 · portal 8/12 · 10/15 ไม่มี `no such column` และไม่มี WARNING ของ config GC (L1)
- **ให้ข้อ 3 ตามข้อ 2 ทันที:** code ที่รันอยู่ (`4eb2bbf`) มีตัวเรียนรู้ของ 8.1 (เขียนแถว `learned` / `proposed` ที่ `is_active = 1`) แต่ยังไม่มีตัวอ่านที่กรอง `status` —
  ตัวเรียนรู้รัน 30 วินาทีหลังเริ่ม server แล้วทุก 6 ชม. (ครั้งถัดไป ~01:58, ~07:58) ถ้าข้อ 2 กับ 3 คร่อมรอบนั้น ข้อเสนอของมันเข้า prompt จนกว่าจะ restart

### 12.3 ถอยกลับ — ซ้อมแล้วทั้งสองระดับ

```bash
cd /Users/seal/Documents/GitHub/AI
# ก. ทุกระดับ: ซ่อนข้อเสนอจาก code ก่อน 8.1 (อ่าน is_active ไม่อ่าน status)
for t in schema_contexts schema_business_rules golden_examples schema_semantic_mapping master_hierarchy master_hierarchy_values data_warnings vanna_documentation; do sqlite3 config.db "UPDATE $t SET is_active = 0 WHERE status != 'active'"; done
# ข. code — ระดับ 1: ถอยตัวอ่าน + กฎข้อ 5 (= code ที่รันอยู่ตอนนี้)
git checkout 4eb2bbf -- app mcp_servers scripts
#    หรือ ระดับ 2: ถอย 8.1 ทั้งหมด (= 8.0 + fix ของมัน — branch ในเครื่อง ไม่ได้ push)
git checkout p8.0-without-8.1 -- app mcp_servers scripts
# ค. restart port 8000 แบบเดิม
```
- ซ้อมบนสำเนาที่ migrate แล้ว: ระดับ 1 → 6/12 · 8/15 (R1 — P03 ข้อความ, P11 โมเดลเลือกยอดเพิ่มแทนอัตรา) · ระดับ 2 + ก. → 9/12 · 11/15 (R2) ·
  ก. บนสำเนาวันนี้เปลี่ยน 0 แถว (ยังไม่มีข้อเสนอ) · `schema_metadata` ไม่มี `is_active` — 8.1 ไม่เขียนแถว `proposed` ลงตารางนี้ (ข้อเสนอไปคิว)
- ระดับ 2 ทิ้งไฟล์ที่ 8.1 เพิ่มไว้ (`app/services/provenance.py`, `scripts/migrate_knowledge_provenance.py`) — code เดิมไม่ import
- **ไม่ต้องถอย DB** (คอลัมน์เพิ่มอย่างเดียว — code เดิม + DB ที่ migrate แล้ว = prompt เท่าเดิม §8.2) · ถ้าต้องการ DB ก่อน migrate จริง:
  หยุด server → `cp $D/config.db config.db` (เสียการแก้ config หลัง backup) → start
- **กลับมาใช้ 8.1:** `git checkout main -- app mcp_servers scripts` + restart (migration ยังอยู่)
- `git revert d06d497 38b69c8 c75af27` ได้ code เท่ากับระดับ 1 ทุกไบต์ (ตรวจแล้ว) · revert ทั้ง 8.1 ชนที่ไฟล์ผลนี้ → ใช้ `git checkout` แทน

### 12.4 ของจริงที่ยังไม่ได้ทำ
- migration / restart — รอเจ้าของ (§12.2) · push — ยังไม่ได้สั่ง
- key ของ portal (id 4) ไม่ได้แตะ · port 8000 ไม่ถูกเรียกเลย — ทุกการวัดบน port 8001 + สำเนา · ของจริงอ่านแบบ `mode=ro` เท่านั้น (backup 21:04, `query_audit`, schema)

---

### 12.5 ขึ้นของจริงแล้ว — 2026-09-21 (เจ้าของทำเอง ตาม §12.2)

| เวลา | ขั้น | หลักฐาน (อ่านแบบ `mode=ro`) |
|---|---|---|
| 22:06:00 | backup สด | `~/nt-ai-backups/p8-1-golive-20260921-220600/` |
| 22:06 | migrate | ป้ายทุกตารางตรงกับ §8.1 ทุกตัว · ไม่มี `source` ว่าง · คิว `knowledge_proposals` 0 แถว |
| 22:06:26 | restart port 8000 ด้วย `1857dbe` (code = `d06d497`) | PID 82961 · ไฟล์ app บนดิสก์ = HEAD |
| 22:08–22:11 | คำถามจริงผ่าน portal 4 ข้อ (`query_audit` #282–#285) | ไม่มี error ทั้ง 4 · #282 "รายได้แต่ละกลุ่มธุรกิจ" ✅ งวดอ้างอิง · #284 "รายได้สะสม รายกลุ่มธุรกิจ" ✅ `revenue_ytd` ของ 202608 · **#283 "ขอเป็นรายได้สะสม ของปีนี้" ❌** `SUM(revenue_ytd) … WHERE year = 2026` = **115,090.16 ล้านบาท** (ถูก = 26,036.32) · #285 "มีข้อมูลค่าใช้จ่ายไหม" ❌ ตอบด้วยรายได้ (P12 เดิม) |

**#283 มีมาก่อน 8.1:** ถาม #282–#284 + "รายได้สะสมปีนี้เท่าไหร่" (scope เดียวกับ portal) บนสำเนาของจริงหลัง migrate — base (`p8.0-without-8.1`) 2 รอบ vs HEAD 2 รอบ (restart ก่อนทุกรอบ):
#283 ได้ SQL เดียวกันและ 115,090.16 ทั้ง 4 รอบ · "รายได้สะสมปีนี้เท่าไหร่" ถูก (26,036.32, `year = 2026 AND month = 8`) ทั้ง 4 รอบ · #282 / #284 ถูกทั้ง 4 รอบ ·
metadata ของ `revenue_ytd` เท่าเดิมก่อน/หลัง 8.1 (`is_summable = 0`, "point-in-time, ห้าม sum ข้ามงวด") — 115,090 คือตัวเลขเดียวกับที่ `FIX_NOTES` (F11) บันทึกว่าแก้ด้วย metadata แล้ว → §13 ข้อ 7

**ยังไม่ได้ตรวจ (ต้อง login / UI — เจ้าของ):** หน้า admin 6 ตาราง + hierarchy (เสียช่วง 19:57–22:06), chat บนเว็บของ context legacy, Telegram,
ปุ่มแก้ SQL / thumbs-up ของ admin · **เฝ้าดู:** ตัวเรียนรู้ ~04:07 / ~10:07 (ทุก 6 ชม. จาก 22:06:56 — ข้อเสนอต้องเป็น `proposed` และไม่ถึง prompt),
config GC ~22:07 วันถัดไป (ไม่มี `no such column`), DataFeed publish ครั้งถัดไป (re-sync ด้วยกฎใหม่ — แถวของ admin เข้าคิว)

## 13. ค้าง / เสนอ — ไม่แก้เอง

1. **กฎข้อ 5 กับ P12** (§11.1) — คง `38b69c8` (ความขัดกันของ `feed_ebt` / `feed_expense` / `pl_costtype` หายไป) แล้วทำ P12 เป็นกฎของ context ตามข้อค้างเดิม ·
   หรือถอย `38b69c8` + `d06d497` = P12 กลับเป็น coin flip แต่ความขัดกันกลับมา · ข้อเสนอ: คง
2. **ตัวอย่างปีใน prompt อธิบายผล** ("เดือนมกราคม 2568", "Q1/2567") ยังเป็นค่าคงที่ใน prompt path — เอาปีออกตรง ๆ ทำให้ P11 หลุด → ทางเลือก: ตัวอย่างที่ใช้งวดอ้างอิงของคำขอ
   (ค่าเดียวกับ `hybrid_flow.scope_note`) — ต้องวัดคำถามจริงสองรอบขึ้นไป
3. ค่าคงที่ที่เหลือจาก §7.4 ไม่ได้แตะใน 8.1: `hybrid_flow.py` "ปี 2569" ใน `scope_note`, `datafeed_knowledge.py` ตัวอย่าง พ.ศ. 2568 → `202501` ใน `instruction_th`
4. จาก §7.7 + ระหว่างซ้อม: ของทดสอบในของจริง (golden 41–50 + `TEST_001`) · `parent_column = "GROUP"` ของ `revenue_org` (§9) · onboarding NOT NULL (8.2) ·
   `RunOnboarding.dry_run = False` · `import_master_data.py` ชี้ business DB · admin ลบจริง 7 ตาราง ·
   **`extract_hierarchy.py` ล้มที่ `revenue_gl`** (`AttributeError: 'int' object has no attribute 'lower'` — `aliases.add(value.lower())` ตั้งแต่ 2026-03-07; รันทุก context แล้วหยุดกลางทาง)
5. หน้า admin ยังไม่มีคิว `knowledge_proposals` ให้รับ / ปฏิเสธ (8.3) — วันนี้ 0 แถว · ข้อเสนอของตัวเรียนรู้จะรอใน DB
6. ข้อค้างของเจ้าของจาก prompt: BG8, ย่อหน้า "ข้อเสนอแนะ…" ท้ายคำตอบ, retention ของคำตอบใน chat, oracle ที่คำนวณเอง, `-ER` ของ EXP4, push
7. **คอลัมน์สะสม (`*_ytd`, `agg: point_in_time`) ถูก SUM ข้ามงวด** (§12.5 #283 — ผู้ใช้เห็นยอด 4.4 เท่า) — metadata บอกแล้วแต่โมเดลไม่ทำตามเมื่อคำถามไม่ระบุเดือน ·
   ข้อเสนอ: กฎทั่วไปใน prompt ที่สร้างจาก metadata — measure ที่ `is_summable = 0` ต้องกรองงวดเดียว (งวดอ้างอิงของ `scope_note`) — ไม่มีชื่อคอลัมน์ตายตัว; แตะ prompt ทุก context → วัดคำถามจริง + legacy ·
   ทางเร็วกว่าแต่ผูกกับ context: golden / กฎของ `feed_revenue`

---

## 14. ตรวจโดย Codex (2026-09-22) — 9 ข้อ แก้ครบ

ผู้ตรวจไล่ 17 commit `0078dcf..0868447` และทำซ้ำทุกข้อบน DB จำลอง · ทุกข้อมี test ที่**ล้มบน code ก่อนแก้** (18 test ล้มบน `8906cd5` —
worktree ที่ใส่ test ใหม่) และผ่านหลังแก้ · pytest **1180 passed, 3 skipped** · lint ของ CI ผ่าน · unused import ไม่เพิ่ม

| # | ที่ผู้ตรวจพบ | แก้ | commit |
|---|---|---|---|
| 1 P1 | `save_examples` เก็บแถวใน dict ตามคำถาม (ตารางไม่มี key) แล้ว UPDATE ทุกแถวที่คำถามตรง — golden ของคนที่คำถามซ้ำกับ contract ถูกเปลี่ยน SQL + ป้ายเป็น `declared` | ทีละ row id + ตรวจ provenance ใน UPDATE เอง | `ddd58bf` |
| 2 P1 | `/chat/train` ของ user แก้ golden ของเครื่องที่ **active** อยู่ได้ตรง ๆ (`may_replace` ให้ `learned` ทับแถวเครื่องทุกสถานะ) | `learned` เปลี่ยนได้เฉพาะข้อเสนอที่ยังรอ — ที่ใช้อยู่ = เข้าคิว (ตัวเรียนรู้ด้วย) | `39c2003`, `ddd58bf` |
| 3 P1 | `_declare` ตรวจ provenance จากแถวที่อ่านไว้ แต่ UPDATE ตรวจแค่ key — คนแก้ระหว่างอ่านกับเขียน contract ทับได้ | UPDATE มีเงื่อนไข `replaceable()` + rowcount 0 = เข้าคิว · INSERT ที่ชนแถวที่เพิ่งเกิด = อ่านใหม่แล้วตัดสินตามกฎ | `39c2003`, `ddd58bf` |
| 4 P2 | backfill ล้มหลัง DROP TRIGGER: ข้อมูล rollback แต่ trigger หาย (pysqlite เริ่ม transaction เฉพาะก่อน DML) | label + trigger + คิว ใน transaction เดียวที่เริ่มเอง (`isolation_level None`, `BEGIN IMMEDIATE`) | `e7a732a` |
| 5 P2 | contract ถอนแถวที่คน **rejected** ได้ แล้วประกาศใหม่ = `declared/active` — การปฏิเสธหาย | ถอนเฉพาะแถวของ contract ที่ไม่ใช่ rejected (metadata, doc, golden) | `ddd58bf` |
| 6 P2 | `_sync_ddl` กรองแค่ `is_active` (context ที่ proposed ถูก train DDL) · `get_known_terms` ไม่ดูระดับแม่ | กรอง `status` ของ context · ค่าเป็นคำในพจนานุกรมเมื่อระดับของมันใช้อยู่ด้วย (+ ชื่อที่ `hierarchy_context` ใช้ตรวจคำระดับ) | `487d21e` |
| 7 P2 | `propose()` ใช้ `json_patch` — JSON null = ลบ key → ข้อเสนอให้ล้างค่าหาย | รวมด้วย `json_set` (เก็บ null) | `39c2003` |
| 8 P2 | onboarding `proposed = excluded.proposed` — ทับข้อเสนอของเครื่องอื่นทั้งก้อน (`dimension_group` หาย) | รวมทีละช่องด้วย `json_set` เหมือนกฎกลาง | `ddd58bf` |
| 9 P2 | ด่านเริ่ม server ตรวจแค่ `status` — ลบ `knowledge_proposals` แล้วยังเริ่มได้ | `missing_provenance()`: ทุกคอลัมน์ source / status / confidence + คิว + index ของคิว | `39c2003` |
| + | ข้อเสนอเรื่อง `is_active=0` | ตัวเรียนรู้เขียนข้อเสนอแบบปิดไว้ · `mark_human_edit` เปิดให้ด้วยเมื่อคนรับ (ยกเว้นคนตั้ง `is_active` เอง) | `39c2003`, `ddd58bf` |

**prompt ไม่เปลี่ยน:** ตัวอ่านที่แก้ (พจนานุกรม, ระดับชั้น + ชื่อ, DDL) บนสำเนาของ config DB จริงให้ผล**เท่ากันทุกไบต์** ระหว่าง code ก่อน/หลังแก้ —
พจนานุกรม 9 context (11,924 คำ), ระดับชั้น 8 context, DDL 8 ตัว · ของจริงไม่มีค่าใต้ระดับที่ไม่ได้ใช้ (0 แถว) และไม่มี context ที่รอ

**ที่ผู้ตรวจยืนยันว่าไม่พบปัญหา:** `_lit()` escape ถูก, `_guarded()` ไม่มีช่อง injection, ตัวอ่านหลักกรอง active แล้ว, ไม่มีการผ่อน scope / allowlist /
`request_pinned` / `llm_data_policy` / `check_select` / audit

### 14.1 ถึงของจริง
- **ตอนตรวจ (2026-09-22 ค่ำ) ไม่มี service ใดรัน** — เครื่อง boot ใหม่ ~4.5 ชม. ก่อนหน้า: AI server (8000), PocketBase ของ portal (8090), frontend (8081) ไม่ได้ start กลับ ·
  คำถามจริงล่าสุด #287 (chat, 15:03)
- start ครั้งถัดไป = ขึ้น `git log 1857dbe..HEAD` (4 commit ของข้อนี้ + `8906cd5` frontend + เอกสาร) — **ไม่ต้อง migrate**: ด่านใหม่ผ่านบนสำเนา schema ของจริง ·
  คำสั่งเดิม `venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`
- ถ้า server เดิมยังรันอยู่ขณะ commit: `context_onboarding` (import ตอนใช้) จะโหลดไฟล์ใหม่ที่ต้องการ `merged_proposal` จาก `provenance` เวอร์ชันใหม่ → onboarding ล้มจนกว่าจะ restart
- **ถอยกลับ:** `git checkout 1857dbe -- app mcp_servers scripts` + restart — DB ไม่ต้องถอย (ไม่มีการเปลี่ยน schema; ข้อเสนอที่ปิดไว้ code เดิมก็ไม่อ่าน)


## 15. ตรวจรอบ 2 โดย Codex (2026-09-23) — 8 ข้อ + manifest

ขอบเขต `0868447..369390c` (8 commit) · รายงานของผู้ตรวจอยู่นอก repo (ไฟล์ชั่วคราว ไม่ได้เก็บ) — สิ่งที่ต้องรู้จากรายงานสรุปไว้ในตารางนี้ · **แยกสองคำรับรอง:** 9 repro ของ §14 ปิดจริง
(regression 60 test ผ่าน) **แต่ไม่เท่ากับ** "ทุกตัวเขียน / ตัวอ่านของระบบครบกติกา" — R2-1..R2-4 คือเส้นทางที่ §14 ไม่ได้ครอบ · test ของ R2-1..R2-4, R2-6 (`'`, `"`, `\`),
R2-7, R2-8 **ล้มบน code ก่อนแก้** (ตรวจแล้ว: stash `app scripts mcp_servers` เก็บ test ไว้ — 12 ล้ม) และผ่านหลังแก้ · ชื่อ field `a.b` / `$money` / ไทย
ผ่านทั้งก่อนและหลัง (เป็นตัวกันถอย ไม่ใช่ repro) · R2-5 ยืนยันด้วยการรันแบบ CI ไม่ใช่ test ที่ล้ม · pytest **1194 passed, 3 skipped** ทั้งบนสำเนา DB และแบบ CI (checkout สะอาด ไม่มี `.env` / DB) · lint ของ CI ผ่าน

| # | ที่ผู้ตรวจพบ | แก้ | test |
|---|---|---|---|
| R2-1 P1 | schema analyzer, dimension detector, view copy, hierarchy bootstrap: ตรวจ `may_replace` ก่อน แล้วเขียนด้วย key อย่างเดียว — คนแก้ระหว่างอ่านกับเขียนถูกทับเนื้อหา | ORM: `query.update` + `replaceable(INFERRED)` ใน WHERE (แบบ `save_training`) · view copy: เงื่อนไขใน UPDATE + rowcount 0 = เข้าคิว · bootstrap: ไม่อ่านก่อนแล้ว — `ON CONFLICT DO UPDATE ... WHERE replaceable` + rowcount 0 = เข้าคิว | `test_provenance_machines`: `test_a_persons_edit_between_the_check_and_the_write_wins` (คนแก้ใน hook ของ `may_replace`), `test_bootstrap_leaves_a_level_a_person_took_just_before_the_write` (คนแก้ก่อน UPSERT — code เดิมได้ `["division"]` ทับ `["human"]` ตามที่ผู้ตรวจพบ) |
| R2-2 P2 | Admin Agent / `nt_admin_mcp`: search examples / mappings / rules และ list contexts คืนแถว proposed / rejected → ส่งให้โมเดลสรุป | 4 tool กรอง `status = 'active'` + `is_active` (search rules เดิมไม่กรอง `is_active` และมี parameter ขอกฎที่ปิด — ตัดทั้งใน tool และ `nt_admin_mcp.search_rules`; search hierarchy กรองอยู่แล้ว) — ข้อเสนอดูที่คิว ไม่ใช่ผ่านเครื่องมือของ agent | `test_provenance_readers`: `test_the_admin_agents_tools_hand_its_model_active_rows_only` (+ กฎ `is_active = 0, status = active`) |
| R2-3 P2 | thumbs-up / review ของ admin: มีตัวอย่างของคำถามนั้นรออยู่ = ไม่แตะ (`if not existing`) แต่ thumbs-up ยัง train Vanna | ทั้งสองทางใช้ `save_training(is_admin=True)` ตัวเดียวกับ `/chat/train` (ย้ายไป `feedback_service`) — ตัวอย่างแรกของคำถาม (ตาม id) เป็นของ admin + active + เปิด **ก่อน** train · category = `chat.context_name` (เดิม review ใส่ feedback category) | `test_provenance_learner`: `test_an_admin_taking_a_waiting_example_puts_it_in_use_before_training` |
| R2-4 P2 | `update_value` ของ hierarchy รับข้อเสนอเป็น `manual/active` แต่ `is_active` ยัง 0 | เปิดเมื่อสถานะเดิมไม่ใช่ `active` (กฎ `mark_human_edit`) · การรับค่าลูกใน `upsert_level` คงเป็นแบบสถานะอย่างเดียว: extract เขียนค่าแบบเปิด ค่าที่ปิด = คนลบ | `test_provenance_people`: `test_a_person_editing_a_proposed_hierarchy_value_switches_it_on` |
| R2-5 P2 | CI หลัง pin ผ่าน collection แต่ล้ม 5 (`--maxfail=5` — รันแบบไม่หยุดได้ 7 เมื่อรวมสอง test ที่ R2-2/R2-3 กระทบ) — test อ่าน `.env` / config DB ของเครื่อง dev | fixture ตั้ง `CONFIG_DB_URL` / config engine ของตัวเอง, mock `_workspaces` ใน test ที่ไม่ได้ทดสอบ registry | รันแบบ CI ในเครื่อง: 1194 passed |
| R2-6 P3 | ชื่อ field ใน JSON path: `'` = SQL syntax error, `"` / `\` = path เสีย | `'` ซ้อน · `"` / `\` = `ValueError` ก่อนเขียนอะไร — SQLite 3.40 (Python 3.10 ของ venv) ไม่อ่าน escape ใน label (3.51 อ่าน) จึงไม่มีรูปที่ใช้ได้ทุกเครื่อง · ชื่อ field ทุกตัวที่ใช้จริงเป็นชื่อคอลัมน์ | `test_a_merged_field_keeps_its_name`, `test_a_field_name_no_path_can_carry_is_refused_before_anything_is_filed` |
| R2-7 P3 | `propose()`: อีก connection เสนอค่าเดียวกันหลัง SELECT → เขียนซ้ำ คืน True ขยับเวลา | `DO UPDATE ... WHERE json(merged) != json(proposed)` + คืน rowcount — ตรวจบน SQLite 3.40 ด้วย · การ reject แทรกกลาง (SELECT แล้ว) ยังไม่ serialize | `test_the_same_proposal_filed_meanwhile_by_another_connection_is_not_written_again` |
| R2-8 P3 | `save_examples`: UPDATE ได้บางแถว (อีกแถวคนเพิ่งเอาไป) → `written = 0` | นับต่อคำถามเมื่อ rowcount > 0; แถวของ contract พูดตามนั้นแล้ว = ไม่มีอะไรรอ (เหมือน `mine and not stale`) | `test_provenance_contract`: `..._counts_a_question_written_even_when_a_person_took_one_of_its_rows_meanwhile` |
| + | `mcp_servers/requirements.txt` ยัง `mcp>=1.0.0` + `fastmcp` (ไม่มีใคร import) | `mcp==1.26.0` ตรงกับ root, ตัด `fastmcp` (+ README) | — |

**ตรวจซ้ำ diff (ผู้ตรวจ, อ่านอย่างเดียว 2026-09-23):** search rules ยังคืนกฎที่ปิด, test bootstrap เดิม (`inferred/rejected`) ผ่านบน code เก่าด้วย
และไม่ตรวจคิว, อ้าง path ชั่วคราว — แก้ทั้งสามข้อในรอบเดียวกันนี้ (ด้านบน)

**test ของผู้ตรวจรันซ้ำบน code ใหม่:** R2-2..R2-4, R2-7, R2-8 ผ่าน · `a"b` / `a\b` ล้มด้วย `ValueError` ตามที่ตัดสิน · race ของ analyzer / dimension / bootstrap
ในชุดของผู้ตรวจ**ไม่ได้ทดสอบอะไรแล้ว** — จุดที่มันเกี่ยว (`before_flush`, `may_replace` ใน bootstrap) ไม่อยู่บนทางเขียนแล้ว คนในจำลองจึงไม่ได้แก้ ·
test ของเราเกี่ยวที่ `may_replace` ก่อนคำสั่งเขียน (ล้มบน code เดิม) · `_declare` แถวหาย / UNIQUE ชุดอื่น = ข้อจำกัดที่ผู้ตรวจแยกไว้ ไม่ได้แก้

**CI (2026-09-23):** commit `3b8f692`, `f3b280b`, `4f7eaf3`, `9e912aa` — run 35814933388 **ผ่าน: lint + 1194 passed, 3 skipped** (Python 3.12) —
เขียวครั้งแรกบน main ตั้งแต่ 2026-07-13

**ยังไม่ได้ทำ / ไม่ได้ตรวจ:** ไม่ได้ restart — **server รันจาก working tree**: start ครั้งถัดไป = ขึ้น `git log 528be11..HEAD`
(ไม่ต้อง migrate) · script เก่าที่เขียนตรง (`populate_schema_metadata.py`, `import_master_data.py`, `add_mapping.py`, `insert_golden_example.py`) ยังไม่ผ่าน helper ·
duplicate check ของ AddMapping / AddRule ยังบอกว่ามีแถว (รวมแถว rejected) ให้โมเดลได้ · pivot / live eval / Telegram / Celery E2E ไม่ได้ตรวจ

---

## commit

| commit | ข้อ |
|---|---|
| `80a0ce5` | 7 — สำรวจ 7 ตาราง |
| `c574cf9` | 8 — คอลัมน์ที่มา / สถานะ / ความมั่นใจ + คิว (migration) |
| `ae1b1ad` | 9 — ตัวเขียนของคน + กฎเดียว |
| `fa37c24` | 9 — contract ทับการประกาศของตัวเอง, ของคนเข้าคิว |
| `c4dcce3` | 9 — เครื่องเปลี่ยนได้เฉพาะของเครื่อง |
| `0a05000` | 9 — ตัวเขียนที่ไม่เคยทำงานเขียน config.db ตามกฎ |
| `c75af27` | 10 — ตัวอ่านใช้เฉพาะ `active` + ด่านเริ่ม server |
| `38b69c8` | 10 — กฎ SQL ไม่ตั้งชื่อคอลัมน์เวลาเอง |
| `df51e8c` | เอกสาร §9–10 |
| `d06d497` | 10 — ถอยตัวอย่างปีใน prompt อธิบายผล (วัดแล้ว) |
| `7e929c0` | 11 — ตัวเติม 3 ตัวรันสองรอบใน test |
| `1857dbe`, `0868447` | เอกสาร §11–13, ขึ้นของจริง §12.5 |
| `39c2003` | 14 — กฎหลังตรวจ: `learned` แก้ได้เฉพาะข้อเสนอ, `replaceable()`, `json_set`, ด่านครบ, รับข้อเสนอ = เปิด |
| `ddd58bf` | 14 — ตัวเขียนตรวจ provenance ในคำสั่งเขียน ทีละแถว และเก็บการปฏิเสธ |
| `e7a732a` | 14 — migration ล้มแล้ว trigger กลับมา |
| `487d21e` | 14 — DDL + พจนานุกรมอ่านเฉพาะ context / ระดับที่ใช้อยู่ |
