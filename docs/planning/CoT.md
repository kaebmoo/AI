---
## สรุปสิ่งที่ทำแล้ว (Implementation Status)

### ✅ ระดับ 1 — Structured CoT Prompt
- **สถานะ:** ✅ Done + Verified
- **ไฟล์:** `app/services/ai_service.py:1419`
- **รายละเอียด:** เพิ่ม `ขั้นตอนที่ 1 — วิเคราะห์คำถาม` ใน `user_prompt` ของ `query_hybrid()`
  ให้ AI วิเคราะห์ metric/dimension/filter/time_range ก่อนเขียน SQL เสมอ (One-Pass CoT Mode)
- **Admin:** ไม่มี toggle — ทำงานตลอดเวลาทุก provider

### ✅ ระดับ 2 — Claude Extended Thinking
- **สถานะ:** ✅ Done + Verified (end-to-end)
- **Flow ที่ตรวจสอบแล้ว:**
  ```
  AdminConfigService.get_ai_config()        → chat.py:303
    └─ claude_extended_thinking             → create_claude_service():314
    └─ claude_thinking_budget_tokens        → create_claude_service():315
         └─ AIService.__init__() kwargs     → ai_service.py:963-964
              └─ ClaudeProvider.__init__()  → ai_service.py:141-147
                   └─ generate_content()   → kwargs["thinking"] ai_service.py:324
  ```
- รองรับเฉพาะ `claude-sonnet-4*` / `claude-opus-4*` ตรวจ model อัตโนมัติ
- `max_tokens` = `thinking_budget_tokens + 2000` อัตโนมัติ
- **Admin:** Settings → Claude Configuration → **Extended Thinking** switch + **Thinking Budget**

### ✅ ระดับ 3 — Two-Pass SQL Generation
- **สถานะ:** ✅ Done + Verified (end-to-end)
- **Flow ที่ตรวจสอบแล้ว:**
  ```
  AdminConfigService.get_feature_flags()    → chat.py:402
    └─ two_pass_enabled                     → query_hybrid():1253 → _extract_intent() + _build_pass2_prompt()
    └─ value_lookup_enabled                 → query_hybrid():1254 → _lookup_values_from_question()
  ```
- **Pass 1** (`_extract_intent()`): AI ส่งคืน JSON → `intent`, `metrics`, `dimensions`, `filters`, `time_range`
- **Pass 2** (`_build_pass2_prompt()`): สร้าง SQL prompt จาก structured intent
- ถ้า Pass 1 fail → fallback กลับ One-Pass CoT อัตโนมัติ (`ai_service.py:1405`)
- ถ้า attempt > 0 (retry) → ใช้ One-Pass แทน Two-Pass (`ai_service.py:1409`)
- **Admin:** Settings → Advanced Features → **Two-Pass SQL Generation** + **Value Lookup**

---

## การตั้งค่าผ่าน Web Admin (`/settings`)

ฟีเจอร์ทั้ง 3 ระดับรองรับการตั้งค่าผ่าน Admin UI ครบแล้ว ไม่ต้องแก้ไฟล์โค้ด

### หน้า Settings → Claude Configuration

| UI Label | Field Name | ค่า Default | หมายเหตุ |
|----------|-----------|-------------|---------|
| **Extended Thinking** (Switch) | `claude_extended_thinking` | `false` | เปิดใช้ Level 2 — รองรับเฉพาะ `claude-sonnet-4*` / `claude-opus-4*` |
| **Thinking Budget (tokens)** (InputNumber) | `claude_thinking_budget_tokens` | `8000` | แสดงเฉพาะเมื่อ Extended Thinking = ON, ช่วง 1,024–100,000 |

> ยิ่ง budget มาก → Claude คิดลึกขึ้น แต่ใช้เวลาและ cost มากขึ้น
> แนะนำ: `5000` สำหรับใช้งานปกติ, `10000+` สำหรับคำถามซับซ้อน

### หน้า Settings → Advanced Features

