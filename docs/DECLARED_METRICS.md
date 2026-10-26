# Declared metrics — metric ที่ประกาศเป็นข้อมูล แล้วให้ code ประกอบ SQL (2026-10-24)

> ที่มา: `plan/RESEARCH_DECLARED_METRICS.md` (วิจัย) · `plan/RESULT_P8_DECLARED_METRICS.md` (ผลวัด) · `plan/GOLIVE_DECLARED_METRICS.md` (ขึ้นของจริง)
> ฝั่ง NT-Report: `DataFeed/SPEC.md` §5.5, `DataFeed/contracts/ebt.yaml` (`metrics:`), `DataFeed/CHANGELOG.md` 2026-10-24

## 1. ปัญหาที่แก้

สูตรทางธุรกิจ (เช่น "EBT ไม่รวมค่าใช้จ่ายบุคลากร" = EBT + หมวด 1–3 ชื่อตรง, ไม่บวก `-ER` กลับ) เคยอยู่ได้ที่เดียวคือ**ข้อความ**ใน `business_rules` ของ contract →
system prompt / RAG → ให้โมเดลตีความเอง. two-pass ไม่มีที่ให้สูตร: pass 1 บอกได้แค่ `metrics: ["ebt"]` + `aggregate_function` ตัวเดียว และ pass 2 ถูกสั่ง
"ยึดตาม Structured Intent / ห้ามเพิ่ม WHERE" → คำตอบคือ `SUM(ebt)` = EBT ปกติ; เติมกฎข้อความอีก 4 รอบก็ไม่หาย (และทำข้ออื่นพัง). รายละเอียด: RESEARCH §2.1

## 2. หลักการและเทคนิคที่ใช้ (เรียกชื่อให้ตรงกับที่วงการใช้)

| หลักการ | ชื่อที่ใช้กันทั่วไป | ในระบบนี้ |
|---|---|---|
| metric เป็น**ข้อมูลมีโครง** ไม่ใช่ร้อยแก้ว: ชื่อ, คำพ้อง, ตาราง, ความหมายเวลา, มิติที่ใช้ได้, ก้อนที่กรองแล้ว (filtered measure), สูตรเลขคณิต | **Semantic layer / metric layer** (dbt MetricFlow, Cube, LookML, Snowflake semantic views, Databricks metric views — RESEARCH §2.2) | key `metrics:` ใน contract → ตาราง `schema_metrics` |
| **LLM เลือก, code ประกอบ**: โมเดลเลือก metric id + มิติ + ตัวกรอง + ช่วงเวลาเป็น object เล็ก ๆ; compiler ที่ตรวจสอบได้สร้าง SQL | **Bounded semantic planning + deterministic compilation** (Ai 2026, arXiv 2608.16663); "metric query IR + compiler" (Kim et al. 2026); dbt-mcp `query_metrics` | `INTENT_SCHEMA.metric_id` (pass 1) → `metric_compiler.plan()` → `compile()` แทน pass 2 |
| ส่งให้โมเดลเฉพาะ**ชื่อ/คำพ้อง** ไม่ส่งสูตร | **Structured output with a closed option set** (เลือกจากรายการ ไม่แต่งเอง) | `metric_catalog` / `metric_note` ใน header ของ pass 1 (D-5) |
| "ไม่รวม X" = **filtered measure** บน term ไม่ใช่สูตรใหม่; derived = expression บน metric/term อื่น; `extends` สืบทอด**เฉพาะโครง** | filtered measures (LookML `filters:`), derived/ratio metrics (MetricFlow), input metric filters | `terms{where}` + `expr` + `extends` (dataset/period/dimensions/official_scope + merge terms เท่านั้น) |
| ความหมายเวลาแยกเป็นสองแกน: คอลัมน์ที่เก็บเป็นสะสม vs รูปที่ถาม (เดือน/YTD) | semi-additive measure (`semiadditive: last`), `grain_to_date` | `period.value{cumulative: amount_ytd, month: amount}` + กฎ "ไม่เอ่ยเวลา = YTD" ของเจ้าของ |
| **ความแม่นต้องอยู่ใน code ไม่ใช่ใน prompt**: สิ่งที่ต้องถูกทุกครั้ง (งวด, คอลัมน์สะสม, scope, สูตร) ให้ code ตัดสิน แล้วให้โมเดลทำส่วนที่คลุมเครือ (เข้าใจคำถาม) | "เลิกแก้ถ้อยคำ" — บทเรียนซ้ำของโปรเจกต์ตั้งแต่ RESULT_F11 §10, RESULT_P8_KNOWLEDGE_SCOPE §8 | compile path, guards (`cumulative_sum_error`, `dropped_filter_error`), scope wrapper |
| ความรู้มี**เจ้าของและที่มา**: เจ้าของข้อมูลประกาศใน contract (`declared`), admin แก้ (`manual`), เครื่องเสนอ (`inferred/learned`) เข้าคิว | contract-first / data owner declares (governance ของ semantic layer: owner, verified) | Plan 8.1 provenance: `_declare`, `may_replace`, `knowledge_proposals`; reader กรอง `status='active'` |
| ค่าอ้างอิงมาจาก**ผู้ผลิตข้อมูล** ตอน build ไม่ใช่จากฝั่ง AI | control totals / reconciliation gate เป็น oracle ของ eval | NT-Report `control_totals.measures` + `portal_questions.py`; `reference.control_totals` ใน metric |
| วัดแบบ**จับคู่ก่อน/หลังบนสำเนา** หลายรอบ แยกผลจริงจากความแปรปรวนของโมเดล; อ่าน intent จริงของโมเดลก่อนโทษ code | paired evaluation, exact McNemar; "observe the real pass 1" | server ซ้อม 2 ตัว × 5 รอบ, `aggregate.py`; slice 04–06 เกิดจาก intent จริง (RESULT §2) |
| **planner–reviewer + coder**: Claude วางแผนเป็น slice ที่ตรวจรับได้ มี acceptance command; Codex เขียน; ตรวจ diff + รัน acceptance เองก่อน PASS; ของจริงไม่ถูกแตะจน merge | /delegate workflow (`~/.claude/skills/delegate`), worktree นอก repo, ff-merge | Run A (NT-Report 3 slice) + Run B (AI 6 slice), 13 รอบ Codex |

