# PROMPT — portal เรียงคอลัมน์ของตารางคำตอบผิด (ฝั่ง NT-Report, Phase 4.2 ของ `PLAN_ANOMALY_AVG_FIX.md`)

> รันใน repo **NT-Report** · แผนเต็มอยู่ใน repo AI: `plan/PLAN_ANOMALY_AVG_FIX.md` (F8 ใน §1, Phase 4 ใน §7)
> งานเล็ก: 2 ไฟล์ + test — ทำใน worktree, ห้าม deploy / ห้ามรัน `pocketbase_0/scripts/sync_to_prod.sh` จนกว่าเจ้าของสั่ง

---

## 1. ปัญหา

ตารางคำตอบใน panel "ถามข้อมูลรายงานนี้" แสดงคอลัมน์**เรียงตามตัวอักษร** ไม่ใช่ลำดับที่ SQL เลือก — คำตอบจริง 2026-10-28 (รายงานยอดขาย งวด 2569-09)
ได้หัวตาราง `รายได้เฉลี่ยก่อนกันยายน | รายได้เดือนกันยายน | ส่วนต่างรายได้ | หน่วยงาน | เปอร์เซ็นต์เปลี่ยนแปลง` = เรียงตาม Unicode พอดี
(ชื่อหน่วยงานควรอยู่คอลัมน์แรก)

สาเหตุที่น่าจะเป็น (ยืนยันในข้อ 3):
- `pocketbase_0/pb_hooks/assistant.pb.js` อ่าน `res.json` ของ `$http.send` (Go แปลง JSON เป็น map) แล้วส่ง `payload.data` ต่อด้วย `e.json(...)`
  → Go เรียง key ของ map ตามตัวอักษรตอน marshal
- `pocketbase_0/pb_public/assets/ask.js` ใช้ `Object.keys(rows[0])` เป็นหัวตาราง (`renderTable`) และหัว CSV (`toCsv`)
- test ของ hook (`scripts/test_assistant_hook.js`) ป้อน JS object ตรง ๆ จึงไม่เห็นการเรียงของ Go
- ลำดับ**แถว**ไม่เสีย (เป็น array)

ฝั่ง AI จะเพิ่ม field `columns` (list ลำดับคอลัมน์ของผลลัพธ์) ใน response ของ `POST /api/v1/query` (Phase 4.1) — field เพิ่ม ไม่กระทบของเดิม

## 2. ก่อนเริ่ม

- อ่าน `CONVENTIONS.md` §0 และ `pocketbase_0/README.md` / `pocketbase_0/DEPLOY_NOTES.md` ส่วน local dev
- worktree: `git worktree add ../_worktrees/NT-Report-anomaly -b ai/portal-columns main`
- ถ้าจะลองบน PocketBase local: `.env` ของ local ต้องชี้ `ASSISTANT_API_URL` ไป **server ซ้อมของ AI (port 8001+)** ด้วย **key ซ้อม** —
  **ห้ามใช้ key ของ portal (AI key id 4)** และห้ามชี้ไป server จริงของ AI (port 8000)

## 3. ยืนยันสาเหตุก่อนแก้

- รัน PocketBase local (`./scripts/serve.sh --http=127.0.0.1:8091`) ด้วยโค้ดปัจจุบัน → ถามคำถามที่ได้ตารางหลายคอลัมน์ชื่อไทย
  (เช่น "ยอดขายแยกตามฝ่าย 5 อันดับแรก") → เทียบลำดับหัวตารางกับ `result_columns` ของแถวนั้นใน `query_audit` (app.db ของ **server ซ้อม** AI)
- ถ้าลำดับตรงกันอยู่แล้ว (สาเหตุไม่ใช่ข้อ 1) → **หยุด** แจ้งเจ้าของพร้อมสิ่งที่เห็น

## 4. แก้

1. `pocketbase_0/pb_hooks/assistant.pb.js` — ในผลลัพธ์ 200 เพิ่ม
   `columns: Array.isArray(payload.columns) ? payload.columns.filter(c => typeof c === "string") : null`
   (array คงลำดับผ่าน Go ได้)
2. `pocketbase_0/pb_public/assets/ask.js`
   - `renderTable(rows, rowCount, columns)` และ `toCsv(rows, columns)`: หัวตาราง = `columns` ที่กรองเหลือเฉพาะ key ที่มีใน `rows[0]`
     ต่อด้วย key ที่ `columns` ไม่มี (ตามลำดับ `Object.keys`); ไม่มี `columns` = `Object.keys(rows[0])` เหมือนเดิม
   - จุดเรียก: `renderTable(res.data, res.row_count || 0, res.columns)` และ CSV เก็บ `columns` คู่กับ `rows` ใน `csvStore`
3. tests
   - `pocketbase_0/scripts/test_assistant_hook.js`: upstream ส่ง `columns` → ผลลัพธ์ของ hook มี `columns` ลำดับเดิม; ไม่ส่ง → `null`; ไม่ใช่ array → `null`
   - `pocketbase_0/scripts/test_ask_markdown.js` (หรือไฟล์ test ใหม่ข้างกัน): rows ที่ key เรียงตามตัวอักษร + `columns` ลำดับ SQL →
     หัวตาราง / หัว CSV ตาม `columns`; ไม่มี `columns` → ตาม `Object.keys`; `columns` ขาดบาง key → key ที่ขาดต่อท้าย
   - รัน: `node pocketbase_0/scripts/test_assistant_hook.js && node pocketbase_0/scripts/test_ask_markdown.js` → ผ่านทั้งหมด

## 5. Acceptance

- test ข้อ 4.3 ผ่าน + test เดิมทั้งสองไฟล์ผ่าน
- PocketBase local + server ซ้อม AI ที่มี Phase 4.1 แล้ว: หัวตาราง = ลำดับใน SQL (`result_columns`) ทั้งบนหน้าเว็บและใน CSV
- PocketBase local + server ซ้อม AI ที่**ยังไม่มี** Phase 4.1: หน้าเว็บทำงานเหมือนเดิม (fallback)
- commit บน `ai/portal-columns` (ตามรูปแบบ commit ของ repo) + บรรทัดใน `pocketbase_0/CHANGELOG.md`
- สรุปให้เจ้าของ: ผลยืนยันสาเหตุ (ข้อ 3), ผล test, ภาพหัวตารางก่อน/หลัง — **ไม่ deploy เอง**
