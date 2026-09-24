# Prompt สำหรับ repo NT-Report — กฎเชื่อมรายงาน EBT กับ expense feed และ sales feed (2026-09-23)

> ส่ง code block ข้างล่างให้ session ที่ทำงานใน repo NT-Report
> ที่มา: ผู้ใช้อยากถามต่อจากรายงาน EBT ว่า "ค่าใช้จ่ายที่คิดใน EBT มีรายละเอียดอะไรบ้าง" — `fact_ebt` แยกได้ถึงกลุ่มค่าใช้จ่าย (`group_1`) เท่านั้น
> ส่วนรายละเอียดระดับ GL / หมวด (`cat_l2_th`) อยู่ใน expense feed. ฝั่ง AI ไม่ JOIN ข้ามโดเมนและไม่ถือว่าสองชุดเท่ากันเอง
> → ต้องมีกฎจากเจ้าของนิยาม EBT. ชุดวัดฝั่ง AI: `scripts/eval/ebt_expense_golden.json` (5 ข้อ)

```
ทำงานใน repo NT-Report (branch ตามปกติ, commit เป็นก้อนต่อข้อ, ยังไม่ push)
แก้ที่ tools/feed/domains.py → gen_contract → contracts/*.yaml แล้ว build feed ใหม่ — bump schema_version (PATCH = rule/description)
AI re-sync knowledge จาก contract เอง ฝั่ง AI ไม่ต้องรันอะไร

เป้าหมาย: ให้ AI ตอบ "ค่าใช้จ่ายที่คิดใน EBT มีรายละเอียดอะไรบ้าง" ลงถึงระดับ GL / หมวด จาก expense feed ได้ โดยมีกฎที่เจ้าของนิยาม EBT ประกาศ

สิ่งที่ฝั่ง AI ตรวจแล้ว (dist/*/latest: ebt 1.4.2 งวด 202607, expense 1.2.2 งวด 202608):
- fact_ebt_total_monthly.expense_month = SUM(fact_expense.expense_value_thb) ของ cost_center ที่ dim_org_snapshot ของงวดเดียวกัน
  (effective_month = time_key) ระบุ division เป็น 'สายงานขายและปฏิบัติการลูกค้า 1' หรือ '… 2'
  → ตรงทุกสตางค์ 16 จาก 19 งวด (202501–202607) และตรงรายกลุ่มด้วย: fact_ebt.group_1 (ตัดเลขนำหน้า) = fact_expense.expense_group_name
  (ใช้ cost_center จาก fact_ebt ของงวดเดียวกันแทน dim_org_snapshot ก็ได้ผลเท่ากันทุกงวด)
- 202603 / 202604 / 202605 ต่างกันเท่ากับรายการ ER/MSP พอดี (166,181,565.07 / −875,671.37 / 5,939,303.52)
  expense feed เก็บ ER เป็นกลุ่มแยก expense_group_name = 'ค่าใช้จ่ายตอบแทนแรงงาน-ER' — expense_group_seq = 1 ซ้ำกับ
  'ค่าใช้จ่ายตอบแทนแรงงาน' จึงจับคู่ด้วยเลข seq อย่างเดียวไม่ได้
- 202606 expense feed มากกว่า 51,102,551.37 = GL 54691907 (ค่าที่ปรึกษา/วิชาชีพ, กลุ่มค่าใช้จ่ายดำเนินงานอื่น) ทั้งก้อน บน 13 cost center
  (มากสุด 2R10205 11,569,893.14 · 2R10204 8,783,527.39 · 2R20202 6,512,343.12), source_file EXPORT_EXPENSE_BEFORE_NT_2026-6.csv
  — กลุ่ม 16 ใน fact_ebt ของ 2 สายงาน = 57,767,790.41 แต่ใน expense feed = 108,870,341.78

1) หาสาเหตุของ 202606: GL 54691907 ก้อนนี้ควรอยู่ในค่าใช้จ่ายของ EBT เดือนนั้นไหม
   (บันทึกหลังตัดยอด EBT / reclass / ตัดออกตามนโยบาย / อื่น ๆ)
   - ถ้าเป็นข้อยกเว้นตามนโยบาย → ใส่เป็นเงื่อนไขในกฎข้อ 2
   - ถ้าเป็นเรื่องเวลาตัดยอด → ระบุในกฎว่างวดไหนไม่เท่าและเพราะอะไร (หรือ rebuild ถ้าต้นทางแก้แล้ว)
   ห้ามปรับตัวเลขให้ตรงกัน — ถ้าหาสาเหตุไม่ได้ ให้รายงานกลับมาตามจริง

2) expense — business_rule ใหม่ (ปรับถ้อยคำได้ แต่ต้องมีเงื่อนไขครบ):
   {"id": "expense_in_ebt_report",
    "text": "ค่าใช้จ่ายที่คิดในรายงาน EBT = fact_expense ของ cost_center ที่ dim_org_snapshot ของงวดเดียวกัน (effective_month = time_key)
             ระบุ division = 'สายงานขายและปฏิบัติการลูกค้า 1' หรือ 'สายงานขายและปฏิบัติการลูกค้า 2' และไม่รวม
             expense_group_name = 'ค่าใช้จ่ายตอบแทนแรงงาน-ER'. ใช้ตอบรายละเอียดที่ fact_ebt ไม่มี (GL, cat_l2_th, cost_nature, cost_center);
             ยอดค่าใช้จ่าย/EBT ทางการของรายงานยังมาจาก ebt feed. ยอดรายกลุ่มเท่ากับ fact_ebt.group_1 (ตัดเลขนำหน้า).
             สายงานอื่นไม่อยู่ในรายงาน EBT. <เงื่อนไข/งวดยกเว้นจากข้อ 1>"}

3) ebt — business_rule ชี้ทาง (PATCH):
   {"id": "ebt_expense_detail_in_expense_feed",
    "text": "fact_ebt แยกค่าใช้จ่ายได้ถึง group_1 (กลุ่มค่าใช้จ่าย) เท่านั้น — รายละเอียดระดับ GL / หมวด (เช่น ค่าไฟฟ้า, ค่ารักษาความปลอดภัย)
             ไม่มีในชุดนี้: ให้บอกว่าต้องดูจาก expense feed ตามกฎ expense_in_ebt_report และห้ามใช้ยอดของกลุ่ม
             (เช่น 05.ค่าสาธารณูปโภค) ตอบแทนหมวดย่อย"}

4) กันกฎเสียเงียบ: ตอน build ตรวจว่าทุกงวดที่มีทั้งสองโดเมน SUM(expense feed ตามกฎข้อ 2) = fact_ebt_total_monthly.expense_month (tol abs 1.0)
   งวดที่ต่างและมีคำอธิบายจากข้อ 1 ให้อยู่ใน allowlist พร้อมเหตุผล; ไม่ตรง = build ไม่ผ่าน
   (หรือเขียนลง manifest.reconcile ถ้า pipeline ตอนนี้ fail ข้ามโดเมนไม่ได้)

5) ebt ↔ sales — กฎ ebt_sales_base_vs_sales_dw ("ยังไม่มี bridge ห้ามเทียบ") ขัดกับข้อมูล: ฝั่ง AI ตรวจแล้ว
   fact_ebt_total_monthly.sales_base_revenue_month = SUM(fact_sales.amount) ที่ metric = 'actual'
   AND sales_line IN ('สายงานขายและปฏิบัติการลูกค้า 1', 'สายงานขายและปฏิบัติการลูกค้า 2')   ← sales_line ตามงวด ไม่ใช่ sales_line_current
   AND business_group เป็น 1–7 (ไม่รวม 8.รายได้อื่น และ โครงการภาครัฐ)
   → ตรงทุกสตางค์ 17 จาก 19 งวด และตรงราย business group ด้วย (ebt group_1 '04.Fixed Line & Broadband' = sales '4.Fixed Line & Broadband')
   - 202603 / 202604: BG 7 ของสายงาน 2 ต่าง −92,523.33 / +92,523.33 (ย้ายงวด; YTD ณ 202604 ตรง)
   - BG 8 ไม่เท่ากัน: ebt '08.รายได้อื่น' 9.97 M vs sales '8.รายได้อื่น' ของ 2 สายงาน 53.11 M (ก.ค. 69) — EBT ตัด 08 ออกจากยอดทางการอยู่แล้ว
   - เทียบด้วย cost_center จะไม่ตรง (ต่าง 2.8–234 M ต่องวด) — ต้องใช้ sales_line
   ขอ:
   a) ยืนยันว่าความเท่ากันนี้เป็นนิยาม (ไม่ใช่บังเอิญ) และอธิบายการย้ายงวด 92,523.33 + BG 8
   b) แทน ebt_sales_base_vs_sales_dw ด้วยกฎ bridge เช่น
      {"id": "ebt_sales_base_equals_sales_feed",
       "text": "รายได้ (ฐานยอดขาย) รายเดือนของ EBT = fact_sales ของ sales feed ที่ metric='actual', sales_line = 2 สายงานขาย
                (sales_line ตามงวด ไม่ใช่ *_current), business_group 1–7. ใช้ตอบรายละเอียดที่ fact_ebt ไม่มี (product, sales_group,
                sales_dept, geo); รหัสกลุ่ม ebt '0N.' = sales 'N.'. BG 8 ไม่เท่ากัน ห้ามเทียบ. <ข้อยกเว้นจาก a>"}
      + กฎชี้ทางฝั่ง ebt ทำนองเดียวกับข้อ 3 (รายละเอียดระดับผลิตภัณฑ์ของรายได้ใน EBT อยู่ใน sales feed)
   c) ใส่การตรวจแบบข้อ 4 สำหรับคู่นี้ด้วย
   กฎ ebt_sales_base_is_not_revenue (ห้ามเทียบกับ revenue feed) ยังถูกต้อง — ไม่ต้องแก้

แจ้งฝั่ง AI เมื่อเสร็จ: schema_version ใหม่ของ ebt / expense / sales, id + ข้อความจริงของกฎทุกข้อ, สาเหตุของ 202606, การตรวจข้อ 4 อยู่ที่ไหน
```

