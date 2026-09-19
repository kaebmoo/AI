# Plan 7 Phase 4.5 — Data protection (2026-09-19)

แผน: `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §6.6, §6.8 · ผล + ตารางสำรวจจุดรั่ว: `plan/archive/RESULT_P7_PHASE45.md` · การตัดสินใจ: `plan/FIX_NOTES.md`

## สิ่งที่เปลี่ยนสำหรับผู้ใช้ / ผู้ดูแล

| เรื่อง | ก่อน | หลัง |
|---|---|---|
| ข้อมูลที่ออกไปหา LLM | ทุก source: ค่าตัวอย่าง, value lookup, RAG, แถวผลลัพธ์ (อธิบายผล), คำตอบเก่าใน history | ตั้งได้ต่อ source: `full` (เหมือนเดิม — ค่าเริ่มต้นของทุก source) / `aggregated_only` / `schema_only` — บังคับที่ชั้น provider + ต้นทางของค่า |
| เลือก provider | ค่ากลางของระบบ / ผู้ใช้เลือก | + `llm_provider_allowlist` ต่อ source (นอกรายการ = 403) — Matcha ใช้กับข้อมูลอ่อนไหวได้ (D4) |
| แถวผลลัพธ์ในประวัติแชท | เก็บตลอดไป | ล้างหลัง `result_retention_days` (**default 30**, 0 = ไม่ลบ; override ต่อ workspace); โหมด `store_result_data=false` = ไม่เก็บเลย — คำถาม/SQL/คำตอบอยู่ครบ |
| ลบข้อมูลตามคำขอ | ไม่มี | `DELETE /admin/users/{id}/data` (dry-run เป็นค่าเริ่มต้น) |
| Audit ของคำถาม | เฉพาะ web chat (`chat_history`); `/api/v1/query` + telegram ไม่มีร่องรอย | `query_audit` ทุกช่องทาง: key / workspace / scope / context / SQL / คอลัมน์ / จำนวนแถว / policy / error + ค้น + export CSV |
| Onboarding / หน้า schema / keyword index / hierarchy | ส่ง + เก็บค่าตัวอย่างของทุก view | ไม่ส่ง ไม่เก็บ ของ source ที่ policy ≠ `full` |

⚠️ **หลัง upgrade:** job retention รอบแรกจะล้างแถวผลลัพธ์ที่เก่ากว่า 30 วัน (บนสำเนา app.db จริง: 1,285 แถว + session data 55 รายการ; ข้อความคำถาม/คำตอบไม่หาย) — ต้องการเก็บนานกว่า ตั้ง `result_retention_days` ก่อน start

## Upgrade
```bash
python scripts/migrate_data_sources.py   # + data_sources.llm_data_policy ('full'), llm_provider_allowlist
python scripts/migrate_workspaces.py     # + workspaces.result_retention_days, store_result_data
```
`query_audit` (app DB) สร้างเองตอนใช้ครั้งแรก. ไม่ migrate = พฤติกรรมเดิมทุกอย่าง (ไม่มี policy ให้ตั้ง)

## ไฟล์หลัก
- `app/core/llm_policy.py` — policy, `request_llm_policy` (ContextVar), `guard_call` (sink), `PolicyMCPClient`, `history_without_answers`, `is_aggregate_sql`
- `app/providers/base.py` — `AIProvider.__init_subclass__` ห่อ provider ทุกตัว
- `app/services/data_sources.py` — policy บน `ResolvedSource`, `policy_for_table`, `policy_for_context`
- `app/services/query_engine.py` — ตั้ง policy ต่อ request, เลือก provider ตาม allowlist, cache ตรวจ policy, เขียน audit
- `app/services/retention.py`, `app/services/scheduler.py` (`result_retention`) · `app/services/user_data.py` · `app/services/query_audit.py`, `app/models/query_audit.py`
- API: `PUT /admin/sources/{name}/policy`, `PUT /admin/workspaces/{id}/retention`, `PUT /admin/config/settings/result_retention_days`, `DELETE /admin/users/{id}/data`, `GET /admin/query-audit`
- Tests: `tests/unit/test_llm_data_policy.py` (กับดัก sentinel ที่ขอบ HTTP ของ provider), `test_retention.py`, `test_query_audit.py`, `test_user_data_erase.py`

## ข้อจำกัดที่ต้องรู้
- `aggregated_only` ตรวจจากข้อความ SQL ไม่ใช่ k-anonymity — ของที่ห้ามเห็นรายแถวใช้ `schema_only`
- `schema_only`: ไม่มี value lookup / RAG → คำถามที่ต้องเดาค่าจริง (ชื่อ product ฯลฯ) แม่นน้อยลง; คำอธิบายเป็น template; `mode=mcp` ใช้ไม่ได้
- นอกขอบเขต policy: Telegram, schema analyzer (ไฟล์ upload), admin agent สรุปคำถามของผู้ใช้
- ยังไม่มี Admin UI — ใช้ API (`docs/ADMIN_CONFIGURATION.md`)
- classification ต่อคอลัมน์ / k ≥ 5 / mask (§6.6 ข้อ 1–2) เลื่อน (D5); PDPA ข้อ 8 รอ DPO
