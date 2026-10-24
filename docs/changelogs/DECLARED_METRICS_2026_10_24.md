# Declared metrics — metric ประกาศเป็นข้อมูล, code ประกอบ SQL แทน pass 2 (2026-10-24)

วิจัย: `plan/RESEARCH_DECLARED_METRICS.md` · ผลวัด: `plan/RESULT_P8_DECLARED_METRICS.md` · ขึ้นของจริง: `plan/GOLIVE_DECLARED_METRICS.md` · คู่มือ: `docs/DECLARED_METRICS.md`
AI `main` `ff886c0..01cf5ee` · NT-Report `main` `001c0c3..541b3e1` (contract ebt **1.5.0**)

## สิ่งที่เพิ่ม

| เรื่อง | ก่อน | หลัง |
|---|---|---|
| ที่อยู่ของสูตร | ข้อความใน `business_rules` → system prompt + RAG (pass 1) ให้โมเดลตีความ | `metrics:` ใน contract (terms + expr + dimensions + period + official_scope/total + reference) → `schema_metrics` (provenance `declared`) |
| pass 1 | `metrics: [คอลัมน์]` + `aggregate_function` ตัวเดียว | + `metric_id`; header มีรายการ metric (ชื่อ/คำพ้องเท่านั้น) + บรรทัดที่ code จับได้ |
| SQL ของคำถามแบบ metric | pass 2 (LLM) — "EBT ไม่รวมบุคลากร" = SUM(ebt) | `metric_compiler.plan()` → `compile()` — SQL จาก code, ไม่เรียก pass 2; รูปที่ไม่รองรับไปทางเดิม |
| ความรู้ของ NT-Report | สูตร nohr อยู่ใน code ของรายงานเท่านั้น | คอลัมน์ `hr_expense` / `ebt_ex_personnel` (+`_month`) ใน 2 ตารางอนุพันธ์ + control_totals + กฎ `ebt_ex_personnel_definition` + `metrics:` 3 ตัว + eval P11–P14 |
| ตาราง config | 9 ตารางความรู้ | + `schema_metrics` (`scripts/migrate_schema_metrics.py`; server เริ่มได้แม้ยังไม่มี — sync ข้าม) |
| CI | แดงตั้งแต่ DuckDB 2.0.0 (recursive CTE) | `check_select` อ่าน `value.query_node` ด้วย (`01cf5ee`) |

## ผลวัด (สำเนา, code สุดท้าย 2 รอบ × 63 ข้อ, ฝั่งก่อน = contract 1.5.0 เดียวกัน + code เดิม)
น่าน 2/8 → **8/8** (54,469,208.99 ตรงเจ้าของ) · ebt 19/28 → 20/28 · context ไม่มี metric ไม่เปลี่ยน · รวม 90 → 98 /126, McNemar exact p = 0.039 · เร็วขึ้นเมื่อ compile (ไม่มี pass 2)

## แก้หลังขึ้นจริง (2026-10-24 บ่าย — จากการถามผ่าน Claude Desktop/MCP)
- "หน่วยงานไหนได้ EBT สูงสุด 10 อันดับแรก" ตกไป pass 2 แล้วได้ SQL ที่นับแต่ `รวมรายได้ทั้งสิ้น` และ SUM `amount_ytd` ข้าม 202601–202609 (อันดับ 1 = 1,744 ล้าน ทั้งที่ทั้งสายงาน 2 มี 901 ล้าน; `query_audit` 407)
  สาเหตุ: `supports()` ปฏิเสธ `ordering.column` ที่เป็นชื่อ metric เอง ("ebt") และ `plan()` ใส่ ORDER BY ให้เฉพาะ `intent_type=ranking` → แก้ให้ชื่อ metric / official column / ค่าใน `metrics` เป็น "เรียงตามค่า" และ `aggregation`+`limit` ก็เรียง
