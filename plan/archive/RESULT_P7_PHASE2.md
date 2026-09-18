# RESULT Plan 7 Phase 2 — Contract-driven knowledge + freshness

**วันที่:** 2026-09-18 | **Branch:** `main` (ยังไม่ push) | **Provider:** admin default (matcha, gpt-4.1)
**Interpreter:** `venv/bin/python3.14` | **แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 2

## สรุป

| Exit criterion | ผล | ผ่าน? |
|---|---|---|
| 4 โดเมนตอบได้ | ลงทะเบียนครบ 4 (revenue, expense, sales, ebt) ผ่าน gate ทุกข้อ และตอบผ่าน QueryEngine ได้ทั้ง 4 — **แต่ sales/ebt ตอบเลขผิดความหมาย** เพราะ contract ไม่บอกกฎที่จำเป็น (ดู "ข้อขัดกับแผน") → ปิด `feed_sales`/`feed_ebt` ไว้ (`is_active=0`) รอตัดสิน | ⚠️ 2/4 |
| eval แต่ละโดเมน value match ≥ 90% เทียบ control_totals | revenue **14/14**, expense **12/12** — sales: control_totals รวม actual+target (เทียบไม่ได้ความหมาย), ebt: contract ไม่มี control_totals | ⚠️ 2/4 |
| publish รอบใหม่แล้ว AI เห็นเองโดยไม่ต้องรันอะไร | ✅ พิสูจน์บนสำเนาข้อมูลจริง (layout `builds/<id>` + symlink แบบ NT-Report `7d639b0`) — คำถามถัดไปได้ build ใหม่ + `data_as_of` ใหม่ทันที; NT-Report ยังไม่ได้ publish แบบ atomic จริง | ✅ (บนสำเนา) |
| pytest ไม่มี test เดิมพัง | 714 → **740 passed**, 3 skipped (+26; test เดิมแก้ 1 จุด: mock ของ `/query` เพิ่ม `data_as_of = None`) | ✅ |

→ **Phase 2 ยังไม่ผ่าน exit ครบ** — ที่ขาดเป็นเรื่องความหมายใน contract ของ NT-Report (sales, ebt) ไม่ใช่ code ฝั่ง AI (ดูทางเลือกท้ายไฟล์)

## ข้อ 1 — NT-Report publish แบบ atomic แล้วหรือยัง

ตรวจ 2026-09-18: **ยัง** — `dist/<domain>/latest` ทั้ง 4 โดเมนเป็นโฟลเดอร์ธรรมดา (ไม่ใช่ symlink), ไม่มี `builds/`, manifest ไม่มี `build_id`
(code publish แบบ atomic อยู่ใน NT-Report `7d639b0` แล้ว แต่ยังไม่ได้รัน) → บันทึกเป็นงานค้าง; ฝั่ง AI ไม่ต้องลงทะเบียนใหม่เมื่อ publish จริง
(resolver ตาม realpath ของ `latest` — พิสูจน์แล้วใน demo ด้านล่าง)

## สิ่งที่ทำ

### 2a. `data_as_of` ใน `/api/v1/query` (`deb0a7e`)
- `ResolvedSource.data_as_of` = `{period, built_at, build_id}` จาก manifest ของ build ที่ adapter ตรวจแล้ว; legacy / ไม่มี manifest = `null`
- เก็บลง `QueryEngineResult` ตอน resolve source → เป็น build เดียวกับที่ SQL อ่าน; คำตอบจาก cache ก็ถือ build เดิม (cache ผูก build อยู่แล้ว)
- ค่า live: `feed_revenue` → `{"period": 202608, "built_at": "2026-09-11T01:37:35+00:00", "build_id": null}`; `revenue`/`expense` → `null`
- `docs/PORTAL_INTEGRATION.md` อธิบาย field + วิธีใช้ฝั่ง portal

### 2b. knowledge จาก contract เป็น service + re-sync อัตโนมัติ (`38ab63d`)
- logic ของ `gen_docs_from_contract` ย้ายไป `app/services/datafeed_knowledge.py` (script เหลือเป็น wrapper) —
  output ของ revenue **เหมือนเดิมทุก byte** (dump 393 บรรทัดของ context/metadata/docs เทียบกับ script เดิม)
- `register_file_source` เขียน registry + knowledge + ตำแหน่ง contract ใน **transaction เดียว** (ไม่ต้องรัน gen_docs ก่อนแล้ว)
- `data_sources` เพิ่ม `contract_file`, `knowledge_sha` (= sha ของ contract + schema_version ของ build) — migration idempotent
- ต่อ request: resolver `stat` ไฟล์ contract (0.5 ms); ถ้า contract หรือ schema_version ของ build เปลี่ยน →
  re-sync ครั้งเดียวข้ามทุก process (compare-and-set บน `knowledge_sha`) + `mark_brain_dirty()` + ล้าง query cache ของ process;
  re-sync ล้ม = คง knowledge เดิม ไม่ทำให้ request ล้ม
