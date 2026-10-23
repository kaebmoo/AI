# PROMPT — Research: สูตร / metric ที่ประกาศเป็นข้อมูล แทนการให้ LLM ตีความกฎที่เป็นข้อความ

> **งานนี้เป็น research ไม่ใช่ implementation** — ผลลัพธ์คือรายงาน + ข้อเสนอให้เจ้าของตัดสิน
> **ห้าม**แก้ code / config / contract ของจริง, ห้าม commit code — เขียนได้เฉพาะไฟล์รายงานใน `plan/`
> (เขียนเสร็จแล้วหยุด รอเจ้าของอ่าน)

---

## 0. ก่อนเริ่ม — ข้อห้ามที่ต้องรู้

- **server จริงรัน `uvicorn --reload` จาก working tree ของ `main`** — แก้ไฟล์ `.py` ใน repo นี้ = ขึ้นของจริงทันที → ห้ามแก้
- **ฝั่ง AI อ่าน contract ของ NT-Report ตรงที่ `NT-Report/DataFeed/contracts/*.yaml` และ re-sync เองทุก request** →
  แก้ไฟล์ YAML ใน NT-Report = ขึ้นของจริงทันที → ห้ามแก้
- working tree ทั้งสอง repo มีงานที่ยังไม่ commit ของคนอื่น (AI: `app/core/outbound.py` ส่วน `llm_unavailable`,
  `docs/EVAL_HARNESS.md`, `scripts/eval/run_portal_questions.py`; NT-Report: `pocketbase_0/*`, `DataFeed/README.md`,
  `tools/feed/portal_questions.py`) — อย่าแตะ
- ถ้าต้องทดลอง: ทำบนสำเนาเท่านั้น — worktree นอก repo (scratchpad) + สำเนา `config.db` / `app.db` / Chroma +
  server ซ้อม port 8001+ + key ซ้อมที่สร้างบนสำเนา (**ห้าม port 8000, ห้าม API key id 4 = key ของ portal**) —
  วิธีตั้งดู `plan/archive/RESULT_P8_KNOWLEDGE_SCOPE.md` §4 และ §8–9 · pytest ต้องใช้ `venv/bin/python3.14`
  (`venv/bin/python` = 3.10 ไม่มี pytest; แต่ server / eval ใช้ 3.10 เพราะมี RAG)
- อ่าน `CLAUDE.md` ทั้งไฟล์ก่อน (โดยเฉพาะ Plan 8, scope, two-pass, outbound, data protection)

---

## 1. ปัญหา (หลักฐานจริง 2026-10-23)

คำถามจาก dashboard ของ NT-Report: **"ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร จะเป็นเท่าไหร่"** (context `feed_ebt`, portal scope ม.ค. 2568–ก.ย. 2569)

