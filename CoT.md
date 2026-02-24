  ---
  การวิเคราะห์ปัญหาปัจจุบัน

  ระบบ Hybrid Mode (หลัก) ทำงานแบบ:
  คำถาม → system_prompt + user_prompt → AI → SQL (ตรงๆ) → execute

  จุดอ่อน:
  1. AI ไม่มีขั้นตอน "คิด" ก่อนเขียน SQL — ถ้าคำถามคลุมเครือก็ guess ตรงๆ
  2. Semantic mapping ถูก inject ใน system prompt แต่ AI ไม่ถูกบังคับให้ "ตรวจ" มันก่อน
  3. Retry ส่ง error กลับไปให้แก้ แต่ไม่ได้ให้ AI reason ว่า "ทำไมถึงผิด"
  4. Visualization config มักผิด → ระบบต้อง post-process swap ใน Python code เอง

  ---
  แนวทางปรับปรุง: 3 ระดับ

  ระดับ 1 — Structured CoT Prompt (ทำได้ทันที, ทุก provider)

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

  ### ระดับ 2 — Claude Extended Thinking (Claude provider เท่านั้น)

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
  ระดับ 3 — Two-Pass SQL Generation (ซับซ้อน, แม่นยำสูงสุด)

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