# RESULT F10 — DataFeed Integration (pilot: revenue)

**วันที่:** 2026-07-11 | **Provider:** admin default (matcha)

## Import (Phase A)

- Source: `NT-Report/DataFeed/dist/revenue/latest` (schema 1.0.0, period 202605)
- Integrity gates ผ่านครบ 4 ชั้น: reconcile.ok ✓, sha256 16 ไฟล์ ✓, row counts 15 ตาราง ✓, control totals 522 แถวใน tolerance ✓
- **255,404 แถว ใน 3.4 วินาที** → ตาราง `feed_revenue_*` (8 fact + 7 dim) + `feed_import_log`

## Knowledge (Phase B)

- Context `feed_revenue` (main_view = `feed_revenue_fact_bu_monthly`)
- 159 schema_metadata rows + 21 vanna_documentation docs (ตาราง/grain/keys, business rules ทุกข้อ รวม `bg8_ytd_not_summable`, `sales_is_not_revenue`, กฎ year_month YYYYMM)
- Idempotent ✓ (รันซ้ำ → จำนวนเท่าเดิม)

## Golden (Phase C)

- 14 ข้อจาก control_totals (category=`feed_revenue`): grand total 4 งวด, per-BG (รวมชื่อไทย "7.กลุ่มบริการอื่นไม่ใช่โทรคมนาคม"), YTD 2 ข้อ — คำถามใช้เดือนไทย + พ.ศ. (exercise กฎแปลงปี)

## Baseline eval (Phase D)

| Metric | รอบแรก (value-based) | รอบสอง (strict — หลัง review P1-4) |
|--------|------|------|
| **exact_match (ค่า+ชื่อคอลัมน์)** | 13/14 = 92.9% | 0/14 (alias ที่โมเดลตั้งไม่ตรง golden) |
| **value_match (ค่าตรง ชื่อคอลัมน์ต่าง)** | — | 14/14 |
| **รวมค่าถูกต้อง (accuracy_incl_value_match)** | 92.9% | **100%** |
| Latency P50 / P95 | 10.5s / 17.4s | — |
| golden_broken | 0 | 0 |

**การตีความหลังเปลี่ยนเกณฑ์ (review P1-4):** ค่าตัวเลขถูกทุกข้อ แต่ชื่อคอลัมน์ (alias) ที่โมเดลตั้งไม่เคยตรงกับ golden ("revenue" vs "รายได้รวม" ฯลฯ) — `value_match` แสดงแยกให้ตรวจ projection ด้วยตาได้ ไม่ปนกับ headline accuracy

**Business rule ผ่านการพิสูจน์:** คำถาม YTD ทั้ง 2 ข้อ → SQL ใช้ `revenue_ytd` (ไม่ sum revenue รายเดือน) — กฎจาก contract เข้า knowledge จริง

## หมายเหตุ

- Acceptance ข้อ "ถามผ่าน UI 5 คำถาม" ยังไม่ได้ทำ (ต้องเปิด frontend) — eval execution-match ครอบคลุมพิสูจน์เดียวกันที่ระดับ API
- โดเมนอื่น (expense/sales/ebt): รัน 3 scripts เดิมซ้ำ (เขียนแบบ domain-agnostic แล้ว)
