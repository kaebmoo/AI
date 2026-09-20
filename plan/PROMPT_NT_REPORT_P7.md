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

## งานถัดไปของ NT-Report — ebt PATCH (2026-09-19 บ่าย, หลัง 1.3.0)
```
ebt 1.3.0 (bebc797) ฝั่ง AI eval ได้ 18/24: โมเดล SUM คอลัมน์สะสมข้ามงวด 4 ข้อ (SUM(ebt) WHERE time_key BETWEEN 202501 AND 202505)
และใช้คอลัมน์สะสมตอบคำถามรายเดือน 2 ข้อ (SELECT ebt … ถาม "ของเดือน") — แก้ที่ domains.py → contract, bump PATCH:
1) control_totals.measures: sales_base_revenue / expense / ebt → agg: point_in_time (ตอนนี้ sum); *_month คง sum
2) business_rule ใหม่สำหรับ fact_ebt_total_monthly (แบบ ytd_point_in_time ของ revenue): คอลัมน์ sales_base_revenue / expense / ebt
   เป็นยอดสะสม ณ งวด — เลือกแถว time_key = งวดที่ถามแถวเดียว ห้าม SUM หรือ BETWEEN ข้ามงวด (สะสมถึง พ.ค. 2568 = WHERE time_key = 202505);
   ยอดรายเดือนใช้ *_month (SUM ข้ามงวดได้)
3) description ของ 3 คอลัมน์สะสมขึ้นต้นว่า "ยอดสะสมตั้งแต่ต้นปี (YTD) — ไม่ใช่ยอดของเดือน; รายเดือนใช้ <col>_month"
4) กฎว่า EBT/รายได้/ค่าใช้จ่าย "รายสายงาน" หรือ "รายศูนย์ต้นทุน" คำนวณจาก fact_ebt อย่างไร (SUBTOTAL ต่อ division? หัก 08.รายได้อื่น และ ER/MSP ด้วยไหม?)
   — ตอนนี้ AI ไม่มีกฎนี้ จึงยังไม่ควรตอบ
ฝั่ง AI re-sync เอง ไม่ต้องลงทะเบียนใหม่ (คอลัมน์ไม่เปลี่ยน)
```

## ฝั่ง AI เมื่อ NT-Report เสร็จ
1. `control_totals.filter` → gate (`check_control_totals`) + `gen_golden_from_controls` ใส่ WHERE ก่อน aggregate (~0.5 วัน, พร้อม test)
2. knowledge re-sync เอง (Phase 2) — ตรวจว่า rule ใหม่อยู่ใน instruction ของ context แล้วเปิด `feed_sales` / `feed_ebt` (`is_active=1`)
3. `gen_golden_from_controls --domain sales|ebt` → eval ≥ 90% → ปิด REMAIN-11 และ Phase 2 exit
4. `scope_columns` จาก contract ทับค่า period ที่ตั้งมือใน config (`feed_revenue`/`feed_expense`) อัตโนมัติ — ถ้ามี `scope_exempt` ต้องเพิ่ม support

## สถานะ 2026-09-19 (ค่ำ)
ebt 1.3.1 (`73ddc96`) ทำครบ 4 ข้อของ "ebt PATCH" → ฝั่ง AI เปิด `feed_ebt` แล้ว eval 22/24 — **ไม่มีงานค้างที่บล็อก**. ข้อเสนอ (ไม่บังคับ):
- control totals ราย `division` ของ ebt (เช่น dataset ยอดรายสายงานต่องวด + `bg_key: division`) → ฝั่ง AI จะสร้าง golden รายสายงานและวัดสูตรหัก `08.รายได้อื่น`/ER ได้ (ตอนนี้โมเดลลืมหัก 1 ใน 2 รอบ และไม่มีอะไรวัด)
- description ของ `expense` ให้ขึ้นต้นด้วย "สะสม (YTD)" ชัดกว่านี้ หรือกฎว่า "ค่าใช้จ่ายของเดือน = `expense_month`" ตรง ๆ — โมเดลยังหยิบ `expense` ตอบคำถามรายเดือนเป็นครั้งคราว

