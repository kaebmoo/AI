# RESULT Plan 7 Phase 5 — ถามข้ามหลาย context

**วันที่:** 2026-09-19 | **Branch:** `main` (ยังไม่ push) | **แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 5
**Baseline:** pytest **946 passed, 3 skipped** (`venv/bin/python3.14 -m pytest -q -p no:cacheprovider`; 936 ของ Phase 4.5 + 10 จากงาน AuditService/admin tools ที่ merge เข้า main ระหว่างทาง) | backup `config.db` + `app.db` อยู่ใน scratchpad ของ session
**Provider ของการวัด:** admin default (matcha, gpt-4.1) | ทุกการทดลองรันบน**สำเนา** config/app DB ที่ migrate แล้ว — DB จริงไม่ถูกแตะ

## สรุป

| Exit criterion | ผล | ผ่าน? |
|---|---|---|
| ชุดคำถามข้ามโดเมน 10 ข้อ ถูก ≥ 8 (เทียบตัวเลขที่ dashboard ใช้) | baseline (flag ปิด) **0/10** → เปิด orchestrator **8/10, 8/10, 9/10** (3 รอบ LLM จริง; รอบ 3 ใช้เกณฑ์ให้คะแนนที่เข้มขึ้นหลัง review) — `eval_20260919_2200` (baseline), `_2203`, `_2209`, `_2221` | ✅ |
| ข้อที่ตอบไม่ได้ต้องบอกว่าไม่ได้ ไม่เดาตัวเลข | orchestrator: ส่วนที่ล้ม/ถูกปฏิเสธ = "ตอบได้ k จาก n ส่วน" + ไม่คำนวณ (unit test); **แต่ข้อ 10 "กำไรของทั้งบริษัท" ยังถูกตอบด้วยยอดของ 2 สายงานขาย (−284.05 M) ทั้ง 3 รอบ** — เป็น pipeline context เดียว (`feed_ebt`) + contract ไม่มีกฎสำหรับคำถามนอกขอบเขต ไม่ใช่ orchestrator → ข้อเสนอถึง NT-Report (§7) | ⚠️ 9/10 ข้อ |
| eval รายโดเมนไม่ลด (flag เปิด) | revenue **14/14**, expense **12/12**, sales **12/12**, ebt **35/36** — เท่าเดิมทุกโดเมน (P50 5.6 / 6.6 / 6.2 / 7.4 s) | ✅ |
| latency คำถามข้ามโดเมน (เพดานที่เจ้าของรับ: P50 ≤ 15 s, P95 ≤ 30 s) | P50 **7.8–9.2 s**, P95 **11.5–12.1 s** (2 ใน 3 รอบ); รอบแรก P95 = 106 s จากข้อเดียวที่ gateway ค้าง (ไม่เกิดซ้ำ) — baseline context เดียว P50 6.3 s | ✅ |
| flag ปิด = พฤติกรรมเดิม | unit test (ไม่มี provider call, `engine.query` ได้ argument เดิม); response เพิ่ม field `parts` / `computed` = `null` | ✅ |
| sentinel ที่ขอบ HTTP: source A = `full`, B = `schema_only` → ไม่มีค่าของ B ใน request ใด | `test_no_value_of_the_restricted_source_reaches_a_provider` — QueryEngine → AIService → MatchaProvider จริง ทั้ง call แตกคำถามและคำถามย่อยทั้งสอง; ค่าของ A เดินทาง (ตัวควบคุมบวก), ของ B = 0, ผู้เรียกยังได้แถวของ B, ratio คำนวณใน code | ✅ |
| review อิสระ (agent แยก อ่านอย่างเดียว) | **ไม่มี critical / high**; medium 3 → แก้ `d07f397`; low 2 (1 แก้, 1 รับไว้) — §6 | ✅ |
| pytest | 946 → **997 passed**, 3 skipped (+51; ไม่มี test เดิมถูกแก้) | ✅ |

**เจ้าของตัดสิน (2026-09-19):** orchestrator + template (ไม่มี LLM ในขั้นรวม) · ชุด 10 ข้อ = ชุดร่าง §2 · งวดไม่เท่ากัน = ตอบ + เตือน ไม่คำนวณข้าม · ratio + ส่วนต่างพร้อมป้าย "ไม่ใช่กำไร / EBT ทางการ" · ไม่ข้าม workspace · scope ที่ไม่ประกาศ = 400 ทั้งคำถาม · `/api/v1/query` ก่อน · P50 ≤ 15 s / P95 ≤ 30 s

## 1. สำรวจ

### 1a. คำถามข้ามโดเมนที่ผู้ใช้ถามจริง

`chat_history` 1,513 คำถาม (2026-01-26 → 2026-07-14 — **ก่อน** มี `feed_*` ครบ 4 โดเมน; ช่องทาง portal ยังไม่มี key จริง จึงยังไม่มีคำถามจาก portal เลย), `trending_queries` 3, `unmatched_keywords` 26:

| แบบ | จำนวน | ตัวอย่างจริง | ตอนนี้ไปไหน |
|---|---|---|---|
| ผลดำเนินงาน: รายได้ + ค่าใช้จ่าย + กำไร/EBT/margin ราย**กลุ่มธุรกิจ/บริการ** | ~55 (กำไร/ขาดทุน/ebt/margin) + 10 (รายได้+ค่าใช้จ่าย) | "ผลดำเนินงานของกลุ่มธุรกิจ ปี 2025 รายได้ ค่าใช้จ่าย กำไรขั้นต้น และ ebt", "ขอ % ebt margin ของกลุ่มธุรกิจ เทียบระหว่างปี" | `pl_costtype` (workspace `default`) = **context ที่รวมมาแล้วจากต้นทาง** → ทางเลือก 1 ใช้อยู่แล้ว |
| รายได้เทียบค่าใช้จ่ายของ**หน่วยงาน** | 1 | "รายได้ของจังหวัดแพร่ เมื่อเทียบกับ ค่าใช้จ่ายตอบแทนแรงงาน เป็นอย่างไร" | ไม่มี context ที่รวมไว้ → **ต้อง orchestrator** (revenue + expense, key = หน่วยงาน) |
| ยอดขาย + รายได้ | 2 | "รายได้ รายฝ่าย โดยฝ่ายที่มียอดขายมากสุด…" | ผู้ใช้ใช้คำว่า "ยอดขาย" แทนรายได้ — ไม่ใช่ข้ามโดเมนจริง |
| transfer price + รายได้/ค่าใช้จ่าย | 2 | "รายละเอียดการ transfer ของสายงานยุทธศาสตร์ ในมุมที่เป็นรายได้" | context เดียว (`transfer price`) |

**Dashboard / รายงานของ NT-Report ที่แสดงตัวเลขมากกว่าหนึ่งโดเมน** (portal มี report_type = ebt / expense / revenue / sales / presentation; `ASSISTANT_CONTEXT_MAP` map 1:1 → ไม่มี context ข้ามโดเมน):

| หน้า | โดเมน | แสดง / คำนวณอะไร | grain | คำนวณเองหรืออ่านชุดที่รวมแล้ว |
|---|---|---|---|---|
| **Forecast Dashboard** (`Forecast/dashboard_build/07_build_dashboard.py:1053-1066`) | revenue + expense | KPI: Revenue (เดือนล่าสุด), Expense (เดือนล่าสุด), **Revenue / Expense Ratio** = Σรายได้ ÷ Σค่าใช้จ่าย | ทั้งบริษัท, รายเดือน | คำนวณเองจาก DW CSV สองชุด |
| **OrgReport Division Report** — exec summary (`OrgReport/sections/exec_summary.py:17-74`) | revenue + sales + expense | KPI 3 ใบเรียงกัน: รายได้ YTD, ยอดขาย YTD (เทียบเป้า), ค่าใช้จ่าย YTD | **สายงาน**, YTD | อ่าน clean layer ของแต่ละโดเมน วางข้างกัน |
| OrgReport — quarterly (`data_engine.py:738-766`) | revenue + expense | **cost ratio = ค่าใช้จ่าย ÷ รายได้** ต่อไตรมาส; กลุ่มค่าใช้จ่ายที่โตเร็วกว่ารายได้ | สายงาน, ไตรมาส | คำนวณเอง |
| OrgReport — ภาคผนวก ก (`sections/appendix_units.py:45-100`) | revenue + sales + expense | รายได้ YTD / ยอดขาย YTD / ขายเทียบเป้า / ค่าใช้จ่าย YTD ในแถวเดียว | **ฝ่าย** | วางข้างกัน |
| OrgReport — EBT module / EBT Dashboard v4 | ebt | รายได้ (ฐานยอดขาย) / ต้นทุน / EBT / margin | สายงาน → ฝ่าย → ส่วน | **ชุดที่รวมมาแล้ว** (= `feed_ebt`); เอกสารของรายงานระบุเองว่า**คนละฐานบัญชี ไม่กระทบยอด**กับส่วนรายได้/ค่าใช้จ่าย และข้ามส่วนนี้เมื่องวด EBT ≠ งวดรายงาน |

→ ของจริงที่ "ข้ามโดเมน" มีสองรูป: **(ก) วางตัวเลขของหลายโดเมนข้างกัน** ที่ grain เดียวกัน (บริษัท / สายงาน / ฝ่าย / ศูนย์ต้นทุน) และ **(ข) อัตราส่วนรายได้↔ค่าใช้จ่าย** — ไม่มีหน้าใดเอา "รายได้ − ค่าใช้จ่าย" จากสองโดเมนมาเรียกว่ากำไร (กำไร/EBT มาจากชุด EBT ที่รวมแล้วเสมอ)

### 1b. ตอบจาก context เดียวได้ไหม — เทียบ contract 4 โดเมน

contract: revenue 2.3.0, expense 1.2.0, sales 1.3.0, ebt 1.4.0 | งวดล่าสุด (manifest, ตรวจ 2026-09-19): revenue / expense / **sales = 202608**, **ebt = 202607** (prompt ของ session ระบุ sales 202607 — NT-Report publish build ใหม่แล้ว) → งวดร่วมล่าสุด **202607**, ช่วงร่วม 202501–202607

| key | ใช้ร่วมได้ระหว่าง | หลักฐาน (ค่าจริงในไฟล์) |
|---|---|---|
| งวด YYYYMM (int) | ทั้ง 4 | รหัสเดียวกัน ชื่อคอลัมน์ต่าง (`year_month` / `time_key`) |
| `cost_center` (7 ตัวอักษร) | ทั้ง 4 | rev∩exp 445, rev∩sales 397, exp∩ebt 599/599, sales∩exp 502/503 |
| สายงาน (ชื่อ) | expense ↔ ebt ตรงกัน 12/12; revenue ต่าง 1 ชื่อ (`กรรมการผู้จัดการใหญ่` vs `… บมจ.เอ็นที`) + `ไม่ระบุ`; **sales ไม่มีสายงาน** (มี `sales_line / sales_group / sales_dept` = สายการขาย) | expense ต้องผ่าน `dim_org_snapshot` (per เดือน) |
| กลุ่มธุรกิจ | revenue `bu` ↔ sales `business_group` รหัสเดียวกัน (`3.Mobile`); **ebt `group_1` = `03.Mobile`** (เติม 0); expense ไม่มี | sales มีค่าเพิ่ม `โครงการภาครัฐ` |
| product | revenue `product_key` ↔ sales `product_code` ร่วม 164 รหัส | — |