## 3. โครงของ metric (contract `metrics:` → `schema_metrics`)

```yaml
metrics:
  - id: ebt                                   # snake_case; ชื่อที่ pass 1 เลือก
    name_th: EBT (กำไรก่อนภาษี ตามรายงาน EBT)
    synonyms: [EBT, ebt, กำไร, กำไร (ขาดทุน), ผลประกอบการ]
    dataset: fact_ebt                         # ตารางที่คำนวณได้ทุกมิติ (ฝั่ง AI เก็บชื่อเต็ม feed_<domain>_<dataset>)
    period: {column: time_key, value: {cumulative: amount_ytd, month: amount}}
    dimensions: [division, sub_division, unit, sub_unit, sub_unit_fname, unit_fname, unit_short_name, cost_center]
    terms:                                    # แต่ละก้อน = COALESCE(SUM(CASE WHEN <where> THEN <value> END), 0)
      rev:   {where: "measure_type = 'SUBTOTAL' AND group_1 = 'รวมรายได้ทั้งสิ้น'"}
      other: {where: "measure_type = 'ADDITIVE' AND group_1 = '08.รายได้อื่น'"}
      exp:   {where: "measure_type = 'SUBTOTAL' AND group_1 = 'รวมค่าใช้จ่ายทั้งสิ้น'"}
      er:    {where: "measure_type = 'ADDITIVE' AND group_1 = '01.ค่าใช้จ่ายตอบแทนแรงงาน-ER'"}
    expr: "rev - other - (exp - er)"          # เลขคณิตบน term/metric เท่านั้น: + - * / ( ) ตัวเลข nullif(a, b)
    official_scope: "division IN ('สายงานขายและปฏิบัติการลูกค้า 1', 'สายงานขายและปฏิบัติการลูกค้า 2')"
    official_total: {dataset: fact_ebt_total_monthly, column: ebt, month_column: ebt_month}
    reference: {control_totals: ebt}          # measure ใน control_totals = เฉลยของ eval
    unit: บาท (THB)
  - id: ebt_excluding_personnel
    extends: ebt                              # สืบทอดเฉพาะ dataset / period / dimensions / official_scope + รวม terms
    terms: {hr: {where: "measure_type = 'ADDITIVE' AND group_0 = '02.ค่าใช้จ่าย' AND group_1 IN ('01.ค่าใช้จ่ายตอบแทนแรงงาน', '02.ค่าสวัสดิการ', '03.ค่าใช้จ่ายพัฒนาและฝึกอบรมบุคลากร')"}}
    expr: "ebt + hr"                          # ไม่บวก -ER กลับ (ถูกตัดจากค่าใช้จ่ายในสูตร EBT อยู่แล้ว)
  - id: ebt_margin
    extends: ebt
    expr: "ebt / nullif(rev - other, 0) * 100"
    unit: percent                             # ไม่มี official_total / reference (ratio รวม __ALL__ ไม่ได้)
    ranking:                                  # (ebt 1.6.0) ใช้เฉพาะเมื่อแยกมิติ/จัดอันดับ — ไม่แตะยอดรวมและการค้นหน่วยที่ระบุชื่อ
      scope: "is_hq = 0"                      #   WHERE เพิ่ม: เปรียบเฉพาะหน่วยปฏิบัติการ (margin ของหน่วยสนับสนุนรายได้ 442 บาท = −47 ล้าน%)
      base: "rev - other"                     #   expression ตาม grammar เดียวกับ expr → คอลัมน์ตัวหารคู่ไปก่อนค่า metric
      base_name_th: "รายได้ (ฐานยอดขาย)"       #   ชื่อคอลัมน์นั้น
```

