# Plan 4: Telegram Interface (User + Admin)

**Priority:** 4  
**ประมาณเวลา:** 3-5 วัน  
**Prerequisite:** Plan 1 (Admin Agent)  
**อ้างอิง:** เดิมคือ Phase 4 ของ NT AI Refactoring Plan (deferred), ใช้ OpenMiniCrew เป็นฐาน

---

## 1. แนวคิด

ให้ทั้ง user ทั่วไป และ admin ใช้งาน NT AI Assistant ผ่าน Telegram:

| ผู้ใช้ | ทำอะไรได้ |
|--------|----------|
| **User** | ถามข้อมูลรายได้/ค่าใช้จ่าย/P&L เหมือนบน web, ดู chart (ส่งเป็นรูป), export CSV |
| **Admin** | ทุกอย่างที่ user ทำได้ + สั่ง admin agent (Plan 1), รับ notification จาก auto-analyzer (Plan 3), approve/reject fixes |

## 2. สถาปัตยกรรม: 2 ทางเลือก

### ทางเลือก A: Telegram Bot ใน NT AI Assistant (แนะนำ)

เพิ่ม Telegram interface ตรงใน NT AI Assistant โดยไม่ผ่าน OpenMiniCrew

```
Telegram User Message
        │
        ▼
app/telegram/
  ├── bot.py          (polling/webhook, เหมือน OpenMiniCrew interfaces/)
  ├── dispatcher.py   (route: user query vs admin command)
  ├── handlers.py     (message handlers)
  └── formatters.py   (format response สำหรับ Telegram: split, markdown, chart→image)
        │
        ├── User query → QueryEngine (existing) → format response → send
        └── Admin command → AdminAgent (Plan 1) → format response → send
```

**ข้อดี:** ใช้ services ที่มีอยู่ตรง (QueryEngine, SchemaService, AdminAgent) ไม่ต้องผ่าน HTTP
**ข้อเสีย:** เพิ่ม complexity ใน codebase หลัก

### ทางเลือก B: OpenMiniCrew เป็น Telegram Gateway

เพิ่ม tool ใน OpenMiniCrew ที่เรียก NT AI Assistant API

```
Telegram → OpenMiniCrew Dispatcher
        │
        ├── /query "รายได้รวม" → NTQueryTool.execute() → HTTP POST /api/v1/chat/ → ส่งกลับ
        ├── /admin "เพิ่ม mapping" → NTAdminTool.execute() → HTTP POST /admin/agent/chat → ส่งกลับ
        └── /email → EmailSummaryTool (existing) → ส่งกลับ
```

**ข้อดี:** OpenMiniCrew มี infrastructure พร้อม (polling/webhook, rate limit, memory, scheduler)
**ข้อเสีย:** ต้อง authenticate ผ่าน HTTP, latency เพิ่ม, deploy 2 services

### แนะนำ: ทางเลือก A

เพราะ NT AI ใช้ async/FastAPI อยู่แล้ว เพิ่ม Telegram webhook ง่ายกว่าไปวน HTTP อีกชั้น แต่ยืม pattern (dispatcher, formatters, rate limit) จาก OpenMiniCrew

## 3. User Flow

```
User พิมพ์: "รายได้กลุ่ม mobile ปี 68"
        │
        ▼
[Telegram Bot receives message]
        │
        ▼
[Auth: chat_id → lookup user ใน users table]
  ├── ไม่พบ → "กรุณาลงทะเบียนก่อน /start"
  └── พบ + is_active
        │
        ▼
[Dispatcher]
  ├── /start → register flow (ส่ง OTP ไป email ที่ลงทะเบียน)
  ├── /help → แสดง commands
  ├── /context → เลือก data context (revenue/expense/pl)
  ├── /model → เลือก AI provider
  │
  └── Free text → QueryEngine.execute()
        │
        ├── SQL generated → execute → format result
        │   ├── ตาราง → format เป็น monospace text
        │   ├── กราฟ → render chart → ส่งเป็นรูป
        │   └── ข้อมูลเยอะ → "ดูเพิ่มเติมบน web: [link]"
        │
        └── Error → ส่ง error message + log

User พิมพ์: "export เป็น excel"
        │
        ▼
[Dispatcher detects export intent]
  → ReportExportTool (existing) → ส่งไฟล์ CSV/Excel ผ่าน Telegram
```

## 4. Admin Flow

```
Admin พิมพ์: "datacom ต้องค้นจาก service_group ไม่ใช่ business_unit"
        │
        ▼
[Dispatcher: detect admin intent / admin role]
  → AdminAgent.chat() (Plan 1)
  → Agent เรียก search_mappings("datacom") → ไม่พบ
  → Agent เรียก add_mapping(keyword="datacom", target_column="service_group", ...)
  → ถาม confirm
  
Admin ตอบ: "ใช่"
  → Apply + "เพิ่มแล้ว"

[Auto-Analyzer notification (Plan 3)]
  → Bot ส่งข้อความ: "พบ 5 queries ที่ fail ด้วย pattern เดียวกัน แนะนำเพิ่ม mapping X"
  → Admin ตอบ: "approve" / "reject"
```

## 5. ไฟล์ที่ต้องสร้าง/แก้

### ไฟล์ใหม่

| ไฟล์ | หน้าที่ |
|------|---------|
| `app/telegram/__init__.py` | Package |
| `app/telegram/bot.py` | Telegram Bot setup (polling + webhook mode) |
| `app/telegram/dispatcher.py` | Route messages (user query vs admin vs command) |
| `app/telegram/handlers.py` | Message handlers (start, help, query, admin) |
| `app/telegram/formatters.py` | Format response for Telegram (split, markdown, table) |
| `app/telegram/auth.py` | chat_id → user mapping + registration flow |
| `app/telegram/chart_renderer.py` | Render chart data → PNG image (matplotlib/plotly) |