ความหมายที่**ไม่**ตรงกัน (ตรวจด้วยตัวเลข 202607):
- ebt `sales_base_revenue_month` 1,206,460,451.69 ≠ รายได้ feed_revenue ของ 2 สายงานเดียวกัน 1,141,292,680.87 (ห่าง 65.2 M) — ตรงกับกฎ `ebt_sales_base_is_not_revenue`; contract ebt ระบุ `ebt_sales_base_vs_sales_dw`: **ไม่มี bridge ที่อนุมัติ**ไปหา sales feed
- ebt ครอบคลุม **2 สายงานขาย**เท่านั้น: `expense_month` 1,490,506,698.33 (กระทบยอดกับ feed_expense ของ 2 สายงานเดียวกัน**ตรงทุกสตางค์**) แต่ค่าใช้จ่ายทั้งบริษัท = 4,144,812,053.53
- sales (actual) vs revenue รายกลุ่มธุรกิจ: BG1–7 ต่างกัน ≤ 0.1 M, BG8 ต่าง 15.0 M; รวม 3,289.66 vs 3,274.67 M — contract ทั้งสองฝั่งยังห้ามใช้แทนกัน (`sales_is_not_revenue`)
- → **"รายได้ − ค่าใช้จ่าย" จาก feed_revenue + feed_expense ไม่ใช่ EBT/กำไรทางการของอะไรเลย** (ทั้งบริษัท = 3,274.67 − 4,144.81 = −870.15 M; EBT ทางการของรายงาน = −284.05 M ของ 2 สายงานขาย)

| # | แบบคำถาม | โดเมน | ตอบจาก context เดียว? | key ที่ใช้เทียบ | ตัวเลขอ้างอิง (202607 เว้นแต่ระบุ) |
|---|---|---|---|---|---|
| P1 | รายได้ + ค่าใช้จ่าย (+ ยอดขาย) **ทั้งบริษัท** รายเดือน | rev + exp (+ sales) | ❌ → orchestrator | งวด | 3,274,665,994.46 / 4,144,812,053.53 / ยอดขายจริง 3,289,655,675.33 — Forecast Dashboard KPI; `control_totals.csv` ของแต่ละโดเมน |
| P2 | อัตราส่วนรายได้ ÷ ค่าใช้จ่าย (หรือกลับกัน) | rev + exp | ❌ → orchestrator + คำนวณใน code | งวด | 202608: 3,434,072,699.62 ÷ 3,690,470,021.65 = 0.9305 — Forecast Dashboard "Revenue / Expense Ratio" |
| P3 | รายได้ / ยอดขาย / ค่าใช้จ่ายของ**หน่วยงานเดียวกัน** | rev + sales + exp | ❌ → orchestrator | `cost_center` (ทุกโดเมน); สายงาน (rev/exp เท่านั้น) | ศูนย์ต้นทุน 2P10200: 34,020,833.34 / 452,157,846.07 / 46,206,528.85 — OrgReport ภาคผนวก ก |
| P4 | ยอดขาย vs รายได้ รายกลุ่มธุรกิจ | sales + rev | ❌ → orchestrator | `bu` = `business_group` | 3.Mobile: ยอดขายจริง 180,775,231.30 / รายได้ 180,756,888.16 |
| P5 | EBT / กำไร / margin / รายได้ฐานยอดขาย / ค่าใช้จ่าย ของ 2 สายงานขาย, รายสายงาน/ศูนย์ต้นทุน | ebt | ✅ `feed_ebt` | — | สายงาน 1: `expense_month` 827,557,643.30, `ebt_month` −233,166,436.29; รวม `ebt` สะสม 417,325,628.68 — EBT Dashboard |
| P6 | ยอดขายเทียบเป้า / รายได้เทียบเป้า | sales หรือ revenue | ✅ context เดียว (เป้าอยู่ในโดเมนเดียวกัน) | — | eval รายโดเมนครอบคลุมแล้ว |
| P7 | ผลดำเนินงานรายกลุ่มธุรกิจ/บริการ (รายได้, ต้นทุน, กำไรขั้นต้น, EBT) | — | ✅ `pl_costtype` (workspace `default`) | — | คำถามจริงของผู้ใช้เกือบทั้งหมดเป็นแบบนี้ |
| P8 | **กำไร/EBT ทั้งบริษัท** หรือของหน่วยงานนอก 2 สายงานขาย | — | ❌ **ไม่มีข้อมูลทางการใน `nt-report`** | — | ต้อง "ตอบไม่ได้" — rev − exp ไม่ใช่ตัวเลขทางการ (ข้อเสนอถึง NT-Report: §4) |
| P9 | โดเมนที่งวดล่าสุดไม่เท่ากัน ("รายได้และ EBT เดือนล่าสุด") | rev + ebt | ❌ → orchestrator + **ต้องบอกงวดของแต่ละตัวเลข** | งวด | รายได้ 202608 = 3,434,072,699.62; `ebt_month` 202607 = −284,046,246.64 |

### 1c. Baseline — router + pipeline ปัจจุบันกับคำถามข้ามโดเมน

Router (deterministic, config จริง): คำถามข้ามโดเมน 12 แบบ → **เลือก context เดียวเงียบ ๆ ทุกข้อ**; ข้อที่มีคำว่า "ค่าใช้จ่าย" ไป `expense`/`feed_expense` เสมอ เพราะ keyword ซ้อนกัน (`ค่า` + `ค่าใช้จ่าย` + `จ่าย` = 3 คะแนนจากคำเดียว) — รวมถึง "รายได้ ค่าใช้จ่าย และกำไรของกลุ่มธุรกิจ" ที่ควรไป `pl_costtype`

