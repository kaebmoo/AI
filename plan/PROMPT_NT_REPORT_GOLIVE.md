งานฝั่ง NT-Report สำหรับเปิดใช้ "ถามข้อมูลรายงาน" (Assistant, F11) กับ AI จริง — repo /Users/seal/Documents/GitHub/NT-Report, branch main
คู่กับ session ฝั่ง AI (`/Users/seal/Documents/GitHub/AI/plan/PROMPT_P7_GOLIVE_NT_REPORT.md`) — สอง session ทำงานขนานกันได้: ข้อ 1–5 ข้างล่างไม่ต้องรอฝั่ง AI; ข้อ 6–7 ต้องรอ key จริงจากฝั่ง AI
ทำตาม CONVENTIONS.md / README ของ repo นี้ (รูปแบบ commit, test, การ bump version ของ contract); commit เป็นก้อนต่อข้อ; **ห้าม push จนกว่าจะสั่ง**; ห้าม rebase / force-push
repo AI (/Users/seal/Documents/GitHub/AI) = **อ่านอย่างเดียว** — สิ่งที่ต้องแก้ฝั่ง AI ให้เขียนเป็นข้อเสนอในไฟล์ผลของงานนี้ ไม่แก้เอง

## บริบท (ฝั่ง AI ทำอะไรไปแล้ว — 2026-09-20)
- AI อ่าน `DataFeed/dist/<domain>/latest/` **ตรง ไม่ import** (DuckDB) — build ใหม่ที่ publish แบบ atomic ถูกเห็นเองในคำถามถัดไป; ความรู้ของแต่ละ context มาจาก `DataFeed/contracts/<domain>.yaml` และ **re-sync เองเมื่อ contract / schema_version เปลี่ยน** (เพิ่ม/ลบตารางหรือคอลัมน์ ต้องให้ฝั่ง AI ลงทะเบียน source ใหม่)
- context ของ portal อยู่ใน workspace `nt-report`: `feed_revenue` (2.3.0), `feed_expense` (1.2.0), `feed_sales` (1.3.0), `feed_ebt` (1.4.0); งวดล่าสุด revenue / expense / sales 202608, ebt 202607
- API key ของ portal จะผูก workspace `nt-report`: context นอก workspace = **403**, ใช้ได้เฉพาะ `/api/v1/query*`; `scope` บังคับที่ชั้น SQL (key ที่ context ไม่ประกาศ = **400**; ตารางที่ไม่มีคอลัมน์ของ scope key ใช้ไม่ได้ภายใต้ scope นั้น); ทุกคำถามลง audit ฝั่ง AI (`query_audit`: key, channel = `source` ที่ส่งมา, scope, SQL, จำนวนแถว)
- eval ฝั่ง AI เทียบ control totals: revenue 14/14, expense 12/12, sales 12/12, ebt 35/36
- **ของจริงยังไม่เปิด:** ยังไม่มี key จริง, DB จริงของ AI ยังไม่ได้ migrate — session ฝั่ง AI กำลังทำ
- AI มีความสามารถ "คำถามข้ามหลาย context" แล้ว (response มี `parts[]` + `computed`, `data_as_of` ระดับบน = null) แต่**ไม่อยู่ใน go-live รอบนี้**: hook ส่ง `context` เสมอ = เส้นทาง context เดียว

