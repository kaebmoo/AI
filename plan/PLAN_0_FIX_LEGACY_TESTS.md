# Plan 0: Fix 15 Legacy Test Failures

**Priority:** ทำก่อนทุกอย่าง  
**ประมาณเวลา:** 1 วัน  
**Prerequisite:** ไม่มี  
**อ้างอิงจาก:** ผลทดสอบ Context Onboarding (194 passed, 15 failed)

---

## สรุปปัญหา

15 tests fail จาก refactoring Phase 1-3 ที่ย้าย code จาก `ai_service.py` ไป provider registry แต่ไม่ได้ update tests ตาม

## กลุ่มที่ 1: `validate_sql` ถูกลบ (10 tests)

**ไฟล์:** `tests/unit/test_ai_service.py` class `TestAIServiceValidation`

**สาเหตุ:** `AIService` ไม่มี method `validate_sql()` แล้ว -- ถูกย้ายไป `QueryEngine` ตอน refactoring

**วิธีแก้:**
- ตรวจว่า `validate_sql` ยังมีอยู่ที่ไหน: grep ใน `query_engine.py`, `database_service.py`
- ถ้ามี → ย้าย tests ไปอ้าง class ใหม่
- ถ้าไม่มี (SQL validation ถูกรวมเข้า MCP flow แล้ว) → ลบ class `TestAIServiceValidation` ทั้ง class

## กลุ่มที่ 2: Mock Anthropic ผิด (1 test)

**ไฟล์:** `tests/unit/test_ai_service.py` → `test_generate_sql_with_tool_use`

**สาเหตุ:** Test patches `anthropic.Anthropic` (sync) แต่ code ใช้ `anthropic.AsyncAnthropic` แล้ว

**วิธีแก้:**
- แก้ test ให้ patch `anthropic.AsyncAnthropic`
- เปลี่ยนเป็น `@pytest.mark.asyncio` + `async def test_...`
- หรือ mock ที่ level `ClaudeProvider.client` property แทน

## กลุ่มที่ 3: `PromptVersion` / `PromptManager` ถูกลบ (4 tests)

**ไฟล์:** `tests/unit/test_feedback_service.py` class `TestPromptVersion` (2 tests)  
**ไฟล์:** `tests/unit/test_phase_completion.py` class `TestPhase35FeedbackLoop` (2 tests)

**สาเหตุ:** `PromptVersion` model และ `PromptManager` service ถูกลบระหว่าง refactoring -- prompt management ถูกรวมเข้า `schema_contexts.instruction_th` (DB-driven)

**วิธีแก้:**
- ลบ class `TestPromptVersion` จาก `test_feedback_service.py`
- ลบ `test_prompt_manager_exists` + `test_feedback_models_exist` จาก `test_phase_completion.py`
- แก้ `test_feedback_models_exist` ให้ไม่ import `PromptVersion`

---

## Claude Code Instructions

```
## สิ่งที่ต้องอ่านก่อน
- tests/unit/test_ai_service.py
- tests/unit/test_feedback_service.py
- tests/unit/test_phase_completion.py
- app/services/query_engine.py (grep "validate_sql")
- app/services/ai_service.py (confirm validate_sql ไม่มีแล้ว)

## ขั้นตอน
1. grep -rn "validate_sql" app/ เพื่อหาว่า method อยู่ที่ไหน
2. ถ้าอยู่ใน query_engine.py → ย้าย tests ไป test_query_engine.py (สร้างใหม่ถ้าไม่มี)
3. ถ้าไม่มีที่ไหนเลย → ลบ class TestAIServiceValidation ทั้ง class
4. แก้ test_generate_sql_with_tool_use ให้ mock AsyncAnthropic
5. ลบ TestPromptVersion class จาก test_feedback_service.py
6. แก้ TestPhase35FeedbackLoop ใน test_phase_completion.py
7. รัน: python -m pytest tests/ -v --tb=short
8. เป้าหมาย: 209/209 passed, 0 failed

## ห้าม
- ห้ามลบ test ที่ยังใช้ได้ (ลบเฉพาะที่อ้าง code เก่าที่ไม่มีแล้ว)
- ห้ามแก้ production code เพื่อให้ test ผ่าน
- ห้ามเพิ่ม skip marker แทนการแก้จริง
```