## ฝั่ง AI
- วัด baseline **ก่อน** NT-Report แก้ แล้ววัดซ้ำหลัง re-sync บนสำเนา DB (multi-context ปิด = เส้นทาง context เดียว; ข้อ 5 ต้องเปิดบนสำเนาถึงจะแตกสองส่วน):
  `python -m scripts.eval.run_eval --cross-domain scripts/eval/ebt_expense_golden.json`
- ข้อ 1 กับ 4 ตอบจาก `feed_ebt` ได้อยู่แล้ว (ตัวควบคุม) — ข้อ 4 จับคนที่รวม ER: `LIKE 'ค่าใช้จ่ายตอบแทนแรงงาน%'` ใน expense feed ได้ 653.9 M แทน 487.7 M
- ไม่มีคำถามของงวด 202606 จนกว่า NT-Report จะตอบข้อ 1

## ผล — NT-Report เสร็จ 2026-09-23 (ebt 1.4.3 / expense 1.2.3 / sales 1.3.3, build 202608; commit `e76f881`..`2cf7e5d` ใน NT-Report ยังไม่ push)
- **202606 = เรื่องเวลา ไม่ใช่นโยบาย:** GL 54691907 ชื่อใน DW คือ "บ-ค่าใช้จ่ายเกี่ยวกับคดีความ" (ที่นี่เรียกตามหมวด cat_l2 "ค่าที่ปรึกษา/วิชาชีพ") —
  13 รายการบันทึกย้อนเข้า มิ.ย. มากับ re-export 9 ก.ย.; ไฟล์ EBT DW มิ.ย. (ได้ 17 ก.ย.) มีแล้ว แต่ ebt feed 1.4.2 build ก่อน step 01 ประมวลผล →
  rebuild แล้วตรงทุกงวด ไม่มีงวดยกเว้น. **ตัวเลขทางการของ ebt restate:** สะสม ก.ค. ค่าใช้จ่าย 8,050.00 → 8,101.10 MB, EBT 417.33 → 366.22 MB
  (ชุดวัดฝั่ง AI ไม่มีที่ฝัง 417.33 — ตรวจแล้ว)