- พิสูจน์บน config จริง (สำเนา): แก้ contract เพิ่มกฎ → request ถัดไป instruction มีกฎใหม่ + doc ใหม่ใน `vanna_documentation` (request นั้นช้าขึ้น ~0.8 s ครั้งเดียว)
- เปลี่ยนพฤติกรรม: **keywords/priority ตั้งเฉพาะตอนสร้าง context** (เดิม gen_docs เขียนทับทุกครั้ง) → admin แก้ routing แล้ว re-sync ไม่ทับ
- `main_view` ใช้ `control_totals.source` ถ้ามี ไม่งั้น `primary_dataset` (ebt ไม่มี control_totals)

### 2c. ลงทะเบียน expense / sales / ebt (`a2b8568`)
- **bug จริง — CSV sniffer ของ DuckDB:** sniffer ดูแค่ ~20k แถวแรก → `fact_sales.csv` (field มี quote ครั้งแรกที่บรรทัด ~43,026)
  ถูกอ่านเป็น `quote=''` แล้วพังที่ `"บริการเครื่องและอุปกรณ์ 2G,3G,4G"` → pin dialect (`delim=','`, `quote='"'`, `escape='"'`) —
  view ของ revenue ทั้ง 15 ตัว**เหมือนเดิมทุกแถว** (md5 ของทุกแถวก่อน/หลัง), test จำลองกรณีนี้ fail บน code เดิม
- contract dtype `Int64` / `boolean` → `BIGINT` / `BOOLEAN` (register เดิมรู้จักแค่ integer/double/string)
- gate control totals อ่านจาก contract: tolerance ที่ระดับ spec, `__ALL__` = รวม source เมื่อไม่มี grand_total (expense/sales), ข้ามเมื่อ contract ไม่มี control_totals (ebt);
  GROUP BY ครั้งเดียวต่อ measure แทน scan ทีละแถว → ลงทะเบียน revenue 4.8 s → **2.4 s** (expense ไม่งั้นต้อง scan CSV 147 MB × 380 รอบ)
- `gen_golden_from_controls` อ่านตาราง/คีย์/measure จาก `control_totals` (agg `sum` → คำถามรายเดือน, `point_in_time` → YTD);
  revenue **เหมือนเดิมทุก byte**; ใช้ชื่อกลุ่ม `*_name` ในคำถามเมื่อมี (expense_group_name) — golden ของ revenue ใน config **ไม่ได้ regen** (ชุด F10 14 ข้อ)
- router: keyword/priority default ต่อโดเมน — feed context ชนะเฉพาะเมื่อคำถามมี marker (`feed`/`datafeed`/`dashboard`/`แดชบอร์ด`)

| ลงทะเบียน (live `config.db`) | schema | period | gate | knowledge | เวลา |
|---|---|---|---|---|---|
| revenue (ลงใหม่เพื่อบันทึก contract) | 2.0.0 (contract 2.0.1) | 202608 | 16 ไฟล์, 15 views, controls 576 แถว | 159 metadata, 22 docs — **ไม่เปลี่ยน** | 2.4 s |
| expense | 1.1.0 | 202608 | 9 ไฟล์, 8 views, controls 380 แถว | 85 metadata, 13 docs | 1.7 s |
| sales | 1.0.0 | 202607 | 4 ไฟล์, 3 views, controls 172 แถว | 39 metadata, 9 docs | 1.3 s |
| ebt | 1.0.0 (contract 1.0.1) | 202607 | 1 ไฟล์, 1 view, **ไม่มี control totals** | 23 metadata, 6 docs | 1.0 s |

**Router — ตรวจแบบ deterministic** (router จริง, config ก่อน Phase 2 vs หลัง):
golden 63 ข้อ route **เหมือนเดิมทุกข้อ**; คำถามมี marker 13 แบบไปโดเมนถูกทั้งหมด (เช่น "ค่าใช้จ่าย feed เดือนล่าสุด" → `feed_expense`, "ยอดขาย feed" → `feed_sales`,
"EBT feed" → `feed_ebt`, "ข้อมูล feed ล่าสุด" → `feed_revenue`) — ก่อนแก้ `feed_revenue` แพ้ legacy ทุกข้อ (เสมอกันที่ priority) และคำถาม marker ล้วนไป `feed_expense`
→ อัปเดต keywords/priority ของ `feed_revenue` ใน config จริงเป็นค่า default ใหม่ (ครั้งเดียว — เทียบเท่า admin แก้) และมี test คุม 11 กรณี

