# FIX NOTES — สิ่งที่พบระหว่าง execute แผน (ไม่แก้ทันที ตามกฎ)

## จาก F1 (2026-07-11)

- **F1.3 frontend QA:** `frontend/components/Chat/ModelSelector.tsx` auto-select default provider จาก `/admin/config/ai/providers` (`is_default`) แล้ว `frontend/app/(app)/index.tsx` ส่ง `provider` ชัดเจนทุก request — ไม่มี hardcode "gemini" ฝั่ง frontend ถ้า API ล่มจะ fallback (ดู adminService.ts) — พฤติกรรมยอมรับได้ ไม่ต้องแก้
- **F1.4:** `SchemaService._cache` (`set_cached_value` ใน `app/services/schema/service.py:88`) ไม่มี eviction — โตไม่จำกัดในทางทฤษฎี แต่ key space เล็ก (provider×context×language×วัน) และ instance ถูกสร้างใหม่บ่อย ยอมรับได้ระยะนี้; ถ้า SchemaService กลายเป็น singleton ค้างนาน ควรเพิ่ม TTL eviction
- `app/api/v1/query.py` (stateless API) ไม่ส่ง `provider` เลย → ใช้ admin default โดยธรรมชาติ ไม่มี B3 pattern

## จาก F2 (2026-07-11)

- **datetime migration:** ทั้ง repo ใช้ `app.core.time_utils.utcnow()` (naive UTC — semantics เดิมของ `datetime.utcnow()`) เพราะ DB columns เก็บ naive datetime — **migration ไป timezone-aware ทั้งระบบเป็นงานอนาคต** (ต้องทำพร้อม DB migration)
- **`AdminConfigService()` ที่ยังสร้าง per-call โดยไม่ close:** `app/api/v1/admin/config.py`, `providers.py`, `analytics.py`, `vanna_docs.py`, `_shared.py`, `app/services/admin_agent.py` — อยู่นอกขอบเขต F2.1 (B4 ระบุเฉพาะ `deps.get_ai_service` + `QueryEngine.__init__`) แต่เป็น pattern เดียวกัน ควรย้ายมาใช้ `deps.get_admin_config_service` ในรอบถัดไป
- **`tests/unit/test_db_separation.py`** มี assertion เกี่ยวกับ session — ผ่านอยู่ ไม่แตะ
