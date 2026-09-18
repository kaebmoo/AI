# RESULT Plan 7 Phase 3 — Scope enforcement (D3 = A)

**วันที่:** 2026-09-19 | **Branch:** `main` (ยังไม่ push) | **Provider:** admin default (matcha, gpt-4.1)
**แผน:** `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §3.3, §5 Phase 3, §6.2 ชั้น 4 | **ตัดสินก่อนเริ่ม:** เจ้าของเลือกไป Phase 3 ทั้งที่ Phase 2 ผ่าน 2/4 โดเมน (2026-09-19)

## สรุป

| Exit criterion | unit test | ถามจริง (LLM, ข้อมูลจริง) | ผ่าน? |
|---|---|---|---|
| scope `year_month=202607` แล้วถาม "เดือนล่าสุด" ได้ 202607 ไม่ใช่ 202608 | `TestFileSourceScope::test_latest_period_is_the_scoped_one` (SQL ของโมเดล + ฝั่ง prompt) | `feed_revenue`: "รายได้รวมทั้งบริษัทเดือนล่าสุด…" → **ก.ค. 2569 = 3,274,665,994.46** (= control_totals 202607); ไม่มี scope → ส.ค. 2569 = 3,434,072,699.62 | ✅ |
| scope หน่วยงาน A ถามถึงหน่วยงาน B ได้ 0 แถว/ปฏิเสธ | `test_other_org_gets_zero_rows`, `test_qualified_names_cannot_read_around_the_scope`, `TestCteScoping` | scope `org_code=1L00201` ถามศูนย์ต้นทุน 2G10601 → ค่า NULL "ไม่มีข้อมูล"; ถามยอดทั้งบริษัทแยก BU → ปฏิเสธ; ถามของหน่วยงานตัวเอง → **416,370,805.34** ถูก | ✅ |
| scope คอลัมน์ที่ไม่ประกาศ = 400 | `TestScopeErrors`, `test_scope_passed_and_unenforceable_scope_is_400` | `{"division": "x"}` → ScopeError ก่อนเรียก LLM (0.0 s) | ✅ |
| legacy ก็บังคับได้ | `TestLegacyScope` | `revenue` scope `{year: 2025, month: 3}` "เดือนล่าสุด" → 7,465,818,216.56 (มี.ค. 2568) | ✅ |
| pytest ไม่มี test เดิมพัง | 742 → **802 passed**, 3 skipped (Phase 3 +45, REMAIN-9 +15; test เดิมแก้ 1 จุด: T5.4 ของ onboarding ส่ง `config_db_path` ชัด ๆ) | | ✅ |

eval regression (ไม่มี scope — เส้นทางเดิม): ดูตารางท้ายไฟล์

## ทำงานอย่างไร

- `/api/v1/query` รับ `scope` (dict) — `pinned_filters` คง log อย่างเดียว (D3=A)
- `QueryEngine.query(scope=…)` ตั้ง `request_scope` (ContextVar) ตลอด request → **ทุกจุดที่ resolve source** (SQL ของโมเดล, SchemaService ที่สร้าง prompt,
  value lookup, WarningDetector, ValueVerifier) ได้ source ที่ผ่าน scope แล้ว — `asyncio.to_thread` copy context ให้เอง
- สิ่งที่ context ยอมให้ scope = `schema_contexts.scope_columns` `{key: column}` (migration idempotent); `feed_*` ได้จาก `scope_columns` ใน contract (re-sync อัตโนมัติ)
  — key ที่ไม่ประกาศ / ค่าไม่ใช่ int/str (หรือ list 1–1000 ค่า) → `ScopeError` → **HTTP 400** ไม่มีทางตอบแบบไม่กรอง
- บังคับที่ engine: ต่อ query สร้าง **TEMP view ชื่อเดียวกับตารางจริงทุกตาราง** — ตารางที่มีคอลัมน์ครบ = `WHERE <predicate จาก literal ที่ตรวจแล้ว>`,
  ตารางอื่น = ว่าง; แล้ว gate (parser ของ DuckDB) ให้ SQL อ้างได้เฉพาะตารางที่กรองแล้ว **แบบไม่มี schema นำหน้า**
  - file source: `ScopedDuckDB` (cursor ใหม่ต่อ query; ต้นฉบับอ้างผ่าน `"<db catalog>".main.<view>` — TEMP ของ DuckDB อยู่ใน catalog temp schema main)
  - legacy: `ScopedSQLite` — query ที่มี scope รัน **ใน process** บน connection read-only ใหม่ต่อ query (ไม่ผ่าน MCP) อ่านได้เฉพาะ main view;
    legacy ที่ไม่มี scope ยังผ่าน MCP เหมือนเดิม
- cache key และ dedup key รวม scope (คีย์ของคำถามที่ไม่มี scope ไม่เปลี่ยน)
- system prompt ต่อท้ายด้วย scope + รายชื่อตารางที่ใช้ได้ — **จำเป็น**: ไม่งั้นโมเดลยึด main view (`fact_bu_monthly` ไม่มี cost_center) แล้วถูกปฏิเสธทุกรอบ
  แม้คำถามอยู่ใน scope (วัดจริง: ก่อนเพิ่มข้อความ "ตารางหลักใช้ไม่ได้" ตอบไม่ได้ 2/2, หลังเพิ่ม ตอบถูก 2/2)

## Review อิสระ (agent แยก, ได้แค่ code ไม่ได้ข้อสรุปของผม)

| Finding | ความรุนแรง | ผล |
|---|---|---|
| gate เก็บชื่อ CTE จากทุก `WITH` ในต้นไม้เป็นชุดเดียว → CTE ใน subquery ทำให้การอ้างชื่อเดียวกันข้างนอกผ่าน: `SELECT SUM(V) FROM revenue WHERE 1 IN (WITH revenue AS (SELECT 1) SELECT * FROM revenue)` อ่านตาราง raw ทั้งหมดบน legacy ที่มี scope (และ `sqlite_master`) — gate ของ Phase 1 มีจุดเดียวกัน (file source มี shadow ว่างกันไว้ภายใต้ scope; ไม่มี scope ให้อ่าน system view ได้) | **high** | แก้ `525c5b6` — ขอบเขต CTE ตามตำแหน่ง (body เห็นเฉพาะ CTE ก่อนหน้า, ตัวเองเฉพาะ recursive, ไม่รั่วออกนอก) — reproduce ก่อนแก้; SQL จริง 1,548 ชุด (golden + chat_history + eval) ผลตัดสินของ gate **ไม่เปลี่ยนเลย** |
| gate ไม่ตรวจว่า statement เป็น SELECT | low | แก้ `525c5b6` (SELECT_NODE / SET_OPERATION_NODE เท่านั้น) |
| (เสนอ) legacy shadow ทุกตาราง ไม่ใช่แค่ view ที่ scope | defense in depth | ทำ `4949129` — 27 ตาราง ~1 ms/connection; query อุ่นแล้ว 82 ms vs 85 ms แบบไม่มี scope |

ที่ reviewer ลองแล้ว**ถูกกัน**: backtick/bracket identifier (parse ไม่ผ่าน → ปฏิเสธ), `main.`/`temp.`/catalog, หลาย statement, UNION ไปตาราง raw,
`pragma_table_info`, `read_csv`, `WITH RECURSIVE`, ฉีดผ่านค่า scope, contextvar หายใน thread pool, เส้นทาง export

## ข้อจำกัด / ข้อค้าง
- **dim ที่ไม่มีคอลัมน์ของ scope ใช้ไม่ได้ภายใต้ scope นั้น** (เช่น `dim_bu` ภายใต้ `year_month`) — ปลอดภัยไว้ก่อน; ถ้าต้องการให้อ่านได้แบบไม่กรอง ต้องให้เจ้าของประกาศ (เสนอ `scope_exempt: true` ต่อ dataset — ยังไม่ทำ)
- `org_code` ของ revenue: ใส่ใน config ทดลอง (สำเนา) เป็น `cost_center` เท่านั้น — ใน config จริงตั้งไว้แค่ `year_month` (feed_revenue, feed_expense→`time_key`); คอลัมน์หน่วยงานต้องให้ NT-Report ประกาศใน contract (`plan/PROMPT_NT_REPORT_P7.md`)
- keyword index / golden / Vanna (config DB) ไม่ถูกกรองตาม scope → **ชื่อ**ค่าของหน่วยงานอื่นอาจโผล่ใน "Actual Values Found" ได้ (ไม่มีตัวเลข) — PLAN_7 §6.6 ข้อ 4 (Phase 4.5)
- query legacy ที่มี scope ครั้งแรกของ process ช้าขึ้น ~300 ms (โหลด parser ของ DuckDB)
- export xlsx ไม่รับ scope (`/api/v1/query` ไม่ export; chat ไม่รับ scope)

## Commits
```
d72246c feat(P7-3): scope enforced at the SQL layer for file and legacy sources
525c5b6 fix(P7-3): scope CTE names lexically in the query gate
4949129 fix(P7-3): scoped legacy connection shadows every table, not only the scoped view
```

## สถานะ DB (local — ไม่อยู่ใน git)
- `config.db`: `schema_contexts.scope_columns` (migration แล้ว) — `feed_revenue` `{"year_month": "year_month"}`, `feed_expense` `{"year_month": "time_key"}`

## Eval regression หลัง Phase 3 + REMAIN-9/10 (ไม่มี scope — เส้นทางปกติ)

| Context | ไฟล์ผล (`eval_results/`) | value_match | P50 | P95 | เทียบรอบก่อน (Phase 2) |
|---|---|---|---|---|---|
| feed_revenue | `eval_20260919_0135` | 13/14 | 6.17 s | 8.46 s | 14/14, 6.68 s — ข้อที่ตก (YTD ของ `8.รายได้อื่น`) โมเดลเติมคอลัมน์ `bu` → 2 คอลัมน์ vs golden 1 (ค่าเดียวกัน, แถวเดียวกัน) = ข้อจำกัดของเกณฑ์เทียบที่บันทึกไว้ตั้งแต่ F10 ไม่ใช่ผลของ code |
| feed_expense | `eval_20260919_0137` | **12/12** | 6.15 s | 6.90 s | 12/12, 7.07 s — เร็วขึ้นจาก value lookup (REMAIN-10) |
