# Prompt สำหรับ repo NT-Report — งานฝั่ง DataFeed/portal ที่ Plan 7 Phase 2–3 ของ AI ต้องใช้ (2026-09-19)

> ส่งทั้งไฟล์นี้ให้ session ที่ทำงานใน repo NT-Report — ฝั่ง AI เสร็จแล้วทั้ง re-sync knowledge อัตโนมัติ (Phase 2) และ `scope` (Phase 3)
> ที่มา: `plan/archive/RESULT_P7_PHASE2.md` (sales/ebt), `plan/archive/RESULT_P7_PHASE3.md` (scope), เจ้าของตัดสิน 2026-09-19: ทางเลือก A + "EBT = ยอดขาย − ค่าใช้จ่าย" โดย "ยอดขาย" = กลุ่มรายได้ใน fact_ebt (รายได้ฐานยอดขาย ≠ รายได้ในรายงานรายได้)

```
ทำงานใน repo NT-Report (branch ตามปกติ, commit เป็นก้อนต่อข้อ, ยังไม่ push)
AI assistant อ่าน DataFeed/dist/<domain>/latest/ ตรง และสร้าง knowledge จาก contracts/<domain>.yaml เอง
(re-sync อัตโนมัติเมื่อ contract เปลี่ยน — ฝั่ง AI ไม่ต้องรันอะไร) งานข้างล่างแก้ที่ tools/feed/domains.py → gen_contract → contracts/*.yaml
แล้ว build feed ใหม่ — bump schema_version ทุกครั้ง (PATCH = แค่ rule/description, MINOR = เพิ่ม field/คอลัมน์/ไฟล์)

1) sales — AI ตอบ "ยอดขายรวม ก.ค. 69" = 6,978 M เพราะรวม metric actual + target (actual จริง 3,290 M)
   - business_rule ใหม่: fact_sales.metric มี 'actual' และ 'target' ห้ามรวมกัน; "ยอดขาย" = metric='actual' เว้นแต่ถามเป้า
   - description ของ metric ให้ระบุค่าที่มีครบ (actual, target)
   - ระบุใน rule ให้ชัดว่า "ยอดขายรวมทั้งบริษัท" นับ BG ไหน (7 service-sales BG ตาม nt_total หรือรวม 8.รายได้อื่น/โครงการภาครัฐ)
   - control_totals ตอนนี้ SUM ทุกแถว (actual+target) → ให้เป็นยอด actual: เพิ่ม field `filter: {metric: actual}` ใน control_totals
     (AI จะรองรับ field นี้ใน gate + golden: WHERE <col> = <value> ก่อน aggregate) และ build control_totals.csv ใหม่ตามนั้น

2) ebt — AI ตอบ "กำไร ก.ค. 69" = +7,201 M (บวกรายได้กับค่าใช้จ่าย) และไม่มี control_totals
   - เจ้าของกำหนด: **EBT = ยอดขาย − ค่าใช้จ่าย** โดย "ยอดขาย" คือกลุ่มรายได้ใน fact_ebt (group_0 = '01.รายได้') →
       EBT = SUM(amount | measure_type='ADDITIVE', group_0='01.รายได้') − SUM(amount | measure_type='ADDITIVE', group_0='02.ค่าใช้จ่าย')
       (ค่าใช้จ่ายเก็บเป็นค่าบวก) — ค่าที่ควรได้ ก.ค. 69 ทั้งบริษัท: 3,056,678,601.50 − 4,144,812,053.53 = −1,088,133,452.03
   - business_rule ใหม่ (สำคัญ): **รายได้ใน fact_ebt ไม่เท่ากับรายได้ในรายงานรายได้ (revenue feed)** — เป็นรายได้ฐานยอดขาย
     ที่มีการปรับ เช่น นำยอดขายบัตร prepaid มารวม ไม่ได้คิดจาก usage อย่างเดียว → ห้ามรวม/เทียบตรงกับ revenue feed
     (ทำนองเดียวกับกฎ sales_is_not_revenue) และตอนตอบให้เรียกว่า "รายได้ (ฐานยอดขาย)" ไม่ใช่ "รายได้" เฉย ๆ
     - ระบุด้วยว่าถ้าผู้ใช้ถาม "รายได้" ทั่วไป (ไม่ได้พูดถึง EBT/กำไร) ควรใช้ revenue feed หรือไม่
     - ระบุด้วยว่ารายได้ฐานยอดขายนี้เทียบกับ sales feed (Sales DW) ได้หรือไม่ — AI จะไม่เดาเอง
   - description ของคอลัมน์ group_0/group_1/amount ให้สะท้อนความหมายข้างบน และบอกว่าแถว COMPUTED
     '3.1 กำไร (ขาดทุน) ของส่วนงาน (1)-(2)' ใช้/ห้ามใช้เมื่อไร (ตอนนี้ SUM ทั้งบริษัท ก.ค. 69 = 340.7 M ≠ −1,088 M)
   - แนะนำ: เพิ่ม dataset ยอดรวมรายงวด เช่น fact_ebt_total_monthly (time_key, รายได้ฐานยอดขาย, ค่าใช้จ่าย, ebt) เหมือน revenue มี
     fact_total_monthly แล้วประกาศ control_totals (source + grand_total) — AI จะสร้าง golden/เทียบยอดจากนี้ได้โดยไม่ต้องรู้สูตรเอง
     (ถ้าไม่ทำ: อย่างน้อย control_totals ต่อ group_0 ด้วย filter measure_type=ADDITIVE)

3) scope_columns (AI Phase 3) — ใส่ในทุก contract: map "scope key" ที่ portal ส่ง → ชื่อคอลัมน์ในโดเมนนั้น
     scope_columns:
       year_month: year_month     # expense/ebt: time_key
       org_code: <คอลัมน์หน่วยงานที่ใช้จำกัดสิทธิรายงาน>
   - AI บังคับที่ชั้น SQL: dataset ที่มีคอลัมน์ครบตาม key ที่ส่งมา = อ่านได้เฉพาะแถวใน scope; dataset ที่ไม่มีคอลัมน์นั้น = ใช้ไม่ได้เลยภายใต้ scope
     (เช่น revenue ด้วย org_code=cost_center: ใช้ได้แค่ fact_org_monthly + dim ที่มี cost_center; fact_bu_monthly/fact_org_product_* ไม่มี cost_center)
     → เลือกคอลัมน์หน่วยงานที่มีใน fact ที่รายงานจำกัดหน่วยงานใช้จริง (cost_center / unit_name / division_name ...) หรือเพิ่มคอลัมน์นั้นใน fact ที่ต้องใช้
   - dim ที่ไม่มีคอลัมน์ period (dim_bu, dim_product, ...) ตอนนี้ใช้ไม่ได้ภายใต้ scope year_month — ถ้าต้องการให้อ่านได้โดยไม่กรอง
     ให้บอกฝั่ง AI (เสนอ field ต่อ dataset `scope_exempt: true` — ฝั่ง AI ยังไม่ทำ)
   - key ที่ contract ไม่ประกาศ → AI ตอบ 400 (ไม่ตอบแบบไม่กรองเด็ดขาด)

4) portal (pocketbase_0/pb_hooks/assistant.pb.js) — เปลี่ยนจาก pinned_filters (AI แค่ log) เป็น `scope`
   - รายงานทั้งองค์กร: scope = {"year_month": <งวดของรายงาน>}
   - รายงานจำกัดหน่วยงาน: เพิ่ม {"org_code": <หน่วยงานที่ผู้ใช้มีสิทธิ>} (string หรือ list ≤ 1000 ค่า; ค่าเป็น int/string เท่านั้น)
   - response มี `data_as_of` {period, built_at, build_id} — แสดงให้ผู้ใช้เห็น และเตือนเมื่อ period ≠ งวดรายงาน
   - HTTP 400 จาก AI = scope ใช้กับ context นั้นไม่ได้ → แสดงข้อความ ห้าม retry แบบไม่ส่ง scope

5) รัน publish แบบ atomic (7d639b0) จริงครั้งแรก — ตรวจ 2026-09-18 แล้ว latest/ ยังเป็นโฟลเดอร์ธรรมดาและ manifest ยังไม่มี build_id
   - หลังรัน: dist/<domain>/latest เป็น symlink → builds/<id>, manifest มี build_id; ฝั่ง AI ไม่ต้องลงทะเบียนใหม่

แจ้งฝั่ง AI เมื่อเสร็จ: schema_version ใหม่ของแต่ละโดเมน, รูปแบบ field ที่เพิ่มจริง (filter / scope_columns / scope_exempt), และ build_id ที่ publish
```

