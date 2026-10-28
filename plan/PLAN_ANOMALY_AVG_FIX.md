# PLAN — คำถาม "หน่วยงานไหนผิดปกติจากค่าเฉลี่ยก่อนหน้า": AVG ต่อแถว, ปีของเดือนที่ไม่ระบุปี, ตัวเลขในคำบรรยาย, ลำดับคอลัมน์บน portal

> เขียน 2026-10-28 จากการตรวจคำตอบจริงบน portal (รายงานยอดขาย งวด ก.ย. 2569) — **ยังไม่ได้แก้โค้ดใด ๆ**
> สั่งงานบน local: ฝั่ง AI → [`PROMPT_ANOMALY_AVG_FIX_AI.md`](PROMPT_ANOMALY_AVG_FIX_AI.md) · ฝั่ง NT-Report → [`PROMPT_ANOMALY_AVG_FIX_NT_REPORT.md`](PROMPT_ANOMALY_AVG_FIX_NT_REPORT.md)
> ผลทุก phase บันทึกที่ `plan/RESULT_ANOMALY_AVG_FIX.md` (session ที่ทำงานสร้างเอง) · เครื่องมือตรวจ/เฉลย: `scripts/eval/check_anomaly_avg.py` (อ่านอย่างเดียว)
> ลำดับ: **0 → 1 → (2 ตามผล Phase 0) → 3 → 4** · Phase 5 เลื่อนได้ (ข้อตัดสิน D-5)

---

## 0. ข้อห้ามและสภาพแวดล้อม (เหมือน `PLAN_METRICS_CONVERGENCE.md` §0)

- server จริงรัน `uvicorn --reload` จาก working tree ของ `main` (`/Users/seal/Documents/GitHub/AI`) — แก้ `.py` ใน main = ขึ้นของจริงทันที
  → ทำงานใน worktree ใหม่ (เช่น `/Users/seal/Documents/GitHub/_worktrees/AI-anomaly`) บน branch จาก `main`; ขึ้นของจริง = ff `main` หลังเจ้าของสั่งเท่านั้น
- ฝั่ง AI อ่าน contract ที่ `NT-Report/DataFeed/contracts/*.yaml` และ re-sync เองทุก request → แผนนี้**ไม่แก้ contract** (§10)
- ทดลองบนสำเนาเท่านั้น: สำเนา `config.db` / `app.db` / Chroma (เช่น `.ai/db/<ชื่อรอบ>/`), server ซ้อม port 8001+, key ซ้อมที่สร้างบนสำเนา —
  **ห้าม port 8000, ห้าม API key id 4 (portal) และ id 5 (Claude Desktop)**
- pytest ใช้ `venv/bin/python3.14`; server / eval ใช้ `venv/bin/python` (3.10, มี RAG)
- Acceptance ทุก slice = **ACC-T** และ **ACC-L** ตาม `PLAN_METRICS_CONVERGENCE.md` §0 (รันจาก root ของ worktree)

---

## 1. เหตุการณ์และหลักฐาน

คำถามบน portal (รายงานยอดขาย งวด 2569-09 → hook ส่ง `context = feed_sales`, `scope.year_month` = 202501…202609 รวม 21 ค่า, `source = portal`):
**"เดือน กันยายน มีรายได้ของหน่วยงานไหน ผิดปกติไปจากค่าเฉลี่ยก่อนหน้าบ้าง"**

คำตอบที่ได้: ตาราง 88 แถว (portal แสดง 20 แถว) หัวคอลัมน์ `รายได้เฉลี่ยก่อนกันยายน | รายได้เดือนกันยายน | ส่วนต่างรายได้ | หน่วยงาน | เปอร์เซ็นต์เปลี่ยนแปลง`
เช่น ฝ่ายธุรกิจลูกค้าภาครัฐ 1,656,934.61 → 1,113,223,812.81 (+67,085.74%) และคำบรรยายว่า "กันยายน 2568 … เทียบ ม.ค.–ส.ค. 2568",
"ฝ่ายขายฯ หลายภูมิภาค รายได้เพิ่มขึ้นหลายหมื่นล้านบาท", "หน่วยงานส่วนใหญ่รายได้เพิ่มขึ้นอย่างมาก" พร้อมหัวข้อ "ข้อเสนอแนะการแสดงผล"

SQL ที่เจ้าของดึงมาจากระบบ (คำถามเดียวกัน) อยู่ใน Appendix B

