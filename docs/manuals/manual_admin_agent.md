# Admin Agent — คู่มือการใช้งาน

## เข้าถึง

- **URL:** http://localhost:5173/admin-agent
- **สิทธิ์:** Admin only

## ภาพรวม

Admin Agent เป็นระบบ chat-based สำหรับผู้ดูแลระบบ ที่ใช้ LLM ในการเลือกและเรียกใช้ tools อัตโนมัติ สามารถค้นหา เพิ่ม และวิเคราะห์ข้อมูลการตั้งค่าของระบบได้ผ่านคำสั่งภาษาธรรมชาติ (ไทย/อังกฤษ)

## วิธีใช้

พิมพ์คำถามหรือคำสั่งเป็นภาษาไทยหรืออังกฤษในช่อง chat Agent จะเลือก tool ที่เหมาะสมและดำเนินการให้อัตโนมัติ

## ตัวอย่างคำสั่ง

### ค้นหาข้อมูล

- "มี mapping สำหรับ datacom ไหม"
- "ค้นหา rule ที่ severity = error"
- "ค้นหา golden example เรื่อง รายได้"
- "แสดง contexts ทั้งหมด"
- "ดูโครงสร้าง view revenue_search"

### เพิ่มข้อมูล (ต้อง confirm)

- "เพิ่ม mapping datacom ไป SERVICE_GROUP"
- "เพิ่ม rule ใหม่สำหรับตรวจ YEAR filter"
- "เพิ่ม example คำถาม 'รายได้ mobile' กับ SQL ..."

### วิเคราะห์

- "วิเคราะห์ query logs 7 วัน"
- "ดู feedback ที่เป็น thumbs down"
- "validate config สำหรับ revenue"

### ระบบ

- "refresh cache"
- "search hierarchy สำหรับ DIVISION"

## Confirmation Flow

เมื่อคำสั่งเป็นการเพิ่ม/แก้ไขข้อมูล Agent จะถามยืนยันก่อนดำเนินการ:

1. Agent แสดงรายละเอียดสิ่งที่จะทำ (ชื่อ tool, parameters)
2. กดปุ่ม **"ยืนยัน"** หรือ **"ยกเลิก"**
3. ถ้ายืนยัน -> ดำเนินการ + refresh cache อัตโนมัติ
4. ถ้ายกเลิก -> ไม่มีการเปลี่ยนแปลง

## Tool ทั้งหมด (14 tools)

### Mapping Tools

| Tool | คำอธิบาย | ต้อง Confirm |
|------|----------|-------------|
| `search_mappings` | ค้นหา semantic mapping ด้วย keyword | ไม่ |
| `add_mapping` | เพิ่ม mapping ใหม่ (term -> column/value) | ใช่ |

### Rule Tools

| Tool | คำอธิบาย | ต้อง Confirm |
|------|----------|-------------|
| `search_rules` | ค้นหา business rules ด้วย keyword/severity | ไม่ |
| `add_rule` | เพิ่ม business rule ใหม่ | ใช่ |

### Example Tools

| Tool | คำอธิบาย | ต้อง Confirm |
|------|----------|-------------|
| `search_examples` | ค้นหา golden examples ด้วย keyword | ไม่ |
| `add_example` | เพิ่ม golden example (question + SQL) | ใช่ |

### System Tools

| Tool | คำอธิบาย | ต้อง Confirm |
|------|----------|-------------|
| `list_contexts` | แสดง data contexts ทั้งหมด | ไม่ |
| `refresh_cache` | ล้าง cache ทั้งระบบ | ไม่ |
| `search_hierarchy` | ค้นหา hierarchy values | ไม่ |

### Onboarding Tools

| Tool | คำอธิบาย | ต้อง Confirm |
|------|----------|-------------|
| `inspect_view` | ตรวจสอบโครงสร้าง view/table | ไม่ |
| `validate_config` | ตรวจสอบความถูกต้องของ config | ไม่ |

### Analysis Tools

| Tool | คำอธิบาย | ต้อง Confirm |
|------|----------|-------------|
| `analyze_query_logs` | วิเคราะห์ query logs (error rate, patterns) | ไม่ |
| `review_feedback` | ดู feedback จากผู้ใช้ (thumbs up/down) | ไม่ |

## Architecture

### Tool Selection Flow

```
User Message
    |
    v
[1] Native Function Calling (OpenAI tool_choice='auto')
    |-- Success -> Execute tool
    |-- Fail ----v
[2] Keyword-based Fallback
    |-- Match -> Execute tool
    |-- No match -v
[3] LLM Retry (stronger instructions, max 2 retries)
    |-- Success -> Execute tool
    |-- Fail -> "ขออภัย ไม่สามารถเลือก tool ที่เหมาะสมได้"
```

### Result Flow

```
Tool Result (raw data)
    |
    v
LLM Summarization (2nd call)
    |
    v
Thai language summary + mini data table
```

## API Endpoints

| Method | Path | คำอธิบาย |
|--------|------|----------|
| POST | `/api/v1/admin/agent/chat` | ส่งข้อความไปยัง agent |
| POST | `/api/v1/admin/agent/confirm` | ยืนยันการดำเนินการ |
| GET | `/api/v1/admin/agent/conversations` | ดูประวัติการสนทนา |

## UI Features

- **Tool call visualization:** แสดง tool ที่ถูกเรียกพร้อม parameters
- **Mini data tables:** แสดงผลลัพธ์เป็นตารางขนาดเล็ก
- **SQL truncation:** SQL ยาวจะถูกตัดย่อ hover เพื่อดูเต็ม
- **Sticky headers:** header ตารางติดอยู่ด้านบนเมื่อ scroll
- **Zebra striping:** แถวสลับสีเพื่ออ่านง่าย
- **Row numbers:** แสดงลำดับแถว