| UI Label | Field Name | ค่า Default | หมายเหตุ |
|----------|-----------|-------------|---------|
| **Two-Pass SQL Generation** (Switch) | `two_pass_enabled` | `false` | เปิดใช้ Level 3 — เพิ่ม API call 1 ครั้งต่อ query |
| **Value Lookup** (Switch) | `value_lookup_enabled` | `false` | ค้นหาค่าจริงในฐานข้อมูลก่อนสร้าง SQL |

### ระดับ 1 (CoT Prompt) — ไม่มี toggle

CoT Prompt (Level 1) เป็น **default พื้นฐาน** — ทำงานตลอดเวลาในทุก provider
ไม่มี switch เพราะ embedded อยู่ใน `user_prompt` ของ `query_hybrid()` โดยตรง
ผู้ใช้ทุกคนได้ประโยชน์จาก CoT โดยไม่ต้องตั้งค่า

### การ flow ตาม config ที่ตั้ง

```
คำถาม
  │
  ├─ two_pass_enabled = true  →  Pass 1 (Intent JSON) → Pass 2 (SQL from intent)
  │                               ถ้า Pass 1 fail → fallback ลง One-Pass
  │
  └─ two_pass_enabled = false →  One-Pass CoT Prompt (Level 1, always on)
                                  + Extended Thinking ถ้า claude_extended_thinking = true
```

### Config Fallback (3-tier)

```
Admin UI (database) → .env file → Hardcoded defaults
```

| Config Key | .env variable | Hardcoded default |
|-----------|--------------|-------------------|
| `claude_extended_thinking` | `CLAUDE_EXTENDED_THINKING` | `false` |
| `claude_thinking_budget_tokens` | `CLAUDE_THINKING_BUDGET_TOKENS` | `8000` |
| `two_pass_enabled` | `TWO_PASS_ENABLED` | `false` |
| `value_lookup_enabled` | `VALUE_LOOKUP_ENABLED` | `false` |

### ตัวอย่างการตั้งค่าใน .env

ค่าปัจจุบันใน `.env` (AI-related):

```env
# AI Provider Settings
AI_PROVIDER="gemini"                        # default provider: claude | gemini | matcha
ANTHROPIC_API_KEY="sk-ant-api03-..."        # Claude API key
GOOGLE_AI_API_KEY="AIzaSy..."               # Gemini API key
MATCHA_AI_API_KEY="sk-..."                  # Matcha (Gateway) API key
MATCHA_API_URL="https://aigateway.ntictsolution.com/v1/chat/completions"

# AI Models
GEMINI_MODEL="gemini-3-pro-preview"
CLAUDE_MODEL="claude-sonnet-4-6"
MATCHA_MODEL="gpt-4.1"

# CoT / SQL Generation Features
# (ยังไม่ได้ตั้งใน .env → ใช้ hardcoded defaults ทั้งหมด → ควรตั้งค่าผ่าน Admin UI แทน)
# CLAUDE_EXTENDED_THINKING=false            # เปิด Extended Thinking สำหรับ Claude
# CLAUDE_THINKING_BUDGET_TOKENS=8000        # budget token สำหรับ reasoning (1024-100000)
# TWO_PASS_ENABLED=false                    # เปิด Two-Pass SQL Generation
# VALUE_LOOKUP_ENABLED=false                # เปิด Value Lookup จาก keyword index
```

> **หมายเหตุ:** ค่าใน `.env` เป็นแค่ fallback ชั้นที่ 2
> ถ้าตั้งค่าผ่าน Admin UI แล้ว → ค่าใน `.env` จะถูก override ด้วยค่าจาก database เสมอ
> แนะนำให้ใช้ Admin UI เป็นหลัก และใช้ `.env` เฉพาะ API keys ที่ sensitive

---

