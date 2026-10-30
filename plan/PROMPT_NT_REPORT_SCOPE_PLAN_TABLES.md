# Prompt สำหรับฝั่ง NT-Report — ประกาศ `scope_plan_tables` ใน contract sales / revenue

> ส่งให้ Claude Code ที่ทำงานใน repo `NT-Report` (คัดลอกทั้งไฟล์) — เขียน 2026-10-30 ตอบกลับ prompt "ตารางเป้าต้องเห็นครบทั้งปีภายใต้ scope ของ portal"

---

## ที่มา

portal (งวด 2026-09, context `feed_sales`) ถาม "เป้ายอดขาย ม.ค.-ธ.ค. ปี 2569 กลุ่มธุรกิจ ICT Solution เป็นเท่าไหร่" ได้ **2,169.67 ล้านบาท**
(เป้า ม.ค.–ก.ย.) และเรียกว่า "ทั้งปี" — ค่าที่ถูกคือ **2,892.88 ล้านบาท**. สาเหตุ: scope `year_month = [202501 … 202609]` ของ portal
กรองทุกตารางรายเดือน รวมตารางเป้าที่มีครบ 12 เดือนของปีแผน.

ฝั่ง AI แก้แล้ว (AI repo, `app/services/data_sources.py` — `scope_filters` / `plan_note`): ตารางที่ contract ประกาศใน
`scope_plan_tables` ถูกกรอง `year_month` **ระดับปี** (ทุกปีที่อยู่ใน scope) แทนรายเดือน; ตารางผสม actual+target ประกาศ `where`
→ เฉพาะแถวที่ตรงเห็นทั้งปี แถวอื่นยังกรองรายเดือน. ยอดจริงไม่เกินงวดรายงานเหมือนเดิม, ปีนอก scope (เป้าปีหน้า) มองไม่เห็น,
`org_code` กรองเหมือนเดิม (ตารางเป้าที่ไม่มี `cost_center` ยังถูกตัดเมื่อรายงานจำกัดหน่วยงาน). ไม่ประกาศ = พฤติกรรมเดิมทุกอย่าง.
วัดบนสำเนาด้วย contract ที่เติม key นี้แล้ว: ทั้ง `feed_sales` และ `feed_revenue` ได้ 2,892.88; ชุด `portal_questions_{revenue,sales}.json`
ไม่ถอย (revenue 9→10/10, sales 10→9/10 ข้อที่ตกคือ P03 ยอดจริง — SQL/ข้อมูลเหมือนเดิมทุกตัวอักษร คำอธิบายปัดเป็น "ประมาณ 1,439");
`revenue_vs_target` / `sales_vs_target` ได้ผลเท่าเดิม (compiler กรองงวดเอง).

**ไม่ต้องแก้ portal** (`pocketbase_0/pb_hooks/assistant.pb.js` → `scopeMonths` ส่ง scope รูปเดิม — ห้ามแก้).

## ⚠️ ลำดับ — ห้ามวาง contract ใน working tree ของ `main` ก่อนฝั่ง AI ยืนยัน

server จริงของ AI อ่าน `DataFeed/contracts/*.yaml` **จาก working tree ของ NT-Report โดยตรง** และ re-sync ความรู้เองเมื่อไฟล์เปลี่ยน.
ฝั่ง AI ต้อง migrate config DB (`scripts/migrate_data_sources.py` เพิ่มคอลัมน์ `schema_contexts.scope_plan_tables`) **ก่อน** —
ถ้า contract ใหม่ถึงก่อน AI จะ sync สำเร็จโดยไม่มี key นี้ (log warning) และบันทึกว่า sync แล้ว: จะไม่ sync ซ้ำจนกว่า contract จะเปลี่ยนอีกครั้ง.
→ ทำงานบน branch/worktree, commit ได้, แต่ **merge / วางไฟล์ลง `main`** หลังเจ้าของบอกว่าฝั่ง AI migrate แล้วเท่านั้น.

## สิ่งที่ต้องทำ

contract เป็น **AUTO-GENERATED** จาก `tools/feed/domains.py` ผ่าน `tools/feed/gen_contract.py` — ห้ามแก้ YAML ด้วยมือ.

### 1. `tools/feed/domains.py` — key ใหม่ในสเปกของโดเมน

ชื่อ dataset ตามชื่อใน contract (ไม่มี prefix `feed_<domain>_`):

```python
# sales
"scope_plan_tables": {
    "fact_sales_target_monthly": {},                 # ทั้งตารางเป็นเป้า (ครบ 12 เดือนของปีแผน)
},
# revenue
"scope_plan_tables": {
    "fact_bu_target_monthly": {},
    "fact_service_group_target_monthly": {},
    "fact_bu_vs_target_monthly": {"where": "metric = 'target'"},              # ตารางผสม actual + target
    "fact_service_group_vs_target_monthly": {"where": "metric = 'target'"},
},
```

ห้ามใส่ `fact_sales` — `metric='target'` ในนั้นมีถึงงวดล่าสุดเท่านั้น (กฎ `sales_full_year_target`) และ `sales_vs_target` อ่านจากตารางนี้.

ผลใน contract ที่ฝั่ง AI ทดสอบแล้ว (ต่อท้ายหลัง `scope_columns` หรือที่ใดก็ได้ระดับบนสุด):

```yaml
# sales.yaml
scope_plan_tables:
  fact_sales_target_monthly: {}
```
```yaml
# revenue.yaml
scope_plan_tables:
  fact_bu_target_monthly: {}
  fact_service_group_target_monthly: {}
  fact_bu_vs_target_monthly:
    where: metric = 'target'
  fact_service_group_vs_target_monthly:
    where: metric = 'target'
```