ยอดขายเทียบเป้า (sales 1.4.0, 2026-10-25) ใช้ key เพิ่ม 4 อย่าง:

```yaml
  - id: sales_vs_target
    period: {column: year_month, value: {month: amount}}   # ไม่มี cumulative = ยอดสะสม SUM เดือน 01..งวด (BETWEEN y01 AND yMM)
    terms:
      actual: {where: "metric = 'actual' AND substr(business_group, 1, 2) IN ('1.', '2.', '3.', '4.', '5.', '6.', '7.')"}
      target: {where: "metric = 'target' AND substr(business_group, 1, 2) IN ('1.', '2.', '3.', '4.', '5.', '6.', '7.')"}
    expr: "actual / nullif(target, 0) * 100"
    unit: percent
    extra_columns:                                         # แสดงก่อนค่า metric ทั้งยอดรวมและรายหน่วย (ไม่ใช้กับ official_total / การเทียบสองงวด)
      - {expr: actual, name_th: "ยอดขายบริการ (บาท)"}
      - {expr: target, name_th: "เป้ายอดขาย (บาท)"}
    ranking:                                               # ใช้เมื่อแยกมิติเท่านั้น
      positive: target                                     #   HAVING (target) > 0 — ยกเว้นเมื่อตัวกรองระบุชื่อหน่วยของมิติที่จัดกลุ่ม
      threshold: {value: 100, above: [มากกว่าเป้า, เกินเป้า, ถึงเป้า, …], below: [ไม่ถึงเป้า, ต่ำกว่าเป้า, …]}
                                                           #   คำในคำถาม → HAVING ค่า >= 100 / < 100 และเรียงค่า มาก→น้อย / น้อย→มาก
```

กติกา: `expr` ไม่ใช่ SQL เต็ม (ตรวจไวยากรณ์ได้; ชื่อนอก term/metric = ปฏิเสธ) · `where` อ้างได้เฉพาะคอลัมน์ของ dataset (ตรวจตอน sync ฝั่ง AI และ test ฝั่ง NT-Report) ·
`name_th` / `synonyms` / `unit` / `note_th` / `official_total` / `reference` / `expr` **ไม่สืบทอด** · ตัวอย่างและ test: `tests/fixtures/ebt_metrics_1_5_0.yaml`, `tests/unit/test_metric_compiler.py`

รายได้ที่แยกตารางตามมิติ (revenue, 2026-10-26):

```yaml
  - id: revenue
    name_th: รายได้
    synonyms: [รายได้, รายได้รวม, revenue]
    datasets:
      - {name: fact_total_monthly, dimensions: []}
      - {name: fact_bu_monthly, dimensions: [bu_seq, bu]}
      - {name: fact_org_monthly, dimensions: [division_name, unit_name, cost_center]}
    period: {column: year_month, parts: {year: year, month: month}, value: {cumulative: revenue_ytd, month: revenue}}
    terms: {rev: {}}
    expr: rev
    official_total: {dataset: fact_total_monthly, column: revenue_ytd, month_column: revenue}
    unit: บาท (THB)
```