### ✅ Bug Fix — UNION SELECT ถูก block โดยผิดพลาด
- **สถานะ:** ✅ Fixed (2026-02-25)
- **ไฟล์:** `mcp_servers/nt_query_mcp.py:185`
- **ปัญหา:** `INJECTION_PATTERNS` มี `r'UNION\s+SELECT'` ซึ่ง block ทุก `UNION SELECT` รวมถึง query ที่ถูกต้อง
- **แก้ไข:** เปลี่ยนเป็น `r"'\s*UNION\s+SELECT"` (block เฉพาะ `' UNION SELECT` ที่ต่อท้าย string literal เท่านั้น)
- **ผล:** Query แบบ `SELECT ... UNION SELECT ...` ที่ AI สร้างผ่าน validator ได้แล้ว

---

## แผนเดิม (Original Design Notes)

### การวิเคราะห์ปัญหาปัจจุบัน

ระบบ Hybrid Mode (หลัก) ทำงานแบบ:
คำถาม → system_prompt + user_prompt → AI → SQL (ตรงๆ) → execute

จุดอ่อน:
1. AI ไม่มีขั้นตอน "คิด" ก่อนเขียน SQL — ถ้าคำถามคลุมเครือก็ guess ตรงๆ
2. Semantic mapping ถูก inject ใน system prompt แต่ AI ไม่ถูกบังคับให้ "ตรวจ" มันก่อน
3. Retry ส่ง error กลับไปให้แก้ แต่ไม่ได้ให้ AI reason ว่า "ทำไมถึงผิด"
4. Visualization config มักผิด → ระบบต้อง post-process swap ใน Python code เอง