| # | สิ่งที่พบ | หลักฐาน | ความมั่นใจ |
|---|---|---|---|
| **F1** | "ค่าเฉลี่ยก่อนหน้า" = `AVG(amount)` บนแถวดิบของ `fact_sales` (grain = `year_month × cost_center × product_code × metric × sales_line`) = เฉลี่ย**ต่อแถว** แต่ยอดกันยายน = `SUM(amount)` = ยอด**ทั้งเดือน** → อัตราส่วนแปรตามจำนวนแถว ไม่ใช่การเปลี่ยนแปลง | SQL ใน Appendix B · ก.ย./ค่าเฉลี่ย ของหน่วยใหญ่: ภาครัฐ 672 เท่า, ภาคเหนือตอนล่าง 319, ภาคอีสานตอนล่าง 266, ลูกค้าเอกชน 194, ภาคตะวันออกตอนบน 144, ผู้ประกอบการ 105 · ระดับบริษัท BG 1–7: ก.ย. 69 = 3,149.82 ล้าน vs เฉลี่ย ม.ค.–ส.ค. = (27,317.01 − 3,149.82)/8 = 3,020.90 ล้าน → **+4.3%** (`RESULT_METRICS_CONVERGENCE.md` §SALES.2, ตรง `NT_Sales_Report_Workbook_202609`) · จำลองด้วยข้อมูลสังเคราะห์: หน่วยที่ยอดคงที่ (600 แถว/เดือน, เปลี่ยนจริง −0.13%) SQL นี้ให้ **+59,822%** | ยืนยันแล้ว |
| **F2** | ไม่มีเกณฑ์ "ผิดปกติ" — `ABS(ส่วนต่าง) > 0` คืนทุกหน่วย | SQL · 88 แถว | ยืนยันแล้ว |
| **F3** | หน่วยที่ยอด ก.ย. หายเป็น 0 และหน่วยใหม่ที่เพิ่งมียอดใน ก.ย. หายไปจากผล (`LEFT JOIN … WHERE a.avg IS NOT NULL` ตั้งต้นจากหน่วยที่มียอด ก.ย.); เดือนที่ไม่มีแถวไม่ถูกนับเป็น 0 | SQL · จำลอง: หน่วย −100% และหน่วยใหม่ไม่อยู่ในผล | ยืนยันแล้ว |
| **F4** | คำบรรยายเขียน "2568" — ถ้า SQL ของรอบนั้นใช้ 2569 `thai_year.fix_explanation` จะแก้ 2568 → 2569 ให้เอง (จำลองกับข้อความจริงแล้ว: SQL 2569 → แก้เป็น 2569, SQL 2568 → คง 2568) → **รอบที่ได้ตารางนี้น่าจะใช้งวด 202501–202509** = ผิดกฎ "เอ่ยเดือนแต่ไม่ระบุปี → งวดอ้างอิง 202609" ซึ่งมีแค่ใน prompt (`hybrid_flow._period_rules`) ไม่มี code บังคับ — scope ของ portal มีเดือนกันยายนสองครั้ง (202509, 202609) | จำลอง `fix_text` + `answer_years` | **ต้องยืนยันใน Phase 0** |
| **F5** | "เพิ่มขึ้นหลายหมื่นล้านบาท" ผิดขนาด — ส่วนต่างในตารางของฝ่ายขายภาคอยู่ที่ 50.47–100.96 ล้านบาท (เอา "หลายหมื่น %" ไปเขียนเป็นบาท); ไม่มีอะไรตรวจตัวเลขในคำบรรยายกับผลลัพธ์ | ตาราง | ยืนยันแล้ว |
| **F6** | เรียก "รายได้" ทั้งที่เป็นยอดขาย (contract `sales_is_not_revenue`) — note "แหล่งข้อมูลอาจไม่ตรงกับคำถาม" (`chat._context_mismatch`) ทำงานเฉพาะ `/api/v1/chat` ไม่ทำงานบน `/api/v1/query` ที่ portal/MCP ใช้ | โค้ด `app/api/v1/chat.py:260`, `app/api/v1/query.py` | ยืนยันแล้ว |
| **F7** | คำบรรยายเรียกหน่วยที่ยอดหลักร้อยบาท (612, 920 บาท) ว่า "ลดลงอย่างมีนัยสำคัญ"; มีหัวข้อ "ข้อเสนอแนะการแสดงผล" ทั้งที่ prompt ห้าม (`chart_postprocessor.build_explain_prompt`) | ข้อความคำตอบ | ยืนยันแล้ว (ที่มาของหัวข้อ viz รอ Phase 0) |
| **F8** | portal เรียงคอลัมน์ตามตัวอักษร ไม่ใช่ลำดับใน SQL — หัวตาราง = เรียงตาม Unicode พอดี (รายได้เฉลี่ย… < รายได้เดือน… < ส่วนต่าง… < หน่วยงาน < เปอร์เซ็นต์…); `assistant.pb.js` ส่ง `payload.data` (ผ่าน `res.json` ของ Go) ต่อด้วย `e.json` → key ของ map ถูก Go เรียง; `ask.js` ใช้ `Object.keys(rows[0])`; AI ไม่ส่งลำดับคอลัมน์มาใน response | NT-Report `pocketbase_0/pb_hooks/assistant.pb.js:264,324`, `pb_public/assets/ask.js:98,117` · test ของ hook ใช้ JS object จึงไม่เห็น | สูงมาก (ยืนยันบน PocketBase จริงใน Phase 0 / prompt NT-Report) |
| **F9** | SQL ที่เจ้าของแปะกับตารางมาจาก**คนละรอบ** — alias ใน SQL = "ยอดขาย…" แต่หัวตาราง = "รายได้…", และแถวในตารางไม่ได้เรียงตาม `ORDER BY ABS(ส่วนต่าง) DESC` (แถวเป็น array — portal ไม่สลับ) | เทียบ SQL กับตาราง | ยืนยันแล้ว |
| **F10** | ช่องในตัวตรวจ: `hybrid_flow.cumulative_sum_error` คืน `None` ทันทีเมื่อ context ไม่มีคอลัมน์ point-in-time → **feed_sales ไม่เคยผ่าน `sql_invariants` เลย**; SQL จาก tool-loop rescue (`escalation_tool_loop_enabled`) ไม่ผ่าน invariant | `hybrid_flow.py:130-136`, `:1445-1458` | ยืนยันแล้ว |