LLM จริง 8 ข้อ (key จำลองของ workspace `nt-report`, สำเนา config; P50 8.0 s):

| คำถาม | context | ผล |
|---|---|---|
| รายได้และค่าใช้จ่ายเดือน ก.ค. 2569 | feed_expense | ❌ ตอบค่าใช้จ่ายอย่างเดียวใต้หัวข้อ "สรุปรายได้และค่าใช้จ่าย" — ไม่บอกว่าขาดรายได้ |
| รายได้ลบค่าใช้จ่ายเดือน ก.ค. 2569 | feed_expense | ❌ `SUM(expense_value_thb) AS "รายได้ลบค่าใช้จ่าย"` (ป้ายผิด) + `time_key = 256907` → NULL → "ไม่มีข้อมูล" |
| อัตราส่วนค่าใช้จ่ายต่อรายได้ | feed_expense | ❌ ตอบค่าใช้จ่ายรวมใต้หัวข้อ "สรุปอัตราส่วน…" |
| ยอดขายกับรายได้ต่างกันเท่าไหร่ | feed_revenue | ⚠️ ตอบรายได้ + บอกว่าไม่มีข้อมูลยอดขาย (ซื่อสัตย์ แต่ข้อมูลมีอยู่ใน `feed_sales`) |
| ยอดขาย ค่าใช้จ่าย EBT ของ 2P10200 | feed_expense | ⚠️ ตอบค่าใช้จ่าย + บอกว่าไม่มียอดขาย/EBT |
| กำไร EBT เดือน ก.ค. และ**รายได้รวม**เดือนเดียวกัน | feed_ebt | ❌ **ผิดแบบมั่นใจ:** "รายได้รวม 1,206.46 ล้านบาท" = รายได้ฐานยอดขายของ 2 สายงานขาย (รายได้รวมจริง 3,274.67 M) |
| รายได้และค่าใช้จ่ายเดือนล่าสุด | feed_expense | ❌ ค่าใช้จ่ายอย่างเดียว |
| EBT สะสมถึง ก.ค. 2569 ของแต่ละสายงาน | feed_ebt | ✅ (แบบ P5 — ทางเลือก 1 ใช้ได้อยู่แล้ว) |

**Baseline: ถูก 1/8; ตอบบางส่วนโดยไม่บอก 4; ป้ายตัวเลขผิด 2; บอกว่าขาดข้อมูล (ทั้งที่มี) 2** — ไม่พบการ "แต่งตัวเลข" ขึ้นเอง แต่พบการ**เรียกตัวเลขของโดเมนหนึ่งด้วยชื่อของอีกโดเมน** ซึ่งอันตรายเท่ากัน

## 2. แผนย่อย + exit criteria (เสนอ)

| ข้อ | ทำอะไร | Exit (วัดได้) |
|---|---|---|
| 3 | **ทางเลือก 1:** P5–P7 ไป context ที่รวมมาแล้วให้ถูก — keyword ของ context เป็นข้อมูลใน DB (แก้ผ่าน admin / default ของ `datafeed_knowledge` สำหรับ context ใหม่); คะแนน router ไม่นับ keyword ที่ซ้อนกันในคำเดียวซ้ำ; ข้อเสนอถึง NT-Report สำหรับ P8 | golden 63 ข้อ + marker 13 แบบ route เหมือนเดิม; "รายได้ ค่าใช้จ่าย และกำไรของสายงานขาย 1" → `feed_ebt` |
| 4a | **ตรวจหาคำถามข้าม context แบบ deterministic:** context ที่มี keyword **เฉพาะตัว** (ไม่มี context อื่นใน workspace เดียวกันและในสิทธิ์ของผู้เรียกใช้คำเดียวกัน) โผล่ในคำถาม ≥ 2 context = ผู้สมัคร; ผู้เรียกระบุ `context` เอง / มี history = เส้นทางเดิมเสมอ | test: marker ร่วม (`feed`, `dashboard`) ไม่ทำให้เป็นคำถามข้าม context; context นอก allowlist ไม่เป็นผู้สมัครและไม่เข้า prompt |
| 4b | **แตกคำถาม (LLM 1 call, โมเดล cheap):** เห็นแค่คำถาม + ชื่อ/คำอธิบายของ context ผู้สมัคร → `[{context, question}]` + `operation` (`none` / `ratio` / `difference` + ลำดับตัวตั้ง); ตรวจผลแบบ deterministic: context ⊆ ผู้สมัคร, ≤ จำนวนผู้สมัคร, ตอบว่า context เดียวพอ = เส้นทางเดิม; รันภายใต้ `RequestPolicy` = policy เข้มสุด + intersection ของ provider allowlist (ว่าง = ปฏิเสธ) | test: output ที่อ้าง context นอกผู้สมัคร = ปฏิเสธทั้งคำถาม; allowlist ไม่ตัดกัน = 403 ก่อนเรียก provider |
| 4c | **รันคำถามย่อยผ่าน `QueryEngine.query` เดิม** (context ระบุชัด, scope / allowed_contexts / channel เดิม) — ขนานกัน | test: scope ที่ context หนึ่งไม่ประกาศ → ตามที่เจ้าของตัดสิน; 403 ของข้อย่อย = 403 ทั้งคำถาม |
| 4d | **รวมคำตอบด้วย template ใน code — ไม่เรียก LLM** (ทุก policy): ต่อส่วน = context, คำถามย่อย, คำอธิบายของข้อย่อย (ผลิตภายใต้ policy ของ source นั้นแล้ว), SQL, `data_as_of`; คำนวณ `ratio`/`difference` ใน code เฉพาะเมื่อทุกส่วนได้ผลเป็นค่าเดียว **และ**งวดล่าสุดของ source เท่ากัน; งวดไม่เท่า = บรรทัดเตือน; ส่วนใดล้ม = บอกว่าส่วนนั้นตอบไม่ได้ + ไม่คำนวณ | **test sentinel ที่ขอบ HTTP:** source A = `full`, B = `schema_only` → ไม่มีค่าของ B ใน request ใดเลย; ส่วนที่ล้ม → ไม่มีตัวเลขของส่วนนั้นและไม่มีผลคำนวณ |
| 4e | ช่องทาง: `/api/v1/query` ก่อน (stateless; chat เก็บ `context_name` ไว้ใช้กับ follow-up — context แบบ "a+b" จะพาคำถามถัดไปตก legacy DB); response เพิ่ม `parts[]` (context, question, sql, answer, row_count, data_as_of, error); flag `admin_config` default OFF | flag ปิด = response เหมือนเดิมทุก byte (test); audit: แถวแม่ + แถวลูกโยงด้วย `request_group` |
| 5 | eval ข้ามโดเมน: โหมดใหม่ใน `scripts/eval/run_eval.py` (`--cross-domain <json>`) — ต่อข้อ = รายการ (context, expected SQL) + ผลคำนวณที่คาด หรือ "ต้องตอบไม่ได้"; ใช้ `match_status` / report เดิม | **≥ 8/10**, ข้อที่ตอบไม่ได้บอกว่าไม่ได้; eval รายโดเมน 14/12/12/35 ไม่ลด; P50/P95 แยก |
| — | review อิสระ (agent แยก อ่านอย่างเดียว) ก่อนปิดข้อ 4 | ไม่เหลือ critical/high |