- ประกาศ `dataset` XOR `datasets` (เลือกอย่างใดอย่างหนึ่งเท่านั้น); `dataset` เดี่ยวทำงานเหมือนเดิม
- เมื่อใช้ `datasets` ไม่ประกาศ `dimensions` ระดับ metric — code รวมมิติของทุก dataset ตามลำดับที่พบครั้งแรก
- คอลัมน์ของ period / term / scope ต้องมีในทุกตารางที่ระบุใน `datasets` (ตรวจตอน sync)
- `period.parts` (optional) เป็น mapping ไม่ว่าง เฉพาะ `year` / `month` → ชื่อคอลัมน์ไม่ว่างที่มีในทุกตาราง; แต่ละคอลัมน์ต้องไม่ซ้ำกันและไม่ใช่ `period.column` (ตรวจตอน sync)
- เลือกตารางเล็กที่สุดที่มีครบทุกมิติและคอลัมน์ตัวกรองที่ถาม: นับจำนวนมิติที่ประกาศ; เท่ากันเลือกตามลำดับประกาศ
- ไม่มีตารางที่มีครบ → `plan()` ไม่รับด้วยเหตุผล `shape:dimension_set` และส่งคำถามไป free SQL
- term ที่ไม่มี `where` หรือเป็น null / ว่าง / ช่องว่างล้วน = ทุกแถวของตาราง
- period ที่ไม่มี `cumulative` ใช้ SUM คอลัมน์ month แบบ `BETWEEN y01 AND yMM`; sync ปฏิเสธเมื่อคอลัมน์นั้นเป็น `agg: point_in_time` (M-5)
- `excluded_words: [เป้า, target]` (ไม่สืบทอด) = คำของคำถามที่ metric นี้ตอบไม่ได้ → `plan()` ไม่รับด้วย `excluded_word:<คำ>` และคำถามไป free SQL เหมือนก่อนมี metric
  (server ซ้อม r10: "รายได้เทียบเป้า" ถูก compile เป็นรายได้เทียบปีก่อน เพราะ metric `revenue` ไม่มีเป้า — เป้าอยู่ใน `fact_*_target_monthly`)

## 4. เส้นทางของคำถาม (เมื่อ context มี metric)

1. `metric_compiler.load_metrics(context)` (active เท่านั้น, อ่าน DB ตอน request — ไม่ผ่าน prompt cache 6 ชม.) · `match_metrics(question)` จับคำพ้องยาวสุดก่อน
2. header ของ pass 1 ได้รายการ metric (ชื่อ + คำพ้อง) + บรรทัด "metric ที่ตรงกับคำในคำถาม" + กฎข้อ 6 ให้ใส่ `metric_id` — context ที่ไม่มี metric prompt เท่าเดิมทุกไบต์
3. `plan(intent, question, resolved, matched, reference_period, tables)` → `CompileRequest` เมื่อ: `metric_id` ใช้ได้ (หรือ code จับได้ตัวที่เจาะจงกว่า; ชื่อคอลัมน์ของ official_total ก็แปลงให้),
   รูป `aggregation`/`ranking` งวดเดียว, มิติ/ตัวกรองอยู่ในที่ประกาศ, mapping ที่ **ถูกกระตุ้นจริงในคำถามและไม่ใช่ชื่อ metric เอง** = ไม่มี; filter บนคอลัมน์งวดถือเป็นงวด ไม่ใช่ตัวตัดสิทธิ์
