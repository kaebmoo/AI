# RESEARCH — สูตร / metric ที่ประกาศเป็นข้อมูล แทนการให้ LLM ตีความกฎที่เป็นข้อความ

**สถานะ:** 🔬 research เสร็จ 2026-10-23 — **ยังไม่ implement, ไม่แก้ code / config / contract, ไม่มี branch** · รอเจ้าของตัดสิน §5
**โจทย์:** `plan/PROMPT_RESEARCH_DECLARED_METRICS.md` · **วิธี:** อ่าน code ทั้งสอง repo (ไม่รัน server), อ่าน `query_audit` / config DB แบบอ่านอย่างเดียว,
คำนวณค่าอ้างอิงซ้ำจากไฟล์ feed ด้วย DuckDB ในหน่วยความจำ (อ่านอย่างเดียว), ค้นเว็บสำหรับ prior art — **ไม่ได้ทดลองบนสำเนา** (ข้อเสนอทุกข้อจึงเป็นสมมติฐานที่ต้องวัดในขั้นแรกของ §4)
บรรทัดอ้างอิง (`ไฟล์:บรรทัด`) อ่านจาก working tree ของ `main` วันที่ 2026-10-23 (AI: `ba0c0d9` + งานที่ยังไม่ commit; NT-Report: contract ebt 1.4.4, dist build `20261022T031559Z` งวด 202609)

---

## 1. สรุปสำหรับเจ้าของ

1. **ปัญหาไม่ใช่ถ้อยคำ แต่คือโครง:** two-pass ไม่มีที่ให้ "สูตร" เลย — pass 1 บอกได้แค่ `metrics: ["ebt"]` + `aggregate_function` ตัวเดียว (`hybrid_flow.py:1363-1403`),
   pass 2 ถูกสั่ง "ยึดตาม Structured Intent" และ "ห้ามเพิ่ม WHERE filter ที่ไม่อยู่ใน Filters" (`:1637-1638`) ขณะที่สูตร EBT ต้องการ SUM 4 ก้อนที่กรองคนละเงื่อนไขแล้วลบกัน
   สูตรทุกตัวจึงเป็นข้อความใน `business_rules` ของ contract → system prompt + RAG ที่ไปถึง pass 1 เท่านั้น (§2.1) — โมเดลจะทำตามหรือไม่ขึ้นกับรอบ