### ไฟล์แก้

| ไฟล์ | การแก้ |
|------|--------|
| `app/config.py` | เพิ่ม TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET, BOT_MODE |
| `app/main.py` | เพิ่ม Telegram startup (polling/webhook) |
| `app/models/user.py` | เพิ่ม `telegram_chat_id` column (nullable) |
| `database/migrations/` | Migration สำหรับ telegram_chat_id |

### Config เพิ่มใน `.env`

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=123:ABCxxx
TELEGRAM_WEBHOOK_SECRET=random-secret
BOT_MODE=polling  # polling | webhook

# Telegram Auth
TELEGRAM_REQUIRE_EMAIL_VERIFY=true  # true = ต้อง OTP verify email ก่อนใช้งาน
```

## 6. User Registration Flow

```
User พิมพ์ /start
        │
        ▼
Bot: "สวัสดี กรุณาพิมพ์ email ที่ลงทะเบียนในระบบ NT AI Assistant"
        │
User: "pornthep@nt.th"
        │
        ▼
Bot: ตรวจ email ใน users table
  ├── ไม่พบ → "ไม่พบ email นี้ในระบบ กรุณาติดต่อ admin"
  └── พบ → ส่ง OTP ไป email (ใช้ existing OTP service)
        │
User: พิมพ์ OTP "123456"
        │
        ▼
Bot: verify OTP
  ├── ผิด → "OTP ไม่ถูกต้อง"
  └── ถูก → update user.telegram_chat_id = chat_id
            → "ลงทะเบียนสำเร็จ ถามข้อมูลได้เลย"
```

## 7. Chart Rendering สำหรับ Telegram

Telegram ไม่ render HTML/JS → ต้อง render เป็นรูป:

```python
# app/telegram/chart_renderer.py

import matplotlib
matplotlib.use('Agg')  # Non-GUI backend
import matplotlib.pyplot as plt
import io

async def render_chart_to_image(chart_config: Dict, data: List[Dict]) -> bytes:
    """Render chart data → PNG bytes สำหรับส่งผ่าน Telegram"""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    chart_type = chart_config.get("visualization", "bar_chart")
    
    if chart_type in ("bar_chart", "grouped_bar"):
        # ... render bar chart
    elif chart_type == "line_chart":
        # ... render line chart
    elif chart_type == "pie_chart":
        # ... render pie chart
    
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.read()
```

## 8. Rate Limiting & Security

ยืมจาก OpenMiniCrew `telegram_common.py`:
- Token bucket rate limiter (30 msg/sec per chat)
- Message splitting (Telegram limit 4096 chars)
- Webhook secret verification
- User auth (chat_id → user_id → is_active check)

---

## Claude Code Instructions

```
## ไฟล์ที่ต้องอ่านก่อน
- OpenMiniCrew:
  /Users/seal/Documents/GitHub/openminicrew/interfaces/telegram_polling.py
  /Users/seal/Documents/GitHub/openminicrew/interfaces/telegram_webhook.py
  /Users/seal/Documents/GitHub/openminicrew/interfaces/telegram_common.py
  /Users/seal/Documents/GitHub/openminicrew/dispatcher.py
  
- NT AI Assistant:
  app/api/v1/chat.py (QueryEngine flow)
  app/services/query_engine.py (execute query)
  app/services/admin_agent.py (จาก Plan 1)
  app/models/user.py (user model)
  app/services/otp_service.py (OTP verification)

## ลำดับ Implementation

Phase 1: Infrastructure
  1. เพิ่ม config: TELEGRAM_BOT_TOKEN, BOT_MODE
  2. สร้าง app/telegram/ directory structure
  3. สร้าง bot.py (polling + webhook setup)
  4. สร้าง auth.py (chat_id → user mapping)
  5. DB migration: users.telegram_chat_id
  6. สร้าง /start registration flow

Phase 2: User Query
  7. สร้าง dispatcher.py (route free text → QueryEngine)
  8. สร้าง formatters.py (table, text, split)
  9. สร้าง handlers.py (/help, /context, /model, free text query)
  10. ทดสอบ: ถามคำถามภาษาไทย → ได้คำตอบ + ตาราง

Phase 3: Chart & Export
  11. สร้าง chart_renderer.py (matplotlib)
  12. Integrate: ถ้า response มี chart data → render → ส่งรูป
  13. Integrate: ReportExportTool → ส่งไฟล์ CSV

Phase 4: Admin Commands
  14. Integrate AdminAgent (Plan 1) ใน dispatcher
  15. Admin role check (user.role == "admin")
  16. ทดสอบ: admin คุย → agent ใช้ tools

Phase 5: Notifications (ต้องรอ Plan 3)
  17. Auto-analyzer → send notification ผ่าน Telegram
  18. Approve/reject flow ผ่าน Telegram

## กฎ
- ยืม pattern จาก OpenMiniCrew แต่ไม่ copy code ตรง (เพราะ framework ต่างกัน)
- OpenMiniCrew ใช้ python-telegram-bot library → ใช้เหมือนกัน
- User ต้อง verify email ก่อนใช้งาน (security)
- Admin commands ต้อง check role
- Chart render ใช้ matplotlib (มี dependency แล้ว) ไม่ต้อง install ใหม่
- Rate limit ป้องกัน abuse
```