## งานถัดไปของ NT-Report — หลัง AI Plan 7 Phase 4 (2026-09-19) — เอกสาร + hook เล็กน้อย, ไม่มีงาน DataFeed
```
ทำงานใน repo NT-Report (commit เป็นก้อนต่อข้อ, ยังไม่ push). ฝั่ง AI เสร็จ Plan 7 Phase 4 แล้ว:
API key ผูก "workspace" ได้ — config จริงของ AI มี workspace `nt-report` = context feed_revenue, feed_expense,
feed_sales, feed_ebt. key ที่ผูก workspace: เรียก context นอก workspace ได้ HTTP 403, ใช้ได้เฉพาะ /api/v1/query*,
ไม่ส่ง context = AI เลือกภายใน workspace ให้. รายละเอียด: AI/docs/PORTAL_INTEGRATION.md, AI/docs/manuals/manual_api_keys.md

1) pocketbase_0/docs/ASSISTANT.md
   - ขั้น "ออก API key ให้ portal": เปลี่ยนเป็น key ที่ผูก workspace `nt-report`
     (POST /api/v1/admin/api-keys {"name":"nt-report-portal","workspace":"nt-report","rate_limit_per_minute":20,"rate_limit_per_day":2000}
      หรือ snippet ใน AI/docs/PORTAL_INTEGRATION.md) — raw key แสดงครั้งเดียว
   - ASSISTANT_CONTEXT_MAP ต้องชี้ไป context ใน workspace เท่านั้น (feed_revenue / feed_expense / feed_sales / feed_ebt);
     ชี้ไป context อื่น (revenue, expense, ...) = AI ตอบ 403 ทุกคำถาม
   - ตาราง error: เพิ่มแถว AI ตอบ 403 (context นอกสิทธิ์ของ key = config ผิด ไม่ใช่ปัญหาชั่วคราว)
   - สถานะ AI: 4 โดเมนพร้อม (eval 2026-09-19: revenue 14/14, expense 12/12, sales 12/12, ebt 35/36);
     contract เพิ่มตาราง/คอลัมน์ → ฝั่ง AI ลงทะเบียนซ้ำได้ทาง POST /api/v1/admin/sources/register {"domain": "<d>"} (หรือ CLI เดิม)
2) pocketbase_0/pb_hooks/assistant.pb.js — upstream 403 ตอนนี้ตกไป branch "status ไม่ใช่ 2xx" → 502 "ลองใหม่ภายหลัง"
   ซึ่งชวนให้ผู้ใช้ลองซ้ำทั้งที่เป็น config ผิด: แยก 403 → audit status `upstream_forbidden_context`, ตอบผู้ใช้ 502/503
   ด้วยข้อความ "รายงานนี้ยังไม่เปิดให้ถามตอบ" (ไม่บอกรายละเอียด upstream), ห้าม retry ด้วย context อื่นหรือไม่ส่ง context
   + เพิ่ม case ใน scripts/test_assistant_hook.js
3) DataFeed/README.md ส่วนที่พูดถึง register_file_source: เพิ่มว่าทำผ่าน admin API ของ AI ได้แล้ว (ข้อ 1)
ไม่ต้องแก้ contract / build ใหม่
```

## ข้อเสนอจาก AI Plan 7 Phase 5 — ถามข้ามหลาย context (2026-09-19) — ไม่บล็อก
ที่มา/ตัวเลข: `plan/archive/RESULT_P7_PHASE5.md` (ฝั่ง AI ไม่คำนวณตัวเลขทางการเองและไม่ JOIN ข้ามโดเมน — สิ่งที่ขาดต้องมาจากต้นทาง)

