# PLAN F9 — Agentic Latency: ลด LLM calls เคสส่วนใหญ่ เพิ่มเฉพาะเคสยาก

**Prerequisite:** Phase A,B หลัง PLAN_F7 (ต้องมี trace วัดก่อน-หลัง) / Phase C หลัง PLAN_F8 / Phase D หลัง PLAN_F2 / Phase E หลัง PLAN_F3-B + **อนุมัติแยก**
**ประมาณเวลา:** A+B = 1-2 วัน, C = 1 วัน, D = 1 วัน, E = 0.5 วัน (ไม่รวมรอบวัดผล)
**หลักการ (บังคับ):**
1. ไม่เพิ่ม dependency/framework ใหม่ — ทุกอย่างอยู่ใน custom orchestration เดิม
2. ทุก phase มี feature flag ผ่าน admin config 3-tier, **default OFF** (ยกเว้น B ที่เป็น pure code)
3. วัดก่อน-หลังด้วย trace (F7) + eval (F3-B) ทุก phase — ไม่มีตัวเลข = ไม่เปิด flag
4. accuracy > speed เสมอ: phase ไหนทำ eval ตก ห้ามเปิด

## READ FIRST

- `app/services/ai/hybrid_flow.py` (สภาพหลัง F1/F2/F7/F8)
- `app/services/ai/response_utils.py` ← ยังไม่เคย review — โครง explanation dict / chart postprocess ของจริง
- `app/api/v1/chat.py` (`_format_response`, SSE) — สัญญา response ที่ frontend ใช้
- `app/telegram/dispatcher.py` (จุด format คำตอบ + `_guess_chart_type`)
- `app/providers/registry.py` (tier/model mapping ที่มีจริง)
- `app/services/ai/retry_loop.py` (สภาพหลัง F2.6)
- grep frontend: จุด consume `explanation` / `chart_config` เพื่อยืนยัน contract ก่อนสร้าง explanation แบบ template
- `plan/RESULT_*.md` ที่มี (ถ้า F3-B/F10 รันแล้ว) เพื่อรู้ baseline

## Measurement protocol (ใช้ร่วมทุก phase)

กำหนดชุดคำถาม smoke 20 ข้อ (subset ของ golden — mix ง่าย/ยาก/follow-up) → รัน `scripts/eval/run_eval.py --limit`/ชุดนี้ ก่อนและหลังเปิดแต่ละ phase → เทียบ accuracy + latency P50/P95 ต่อ stage จาก trace → บันทึกตารางผลใน `plan/RESULT_F9.md` ทุกครั้ง flag ถูกเปิดถาวรต้องมีแถวอ้างอิงในไฟล์นี้

---

## Phase A — Template answers: ผลลัพธ์ง่ายไม่ต้องเรียก LLM อธิบาย

**เหตุผล:** explanation call คือ LLM call ที่ช้าที่สุดหลัง SQL gen ทั้งที่ผลลัพธ์จำนวนมากเป็นค่าเดียว/ตารางเล็กซึ่ง template deterministic อธิบายได้ดีกว่า (เลขไม่ถูก LLM แต่ง) — pattern เดียวกับ narrative ใน NT-Report (template-first, LLM optional)

**เงื่อนไขเข้า template path (เริ่มแคบ ค่อยขยาย):**
- ผลลัพธ์ 1 แถว × ≤3 คอลัมน์ หรือ
- ≤5 แถว × 2 คอลัมน์ (มิติเดียว + ค่าเดียว เช่น รายได้ราย BG)

**การทำ:**
1. config key `template_answers_enabled` (default false) + `template_answers_max_rows`
2. module ใหม่ `app/services/ai/template_answer.py`:
   - input: rows, columns, intent (ถ้ามี), context docs (หน่วยของ metric ถ้าหาได้)
   - output: **โครงเดียวกับ explanation เดิมเป๊ะ** (dict ที่มี explanation / visualization / chart_config ตาม contract ที่อ่านจาก response_utils + frontend) — 1×1 ไม่มี chart; ตารางเล็ก visualization=table หรือ bar ตามกติกา deterministic
   - ข้อความไทย: ระบุ metric + เงื่อนไข/งวด (provenance จาก intent หรือ SQL WHERE สรุปสั้น) + ค่า format คั่นหลักพัน; ถ้าค่า ≥ 1,000,000 วงเล็บหน่วยล้านบาททศนิยม 1 ตำแหน่ง
   - **ห้าม** ส่งตัวเลขผ่าน LLM ใน path นี้เด็ดขาด
3. จุดเสียบใน `run_hybrid_attempt`: ก่อนเรียก explanation LLM → ถ้า flag เปิด + เข้าเงื่อนไข → ใช้ template แล้วข้าม LLM call; log `explain_mode=template|llm` ลง trace
4. คำเตือน limit (F1.2) ต้องยังต่อท้ายได้ทั้งสอง mode

**Tests:** unit — 1×1, 3×2, 6×2 (เกิน → ไป LLM path), รูปแบบ dict ตรง contract, ตัวเลข format ถูก, ภาษาไทยไม่มี placeholder หลุด
**Acceptance:** เปิด flag ใน dev → smoke 20 ข้อ: ข้อที่เข้า template ไม่มี explanation call ใน trace, latency P50 กลุ่มนั้นลด ≥ 30%, ตัวเลขในข้อความตรงกับ data ทุกข้อ; manual QA อ่านคำตอบ template 10 ข้อแล้วยอมรับคุณภาพก่อนเปิดถาวร

---

## Phase B — Parallel prep (pure code ไม่มี flag)

