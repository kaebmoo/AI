# FIX NOTES — สิ่งที่พบระหว่าง execute แผน (ไม่แก้ทันที ตามกฎ)

## จาก F1 (2026-07-11)

- **F1.3 frontend QA:** `frontend/components/Chat/ModelSelector.tsx` auto-select default provider จาก `/admin/config/ai/providers` (`is_default`) แล้ว `frontend/app/(app)/index.tsx` ส่ง `provider` ชัดเจนทุก request — ไม่มี hardcode "gemini" ฝั่ง frontend ถ้า API ล่มจะ fallback (ดู adminService.ts) — พฤติกรรมยอมรับได้ ไม่ต้องแก้
- **F1.4:** `SchemaService._cache` (`set_cached_value` ใน `app/services/schema/service.py:88`) ไม่มี eviction — โตไม่จำกัดในทางทฤษฎี แต่ key space เล็ก (provider×context×language×วัน) และ instance ถูกสร้างใหม่บ่อย ยอมรับได้ระยะนี้; ถ้า SchemaService กลายเป็น singleton ค้างนาน ควรเพิ่ม TTL eviction
- `app/api/v1/query.py` (stateless API) ไม่ส่ง `provider` เลย → ใช้ admin default โดยธรรมชาติ ไม่มี B3 pattern

## จาก F2 (2026-07-11)

- **datetime migration:** ทั้ง repo ใช้ `app.core.time_utils.utcnow()` (naive UTC — semantics เดิมของ `datetime.utcnow()`) เพราะ DB columns เก็บ naive datetime — **migration ไป timezone-aware ทั้งระบบเป็นงานอนาคต** (ต้องทำพร้อม DB migration)
- **`AdminConfigService()` ที่ยังสร้าง per-call โดยไม่ close:** `app/api/v1/admin/config.py`, `providers.py`, `analytics.py`, `vanna_docs.py`, `_shared.py`, `app/services/admin_agent.py` — อยู่นอกขอบเขต F2.1 (B4 ระบุเฉพาะ `deps.get_ai_service` + `QueryEngine.__init__`) แต่เป็น pattern เดียวกัน ควรย้ายมาใช้ `deps.get_admin_config_service` ในรอบถัดไป
- **`tests/unit/test_db_separation.py`** มี assertion เกี่ยวกับ session — ผ่านอยู่ ไม่แตะ

## จาก F4 (2026-07-11)

- **⚠️ ต้องถามเจ้าของโปรเจกต์:** `app/services/schema/view_manager.py:57-60` **เขียนลง business DB** (CREATE/DROP VIEW ผ่าน `business_engine`) — เป็น admin feature (view manager) ที่ตั้งใจ ดังนั้น F4.1 จึง**ไม่ได้**ทำ `business_engine` ฝั่ง app เป็น read-only (ทำเฉพาะ MCP servers ซึ่งเป็น reader ล้วน) — ถ้าต้องการ RO ฝั่ง app ด้วย ต้องแยก engine สำหรับ view_manager ก่อน
- **`app/services/database_adapter.py` และ `app/services/business_db.py` ไม่มี production caller** (business_db มีแค่ test import) — เป็น dead module ควรพิจารณาลบในรอบ cleanup
- validate_sql delegation: import `app.services.validation_service` จาก MCP process ใช้เวลา ~0.07s — ไม่มีปัญหา startup

## จาก F5 (2026-07-11)

- **Manual webhook end-to-end ยังไม่ได้ทดสอบ** — ต้องใช้ bot token จริง + tunnel (ngrok/cloudflared) ซึ่งไม่มีใน environment นี้ — โค้ด initialize/set_webhook/delete_webhook เขียนตาม PTB 22 docs และ unit tests ผ่าน แต่ acceptance ข้อ "Manual webhook end-to-end" ค้างไว้ให้เจ้าของโปรเจกต์รัน (ขั้นตอนอยู่ใน PLAN_F5 หัวข้อการทดสอบ)
- python-telegram-bot ติดตั้งเฉพาะ system python3.10 (ไม่อยู่ใน venv) — venv ที่ใช้รัน pytest ไม่มี PTB แต่ tests mock หมดจึงผ่าน

## จาก F7 (2026-07-11)

- **`app/services/cost_service.py` ไม่มี caller เลย** (dead module เหมือน database_adapter/business_db) — F7.2 ข้อ 5 จึงไม่มีอะไรต้อง wire; ถ้าจะใช้จริงต้องเรียก `calculate_cost` จาก usage_breakdown ที่มีแล้ว (input/output แยกให้แล้ว) — พิจารณาลบหรือ wire ในรอบถัดไป
- trace ถูกสร้าง/emit ที่ระดับ **QueryEngine** (ไม่ใช่ hybrid_flow) เพื่อให้ cache hit ถูก trace ด้วย — hybrid_flow เติม stages/usage ผ่าน parameter
- mcp mode (`query_with_retry`) ยังไม่ผูก trace/stage breakdown — tokens จาก generate_sql ของ provider ถูกรวมอยู่แล้ว (ไม่ hardcode) แต่ไม่มี per-stage breakdown — ยอมรับได้เพราะ hybrid คือ default

## จาก F8 (2026-07-11)

- **`TWO_PASS_ENABLED` ยังคง default OFF** — F8 ทำให้ Pass 1 พร้อมใช้ (structured output + fallback) แต่การเปิด flag ถาวรรอเทียบ eval (F3-B baseline) ก่อน — decision ของเจ้าของโปรเจกต์
- **Gemini structured output ใช้ mime json + schema ใน prompt** (ไม่ใช่ `response_schema`) — การแปลง JSON Schema → google-genai Schema type เปราะต่อเวอร์ชัน SDK; วิธีที่เลือกเสถียรกว่าและยอมรับตามแผน
- **งานอนาคต:** เปลี่ยน main SQL generation path เป็น structured output — ยังไม่ทำเพราะ CoT + ```sql fence ทำงานอยู่และต้องมี eval คุมก่อน
- Manual smoke ที่ต้องเปิด two_pass + ยิงคำถาม follow-up 3 แบบกับ key จริง — ค้างให้เจ้าของโปรเจกต์ (env นี้เรียก LLM ผ่าน default provider ได้ แต่การเปิด two-pass ใน admin_config เป็น state change ที่ควรทำใน dev ของทีม)