ต้นเหตุร่วมของ F1–F3 ที่น่าจะเป็น (ยืนยันจาก intent ใน log ที่ Phase 0 ข้อ 2): pass 1 มี `aggregate_function: AVG` ใน `INTENT_SCHEMA` และ pass 2
ถูกสั่งให้ยึด intent → เขียน `AVG(<measure>)` ตรงบนตาราง fact; และไม่มี invariant ใดรู้ว่าตาราง fact เป็นระดับรายการ (grain ใน contract `datasets[].keys`)

---

## 2. ข้อตัดสินที่เจ้าของต้องเคาะ

| # | เรื่อง | ทางเลือก | แนะนำ |
|---|---|---|---|
| **D-1** | "ค่าเฉลี่ยก่อนหน้า" เมื่อคำถามไม่ระบุช่วง | (ก) ม.ค. ถึงเดือนก่อนเดือนที่ถาม ของปีเดียวกัน · (ข) 12 เดือนก่อนหน้า · (ค) 3 เดือนก่อนหน้า | **(ก)** — ตรงกับที่ผู้ใช้และระบบอ่านอยู่แล้ว; ใช้ใน Phase 3 (กฎคำบรรยาย) และ Phase 5 |
| **D-2** | เกณฑ์ "ผิดปกติ" ค่าเริ่มต้น | (ก) ส่วนต่าง ≥ 5 ล้านบาท **และ** (≥ 30% หรือ ≥ 2 SD ของเดือนก่อนหน้า) · (ข) z-score อย่างเดียว · (ค) ไม่กรองใน SQL — แสดงทุกหน่วยเรียงตามส่วนต่าง แล้วคำบรรยายเลือกเฉพาะที่เกินเกณฑ์ | **(ค) สำหรับ free SQL + เกณฑ์ (ก) ในคำบรรยาย** — ไม่ต้องเขียนกฎลง prompt ของ SQL (ประสบการณ์: กฎข้อความทำคำถามอื่นถดถอย — `PROMPT_RESEARCH_DECLARED_METRICS.md` §2); เกณฑ์ (ก) ใช้ใน Phase 5 |
| **D-3** | ถาม "รายได้" บน context ยอดขาย (เช่น รายงานยอดขาย) | (ก) ตอบจากยอดขาย เรียกว่า "ยอดขาย" + บอกหนึ่งบรรทัดว่าไม่ใช่รายได้ · (ข) ไม่ตอบ แนะนำให้ถามจากรายงานรายได้ | **(ก)** |
| **D-4** | คำบรรยายมีจำนวนเงินที่ผลลัพธ์ไม่รองรับ (Phase 3.1) หลังถามซ้ำ 1 ครั้งแล้วยังผิด | (ก) แทนด้วยคำบรรยายที่ code สร้างจากแถว (ตัวเลขไม่ผ่าน LLM) · (ข) คงข้อความ LLM + บรรทัดเตือน | **(ก)** |
| **D-5** | ทำ Phase 5 (metric ยอดขาย + compiler รูป "เทียบค่าเฉลี่ย") ตอนนี้ไหม | (ก) เลื่อน — ทำเมื่อ `query_audit` แสดงว่าคำถามรูปนี้ถามบ่อย · (ข) ทำต่อจาก Phase 4 | **(ก)** |
| **D-6** | I4 บน context ที่ไม่รู้ grain (legacy ไม่มี contract) | (ก) ไม่ตรวจ (no-op) · (ข) ตรวจแบบเดา: AVG ของ measure ข้ามหลายงวดโดยไม่ GROUP BY งวด | **(ก)** — ไม่มี grain = ไม่รู้ว่าแถวคืออะไร เดาแล้ว false positive |

**เคาะแล้ว 2026-10-28 (เจ้าของ — ตามที่แนะนำทุกข้อ):** D-1 = ก · D-2 = ค + เกณฑ์ ก ในคำบรรยาย · D-3 = ก · D-4 = ก · D-5 = ก (เลื่อน Phase 5) · D-6 = ก

---

## 3. Phase 0 — ตรวจหลักฐาน (อ่านอย่างเดียว, ไม่แก้อะไร)

1. **หา audit ทั้งสองรอบ** ใน `app.db` ของ server จริง (อ่านอย่างเดียว — `sqlite3 -readonly` หรือสำเนา):
   ```sql
   SELECT id, created_at, channel, context_name, metric_path, cache_hit, row_count, error,
          result_columns, scope, sql_query
   FROM query_audit
   WHERE question LIKE '%ผิดปกติ%' AND question LIKE '%ค่าเฉลี่ย%'
   ORDER BY id DESC LIMIT 20;
   ```
   - รอบที่ได้ตารางที่แปะ: `channel = 'portal'`, `row_count = 88`, `result_columns` มี "รายได้เฉลี่ยก่อนกันยายน"
   - บันทึก: งวดใน `sql_query` ของรอบนั้น (2025 หรือ 2026) → ตัดสิน **F4** (ทำ Phase 2 แบบไหน)
   - เทียบลำดับใน `result_columns` (= ลำดับของ SQL) กับหัวตารางบน portal → ยืนยัน **F8**