หลัง F2.5 (hoist resolve_context_info): งานก่อน generate SQL ที่ independent — Vanna/RAG retrieval กับ context/schema assembly — เปลี่ยนเป็น `asyncio.gather` (ระวัง: ถ้า RAG ใช้ sync client ต้อง `asyncio.to_thread` — ดูของจริง) จุดอื่นห้ามฝืน parallel ถ้ามี dependency
**Acceptance:** trace แสดง stage `rag` กับ `context` ทับเวลากัน; total P50 ลดตามคาด; pytest ผ่าน

---

## Phase C — Structured follow-up state (ต่อยอด F8)

**เหตุผล:** follow-up ปัจจุบัน re-derive intent จาก raw history ทุกครั้ง — ช้า, prompt ใหญ่, และ inheritance ไม่ deterministic

**การทำ:**
1. เก็บ intent JSON ล่าสุดของ conversation — ตำแหน่งเก็บให้ Claude Code เลือกหลังอ่าน `app/models/chat.py`: column ใหม่ใน chat_history (intent_json TEXT) หรือตาราง conversation_state — เลือกแบบที่ migration เบาสุด จดเหตุผล
2. เมื่อเป็น follow-up (มี history): prompt intent = previous_intent_json + คำถามใหม่ → สั่ง "อัปเดต intent" ผ่าน `generate_structured` (F8) — prompt สั้นกว่าเดิมมาก ไม่ต้องแนบ history ยาว
3. flag `intent_state_enabled` (default false); ถ้า previous intent ไม่มี/parse ไม่ได้ → fallback เส้นเดิมเงียบ ๆ
4. หมายเหตุ: phase นี้มีผลเฉพาะเมื่อ two-pass เปิด — ถ้า two-pass ยัง OFF ให้ทำโค้ดรอไว้และทดสอบหลัง flag ทั้งคู่เปิดใน dev เท่านั้น

**Acceptance:** eval ชุด follow-up (สร้าง golden follow-up ≥ 8 ข้อถ้ายังไม่มี) — accuracy ≥ เดิม และ intent stage latency ลด; ผลลง RESULT_F9

---

## Phase D — Escalation ladder: retry แบบไต่ระดับแทนลองซ้ำของเดิม

**โครงบันได (แทน loop เดิมใน query_hybrid):**
- Attempt 1: path ปกติ (model ตาม config ปัจจุบัน)
- Attempt 2: escalate เป็น strong tier ของ provider เดิม + error context (โครง error feedback มีแล้ว — เพิ่มการสลับ model ผ่าน registry; อ่านว่า tier map อยู่ตรงไหน ถ้าไม่มี ให้เพิ่ม config `model_tier_map` ต่อ provider)
- Attempt 3 (flag `escalation_tool_loop_enabled`, default false): ส่งเข้า tool-loop (`retry_loop` / mcp mode หลัง F2.6) — ให้ mcp mode เปลี่ยนบทบาทจาก "โหมดที่ user เลือก" เป็น tier กู้ภัยอัตโนมัติ
- Budget: config `query_latency_budget_s` (default 45) — เวลาสะสมเกิน budget → ไม่เข้า attempt ถัดไป คืน error อธิบายตรง ๆ
- ทุกการ escalate ลง trace (`escalated_to`)

**ข้อควรระวัง:** อย่าให้ attempt 3 มีสิทธิ์เกิน read-only เดิม (tool ชุดเดียวกับ mcp mode ปกติ) และ dedup/cache semantics (F1/F2) ต้องไม่เพี้ยนเมื่อ path ยาวขึ้น
**Acceptance:** จำลองคำถามที่ A1 fail (golden ที่เคย fail จาก eval) → A2/A3 กู้ได้อย่างน้อยบางส่วนโดย accuracy รวมไม่ลด; latency เคสปกติ (A1 ผ่าน) เท่าเดิมใน trace

---

## Phase E — Heuristic router → cheap tier (**decision-gated ห้ามเปิดเอง**)

- เงื่อนไข route ไป cheap/Matcha: ไม่มี history + metric เดียว + ไม่มีคำ trigger ความซับซ้อน (เทียบ, แนวโน้ม, ต่อหัว, สัดส่วน, top, เฉลี่ยย้อนหลัง ฯลฯ — ลิสต์ใน config แก้ได้)
- **เกณฑ์เปิด:** รัน eval แยก tier บน subset ที่ router เลือกไป cheap — accuracy ต่ำกว่า strong ได้ไม่เกิน 2 percentage points; ไม่ผ่าน = ปิดถาวร บันทึกผล
- flag `router_enabled` default false; ทุก decision ของ router ลง trace (`routed_tier`, เหตุผล)

---

## สิ่งที่จงใจไม่ทำ (บันทึกไว้กันหยิบผิดในอนาคต)

- Self-consistency หลาย candidate ทุก query — คูณ token/เงินโดยตรง
- LLM-verifier ทุก query — บวก call ทุกเคส; ใช้ deterministic validation ที่มี (sqlglot = deferred decision เดิม)
- ReAct/tool-loop เป็น default — round-trip หลายรอบขัดเงื่อนไขความเร็ว (ใช้เป็น Attempt 3 เท่านั้น)
- LangGraph/multi-agent framework — ยืนตาม architecture decision เดิม

## Acceptance Criteria (ทั้งแผน)

- [ ] pytest + tests ใหม่ผ่านทุก phase
- [ ] `plan/RESULT_F9.md` มีตาราง ก่อน-หลัง ของทุก phase ที่เปิด flag
- [ ] ไม่มี flag ใดถูกเปิด production โดยไม่มีแถวผลวัดใน RESULT_F9
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md`
