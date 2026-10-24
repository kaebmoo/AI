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

## ที่ต้องรู้ตอนแก้ต่อ
- ตัวอ่าน metric ใหม่ต้องกรอง `status='active'` และอ่าน DB ตอน request (prompt cache 6 ชม. ไม่เห็น) · ตัวเขียนผ่าน `_declare`
- ลำดับขึ้นของ: AI code → migrate → contract/dist ของ NT-Report → `register_file_source` (ตารางได้คอลัมน์ใหม่)
- pass 1 จริงใส่งวดลง `filters`, เขียน `metric_id` เป็นชื่อคอลัมน์, สะท้อนชื่อ metric เป็น mapping — `plan()` รองรับ (`tests/unit/test_metric_intent.py`)
- ยังไม่ทำ: expression → pass 2 สำหรับ trend/detail, ratio สองงวด, admin UI สำหรับ metric `manual`, `metric` ใน REST response