กติกาที่ผู้อ่าน (AI) ตรวจตอน sync — entry ที่ผิดถูกข้าม (log) และตารางนั้นกรองรายเดือนเหมือนเดิม:
- ต้องเป็น dataset ของ contract นี้ และมีคอลัมน์ของ `scope_columns.year_month`
- ค่าเป็น `{}` หรือ `{where: <predicate>}` เท่านั้น
- `where` = นิพจน์ BOOLEAN เดียวบนคอลัมน์ของ dataset นั้น (DuckDB ผูกกับ dtype ใน contract) — ห้ามมี `;`, comment, subquery,
  วงเล็บหรือเครื่องหมายคำพูดที่ไม่ปิด

### 2. `tools/feed/gen_contract.py` — ส่ง key ต่อลง contract

แบบเดียวกับ `org_levels` / `metrics`: `if spec.get("scope_plan_tables"): contract["scope_plan_tables"] = spec["scope_plan_tables"]`
(วางต่อจาก `scope_columns`).

### 3. `tools/feed/feed.py` — SCHEMA.md

ใต้หัวข้อ "## Scope columns" เติมรายการตารางแผน เช่น
"- ตารางเป้า/แผน (`scope_plan_tables`): `year_month` กรองระดับปี — `fact_sales_target_monthly` (ทั้งตาราง), `fact_bu_vs_target_monthly` (เฉพาะแถว `metric = 'target'`)"

### 4. Test (ใน `tools/feed/`)

- `test_scope_columns.py` (หรือไฟล์ใหม่): ทุก dataset ใน `scope_plan_tables` มีอยู่ในโดเมนนั้น, มีคอลัมน์ `year_month` ของ scope,
  `where` อ้างเฉพาะคอลัมน์ที่มี, ไม่มี `fact_sales` และไม่มีตารางยอดจริงล้วน
- ข้อมูลจริง: ตารางทั้งตารางเป็นเป้ามีครบ 12 เดือนของทุกปีแผน; ตารางผสม — แถว `metric = 'target'` ครบ 12 เดือน, แถว `actual` ไม่เกินงวดของ build
  (นี่คือสมมติฐานที่ทำให้ "เห็นทั้งปี" ไม่รั่วยอดจริง — ต้องคงจริงทุก build)

### 5. Version + เอกสาร

- **MINOR** ทั้งสองโดเมน (key ใหม่ที่ผู้อ่านเก่าข้ามได้ — แบบเดียวกับ `org_levels`): sales 1.4.1 → **1.5.0**, revenue 2.6.0 → **2.7.0**
- `DataFeed/CHANGELOG.md`: รายการ 2026-10-30 ต่อโดเมน — อาการ (2,169.67 vs 2,892.88), key ใหม่, ไม่มีคอลัมน์/ข้อมูลเปลี่ยน
- `DataFeed/SPEC.md`: หัวข้อใหม่ใต้ §5 (เช่น §5.4c `scope_plan_tables`) — ความหมาย, รูปแบบ, กติกา `where`, หลัก "ยอดจริงไม่เกินงวด / ปีนอก scope มองไม่เห็น"
- `pocketbase_0/docs/ASSISTANT.md`: บรรทัดเดียวว่า scope เดิมของ portal เห็นเป้าครบทั้งปีของปีใน scope ได้แล้ว (portal ไม่ต้องแก้)
- schema/ข้อมูลไม่เปลี่ยน → ถ้ากติกาของ repo ไม่บังคับ rebuild dist สำหรับ key ใหม่ใน contract ก็ไม่ต้อง rebuild (ผู้อ่าน re-sync จาก contract เอง);
  ถ้า `gen_contract` ให้ค่าอื่นต่างจาก build ที่ publish อยู่ (เช่น `row_count_built` เพราะ raw เปลี่ยน) ให้ทำตามขั้นตอนปกติของ repo และรายงาน

### 6. ชุดคำถาม eval (`tools/feed/portal_questions.py`)

เพิ่มข้อละหนึ่งใน sales และ revenue ให้การแก้นี้ถูกวัดทุก build:
- sales: "เป้ายอดขาย ม.ค.-ธ.ค. ปี {พ.ศ.} กลุ่มธุรกิจ ICT Solution เป็นเท่าไหร่" — เฉลย `SUM(target_amt)` จาก `fact_sales_target_monthly`
  ทั้ง 12 เดือนของปีแผน กรอง business_group ICT Solution (build 20261022T031551Z = **2,892.88**)
- revenue: "เป้ารายได้ ม.ค.-ธ.ค. ปี {พ.ศ.} กลุ่มธุรกิจ ICT Solution เป็นเท่าไหร่" — `SUM(revenue_target)` จาก `fact_bu_target_monthly` ทั้งปี (**2,892.88**)
- `base_words` ควรมี "ทั้งปี" / "ม.ค.–ธ.ค." และ test ใน `test_portal_questions.py` ตามแบบข้ออื่น

## ห้าม

- แก้ portal hook / รูป scope ที่ portal ส่ง
- ประกาศตารางที่มียอดจริงโดยไม่มี `where` ที่ตัดยอดจริงออก
- เดาตารางจากชื่อ — ประกาศทีละตารางเท่านั้น; ebt / expense: ถ้ามีตารางแผน/งบประมาณรายปี **รายงานกลับ** อย่าเพิ่มเอง

## ส่งกลับ

diff สรุป, ผล test, version ใหม่ของทั้งสอง contract, YAML ส่วน `scope_plan_tables` ที่ gen ออกมาจริง, และต้อง rebuild dist หรือไม่