## สถานะ 2026-09-19
NT-Report ทำครบข้อ 1–5 (`5abdca7`, `0c4b567`, `386c63a`, `ff4af5e`, publish atomic) — ฝั่ง AI ทำข้อ 1–4 ข้างล่างแล้ว: sales เปิด + eval 12/12, `scope_columns` จาก contract, ไม่มี `scope_exempt`.
**ค้าง — ebt (รอเจ้าของตัดสิน ก่อนส่งงานกลับ NT-Report):** `90fd787` (ebt 1.2.1) เปลี่ยน `fact_ebt_total_monthly` เป็นยอด**สะสม**ของ 2 สายงานขาย (ก.ค. 69 = +417.33 MB) ขัดกับ −1,088,133,452.03 (รายเดือนทั้งบริษัท) ที่กำหนดไว้ข้างบน.
ถ้ายืนยันนิยามใหม่ ต้องแก้ contract: measure ทั้ง 3 ของ `fact_ebt_total_monthly` เป็น `agg: point_in_time` (ตอนนี้ `sum` — SUM ข้ามงวดจะผิด) และ description/note ขึ้นต้นว่า "ยอดสะสมตั้งแต่ต้นปีถึงงวดนั้น เฉพาะ 2 สายงานขายหลัก" + กฎว่าถาม "กำไรเดือน X" / "ทั้งบริษัท" / "รายสายงาน" ต้องตอบจากอะไร — รายละเอียด `plan/archive/RESULT_P7_PHASE2.md`

## ฝั่ง AI เมื่อ NT-Report เสร็จ
1. `control_totals.filter` → gate (`check_control_totals`) + `gen_golden_from_controls` ใส่ WHERE ก่อน aggregate (~0.5 วัน, พร้อม test)
2. knowledge re-sync เอง (Phase 2) — ตรวจว่า rule ใหม่อยู่ใน instruction ของ context แล้วเปิด `feed_sales` / `feed_ebt` (`is_active=1`)
3. `gen_golden_from_controls --domain sales|ebt` → eval ≥ 90% → ปิด REMAIN-11 และ Phase 2 exit
4. `scope_columns` จาก contract ทับค่า period ที่ตั้งมือใน config (`feed_revenue`/`feed_expense`) อัตโนมัติ — ถ้ามี `scope_exempt` ต้องเพิ่ม support