## Eval (`python -m scripts.eval.run_eval --context …`)

| Context | ไฟล์ผล (`eval_results/`) | golden | value_match | P50 | P95 |
|---|---|---|---|---|---|
| feed_expense | `eval_20260918_2243` | 12 (ใหม่ จาก control_totals) | **12/12** | 7.07 s | 11.47 s |
| feed_revenue (regression) | `eval_20260918_2245` | 14 (ชุด F10) | **14/14** | 6.68 s | 8.41 s |
| feed_revenue Phase 1 (อ้างอิง) | `eval_20260918_2127` | 14 | 14/14 | 6.67 s | 10.37 s |

strict exact_match = 0 ทุกรอบ (alias ภาษาไทยไม่ตรง golden — เหมือน F10/Phase 1)

## Publish รอบใหม่ → AI เห็นเอง (สำเนาข้อมูลจริง, config สำเนา)

`builds/202608-A` (hard link ไฟล์ revenue จริง) → symlink `latest` → ลงทะเบียนครั้งเดียว → แล้ว "publish" `builds/202609-B` (เพิ่มงวด 202609) + สลับ symlink แบบ atomic:
```
before publish: data_as_of={'period': 202608, 'build_id': '202608-A', ...} answer=[{'latest': 202608}]
after publish : data_as_of={'period': 202609, 'build_id': '202609-B', ...} answer=[{'latest': 202609}]
```
ฝั่ง AI ไม่ได้รันอะไรเลยระหว่างสองบรรทัด (resolver เห็น realpath ใหม่ → ตรวจ manifest ของ build ใหม่ → adapter ใหม่; cache ของ build เดิมเป็น miss)

## ⚠️ ข้อขัดกับแผน — sales / ebt (รอตัดสิน)

ถามผ่าน QueryEngine เต็มเส้นทาง (ก.ค. 2569):

| คำถาม | SQL ที่โมเดลเขียน | ได้ | ที่ถูกตามกฎใน contract |
|---|---|---|---|
| ยอดขายรวมทั้งบริษัท | `SUM(amount) WHERE year_month = 202607` | 6,978,071,395.50 | actual อย่างเดียว 3,289,655,675.33 (และ KPI ใช้ BG 1–7 เท่านั้น) |
| ยอดขาย 3.Mobile | `SUM(amount) … business_group LIKE '%3.Mobile%'` | 495,830,070.30 | actual อย่างเดียว |
| กำไร (ขาดทุน) ทั้งบริษัท | `SUM(amount) … measure_type = 'ADDITIVE'` | +7,201,490,655.03 | รายได้ 3,056,678,601.50 − ค่าใช้จ่าย 4,144,812,053.53 = **−1,088,133,452.03** |
| รายได้รวม (ข้อมูล EBT) | เหมือนข้อบน | 7,201,490,655.03 | 3,056,678,601.50 (`group_0 = '01.รายได้'`) |

ต้นเหตุ (ฝั่ง contract ของ NT-Report — code ฝั่ง AI ทำตาม contract ถูกแล้ว):
- **sales:** `fact_sales.metric` มี `actual` 87,006 แถว + `target` 15,821 แถว (202501–202607) — contract อธิบายแค่ "ชนิดตัวเลข (เช่น actual)" ไม่มีกฎห้ามรวม;
  `control_totals.csv` ก็รวม actual+target (`__ALL__` 202607 = 6,978,071,395.50 = SUM ทุกแถว) → golden จาก control totals จะให้คะแนนคำตอบที่**ถูก**ว่าผิด
- **ebt:** contract ไม่มี `control_totals` (NT-Report ตั้งใจ: "OBT, no control-totals") และไม่มีกฎบอกว่า EBT = รายได้ − ค่าใช้จ่าย (ค่าใช้จ่ายเก็บเป็นบวก) — มีแค่ "filter ADDITIVE ก่อน agg"

สถานะตอนนี้: source + knowledge ของ sales/ebt ลงทะเบียนแล้ว แต่ context **ปิดไว้** (`is_active=0`) — ไม่มี golden ของ sales/ebt ใน config
(เปิดคืน: `UPDATE schema_contexts SET is_active=1 WHERE name IN ('feed_sales','feed_ebt')` หรือผ่านหน้า admin)

**ทางเลือก:**
- **A (แนะนำ) — แก้ contract ที่ NT-Report:** เพิ่มกฎ (business_rules) ที่ขาด + control totals ที่มีความหมาย → ฝั่ง AI re-sync knowledge เองอัตโนมัติ (2b) แล้วรัน gen_golden + eval — prompt ด้านล่าง
  ถ้าจะให้ control totals กรองได้ (เช่น `metric = 'actual'`, `measure_type = 'ADDITIVE'`) ฝั่ง AI ต้องรองรับ field ใหม่ใน spec (gate + golden) ~0.5 วัน
