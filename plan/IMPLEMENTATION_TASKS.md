# NT AI Assistant - Current Implementation Tasks

> ประเภทเอกสาร: backlog และงานถัดไปที่อิงจาก source ปัจจุบัน
> Snapshot date: 2026-03-22
> วิธีอ่าน: ไฟล์นี้ไม่ใช่ประวัติการสร้างโปรเจกต์แล้ว แต่เป็นรายการงานที่ยังเหลือและงาน hardening ที่ควรทำต่อจากฐานโค้ดปัจจุบัน

---

## เสร็จแล้วในระดับโปรดักต์

- [x] FastAPI backend หลัก
- [x] OTP auth + session auth
- [x] API key auth และ stateless query endpoint
- [x] Chat endpoint + SSE stream endpoint
- [x] Multi-context routing
- [x] Admin CRUD platform
- [x] Admin Agent backend + UI
- [x] Provider/model/settings management
- [x] Context onboarding flow
- [x] Telegram bot integration
- [x] Expo user app core chat flow
- [x] pytest unit/integration structure
- [x] Docker production compose file

---

## P0 - ต้องทำก่อน production hardening รอบถัดไป

- [x] แยก `app/api/v1/admin.py` ออกจากไฟล์ monolith เป็น package ที่ `app/api/v1/admin/`
- [x] แยก `app/services/ai_service.py` ออกจากไฟล์ monolith เป็น package facade + compatibility shim
- [x] แยก `app/services/schema_service.py` ออกจากไฟล์ monolith เป็น package facade + compatibility shim
- [x] ปิดช่อง SQL interpolation ที่ยังยืนยันได้ใน `schema_service.py` และ `vanna_service.py`
- [ ] ลด `except Exception` ที่ยังมีจำนวนมากใน `app/`
- [ ] ทำให้ cache / dedup / global in-memory state ปลอดภัยขึ้นสำหรับ multi-worker execution

### Follow-up หลัง refactor หลัก

- [x] เก็บ cleanup ของ `app/services/analyzer_service.py` ให้สอดคล้องกับ public AI service surface ปัจจุบัน
- [ ] เก็บ minor consistency cleanup ของ `_detect_hierarchy_level()` ถ้าต้องการลด shim indirection ในภายหลัง
- [ ] พิจารณา hierarchy cache owner transfer ไป `hierarchy_service.py` ถ้าจะลด bridge debt ในรอบถัดไป
- [ ] ลด static-analysis noise ใน route modules ใต้ `app/api/v1/admin/` เท่าที่คุ้มค่า
- [ ] เพิ่ม integration coverage สำหรับ compatibility shim ของ `schema_service.py` และ `ai_service.py`

---

## P1 - งานผลิตภัณฑ์ที่ยังขาดชัดเจน

### Reports / Export

- [ ] เพิ่ม report service ฝั่ง backend
- [ ] เพิ่ม report API endpoints
- [ ] เพิ่ม export CSV/XLSX/PDF แบบเป็นทางการ
- [ ] เพิ่ม scheduled report worker ถ้าจะใช้ Celery จริงในส่วนนี้

### Deployment / Operations

- [ ] เพิ่ม CI/CD pipeline จริง
- [ ] เพิ่ม deployment runbook ที่เป็นเอกสารหลักเพียงชุดเดียว
- [ ] เพิ่ม reverse proxy / SSL / health check story ที่ชัดเจน
- [ ] กำหนด environment matrix สำหรับ local / staging / production ให้ครบ

### Security / Hardening

- [ ] ทดสอบ SQL injection regressions แบบอัตโนมัติ
- [ ] เพิ่ม security tests สำหรับ API key scopes
- [ ] เพิ่ม audit trail สำหรับ sensitive admin operations ให้ชัดเจนขึ้น
- [ ] ทบทวน rate limits สำหรับ chat / API key / Telegram

---

## P2 - งาน UX / Product polish

### Expo Frontend

- [ ] จัด route และ screen structure ให้สอดคล้องกับ capability ที่มีใน service/components
- [ ] รวม conversation/history UX ให้ชัดเจนใน app flow
- [ ] เพิ่ม settings/history screens แบบสมบูรณ์ถ้าต้องการให้ตรง capability backend
- [ ] ปรับ mobile-specific UX และ responsive details เพิ่มเติม

### Admin UI

- [ ] ลดขนาด component ใหญ่ เช่น `Settings.tsx`, `HierarchyManager.tsx`, `Analyzer.tsx`
- [ ] ตรวจหน้า dashboard ที่ยังมีข้อความ static บางส่วนให้ดึงจาก backend จริงทั้งหมด
- [ ] เพิ่ม consistency ของ loading/error state ระหว่างหน้า admin ทั้งชุด

---

## P3 - งานคุณภาพและ test coverage

- [ ] เพิ่ม integration tests สำหรับ admin endpoints ที่สำคัญ
- [ ] เพิ่ม tests สำหรับ context onboarding edge cases
- [ ] เพิ่ม tests สำหรับ SSE streaming flow
- [ ] เพิ่ม tests สำหรับ Redis/cache failure scenarios
- [ ] เพิ่ม E2E flow สำหรับ user app และ admin app
- [ ] เพิ่ม load/performance test ที่ repeatable

---

## งาน cleanup เอกสารและโครงสร้าง

- [ ] รวม deployment docs ที่กระจายอยู่หลายไฟล์ให้เหลือ source of truth เดียว
- [ ] รวม planning docs เก่าที่ซ้ำกันใน `plan/` และ `docs/planning/`
- [ ] ทำ index ของเอกสารใน `plan/`, `docs/`, `reports/`
- [ ] แยก changelog, snapshot, report, backlog ให้ใช้รูปแบบชื่อไฟล์เดียวกันทั้ง repo

---

## รายการที่ไม่ควรนับว่าเป็นงานหลักแล้ว

รายการด้านล่างเคยอยู่ใน checklist เดิม แต่ไม่ควรใช้เป็น backlog ปัจจุบันอีกต่อไป เพราะมี implementation จริงแล้ว

- [x] Init FastAPI / config / middleware
- [x] OTP/Auth endpoints
- [x] Chat API endpoints
- [x] Multi-LLM support
- [x] Admin React project setup
- [x] Context management UI
- [x] Telegram bot base implementation
- [x] API key management base implementation

---

## ตัวชี้วัดจาก repo ปัจจุบัน

- [x] Admin pages ที่พบ: 23 หน้า
- [x] Unit test modules ที่พบ: 25 โมดูล
- [x] Integration test modules ที่พบ: 9 โมดูล
- [x] Telegram modules ที่พบ: bot, dispatcher, handlers, auth, formatters, chart renderer

---

## Suggested execution order

1. แก้ security/reliability debt ที่ยืนยันได้จาก audit
2. แยกไฟล์ monolith ให้อ่านและทดสอบได้ง่ายขึ้น
3. ปิดช่องว่าง reports/export
4. ทำ deployment/CI/CD ให้พร้อมใช้งานจริง
5. polish UX ฝั่ง Expo และ admin