| | บาท |
|---|---:|
| ระบบตอบ (audit `query_audit` #382; ระดับรายงานรวม #324 ผิดแบบเดียวกัน) | 24,410,200.83 = **EBT ปกติ** |
| ค่าที่ถูก — น่าน สะสม ก.ย. 2569 | **54,469,208.99** = 24,410,200.83 + 27,079,447.18 (01.ค่าใช้จ่ายตอบแทนแรงงาน) + 2,937,952.13 (02.ค่าสวัสดิการ) + 41,608.85 (03.ค่าใช้จ่ายพัฒนาและฝึกอบรมบุคลากร) |
| ค่าที่ถูก — รายงานรวม (2 สายงานขาย) สะสม ก.ย. 2569 | **5,799,842,156.45** = 570,852,985.68 (`fact_ebt_total_monthly.ebt`) + 5,228,989,170.77 (หมวด 1–3) |

**นิยาม (เจ้าของยืนยัน 2026-10-23):** "EBT ไม่รวมค่าใช้จ่ายบุคลากร" = EBT ตามสูตร + ค่าใช้จ่ายบุคลากรหมวด 1–3 (ตรงชื่อ) ในมิติเดียวกัน
และ**ไม่รวม MSP** — แถว `01.ค่าใช้จ่ายตอบแทนแรงงาน-ER` ถูกตัดออกจากค่าใช้จ่ายในสูตร EBT อยู่แล้ว ห้ามบวกกลับ.
ที่มา: NT-Report `EBT/pipeline/group_report/data.py` (`_nohr_cc`, ฉบับ `nohr`), `EBT/pipeline/02_aggregate_hierarchy.py`
(`hrActual` = exact match หมวด 1/2/3 ไม่จับ `-ER`), `EBT/docs/QA_Reconciliation_Guide.md` G5 — **นิยามนี้ไม่มีใน DataFeed contract**
ฝั่ง AI จึงเดาว่าแถว `-ER` คือค่าใช้จ่ายบุคลากร และ "บวกกลับ" ด้วยสูตรเดิมทุกตัวอักษร

---

## 2. สิ่งที่ลองแล้ว — วนอยู่กับการแก้ถ้อยคำ (วัดบนสำเนา, ชุดคำถาม ebt 10 ข้อ + คำถามบุคลากร 3 ข้อ, รอบละ 2)

| ลอง | ผล |
|---|---|
| กฎกลาง `SQL_SAFE_SUM_ARITHMETIC` (COALESCE(SUM(...),0)) เป็น business rule | แก้ NULL ของ "ebt ของ น่าน" ได้ แต่ ebt P03 "ค่าใช้จ่ายสะสม…" / P04 "EBT Margin สะสม" ผิด **3/3** (ไม่มีกฎ: ถูก 3/3) — ทั้งข้อความยาวและสั้น |
| เขียน COALESCE ลงในกฎ `ebt_dimension_breakdown` ของ contract | AI ครอบ COALESCE แม้กรองผิดคอลัมน์ → ตอบ **"EBT ของน่าน = 0 บาท"** (แย่กว่าไม่มีข้อมูล) → ถอน |
| กฎใหม่ `ebt_excluding_personnel` ใน contract (ฉบับยาว / ฉบับสั้น) | คำถามบุคลากรถูกได้ ≤ 1/2, ระดับรายงานรวม 0/4; ชุด ebt **7 → 5** ทุกรอบ (P03/P04 ผิด) |
| ตัวตรวจหลัง pass 1: เจตนาสะสม + metric `<col>_month` → เปลี่ยนเป็น `<col>` | ตัวตรวจทำงาน 9 ครั้ง แต่ **pass 2 ยังเขียน `SUM(expense_month)`**; ชุด ebt 6/6 (ไม่ดีขึ้น) → ไม่ได้นำขึ้น |

ข้อสังเกตจาก log (server ซ้อม):
- เมื่อ prompt ของ ebt เพิ่มข้อความใด ๆ, pass 1 ของ P03/P04 เขียน `"time_range": {"cumulative": true}` คู่กับ `"metrics": ["expense_month"]` /
  `["ebt_month", "sales_base_revenue_month"]` — เจตนาขัดกันเอง; diff ของ system prompt สองฝั่งมีแค่เลขเวอร์ชัน + กฎหนึ่งบรรทัด
- สูตรหลายก้อน (EBT = รายได้ฐานยอดขาย − รายได้อื่น − (ค่าใช้จ่าย − ER), EBT ไม่รวมบุคลากร, EBT Margin) อยู่ในรูป**ข้อความ**ใน
  `business_rules` ของ contract → `vanna_documentation` / system prompt — ให้ LLM ตีความเอง
- **two-pass ไม่มีที่ให้สูตร:** `INTENT_SCHEMA` (pass 1) มีแค่ metrics / aggregate / dimensions / filters / time_range / ordering /
  matched_mappings; pass 2 ถูกสั่ง "ยึดตาม Structured Intent เป็นหลัก", "ห้ามเพิ่ม WHERE filter ที่ไม่อยู่ใน Filters" — intent บอก `SUM(ebt)`
  จึงได้ EBT ปกติ; RAG (golden examples / docs) ไปถึง pass 1 แต่**ไม่ถึง pass 2** (`build_pass2_prompt`)
- ชุดวัดเล็ก: P03/P04 สลับถูกผิดเองแม้ไม่แก้อะไร — ผลต่าง ±1–2 ข้อจาก 10 ข้อ × 2 รอบแยกจากความแปรปรวนไม่ได้
- สิ่งที่**ได้ผลแบบคงที่**ในอดีต = ให้ code ประกอบส่วนที่ต้องแม่น: คอลัมน์ยอดสะสม / เดือนสุดท้ายจาก code (`RESULT_F11` §10 —
  "แก้ถ้อยคำอย่างเดียวไม่ได้ผล"), value lookup → pass 1, scope ที่ชั้น SQL, guard ที่ตรวจ SQL แล้ว retry

---

## 3. คำถามวิจัย

### R1 — สำรวจของที่มีวันนี้ (อ่าน code — อ้างไฟล์:บรรทัด)
- สูตร / metric / ความหมายเชิงธุรกิจอยู่ที่ไหนบ้าง และถึง LLM ทางไหน (pass 1, pass 2, one-pass, ขั้นอธิบาย, RAG):
  contract `business_rules` → `datafeed_knowledge.sync_documentation`; `schema_metadata` (`agg`, `is_summable`);
  `schema_business_rules` + `knowledge_scope`; `golden_examples` / Vanna; `semantic_mapping`; `hybrid_flow._cumulative_columns` /
  `intent_period_note` / `cumulative_sum_error` / `dropped_filter_error` / `null_arithmetic_error`; `template_answer`;
  `multi_context` (คำนวณ ratio ใน code — ตัวอย่างที่ code คิดเลขแทน LLM แล้ว)
- `INTENT_SCHEMA`, `extract_intent`, `build_pass2_prompt`, `unfilterable_rule`, one-pass fallback — อะไรบังคับ / อะไรแค่แนะนำ
- metric ที่ผู้ใช้ถามจริง: นับจาก `query_audit` (อ่านอย่างเดียว) + ชุดคำถามใน `NT-Report/DataFeed/eval/portal_questions_*.json`
  และ `scripts/eval/portal_real_questions.json` — คำถามที่เป็น "สูตร" (ratio, ไม่รวม X, เทียบเป้า, YoY, margin) มีสัดส่วนเท่าไร

### R2 — prior art (ค้นเว็บ + อ้างแหล่ง)
semantic layer / metric layer กับ text-to-SQL: dbt Semantic Layer / MetricFlow, Cube, LookML, Malloy, Snowflake Cortex Analyst
(semantic model YAML / semantic views), Databricks metric views / AI/BI Genie, Power BI measures + Copilot, Vanna และงานวิจัย
text-to-SQL ที่วัดผลของ semantic layer — สรุป: รูปแบบนิยาม metric (expression, grain, dimensions ที่ใช้ได้, filter, time semantics
YTD vs period, derived/ratio metrics), LLM เลือกอะไร / code ประกอบอะไร, วิธีรองรับ dimension หลายระดับและหลายตาราง

### R3 — ทางเลือกการออกแบบสำหรับระบบนี้ (เทียบข้อดี/ข้อเสีย/ความเสี่ยง/ขนาดงาน)
อย่างน้อย:
- **(a) metric ที่ประกาศใน contract** (id, ชื่อไทย + คำพ้อง, ตาราง, expression SQL ที่มีที่ว่างให้ใส่มิติ/งวด, grain, ความหมายเวลา) —
  pass 1 เลือก metric id; code ประกอบ SQL หรือส่ง expression ที่แน่นอนให้ pass 2
- **(b) อ้างกฎด้วย id** — pass 1 บอกว่ากฎข้อไหนใช้, pass 2 ได้ข้อความกฎนั้นพร้อมคำสั่งให้ใช้
- **(c) golden example ถึง pass 2** / few-shot ต่อ metric
- **(d) guard ที่ SQL** (เช่น เจตนาสะสม แต่ SQL ใช้ `<col>_month`) — เป็นตัวเสริมหรือแทน
- **(e) ผสม**
พิจารณากับข้อจำกัดของระบบ: file source (DuckDB) + legacy (SQLite), คำถามภาษาไทย, ต่อ workspace, scope ที่ชั้น SQL (`scope_column_names`),
`llm_data_policy` (`aggregated_only` / `schema_only` — อะไรส่งให้ LLM ได้), provenance (Plan 8.1: `declared` / `manual` / `inferred`,
`knowledge_proposals`), ช่องทางขาออก (`app/core/outbound.py`), Plan 8 (self-service, pipeline เดียวสองโหมด อนุมาน + contract —
metric ที่ไม่มี contract จะมาจากไหน: อนุมาน / admin / คิวให้คนตัดสิน)

### R4 — ฝั่งเจ้าของข้อมูล (NT-Report)
- metric อะไรที่ NT-Report นิยามไว้แล้วใน code ของรายงาน (EBT step 02/07, `ebt_definition`, `ebt_dimension_breakdown`,
  `expense_in_ebt_report`, sales/revenue targets, …) และย้ายมาเป็นข้อมูลใน contract ได้อย่างไร (`tools/feed/domains.py` →
  `gen_contract.py` → `contracts/*.yaml`; semver PATCH/MINOR ตาม `DataFeed/CHANGELOG.md`)
- NT-Report คำนวณ**ค่าอ้างอิงของแต่ละ metric** ตอน build ได้ไหม (แบบ `control_totals` / bridges) → ใช้เป็น oracle ของ eval
  และ golden อัตโนมัติ

### R5 — การวัดผลที่เชื่อได้
ออกแบบชุดวัดที่แยกผลจริงจากความแปรปรวนได้: จำนวนคำถามต่อ metric × ระดับมิติ × งวด, จำนวนรอบซ้ำ, เกณฑ์ตัดสิน (เช่น ช่วงความเชื่อมั่น /
paired comparison), ค่าอ้างอิงจาก NT-Report; ใช้ของที่มี (`scripts/eval/run_portal_questions.py`, NT-Report `tools/feed/portal_questions.py`)
และประมาณเวลา/ค่าใช้จ่ายต่อรอบ (ตอนนี้ ~9 วินาที/คำถาม, matcha `gpt-4.1-mini`)

---

## 4. สิ่งที่ต้องส่ง

ไฟล์เดียว: `plan/RESEARCH_DECLARED_METRICS.md` (ภาษาไทย, ศัพท์เทคนิคเป็นอังกฤษได้) ประกอบด้วย
1. สรุปสั้นสำหรับเจ้าของ (≤ 15 บรรทัด): ปัญหา, ทางที่แนะนำ, ทำไม, ขนาดงาน
2. ผล R1–R5 พร้อมหลักฐาน (ไฟล์:บรรทัด, ลิงก์แหล่ง, ตัวเลข)
3. ข้อเสนอการออกแบบที่เลือก: รูปแบบ field ใน contract (ตัวอย่าง YAML ของ metric ชุดแรก: `ebt`, `ebt_excluding_personnel`,
   `ebt_margin`), จุดที่ two-pass / guard / RAG ต้องเปลี่ยน, ใครเป็นเจ้าของ metric (contract / admin / อนุมาน) และ provenance
4. แผนเป็นขั้น (ขั้นแรกเล็กที่สุดที่พิสูจน์แนวคิดได้) + เกณฑ์ผ่านของแต่ละขั้น + วิธีวัด
5. **ข้อตัดสินที่ต้องการจากเจ้าของ** (เป็นข้อ ๆ พร้อมตัวเลือก) และความเสี่ยง / สิ่งที่ยังไม่แน่ใจ — บอกตรง ๆ ว่าอะไรยังไม่ได้ตรวจ

ไม่ต้อง implement, ไม่ต้องสร้าง branch — ถ้าทดลองบนสำเนา ให้บันทึกวิธีและผลไว้ในรายงาน แล้วลบสำเนา / `.env` ที่คัดลอก / key ซ้อมทิ้ง

---

## 5. อ่านประกอบ

- `CLAUDE.md` · `plan/PLAN_8_SELF_SERVICE_ONBOARDING.md` (§2.1, §9 เครื่องมือร่าง contract) · `plan/archive/RESULT_P8_KNOWLEDGE_SCOPE.md` (§8–9)
  · `plan/archive/RESULT_F11.md` (§4.1, §7, §10) · `docs/DATAFEED_INTEGRATION.md` · `docs/PORTAL_INTEGRATION.md`
- code: `app/services/ai/hybrid_flow.py`, `app/services/ai/hierarchy_context.py`, `app/services/datafeed_knowledge.py`,
  `app/services/schema/prompt_builder.py`, `app/services/schema/knowledge_scope.py`, `app/services/multi_context.py`,
  `app/services/ai/template_answer.py`, `app/services/contract_draft.py`, `app/services/provenance.py`
- NT-Report: `tools/feed/domains.py`, `tools/feed/gen_contract.py`, `tools/feed/feed.py`, `DataFeed/contracts/ebt.yaml`, `DataFeed/SPEC.md` §5,
  `DataFeed/CHANGELOG.md`, `EBT/pipeline/02_aggregate_hierarchy.py`, `EBT/pipeline/group_report/data.py`, `EBT/docs/QA_Reconciliation_Guide.md`
- memory ของโปรเจกต์ (โหลดอัตโนมัติ): บทเรียน "อย่าแก้แบบ whack-a-mole", "Portal default period = YTD (wording alone failed)", "Two-pass drops rule-only scope"