2. **log ของ request นั้น** (บรรทัด `query_trace` JSON เดียวต่อ request ใน log ของ server, ค้นด้วยเวลา/คำถาม): `attempts`, `stages`
   (`invariant`, `explain`, `escalated_to`), retry history — ดูว่าคำบรรยายมาจาก `build_explanation` ตามปกติหรือทางอื่น (cache / tool loop / multi-context)
   และค่า `escalation_tool_loop_enabled` ใน admin config
3. **รันเฉลย** (อ่านอย่างเดียวจาก view เดียวกับที่ server query):
   ```bash
   cd /Users/seal/Documents/GitHub/AI   # หรือ worktree — ใช้ .source_cache ของ server จริงได้ เปิดแบบ read-only
   venv/bin/python scripts/eval/check_anomaly_avg.py --db "$(ls -t .source_cache/datafeed_sales-*.duckdb | head -1)"
   ```
   - ข้อ 1 ต้องได้ "เฉลี่ยต่อแถว" ≈ **1,656,934.61** และ "ยอดเดือนที่ถาม" = **1,113,223,812.81** ในปีใดปีหนึ่ง (202609 หรือ 202509) → ยืนยัน F1 + ปีของรอบนั้นซ้ำอีกทาง
   - ข้อ 2 ยอดรายเดือนทั้งบริษัท (ก.ย. ไม่ควรกระโดด) · ข้อ 3 = **คำตอบที่ถูก** ของคำถามนี้ (เก็บทั้งตารางไว้ใน RESULT เป็น oracle ของ Phase 1)
   - รันซ้ำด้วย `--by unit_fname_current` — หน่วยที่ผิดปกติเฉพาะกับ `unit_fname` = ผลของการย้ายศูนย์ต้นทุนระหว่างปี (contract `current_section_columns`)
4. เขียน `plan/RESULT_ANOMALY_AVG_FIX.md` §0: audit id ทั้งสองรอบ, งวดใน SQL, ทาง explain, F8 ยืนยัน/ไม่, ตาราง oracle
   - **หยุดถามเจ้าของ** ถ้าผลขัดกับ §1 (เช่น SQL ของรอบที่ได้ตารางไม่ได้ใช้ AVG ต่อแถว)

---

## 4. Phase 1 — invariant **I4 `avg_over_fact_rows`** (AI) — แก้ F1, F10

**ไฟล์ที่อนุญาต:** `app/services/ai/sql_invariants.py`, `app/services/ai/hybrid_flow.py` (เฉพาะ `cumulative_sum_error` / `invariant_code` /
helper ดึงคอลัมน์), helper อ่าน grain (ดูข้อ 3), `tests/unit/test_sql_invariants.py`, `tests/unit/test_hybrid_invariants.py`,
`tests/unit/test_prompt_scope_note.py`, `scripts/eval/portal_real_questions.json` (เพิ่มคำถามเหตุการณ์),
`docs/DECLARED_METRICS.md` หรือ `docs/ai_workflow.md` (ย่อหน้าอธิบาย invariant)

1. **กฎ (ใน `sql_invariants.check`)** — ใน SELECT node หนึ่ง ถือว่าผิดเมื่อครบทุกข้อ:
   - มี aggregate หรือ window function ในชุด `avg / mean / median / stddev* / var*` (ค่าคงที่ชุดเดียว) ที่อาร์กิวเมนต์อ้างคอลัมน์ใน `summable`
     (`schema_metadata.is_summable = 1`, double) — **หรือ** นิพจน์ `SUM(<summable>) / COUNT(*)` / `COUNT(<col>)` (เฉลี่ยต่อแถวแบบเขียนมือ;
     `COUNT(DISTINCT <period>)` ไม่นับ)
   - FROM ของ node นั้นเป็น **ตารางจริงล้วน** (BASE_TABLE ที่ไม่ใช่ชื่อ CTE) อย่างน้อยหนึ่งตารางรู้ grain keys — FROM ที่มี CTE / subquery ปนอยู่
     = ไม่ตรวจ (checker ไม่มี column lineage จึงไม่รู้ว่าคอลัมน์ในอาร์กิวเมนต์มาจากฝั่งไหน)
   - จำนวน key ของตารางนั้นที่**ไม่ถูกตรึง** > 1 — ตรึง = อยู่ใน GROUP BY, อยู่ใน PARTITION BY ของ window นั้น,
     หรือเงื่อนไข `col = <ค่าคงที่>` / `col IN (<ค่าเดียว>)` ใน WHERE / JOIN ON (ใช้ `_conjuncts` เดิม)
   - ตารางที่ไม่รู้ grain → ไม่ตรวจ (D-6)
   - ตัวอย่าง: SQL ใน Appendix B มี key ไม่ตรึง `{year_month, cost_center, product_code, sales_line}` = 4 → **ผิด**;
     `AVG(revenue) FROM <bu × เดือน> WHERE bu = 'X'` เหลือ `{year_month}` = 1 → ผ่าน; AVG จาก CTE ที่ SUM ต่อเดือนแล้ว → ไม่ตรวจ (FROM เป็น CTE)
   - `Violation("I4", "avg_over_fact_rows", columns, blocking=True)`