- **±92,523.33 ไม่ใช่การย้ายงวด:** รายการตั้ง (มี.ค.) / กลับรายการ (เม.ย.) BG 7.1 ที่ cost center 2Q30000 — EBT นับเป็นสายงาน 2, Sales DW ลง `sales_line = 'หน่วยงานอื่น'` (ข้อยกเว้นในกฎ)
- กฎใหม่: `expense_in_ebt_report`, `ebt_expense_detail_in_expense_feed`, `ebt_sales_base_equals_sales_feed`, `ebt_revenue_detail_in_sales_feed`; ลบ `ebt_sales_base_vs_sales_dw`
- ตรวจทุก build: `BRIDGES` / `bridge_checks()` ใน `tools/feed/domains.py` → `manifest.reconcile.bridges` (ต่างนอกข้อยกเว้น = build ไม่ผ่าน)

### ฝั่ง AI (ตรวจบนสำเนา config.db 2026-09-23)
- re-sync: ebt + expense ขึ้นครบ (instruction + เอกสาร). **sales 1.3.3 เข้าคิว `knowledge_proposals` แทน** — `feed_sales` เป็น `manual`
  ตั้งแต่ 2026-09-22 07:59 → กฎ bridge อยู่ในเอกสาร (RAG) แต่ไม่อยู่ใน instruction จนกว่าคนจะตัดสินข้อเสนอ (ยังไม่มีทางตัดสิน — Plan 8 §9.2)