- การแยกตามมิติโดยไม่มีตัวกรอง (เช่น รายศูนย์ต้นทุน) ใส่ `official_scope` แล้ว (D-3) — เดิมไม่ใส่ ทำให้ 2P10201 (สายงานโครงสร้างพื้นฐาน) ขึ้นอันดับ 1; มีตัวกรองยังคำนวณหน่วยนอกขอบเขตได้เหมือนเดิม
  ผลที่ถูก (สะสม ก.ย. 2569, 2 สายงานขาย): ระยอง 130.03 · แหลมฉบัง 124.88 · กรุงเทพกลาง 2 106.81 … สุพรรณบุรี 74.44 ล้านบาท — ยอดสายงานจากสูตรเดียวกันตรง `fact_ebt_division_monthly` (901.53 / −330.68)

- "ฝ่ายที่มี ebt สูงสุด 5 อันดับแรก" ตอบระดับสายงาน (2 แถว, ตัวเลขถูก ระดับผิด) — ความรู้ว่า "ฝ่าย = `unit`" ไม่เคยถึงโมเดล **3 ชั้นซ้อน** (แก้ครบแล้ว 2026-10-24 บ่าย, คำตอบตรง oracle: ภาคตะวันออกตอนล่าง 462.78 … ภาคใต้ตอนบน 245.14 ล้านบาท):
  1. contract ทุกโดเมนไม่มี `description` ของคอลัมน์ระดับหน่วยงาน → NT-Report `c5f6441` (revenue 2.3.3 / expense 1.2.5 / sales 1.3.4 / ebt 1.5.1: สายงาน > กลุ่ม > ฝ่าย > ส่วน)
  2. `prompt_builder._build_schema_from_metadata` แสดงเฉพาะ `special_notes` ไม่แสดง `description` ที่ contract sync เขียน → `f94d5e9` (`special_notes or description`)
  3. schema ใน prompt มีแค่ `main_view` (`fact_ebt_division_monthly`) และ catalog ของ metric ไม่บอกมิติ → `6cda6c6` (`dimension_labels` + catalog "unit (ฝ่าย), …") — **ยังไม่พอ**;
     ที่ตัดสินจริงคือ `master_hierarchy` ของ `feed_ebt` ซึ่งว่างเปล่า (feed context ไม่เคยมี level) → เพิ่ม 5 ระดับ `manual` ผ่าน `HierarchyService.upsert_level`
     (สายงาน/กลุ่ม/ฝ่าย/ส่วน/ศูนย์ต้นทุน → division/sub_division/unit/sub_unit/cost_center + detection_keywords) → level note บอก pass 1 ว่า "ฝ่าย → `unit`" — เป็น **config ใน config.db ไม่ใช่ code**;
     revenue/expense/sales ยังไม่มี level ระดับหน่วยงาน (revenue มี hierarchy ผลิตภัณฑ์อยู่แล้ว 3 ระดับ — ตารางมี UNIQUE(context, level) จึงต้องออกแบบก่อน) → เข้า `plan/PLAN_METRICS_CONVERGENCE.md`

## ที่ต้องรู้ตอนแก้ต่อ
- ตัวอ่าน metric ใหม่ต้องกรอง `status='active'` และอ่าน DB ตอน request (prompt cache 6 ชม. ไม่เห็น) · ตัวเขียนผ่าน `_declare`
- ลำดับขึ้นของ: AI code → migrate → contract/dist ของ NT-Report → `register_file_source` (ตารางได้คอลัมน์ใหม่)
- pass 1 จริงใส่งวดลง `filters`, เขียน `metric_id` เป็นชื่อคอลัมน์, สะท้อนชื่อ metric เป็น mapping — `plan()` รองรับ (`tests/unit/test_metric_intent.py`)
- ยังไม่ทำ: expression → pass 2 สำหรับ trend/detail, ratio สองงวด, admin UI สำหรับ metric `manual`, `metric` ใน REST response