2. **ต่อสาย (`hybrid_flow`)**:
   - `cumulative_sum_error` ต้องตรวจ I4 แม้ context ไม่มีคอลัมน์ point-in-time (ตอนนี้ `return None` ก่อน) — I1/I2 คงพฤติกรรมเดิมทุกไบต์
   - ข้อความ retry (ขึ้นต้น `I4 avg_over_fact_rows: `): "`AVG(<col>)` บนแถวดิบของ `<table>` (grain: `<keys>`) = ค่าเฉลี่ยต่อรายการ ไม่ใช่ต่อเดือน/ต่อหน่วย —
     ให้ SUM ต่อ <มิติที่ถาม> × <คอลัมน์งวด> ใน CTE ก่อน แล้วค่อยเฉลี่ยจาก CTE; เดือนที่ไม่มีแถวนับเป็น 0 (หารด้วยจำนวนเดือนของช่วง);
     อย่าตัดหน่วยที่ไม่มียอดในงวดใดงวดหนึ่ง (เริ่มจากรายชื่อหน่วยของทั้งสองช่วง)"
   - `invariant_code` รู้จัก `("I4", "avg_over_fact_rows")` → attempt สุดท้ายยังผิด = ปฏิเสธ (`query_failed`) แบบเดียวกับ I1/I2
3. **grain keys มาจากไหน** (เลือกหนึ่ง, บันทึกเหตุผลใน RESULT):
   - **(แนะนำ) อ่านจาก contract** — `datasets[].keys` ของ contract ที่ data source ของ context ชี้ (`contract_file` ใน registry) ผ่าน
     `datafeed_knowledge.load_contract` + cache ตาม (path, mtime); ชื่อตาราง = `feed_<domain>_<dataset>` — ไม่ต้อง migrate config.db
   - (ทางเลือก) เก็บตอน sync เป็นคอลัมน์ใหม่ `schema_metadata.is_key` — ต้องมี migration script และต้องรันบน config.db จริง**ก่อน** restart (บทเรียน §SALES.3)
4. **tests** — ต้องผิด: SQL ใน Appendix B ทั้งก้อน; `AVG(amount)` ไม่มี GROUP BY; GROUP BY คอลัมน์ที่ไม่ใช่ key (`unit_fname`);
   `AVG(amount) OVER (PARTITION BY unit_fname)`; `SUM(amount) / COUNT(*)`; AVG ใน CASE —
   ต้องผ่าน: SQL เฉลยใน `scripts/eval/check_anomaly_avg.py` (`anomalies()`); AVG จาก subquery; ตาราง grain เล็กที่ตรึง key ครบเหลือหนึ่ง;
   ตารางไม่รู้ grain; `SUM(amount) / COUNT(DISTINCT year_month)`; **ทุกรูปของ compiler** (`test_compiler_shapes` / `test_compiler_ranking` ต้องไม่มี I4) —
   ต่อสาย: context ที่ไม่มี point-in-time ยังได้ I4; ข้อความขึ้นต้นถูก; รอบสุดท้ายยังผิด → `query_failed`
5. **Acceptance:** ACC-T, ACC-L ·
   **server ซ้อม** (สำเนา config.db/app.db/Chroma, contract จริงอ่านอย่างเดียว) ถามคำถามจริงด้วย scope แบบ portal (`year_month` 202501…202609, `context = feed_sales`) 3 รอบ:
   SQL ไม่มี AVG ต่อแถว และ ยอด ก.ย. / ค่าเฉลี่ยต่อเดือน ของหน่วยที่ปรากฏตรง oracle ของ Phase 0 ข้อ 3 (±0.01 บาท) — ถ้ารอบไหนเลือกปี 2568
   ให้บันทึกแยก (เป็นเรื่องของ Phase 2 ไม่ใช่ I4) ·
   **regression** (โค้ดก่อน/หลังบน server ซ้อมเดียวกัน): `NT-Report/DataFeed/eval/portal_questions_{sales,revenue,expense,ebt}.json`
   (สร้างด้วย `NT-Report/tools/feed/portal_questions.py` ถ้ายังไม่มี — `DataFeed/` นอก contracts ไม่อยู่ใน git) +
   `scripts/eval/portal_real_questions.json` (ตัวรัน `scripts/eval/run_portal_questions.py`) — จำนวนข้อถูกไม่ลดลง และนับครั้งที่ I4 ยิง:
   I4 ยิงบน SQL ที่ถูกอยู่แล้ว = false positive → แก้กฎก่อนไปต่อ ·
   **เพิ่มคำถามเหตุการณ์** ลง `scripts/eval/portal_real_questions.json` (id ถัดไป, `time_in_question: true`) โดย `accept.values` = ยอด ก.ย. 69 (ล้านบาท)
   ของ 3 หน่วยแรกในตาราง oracle ของ Phase 0 และ `years_be: [2569]` — ให้ชุดวัดจับเหตุการณ์นี้ได้ทุกรอบต่อจากนี้ (ไฟล์นี้อยู่ในไฟล์ที่อนุญาตของ Phase 1)