ไม่ทำ (YAGNI จนกว่าจะมีเหตุ): cache ของคำตอบรวม (ข้อย่อยมี cache ของตัวเองที่ผูก scope + allowlist + build + policy แล้ว), LLM เขียนบทสรุปรวม, JOIN ข้าม source, ข้าม workspace

### ชุดคำถาม 10 ข้อ (ร่าง — ตัวเลขจาก source ตรง ซึ่งกระทบยอดกับ `control_totals.csv` ที่ dashboard ใช้)

| # | คำถาม | แบบ | คาดหวัง |
|---|---|---|---|
| 1 | รายได้รวมและค่าใช้จ่ายรวมเดือนกรกฎาคม 2569 เท่าไหร่ | P1 | rev 3,274,665,994.46 · exp 4,144,812,053.53 |
| 2 | อัตราส่วนรายได้ต่อค่าใช้จ่ายเดือนสิงหาคม 2569 | P2 | 3,434,072,699.62 ÷ 3,690,470,021.65 = 0.9305 |
| 3 | ยอดขายจริงและรายได้ของกลุ่มธุรกิจ 3.Mobile เดือนกรกฎาคม 2569 | P4 | sales 180,775,231.30 · rev 180,756,888.16 |
| 4 | ยอดขายจริงรวมกับรายได้รวมเดือนกรกฎาคม 2569 ต่างกันเท่าไหร่ | P4 + difference | 3,289,655,675.33 − 3,274,665,994.46 = 14,989,680.87 |
| 5 | รายได้ ยอดขายจริง และค่าใช้จ่ายของศูนย์ต้นทุน 2P10200 เดือนกรกฎาคม 2569 | P3 | 34,020,833.34 · 452,157,846.07 · 46,206,528.85 |
| 6 | ค่าใช้จ่ายและ EBT ของสายงานขายและปฏิบัติการลูกค้า 1 เดือนกรกฎาคม 2569 | P5 (context เดียว) | `feed_ebt`: 827,557,643.30 · −233,166,436.29 |
| 7 | EBT สะสมถึงเดือนกรกฎาคม 2569 และรายได้รวมสะสมทั้งบริษัทถึงเดือนเดียวกัน | P1 (ebt + rev, YTD) | ebt 417,325,628.68 · revenue_ytd 22,631,218,136.75 |
| 8 | รายได้และค่าใช้จ่ายเดือนล่าสุด | P1 (งวดเท่ากัน) | 202608: 3,434,072,699.62 · 3,690,470,021.65 |
| 9 | รายได้รวมและ EBT เดือนล่าสุด | P9 | rev 202608 3,434,072,699.62 · `ebt_month` 202607 −284,046,246.64 **+ คำเตือนงวดไม่เท่ากัน** |
| 10 | กำไรของทั้งบริษัทเดือนกรกฎาคม 2569 | P8 | **ต้องบอกว่าไม่มีตัวเลขทางการ** — ห้ามเสนอ rev − exp หรือ EBT ของ 2 สายงานขายเป็นกำไรทั้งบริษัท |