1. **ebt — คำถามระดับ "ทั้งบริษัท" ถูกตอบด้วยยอดของ 2 สายงานขาย** (PATCH ของ contract, ไม่แตะข้อมูล): ถาม "กำไรของทั้งบริษัทเดือนกรกฎาคม 2569" →
   `SUM(ebt_month)` ของ `fact_ebt_division_monthly` = −284.05 M แล้วอธิบายว่า "กำไรสุทธิรวมของบริษัท" — contract มีกฎขอบเขต (`ebt_report_scope_and_exclusions`,
   `computed_segment_profit_not_company_ebt`) แต่ไม่มีกฎที่บอกว่า**ถูกถามถึงทั้งบริษัท / หน่วยงานนอก 2 สายงานขายแล้วต้องทำอย่างไร** → ขอ business_rule ใหม่ เช่น
   `ebt_not_company_wide`: "ชุดข้อมูลนี้ครอบคลุมเฉพาะ 2 สายงานขาย — คำถามถึงกำไร/EBT ของทั้งบริษัทหรือสายงานอื่น ไม่มีข้อมูลในชุดนี้: ห้ามตอบด้วยยอดของ 2 สายงานขาย; ถ้าตอบ ต้องตั้งชื่อคอลัมน์ผลลัพธ์และคำอธิบายว่า 'เฉพาะ 2 สายงานขาย'"
   และขึ้นต้น description ของ `ebt` / `ebt_month` / ตาราง total ว่า "เฉพาะ 2 สายงานขาย"
2. **(ตัวเลือก) dataset ผลดำเนินงานทั้งบริษัท / ทุกสายงาน** — ถ้า portal ต้องตอบ "กำไรทั้งบริษัท": ตอนนี้ไม่มีใน DataFeed (รายได้ − ค่าใช้จ่าย จาก revenue + expense feed = −870.15 M ก.ค. 69 ไม่ใช่ตัวเลขทางการของอะไร) — ฝั่ง AI จะแสดงเป็น "ส่วนต่าง (ไม่ใช่กำไร / EBT ทางการ)" เท่านั้น
3. **ชื่อสายงานไม่ตรงกันข้ามโดเมน:** revenue `division_name` = `กรรมการผู้จัดการใหญ่` แต่ expense / ebt `division` = `กรรมการผู้จัดการใหญ่ บมจ.เอ็นที` (+ revenue มี `ไม่ระบุ`) — คำถาม "รายได้และค่าใช้จ่ายของสายงาน X" ถูกแตกเป็นสองคำถามที่กรองด้วยชื่อเดียวกัน → ขอชื่อชุดเดียว หรือรหัสสายงานร่วมในทุกโดเมน
4. **sales ไม่มีสายงาน** (มี `sales_line / sales_group / sales_dept`) — เทียบกับ revenue / expense ของหน่วยงานเดียวกันได้เฉพาะผ่าน `cost_center`; ถ้า OrgReport เทียบรายสายงานอยู่แล้ว ขอ mapping เดียวกันใน feed (`dim_org` ของ sales มี `division` ไหม)
5. **ebt `group_1` = `03.Mobile`** ขณะที่ revenue `bu` / sales `business_group` = `3.Mobile` — ถ้าจะให้ถามรายกลุ่มธุรกิจข้าม ebt ↔ revenue/sales ได้ ขอคอลัมน์รหัสกลุ่มธุรกิจแบบเดียวกัน (เช่น `bu_seq`)
6. `description` ของ context (`contract.description`: "NT Revenue Data Feed" ฯลฯ) ถูกใช้เป็นคำอธิบายให้ตัวแตกคำถามเลือก context — ประโยคภาษาไทยสั้น ๆ ว่าชุดนี้ตอบอะไร/ไม่ตอบอะไร (เช่น ebt: "EBT ของ 2 สายงานขาย — ไม่ใช่ทั้งบริษัท") จะช่วยให้แตกถูกขึ้น