2. **นิยาม "ค่าใช้จ่ายบุคลากร" ไม่มีที่ไหนเลยนอกจาก code ของรายงาน NT-Report** (`EBT/pipeline/group_report/data.py:104-109`, `02_aggregate_hierarchy.py:124-129`) —
   contract ebt 1.4.4 ไม่มีคำว่า "บุคลากร" (grep = 0) → โมเดลเดาว่าแถว `-ER` คือบุคลากร (audit #382, #324) — และเมื่อเติมเป็นกฎข้อความแล้ว (ทดลองบนสำเนา §2 ของโจทย์) ก็ยังถูก ≤ 1/2
3. **ค่าอ้างอิงของเจ้าของยืนยันแล้วจากไฟล์ feed จริง:** น่าน 54,469,208.99 · รายงานรวม 5,799,842,156.45 (ตรงทุกสตางค์, §2.4)
4. **คำถามแบบสูตรมีสัดส่วนจริง 1 ใน 5–3 ใน 10:** audit 384 แถว / 122 คำถามไม่ซ้ำ → ratio / เทียบ / เป้า / ไม่รวม / เฉลี่ย = 26 ข้อ (21%); นับ EBT (ซึ่งเป็นสูตร 4 ก้อน) ด้วย = 39 ข้อ (32%) · ชุดวัด portal 55 ข้อ: 14 ข้อ (25%) · ไม่มีข้อ "ไม่รวม X" ในชุดวัดเลย (§2.3)
5. **ทางที่แนะนำ — (a)+(d): metric ที่ประกาศเป็นข้อมูลใน contract + code ประกอบ SQL + guard ที่ SQL** — pass 1 เลือก `metric_id` จากรายการ (เพิ่ม field เดียว), code ประกอบ SQL จาก
   expression ที่ประกาศ (ไม่มี LLM เขียน SQL ในรูปที่รองรับ), รูปที่ยังไม่รองรับส่ง expression ที่แน่นอนให้ pass 2 + guard ตรวจว่าใช้ครบ — เป็นแบบเดียวกับที่**ได้ผลคงที่**มาตลอด
   (คอลัมน์สะสม/เดือนสุดท้ายจาก code, value lookup → pass 1, scope ที่ชั้น SQL, `multi_context.compute` คิด ratio ใน code) และตรงกับทุก semantic layer ใน prior art (§2.2): LLM เลือก metric + มิติ + ตัวกรอง, compiler สร้าง SQL
6. **ขนาดงาน:** ขั้นแรกพิสูจน์แนวคิด (metric 3 ตัวของ ebt, ชุดวัดมี oracle) ≈ NT-Report 1 วัน (คอลัมน์อ้างอิง + `metrics:` ใน contract, MINOR 1.5.0) + AI 2–3 วัน (ตาราง + sync + `metric_id` + compiler + วัด) ·
   ครบ (ratio, เทียบงวด, admin UI, อนุมาน) ≈ +1–2 สัปดาห์ (§4)
7. **ต้องการข้อตัดสิน 7 ข้อ** (§5) — ที่สำคัญที่สุด: D-1 เจ้าของนิยาม metric = contract, D-4 เมื่อเลือก metric ได้ให้ข้าม pass 2 เลย, D-6 NT-Report ออกค่าอ้างอิงต่อ metric ตอน build

---

## 2. ผลวิจัย

### 2.1 R1 — ของที่มีวันนี้: สูตรอยู่ที่ไหน ถึง LLM ทางไหน อะไรบังคับ อะไรแค่แนะนำ

**ภาพรวม:** ไม่มี field / ตาราง / schema ใดสำหรับ *expression* ของ metric (grep `formula|derived_metric|metric_expr|declared_metric` ใน `app/ scripts/ tests/` = 0) ·
สูตรมีอยู่เฉพาะเป็นข้อความไทยใน `business_rules[].text` ของ contract และใน `description` ของคอลัมน์ · สิ่งเดียวที่ code บังคับเกี่ยวกับ measure คือบิตเดียว `schema_metadata.is_summable`
(contract `agg` ถูกยุบเป็น 0/1 ที่ `datafeed_knowledge.py:159-160`)

| # | ที่เก็บ | ใครเขียน | ถึง LLM ทาง | ขั้นที่ถึง | บังคับโดย code? |
|---|---|---|---|---|---|
| A | contract `business_rules[].{id,text}` (`NT-Report/DataFeed/contracts/ebt.yaml:48-123` — `ebt_definition` :71-78, `ebt_dimension_breakdown` :83-93) | NT-Report `gen_contract.py` (`declared`) | (1) `datafeed_knowledge.register_context` :107-120 → `schema_contexts.instruction_th` → `prompt_builder._build_thai_prompt` :350/:403 = **system prompt** · (2) `sync_documentation` :212-213 → `vanna_documentation` → RAG (`hierarchy_context.get_vanna_context_string` :132-134) | (1) pass 1, pass 2, one-pass, retry · (2) **pass 1 / one-pass / tool loop เท่านั้น — ไม่ถึง pass 2** (`build_pass2_prompt` :1537-1547 ไม่มี rag) · **ไม่ถึงขั้นอธิบาย** (`build_explanation` :603 system prompt คงที่) | ❌ ข้อความล้วน |
| B | contract `columns[].{description,unit,agg}`, `control_totals.measures[].{name,agg,note}` (`ebt.yaml:29-47`) | contract | `sync_schema_metadata` :137-174 — `is_summable = 1 iff dtype=='double' and agg=='sum'` :159-160; `agg` เองไม่ถูกเก็บ; `note` ไม่ sync (อ่านเฉพาะ `gen_golden_from_controls.py:60`) | `is_summable` → ตาราง schema ใน system prompt (`prompt_builder.py:27-34`); `description` **ไม่**อยู่ในตาราง schema (:21-36) — ถึงเฉพาะขั้นอธิบาย (คอลัมน์ point-in-time, `chart_postprocessor.py:309-319`) และ RAG | ✅ **`is_summable` บังคับ:** `_cumulative_columns` :75-91 → `cumulative_sum_error` :118-143, pass-2 `time_text` :1584-1592 |
| C | `schema_metadata` (ไม่มี `agg`, ไม่มี expression; `conversion_sql` = ข้อความ) | contract / admin / onboarding | `build_schema_text` :13-36 | system prompt ทุกขั้น SQL | เฉพาะ `is_summable` |
| D | `schema_business_rules` (`inject_mode` schema_context / instruction) | admin, onboarding, admin agent | `scoped_rules` :52-62 (knowledge_scope) → system prompt; Vanna doc | system prompt + RAG; ไม่ถึงขั้นอธิบาย | ❌ (`ValidationService.check_business_rules` ให้แค่คะแนนความมั่นใจ ไม่บล็อก — `validation_service.py:124-160`, `hybrid_flow.py:667-705`) |
| E | `schema_semantic_mapping.full_condition` | admin, scheduler (learned) | `build_semantic_mapping_text` :124-199 → system prompt → pass 1 คัดลอกเข้า `matched_mappings[].sql_condition` (:1408) → pass 2 :1627-1628, :1641 "ใช้ sql_condition จาก mapping โดยตรง" | **ช่องทางเดียวที่ความรู้ไปถึง pass 2 แบบมีโครง** — แต่เป็น WHERE fragment ไม่ใช่ measure | ❌ โมเดลคัดลอก |
| F | `golden_examples` (36 ข้อของ feed_ebt จาก control totals: revenue/expense/EBT × รวม/สายงาน × เดือน/สะสม — ไม่มี margin, ไม่มี "ไม่รวม", ไม่มีระดับ sub_unit) | `gen_golden_from_controls.py` (declared), admin, feedback (learned) | Vanna → RAG | pass 1 / one-pass เท่านั้น; ปิดทั้งหมดภายใต้ policy ไม่ใช่ `full` (`hierarchy_context.py:120-122`) | ❌ |
| G | `multi_context.SPLIT_SCHEMA.operation` enum `none/ratio/difference` + `compute()` (`multi_context.py:39-48, 229-239`) | — | LLM เลือก operation, **code คิดเลข** | — | ✅ ตัวอย่างที่มีอยู่แล้วของ "LLM เลือก, code คำนวณ" |

**`INTENT_SCHEMA` (pass 1, `hybrid_flow.py:1363-1403`)** — field ทั้งหมด: `intent_type` (enum 6), `metrics: [string]` (= ชื่อคอลัมน์), `aggregate_function` (enum SUM/COUNT/AVG/MIN/MAX **ตัวเดียวสำหรับทุก metric**),
`dimensions`, `filters[{column,operator,value}]` (WHERE ร่วมทั้งก้อน), `time_range{year,month,cumulative}`, `ordering`, `limit`, `matched_mappings[{keyword,sql_condition}]`
→ **ไม่มี** field สำหรับสูตร / expression / metric อนุพันธ์ / id ของกฎ / "ไม่รวม X" / aggregate ที่สอง / filter ต่อก้อน — "SUM(x) where A − SUM(x) where B" เขียนไม่ได้
pass 2 render เป็น `Metrics: SUM(ebt)` (:1622) และ instruction ตัวเต็ม (:1634-1643):

```
- **ยึดตาม Structured Intent เป็นหลัก** — Dimensions คือ GROUP BY, Filters คือ WHERE
- ห้ามเพิ่ม WHERE filter ที่ไม่อยู่ใน Filters ข้างต้น (ยกเว้น time_range)
- ถ้ามี Matched Semantic Mappings ให้ใช้ sql_condition จาก mapping โดยตรง
```

**ที่ code ประกอบส่วนที่ต้องแม่นอยู่แล้ว (แบบอย่างของข้อเสนอ):** `time_text` ของ pass 2 — code เลือกเดือนสุดท้ายและชื่อคอลัมน์สะสม (:1573-1594) · `intent_period_note` เขียน JSON ให้ pass 1 คัดลอก (:390-413) ·
`unfilterable_columns` เลือกตารางที่มีคอลัมน์ให้ (:199-227) · `multi_context.compute` (ratio/difference) · `template_answer` (ไม่มี LLM) · `thai_year` (ปีคำนวณใน code แล้วตรวจซ้ำ)

**guard ที่ตรวจ SQL / ผลลัพธ์แล้ว retry (`run_hybrid_attempt` :930-1140):** `dropped_filter_error` :241-248 · `cumulative_sum_error` :118-143 · `validate_sql` (SELECT-only, pattern อันตราย) ·
`ValueVerifier` · execution error · `null_arithmetic_error` :329-340 · `zeros_after_null_retry` :343-350 — **ไม่มี guard ใดรู้ว่า "measure/สูตรที่ใช้ถูกไหม"** รู้แค่ "คอลัมน์นี้ sum ได้ไหม / มีคอลัมน์นี้ไหม / ผลเป็น NULL ไหม"
**ข้อค้นพบที่อธิบายว่าทำไม guard ใน §2 ของโจทย์ไม่ลู่เข้า:** prompt ตอน retry (`build_retry_user_prompt` :451-475) **ไม่มี intent, ไม่มี RAG, ไม่มี Actual Values** — มีแค่คำถาม + SQL เดิม + ข้อความ error
→ guard ใดก็ตามต้องใส่คำสั่งทั้งหมดลงใน error string เอง (ตัวที่มีอยู่ทำแบบนี้) และ pass 2 ที่ retry ไม่เห็น Structured Intent อีกเลย

**สิ่งที่ pass 1 เห็นแต่ pass 2 ไม่เห็น:** `intent_table_hint` (:158-169), `intent_period_note`, `value_note` (:172-196), RAG (`rag_context`) — pass 2 เห็น `value_matches` เฉพาะคอลัมน์ที่ pass 1 เลือกเป็น filter (:1601-1609)
**ขั้นอธิบาย** ไม่เห็นกฎ / สูตร / mapping / golden ใดเลย (`build_explain_prompt`, `chart_postprocessor.py:275-409`) → ตัวอธิบายไม่มีทางรู้ว่า `SUM(ebt)` ควรเรียกว่า "EBT ไม่รวมบุคลากร"

**ค่า config จริง (อ่านอย่างเดียว 2026-10-23):** `two_pass_enabled = true`, `default_ai_provider = matcha`, `matcha_model = gpt-4.1-mini`, `rag_enabled = false` ใน `admin_config` แต่ `query_engine.py:644` ส่ง `rag_enabled=True` (lite prompt) — RAG จริงขึ้นกับ Chroma ของ 3.10 ตาม memory `eval-python-rag`

**ข้อค้นพบระหว่างทาง (ไม่เกี่ยวกับสูตรโดยตรง แต่กระทบการ sync metric):** `datafeed_knowledge.ensure_current` :297-325 ล้าง query cache + `mark_brain_dirty` แต่**ไม่**เรียก `schema_service.refresh_cache()` → system prompt (ที่มี `instruction_th` = ข้อความกฎ) cache 6 ชม. (`prompt_builder.py:260-266`)
→ กฎที่แก้ใน contract อาจรอได้ถึง 6 ชม. ก่อนถึง system prompt (vanna docs ขึ้นทันที) — metric ที่ประกาศควรอ่านจาก DB ตอน request ไม่ผ่าน prompt cache

### 2.2 R2 — prior art

**ข้อสรุปร่วมของทุกระบบ:** metric เป็น*ข้อมูล*ที่มีโครง (ชื่อ, aggregate/expression, filter, คำพ้อง, คำอธิบาย) — **LLM เลือก metric id + มิติ + ตัวกรอง + ช่วงเวลา เป็น object เล็ก ๆ; compiler ประกอบ SQL** — ไม่มีระบบใดให้ LLM ตีความสูตรจากข้อความ
(ค้น 2026-10-23; แหล่งที่ใช้ตัดสินใจ 3 แห่งผมเปิดตรวจเองซ้ำ: arXiv 2608.16663, arXiv 2604.25149, dbt blog 2026 — ที่เหลือจาก agent ค้น; คำกล่าวอ้างของ vendor ระบุว่า vendor)

| ระบบ | รูปแบบนิยาม metric | derived / ratio | "ไม่รวม X" (filtered measure) | ความหมายเวลา (YTD / สะสม) | มิติที่ใช้ได้ | LLM เลือกอะไร / code ทำอะไร | ตัวอย่างที่รับรอง | หลักฐานความแม่น |
|---|---|---|---|---|---|---|---|---|
| **dbt MetricFlow** ([metrics-overview](https://docs.getdbt.com/docs/build/metrics-overview), [derived](https://docs.getdbt.com/docs/build/derived), [cumulative](https://docs.getdbt.com/docs/build/cumulative)) | YAML `metrics:` ชนิด simple / ratio / derived / cumulative / conversion; `expr` + `filter` ต่อ metric | `derived.expr: revenue - cost` บน `input_metrics` (แต่ละตัวมี `filter` / `offset_window` ของตัวเอง); `ratio` numerator/denominator | `filter` บน metric หรือบน input แต่ละตัว (`{{ Dimension('x') }} = …`) | `cumulative` + `window` หรือ `grain_to_date: month/year` (MTD/YTD), `period_agg: last`; `non_additive_dimension` สำหรับยอดคงเหลือ | ไม่ประกาศต่อ metric — ได้จาก entity join; `dbt sl list dimensions --metrics a,b` = intersection | [dbt-mcp](https://github.com/dbt-labs/dbt-mcp) `query_metrics(metrics, group_by[{name,grain}], where, order_by, limit)`; prompt สั่ง "ไม่มี metric ที่ตรง → ปฏิเสธและเสนอตัวใกล้เคียง"; MetricFlow compile (ratio = subquery สองก้อน join มิติ + `nullif`) | saved queries | **vendor** ([2026](https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026) — ตรวจแล้ว): ACME Insurance 11 ข้อ × 20 รอบ: Sonnet 4.6 text-to-SQL 90.0% → SL 98.2%; GPT-5.3-Codex 84.1% → 100% (text-to-SQL ได้ DDL ทั้งหมด; คำถามนอก model = SL ตอบ 0% คือ*ปฏิเสธ* ไม่ใช่ตอบผิด) |
| **Cube** ([measures](https://docs.cube.dev/reference/data-modeling/measures), [views](https://docs.cube.dev/reference/data-modeling/view), [ai_context](https://docs.cube.dev/docs/data-modeling/ai-context.md)) | YAML measure `sql` + `type` (sum/count/number…), dimensions, segments, views | `type: number`, `sql: "1.0 * {a} / {b}"` อ้าง measure อื่นด้วย `{name}` | `filters: [{sql: "{CUBE}.status = 'x'"}]` บน measure; `segments` = filter ตั้งชื่อ | `rolling_window: {type: to_date, granularity: year}` = YTD; trailing/offset | **view** = ชุด measure+dimension ที่รวมกันได้ + `join_path` เดียว ("AI agents query through views") | REST JSON `{measures, dimensions, timeDimensions{granularity, dateRange}, filters}` หรือ agent เขียน Cube SQL บน view; `meta.ai_context` ≤ 2,000 ตัวอักษร (คำพ้อง, measure ที่ควรใช้) | — | ไม่มีตัวเลขเผยแพร่ |
| **LookML / Looker** ([measure types](https://docs.cloud.google.com/looker/docs/reference/param-measure-types), [filtered measures](https://docs.cloud.google.com/looker/docs/reference/param-field-filters), [Conversational Analytics](https://docs.cloud.google.com/looker/docs/conversational-analytics-overview)) | `measure` block | `type: number` อ้างได้**เฉพาะ measure อื่น** `${a} / NULLIF(${b},0)` | `filters: [field: "expr"]` ใช้ได้กับ sum/count/avg **ไม่ได้กับ `number`** → แบบแผนที่เอกสารสอน: กรองที่ aggregate ข้างล่างแล้วค่อยหารใน `number` — ตรงกับ "EBT ไม่รวมบุคลากร" / "EBT margin" พอดี | `dimension_group` time; `period_over_period`, `running_total` (post-SQL) | Explore joins, `hidden` | **Gemini เลือก field / filter / sort / limit; Looker ประกอบ query จาก model — LLM ไม่เขียน SQL**; agent มี glossary + "verified (golden) queries" | verified queries | **vendor**: "ลด data error ได้ถึงสองในสาม" (ไม่มีวิธีวัด) |
| **Malloy** ([expressions](https://docs.malloydata.dev/documentation/language/expressions), [MCP](https://docs.malloydata.dev/documentation/user_guides/publishing/mcp_agents)) | `measure:` ใน source | expression บน measure; `all()` / `exclude()` | `sum(x) { where: … }` บน aggregate ใด ๆ และ**กรองซ้ำ measure ที่มีอยู่**ได้ (`flight_count { where: … }`) | ไม่มี declarative | aggregate locality กัน fan-out | agent เขียนภาษา Malloy; compiler ตรวจ (`malloy_compile`); แนะนำ `view:` สำเร็จรูป "steer the AI toward valid queries" | pre-built views | ไม่มี |
| **Snowflake Cortex Analyst / semantic views** ([spec](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec), [querying](https://docs.snowflake.com/en/user-guide/views-semantic/querying), [VQR](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/verified-query-repository), [behind the scenes](https://www.snowflake.com/engineering-blog/snowflake-cortex-analyst-behind-the-scenes/)) | YAML / `CREATE SEMANTIC VIEW`: tables, relationships, dimensions, time_dimensions, facts, `metrics{name, synonyms, description, expr}`, `filters`, `verified_queries`, `custom_instructions` แยกขั้น (`sql_generation` / `question_categorization`) | view-level metric อ้าง `table.metric`: `(orders.total_revenue - orders.total_cost) / orders.total_revenue` | `filters` ตั้งชื่อ (มี `synonyms`) หรือ boolean dimension `labels: [filter]` | `non_additive_dimensions` (`NON ADDITIVE BY (dim ASC)`), window `OVER` ใน expr | **มาจาก relationship + granularity**: มิติใช้ได้เมื่อตารางสัมพันธ์กันและ grain เท่าหรือหยาบกว่า; `SHOW SEMANTIC DIMENSIONS FOR METRIC` | pipeline หลาย agent: จัดหมวดคำถาม (ปฏิเสธที่กำกวม) → ดึง verified query ที่คล้าย + literal จาก semantic search ของค่า → หลาย LLM เขียน SQL บน *logical schema* → compiler แก้ error → synthesizer; `SEMANTIC_VIEW(sv METRICS … DIMENSIONS …)` ประกอบ join/agg | `verified_queries` (ดึงตามความคล้าย) | **vendor**: "~90%+", "~2× single-shot SoTA" |
| **Databricks metric views + Genie** ([YAML](https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference), [window measures](https://docs.databricks.com/aws/en/metric-views/window-measures), [knowledge store](https://docs.databricks.com/aws/en/genie/knowledge-store), [benchmarks](https://docs.databricks.com/aws/en/genie/benchmarks)) | YAML `measures[{name, expr (aggregate), window, synonyms ≤10}]`, `dimensions`, `joins`, `filter` ทั้ง view | `MEASURE(a) / MEASURE(b)`; derived บน window measure | Genie "SQL expressions": `filter` / `measure` / `field` ตั้งชื่อ + คำพ้อง — เอกสารระบุว่า "ให้ผลคงที่กว่า text instruction เพราะใช้ตามที่เขียนทุกตัวอักษร" | `window: {order, range: cumulative/trailing/current, semiadditive: last, offset: -12 month}` — `semiadditive: last` = คืนค่า ณ งวดสุดท้ายเมื่อไม่ GROUP BY งวด (= กฎ "คอลัมน์ไม่มี suffix = YTD" ของ feed_ebt) | `joins` ใน YAML; ≤ 50 asset ต่อ agent | Genie เขียน SQL ด้วย `MEASURE()` (ไม่เขียน aggregate เอง); **trusted assets** = parameterized SQL / UC function → คำตอบติดป้าย "verified"; value dictionary ("Florida" → `state='FL'`) = `keyword_value_index` ของเรา | example SQL, parameterized queries; benchmark = คำถาม + SQL เฉลย เทียบ**ผลลัพธ์** 4 นัยสำคัญ | **vendor** ([2026](https://www.databricks.com/blog/introducing-genie-one-genie-ontology-and-genie-agents)): 28 ข้อ Genie 84.5% vs coding agent ทั่วไป 52.4% — ไม่มี ablation |
| **Power BI** ([verified answers](https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-verified-answers), [AI instructions](https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-instructions)) | DAX measure ใน model + linguistic schema (คำพ้องต่อภาษา) | DAX | DAX / instruction | DAX time-intelligence | AI data schema (subset) | Copilot เขียน DAX; verified answer = visual + 5–15 trigger phrase จับคู่เชิงความหมาย (**ไม่จับถ้า measure เปลี่ยน**); Microsoft เขียนเองว่า instruction "LLM only interprets … no guarantee" | verified answers (≤ 250) | ไม่มี |
| **Vanna** ([README v0.7.9](https://raw.githubusercontent.com/vanna-ai/vanna/v0.7.9/README.md), [2023 test](https://ask.vanna.ai/blog/ai-sql-accuracy.html)) | ไม่มี — DDL + documentation ข้อความ + คู่คำถาม-SQL | ข้อความ | ข้อความ | ข้อความ | — | LLM เขียน SQL จาก context ที่ retrieve; repo เดิม archived 2026-03; 2.0 = agent + "tool memory" ไม่มี metric spec | คู่คำถาม-SQL เป็น RAG | 2023, 20 ข้อ: schema อย่างเดียว ~3% → retrieve 10 ชิ้น ~80% — หลักฐานของ*การดึงตัวอย่าง* ไม่ใช่ของ metric ที่ประกาศ |
| **Minerva (Airbnb)** ([DAIS 2022](https://microsites.databricks.com/sites/default/files/2022-07/Democratizing-Metrics-at-Airbnb.pdf)) | config `expression: SUM(bookings)` + `filter: booking_country = 'fr'` ต่อ metric; 30k+ metric | `AGG(a)/AGG(b)` ใน SQL interface → SQLGlot เขียนใหม่เป็น SUMIF subquery join `ds` | `filter:` | — | dimension sources | ก่อนยุค LLM; บทเรียน 1.0: สร้าง metric แยกต่อ filter ล่วงหน้า → "metric swamp" → ให้ filter ที่ query time แทน | — | — |

**งานวิจัยอิสระ (ไม่ใช่ vendor):**
- [arXiv 2608.16663](https://arxiv.org/abs/2608.16663) (Ai, ส.ค. 2026 — ตรวจแล้ว) "Bounded Semantic Planning and Deterministic Compilation": ACME insurance 38 ข้อ × 3 รอบ — LLM แค่จับคำกับ*ตัวเลือกที่กำกับไว้*, code ทำ graph traversal / grain / SQL → ถูก**ทุกรอบ** 37/38 (97.4%) vs DDL-to-SQL 21/38 (55.3%); McNemar p = 3.05×10⁻⁵ (16 ข้อต่างกัน เข้าข้าง SPC ทั้งหมด); 0 รอบ "ผิดแต่รันได้" vs 29; ผู้เขียนเองระบุว่าเป็นผลของระบบรวม (ได้ความรู้เพิ่มด้วย ไม่ใช่แค่ compile)
- [arXiv 2604.25149](https://arxiv.org/abs/2604.25149) (Rumiantsau & Fokeev, เม.ย. 2026 — ตรวจแล้ว): 100 ข้อ Contoso/ClickHouse, Opus 4.7 / Sonnet 4.6 / GPT-5.4 — เอกสาร semantic layer 4 KB (measure + convention) ทำให้ถูก 45.5–50.5% → 67.7–68.7% (+17–23 จุด ทุกโมเดล, p < 0.01); ตัวโมเดลไม่ใช่ตัวแปรสำคัญ ชั้นความหมายต่างหาก
- [arXiv 2606.31041](https://arxiv.org/abs/2606.31041) (Kim et al. 2026): Semantic Model Query IR + deterministic compiler → 94.15% EX บน Spider2-snow (Gemini 3 Pro) · [arXiv 2606.05634](https://arxiv.org/abs/2606.05634) GATE: เติม grounding จาก execution เมื่อ semantic layer ไม่ครบ
- ฐานเปรียบเทียบความยากของ enterprise: [BEAVER](https://arxiv.org/abs/2409.02038) (9,128 คู่จริง: GPT-5.2 agentic 10.8%, มี oracle hint 30.1%), [Spider 2.0](https://arxiv.org/abs/2411.07763) (o1-preview 21.3% vs 91.2% Spider 1) — ไม่มีความรู้ที่ประกาศ = ต่ำทั้งนั้น
- แบบแผนเดียวกันทุกผล: กำไรมาจากการ**ตัดการเดา** (join, grain, filter, สูตร) และความล้มเหลวย้ายจาก "ตัวเลขผิดที่ดูน่าเชื่อ" ไปเป็น "ปฏิเสธนอกขอบเขต" — ตรงกับที่ audit #322/#382 ของเราผิดแบบเงียบ

**บทเรียนที่นำมาใช้กับระบบนี้ (ที่มา → ข้อเสนอ §3):**
1. **หน่วยที่ LLM เลือกคือ metric id ไม่ใช่สูตร** (ทุกระบบ) → pass 1 เพิ่ม `metric_id`; prompt เห็น id + ชื่อ + คำพ้อง ไม่เห็นสูตร
2. **derived = expression บน metric/term อื่น**; **"ไม่รวม X" = filter ที่ input ไม่ใช่สูตรใหม่** (dbt `input_metrics[].filter`, LookML "กรองที่ aggregate แล้วหารใน number", Malloy `{ where: }`) → `terms{where}` + `expr` + `extends` ใน §3.2; ไม่สร้าง metric แยกต่อ filter (Minerva "metric swamp")
3. **เวลาเป็นสอง flag แยกกัน**: คอลัมน์ที่เก็บเป็นสะสมอยู่แล้ว (Databricks `semiadditive: last`, dbt `non_additive_dimension`) กับรูปที่ต้องการนำเสนอ (งวด / YTD / trailing / offset) → `period.value{cumulative, month}` ใน §3.2; `cumulative_sum_error` ของเราคือ guard หลัง SQL — spec ทำให้ปฏิเสธได้**ก่อน**สร้าง SQL
4. **ประกาศมิติที่ metric ใช้ได้** (Snowflake จาก relationship + grain, Cube view, dbt `get_dimensions`) → `dimensions:` ต่อ metric; pass 1 เห็นเฉพาะรายการนี้ — เศษความผิดพลาดที่เหลือใน benchmark ของ dbt คือเลือกมิติผิด
5. **output ของ LLM เป็น object เล็กที่ตรวจ id ได้** (dbt-mcp, Cube REST); id ไม่มี → ปฏิเสธแบบมีโครง + เสนอตัวใกล้เคียง (Cortex Analyst question categorization) — ตรงกับ `multi_context.SPLIT_SCHEMA` ที่มีอยู่
6. **คำพ้องเป็น list ธรรมดา ภาษาไทยใช้ได้เหมือนกัน** (Snowflake/Databricks `synonyms`, Power BI linguistic schema ต่อ culture) — ไม่มี vendor ใดเอกสารรองรับภาษาที่ไม่ใช่อังกฤษชัดเจน → ต้องวัดเองด้วย §2.5; value dictionary ของ Genie = `keyword_value_index` ของเรา
7. **เก็บตัวอย่างที่รับรองเป็น คำถาม → query object (metric id + มิติ) ไม่ใช่ → SQL ดิบ** (Power BI verified answer ไม่จับเมื่อ measure เปลี่ยน; Snowflake VQR ดึงตามความคล้าย) → golden ต่อ metric สร้างจาก compiler (§3.3 แถว RAG)
8. **ข้อความ instruction เก็บไว้สำหรับสิ่งที่พิมพ์เป็นโครงไม่ได้ และคาดว่าจะถูกเมินบ้าง** (Microsoft เขียนเอง; Databricks: expression ชนะ text) → ย้ายสูตร/งวด/ข้อยกเว้นออกจาก `business_rules` ข้อความ เหลือกฎไว้สำหรับการนำเสนอ (หน่วย, ปัดเศษ, งวดเริ่มต้น, ขอบเขต)
9. **governance ต่อ metric**: description, synonyms, owner / verified_by / verified_at (Snowflake), public/private, source/status (Plan 8.1 ของเรา) · **compile ต้องตรวจได้โดยไม่รัน** (dbt `--compile`, `get_metrics_compiled_sql`) → endpoint/CLI แสดง SQL ของ metric ให้ admin ดู
10. **วัดแบบที่ vendor วัดแต่ซื่อสัตย์กว่า**: คำถาม + ผลลัพธ์เฉลย (ไม่ใช่ SQL เฉลย), เทียบตัวเลขมี tolerance, หลายรอบ (dbt 20 รอบ; Ai 3 รอบ + McNemar), แยก in-scope / out-of-scope, และ**แยกคะแนน "เลือก metric ถูก" ออกจาก "compile ถูก"** → §2.5

### 2.3 R1 (ต่อ) — คำถามแบบ "สูตร" มีสัดส่วนเท่าไร

**`query_audit` (อ่านอย่างเดียว):** 384 แถว 2026-09-20 → 2026-10-23, **122 คำถามไม่ซ้ำ** (มี "ทดสอบ re-sync" ×12 และชุด eval ที่รันซ้ำ 4–5 รอบ) · portal 328 / chat 53 / api 2 · feed_revenue 165, feed_ebt 97, feed_expense 64, feed_sales 47

| กลุ่ม (ตัดสินจากคำในคำถาม) | คำถามไม่ซ้ำ | แถว |
|---|---:|---:|
| เทียบ / เติบโต / ปีก่อน / ต่างกัน (YoY, MoM, growth) | 15 | |
| ratio / % / สัดส่วน / margin | 9 | |
| ไม่รวม / ยกเว้น (exclude) | 3 (#322, #323, #382 — ทั้งหมดคือกรณีนี้) | |
| เทียบเป้า | 1 | |
| ค่าเฉลี่ย / S.D. | 1 | |
| **รวมแบบสูตร (ไม่นับ EBT)** | **26 / 122 = 21%** | 65 / 384 = 17% |
| + คำถาม EBT (สูตร 4 ก้อนในตัวเอง — "ebt ของ น่าน", "ข้อมูล EBT เป็นอย่างไร", "กำไรของทั้งบริษัท") | **39 / 122 = 32%** | |
| เฉพาะที่คนพิมพ์เองใน chat (25 ข้อไม่ซ้ำ) | 4 แบบสูตร + 8 EBT = 12 / 25 | |

**ชุดวัดที่มี** (`NT-Report/DataFeed/eval/portal_questions_{ebt,expense,revenue,sales}.json` 40 ข้อ + `scripts/eval/portal_real_questions.json` 15 ข้อ): แบบสูตร 10 ข้อ (ebt P04 margin, P05 สัดส่วนต้นทุน, expense P08 YoY, revenue P05 MoM, P10 เทียบเป้า, sales P07, P08, real P11 เติบโต, P14, P15 YoY %)
+ EBT โดยตรง 4 ข้อ (ebt P01, P06, P09, P10) = **14 / 55 = 25%** · **ไม่มีข้อ "ไม่รวม X" เลย** (ใกล้สุด: revenue P02 ตัวเลือกที่สอง "BG 1–7 ไม่รวมรายได้อื่น") · ไม่มีระดับ sub_unit / cost center ·
`cross_domain_golden.json` 10 ข้อ: 2 ข้อ `computed` (ratio, difference — code คิด) · `ebt_expense_golden.json` 5 ข้อ: ทั้งหมดเป็น *filtered measure* ("ค่าใช้จ่ายตอบแทนแรงงาน**ที่คิดใน EBT**" = ไม่รวม ER)

**สองคำถามของโจทย์ใน audit:** #322/#323/#324 "ถ้าไม่รวมค่าใช้จ่ายบุคลากร จะมี EBT…" (portal, 2026-10-22) และ #382 "ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร" (portal, 2026-10-23) — **ทุกข้อ 1 แถว ไม่มี error** = ระบบตอบผิดอย่างมั่นใจ ไม่มี guard ตัวไหนจับได้
- #324 SQL: `ebt (fact_ebt_total_monthly) + SUM(amount_ytd WHERE group_1 LIKE '%-ER%')` **ทุกสายงาน** → 570.85M + 240.48M (ER ของ 2 สายงานขายจริง = 171.25M) แทนที่จะเป็น 5,799.84M
- #382 SQL: สูตร 4 ก้อนของ `ebt_dimension_breakdown` **ถูกต้อง** (รวม `division IN (2 สายงานขาย)` ที่กฎบอก) แต่ "บวกกลับ" `+ SUM(... '-ER')` → น่านไม่มีแถว -ER → = EBT ปกติ 24,410,200.83
→ ตัวอย่างชัดว่าโมเดล**ทำตามกฎข้อความที่มี**ได้ (สูตร EBT) แต่สิ่งที่**ไม่มีนิยาม** (บุคลากร) ถูกเดาจากคำใกล้เคียง (`ตอบแทนแรงงาน-ER`)

**เวลาต่อคำถาม (audit, ไม่ใช่ cache):** portal เฉลี่ย 8.5 s (295 แถว, 4.3–25.8 s) · chat 15.1 s (40 แถว รวมขั้นอธิบายเต็ม) · api 11.0 s

### 2.4 R4 — ฝั่งเจ้าของข้อมูล (NT-Report)

**ค่าอ้างอิงของโจทย์ยืนยันแล้ว** (DuckDB อ่าน `dist/ebt/latest/fact_ebt.parquet` build `20261022T031559Z`, งวด 202609, อ่านอย่างเดียว):

| | รายได้รวม | − รายได้อื่น | − (ค่าใช้จ่ายรวม − ER) | = EBT | + หมวด 1 | + หมวด 2 | + หมวด 3 | = **EBT ไม่รวมบุคลากร** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| น่าน (`sub_unit = 'ส่วนขายและบริการลูกค้า น่าน'`, ER = 0 แถว) | 95,820,451.26 | 673,332.90 | 70,736,917.53 − 0 | **24,410,200.83** | 27,079,447.18 | 2,937,952.13 | 41,608.85 | **54,469,208.99** ✓ |
| รายงานรวม (2 สายงานขาย; `fact_ebt_total_monthly.ebt`) | | | | **570,852,985.68** | หมวด 1–3 รวม = 5,228,989,170.77 | | | **5,799,842,156.45** ✓ |

**metric ที่ NT-Report นิยามไว้ใน code แล้ว (ไม่มีใน contract):**

| metric | สูตร | code | ใน contract? |
|---|---|---|---|
| `costActual` / expense | subtotal ค่าใช้จ่าย − ER (`01.ค่าใช้จ่ายตอบแทนแรงงาน-ER`) | `EBT/pipeline/02_aggregate_hierarchy.py:120-122, 253`; feed `tools/feed/domains.py:244-258` (เพิ่ม `MEASURE_TYPE`) | ✅ `ebt_definition`, `ebt_dimension_breakdown` |
| `hrActual` (ค่าใช้จ่ายบุคลากร) | SUM หมวด 1/2/3 **ชื่อตรง** + `GROUP_0 = '02.ค่าใช้จ่าย'` — ไม่จับ `-ER` | `02_aggregate_hierarchy.py:124-129, 215-217` | ❌ |
| **EBT ฉบับ nohr** | `costActual − hrActual` ต่อ cost center แล้ว roll-up → EBT nohr = EBT ปกติ + หมวด 1–3 (ไม่บวก ER กลับ) | `group_report/data.py:100-109` (`_nohr_cc`); QA G5 `qa/checks/group_report_qa.py:97-112`; Excel check `excel_check.py:28,137-139` ("รวมค่าใช้จ่ายบุคลากร (ไม่รวม MSP)") | ❌ |
| `ebtMargin` | (rev − cost) / rev × 100 (0.0 เมื่อ rev ≤ 0) | `02_aggregate_hierarchy.py:191`; `05_generate_narrative.py:455-457`; `99_verify.py:179-207` | ❌ (มีแค่คำถาม eval P04) |
| `revPerHead`, `hrCostPerHead`, `revPerHRCost`, `ebtWithScrap`, `performancePerHead`, EBITDA (+หมวด 11/12/18), `ebitdaMargin`, ratio รายได้/ค่าใช้จ่าย, YoY deltas, cost groups | — | `02:192-197, 373-377`; `group_report/data.py:271-334`; `04_build_ebt_data_js.py:580-626` (prior-year / FY benchmark) | ❌ ทั้งหมด |
| revenue vs เป้า (ฐาน BG 1–7), ex-divested YoY, sales actual/target | ตาราง target + กฎข้อความ | `domains.py:121-140, 164-204, 506-513` | 🟡 ตารางมี, **อัตราส่วนเป็นข้อความ** (`revenue_target_basis`, `ex_mobile_divest`) |

**contract pipeline:** `domains.DOMAINS` = single source of truth (`domains.py:4-13`) → `gen_contract.build_contract` (`gen_contract.py:45-88`) เขียน**เฉพาะ** `schema_version, domain, title, owner, description, units, encoding, naming, period_key, primary_dataset, [scope_columns], [control_totals], business_rules, datasets[]` (:74-87)
· `business_rules` = `[{id, text}]` ล้วน ไม่มี `applies_to` · **ไม่มี key `metrics` / `targets` / `reference_values`** · semver: PATCH = แก้กฎ/คำอธิบาย, MINOR = เพิ่มคอลัมน์/ตาราง, MAJOR = เปลี่ยน grain (`DataFeed/CHANGELOG.md:3-5`; ไม่มี code บังคับ bump นอกจาก `validate_contract` ที่จับ breaking `feed.py:737`)
· ลำดับขึ้นของ: "ฝั่ง AI รองรับก่อน แล้วจึงวาง contract" (CHANGELOG 2026-10-22) — ตัวอ่านฝั่ง AI อ่านเฉพาะ key ที่รู้จัก (`datafeed_knowledge.py` ใช้ `contract.get(...)` รายชื่อ) **ยังไม่ได้ทดสอบว่า key แปลกไม่ทำให้ sync ล้ม**

**ค่าอ้างอิงต่อ metric ตอน build — ทำได้ด้วยกลไกที่มี:** `transforms` (`derive_ebt_total_monthly` `domains.py:217-297`) สร้างตารางอนุพันธ์อยู่แล้ว → เพิ่ม `HR_EXPENSE` / `EBT_EX_PERSONNEL` (+ `_MONTH`) ลง `fact_ebt_division_monthly` / `fact_ebt_total_monthly` ≈ 25 บรรทัด + `control_totals.measures` 2 รายการ + `col_meta` + fixture ใน `test_ebt_totals.py` → **MINOR 1.5.0**, `reconcile_gate` ใช้ได้เลย (บวกได้ข้ามสายงาน)
· ระดับหน่วยย่อย (น่าน): ต้องมีตารางใหม่ `fact_ebt_org_monthly` (grain `time_key × cost_center`, ~194 CC × 21 งวด) — transform เดียวกัน groupby ต่างกัน, ต้องผ่อน guard `missing` (`domains.py:259-265`) เพราะหลาย CC ไม่มีฝั่งใดฝั่งหนึ่ง — งานปานกลาง
· **ratio (margin) ใส่ control_totals ตรง ๆ ไม่ได้** — `make_control_totals` `groupby().sum()` จะรวม `__ALL__` ผิด (`feed.py:228-247`) → เป็นคอลัมน์นอก control_totals หรือเพิ่ม `agg: ratio` ที่ข้าม `__ALL__`
· `portal_questions.py` (untracked) สร้างเฉลยจาก control_totals + parquet ด้วยมือต่อโดเมน (:235-271) — มี `values` / `rows` / `percent` + SQL เฉลยต่อข้อ → ขยายได้ทันทีเมื่อมี measure ใหม่
· สองสูตร EBT ใน NT-Report (dashboard กรอง `GROUP_1` อย่างเดียว; feed เพิ่ม `MEASURE_TYPE`) เท่ากันวันนี้ (ต่าง 0.00) — ของ feed เข้มกว่าและเป็นตัวที่ contract เขียน
· `ebt_definition` มีตัวเลขตายตัว "ก.ค. 2569 สะสม: … 366,223,077.31" ที่จะเก่า — ถ้าค่าอ้างอิงเป็นข้อมูลแล้วควรชี้ไป `control_totals` แทน

### 2.5 R5 — การวัดผลที่เชื่อได้ (ออกแบบ)

**ทำไมชุดวัดปัจจุบันตัดสินไม่ได้:** 10 ข้อ × 2 รอบ → ช่วงความเชื่อมั่น 95% ของ 7/10 = [0.42, 0.98] (กว้าง 0.57); ของ 14/20 = [0.50, 0.90] — ผลต่าง ±1–2 ข้อแยกจากความแปรปรวนไม่ได้ (RESULT_P8_KNOWLEDGE_SCOPE §4.2: ebt P03/P04 สลับเองโดยไม่แก้อะไร)
· ตัวอย่างขนาดที่ต้องมี (สองสัดส่วน, power 80%, α 0.05): 0.60→0.80 ต้อง 82 question-runs ต่อฝั่ง, 0.70→0.85 ต้อง 121, 0.60→0.90 ต้อง 32

**ข้อเสนอชุดวัด (ขั้น 1 ของ §4):**
1. **oracle มาจาก NT-Report ไม่ใช่ฝั่ง AI** — ค่าต่อ metric × มิติ × งวดจาก build (`control_totals` + ตารางอนุพันธ์ใหม่ §2.4) ผ่าน `portal_questions.py` → สูตรมีที่เดียว (ไม่ทำสำเนาสูตรใน AI เพื่อ eval)
2. **ชุดคำถาม:** metric {ebt, ebt_excluding_personnel, ebt_margin} × ระดับ {รวม, สายงาน, sub_unit, cost_center} × งวด {เดือน, สะสม} × ถ้อยคำ 2 แบบ (ทางการ / แบบผู้ใช้พิมพ์ เช่น "ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร") = **48 ข้อใหม่** + ชุดเดิม 55 ข้อ (regression) ≈ 100 ข้อ
   · ถ้อยคำแบบผู้ใช้ให้ดึงจาก audit จริง (§2.3) — RESULT_F11 §7 บทเรียน: คำถามที่ทีมเขียนเองให้คะแนนสูงเกินจริง
3. **รอบ:** 3 รอบต่อ variant ต่อข้อ · server ซ้อมบนสำเนา (port 8001+, key ซ้อม) · **query cache 30 นาที** (`query_engine.py:105`, `use_cache = not history` :484) → รอบซ้ำต้อง restart server หรือใช้ instance แยกต่อรอบ (RESULT §4 ใช้ 8001–8004) — ไม่งั้นได้ cache hit (RESULT_F11 §6)
4. **การตัดสิน (ตั้งก่อนวัด):** จับคู่ต่อ question-run (ก่อน/หลัง, prompt เดิมทุกอย่างยกเว้นสิ่งที่แก้) → McNemar exact บนคู่ที่ต่างกัน: ต่างกัน 10 คู่ต้องไปทางเดียวกัน ≥ 9, 12 คู่ ≥ 10, 15 คู่ ≥ 12, 20 คู่ ≥ 15 (p < 0.05) ·
   เกณฑ์ regression: ข้อที่ถูก 3/3 ก่อนแก้ ห้ามตก ≤ 1/3 หลังแก้ (แบบเดียวกับที่ RESULT §8/§9 ใช้ "ไม่มีข้อที่ถูกสองรอบก่อนแล้วผิดสองรอบหลัง") · รายงานสองตัวเลข: ถูกรวม และ **ข้อที่ถูกครบทุกรอบ** (เสถียร)
5. **เวลา/ค่าใช้จ่าย:** 100 ข้อ × 3 รอบ × 8.5 s ≈ **43 นาทีต่อ variant** (serial) → ก่อน+หลัง ≈ 1.5 ชม. ต่อการเปรียบเทียบ; ต่อคำถาม = pass 1 + pass 2 + อธิบาย (3 call ของ `gpt-4.1-mini`, system prompt ebt ≈ 20.6k ตัวอักษร) — ราคาต่อ token ของ gateway Matcha ผมไม่มีข้อมูล จึงประเมินเป็นเวลาเท่านั้น
   · ทางลัดสำหรับ A/B ของ prompt: จับ prompt จริงของ pass 1 แล้ว replay (memory `rag-period-copy`) — ใช้วัด "pass 1 เลือก metric_id ถูกไหม" แยกจาก SQL ได้ในหลักวินาทีต่อ variant
6. **ตัวให้คะแนน:** `run_portal_questions.py` รองรับ `values` / `rows` / `percent` + อ่านข้อความที่ผู้ใช้เห็น (ตัวเลข, ปี พ.ศ., ฐาน) อยู่แล้ว — เพิ่มเฉพาะ `--rounds` หรือรันซ้ำ

---

## 3. ข้อเสนอการออกแบบที่เลือก — (a) metric ประกาศเป็นข้อมูล + (d) guard ที่ SQL

### 3.1 ทางเลือกที่เทียบ

| ทาง | ข้อดี | ข้อเสีย / ความเสี่ยง | ขนาด | ตัดสิน |
|---|---|---|---|---|
| **(a) metric ใน contract + code ประกอบ SQL** | ส่วนที่ต้องแม่นอยู่ใน code (แบบเดียวกับ scope, คอลัมน์สะสม, `multi_context.compute`); ไม่มี LLM เขียน SQL ในรูปที่รองรับ → ผลคงที่ ทดสอบด้วย unit test ได้; metric เป็นข้อมูลที่มี provenance, admin แก้ได้, NT-Report ออกค่าอ้างอิงคู่กันได้; ตรงกับทุก semantic layer ใน prior art | ต้องสร้างตาราง + sync + compiler (ขอบเขตจำกัด); pass 1 ต้องเลือก `metric_id` ถูก (คำพ้องไทย); รูปคำถามที่ compiler ไม่รองรับยังตกไปทางเดิม; metric ของ legacy context ต้องมีคนประกาศ | AI 2–3 วัน PoC, NT-Report 1 วัน | ✅ **หลัก** |
| (b) อ้างกฎด้วย id — pass 1 บอกกฎข้อไหน, pass 2 ได้ข้อความกฎพร้อมคำสั่งให้ใช้ | เล็กมาก (field เดียว + ตัดข้อความ) | pass 2 **เห็นข้อความกฎทั้งหมดอยู่แล้ว** (`instruction_th` ใน system prompt) — ที่ขาดคือการบังคับ ไม่ใช่การมองเห็น; ยังเป็นการตีความข้อความ ขัดกับ "ห้ามเพิ่ม WHERE"; §2 ของโจทย์วัดแล้วว่าเติมข้อความไม่พอ | 0.5 วัน | ❌ ไม่แก้ต้นเหตุ — ใช้ได้เฉพาะกฎที่ไม่ใช่สูตร (ขอบเขต, การปฏิเสธ) |
| (c) golden example ถึง pass 2 / few-shot ต่อ metric | ใช้ของที่มี; ช่วย one-pass และ legacy | RAG ไม่ถึง pass 2 โดยโครง (ต้องเพิ่ม), Chroma ไม่ deterministic, ปิดทั้งหมดภายใต้ policy ที่ไม่ใช่ `full`; golden ต่อ metric × ระดับมิติ × รูปงวด ระเบิดเป็นหลายสิบข้อ; RESULT_F11 §5: โมเดลไม่ทำตามกฎที่มีอยู่ (REV8/REV10) แม้มี golden; ไม่ให้ oracle | 1 วัน | 🟡 **เสริม** สำหรับ one-pass / คำถามที่ compiler ไม่รองรับ — ไม่ใช่ทางหลัก |
| (d) guard ที่ SQL (เจตนาสะสมแต่ใช้ `_month`; metric ที่เลือกแต่ SQL ไม่มีก้อนของสูตร) | guard คือสิ่งที่ได้ผลคงที่ในอดีต (`cumulative_sum_error`, `dropped_filter_error`) | guard ตรวจได้เฉพาะสิ่งที่**รู้ว่าต้องเป็นอย่างไร** → ไม่มี (a) ก็ไม่รู้ว่า "EBT ไม่รวมบุคลากร" หน้าตาอย่างไร; retry prompt ไม่มี intent (§2.1) จึงต้องยัดคำสั่งลง error string; §2 ของโจทย์: guard `_month` ทำงาน 9 ครั้งแต่ pass 2 ไม่ลู่เข้า | 0.5–1 วัน | ✅ **คู่กับ (a)** — ใช้เมื่อ expression ถูกส่งให้ pass 2 (รูปที่ไม่ compile) |
| (e) ผสม = (a) หลัก + (d) ตรวจ + (c) เสริม one-pass + ขั้นอธิบายได้ชื่อ metric | | | | ✅ ที่เสนอ |

### 3.2 รูปแบบ field ใน contract (ตัวอย่าง metric ชุดแรกของ ebt)

```yaml
# DataFeed/contracts/ebt.yaml — key ใหม่ระดับบนสุด (gen_contract.py:82-86 ส่งผ่านเหมือน control_totals)
metrics:
  - id: ebt
    name_th: EBT (กำไรก่อนภาษี ตามรายงาน EBT)
    synonyms: [EBT, กำไร, กำไร (ขาดทุน), ผลประกอบการ, earnings before tax]
    dataset: fact_ebt                      # ตารางที่คำนวณได้ทุกมิติ
    period: {column: time_key, value: {cumulative: amount_ytd, month: amount}}   # ความหมายเวลา: สะสม = แถวงวดเดียว, เดือน = amount
    dimensions: [division, sub_division, unit, sub_unit, sub_unit_fname, unit_fname, unit_short_name, cost_center]
    terms:                                 # แต่ละก้อน = COALESCE(SUM(CASE WHEN <where> THEN <value> END), 0) — code ครอบเอง
      rev:   {where: "measure_type = 'SUBTOTAL' AND group_1 = 'รวมรายได้ทั้งสิ้น'"}
      other: {where: "measure_type = 'ADDITIVE' AND group_1 = '08.รายได้อื่น'"}
      exp:   {where: "measure_type = 'SUBTOTAL' AND group_1 = 'รวมค่าใช้จ่ายทั้งสิ้น'"}
      er:    {where: "measure_type = 'ADDITIVE' AND group_1 = '01.ค่าใช้จ่ายตอบแทนแรงงาน-ER'"}
    expr: "rev - other - (exp - er)"       # ไวยากรณ์เล็ก: ชื่อ term / metric, + - * /, วงเล็บ, ตัวเลข, nullif()
    official_scope: "division IN ('สายงานขายและปฏิบัติการลูกค้า 1', 'สายงานขายและปฏิบัติการลูกค้า 2')"   # ใช้เมื่อไม่มีมิติ/ตัวกรองหน่วยงาน (D-3)
    official_total: {dataset: fact_ebt_total_monthly, column: ebt, month_column: ebt_month}            # ยอดทางการเมื่อไม่มีมิติ
    reference: {control_totals: ebt}       # ชื่อ measure ใน control_totals = oracle ของ eval
    unit: บาท

  - id: ebt_excluding_personnel
    name_th: EBT ไม่รวมค่าใช้จ่ายบุคลากร
    synonyms: [ไม่รวมค่าใช้จ่ายบุคลากร, ไม่รวมบุคลากร, ก่อนหักค่าใช้จ่ายบุคลากร, ไม่รวม HR, nohr]
    extends: ebt                           # รับ dataset / period / dimensions / terms / official_scope มาทั้งหมด
    terms:
      hr: {where: "measure_type = 'ADDITIVE' AND group_0 = '02.ค่าใช้จ่าย' AND group_1 IN ('01.ค่าใช้จ่ายตอบแทนแรงงาน', '02.ค่าสวัสดิการ', '03.ค่าใช้จ่ายพัฒนาและฝึกอบรมบุคลากร')"}
    expr: "ebt + hr"
    note_th: "บวกกลับเฉพาะหมวด 1–3 ชื่อตรง (= hrActual ของรายงาน); ไม่บวก '01.ค่าใช้จ่ายตอบแทนแรงงาน-ER' กลับ เพราะถูกตัดออกจากค่าใช้จ่ายในสูตร EBT อยู่แล้ว (QA G5)"
    official_total: {dataset: fact_ebt_total_monthly, column: ebt_ex_personnel, month_column: ebt_ex_personnel_month}   # คอลัมน์ใหม่ 1.5.0
    reference: {control_totals: ebt_ex_personnel}

  - id: ebt_margin
    name_th: EBT Margin
    synonyms: [EBT margin, อัตรากำไร EBT, margin, กำไรต่อรายได้]
    extends: ebt
    expr: "ebt / nullif(rev - other, 0) * 100"
    unit: percent                          # ไม่เป็น measure ใน control_totals (ratio รวม __ALL__ ไม่ได้ — §2.4)
    note_th: "ฐาน = รายได้ (ฐานยอดขาย) ไม่รวมรายได้อื่น; รายงานใช้ 0.0 เมื่อรายได้ ≤ 0"
```

หลักที่ยึด: **expr ไม่ใช่ SQL เต็ม** — term เป็น WHERE fragment ที่เจ้าของประกาศ (ชนิดเดียวกับ `full_condition` ของ semantic mapping ที่ส่งให้ LLM อยู่แล้ว), สูตรเป็นเลขคณิตบน term/metric เท่านั้น → ตรวจทางไวยากรณ์ได้ก่อนใช้ (ชื่อ term มีจริง, คอลัมน์ใน where มีในตาราง, ไม่มี `;` / subquery) และยังผ่าน `check_select` + scope wrapper ตามเดิม

### 3.3 จุดที่ two-pass / guard / RAG / ขั้นอธิบายต้องเปลี่ยน

| จุด | วันนี้ | เปลี่ยนเป็น |
|---|---|---|
| ตารางความรู้ | ไม่มี | `schema_metrics` (ConfigBase) — `context_name, metric_id, name_th, synonyms (JSON), dataset, period (JSON), dimensions (JSON), terms (JSON), expr, official_scope, official_total (JSON), reference (JSON), unit, note_th` + `source / status / confidence` · เพิ่มใน `provenance.KNOWLEDGE_TABLES` + `DECLARED_FIELDS` · writer ตาม `datafeed_knowledge._declare` (`may_replace` + `replaceable()` ใน WHERE) · reader กรอง `status='active'` + test แบบ `test_provenance_readers.py` · ไม่ผ่าน prompt cache (§2.1 ข้อค้นพบ 6 ชม.) |
| sync | `sync_knowledge` อ่าน rules / columns / control_totals | + `sync_metrics(contract.get("metrics", []))` ใน transaction เดียวกัน; key แปลก = ข้าม ไม่ล้ม |
| pass 1 (`extract_intent`) | ไม่รู้จัก metric | header เพิ่มรายการ metric ของ context (id, name_th, คำพ้อง — ข้อความสั้น) + **code จับคำพ้องก่อน** (longest-match แบบ `known_terms`) → บรรทัด "metric ที่ตรงกับคำในคำถาม: ebt_excluding_personnel" แบบเดียวกับ `value_note` · `INTENT_SCHEMA` + `metric_id: string|null` · code ตรวจว่า id มีจริง ไม่งั้น null |
| หลัง pass 1 (ใหม่) | → pass 2 เสมอ | **ถ้า `metric_id` มี และรูปรองรับ** (`intent_type ∈ {aggregation, ranking}`, งวดเดียวจาก `time_range`/งวดอ้างอิง, `dimensions ⊆ metric.dimensions`, filters บนคอลัมน์ที่ประกาศ) → `metric_compiler.compile()` สร้าง SQL ใน code, **ไม่เรียก pass 2** (D-4): `SELECT <dims>, <expr แทนที่ term ด้วย COALESCE(SUM(CASE WHEN … THEN <value> END),0)> AS "<name_th>" FROM <dataset> WHERE <period> = <p> [AND official_scope] [AND filters] GROUP BY <dims>` · ไม่มีมิติ + ไม่มีตัวกรองหน่วยงาน → `official_total` · เทียบสองงวด (`comparison`) → compile สองครั้งแล้ว code คิดส่วนต่าง/% แบบ `multi_context.compute` (ขั้น 2) |
| pass 2 (`build_pass2_prompt`) | `Metrics: SUM(ebt)` | รูปที่ไม่ compile (trend หลายงวด, detail): บรรทัด `Metric expression (ใช้ตามนี้ทุกตัวอักษร): …` แทน `Metrics:` และยกเว้นก้อนของสูตรจาก "ห้ามเพิ่ม WHERE" |
| guard (d) | — | `metric_expr_error(sql, metric)`: SQL ต้องมี where ของทุก term (normalize ช่องว่าง/quote) และไม่มี `SUM(<คอลัมน์ measure>)` เปล่า → error string ใส่ expression ทั้งก้อน (retry prompt ไม่มี intent) · เสริม: `cumulative` แต่ใช้ `_month` → error ที่บอกคอลัมน์สะสมด้วยชื่อ |
| ขั้นอธิบาย | ไม่เห็นกฎ/สูตร | `build_explain_prompt` ได้ `name_th` + `note_th` + `unit` ของ metric ที่ใช้ → เรียกตัวเลขถูกชื่อ ("EBT ไม่รวมค่าใช้จ่ายบุคลากร 54.47 ล้านบาท (ก.ย. 2569 สะสม, เฉพาะส่วนขายและบริการลูกค้า น่าน)") · policy ไม่ใช่ `full` → template เดิม |
| RAG / golden | 36 golden จาก control_totals (คำถาม → SQL ดิบ) | `gen_golden_from_controls` สร้าง golden ต่อ metric จาก `reference` (ใช้ SQL ที่ compiler สร้าง = เฉลยที่ตรง oracle โดยนิยาม) — เพื่อ one-pass / tool loop เท่านั้น · ระยะต่อไป (R2 ข้อ 7): เก็บเป็น คำถาม → `{metric_id, dimensions, filters, time}` แล้ว compile ตอนใช้ จะไม่เก่าเมื่อสูตร/คอลัมน์เปลี่ยน |
| ช่องทางขาออก (`outbound.py`) | — | ไม่เปลี่ยน: SQL ที่ compile ออกเฉพาะ field `sql` เมื่อขอ; response เพิ่ม `metric: {id, name_th, official: bool}` ใน `render_meta` / `source` (แบบที่ chat บอกแหล่งอยู่แล้ว) |
| `llm_data_policy` | — | compile = ไม่มี provider call → นอก guard · รายชื่อ metric + คำพ้อง + note ที่ส่งให้ pass 1 = "written knowledge" ชั้นเดียวกับ rule text / mapping (`llm_policy.py:4-9`) · literal ใน `where` (ชื่อหมวด) ไม่ถูกส่งให้ LLM เลยในทางหลัก; ถ้าส่งให้ pass 2 (รูปที่ไม่ compile) = ชั้นเดียวกับ `full_condition` ที่ส่งอยู่แล้ว — ขอเจ้าของยืนยัน (D-5) · ระวัง taint (`llm_policy._taint` :91-102): ค่า literal เดียวกันที่เคยออกมาเป็นแถวผลลัพธ์ใน request เดียวกันจะถูกปฏิเสธ — compile ก่อน execute จึงไม่ชน |
| scope | wrapper ที่ชั้น SQL | ไม่เปลี่ยน — SQL ที่ compile ผ่าน `ScopedDuckDB/ScopedSQLite` เหมือน SQL ของ LLM; งวด = `reference_period()`; `official_total` ที่ไม่มีคอลัมน์ scope (เช่น `org_code`) ปิดตามกฎเดิม → compiler เลือก `dataset` แทน (ตรงกับกฎ `ebt_total_uses_total_table`) |
| multi-context | ห้าม JOIN ข้าม source | metric อ้างได้เฉพาะ dataset ของ source เดียว (ตรวจตอน sync) |
| legacy (SQLite view) | ไม่มี contract | metric `manual` จาก admin UI (ขั้น 3) — compiler ใช้ SQL มาตรฐาน (CASE WHEN / COALESCE / NULLIF) ทั้ง DuckDB และ SQLite |

### 3.4 ใครเป็นเจ้าของ metric + provenance

| ที่มา | `source` | ใครตัดสิน | หมายเหตุ |
|---|---|---|---|
| contract ของเจ้าของข้อมูล (`metrics:`) | `declared` | NT-Report (semver) | ทางหลัก; ขัดกับ `manual` = เข้าคิว `knowledge_proposals` (D-C เดิม) |
| admin เพิ่ม/แก้ผ่าน UI (legacy context, metric ที่ contract ยังไม่มี) | `manual` | admin | ต้องมีหน้า CRUD (ขั้น 3) — วันนี้คิว proposal ยังไม่มีทางตัดสิน (Plan 8 §9.2 ข้อ 1) |
| อนุมานจากข้อมูล (Plan 8.2) | `inferred` → `proposed` | คน | ทำได้เฉพาะ metric **อย่างง่าย** = measure ตัวเดียวจาก `control_totals.measures` / `agg` (`contract_draft.detect_agg` :216-264 ทำอยู่แล้ว) — สูตรอนุพันธ์ (ไม่รวม X, margin) **อนุมานไม่ได้** ต้องถามเจ้าของ (Plan 8 §9.1 "ต้องถามเจ้าของเท่านั้น: ความหมายทางธุรกิจ · ข้อยกเว้น") |
| เรียนจากคำถามจริง | `learned` | คน | ผู้ใช้ถามด้วยคำที่ไม่ตรงคำพ้อง → เสนอคำพ้องใหม่เข้าคิว (ไม่แตะสูตร) |

---

## 4. แผนเป็นขั้น

| ขั้น | งาน | เกณฑ์ผ่าน | วิธีวัด | ขนาด |
|---|---|---|---|---|
| **0 — oracle ก่อน** (NT-Report) | `HR_EXPENSE` / `EBT_EX_PERSONNEL` (+`_MONTH`) ใน `fact_ebt_division_monthly` / `fact_ebt_total_monthly` + `control_totals.measures` + กฎข้อความ `ebt_ex_personnel_definition` (ให้ทางเดิมมีนิยามด้วย) + `metrics:` 3 ตัว (§3.2) ใน contract → **1.5.0** · `portal_questions.py` เพิ่มข้อต่อ metric (รวม/สายงาน × เดือน/สะสม) · ถ้าเจ้าของเอา D-6(b): `fact_ebt_org_monthly` สำหรับระดับหน่วยย่อย | build ผ่าน gate; ค่า 202609 = 5,228,989,170.77 / 5,799,842,156.45; AI sync contract 1.5.0 ได้โดย key `metrics` ไม่ทำให้ล้ม (ทดสอบบนสำเนาก่อนวาง — ลำดับ: code AI ที่ทนต่อ key แปลกก่อน contract) | `test_ebt_totals.py` + `test_portal_questions.py` + sync บนสำเนา | NT-Report 1 วัน |
| **1 — PoC** (AI, บนสำเนา) | `schema_metrics` + migration (idempotent) + `sync_metrics` + provenance · pass 1: รายการ metric + code จับคำพ้อง + `metric_id` · compiler รูป aggregation/ranking งวดเดียว + `official_total` / `official_scope` · ขั้นอธิบายได้ชื่อ metric · unit test ของ compiler กับ fixture สังเคราะห์ (เหมือน `test_ebt_totals.py`) | คำถามบุคลากร (รวม + สายงาน + น่าน × เดือน/สะสม × 2 ถ้อยคำ ≈ 12 ข้อ) ถูก **3/3 ทุกข้อ**; ชุด ebt 10 + real 15 + อีก 3 โดเมน ไม่มี regression ตามกฎ §2.5 ข้อ 4; pass 1 เลือก `metric_id` ถูก ≥ 95% (replay prompt) | §2.5 — 3 รอบ × ~100 ข้อ ต่อฝั่ง | 2–3 วัน |
| **2 — ครอบรูปที่เหลือ** | expression → pass 2 + guard `metric_expr_error` สำหรับ trend/detail · `comparison` สองงวด compile ×2 + code คิด (`multi_context.compute` แบบเดียวกัน) · `ebt_margin` / ratio (`nullif`) · golden ต่อ metric จาก compiler | ebt P04/P05 (margin, สัดส่วน) 3/3; YoY/MoM ของชุด portal ไม่ถอย; รวม ≥ เกณฑ์ที่เจ้าของตั้ง (วันนี้ 43/55) | เดิม | 2–3 วัน |
| **3 — self-service** (Plan 8.2/8.3) | admin UI CRUD + คิวตัดสิน · `contract_draft.to_contract` ออก `metrics` อย่างง่ายจาก measures · metric ของ legacy (`revenue_search` ฯลฯ) ประกาศ `manual` · ขั้นอัตโนมัติเมื่อ contract เปลี่ยน (hook `ensure_current` + ล้าง prompt cache) | metric ของ 4 context ใน workspace `default` ถูกประกาศ ≥ 1 ตัวและชุด legacy 37 ข้อไม่ถอย | `run_eval.py --legacy` | 1 สัปดาห์ |
| **ขึ้นของจริง** | ลำดับ: code AI → restart (ไล่ `git log <running>..HEAD` ก่อน — memory `plan8-1-provenance`) → migration → contract 1.5.0 → rebuild/publish → `register_file_source` → rebuild keyword index | คำถาม #322/#382 ซ้ำบนของจริงได้ 5,799.84M / 54.47M | audit | 0.5 วัน |

ขั้นแรกที่เล็กที่สุดที่พิสูจน์แนวคิดได้ = **ขั้น 0 + ขั้น 1 เฉพาะ `ebt` และ `ebt_excluding_personnel` รูป aggregation งวดเดียว** — ถ้าแม้แต่รูปนี้ pass 1 เลือก metric ไม่ถูกหรือ compiler ชน scope ก็รู้ใน 3 วัน

---

## 5. ข้อตัดสินที่ต้องการจากเจ้าของ

| # | คำถาม | ตัวเลือก | ข้อเสนอ |
|---|---|---|---|
| **D-1** | ใครเป็นเจ้าของนิยาม metric | (ก) contract ของเจ้าของข้อมูล = `declared` เป็นหลัก, admin = `manual` เฉพาะที่ contract ไม่มี · (ข) admin เป็นหลัก (DB ก่อน contract) · (ค) ทั้งสองเท่ากัน ขัดกัน = คิว | **(ก)** — สอดคล้อง Plan 8 D-C และ "ส่วนที่ contract ประกาศแก้ได้ที่ contract" |
| **D-2** | รูปแบบ expression | (ก) term (WHERE fragment) + เลขคณิตเล็ก (§3.2) · (ข) SQL expression เต็มต่อ metric (ยืดหยุ่น, ตรวจยาก, อ่านยากสำหรับเจ้าของข้อมูล) · (ค) โครงสร้างล้วนไม่มี SQL เลย (`{column, equals}` ต่อ term — ปลอดภัยสุด แต่เขียน `IN (…)` / `group_0 AND group_1` ยาก) | **(ก)** |
| **D-3** | ขอบเขตทางการ (2 สายงานขาย) เมื่อถามหน่วยที่อยู่นอก scope หรือไม่ระบุสายงาน | (ก) ไม่มีมิติ/ตัวกรองหน่วยงาน → ใช้ `official_scope` เสมอ; มีตัวกรองหน่วยงาน → ไม่ใส่ scope แต่ติดป้าย `official: false` ถ้าหน่วยนั้นอยู่นอก 2 สายงาน · (ข) ปฏิเสธนอก scope · (ค) คำนวณทุกสายงานเมื่อผู้ถามไม่ระบุ | **(ก)** — ต่อเนื่องจากข้อตัดสิน EBT9 "ตอบพร้อมป้ายขอบเขต = ยอมรับได้" |
| **D-4** | เมื่อ pass 1 เลือก `metric_id` และรูปรองรับ | (ก) **ข้าม pass 2** — code ประกอบ SQL ทั้งก้อน · (ข) ส่ง expression ให้ pass 2 เสมอแล้ว guard ตรวจ | **(ก)** — ลด 1 LLM call (≈ −3 s), ผลคงที่, ทดสอบได้; (ข) เก็บไว้สำหรับรูปที่ไม่รองรับ |
| **D-5** | literal ในนิยาม metric (ชื่อหมวด `'08.รายได้อื่น'`) นับเป็น schema (ส่งให้ LLM ได้ภายใต้ `schema_only`) หรือข้อมูล | (ก) schema — เจ้าของประกาศเอง เหมือน rule text / `full_condition` วันนี้ · (ข) ข้อมูล — ไม่ส่งให้ LLM, compile ได้อย่างเดียว | **(ก)** — ทางหลัก (compile) ไม่ส่งอยู่แล้ว ต่างกันเฉพาะรูปที่ตกไป pass 2 |
| **D-6** | NT-Report ออกค่าอ้างอิงต่อ metric ตอน build | (ก) คอลัมน์ใน division/total (MINOR 1.5.0) เท่านั้น · (ข) + `fact_ebt_org_monthly` ระดับ cost center (oracle รายหน่วย + ตอบ "ebt ของน่าน" เป็น lookup ได้) · (ค) ไม่ทำ — AI คำนวณ oracle เองจาก parquet (สูตรซ้ำสองที่) | **(ข)** ถ้ารับงานปานกลางได้, ไม่งั้น (ก) ก่อน |
| **D-7** | ชุดวัด / เกณฑ์ | รับแบบ §2.5 (≈100 ข้อ × 3 รอบ ≈ 45 นาที/ฝั่ง, McNemar + กฎ regression) หรือตั้งเกณฑ์เอง | รับ §2.5; เกณฑ์รวมหลังขั้น 2 ≥ 48/55 (จาก 43) |

### ความเสี่ยง / สิ่งที่ยังไม่แน่ใจ / ยังไม่ได้ตรวจ

- **ยังไม่ได้ทดลองใด ๆ บนสำเนา** — ตัวเลข "ถูก 3/3" ของ compiler เป็นสมมติฐาน (ทาง compile ไม่มี LLM จึงควรนิ่งโดยนิยาม แต่ pass 1 เลือก `metric_id` ยังเป็น LLM); ความแปรปรวนของ pass 1 กับ `gpt-4.1-mini` ในการจับคำพ้องไทยไม่มีตัวเลข — บรรเทาด้วย code จับคำพ้องก่อนและ replay prompt
- **ความซับซ้อนที่ซ่อน:** metric ที่ grain ต่างจากคำถาม (ถามรายเดือนทั้งปี = หลายงวด), มิติที่ต้อง JOIN ตารางอื่น (expense `dim_org_snapshot`) — v1 รองรับเฉพาะ dataset เดียว; คำถามข้าม context ยังเป็นของ multi-context
- **คอลัมน์ `official_total` vs สูตรจาก `dataset`:** ยอดทางการจำกัด 2 สายงาน; ถ้าผู้ใช้กรองหน่วยที่อยู่นอก scope ค่าจะไม่ใช่ "ของรายงาน" (D-3) — ต้องมี lookup ว่าหน่วยนั้นอยู่สายงานไหน (จาก `fact_ebt` เอง)
- **key `metrics` ใน contract กับ code AI ปัจจุบัน:** จากการอ่าน `datafeed_knowledge.py` ตัวอ่านใช้ `contract.get(...)` รายชื่อ จึง*น่าจะ*ข้าม key แปลก — **ยังไม่ได้ทดสอบ**; CHANGELOG กำหนดลำดับ "AI รองรับก่อน contract" อยู่แล้ว ให้ทำตาม
- **prompt cache 6 ชม.ไม่ถูกล้างเมื่อ contract เปลี่ยน** (ตรวจแล้วใน code §2.1) — มีผลกับทางเดิม (กฎข้อความ) วันนี้ด้วย; metric ใหม่ต้องอ่านจาก DB ตอน request
- **ขั้นอธิบาย** ยังเป็น LLM แปลงตัวเลข → ปี พ.ศ. / ชื่อ metric ผิดได้แม้ SQL ถูก (RESULT_F11 §9) — ส่งชื่อ metric ให้ช่วยได้ระดับหนึ่ง; template answer สำหรับ metric ที่ compile ได้เป็นทางเลือกที่นิ่งกว่า (flag `template_answers_enabled` มีอยู่)
- **สองสูตร EBT ใน NT-Report** (dashboard `GROUP_1` อย่างเดียว / feed + `MEASURE_TYPE`) เท่ากันวันนี้ — ถ้า DW มีแถว subtotal ที่ measure_type ไม่ใช่ SUBTOTAL ในอนาคตจะแยกกัน (ข้อเสนอ hygiene ของ NT-Report, ไม่อยู่ในงานนี้)
- **ไม่ได้ตรวจ:** ค่าใช้จ่ายต่อ token ของ gateway Matcha; พฤติกรรมของ Claude/Gemini provider กับ field `metric_id` (ใช้ `generate_structured` เหมือนกัน — `claude_provider.py:175-178` บังคับ tool schema จึงควรเหมือน); legacy view ของ `pl_costtype` ที่มี EBT อยู่แล้ว (audit #344 "EBT เดือนตุลาคม 2569" ตอบจาก pl_costtype) — ความหมาย EBT คนละตัวกับ feed_ebt ต้องประกาศแยก context
- **สิ่งที่เสนอไม่แก้:** คำถามที่ไม่เอ่ย metric ใดเลย ("ข้อมูล EBT เป็นอย่างไรบ้าง" ×17 ใน audit) ยังไปทางเดิม; คำพ้องที่ผู้ใช้ใช้นอกรายการ (เรียน `learned`)

---

## ภาคผนวก — ไฟล์ที่อ้าง

AI: `app/services/ai/hybrid_flow.py` (INTENT_SCHEMA :1363-1403, `extract_intent` :1415-1534, `build_pass2_prompt` :1537-1650, guards :75-413, :930-1140, retry prompt :451-475) · `app/services/schema/prompt_builder.py` (:13-36, :52-62, :124-199, :256-266) · `app/services/datafeed_knowledge.py` (:50-77 `_declare`, :105-120, :137-174, :212-213, :297-325) ·
`app/services/multi_context.py` (:39-48, :229-239) · `app/services/provenance.py` (:22-63, :127-154) · `app/core/llm_policy.py` (:4-9, :91-102, :162-184) · `app/services/query_engine.py` (:105, :484, :636-648) · `app/services/contract_draft.py` (:216-264, :569-616) · `scripts/eval/run_portal_questions.py` · `scripts/datafeed/gen_golden_from_controls.py`
NT-Report: `EBT/pipeline/02_aggregate_hierarchy.py` (:120-129, :190-197, :249-255) · `EBT/pipeline/group_report/data.py` (:100-109, :271-334) · `EBT/pipeline/group_report/excel_check.py` (:28, :137-139) · `EBT/pipeline/qa/checks/group_report_qa.py` (:97-112) · `EBT/docs/QA_Reconciliation_Guide.md:152` ·
`tools/feed/domains.py` (:217-297, :244-258, :259-265) · `tools/feed/gen_contract.py` (:45-88) · `tools/feed/feed.py` (:193-286, :700-838) · `tools/feed/portal_questions.py` (:235-271) · `DataFeed/contracts/ebt.yaml` (:29-47, :48-123) · `DataFeed/CHANGELOG.md:3-25` · `DataFeed/dist/ebt/latest/` (parquet, อ่านอย่างเดียว)