- `ebt_expense_golden.json` หลังกฎขึ้น: **0/5 (value match 1/5)**, P50 9.5 s — ทุกข้อ route ไป `feed_expense`
  - ข้อ 1 ✅ ทำตามกฎครบ (2 สายงานผ่าน `dim_org_snapshot`, ไม่รวม ER)
  - ข้อ 2 ใช้ `expense_group_name LIKE '%ค่าไฟฟ้า%'` (ค่าไฟฟ้าอยู่ใน `cat_l2_th`) + ปีผิด 202407
  - ข้อ 3, 4, 5 ไม่กรอง 2 สายงานเลย; ข้อ 4 ติดกับดัก ER (`LIKE '%ค่าใช้จ่ายตอบแทนแรงงาน%'`); ข้อ 5 ไม่มีส่วน EBT (multi-context ปิด)
  - baseline ก่อนกฎวัดไม่ได้แล้ว (`latest/` ชี้ build ใหม่)
- ผลนี้รันบน working tree ที่มีงานค้างของอีก session (Codex round 2) — ไม่กระทบเส้นทางนี้ แต่ให้วัดซ้ำหลังงานนั้น commit

### ขึ้นของจริง 2026-09-24 22:57
- `feed_sales` คืนเป็น `declared` (เจ้าของอนุมัติ; สาเหตุแก้ใน `6a7a4c5`) → re-sync บน config.db จริง: ebt 1.4.3 / expense 1.2.3 / sales 1.3.3 ขึ้นครบ ไม่มีข้อเสนอค้าง, กฎใหม่ 4 ข้อ active — ผู้ใช้เห็น EBT สะสม ก.ค. 366.22 MB (เดิม 417.33)
- ยังค้างฝั่ง AI: golden 0/5 (ข้างบน) — golden example ของคำถาม "…ใน EBT" (คนละชุดกับข้อสอบ) + mapping หมวด → `cat_l2_th`, แล้ววัดซ้ำ

### แก้ 0/5 ฝั่ง AI — ความรู้ 2 ชิ้น ไม่แก้ code (วัดบนสำเนา 2026-09-24)
**สาเหตุ:** กฎ `expense_in_ebt_report` ถึงโมเดลทั้งสอง pass แต่ two-pass pass 1 (โมเดล cheap) แทบไม่แปลงเป็น filter และ pass 2 ถูกสั่ง
"ห้ามเพิ่ม WHERE filter ที่ไม่อยู่ใน Filters ข้างต้น" (`hybrid_flow.py` ~1375) · ตารางคอลัมน์ใน prompt ไม่พิมพ์ description ของ contract จึงไม่รู้ว่า
ค่าไฟฟ้าอยู่ใน `cat_l2_th` · pass 1 ใส่ปี พ.ศ. ใน `time_key` (256907) · routing: "ค่า/ค่าใช้จ่าย/จ่าย" = 3 คะแนนให้ feed_expense ทุกข้อ
**ความรู้ที่ใส่** (semantic mapping ถูกคัดลอกเข้า `matched_mappings` ของ pass 1 และ pass 2 ใช้ตามตัว — รอดผ่าน two-pass; metadata = field ที่ contract ไม่เขียน จึงไม่หลุดตอน re-sync):
```sql
INSERT INTO schema_semantic_mapping (keyword, keyword_type, target_column, target_condition, full_condition, description, priority, is_active, context_name, source, status)
VALUES ('EBT', 'term', 'cost_center', '',
  'cost_center IN (SELECT o.cost_center FROM feed_expense_dim_org_snapshot o WHERE o.division IN (''สายงานขายและปฏิบัติการลูกค้า 1'', ''สายงานขายและปฏิบัติการลูกค้า 2'') AND CAST(o.effective_month AS INTEGER) = time_key) AND expense_group_name <> ''ค่าใช้จ่ายตอบแทนแรงงาน-ER''',
  'ค่าใช้จ่ายที่คิดในรายงาน EBT = เฉพาะ cost center ของ 2 สายงานขาย ณ งวดนั้น และไม่รวมกลุ่ม ค่าใช้จ่ายตอบแทนแรงงาน-ER — ใส่เงื่อนไขนี้ทุกครั้งที่คำถามพูดถึง EBT',
  10, 1, 'feed_expense', 'manual', 'active');
UPDATE schema_metadata SET display_name_th = 'รายการค่าใช้จ่าย (หมวดย่อย L2)', special_notes = 'ชื่อรายการค่าใช้จ่ายย่อย (เช่น ค่าน้ำประปา) — คำถามที่เอ่ยชื่อรายการระดับนี้ให้กรองด้วย cat_l2_th ไม่ใช่ expense_group_name; "รายการไหน" ภายในกลุ่ม = GROUP BY cat_l2_th' WHERE table_name = 'feed_expense_fact_expense' AND column_name = 'cat_l2_th';
UPDATE schema_metadata SET display_name_th = 'กลุ่มค่าใช้จ่าย (หมวดใหญ่)', special_notes = 'กลุ่มใหญ่ราว 19 กลุ่ม (เช่น ค่าสวัสดิการ, ค่าเช่าและค่าใช้สินทรัพย์) — 1 กลุ่มมีหลายรายการ cat_l2_th; ชื่อที่ต่างกันแค่ส่วนต่อท้าย (เช่น -ER) เป็นคนละกลุ่ม' WHERE table_name = 'feed_expense_fact_expense' AND column_name = 'expense_group_name';
UPDATE schema_metadata SET display_name_th = 'งวด ค.ศ. (YYYYMM)', special_notes = 'ปี ค.ศ. เสมอ: (ปี พ.ศ. − 543) × 100 + เดือน เช่น มกราคม พ.ศ. 2568 = 202501 — ห้ามใช้เลขปี พ.ศ. ใน time_key' WHERE table_name = 'feed_expense_fact_expense' AND column_name = 'time_key';
```
**แถว mapping เป็นสำเนาของกฎ `expense_in_ebt_report` (contract expense 1.2.3)** — ถ้า NT-Report เปลี่ยนขอบเขต EBT ต้องแก้แถวนี้ด้วย; ทางถาวรคือแก้ two-pass ให้เคารพกฎของ context เอง แล้วถอดแถวนี้
ถอยกลับ: `UPDATE schema_semantic_mapping SET is_active = 0 WHERE keyword = 'EBT' AND context_name = 'feed_expense'` + ตั้ง `display_name_th` / `special_notes` ของ 3 แถวกลับเป็น NULL

