# PLAN F8 — Structured Output สำหรับ Intent Extraction (Pass 1) และ JSON tasks

> **ตรวจ source ซ้ำ 2026-09-21:** แผนนี้มี implementation แล้ว ไม่ต้อง execute ซ้ำ; สถานะรายข้อ หลักฐาน และ acceptance ที่ยังค้างดู [รายงาน F1–F8](../REVIEW_F1_F8_2026-09-21.md) ข้อความและ checklist ด้านล่างคงไว้เป็นแผนในอดีต

**Prerequisite:** PLAN_F2 เสร็จ (แนะนำหลัง F7 เพื่อให้ usage tracking ครอบ method ใหม่ด้วย)
**ประมาณเวลา:** 1-2 วัน
**ขอบเขต:** ใช้ความสามารถ native ของ provider ที่มีอยู่ — **ไม่เพิ่ม dependency ใหม่**
**หมายเหตุความเสี่ยง:** Two-pass ปัจจุบัน default OFF (`TWO_PASS_ENABLED=False`) — แผนนี้ทำให้ Pass 1 แข็งแรงพอจะเปิดใช้จริง แต่**การเปิด flag เป็น decision แยก** วัดด้วย eval (F3-B) ก่อน

## READ FIRST

- `app/services/ai/hybrid_flow.py::extract_intent` + `build_pass2_prompt`
- `app/services/ai/response_utils.py` ← ยังไม่เคย review — ดู `parse_intent_json`, `extract_sql` ของจริง
- `app/providers/base.py`, ทั้ง 3 provider files (matcha/gemini ยังไม่เคย review)
- `app/services/ai/service.py::suggest_mappings` (JSON task อีกจุด)
- SDK docs ตามเวอร์ชันที่ติดตั้ง: Anthropic tool use + `tool_choice`, OpenAI `response_format json_schema`, google-genai `response_schema`

---

## F8.1 — Interface ใหม่บน AIProvider

`providers/base.py`:

```python
async def generate_structured(
    self,
    prompt: str,
    schema: Dict[str, Any],          # JSON Schema (draft ที่ทุกเจ้ารองรับ: type/properties/required/enum)
    system_prompt: Optional[str] = None,
    schema_name: str = "result",
) -> Optional[Dict]:
    """คืน dict ตาม schema หรือ None ถ้า provider ทำไม่ได้/response ไม่ valid — caller ต้องมี fallback เสมอ"""
    return None   # default: ไม่รองรับ
```

Implement ต่อ provider:
- **Claude:** forced tool call — สร้าง tool เดียว `{"name": schema_name, "input_schema": schema}` + `tool_choice={"type": "tool", "name": schema_name}` → อ่าน `content` block ที่ `type=="tool_use"` คืน `.input`; ห้ามใส่ temperature+top_p คู่กัน (บทเรียน F2.6)
- **Matcha (OpenAI-compatible):** ลอง `response_format={"type":"json_schema","json_schema":{"name":schema_name,"schema":schema,"strict":True}}` → ถ้า gateway ตอบ error ว่าไม่รู้จัก parameter: retry อัตโนมัติด้วย `{"type":"json_object"}` + ยัด schema ลง prompt → parse; ถ้ายังพัง คืน None (จำผล capability ต่อ instance กันลองซ้ำทุก call)
- **Gemini:** `config` มี `response_mime_type="application/json"` + `response_schema=schema` (แปลง JSON Schema → รูปแบบที่ google-genai ต้องการตาม SDK จริง — ถ้าแปลงยุ่งเกิน ใช้ mime_type json + schema ใน prompt แล้ว parse ก็ยอมรับได้ จดการตัดสินใจ)
- ทุกตัว: set `last_usage` (จาก F7) + validate ขั้นต่ำว่า key ใน `required` ครบก่อนคืน (ไม่ต้องใช้ jsonschema lib — เช็คมือแบบ shallow พอ)

## F8.2 — Intent schema + เปลี่ยน extract_intent

1. ประกาศ `INTENT_SCHEMA` ใน `hybrid_flow.py` (หรือ module ใหม่) ให้ตรงกับ JSON structure ที่ prompt เดิมขอทุก field: `intent_type` (enum 6 ค่า), `metrics` (array str), `aggregate_function` (enum), `dimensions`, `filters` (array object: column/operator(enum)/value), `time_range` (object year/month nullable), `ordering` (object nullable), `limit` (int nullable), `matched_mappings` (array object keyword/sql_condition) — required: `intent_type`, `metrics`, `filters` (ที่เหลือ optional เพื่อไม่บีบโมเดลเกิน)
2. `extract_intent`: 

```python
intent = await service.provider.generate_structured(intent_prompt_core, INTENT_SCHEMA, system_prompt)
if intent is None:
    # fallback = เส้นทางเดิมทั้งก้อน (generate_content + parse_intent_json)
    ...
```

`intent_prompt_core` = prompt เดิมตัดส่วน "ตอบเป็น JSON เท่านั้น/โครงสร้าง JSON" ออก (schema บังคับแทน) — คงส่วนกฎ semantic mapping / พ.ศ.→ค.ศ. / follow-up ไว้ครบ และ**แก้เลขข้อซ้ำ (4,5,5) ใน prompt เดิมไปในตัว**
3. cheap-model swap logic เดิม (try cheap → fallback default) ต้องครอบ path ใหม่ด้วย — โครง try/finally restore model เดิมใช้ต่อได้
4. log ว่า intent มาจาก `structured` หรือ `fallback_text` (เข้า trace ของ F7 ถ้ามีแล้ว)

## F8.3 — จุด JSON รองอื่น (ทำเมื่อ F8.2 นิ่ง)

- `AIService.suggest_mappings`: schema `{"suggestions": [{"col","alias","reason"}]}` ผ่าน generate_structured + fallback เดิม
- `parse_intent_json` ใน response_utils: คงไว้เป็น fallback — เพิ่ม test coverage กรณี JSON ห่อ markdown fence / มี text ปน (อ่านไฟล์จริงก่อน อาจมีแล้ว)

**ไม่ทำ:** เปลี่ยน main SQL generation path เป็น structured — CoT + ```sql fence ทำงานอยู่และการเปลี่ยนกระทบ prompt ใหญ่ ต้องมี eval คุมก่อน (จดเป็นงานอนาคตใน FIX_NOTES)

## การทดสอบ

- `tests/unit/test_generate_structured.py`: mock SDK ต่อ provider — happy path คืน dict ตรง schema; Claude ตอบไม่มี tool_use block → None; Matcha gateway reject json_schema → auto-retry json_object สำเร็จ; Gemini คืน JSON string → parse
- `extract_intent`: structured สำเร็จ → ไม่เรียก parse_intent_json; structured คืน None → fallback ทำงานและผลเท่า flow เดิม
- Manual (ต้องมี key จริง อย่างน้อย matcha): เปิด `two_pass_enabled` ชั่วคราวใน admin_config → ยิงคำถาม follow-up 3 แบบ → intent JSON ใน log ครบถ้วน ไม่มี parse warning

## Acceptance Criteria

- [ ] pytest ผ่าน + tests ใหม่ผ่าน
- [ ] เปิด two-pass แล้ว Pass 1 fail-to-parse rate = 0 ใน manual smoke (ก่อนหน้า: fallback ทั้ง flow เมื่อ parse พัง)
- [ ] Flag `TWO_PASS_ENABLED` **ยังคง default เดิม** — การเปิดถาวรเป็นคนละ decision (บันทึกใน FIX_NOTES ว่ารอเทียบ eval)
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md`