---

## 5. Phase 2 — ปีของ "เดือน X" ที่ไม่ระบุปี (AI) — แก้ F4 (ทำตามผล Phase 0)

**ถ้า Phase 0 พบว่า SQL ของรอบนั้นใช้ 2025 (202501–202509):** เพิ่มการตรวจ **I5 `month_outside_reference_year`** ใน `hybrid_flow` (ต้องรู้คำถาม + `reference_period()`):
- เงื่อนไขเข้า: คำถามมีชื่อเดือนไทย (เต็ม/ย่อ — ใช้ชุดเดียวกับ `thai_year._MONTHS` / `_MONTHS_SHORT`) และ**ไม่มี**ปี (25xx / 20xx / "ปี 69") และไม่มีคำบอกปีอื่น
  (ปีก่อน / ปีที่แล้ว / ปีก่อนหน้า / YoY / เทียบปี) และมี `reference_period()` เป็น YYYYMM
- งวดที่ถูก = เดือนนั้นครั้งล่าสุดที่ ≤ งวดอ้างอิง (ถาม "ธันวาคม" ที่งวดอ้างอิง 202609 → 202512)
- ผิดเมื่อ literal งวดใน SQL มีเดือนนั้นแต่**ไม่มี**งวดที่ถูกเลย (เช่นมี 202509 แต่ไม่มี 202609); มีทั้งสองงวด (เทียบปีก่อน) = ผ่าน
- blocking + ข้อความ retry "เดือน<ชื่อ>ที่ไม่ระบุปี = <งวดที่ถูก> (งวดอ้างอิง <ref>) — ใช้ <งวดที่ถูก> และช่วงก่อนหน้าของปีเดียวกัน"; `invariant_code` รู้จัก I5
- **ไฟล์ที่อนุญาต:** `app/services/ai/hybrid_flow.py`, `app/services/ai/thai_year.py` (export ชุดชื่อเดือนเท่านั้น), `tests/unit/test_hybrid_invariants.py`, `tests/unit/test_prompt_scope_note.py`
- tests: คำถามจริงของเหตุการณ์ + SQL ปี 2568 → I5; SQL ปี 2569 → ผ่าน; "เทียบกันยายนปีก่อน" (มีทั้งสองงวด) → ผ่าน; "ธันวาคม" ที่ ref 202609 → 202512 ผ่าน;
  คำถามที่ระบุปี → ไม่ตรวจ; ไม่มี scope และไม่มี period ของ source → ไม่ตรวจ
- Acceptance: ACC-T, ACC-L · server ซ้อม: คำถามของเหตุการณ์ 5 รอบ ได้ 202609 ทุกรอบ · regression ชุดเดียวกับ Phase 1 ไม่ลดลง

**ถ้า Phase 0 พบว่า SQL ใช้ 2026 แต่ข้อความยังเป็น 2568:** ไม่ทำ I5 — หาทางที่คำบรรยายไม่ผ่าน `fix_explanation` (cache ที่เก่ากว่าตัวแก้ / tool loop /
multi-context / ทางอื่นที่ Phase 0 ข้อ 2 เห็น) แล้วให้ทุกทางผ่าน `fix_explanation` + test ของทางนั้น

---

## 6. Phase 3 — คำบรรยาย (AI) — แก้ F5, F6, F7

**ไฟล์ที่อนุญาต:** โมดูลใหม่ `app/services/ai/explain_amounts.py`, `app/services/ai/hybrid_flow.py` (`build_explanation`),
`app/providers/chart_postprocessor.py` (`build_explain_prompt` — เฉพาะบรรทัดกฎ), `app/api/v1/query.py`, `app/api/v1/chat.py` (ย้าย helper ออกเท่านั้น),
`app/services/query_engine.py` (ส่ง note ถึงขั้นคำบรรยาย), tests ใหม่ `tests/unit/test_explain_amounts.py` + tests เดิมที่เกี่ยวข้อง

1. **ตรวจจำนวนเงินในคำบรรยาย (F5)** — แบบเดียวกับ `thai_year` (ตรวจด้วย code ไม่ขอให้โมเดลระวัง):
   - อ่านจำนวนเงินที่มีหน่วยในข้อความ: `<n> บาท`, `<n> ล้านบาท` / `ล้าน`, `<n> พันล้าน`, คำขนาด `หลาย(สิบ|ร้อย|พัน|หมื่น|แสน)ล้าน(บาท)?` (= ค่าต่ำสุดของช่วง เช่น หลายหมื่นล้าน ≥ 2×10¹⁰)
     — อ่านเฉพาะตัวเลขที่มีหน่วยเงินตามหลัง ปี (ไม่มีหน่วย) และตัวเลขที่ตามด้วย `%` จึงไม่ถูกอ่าน
   - ขอบบน = ค่าสัมบูรณ์มากสุดที่ผลลัพธ์รองรับ: เซลล์ตัวเลข, ผลรวมของแต่ละคอลัมน์ตัวเลข, ผลต่างของสองเซลล์ในแถวเดียวกัน
   - ผิดเมื่อจำนวนใดเกินขอบบน > 1% → ถามคำบรรยายใหม่ 1 ครั้งพร้อมบอกจำนวนที่ผิดและขอบบน → ยังผิด → D-4
   - รอบแรกตรวจเฉพาะ "เกินขอบบน" (จับเหตุการณ์นี้ได้, false positive ต่ำ) — การตรวจว่าเลขทุกตัวมีในผลลัพธ์จริงเป็นงานรอบถัดไป