| ชุด (Python 3.10 = มี RAG แบบ server จริง) | ก่อน | หลัง |
|---|---|---|
| `ebt_expense_golden` (5) | 0/5 | **3/5, 4/5** (agent: 4/5 × 4 รอบ) — ข้อ 5 ต้อง multi-context |
| `run_eval --context feed_expense` (12) | 8/12, 8/12 | 8/12, 8/12 — ข้อที่ผิดชุดเดียวกัน (69, 70, 72, 73) |

**ปัญหาแยกที่พบ (มีอยู่แล้วบน server จริง ไม่เกี่ยวกับ fix นี้):** feed_expense ได้ 12/12 เมื่อไม่มี RAG (Python 3.14) แต่ 8/12 เมื่อมี RAG — 4 ข้อที่ผิด
= "เดือน … 2568" ตอบเป็น 2026 เพราะตัวอย่างที่ RAG ดึงมาคือ "…พฤษภาคม 2569 → 202605" แล้วโมเดลลอกงวด · eval ที่รันด้วย 3.14 จึงไม่เห็น
**งานแก้ใน code ที่เสนอ** (task แยก): pass 2 ต้องใส่ filter ที่กฎ / mapping บังคับได้, พิมพ์ description ของ contract, กติกาเวลาใน pass 1,
ตัวอย่างจาก RAG ต้องไม่กำหนดงวดแทนคำถาม

**ขึ้นของจริง 2026-09-25 00:04** (เจ้าของอนุมัติ; backup ก่อนใส่ใน scratchpad ของ session `backup_20260925/`; mapping id 216; restart บน `b2a5ddd`) ·
วัดบนสำเนาของ DB จริงหลังขึ้น (Python 3.10 + RAG): **3/5, 3/5** — ข้อ 1, 3, 4 ถูกทุกรอบ · ข้อ 2 ใส่ขอบเขต EBT + ปีถูกแล้ว แต่กรอง
`expense_group_name LIKE '%ค่าไฟฟ้า%'` แทน `cat_l2_th` (pass 2 ซ่อนผล value lookup ของคอลัมน์ที่ pass 1 ไม่ได้เลือก — แก้ใน code, ไม่เพิ่ม mapping รายรายการ) ·
ข้อ 5 ต้อง multi-context
