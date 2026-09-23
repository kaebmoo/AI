# PROMPT — ให้ผู้ตรวจ (Codex) ตรวจรอบ 2: การแก้ตามผลตรวจ 9 ข้อ + pin CI

repo `/Users/seal/Documents/GitHub/AI` (branch `main`) · รอบแรกคุณตรวจ `0078dcf..0868447` และพบ 9 ข้อ — รอบนี้ตรวจว่า
**การแก้ปิดจริงไหม และการแก้สร้างรูใหม่หรือเปล่า**

## ขอบเขต
`git log 0868447..369390c` (7 commit):

| commit | สิ่งที่ทำ |
|---|---|
| `8906cd5` | frontend: pivot บอกว่าโหลดไม่สำเร็จแทนค้าง Loading (โหลด library แบบ lazy จาก dev server) |
| `39c2003` | กฎ: `learned` แก้ได้เฉพาะข้อเสนอที่ยังรอ · `replaceable()` (may_replace เป็น SQL) · `propose()` ใช้ `json_set` · `missing_provenance()` · `mark_human_edit` เปิดแถวเมื่อคนรับ |
| `ddd58bf` | ตัวเขียน: golden ของ contract ทีละ row id · `_declare` ตรวจ provenance ในคำสั่งเขียน + INSERT ที่ชนแถวใหม่ · ไม่ถอนแถว `rejected` · `/chat/train` + ตัวเรียนรู้ (is_active=0) · onboarding รวมข้อเสนอทีละช่อง |
| `e7a732a` | migration: label + trigger + คิว ใน transaction เดียวที่เริ่มเอง (`isolation_level=None`, `BEGIN IMMEDIATE`) |
| `487d21e` | ตัวอ่าน: DDL ของ Vanna กรอง `status` · พจนานุกรมคำ + ชื่อที่ใช้ตรวจระดับชั้น ดูสถานะของระดับแม่ |
| `7cdc7af`, `369390c` | เอกสาร: `RESULT_P8_PHASE1.md` §14 (ตาราง 9 ข้อ + หลักฐาน), FIX_NOTES, รายงาน F1–F8 + หัวข้อตรวจต่อ |
| `36d1867` | `requirements.txt`: `mcp>=1.26.0` → `mcp==1.26.0` (CI แดง 8/8 รอบตั้งแต่ 2026-09-18 เพราะ mcp 2.x) |

สิ่งที่ประกาศไว้และต้องถูกตรวจว่าตรงกับ code จริง: `plan/archive/RESULT_P8_PHASE1.md` **§14** (ตารางข้อ 1–9, หลักฐาน,
คำกล่าวที่ว่า "prompt ไม่เปลี่ยน") และ `CLAUDE.md` หัวข้อ Plan 8.1

## สิ่งที่ต้องยืนยัน
1. **9 ข้อเดิมปิดจริง** — ลอง reproduce เคสเดิมของแต่ละข้อบน DB จำลองอีกครั้ง ถ้ายังทำซ้ำได้ ถือว่ายังไม่ปิด
2. **`replaceable()` = `may_replace()` ทุกกรณี** (source × status × writer รวม NULL และ `'auto'`) และทุกจุดที่เขียนใช้เงื่อนไขนี้จริง
   ไม่ใช่แค่บางที่ — ไล่ให้ครบทั้ง repo
3. **`propose()` / `merged_proposal()`** — การ escape ชื่อคอลัมน์ใน JSON path (`"`, `$`, จุด), ค่า null, ค่าที่ไม่ใช่ scalar,
   เงื่อนไข "ไม่เขียนซ้ำ" (rejected / proposed ที่ครอบคลุมอยู่แล้ว), และ race ระหว่างอ่านข้อเสนอเดิมกับ `INSERT … ON CONFLICT`
4. **`_declare()`** — `INSERT … ON CONFLICT DO NOTHING` + อ่านใหม่ + `rowcount`: ครบทุกเส้นทางไหม (แถวถูกลบระหว่างนั้น,
   ตารางที่มี UNIQUE หลายชุด, `updated_at` / `stamp`, การนับ "ไม่มีอะไรเปลี่ยน = ไม่เขียน")