2. **ชื่อตัวชี้วัด (F6, D-3)** — ใช้ตรรกะของ `chat._context_mismatch` กับ `/api/v1/query` ด้วย (ย้ายไป helper กลาง) แต่ note ของ `/query`
   **ส่งถึงขั้นคำบรรยายเท่านั้น** (ไม่เข้า prompt ของ pass 1 / pass 2 — กันคำถามอื่นถดถอย): "คำถามใช้คำว่า '<คำ>' แต่ข้อมูลนี้คือ <ชื่อ context>
   — เรียกตัวเลขว่า <ชื่อ context> และบอกหนึ่งบรรทัดว่าไม่ใช่ <คำ>" (D-3 = ก) · chat คงพฤติกรรมเดิม
3. **กฎคำบรรยาย (F7, D-1, D-2)** ใน `build_explain_prompt` (ขั้นคำบรรยายเท่านั้น):
   - ผลที่มีคอลัมน์ส่วนต่าง/เปอร์เซ็นต์: เรียก "ผิดปกติ / มีนัยสำคัญ" เฉพาะแถวที่เกินเกณฑ์ D-2 (ก) และบอกเกณฑ์ในคำบรรยาย; % บนฐานเล็กกว่าเกณฑ์ไม่ใช่ข้อสรุป
   - ถ้า Phase 0 ยืนยันว่าหัวข้อ "ข้อเสนอแนะการแสดงผล" มาจาก `build_explanation`: ตัดหัวข้อที่ชื่อตรง `ข้อเสนอแนะ.*(แสดงผล|กราฟ)` ออกด้วย code หลังได้คำบรรยาย
4. **Acceptance:** ACC-T, ACC-L · tests: ข้อความจริงของเหตุการณ์ + ตารางที่แปะ → จับ "หลายหมื่นล้านบาท" ได้; ข้อความที่ใช้ตัวเลขถูก → ไม่ยิง;
   "2,568 ล้านบาท" ไม่ถูกอ่านเป็นปี และ "ปี 2569" ไม่ถูกอ่านเป็นเงิน · server ซ้อม: คำถามเหตุการณ์ + ชุด portal_questions ทั้ง 4 โดเมน — นับครั้งที่ตัวตรวจยิง,
   ทุกครั้งที่ยิงต้องเป็นตัวเลขผิดจริง (บันทึกตัวอย่างใน RESULT)

---

## 7. Phase 4 — ลำดับคอลัมน์บน portal (AI + NT-Report) — แก้ F8

- **4.1 AI** (`app/api/v1/query.py`, `tests/unit/test_simple_query.py`, `docs/PORTAL_INTEGRATION.md`):
  `SimpleQueryResponse.columns: Optional[List[str]]` = ลำดับคอลัมน์ของผลลัพธ์ทั้งชุด (แบบเดียวกับ `query_audit.result_columns`); `parts[]` มี `columns` ของตัวเอง;
  ส่งเมื่อ `include_data` — field เพิ่ม ไม่กระทบผู้เรียกเดิม · Acceptance: ACC-T, ACC-L + test ว่าลำดับตรง SQL (คอลัมน์ไทยไม่เรียงตามตัวอักษร)
- **4.2 NT-Report** — ดู [`PROMPT_ANOMALY_AVG_FIX_NT_REPORT.md`](PROMPT_ANOMALY_AVG_FIX_NT_REPORT.md): hook ส่ง `columns` ต่อ, `ask.js` ใช้ `columns` เป็นหัวตารางและ CSV
  (ไม่มี = `Object.keys` เหมือนเดิม) — ทำก่อนหรือหลัง 4.1 ก็ได้ เพราะมี fallback

---

## 8. Phase 5 — (เลื่อนได้, D-5) คำตอบ "เทียบค่าเฉลี่ย" แบบ deterministic

ทำเมื่อเจ้าของสั่ง: นับก่อนว่าคำถามรูปนี้ถามบ่อยแค่ไหน (`query_audit.question` มี เฉลี่ย / ผิดปกติ / ต่างจากปกติ)
1. NT-Report: ประกาศ metric `sales_amount` (actual, full disclosure ตาม `sales_total_scope`) ใน `DOMAINS["sales"]["metrics"]` → contract MINOR — กระทบทุกคำถาม "ยอดขาย" เฉย ๆ ที่ตอนนี้เป็น free SQL → ต้องวัดชุด sales ทั้งชุด
2. AI: `metric_compiler` รูปใหม่ `baseline_avg` (ค่าเฉลี่ยต่อเดือนของช่วงฐานตาม D-1, เดือนว่าง = 0, ทุกหน่วยของทั้งสองช่วง, คอลัมน์ ฐาน / งวด / ส่วนต่าง / % / z, กรองตาม D-2 ก)
   + `plan_with_reason` รับ intent ที่ `aggregate_function = AVG` คู่งวดเดียว — แบบเดียวกับ §CMP (`PLAN_METRICS_COMPARISON.md`)