### ข้อ 3 (ทางเลือก 1) — ลองแล้ว ถอยกลับ (2026-09-19)
ลองแก้คะแนน router ไม่ให้ keyword ที่ซ้อนกันในคำเดียว (`ค่า` ⊂ `ค่าใช้จ่าย` ⊃ `จ่าย`) นับซ้ำ แล้ววัดกับคำถามจริง + golden **989 ข้อ** (router จริง, ไม่มี LLM) ก่อน/หลัง:
เปลี่ยน 26 ข้อ — ดีขึ้น 3 ("ผลดำเนินงาน … รายได้ ค่าใช้จ่าย กำไรขั้นต้น และ ebt" ของ key `nt-report` → `feed_ebt`), **แย่ลง 14** (คำถามค่าใช้จ่าย "รายฝ่าย/หน่วยงาน" 8 ข้อ → `transfer price` เพราะ keyword `ฝ่าย`/`หน่วยงาน` ของมัน; "กำไรขั้นต้น" 6 ข้อ → `revenue` เพราะ `กำไร` ⊂ `กำไรขั้นต้น` และ `revenue` priority สูงกว่า `pl_costtype`), ที่เหลือคือคำถามข้ามโดเมนที่ย้ายจาก context ผิดตัวหนึ่งไปอีกตัว
→ การนับซ้ำเป็นสิ่งที่ค้ำ routing ของ workspace `default` อยู่ — แก้ที่สูตรคะแนน = เปลี่ยนพฤติกรรมของคำถาม context เดียว (ขัดกติกา) → **revert, ไม่มี code เปลี่ยน**
- P5–P7 ที่ใช้คำของโดเมนเดียว ("EBT สะสมของแต่ละสายงาน", "ผลดำเนินงาน…") route ถูกอยู่แล้ว; ข้อที่ปนคำของหลายโดเมน ("ค่าใช้จ่ายและ EBT ของสายงานขาย 1") ต้องพึ่งขั้นตรวจผู้สมัครของ orchestrator (ข้อ 4a–4b: ตัวแตกคำถามตอบได้ว่า "context เดียวพอ")
- งานแยกที่ควรทำ (ไม่ใช่ของ phase นี้): ทำความสะอาด keyword ของ workspace `default` (`ฝ่าย`, `หน่วยงาน`, `owner`, `user` ของ `transfer price`; `กำไร`/`profit` ของ `revenue`) พร้อมวัดด้วยชุด 989 ข้อนี้ — ทำผ่าน admin UI ได้ ไม่ต้องแก้ code

## 3. ข้อที่เสนอให้เจ้าของตัดสิน — **รับข้อเสนอทุกข้อ (2026-09-19)**

| # | เรื่อง | ข้อเสนอ |
|---|---|---|
| Q1 | ชุด 10 ข้อ + ตัวเลขอ้างอิง: ใครให้ / หน้าไหนคือ "ความจริง" | ใช้ชุดร่างข้างบน; ความจริง = `control_totals.csv` ของแต่ละโดเมน (ชุดเดียวกับที่ dashboard ของโดเมนนั้นกระทบยอด) + Forecast Dashboard (ratio) + OrgReport ภาคผนวก ก (หน่วยงาน) |
| Q2 | ขอบเขต | ทั้งสองทาง: ทางเลือก 1 ครอบ P5–P7; **P1–P4, P9 ต้อง orchestrator** (ไม่มีชุดที่รวมไว้ และ dashboard จริงก็วางข้างกัน/หารกันเอง) |
| Q3 | ข้าม workspace | ไม่ได้ — ผู้สมัครต้องอยู่ workspace เดียวกัน |
| Q4 | `scope` ที่ context หนึ่งไม่ประกาศ | 400 ทั้งคำถาม (ตรง Phase 3) |
| Q5 | งวดของ source ไม่เท่ากัน | ตอบ + บอกงวดของทุกตัวเลข + บรรทัดเตือน; **ไม่คำนวณข้ามโดเมน**เมื่องวดล่าสุดไม่เท่ากัน |
| Q6 | ขั้นรวมภายใต้ policy ≠ `full` | template ทุกกรณี (ไม่มี LLM ในขั้นรวมเลย) → ข้อนี้หมดไป |
| Q7 | latency / ช่องทาง | `/api/v1/query` ก่อน; เพดานที่เสนอ: P50 ≤ 15 s, P95 ≤ 30 s สำหรับ 2–3 context (แตก ~1.5 s + ข้อย่อยขนานกัน ~6–10 s) |
| Q8 | **ใหม่:** "รายได้ − ค่าใช้จ่าย" ข้ามโดเมน | ratio (dashboard จริงทำ) คำนวณได้พร้อมสูตรและที่มา; **difference ระหว่าง revenue กับ expense ไม่เรียกว่ากำไร/EBT** — แสดงเป็น "ส่วนต่าง (ไม่ใช่ EBT ทางการ)"; คำถามที่ถาม "กำไร" ตรง ๆ ไป `feed_ebt` / บอกว่าไม่มี (P8) |

## 4. สิ่งที่ทำ (ข้อ 4) — `app/services/multi_context.py`

```
/api/v1/query (ไม่ส่ง context) → multi_context.ask
  1. enabled_workspaces   admin_config.multi_context_workspaces (JSON list; อ่านไม่ได้ = ปิด)
  2. candidates           deterministic: context ที่ keyword "เฉพาะตัว" อยู่ในคำถาม — workspace เดียว, ในสิทธิ์ของ key; < 2 = เส้นทางเดิม
  3. _split               LLM 1 call (cheap model) ใต้ RequestPolicy = policy เข้มสุด + intersection ของ provider allowlist
                          เห็น: คำถาม + ชื่อ/คำอธิบาย/keyword ของผู้สมัคร → parse_split ตรวจใน code (context ⊆ ผู้สมัคร, operation, operands)
                          1 ส่วน = ใช้ context นั้นกับคำถามเดิม · ผิดรูป/ล้ม = เส้นทางเดิม (log ERROR)
  4. engine.query × n     ขนานกัน; scope / allowed_contexts / user / key / channel เดิม + request_group
                          ScopeError / ContextNotAllowed / LLMPolicyError ของข้อใด = ปฏิเสธทั้งคำถาม (400 / 403)
  5. compute + combine    ใน code ไม่มี LLM: ที่มาของทุกส่วน (context, คำถามย่อย, งวด), ratio / difference เมื่อทุกส่วนได้ float ตัวเดียว
                          และงวดล่าสุดของ source เท่ากัน, เตือนงวดไม่เท่ากัน, "ตอบได้ k จาก n ส่วน"
  6. audit                แถวแม่ (context_name = a+b) + แถวลูก ใช้ request_group เดียวกัน
```
- เปิด/ปิด: `PUT /admin/workspaces/{id}/multi-context` (`GET /admin/workspaces` แสดงสถานะ) — config จริง**ยังไม่ได้เปิด** (เปิดเฉพาะบนสำเนาที่ใช้วัด)
- response: `parts[]` (context, question, answer, row_count, error, data_as_of, + sql / data เมื่อขอ) + `computed` — `docs/PORTAL_INTEGRATION.md`
- `QueryEngine._provider_for` แยกจาก `_execute_query` (ย้าย code เดิม) ให้การเลือก provider ตาม allowlist ใช้ชุดเดียวกัน; `query(request_group=…)`
- ไม่ทำ (ตามแผน): cache ของคำตอบรวม, LLM สรุปรวม, JOIN ข้าม source, ข้าม workspace, chat / telegram