## อ่านก่อน (บังคับ)
- repo นี้: CONVENTIONS.md, pocketbase_0/pb_hooks/assistant.pb.js (ทั้งไฟล์), pocketbase_0/docs/ASSISTANT.md, pocketbase_0/.env.example (หัวข้อ Assistant proxy), pocketbase_0/pb_hooks/report_types.pb.js, docs/PERMISSIONS.md, หน้า/สคริปต์ฝั่ง browser ที่เรียก `/api/nt/assistant/*` (ค้นจากชื่อ endpoint),
  DataFeed/README.md + SPEC.md, DataFeed/contracts/*.yaml, tools/feed/domains.py + gen_contract.py + build_feed.py + test ของ tools/feed
- repo AI (อ่านอย่างเดียว): docs/PORTAL_INTEGRATION.md (รูป request / response / status code — **ความจริงของสัญญา**), docs/manuals/manual_api_keys.md, docs/DATAFEED_INTEGRATION.md,
  plan/PROMPT_NT_REPORT_P7.md (สิ่งที่ขอ repo นี้ไปแล้วทุกรอบ + สถานะ + "ข้อเสนอจาก AI Plan 7 Phase 5" ท้ายไฟล์), plan/archive/RESULT_P7_PHASE5.md §1b + §5 + §7, plan/archive/RESULT_P7_PHASE6.md §9 ("ของเดิมที่พบ" = ข้อบกพร่องของ REST ที่ hook ได้รับอยู่วันนี้), app/api/v1/query.py (`SimpleQueryRequest` / `SimpleQueryResponse`)

## สิ่งที่ฝั่ง AI เห็นจากการอ่าน hook (2026-09-20) — **ตรวจยืนยันกับ code ก่อนเชื่อ**
1. **คำตอบแบบ 200 + `error` ที่ `data_as_of` = null ถูก hook แปลงเป็น 502 ทั่วไป** ("upstream_invalid"): AI คืน 200 พร้อม `error` และ `data_as_of: null` เมื่อ error เกิดก่อนอ่านข้อมูล — เช่น **"ข้อมูลกำลังถูก publish — กรุณาถามใหม่"**, คำถามซ้ำภายใน 5 วินาที (`duplicate_request`), สร้าง SQL ไม่สำเร็จ → ผู้ใช้เห็น "ไม่สามารถประมวลผลคำถามได้ในขณะนี้" ทุกกรณี ทั้งที่บางกรณีควรบอกให้ลองใหม่ทันที
   - หมายเหตุ: ผู้ใช้ portal ทุกคนเข้ามาที่ AI ในชื่อ user เดียวของ key และ dedup ของ AI ผูก user + คำถาม → สองคนถามคำถามเดียวกันพร้อมกัน คนที่สองได้ `duplicate_request` (ฝั่ง AI รับทราบแล้ว)
2. **คำเตือนงวดไม่ตรงน่าจะเตือนผิด:** hook เทียบ `data_as_of.period` (= งวดล่าสุด**ของ build**) กับงวดของรายงานแบบ `!==` — แต่ `scope.year_month` บังคับให้คำตอบเป็นงวดของรายงานอยู่แล้ว → เปิดรายงาน 2026-07 ขณะ build ล่าสุดคือ 202608 จะขึ้น "ข้อมูลที่ตอบเป็นงวด 202608 ซึ่งไม่ตรงกับงวดรายงาน 2026-07" ทั้งที่ตัวเลขที่ตอบคือของ 202607; กรณีที่ควรเตือนจริงคือ **build ยังไปไม่ถึงงวดของรายงาน** (`data_as_of.period` < งวดรายงาน → scope ได้ 0 แถว เช่น รายงาน ebt 2026-08 ขณะ ebt อยู่ที่ 202607)
3. **status code ที่ hook ไม่แยก:** 403 (context ใน `ASSISTANT_CONTEXT_MAP` อยู่นอก workspace ของ key หรือถูก policy ปฏิเสธ = **config ผิด ไม่ใช่ปัญหาชั่วคราว** — ตั้งแต่ hardening 2026-09-20 ข้อความ 403 ของ "นอกสิทธิ์" กับ "ไม่มี context นั้น" **เหมือนกัน** แยกจาก response ไม่ได้ ต้องดู log / `GET /admin/query-audit` ฝั่ง AI), 401 (key ผิด/ถูกเพิกถอน — **เกินโควตาเป็น 429 แล้ว ไม่ใช่ 401**), **429** (เกิน rate limit / โควตารายวัน) และ **503** ตัวใหม่ (AI เขียน audit ไม่ได้ จึงไม่ส่งคำตอบ) → ทั้งหมดกลายเป็น 502 ข้อความเดียวกัน และ audit เป็น `upstream_<code>`
4. **สิ่งที่ส่งต่อถึง browser:** hook ขอ `include_sql: true` แล้วส่ง `sql` และ `payload.error` (ข้อความดิบจาก AI) ให้ browser — ขัดกับ comment ในไฟล์เอง ("never leak raw upstream errors"); ฝั่ง AI ยังมีข้อบกพร่องที่รู้แล้ว: ข้อความ exception อยู่ใน `answer` / `error`, และ**มี SQL ในข้อความ `answer` เมื่อได้ 0 แถวแม้ไม่ขอ** (จะแก้ตามที่เจ้าของเลือก — hook ไม่ควรพึ่งว่าแก้แล้ว)
5. **`scope.year_month` = เดือนเดียวของรายงาน:** ภายใต้ scope นี้ AI มองเห็นข้อมูลเดือนเดียว → "เทียบกับเดือนก่อน", "แนวโน้มรายเดือน", "รวม ม.ค.–ก.ค." ตอบไม่ได้/ได้ 0 แถว ทั้งที่ dashboard ของรายงานเดียวกันแสดงหลายเดือน (ยอดสะสมที่เป็นคอลัมน์ point-in-time เช่น `revenue_ytd` ยังตอบได้) — AI รับ `scope` เป็น list ได้ (1–1000 ค่า = `IN`)
6. `ASSISTANT_CONTEXT_MAP` ใน `.env.example` มีแค่ `revenue=feed_revenue`; report_type มี ebt / expense / revenue / sales / presentation (presentation ไม่มี context = ไม่แสดงปุ่ม — ถูกแล้ว)
7. ebt: ถาม "กำไรของทั้งบริษัท" → AI ตอบ EBT ของ **2 สายงานขาย** (−284.05 M ก.ค. 69) แล้วอธิบายว่าเป็น "กำไรสุทธิรวมของบริษัท" — contract มีกฎขอบเขต (`ebt_report_scope_and_exclusions`, `computed_segment_profit_not_company_ebt`) แต่ไม่มีกฎว่า**ถูกถามนอกขอบเขตแล้วต้องทำอย่างไร**; คำถามย่อย "EBT เดือนล่าสุด" บางรอบได้รายสายงาน 2 แถวแทนยอดรวม

## งานตามลำดับ
0. baseline: test ของ repo นี้ตาม CONVENTIONS (tools/feed + อื่น ๆ ที่มี) ผ่านก่อนเริ่ม; จดสถานะ `DataFeed/dist/*/latest` (build_id, period, schema_version ต่อโดเมน)
1. **ยืนยันข้อสังเกต 1–7 กับ code จริง** (hook + ฝั่ง browser + contract) → ตาราง "ข้อสังเกต / จริงไหม / ผลต่อผู้ใช้ / จะแก้อย่างไร" ในไฟล์ผลของงานนี้ (วางตามธรรมเนียมของ repo — เช่น pocketbase_0/docs/ หรือ docs/) — ข้อไหนไม่จริงให้เขียนว่าไม่จริงพร้อมหลักฐาน
2. เสนอแผนแก้ + **หยุดถามเจ้าของ** เรื่องที่ยังไม่ตัดสิน (ข้างล่าง); ส่วนที่ไม่ขึ้นกับคำตอบทำต่อได้
3. **contract ebt (PATCH — ไม่แตะข้อมูล):** `tools/feed/domains.py` → `gen_contract` → `DataFeed/contracts/ebt.yaml`
   - business_rule ใหม่ (เสนอ id `ebt_not_company_wide`): ชุดข้อมูลนี้ครอบคลุมเฉพาะ 2 สายงานขาย — คำถามถึงกำไร / EBT ของ**ทั้งบริษัท**หรือของสายงานอื่น **ไม่มีข้อมูลในชุดนี้: ห้ามตอบด้วยยอดของ 2 สายงานขาย**; ถ้าผู้ถามยืนยันว่าต้องการยอดของรายงาน EBT ให้ตั้งชื่อคอลัมน์ผลลัพธ์และอธิบายว่า "เฉพาะ 2 สายงานขาย"
   - description ของ `ebt` / `ebt_month` / `sales_base_revenue*` / `expense*` ใน `fact_ebt_total_monthly` และ `fact_ebt_division_monthly` ขึ้นต้นว่า "เฉพาะ 2 สายงานขาย"; กฎว่า "EBT รวม / ทั้งรายงาน" ใช้ตาราง total (ไม่ใช่รายสายงาน 2 แถว)
   - bump PATCH, build, test ของ tools/feed ผ่าน, publish แบบ atomic → AI re-sync เอง (ไม่ต้องลงทะเบียนใหม่เพราะคอลัมน์ไม่เปลี่ยน) — **ก่อน publish ของจริงให้บอกเจ้าของ** (AI อ่าน `latest` สด)
4. **`description` ของทุก contract เป็นภาษาไทย 1–2 ประโยค: ชุดนี้ตอบอะไร / ไม่ตอบอะไร** (ตอนนี้เป็น "NT Revenue Data Feed" ฯลฯ) — AI ใช้ข้อความนี้เลือก context ตอนแตกคำถามข้ามโดเมน และแสดงใน `list_contexts` ของ MCP; ตัวอย่าง ebt: "EBT ของ 2 สายงานขาย (รายได้ฐานยอดขาย − ค่าใช้จ่าย) รายสายงาน/ศูนย์ต้นทุน — ไม่ใช่กำไรของทั้งบริษัท และไม่ใช่รายได้ในรายงานรายได้" (PATCH; รวมกับข้อ 3 ใน build เดียวได้)
5. **hook + ฝั่ง browser** (ตามที่เจ้าของเลือกในข้อ 2; ทุกการแก้มี test ตามธรรมเนียมของ repo หรือขั้นทดสอบมือที่เขียนไว้ใน ASSISTANT.md):
   - 200 + `error`: ส่งต่อเป็นข้อความที่ **map แล้ว** (ไม่ใช่ข้อความดิบ) — อย่างน้อยแยก "ข้อมูลกำลังอัปเดต ลองใหม่อีกครั้ง" / "คำถามซ้ำ รอสักครู่" / "ตอบคำถามนี้ไม่ได้" และ**ไม่บังคับ `data_as_of` เมื่อไม่มีคำตอบ**; คำตอบที่สำเร็จยังต้องมี `data_as_of` ที่ถูกต้องเหมือนเดิม
   - คำเตือนงวด: เตือนเมื่อ build ยังไม่ถึงงวดของรายงาน; ไม่เตือนเมื่อ build ใหม่กว่างวดของรายงาน (scope คุมแล้ว) — ข้อความให้ตรงความจริง
   - status: 403 → audit `upstream_forbidden` + ข้อความ "การตั้งค่าไม่ถูกต้อง ติดต่อผู้ดูแล" (ห้ามลองใหม่ด้วย context อื่น / ไม่มี scope); 401 → `upstream_unauthorized`; **429 และ 503** → "ระบบใช้งานเต็ม / ยังไม่พร้อม ลองใหม่ภายหลัง" (ทั้งคู่คือ "ลองใหม่" ไม่ใช่ "ระบบพัง" — ไม่ต้องเดาจาก body อีกแล้ว AI แยก status ให้ตั้งแต่ hardening 2026-09-20); 400 คงเดิม (ไม่ตอบแบบไม่มี scope)
   - ไม่ส่ง `payload.error` ดิบและ (ถ้าเจ้าของเลือก) ไม่ส่ง `sql` ถึง browser; audit ฝั่ง PB เก็บ status ที่แยกแล้ว
   - ไม่แตะ: การตัดสินสิทธิ (`canAccessReport`), การสร้าง scope จากรายงาน + หน่วยงานที่อนุมัติ, default deny เมื่อไม่มี config
6. **เอกสาร + ค่าตั้ง:** `pocketbase_0/docs/ASSISTANT.md` (key ผูก workspace `nt-report` — วิธีขอจากฝั่ง AI; `ASSISTANT_CONTEXT_MAP=revenue=feed_revenue,expense=feed_expense,sales=feed_sales,ebt=feed_ebt` เฉพาะ type ที่ผ่านการเทียบตัวเลขในข้อ 7; ตาราง error ตาม status จริง; checklist เปิดใช้; ขั้นถอยกลับ = ลบ `ASSISTANT_API_KEY` แล้ว restart → ปุ่มหาย), `.env.example` ให้ตรงกัน — **ไม่ใส่ key จริงในไฟล์ที่ track**
7. **(รอ key จริงจากฝั่ง AI)** เจ้าของใส่ `ASSISTANT_API_URL` / `ASSISTANT_API_KEY` / `ASSISTANT_CONTEXT_MAP` ใน `pocketbase_0/.env` + restart PB → ทำ E2E ร่วมกับ session ฝั่ง AI:
   - ผู้ใช้ไม่มีสิทธิ์เปิดรายงาน → 403 จาก PB และ**ไม่มี call ออกไป AI**; ผู้ใช้มีสิทธิ์ → คำตอบ + `data_as_of`; "เดือนล่าสุด" ในรายงานงวด 2026-07 = ก.ค. 69; รายงานที่จำกัดหน่วยงาน A ถามถึง B = ไม่มีข้อมูล; context map ชี้นอก workspace → ข้อความ config ผิด; ระหว่าง publish → "ข้อมูลกำลังอัปเดต"; `audit_logs.action = assistant_ask` ครบทุกกรณีพร้อม status ที่แยกแล้ว
   - **ตัวเลขอ้างอิงจาก dashboard จริง:** ต่อ report_type ที่จะเปิด เตรียม 10 คำถามที่ผู้ใช้ portal จะถามจริง + ตัวเลขที่**หน้า dashboard ของรายงานนั้นแสดง** (ระบุรายงาน / งวด / tab / ที่มาของตัวเลข เช่น data.js หรือ control_totals) → ไฟล์ที่ session ฝั่ง AI อ่านได้ (เสนอ: `DataFeed/handoff/assistant_reference_<period>.md`) — ฝั่ง AI ใช้ปิดเกณฑ์ ≥ 9/10 ต่อ report_type; type ที่ไม่ผ่าน = ตัดออกจาก context map
8. อัปเดตไฟล์ผลของงานนี้ + CHANGELOG / DEPLOY_NOTES ตามธรรมเนียมของ repo; เขียน "ข้อเสนอกลับไปฝั่ง AI" (ถ้ามี) เป็นหัวข้อท้ายไฟล์ผล; แล้วหยุด
   (ถ้า context ใกล้เต็มก่อนถึงข้อนี้ ให้หยุดแล้วเขียน prompt ส่งต่อ session ถัดไป)

## ข้อค้างที่รอเจ้าของตัดสิน (อย่าตัดสินเอง — ถามตอนข้อ 2)
- **ขอบเขตเวลาของ `scope`:** เดือนเดียวของรายงาน (ตอนนี้ — เข้มสุด แต่ถามเทียบเดือน/แนวโน้มไม่ได้) / ทุกเดือนตั้งแต่ต้นปีถึงงวดของรายงาน / ทุกเดือนที่ dashboard ของรายงานนั้นแสดง (≤ งวดของรายงาน) — หลักของแผน: "ถามได้เท่ากับข้อมูลของรายงานที่เปิดได้"; เปลี่ยนตรงนี้ = เปลี่ยน entitlement ต้องสั่ง
- **ผู้ใช้ portal เห็น SQL ไหม** (ตอนนี้ hook ขอและส่งต่อ `sql` เสมอ): เห็นทุกคน / เฉพาะ admin / ไม่เห็น
- ข้อความ error ที่ map แล้ว: ชุดข้อความ + กรณีไหนเชิญให้ลองใหม่
- report_type ที่เปิดรอบแรก: ทั้ง 4 หรือเฉพาะที่ผ่านการเทียบตัวเลข (ข้อเสนอ: เฉพาะที่ผ่าน)
- ใครใส่ key ใน `pocketbase_0/.env` + restart PB (ค่าเริ่มต้น: เจ้าของ) และ PB ที่ใช้ทดสอบ E2E คือ instance ไหน
- publish build ของ contract PATCH (ข้อ 3–4) เมื่อไร — ก่อนหรือหลังฝั่ง AI migrate DB จริง (ข้อเสนอ: ก่อน เพื่อให้การเทียบตัวเลขของ ebt ใช้กฎใหม่)
- ข้อเสนอจาก AI Phase 5 ที่เกิน PATCH (ไม่บล็อก go-live — ตัดสินว่าจะทำไหม/เมื่อไร): ชื่อสายงานของ revenue ต่างจาก expense / ebt 1 ชื่อ (`กรรมการผู้จัดการใหญ่` vs `… บมจ.เอ็นที`) หรือรหัสสายงานร่วม; sales ไม่มีสายงาน (มีแต่สายการขาย); ebt `group_1` = `03.Mobile` ขณะที่ revenue / sales = `3.Mobile`; dataset ผลดำเนินงานทั้งบริษัท (ตอนนี้ไม่มี — AI จะไม่คำนวณเอง); control totals ราย `division` ของ ebt
- multi-context ใน portal (ภายหลัง): ต้องการไหม — ถ้าต้องการ hook ต้อง**ไม่ส่ง `context`** สำหรับรายงาน/หน้าที่ข้ามโดเมน และอ่าน `parts[].data_as_of` แทนระดับบน (`data_as_of` ระดับบน = null, `context` = `a+b`, `computed` = ratio / ส่วนต่างที่คำนวณใน code)

## กติกา
- **สิทธิยังเป็นของ portal:** hook เป็นผู้ตัดสินว่าใครถามอะไรได้ (AI แค่บังคับ scope ที่ส่งไป) — ห้ามทำให้ scope กว้างขึ้นโดยไม่มีคำสั่ง; ห้ามลองใหม่แบบไม่มี scope หรือเปลี่ยน context เมื่อ AI ปฏิเสธ; ไม่มี config = ไม่แสดงปุ่ม; key อยู่ฝั่ง server ของ PB เท่านั้น — browser ห้ามเรียก AI ตรง
- **secret:** key จริงอยู่ใน `pocketbase_0/.env` (ไม่ track) เท่านั้น — ห้ามอยู่ใน commit / log / เอกสาร / ข้อความสรุป; ตรวจ `git diff --cached` ก่อน commit ทุกครั้ง
- contract: เปลี่ยนความหมาย/เพิ่มกฎ/description = PATCH; เพิ่มตาราง/คอลัมน์ = MINOR (ฝั่ง AI ต้องลงทะเบียน source ใหม่ — แจ้งในไฟล์ผล); เปลี่ยนชื่อ/ลบ = MAJOR (ต้องสั่ง); แก้ที่ `domains.py` แล้ว gen — ไม่แก้ yaml ด้วยมือ; control totals ต้องกระทบยอดก่อน publish (`reconcile.ok`) — AI ปฏิเสธ build ที่ไม่ผ่าน
- publish แบบ atomic เท่านั้น (`builds/<id>` + symlink `latest`); AI เห็น build ใหม่ทันที — บอกเจ้าของก่อน publish ของจริง
- ตัวเลขใน dashboard / DataFeed ห้ามเปลี่ยนเพื่อให้ AI "ตอบตรง" — ถ้าไม่ตรงให้หาสาเหตุ (contract / scope / โมเดล / ข้อมูล) แล้วรายงาน
- ถ้าเจอสิ่งที่ขัดกับ PORTAL_INTEGRATION.md ของฝั่ง AI ให้หยุดและรายงานพร้อมทางเลือก — เอกสารนั้นคือสัญญา; ความต่างระหว่างเอกสารกับพฤติกรรมจริงของ AI = ข้อเสนอกลับไปฝั่ง AI
- จบแต่ละข้อสรุป: ทำอะไร, หลักฐาน (test / ขั้นทดสอบมือ), commit list, ข้อค้างที่ต้องให้ผมตัดสิน

## อัปเดตจากงาน hardening ฝั่ง AI (2026-09-20)
สัญญาของ field ไม่เปลี่ยน แต่ `error` เป็น**รหัสคงที่**แล้ว (`query_failed` / `source_unavailable` / `duplicate_request` / `internal_error`), `answer` ไม่มี SQL เมื่อได้ 0 แถว, body ของ 400 / 403 เป็นข้อความตายตัว, เกินโควตา = 429, มี 503 ใหม่, และ `GET /api/v1/query/contexts` ต้องส่ง `X-API-Key` แล้ว — รายละเอียด: `docs/PORTAL_INTEGRATION.md` §"สิ่งที่ response บอก และไม่บอก" และ `plan/PROMPT_NT_REPORT_P7.md` ท้ายไฟล์

## อัปเดตจากฝั่ง AI หลังทำ go-live จริง (2026-09-20 กลางคืน)
ผลเต็ม: `plan/archive/RESULT_P7_GOLIVE.md` · ตัวเลข 10 คำถาม: `plan/archive/RESULT_F11.md` ·
สรุปสำหรับ repo นี้: `plan/PROMPT_NT_REPORT_P7.md` ท้ายไฟล์ (4 หัวข้อ)

1. **ออก key จริงแล้ว** (`nt-report-portal`, workspace `nt-report`, 20/นาที 2,000/วัน) — เจ้าของเป็นผู้ใส่ `.env` และ restart PB
2. **ต้องแก้ hook 1 จุดก่อน E2E ผ่านเกณฑ์:** `mapUpstreamError` หา `/publish/i` ใน `payload.error` ซึ่งตอนนี้เป็น
   **รหัส** `source_unavailable` → ระหว่าง publish ผู้ใช้ได้ "ถามใหม่ด้วยถ้อยคำอื่น" แทน "ข้อมูลกำลังอัปเดต"
3. **ตัวเลขยังไม่ผ่าน 9/10** (revenue 8 · expense 8 · ebt 8 · sales 5 หลังฝั่ง AI แก้ต้นเหตุของ scope กว้าง)
   → **ยังไม่ใส่ report_type ใดใน `ASSISTANT_CONTEXT_MAP`**; ที่เหลือแยกเป็น contract / sales knowledge / ถ้อยคำของกฎ
4. `scopeMonths()` ถูกแล้ว — ขอให้คง "งวดของรายงานเป็นค่ามากสุดของ list" ไว้ ฝั่ง AI ใช้ค่ามากสุดเป็นงวดอ้างอิง
5. **ต้อง restart PocketBase** — process ที่รันอยู่เก่ากว่าการแก้ hook ทั้งหมดของ session นี้