3. eval: รูป `baseline_avg` ใน `gen_metric_questions` โดย expected = SQL ของ `scripts/eval/check_anomaly_avg.py`

---

## 9. ขึ้นของจริง

1. AI Phase 1 (+2, +3, +4.1 ที่ผ่าน) — merge เข้า branch เดียว → ACC-T/ACC-L บน branch → เจ้าของสั่ง → ff `main` (reload เอง; ไม่มี migration ถ้าเลือก grain จาก contract)
2. NT-Report 4.2 — ตามขั้นตอน deploy portal ของ NT-Report
3. เจ้าของถามคำถามเหตุการณ์บน portal อีกครั้ง → บันทึก audit id, SQL, คำตอบ, หัวตาราง ลง RESULT §ขึ้นของจริง และเทียบกับ oracle ของ Phase 0

## 10. ไม่ทำในแผนนี้ (และเหตุผล)

- **ไม่เพิ่มกฎข้อความ "ค่าเฉลี่ยต้อง SUM รายเดือนก่อน" ใน contract / business rules / golden example** — กฎข้อความเคยทำคำถามอื่นถดถอยและ RAG ไม่ถึง pass 2
  (`PROMPT_RESEARCH_DECLARED_METRICS.md` §2); invariant ตรวจด้วย code และข้อความ retry ไปถึง pass 2 ทุกครั้งที่ผิด
- ไม่แตะ `INTENT_SCHEMA` / prompt ของ pass 1 (I4/I5 ทำงานหลัง pass 2)
- tool-loop rescue ไม่ผ่าน invariant (F10) — ถ้า Phase 0 พบว่าเปิด `escalation_tool_loop_enabled` อยู่ ให้บันทึกเป็นงานแยก ไม่แก้ในแผนนี้

---

## Appendix A — เครื่องมือตรวจ / เฉลย `scripts/eval/check_anomaly_avg.py`

อ่านอย่างเดียว: `--db` = ไฟล์ view ใน `.source_cache/` (view `feed_sales_fact_sales` แบบเดียวกับที่ server query) หรือ `--csv` = `DataFeed/dist/sales/latest/fact_sales.csv`
(dialect เดียวกับ server) · ตัวเลือก `--month` (YYYYMM ค.ศ., ก.พ.–ธ.ค.), `--unit`, `--by` (`unit_fname` / `unit_fname_current`), `--min-diff`, `--min-pct`, `--z`

ทดสอบกับข้อมูลสังเคราะห์แล้ว (หน่วยคงที่ 600 แถว/เดือน, หน่วย ×3, หน่วยหายใน ก.ย., หน่วยใหม่, หน่วยที่มีเดือนว่าง) — ข้อ 3 ตรงค่าที่คำนวณแยกด้วย Python ทุกแถว,
และหน่วยคงที่ไม่ติดเกณฑ์ (เปลี่ยนจริง −0.13%)

## Appendix B — SQL ที่ระบบสร้าง (เจ้าของแปะมา 2026-10-28)

```sql
WITH avg_before_sep AS (
    SELECT unit_fname, AVG(amount) AS avg_amount_before_sep
    FROM feed_sales_fact_sales
    WHERE metric = 'actual' AND year_month BETWEEN 202601 AND 202608
    GROUP BY unit_fname
),
sep_amount AS (
    SELECT unit_fname, SUM(amount) AS amount_sep
    FROM feed_sales_fact_sales
    WHERE metric = 'actual' AND year_month = 202609
    GROUP BY unit_fname
)
SELECT s.unit_fname AS "หน่วยงาน",
       s.amount_sep AS "ยอดขายเดือนกันยายน",
       a.avg_amount_before_sep AS "ค่าเฉลี่ยยอดขายก่อนกันยายน",
       (s.amount_sep - a.avg_amount_before_sep) AS "ส่วนต่าง",
       CASE WHEN a.avg_amount_before_sep = 0 THEN NULL
            ELSE (s.amount_sep - a.avg_amount_before_sep) / NULLIF(a.avg_amount_before_sep, 0) * 100
       END AS "เปอร์เซ็นต์เปลี่ยนแปลง"
FROM sep_amount s
LEFT JOIN avg_before_sep a ON s.unit_fname = a.unit_fname
WHERE a.avg_amount_before_sep IS NOT NULL
  AND ABS(s.amount_sep - a.avg_amount_before_sep) > 0 -- กรองเฉพาะที่มีความแตกต่าง
ORDER BY ABS(s.amount_sep - a.avg_amount_before_sep) DESC
```

รันกับข้อมูลสังเคราะห์ชุดเดียวกับ Appendix A:

| หน่วย | ระบบ (SQL นี้) | ที่ถูก (เฉลี่ยต่อเดือน, เดือนว่าง = 0) |
|---|---|---|
| คงที่ 600 แถว/เดือน | +59,822% | −0.13% (ไม่ผิดปกติ) |
| 5 แถว/เดือน, ก.ย. ×3 | +1,400% | +200% |
| ยอด ก.ย. หายเป็น 0 | ไม่อยู่ในผล | −100% |
| หน่วยใหม่ (มีแต่ ก.ย.) | ไม่อยู่ในผล | +40 ล้าน (ไม่มีฐาน) |
