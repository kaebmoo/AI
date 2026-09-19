# Plan 7 Phase 5 — คำถามข้ามหลาย context (2026-09-19)

แผน: `plan/PLAN_7_DATA_SOURCE_SERVICE.md` §5 Phase 5 · ผล + ตารางสำรวจ + eval: `plan/archive/RESULT_P7_PHASE5.md`

## สิ่งที่เปลี่ยนสำหรับผู้ใช้ / ผู้ดูแล

| เรื่อง | ก่อน | หลัง (เมื่อเปิด) |
|---|---|---|
| "รายได้และค่าใช้จ่ายเดือนกรกฎาคม 2569" ผ่าน `/api/v1/query` | router เลือก context เดียว (`feed_expense`) → ตอบค่าใช้จ่ายอย่างเดียวใต้หัวข้อ "สรุปรายได้และค่าใช้จ่าย" | แตกเป็นคำถามย่อยต่อ context → ตอบทั้งสองตัวเลข แต่ละตัวพร้อม context, คำถามย่อย, SQL, งวดข้อมูล |
| อัตราส่วน / ส่วนต่างข้ามโดเมน | ไม่ได้ (หรือป้ายตัวเลขผิด) | คำนวณ**ใน code** จากผลของคำถามย่อย; ส่วนต่างติดป้าย "ไม่ใช่กำไร / EBT ทางการ" |
| งวดของ source ไม่เท่ากัน | ไม่มีใครบอก | บรรทัดเตือน + งวดของแต่ละส่วน; ไม่คำนวณข้ามส่วน |
| ส่วนที่ตอบไม่ได้ | — | "ตอบได้ k จาก n ส่วน" + เหตุผลต่อส่วน; ไม่เดาตัวเลข |
| response ของ `/api/v1/query` | — | + `parts[]`, `computed` (`null` เมื่อเป็นคำตอบ context เดียว) |
| audit | 1 แถวต่อคำถาม | แถวแม่ + แถวคำถามย่อย โยงด้วย `request_group` (filter ใหม่ใน `GET /admin/query-audit`) |

**ปิดเป็นค่าเริ่มต้น** — พฤติกรรมเดิมทุกอย่างจนกว่า admin จะเปิดต่อ workspace:
```bash
curl -X PUT -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" \
  -d '{"enabled": true}' http://localhost:8000/api/v1/admin/workspaces/2/multi-context   # 2 = id ของ nt-report (GET /admin/workspaces)
```
ไม่ต้อง migrate. ใช้ที่ `/api/v1/query` เมื่อผู้เรียกไม่ส่ง `context`; chat / telegram ยังเป็น context เดียว.
ยังไม่แนะนำให้เปิดกับ workspace `default` — keyword ของ context เดิมปนกัน (ดู `plan/FIX_NOTES.md`)

## ขอบเขตที่บังคับ
ไม่ข้าม workspace · เฉพาะ context ในสิทธิ์ของ key (ชื่ออื่นไม่เข้า prompt) · `scope` ใช้กับทุกคำถามย่อย (context ใดไม่ประกาศ = 400 ทั้งคำถาม) ·
403 ของข้อย่อย = 403 ทั้งคำถาม · provider call ของตัวแตกคำถามรันใต้ policy เข้มสุด + intersection ของ provider allowlist ·
ขั้นรวมคำตอบไม่มี LLM · ไม่ JOIN ข้าม source — รายละเอียด `docs/DEPLOYMENT_SECURITY.md`, รูป response `docs/PORTAL_INTEGRATION.md`

## ไฟล์หลัก
- `app/services/multi_context.py` — `candidates` (deterministic), `_split` (LLM 1 call) + `parse_split`, `compute`, `combine`, `answer` / `ask`
- `app/services/query_engine.py` — `_provider_for` (แยกจาก `_execute_query`), `query(request_group=…)`
- `app/services/query_audit.py`, `app/models/query_audit.py` — `request_group` + `ensure_table`
- `app/api/v1/admin/workspaces.py` — `PUT /admin/workspaces/{id}/multi-context`; `GET /admin/workspaces` แสดง `multi_context`
- `app/api/v1/query.py` — เรียกผ่าน `multi_context.ask`, `parts` / `computed`
- `scripts/eval/run_eval.py --cross-domain scripts/eval/cross_domain_golden.json` — eval 10 ข้อ (ตัวเลขคาดหวังมาจาก SQL ตรวจมือที่รันกับ source ตอน eval)
- `tests/unit/test_multi_context.py` (รวม sentinel: source A = `full`, B = `schema_only`), `tests/unit/test_simple_query.py::TestMultiContextResponse`