---
### แนวทางปรับปรุง: 3 ระดับ

  ระดับ 1 — Structured CoT Prompt (ทำได้ทันที, ทุก provider) ✅ Done

  > **Admin Settings:** ไม่มี toggle — ทำงานอัตโนมัติทุก provider ไม่ต้องตั้งค่า

  แก้ที่ query_hybrid() บรรทัด 1333 — เพิ่ม reasoning step ใน user_prompt:

  user_prompt = f"""คำถาม: {question}

  **บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table}){history_context}
  {rag_context}

  ---
  **ขั้นตอนที่ 1 — วิเคราะห์คำถาม (คิดก่อนเขียน SQL):**
  ก่อนสร้าง SQL ให้ตอบคำถามเหล่านี้ก่อน:
  - คำถามต้องการข้อมูลอะไร? (metric, dimension, filter, time range)
  - มี semantic mapping ใดที่ตรงกับ keyword ในคำถาม?
  - ต้อง GROUP BY อะไร? ใช้ aggregate function อะไร?
  - SQL pattern ที่เหมาะสมคืออะไร?

  **ขั้นตอนที่ 2 — SQL:**
  ```sql
  <SQL ที่สร้างจากการวิเคราะห์ข้างต้น>

  ขั้นตอนที่ 3 — อธิบาย:
  <คำอธิบายภาษาไทย>"""

  **ผลลัพธ์:** AI จะ output reasoning ก่อน SQL — ทำให้ SQL ถูกต้องขึ้นมาก โดยเฉพาะ filter ที่ซับซ้อน

  ---

  ### ระดับ 2 — Claude Extended Thinking (Claude provider เท่านั้น) ✅ Done

  > **Admin Settings:** Settings → Claude Configuration
  > - **Extended Thinking** (Switch) → เปิด/ปิด
  > - **Thinking Budget (tokens)** (InputNumber, 1,024–100,000) → ปรากฏเมื่อเปิด Extended Thinking
  > - แนะนำ: `5000` ปกติ / `10000+` คำถามซับซ้อน

  Claude Sonnet 4.5+ รองรับ `thinking` parameter — นี่คือ internal reasoning ที่ทรงพลังที่สุด แก้ที่ `ClaudeProvider.generate_content()`:

  ```python
  async def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
      messages = [{"role": "user", "content": prompt}]

      # ตรวจว่า model รองรับ extended thinking
      supports_thinking = any(m in self.model for m in [
          "claude-sonnet-4", "claude-opus-4"
      ])

      kwargs = {
          "model": self.model,
          "max_tokens": 8000,  # ต้องสูงพอสำหรับ thinking + output
          "messages": messages,
      }

      if system_prompt:
          kwargs["system"] = system_prompt

      if supports_thinking:
          kwargs["thinking"] = {
              "type": "enabled",
              "budget_tokens": 5000  # Claude จะใช้ token นี้สำหรับ reasoning
          }

      response = await self.client.messages.create(**kwargs)

      # extract text (ไม่ใช่ thinking block)
      for block in response.content:
          if block.type == "text":
              return block.text
      return ""

  ผลลัพธ์: Claude จะ "คิด" ภายในก่อน output — ไม่เพิ่ม token ใน prompt แต่ได้ reasoning ฟรี

  ---
  ระดับ 3 — Two-Pass SQL Generation (ซับซ้อน, แม่นยำสูงสุด) ✅ Done

  > **Admin Settings:** Settings → Advanced Features
  > - **Two-Pass SQL Generation** (Switch) → เปิด/ปิด
  > - **Value Lookup** (Switch) → ค้นหาค่าจริงในฐานข้อมูลก่อนสร้าง SQL
  > - เมื่อเปิด Two-Pass → เพิ่ม API call 1 ครั้งต่อ query (Pass 1: Intent JSON)
  > - ถ้า Pass 1 fail → fallback กลับ One-Pass อัตโนมัติ

  แยก AI call เป็น 2 ขั้น:

  async def query_hybrid_cot(self, question, system_prompt, ...):

      # Pass 1: Intent Extraction (ถูก, fast)
      intent_prompt = f"""วิเคราะห์คำถามนี้และตอบเป็น JSON:
  คำถาม: {question}

  {{
    "intent": "aggregation|trend|comparison|lookup",
    "metrics": ["column names to sum/count"],
    "dimensions": ["column names to group by"],
    "filters": [{{"column": "...", "value": "...", "operator": "="}}],
    "time_range": {{"year": ..., "month": ...}},
    "matched_mappings": ["keyword → SQL condition"]
  }}"""

      intent_json = await self.provider.generate_content(intent_prompt, system_prompt)
      intent = json.loads(extract_json(intent_json))

      # Pass 2: SQL Generation from structured intent
      sql_prompt = f"""สร้าง SQL สำหรับ:
  คำถาม: {question}

  Intent ที่วิเคราะห์แล้ว:
  {json.dumps(intent, ensure_ascii=False, indent=2)}

  ตาราง: {context_table}
  สร้าง SQL ที่ตรงกับ intent นี้ทุกข้อ:
  ```sql
  ```"""

      response_text = await self.provider.generate_content(sql_prompt, system_prompt)
      sql_query = self._extract_sql(response_text)

      # ต่อด้วย validate + execute เหมือนเดิม

  ---
  สรุปการแนะนำ

  ┌───────────────────────────┬───────────────────────┬─────────────┬───────────────┐
  │          แนวทาง           │        ความยาก        │   ผลกระทบ   │ ทำกับ provider │
  ├───────────────────────────┼───────────────────────┼─────────────┼───────────────┤
  │ ระดับ 1: CoT Prompt        │ ง่าย (แก้ string)       │ ดีขึ้น ~30-40% │ ทุก provider   │
  ├───────────────────────────┼───────────────────────┼─────────────┼───────────────┤
  │ ระดับ 2: Extended Thinking │ ปานกลาง (แก้ API call) │ ดีขึ้น ~50-60% │ Claude เท่านั้น  │
  ├───────────────────────────┼───────────────────────┼─────────────┼───────────────┤
  │ ระดับ 3: Two-pass          │ ยาก (แก้ flow หลัก)     │ ดีขึ้น ~60-70% │ ทุก provider   │
  └───────────────────────────┴───────────────────────┴─────────────┴───────────────┘

  แนะนำเริ่มที่ระดับ 1 ก่อน เพราะ:
  - แก้น้อย แต่ได้ผลเร็ว
  - ไม่กระทบ flow อื่น
  - วัดผลได้ทันทีว่า SQL ดีขึ้นไหม
  - ถ้าใช้ Claude เป็น default → ทำระดับ 2 เพิ่มได้เลย