## งานเปิดใช้จริง (go-live) — 2026-09-20
prompt แยกสำหรับ session ใน repo NT-Report: `plan/PROMPT_NT_REPORT_GOLIVE.md` (contract ebt PATCH "ไม่ใช่ทั้งบริษัท" + description ภาษาไทยของทุก contract, hook: error 200 ที่ไม่มี `data_as_of` / คำเตือนงวด / status 401·403·429 / ไม่ส่งข้อความดิบถึง browser, เอกสาร + context map, E2E + ตัวเลขอ้างอิงจาก dashboard) — คู่กับ `plan/PROMPT_P7_GOLIVE_NT_REPORT.md` ฝั่ง AI

## สิ่งที่ response ของ `/api/v1/query` เปลี่ยนไป (hardening 2026-09-20) — ฝั่ง NT-Report ต้องรู้
ที่มา: `plan/archive/RESULT_P7_HARDENING.md` · ตารางเต็ม: `docs/PORTAL_INTEGRATION.md` §"สิ่งที่ response บอก และไม่บอก"

**contract ของ field ไม่เปลี่ยน** (`answer`, `context`, `sql`, `data`, `row_count`, `execution_time_ms`, `error`,
`data_as_of`, `parts`, `computed` ครบเหมือนเดิม) — ที่เปลี่ยนคือ *เนื้อ* ของ `error` / ข้อความ และ status บางตัว:

1. **`error` เป็นรหัสคงที่แล้ว** ไม่ใช่ข้อความ exception: `query_failed` · `source_unavailable` · `duplicate_request` ·
   `internal_error` (คำถามข้าม context: `parts[].error` เป็นรหัสเดียวกัน, `parts[].answer` เป็นข้อความตายตัวของรหัสนั้น)
   → hook branch ด้วยรหัสได้ตรง ๆ ไม่ต้อง match ข้อความ
2. **`answer` ไม่มี SQL อีกแล้ว** เมื่อได้ 0 แถว (เดิมมี SQL เต็มแม้ส่ง `include_sql: false`) — ได้ `ไม่พบข้อมูลที่ตรงกับเงื่อนไข`;
   SQL ยังอยู่ใน field `sql` ตามที่ hook ขอ (`include_sql: true`) เหมือนเดิม
3. **เกินโควตา / rate limit = `429`** (เดิม **401**) — hook ปัจจุบันตกเข้าสาขา "non-2xx → 502" ซึ่งยังถูกต้อง
   แต่ควรแยกข้อความให้ผู้ใช้รู้ว่า "วันนี้ถามเยอะเกินโควตา ลองใหม่ภายหลัง" ไม่ใช่ "ระบบขัดข้อง"
4. **`503` ตัวใหม่:** ระบบบันทึกการใช้งาน (audit) เขียนไม่ได้ → ไม่ส่งคำตอบออก. เป็น "ลองใหม่ภายหลัง" เช่นกัน
5. **400 / 403 คืนข้อความตายตัว** (เดิมเป็นข้อความ exception ที่บอกชื่อคอลัมน์ scope ที่รองรับ / ชื่อ data source /
   path ของ script) — status เดิมทุกตัว, hook ที่แยก 400 ออกมาทำงานเหมือนเดิม.
   **context นอกสิทธิ์ กับ context ที่ไม่มีอยู่ ได้ข้อความ 403 เดียวกัน** — ถ้า `ASSISTANT_CONTEXT_MAP` ตั้งผิด
   จะไม่มีทางแยกจากข้อความ response ได้อีก ให้ดูที่ log ของ AI หรือ `GET /admin/query-audit`
6. **`GET /api/v1/query/contexts` ต้องส่ง `X-API-Key` หรือ session token แล้ว** — ไม่มี = 401 (เดิมเป็น public).
   hook ปัจจุบันไม่เรียก endpoint นี้ จึงไม่กระทบ; script/เอกสารฝั่ง NT-Report ที่เรียกอยู่ต้องเพิ่ม header

**ไม่มีอะไรที่ portal ต้องรีบแก้เพื่อไม่ให้พัง** — ข้อ 3, 4, 5 เป็นการทำให้ข้อความถึงผู้ใช้ดีขึ้นเท่านั้น
