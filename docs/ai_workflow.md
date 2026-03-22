# AI Communication Workflow

เอกสารนี้อธิบายกระบวนการทำงานเบื้องหลัง (Under the Hood) ว่าระบบสื่อสารกับ AI Model (Claude / Gemini) อย่างไร ตั้งแต่เริ่มส่งคำถามจนถึงได้คำตอบกลับมาแสดงผล

## 🔄 ภาพรวมการทำงาน (The Flow)

การสื่อสารเป็นแบบ **Loop** (ReAct Pattern) เพื่อให้ AI สามารถ "คิด" และ "ลงมือทำ" (Run SQL) ก่อนตอบ user ได้

1.  **User ยิงคำถาม** (จาก App/Frontend)
    *   **Protocol**: `HTTP POST /api/v1/chat`
    *   **Payload**: `{"question": "ขอดยอดขายเดือนมกราคม", "conversation_id": "...", "provider": "gemini"}`

2.  **เตรียมข้อมูล (Backend Prep)**
    *   **Detect Context**: ระบบจะตรวจสอบว่า User คุยเรื่องอะไร (Revenue vs Expense) เพื่อเลือก Data Context ที่ถูกต้อง
    *   **Build System Prompt**: ดึงโครงสร้าง Database (Schema), กฎทางธุรกิจ (Rules), และตัวอย่างการเขียน SQL (Few-shot examples) มาสร้างเป็นคำสั่งตั้งต้น (System Instruction)

3.  **AI Round 1: คิดและเขียน SQL (Generate SQL)**
    *   **Backend -> AI**: ส่งข้อมูลทั้งหมดไปให้ AI พร้อมนิยามเครื่องมือ (**Tools Definition**)
    *   **AI ตัดสินใจ**: AI วิเคราะห์คำถามและ Schema แล้วตัดสินใจเรียกใช้ Tool ชื่อ `execute_query`
    *   **AI -> Backend**: ส่งกลับมาเป็น **Tool Call Request** (ยังไม่ใช่คำตอบสุดท้าย)

4.  **Backend ทำงานแทน (Execute Tool)**
    *   Backend รับ SQL มาตรวจสอบความปลอดภัย (Security Check: ห้าม Drop/Delete)
    *   รัน SQL ใส่ Database จริง (SQLite/Postgres)
    *   ได้ผลลัพธ์เป็น Raw Data (JSON Array)

5.  **AI Round 2: สรุปผล (Explain Result)**
    *   **Backend -> AI**: ส่งผลลัพธ์จาก Database (Tool Output) กลับไปให้ AI อ่าน
    *   **AI -> Backend**: AI อ่านข้อมูลแล้วเขียนสรุปเป็นข้อความภาษาไทย (Natural Language Response)

6.  **ส่งคำตอบคืน User (Response)**
    *   Backend รวมข้อมูล: คำตอบ (Text) + ตารางข้อมูล (Data) + โค้ด SQL
    *   ส่งกลับ Frontend เพื่อนำไปแสดงผลเป็น Chat Bubble, Chart, และ Log

---

## 📦 รูปแบบข้อมูล (Data Protocol)

เราใช้มาตรฐาน **Native Function Calling** ของ AI Provider (OpenAI/Anthropic/Gemini Format) โดย Backend จะทำหน้าที่แปลง format ให้ตรงกับค่ายที่เลือกใช้

### 1. Request (ขาไปหา AI)
ส่งประวัติการคุย (Messages) และรายการเครื่องมือ (Tools)

```json
{
  "messages": [
    { 
      "role": "system", 
      "content": "You are a SQL expert. User asked regarding Revenue. Schema: Table[revenue_search]..." 
    },
    { 
      "role": "user", 
      "content": "ยอดขายเดือนที่แล้วเป็นเท่าไหร่" 
    }
  ],
  "tools": [
    {
      "name": "execute_query",
      "description": "Run SQL query on database to get data",
      "parameters": {
        "type": "object",
        "properties": {
          "sql": { "type": "string", "description": "SQL Query (SELECT only)" }
        }
      }
    }
  ]
}
```

### 2. Tool Call (ขา AI ตอบกลับมาขอรันคำสั่ง)
AI ไม่ตอบเป็น content แต่ส่ง `tool_calls` มาแทน

```json
{
  "content": null,
  "tool_calls": [
    {
      "id": "call_12345",
      "type": "function",
      "function": {
        "name": "execute_query",
        "arguments": "{ \"sql\": \"SELECT sum(amount) FROM revenue_search WHERE month = 'Jan'\" }"
      }
    }
  ]
}
```

### 3. Tool Output (ขา Backend ส่งผลรันกลับไป)
Backend ส่งผลลัพธ์กลับไปใน role `tool` เพื่อให้ AI รู้ว่านี่คือผลจากคำสั่งเมื่อกี้

```json
{
  "role": "tool",
  "tool_call_id": "call_12345",
  "name": "execute_query",
  "content": "[{\"amount\": 5000000}]"
}
```

---

## 🧩 Key Architecture Components

| Component | หน้าที่ | ไฟล์ที่เกี่ยวข้อง |
| :--- | :--- | :--- |
| **API Endpoint** | รับ Request, จัดการ Session, บันทึก History | `app/api/v1/chat.py` |
| **SchemaService** | เตรียม Metadata, Context, System Prompt | `app/services/schema_service.py` shim และ `app/services/schema/` implementation |
| **AIService** | คุยกับ External API (Claude/Gemini/Matcha), จัดการ Retry/Hybrid flow | `app/services/ai_service.py` shim และ `app/services/ai/` implementation |
| **Tools Agent / Query Orchestration** | ตัว validate/execute SQL, retry, explanation, confidence | `app/services/ai/hybrid_flow.py`, `app/services/ai/retry_loop.py`, `app/services/mcp_client.py` |

> หมายเหตุ: import path เดิมยังใช้ได้เพื่อ compatibility แต่ implementation หลักถูกแยกเป็น package แล้ว