5. **`save_examples()`** — คำถามซ้ำหลายแถว, แถว `rejected`, การนับ written / withdrawn / queued, DELETE ที่มีเงื่อนไข provenance,
   และกรณี rowcount ไม่เท่าที่ตั้งใจ (แถวเปลี่ยนมือกลางคัน)
6. **ทางของคนกับข้อเสนอ** — `/chat/train`, ตัวเรียนรู้ (`is_active=0`), `mark_human_edit` ที่เปิดแถวให้เมื่อคนรับ:
   admin API **ทุกทาง** (mappings, golden, rules, warnings, vanna docs, hierarchy — ทั้ง create และ update) ตั้ง
   `status` + `is_active` ตรงกันหรือยัง มีทางไหนที่รับข้อเสนอแล้วแถวยังปิดอยู่ไหม
7. **migration** — `isolation_level=None` + `BEGIN IMMEDIATE` บน connection ของ SQLAlchemy pool: connection ถูกคืน pool
   ในสถานะเดิมไหม, รันซ้ำปลอดภัยไหม, เกิดอะไรถ้า server กำลังเปิด DB อยู่ (`database is locked`), และ WAL / journal
8. **ตัวอ่าน** — ยังมีที่ไหนส่งความรู้ให้ LLM / RAG / routing / สิทธิ์ของ key โดยไม่กรอง `status` อีกไหม: รวม `mcp_servers/*`,
   `app/tools/admin/*`, `multi_context.py`, `warning_detector`, `validation_service`, การ rebuild keyword index, และ Vanna ทุกเส้นทาง train
9. **`mcp==1.26.0`** — code ใช้ API ที่ 1.26 มีจริงทั้งหมดไหม, มีที่อื่นใน repo ที่ระบุเวอร์ชันขัดกันไหม, และการ pin นี้พอทำให้ CI
   ผ่าน collection ไหม (นอกนั้นรู้หลัง push)
10. **เอกสาร** — §14 ของ RESULT, FIX_NOTES และหัวข้อ "ตรวจต่อ 2026-09-22" ในรายงาน F1–F8: ข้อความตรงกับ code และข้อเท็จจริงไหม
    (รวมคำกล่าวว่าตัวอ่านให้ผลเท่าเดิมทุกไบต์บนสำเนาของจริง)

## ข้อจำกัด (สำคัญ)
- **ของจริงอ่านอย่างเดียว**: ห้ามเขียน DB จริง, ห้าม migrate, ห้าม restart, ห้ามแตะ port 8000 (AI server) และ 8090 (PocketBase),
  **ห้ามใช้ API key ของ portal (id 4)**, NT-Report = อ่านอย่างเดียว
- จะรัน test ให้ใช้ `venv/bin/python3.14 -m pytest -q -p no:cacheprovider` และ export `CONFIG_DB_URL` / `DATABASE_URL` /
  `DATA_SOURCE_CACHE_DIR` ไปยัง**สำเนา** (`venv/bin/python` คือ 3.10 ไม่มี pytest — รอบที่แล้วติดตรงนี้)
- **ห้ามแก้ไฟล์ใน repo** — รายงานอย่างเดียว เจ้าของจะสั่งแก้เอง

## รูปแบบรายงาน
- ต่อข้อ: severity (P1/P2/P3) · ไฟล์ + บรรทัด · **วิธี reproduce ที่รันจริง** (คำสั่ง/สคริปต์ + ผลที่ได้) · ผลที่ควรเป็น · ข้อเสนอการแก้
- แยกให้ชัดระหว่าง "ตรวจแล้วไม่พบปัญหา" กับ "ยังไม่ได้ตรวจ"
- ปิดท้าย: **Exit ของ 8.1 ถือว่าผ่านหรือยัง** ถ้ายัง ขาดอะไรบ้าง