## 5. Eval ข้ามโดเมน (ข้อ 5) — `python -m scripts.eval.run_eval --cross-domain scripts/eval/cross_domain_golden.json`

ต่อข้อ: SQL ตรวจมือต่อ context รันกับ source ตอน eval (ไม่ฝังตัวเลข — build ใหม่ไม่ทำให้ golden เสีย) → ข้อถูกเมื่อ**ทุก**ตัวเลขที่คาดอยู่ในผลลัพธ์**แถวเดียว**ของส่วนที่มาจาก context ที่ยอมรับ + ผลคำนวณตรง + มีคำเตือนงวด (เมื่องวดต่าง) / ข้อ "ต้องตอบไม่ได้" ถูกเมื่อไม่มีตัวเลข

| # | คำถาม | baseline | รอบ 1 | รอบ 2 | รอบ 3 |
|---|---|---|---|---|---|
| 1 | รายได้รวมและค่าใช้จ่ายรวม ก.ค. 2569 | ❌ | ✅ | ✅ | ✅ |
| 2 | อัตราส่วนรายได้ต่อค่าใช้จ่าย ส.ค. 2569 (= 0.9305) | ❌ | ✅ | ✅ | ✅ |
| 3 | ยอดขายจริงและรายได้ของ 3.Mobile | ❌ | ✅ | ✅ | ✅ |
| 4 | ยอดขายจริงรวมกับรายได้รวม ต่างกันเท่าไหร่ (= 14,989,680.87) | ❌ | ✅ (106 s) | ✅ | ✅ |
| 5 | รายได้ / ยอดขาย / ค่าใช้จ่ายของศูนย์ต้นทุน 2P10200 (3 context) | ❌ | ✅ | ✅ | ✅ |
| 6 | ค่าใช้จ่ายและ EBT ของสายงานขาย 1 | ❌ | ✅ | ✅ | ✅ |
| 7 | EBT สะสม + รายได้รวมสะสมทั้งบริษัท | ❌ | ✅ | ✅ | ✅ |
| 8 | รายได้และค่าใช้จ่ายเดือนล่าสุด | ❌ | ✅ | ✅ | ✅ |
| 9 | รายได้รวมและ EBT เดือนล่าสุด (งวดต่างกัน) | ❌ | ❌ | ❌ | ✅ |
| 10 | กำไรของทั้งบริษัท (ต้องตอบว่าไม่มี) | ❌ | ❌ | ❌ | ❌ |
| | **รวม** | **0/10** | **8/10** | **8/10** | **9/10** |
| | P50 / P95 (s) | 6.3 / 9.5 | 9.2 / 106.4 | 8.9 / 11.5 | 7.8 / 12.1 |

- ข้อ 9 (รอบ 1–2): คำถามย่อย "EBT เดือนล่าสุด" ได้ `ebt_month` **รายสายงาน 2 แถว** (−233.17 M, −50.88 M) แทนยอดรวม −284.05 M — ตัวเลขถูก แต่ไม่ใช่ยอดที่ถาม; เป็นพฤติกรรมของ context `feed_ebt` เอง (main view = ตารางรายสายงาน)
- ข้อ 10: `SUM(ebt_month)` ของ 2 สายงานขาย แล้วอธิบายว่า "กำไรสุทธิรวมของบริษัท −284.05 ล้านบาท" — ผิดแบบมั่นใจ, context เดียว, ไม่ผ่าน orchestrator → §7 ข้อ 1
- รอบ 1–2 ให้คะแนนด้วยเกณฑ์เดิม (ตัวเลขอยู่ในแถวใดก็ได้); รอบ 3 ใช้เกณฑ์แถวเดียว — baseline 0/10 ไม่เปลี่ยนภายใต้เกณฑ์ใด

## 6. Review อิสระ (agent แยก อ่านอย่างเดียว, บน `3e7c80e` + `d0f22cb`)

**ไม่พบ critical / high.** Medium — แก้แล้ว `d07f397`:
- M1 `_scalar` รับ int ตัวเดียวในแถวเป็น measure (`SELECT month` แถวเดียว → ถูกนำไปหาร) → นับเฉพาะ **float ตัวเดียว** (ไม่รับ int / bool / NaN / inf) + test
- M2 eval ให้คะแนนหลวม — ตัวเลขที่คาดอยู่ใน cell ใดของ breakdown ก็ผ่าน → นับเฉพาะผลลัพธ์แถวเดียว
- M3 `_split` ล้ม (source resolve ไม่ได้ / provider ล่ม) → fallback ไปเส้นทาง context เดียว = อาการเดียวกับ bug ที่ feature นี้แก้ → คง fallback (ความล้มของตัวแตกไม่ใช่ความผิดของผู้เรียก) แต่ log เป็น **ERROR**

