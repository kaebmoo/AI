# เปิดใช้จริง: NT-Report portal ถามตอบผ่าน AI (2026-09-20)

คำสั่ง: `plan/PROMPT_P7_GOLIVE_NT_REPORT.md` · ผลเต็ม: `plan/archive/RESULT_P7_GOLIVE.md` ·
ตัวเลข 10 คำถาม/report_type: `plan/archive/RESULT_F11.md` · การใช้งานประจำวัน: `docs/manuals/manual_portal_runbook.md`

ผู้ใช้รายแรกของ Plan 7 — เอาของที่ Phase 1–6 สร้างไว้ (วัดบนสำเนาทั้งหมด) ไปเปิดบนของจริง

## สถานะ

| | |
|---|---|
| **ฝั่ง AI** | ✅ เปิดแล้ว — `config.db` migrate แล้ว, server รัน, ทุก source ok, key จริงของ portal ออกแล้ว |
| **ปุ่มฝั่ง portal** | ❌ **ยังไม่เปิด** — เทียบ 10 คำถามต่อ report_type ได้ **8 / 8 / 8 / 5** ยังไม่ถึงเกณฑ์ 9/10 |

## สิ่งที่เปลี่ยนใน code

| เรื่อง | ก่อน | หลัง |
|---|---|---|
| prompt กับ `scope` | โมเดลไม่เคยรู้ว่ามี scope (ห่อ view อย่างเดียว) | เมื่อ `request_scope` ถูกตั้ง prompt บอกขอบเขต + **ค่ามากสุดของ key ที่เป็นตัวเลข = งวดอ้างอิง** และว่า SQL ต้องมีเงื่อนไขงวดของตัวเอง — 4 จุด (prompt แรก, retry, **pass 1 ของ two-pass**, pass 2). คำขอที่ไม่มี scope: prompt เดิมทุกไบต์ |
| `schema_contexts.description` ของ `feed_*` | `contract["title"]` ("NT Revenue Data Feed") | `contract["description"]` — ประโยคไทยที่บอกว่าชุดนี้ตอบอะไร/ไม่ตอบอะไร (ข้อเสนอจากฝั่ง NT-Report) |
| `docs/PORTAL_INTEGRATION.md` | "เตือนเมื่อ `data_as_of.period` ไม่ตรงงวดรายงาน" | เตือนเมื่อ **น้อยกว่า** เท่านั้น (ใหม่กว่า = ปกติ เพราะ scope บังคับที่ชั้น SQL แล้ว) + `error` เป็น**รหัส**ไม่ใช่ข้อความ |

## ทำอะไรบนของจริง

1. backup สด (SQLite backup API จาก `mode=ro` + `quick_check` + SHA-256) — SHA ของต้นฉบับเท่าเดิมตลอดงาน
2. `llm_provider_allowlist` ของ source `datafeed_*` = `["matcha"]` (D4); `llm_data_policy` คง `full`
3. start server → **job `result_retention` รอบแรกรันใน 30 วินาที**: `chat_history` 1,513 แถว (คำตอบกลายเป็นข้อความ
   "หมดอายุ", `result_data` / `sql_result_summary` ล้าง) + ลบ `chat_session_data` 55 แถว — **ตรงกับที่ซ้อมบนสำเนาทุกตัวเลข**;
   คำถาม 1,513 และ SQL 1,511 อยู่ครบ
4. ออก key `nt-report-portal` ผูก workspace `nt-report` (20/นาที 2,000/วัน) — raw key อยู่กับเจ้าของเท่านั้น
5. ถาม 80 ครั้งด้วย key จริงในรูป request เดียวกับ hook เพื่อเทียบกับ dashboard

## ที่พบและยังไม่ปิด

- **hook ของ portal ต้องแก้ 1 จุด**: `mapUpstreamError` หา `/publish/i` ใน `payload.error` ซึ่งตอนนี้เป็นรหัส
  `source_unavailable` → ระหว่าง publish ผู้ใช้ได้ "ถามใหม่ด้วยถ้อยคำอื่น" แทน "ข้อมูลกำลังอัปเดต"
- **ยังไม่ถึง 9/10**: ที่เหลือ 11 ข้อแยกเป็น ฐานเปรียบเทียบที่ contract ไม่ได้ประกาศ (REV8, REV10) ·
  ความรู้ของ `feed_sales` (SAL2/4/7/8/10) · ถ้อยคำของ `ebt_not_company_wide` ที่ยังทำให้ "ตอบพร้อมติดป้าย"
  แทนที่จะ "ปฏิเสธ" (EBT9)
- **ต้อง restart PocketBase** — process ที่รันอยู่เก่ากว่าการแก้ hook ทั้งหมดของวันนี้
- `export_cleanup` ล้มทุกรอบบน `app.db` จริง (`no such table: report_exports`) — ของเดิม ไม่เกี่ยวกับงานนี้

## Test

`1084 passed, 3 skipped` (baseline ก่อนงานนี้ 1078) — รันบนสำเนาของ DB จริงเสมอ