- **B — เพิ่มกฎฝั่ง AI เอง** (`schema_business_rules` ต่อ context) + เขียน golden ของ sales/ebt ด้วยมือ — เร็ว แต่ความหมายไม่ได้มาจากเจ้าของข้อมูล และเลขคาดหวังไม่ได้ตรวจกับ control totals อิสระ
- **C — ปิด Phase 2 ที่ 2 โดเมน** (revenue + expense) ไป Phase 3 ก่อน; sales/ebt ปิดไว้จน A เสร็จ

### Prompt สำหรับ repo NT-Report (ทางเลือก A)
> ⚠️ ฉบับร่าง — ใช้ `plan/PROMPT_NT_REPORT_P7.md` แทน (รวม scope + นิยาม EBT ที่เจ้าของยืนยัน 2026-09-19: "ยอดขาย" = รายได้ฐานยอดขายใน fact_ebt ≠ รายได้ในรายงานรายได้)

```
ใน repo NT-Report (tools/feed/domains.py → gen_contract → contracts/*.yaml) — AI assistant อ่าน DataFeed ตรง
และสร้าง knowledge จาก contract อัตโนมัติ แต่ 2 โดเมนขาดข้อมูลความหมาย ทำให้ AI ตอบเลขผิด:

1) sales: fact_sales.metric มี 'actual' และ 'target' แต่ contract ไม่บอก
   - เพิ่ม business_rule: amount ของ metric ต่างกันห้ามรวมกัน; "ยอดขาย" = metric='actual' เว้นถามเป้า
   - แก้ description ของ metric ให้ระบุค่าที่มีทั้งหมด (actual, target)
   - control_totals ตอนนี้ SUM ทุกแถว (actual+target) → เพิ่ม metric ใน group_keys (หรือแยก measure ต่อ metric)
     แล้ว build ใหม่ให้ control_totals.csv มีคอลัมน์ metric
   - ระบุชัดใน rule ว่า "ยอดขายรวมทั้งบริษัท" (nt_total) = BG 1–7 เท่านั้นหรือรวม 8/โครงการภาครัฐ
2) ebt: ไม่มี control_totals และไม่บอกวิธีคำนวณ EBT
   - เพิ่ม business_rule: EBT = SUM(amount | ADDITIVE, group_0='01.รายได้') − SUM(amount | ADDITIVE, group_0='02.ค่าใช้จ่าย')
     (ค่าใช้จ่ายเก็บเป็นค่าบวก) และบอกว่าแถว COMPUTED '3.1 กำไร (ขาดทุน) ของส่วนงาน (1)-(2)' ใช้เมื่อไร
   - เพิ่ม control_totals (source fact_ebt, period_key time_key, bg_key group_0, measure amount เฉพาะ ADDITIVE)
     + ไฟล์ control_totals.csv ใน bundle
3) bump schema_version (PATCH ถ้าเพิ่มแค่ rule/description, MINOR ถ้าเพิ่มคอลัมน์ใน control_totals)
ไม่ต้องแก้อะไรฝั่ง AI เพื่อให้ knowledge ตาม — AI re-sync เองเมื่อ contract เปลี่ยน
(ถ้า control_totals ต้องกรองแถว เช่น measure_type='ADDITIVE' ให้บอกรูปแบบ field ที่เพิ่ม ฝั่ง AI จะรองรับใน gate/golden)
```

## Commits (branch `main`)
```
deb0a7e feat(P7-2): data_as_of in /api/v1/query from the verified build
38ab63d feat(P7-2): contract knowledge as a service, re-synced when the contract changes
a2b8568 feat(P7-2): register expense/sales/ebt as file sources; contract-driven gates and golden
```

## สถานะ DB หลังจบงาน (local — ไม่อยู่ใน git)
- backup ก่อน Phase 2: scratchpad ของ session (`config.backup.pre_phase2.db`)
- `config.db`: `data_sources` + `contract_file`, `knowledge_sha`; source 5 ตัว (`legacy`, `datafeed_{revenue,expense,sales,ebt}`);
  context `feed_expense` (active), `feed_sales`/`feed_ebt` (**inactive**); `feed_revenue` keywords/priority = default ใหม่;
  golden `feed_expense` 12 ข้อ (ใหม่), `feed_revenue` 14 ข้อ (เดิม)
- brain ถูก mark dirty (docs ของ 3 โดเมนใหม่ยังไม่เข้า Vanna จนกว่า admin กด Sync Brain — instruction/กฎ/metadata ใช้ได้ทันทีเพราะอ่านจาก config ตรง)
- NT-Report `DataFeed/` ไม่ถูกแตะ
