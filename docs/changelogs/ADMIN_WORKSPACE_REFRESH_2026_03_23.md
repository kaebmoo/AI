# Admin Workspace Refresh and Vanna Ops Update

**Date:** 2026-03-23
**Scope:** Admin web refresh, runtime config alignment, browser QA hardening, Vanna ops visibility

## Summary

รอบนี้เน้นแก้ pain point ที่เห็นจริงจากการใช้งาน admin:

- sidebar ยาวและ scroll ยาก
- dashboard อ่อนและใช้ข้อมูล hardcoded
- provider/model แสดงไม่ตรงกันระหว่างหลายหน้า
- browser QA เจอ CORS และ layout issues ใน dev
- Vanna ops ยังไม่ชัดว่า knowledge เปลี่ยนแล้วต้อง sync เมื่อไร

## Delivered

### 1. Admin shell refresh

- จัดเมนูใหม่เป็นหมวด Overview, AI Setup, Data Setup, Monitoring, System
- sidebar มี scroll region ของตัวเอง
- จำสถานะ open keys ของเมนู
- route change scroll content กลับขึ้นบนอย่าง predictable
- header แสดง section/title ชัดขึ้นและลดปัญหา duplicate heading

### 2. Dashboard rebuild

- เพิ่ม `GET /api/v1/admin/dashboard-overview`
- Dashboard ดึง runtime config, usage, feedback, coverage, และ alerts จาก backend จริง
- เพิ่ม quick actions สำหรับ refresh schema cache, sync brain, และ clear query cache

### 3. Provider/model alignment

- เพิ่ม `GET /api/v1/admin/config/ai/effective`
- `AdminConfigService` sync default flags ระหว่าง `admin_config`, `ai_providers`, `ai_models`
- invalidation ของหน้า Providers/Models ทำให้ Dashboard refresh ตาม

### 4. Browser QA fixes

- เพิ่ม dev CORS fallback regex สำหรับ localhost/127.0.0.1
- อัปเดต `.env.example` และ `README.md` ให้ระบุพอร์ต 5173/5175
- แก้ Feedback layout ที่ทำให้ปุ่ม Review กดยาก
- เก็บ Ant Design deprecation ใน Dashboard, Feedback, Context Onboarding, Admin Agent
- เพิ่ม AntD runtime bridge เพื่อลด warning จาก static `message/notification/modal`

### 5. Admin performance follow-up

- เปลี่ยน `frontend-admin/src/App.tsx` เป็น route-level lazy loading
- initial admin bundle แตกเป็น route chunks แล้ว แม้ shared chunk ยังใหญ่พอควร

### 6. Vanna ops visibility

- มีหน้า `Vanna Knowledge` สำหรับจัดการ `vanna_documentation`
- brain freshness ใช้ `last_brain_sync_at` และ `last_brain_relevant_change_at`
- routes ที่กระทบ corpus หลัก mark brain dirty หลัง mutation

## Validation

- `frontend-admin` build ผ่าน
- Python syntax validation ฝั่ง backend ผ่าน
- browser QA ครอบคลุม Dashboard, Providers, Models, API Keys, Vanna Knowledge, Admin Agent
- login ใช้งานได้บน dev ports ที่เกี่ยวข้องหลังปรับ CORS

## Deferred to next round

- admin secondary-page consistency pass
- dashboard/API contract tests
- vendor chunk reduction เพิ่มเติม
- Vanna retrieval quality verification หลังเปลี่ยน corpus เป็น DB-driven