4. `compile()` → SQL หนึ่งคำสั่ง (ไม่มีมิติ/ตัวกรองหน่วยงาน → `official_total` ถ้าตารางลงทะเบียน ไม่งั้น `dataset` + `official_scope`; มีมิติแต่ไม่มีตัวกรอง → `dataset` + `official_scope` และ `official=false`
   — ผู้ถามไม่ได้เลือกหน่วยงาน การแยกตามมิติจึงอยู่ในขอบเขตของรายงาน (D-3; แก้ 2026-10-24 — เดิมไม่ใส่ scope ทำให้ "ศูนย์ต้นทุนไหน EBT สูงสุด" ได้หน่วยนอก 2 สายงานขาย); มีตัวกรองหน่วยงาน → ไม่ใส่ scope และ `official=false` — หน่วยนอกขอบเขตยังคำนวณได้)
   · metric ที่ประกาศ `ranking` และคำขอมีมิติหรือจัดอันดับ (ไม่ใช่ยอดรวม/ไม่ใช่ตัวกรองอย่างเดียว): เพิ่ม `AND (scope)` และคอลัมน์ `base` ก่อนค่า metric; `ORDER BY` ชี้ที่ค่า metric เสมอ
   · การจัดอันดับ ("สูงสุด 10 อันดับ") = `ORDER BY` ค่าของ metric เมื่อ `intent_type=ranking`, มี `limit`, หรือ `ordering.column` เป็นชื่อของ metric เอง (id / name_th / คำพ้อง / คอลัมน์ official_total / ค่าใน `metrics`);
   `ordering` ตามคอลัมน์มิติอย่างเดียวไม่เรียง, ตามคอลัมน์ที่ไม่รู้จัก → `plan()` ไม่รับ
   → **ไม่เรียก pass 2** → guard / `validate_sql` / scope wrapper / execute / explain ตามเดิม (ขั้นอธิบายได้ชื่อ metric + note) · `QueryResult.metric` = `{id, name_th, unit, official, table}`
5. ทุกกรณีที่ `plan()` ไม่รับ → เส้นทางเดิม (LLM เขียน SQL) — จึงไม่มีทางแย่กว่าก่อน

พฤติกรรมของ pass 1 จริง (gpt-4.1-mini) ที่ unit test ไม่เคยเห็นและ `plan()` รองรับแล้ว: ใส่งวดลง `filters` (`time_key = 202609`), เขียน `metric_id` เป็นชื่อคอลัมน์ (`ebt_ex_personnel`),
สะท้อนชื่อ metric กลับมาเป็น `matched_mappings`, คัดลอก mapping กลาง ("สายงาน") ทั้งที่คำถามไม่มี, ใส่ชื่อ metric ลง `ordering.column` ("ebt") และส่ง "10 อันดับแรก" มาเป็น `aggregation` + `limit`
(2026-10-24 — ก่อนแก้ `supports()` ปฏิเสธ ทำให้ EBT รายศูนย์ต้นทุนตกไป pass 2 แล้วได้ SQL ที่นับแต่รายได้และ SUM `amount_ytd` ข้าม 9 เดือน: `query_audit` 407) — ก่อนโทษ compiler ให้อ่าน `Pass 1 complete … Intent:` ใน log ก่อน

พฤติกรรมของ pass 1 ที่เจอกับ `sales_vs_target` บน server ซ้อม (2026-10-25, 7 รอบ × 11 คำถาม) และ `plan()` รับแล้ว — ใช้กับทุก metric ยกเว้นที่ระบุ:
- server ซ้อม r4: ใส่คอลัมน์งวดหรือ `period.parts` ลง `dimensions` ในคำถามงวดเดียว → ตัดออกเมื่อมีเดือนหรือ filter `=` ระบุงวด ไม่มี filter ช่วงงวด (ยกเว้นช่วงตั้งแต่ต้นปีถึงงวดที่ถาม เมื่อมีคำว่า "สะสม" และ `time_range.cumulative` = true) และไม่มีคำแนวโน้ม
- server ซ้อม 20261026-0720 §C.4: `year = 2026` + `month = 9` → filter งวด `202609` เฉพาะเมื่อประกาศ `period.parts`; ใช้กฎงวด / YTD / comparison เดิม
- เมื่อประกาศ `period.parts`: month `<=` M = เดือน 1..M = ยอดสะสม ณ M
- server ซ้อม 20261026-0947: `bu_seq = 8` → ตัวกรองค่าตัวเลข (`=` / `IN`) ใช้ได้เฉพาะมิติที่เป็นตัวเลข (ชนิดจาก `schema_metadata`) และ render เป็นตัวเลข; บนคอลัมน์ข้อความยังปฏิเสธ
- ตัวกรองที่เป็น**นิยามของ metric เอง** (`metric = 'actual'`, `metric IN ('actual','target')`) = คอลัมน์ที่ไม่ใช่มิติ ที่ทุก term เลือกด้วยค่าคงที่ และค่าที่กรองอยู่ในค่าที่ term เลือก → ตัดทิ้ง
  (`metric = 'forecast'` ยังปฏิเสธ); mapping ที่ pass 1 แต่งขึ้นซึ่ง condition เป็นนิยามเดียวกัน (`ยอดขาย` → `metric = 'actual'`) ไม่บล็อก
