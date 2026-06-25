# AI Assistant - Code Audit Report

> ประเภทเอกสาร: technical audit / hardening report
> Refreshed against current source: 2026-03-22
> เดิมสร้างครั้งแรก: 2026-03-16
> จุดประสงค์: แยกให้ชัดว่าอะไร “ยังเป็น finding ปัจจุบัน”, อะไร “แก้แล้ว”, และอะไร “ไม่ควรถูกระบุผิดซ้ำ”

---

## Executive Summary

โค้ดเบสนี้มี capability ทางผลิตภัณฑ์สูงกว่าที่เอกสารเก่าเคยระบุไว้มาก แต่ยังมี technical debt เชิงสถาปัตยกรรมและความเสถียรค่อนข้างหนัก

### สิ่งที่ยืนยันจาก source ปัจจุบัน

- Telegram integration มี implementation จริงแล้ว
- SSE streaming endpoint มีแล้ว
- Stateless query API และ API key management มีแล้ว
- Admin platform ครอบคลุมหลายโดเมนมาก
- pytest suite มีทั้ง unit และ integration แล้ว
- hardcode absolute path แบบ `/Users/seal/...` ใน source กลุ่มที่เพิ่งแก้ ไม่มีแล้ว
- frontend/admin ใช้ env-driven API URL แล้ว โดย localhost fallback ถูกจำกัดไว้สำหรับ dev path

### ความเสี่ยงหลักที่ยังเหลือ

- ไฟล์ monolith ขนาดใหญ่มากหลายไฟล์
- broad exception จำนวนมาก
- SQL interpolation ที่ยังยืนยันได้ในบาง service
- global in-memory cache/state ยังมีความเสี่ยงสำหรับ multi-worker execution
- deployment hardening และ CI/CD ยังไม่ใช่ source of truth ที่ชัดเจน

---

## Current Metrics

Metrics ด้านล่างตรวจจาก repo ปัจจุบันโดยตรง

| Metric | Current value |
| --- | --- |
| `app/api/v1/admin.py` | 2639 lines |
| `app/services/ai_service.py` | 1732 lines |
| `app/services/schema_service.py` | 1769 lines |
| `frontend-admin/src/pages/Settings.tsx` | 598 lines |
| `frontend-admin/src/pages/HierarchyManager.tsx` | 566 lines |
| `frontend-admin/src/pages/Analyzer.tsx` | 449 lines |
| `except Exception` ใน `app/` | 236 matches |

---

## Confirmed Current Findings

## 1. SQL Interpolation ยังมีอยู่บางจุด

### 1.1 Dynamic view creation ใน `schema_service.py`

ยืนยันได้ว่ายังมี:

```python
sql = f"CREATE VIEW {view_name} AS SELECT {select_clause} FROM {source_table}"
```

ความเสี่ยง:

- ถึงแม้มี validation บางส่วน แต่ยังเป็น string interpolation บน SQL identifier
- ถ้า validation หรือ whitelist ไม่แน่นพอ จะเปิดช่องให้เกิด malformed SQL หรือ injection path ได้

ข้อเสนอ:

- แยก identifier validation เป็น helper กลาง
- whitelist table/view names จาก schema จริง
- log และ reject invalid identifiers ทุกกรณี

### 1.2 SQLite schema lookup ใน `vanna_service.py`

ยืนยันได้ว่ายังมี:

```python
text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
```

ความเสี่ยง:

- ยังเป็น direct interpolation บน SQL text
- ควรเปลี่ยนเป็น named parameter ทันที

ข้อเสนอ:

```python
text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:table")
```

---

## 2. Broad Exception Handling ยังสูงมาก

จำนวน `except Exception` ที่พบใน `app/` ปัจจุบัน: **236 จุด**

ไฟล์ที่เห็นชัดว่ายังหนัก:

- `app/services/ai_service.py`
- `app/services/schema_service.py`
- `app/services/context_onboarding.py`
- `app/services/admin_config_service.py`
- `app/api/v1/admin.py`
- `app/api/v1/chat.py`

ผลกระทบ:

- ทำให้ root cause analysis ยาก
- เสี่ยงกลบ error ที่ควร fail fast
- ทำให้ behavior ใน production ไม่แน่นอน โดยเฉพาะ async/background paths

ข้อเสนอ:

- แทนที่ด้วย specific exception ตาม domain
- ห้าม `except Exception: pass` ใน logic สำคัญ
- ถ้าจำเป็นต้องกันแอปล้ม ให้ log พร้อม `exc_info=True`

---

## 3. Monolith Files ยังเป็นปัญหาเชิง maintainability สูง

ไฟล์ที่ควรแตกก่อน:

### 3.1 `app/api/v1/admin.py` - 2639 lines

ปัญหา:

- รวมหลาย bounded contexts ไว้ในไฟล์เดียว
- review/test/ownership ยาก
- regression risk สูงทุกครั้งที่แก้ admin API

ข้อเสนอแบ่งขั้นต่ำ:

- schema
- mappings/rules/examples
- providers/models/settings
- hierarchy
- contexts/onboarding
- query logs / analytics / api keys

### 3.2 `app/services/ai_service.py` - 1732 lines