Low: L1 race ของ lazy `ALTER TABLE` ระหว่างสอง process (เสีย audit 1 แถว + log ERROR; แบบเดียวกับ `ensure_api_key_columns`) — รับไว้; L2 docstring พูดถึง history ที่ `ask()` ไม่รับ → แก้ docstring

ยืนยันว่าถูก: `generate_structured` + `generate_content` อยู่ใต้ `guard_call` ทั้งคู่ และ ContextVar ถูก reset ใน `finally`; policy เข้มสุด + intersection (ว่าง = ปฏิเสธก่อนเรียก); `_provider_for` ไม่คืน provider นอก allowlist แม้ผ่าน fallback; provider instance สร้างใหม่ทุกครั้ง (สลับ cheap model ไม่กระทบ request อื่น); `candidates` (ชื่อจริงตรงตัว, NULL = default, workspace ที่ปิดไม่นับ); resolve แบบไม่มี scope ใน `_split` อ่านแค่ policy; `asyncio.gather` = Task แยก → ContextVar ของคำถามย่อยไม่ปนกัน; refusal ของข้อย่อย → 400/403 ผ่าน `_find_refusal`; ไม่มี provider call ใน `combine` / `compute`; `sql` / `data` ของ `parts` ไม่ออกถ้าไม่ขอ; audit + DSR ครอบแถวแม่; flag ปิด = config read 1 ครั้งแล้วเส้นทางเดิม; session ที่ใช้ร่วมกันระหว่างคำถามย่อย (audit เขียนด้วย Session ใหม่ต่อครั้ง)

## 7. ข้อเสนอถึง NT-Report (ฉบับเต็มอยู่ใน `plan/PROMPT_NT_REPORT_P7.md` หัวข้อ Phase 5)
- P8: ไม่มีชุด "ผลดำเนินงานทั้งบริษัท / ทุกสายงาน" ใน DataFeed — `feed_ebt` = 2 สายงานขาย; ถ้า portal ต้องตอบ "กำไรทั้งบริษัท" ต้องมี dataset ทางการจากต้นทาง (ฝั่ง AI จะไม่คำนวณเอง)
- ชื่อสายงานของ revenue ต่างจาก expense/ebt 1 ชื่อ (`กรรมการผู้จัดการใหญ่` vs `… บมจ.เอ็นที`) — ถ้าจะให้เทียบรายสายงานข้ามโดเมนด้วยชื่อ ควรใช้ชื่อชุดเดียวกัน หรือประกาศรหัสสายงานร่วม
- sales ไม่มีสายงาน (มีแต่สายการขาย) → คำถาม "ยอดขายของสายงาน X" เทียบกับรายได้/ค่าใช้จ่ายของสายงานเดียวกันได้เฉพาะผ่าน `cost_center`
- ebt `group_1` ใช้ `03.Mobile` ขณะที่ revenue/sales ใช้ `3.Mobile`

## 8. สถานะ DB จริง
`config.db` / `app.db` จริง**ไม่ถูกแตะ** (ทุกการวัดใช้สำเนาใน scratchpad ที่ migrate แล้ว) — multi-context ยัง**ปิด**ทุก workspace; migration ของ Phase 4.5 ยังไม่ได้รันบน DB จริง (ข้อค้างเดิม — Phase 5 ไม่ต้องการ migration เพิ่ม: `query_audit.request_group` เพิ่มเองเมื่อใช้ครั้งแรก)

## 9. ค้าง / ข้อสังเกต
- **เปิดใช้จริงกับ `nt-report`** = เจ้าของตัดสิน (`PUT /admin/workspaces/{id}/multi-context`) — แนะนำหลัง NT-Report รับข้อเสนอ §7 ข้อ 1 (กำไรทั้งบริษัท)
- chat / telegram: ต้องออกแบบ follow-up ของคำตอบหลาย context ก่อน (chat เก็บ `context_name` เดียวให้คำถามถัดไป; `a+b` จะตก legacy DB)
- workspace `default`: keyword ปนกัน (`ฝ่าย`/`หน่วยงาน` ของ `transfer price`, `กำไร` ของ `revenue`) → เปิด multi-context แล้วคำถาม context เดียวจำนวนมากจะถูกส่งไปแตก; ทำความสะอาด keyword ก่อน (วัดด้วยชุด 989 ข้อ)
- คำถามซ้ำภายใน 5 วินาที → คำถามย่อยโดน dedup ("คำถามซ้ำ" ต่อส่วน); ไม่มี dedup ระดับคำถามแม่
- คำอธิบายของแต่ละส่วนยังเป็นของ LLM ต่อข้อย่อย (ภายใต้ policy ของ source นั้น) — คำตอบรวมยาว; template สั้นต่อส่วน (`template_answers_enabled`) ช่วยได้เมื่อเปิด
- ข้าม context ด้วยชื่อสายงาน / กลุ่มธุรกิจของ ebt ยังพึ่งการสะกดของแต่ละโดเมน (§1b) — `cost_center` เป็น key เดียวที่ตรงกันทั้ง 4 โดเมน

## Commits
```
3ef27ad docs(P7-5): survey of cross-context questions, contract comparability, baseline of today's router; sub-plan and exit criteria
0cc8304 docs(P7-5): option 1 measured on 989 real questions - de-duplicating overlapping router keywords regresses single-context routing, reverted
3e7c80e feat(P7-5): questions across contexts - split per context, sub-questions through QueryEngine.query, answers combined by code
d0f22cb feat(P7-5): eval of questions across contexts - run_eval --cross-domain, 10 questions scored against each source
d619350 feat(P7-5): admin switches questions across contexts on and off per workspace
d07f397 fix(P7-5): review - only a float is a part's measure; a failed split is logged as an error; the eval counts a number only in a one-row result
```