- mapping ที่ keyword **มีชื่อของ metric อยู่ข้างใน** ("ยอดขายเทียบเป้า" ⊃ "เทียบเป้า") หรือชื่อคอลัมน์ที่ metric แสดง ("ยอดขายบริการรวมทั้งบริษัท" ⊃ "ยอดขายบริการ" ของ `extra_columns`) ไม่บล็อก
- ตัวกรองหลายตัวบนคอลัมน์เดียว = ทางเลือก (OR): "ฝ่าย A และฝ่าย B" มาเป็น LIKE สองตัวบน `unit_fname` — เดิม AND กันจนได้ 0 แถว
- คำถามที่มีช่วง "ม.ค.-ก.ย." / "มกราคม ถึง …" = ยอดสะสมถึงเดือนท้าย แม้ pass 1 ใส่ `cumulative: false` (ช่วงที่ไม่เริ่ม ม.ค. ยังอ่านตาม pass 1)
- เฉพาะ metric ที่ประกาศ `ranking.threshold`: `comparison` / `lookup` = เทียบกับเส้น ไม่ใช่กับปีก่อน (อ่านเป็น aggregation, ตัด period ออกจาก dimensions);
  `ordering.column` ที่ไม่ใช่มิติ ("achievement_diff", "amount - target_amt") = เรียงตามค่าของ metric

## 5. เพิ่ม/แก้ metric (ลำดับที่ต้องรักษา)

1. NT-Report: แก้ `DOMAINS[<domain>]["metrics"]` ใน `tools/feed/domains.py` → bump `schema_version` (PATCH ถ้าแค่ metric/กฎ, MINOR ถ้าเพิ่มคอลัมน์อ้างอิง) → `gen_contract.py --domain <d>` → `pytest tools/feed` (`test_metrics_contract.py` ตรวจการอ้าง) → `build_feed.py --domain <d>`
2. AI: ตาราง `schema_metrics` ต้องมีแล้ว (`scripts/migrate_schema_metrics.py`, idempotent — เพิ่มคอลัมน์ `extra_columns` เมื่อ 2026-10-25 และ `datasets` เมื่อ 2026-10-26; **ต้องรันก่อน restart** ไม่งั้น contract re-sync ของทุก feed context จะล้มเหลวและเก็บ knowledge เดิมไว้ ทำให้ contract ที่เปลี่ยนหรือ metric `datasets` ใหม่ไม่ถึง `schema_metrics`; ตั้งแต่ 2026-10-26 `load_metrics` ยังอ่านแถวที่มีอยู่ได้) — contract ที่เปลี่ยน re-sync เองใน request ถัดไป; ถ้าคอลัมน์ของ dataset เปลี่ยน → `register_file_source --domain <d>`
3. ตรวจ: `SELECT metric_id, source, status FROM schema_metrics WHERE context_name='feed_<d>'`; log `Metric compiled: <id>`
4. metric ของ legacy context (ไม่มี contract) ยังไม่มีทางประกาศ (admin UI = งานถัดไป); ถ้าใส่ตรงลงตารางให้ `source='manual'`

## 6. ที่ยังไม่ทำ / ข้อควรรู้
- รูปที่ไม่ compile (trend หลายงวด, detail, เทียบสองงวด) ยังไปทาง LLM — ขั้น 2 ของ RESEARCH §4: ส่ง expression ให้ pass 2 + guard, compile ×2 สำหรับ ratio/YoY
- "สายงานไหน … สูงกว่า" ให้ LIMIT 1 ทั้งสองทาง แต่เฉลยอยากเห็นทุกค่า · `cost_ratio` ยังไม่ประกาศ · mapping id 57 "สายงาน" ยังรบกวนทางเดิม
- REST `/api/v1/query` ยังไม่ส่ง `metric` ออกไปใน response (มีใน `QueryResult` ภายใน) — เพิ่มได้ผ่าน `app/core/outbound.py` เมื่อ portal ต้องการป้าย "ยอดทางการ"
- ค่าอ้างอิงระดับหน่วยย่อย (น่าน) ยังไม่มีใน `control_totals` (D-6(b)) — ชุดวัด "น่าน" ใช้ค่าจากไฟล์ feed ที่เจ้าของยืนยัน