ปัญหา:

- orchestration, prompting, explanation, provider fallback, confidence handling, business logic ปนกันมาก

### 3.3 `app/services/schema_service.py` - 1769 lines

ปัญหา:

- metadata, views, prompts, cache, context logic ปนใน service เดียว

ผลกระทบรวม:

- unit test isolation ยาก
- blame ownership ไม่ชัด
- defect localization ช้า

---

## 4. In-Memory Shared State ยังต้องทบทวน

จาก codebase ปัจจุบันยังมี pattern ของ cache/store/global state กระจายอยู่หลาย service

ความเสี่ยง:

- ไม่ชัดเจนเรื่อง thread/process safety เมื่อรันหลาย worker
- cache stampede หรือ stale state อาจเกิดได้
- behavior อาจต่างกันระหว่าง dev กับ production

ข้อเสนอ:

- จัดกลุ่ม cache patterns ให้เป็นมาตรฐานเดียว
- ใช้ Redis หรือ thread-safe TTL cache ในจุดที่แชร์ state ข้าม request สำคัญ
- ระบุ invalidation strategy ต่อ service ให้ชัด

---

## 5. Deployment Hardening ยังไม่ครบ story

สิ่งที่มีแล้ว:

- `docker-compose.prod.yml`
- `.env.example`
- `frontend/.env.example`
- `frontend-admin/.env.example`
- runtime config hardening บางส่วนสำหรับ API URL / business DB path

สิ่งที่ยังไม่ชัด:

- CI/CD pipeline
- reverse proxy / SSL setup
- production runbook ชุดเดียวที่ใช้จริง
- infra security checklist ที่ enforce ได้จริง

ผลกระทบ:

- deploy ซ้ำข้าม environment ยังเสี่ยง drift
- on-call / handoff ให้ทีมอื่นยังใช้ effort สูง

---

## 6. Frontend / Admin Maintainability Debt

ไฟล์ใหญ่ฝั่ง admin ที่ยังควรแตก:

- `Settings.tsx` - 598 lines
- `HierarchyManager.tsx` - 566 lines
- `Analyzer.tsx` - 449 lines

หมายเหตุ:

- capability ฝั่ง admin มีเยอะและค่อนข้างครบ
- แต่ component ใหญ่ทำให้แก้ regression ยากและเพิ่ม cost ใน review/testing

---

## Corrected Historical Claims

รายการด้านล่างเป็นสิ่งที่ audit/plan เก่ามักสะท้อนไม่ตรงกับ source แล้ว

- Telegram bot ไม่ได้อยู่สถานะ “ยังไม่เริ่ม”
- SSE streaming ไม่ได้เป็น TODO หลักอีกต่อไป
- Stateless query API มีแล้ว
- API key management มีแล้ว
- Admin Agent มีทั้ง backend และ UI แล้ว
- pytest suite มีทั้ง unit และ integration แล้ว
- `docker/docker-compose.prod.yml` มีแล้ว

---

## Resolved / Reduced Risks Since Previous Snapshot

จากการตรวจล่าสุด สามารถนับว่าความเสี่ยงด้านล่าง “ลดลงแล้ว” เมื่อเทียบกับปัญหา hardcode ที่เคยพบ

### 1. Frontend API URL hardcode

สถานะปัจจุบัน:

- frontend user app ใช้ `EXPO_PUBLIC_API_URL`
- frontend admin ใช้ `VITE_API_URL`
- localhost fallback ถูกจำกัดไว้สำหรับ development path

### 2. Absolute path ใน scripts

สถานะปัจจุบัน:

- script กลุ่มที่แก้แล้วใช้ helper กลางสำหรับ `BUSINESS_DB_PATH` และ `API_BASE_URL`
- ไม่ยึดติดกับ `/Users/seal/...` แล้ว

### 3. Redis/CORS fallback ที่ production เสี่ยงใช้ค่า local แบบเงียบ ๆ

สถานะปัจจุบัน:

- config บังคับให้ env สำคัญต้องถูกตั้งใน production-like environment มากขึ้น

หมายเหตุ:

- localhost ที่ยังพบใน source ตอนนี้เป็น dev-only fallback หรือ env example ซึ่งถือว่ายอมรับได้ตาม design ปัจจุบัน

---

## Recommended Next Actions

1. แก้ SQL interpolation ที่ยืนยันได้ใน `schema_service.py` และ `vanna_service.py`
2. ลด `except Exception` ในไฟล์ top offenders ก่อน
3. แยก `admin.py`, `ai_service.py`, `schema_service.py`
4. กำหนด cache strategy เดียวทั้งระบบ
5. ทำ deployment/CI story ให้ครบและมี source of truth เดียว

---

## Files Verified During Refresh

- `app/main.py`
- `app/api/v1/chat.py`
- `app/api/v1/query.py`
- `app/api/v1/admin.py`
- `app/api/v1/admin_agent.py`
- `app/services/schema_service.py`
- `app/services/vanna_service.py`
- `app/telegram/bot.py`
- `frontend/services/api.ts`
- `frontend-admin/src/services/api.ts`
- `tests/conftest.py`
- `tests/unit/`
- `tests/integration/`
