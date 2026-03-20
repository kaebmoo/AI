# Telegram Bot — คู่มือการใช้งาน

## ภาพรวม

Telegram Bot ช่วยให้ผู้ใช้สามารถสอบถามข้อมูลรายได้ ค่าใช้จ่าย ผ่าน Telegram ได้โดยตรง รองรับทั้งข้อความตอบกลับและกราฟ (PNG)

## Setup

### 1. สร้าง Bot

1. เปิด Telegram แล้วค้นหา `@BotFather`
2. พิมพ์ `/newbot`
3. ตั้งชื่อและ username สำหรับ bot
4. คัดลอก Bot Token ที่ได้

### 2. ตั้งค่า Environment Variables

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_WEBHOOK_SECRET=your_random_secret_string
```

### 3. Start Bot

Bot จะเริ่มทำงานอัตโนมัติเมื่อ start main app:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. ตั้ง Webhook (Production)

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/api/v1/telegram/webhook" \
  -d "secret_token=your_random_secret_string"
```

## ลงทะเบียนผู้ใช้

ผู้ใช้ต้องลงทะเบียนด้วยอีเมลองค์กรก่อนใช้งาน:

1. พิมพ์ `/start yourname@nt.co.th`
2. Bot จะส่ง OTP ไปที่อีเมล
3. พิมพ์ OTP 6 หลักที่ได้รับ
4. ลงทะเบียนสำเร็จ — เริ่มถามคำถามได้เลย

## คำสั่งพื้นฐาน

| คำสั่ง | คำอธิบาย |
|--------|----------|
| `/start <email>` | ลงทะเบียนด้วยอีเมลองค์กร |
| `/help` | แสดงคำสั่งทั้งหมดและวิธีใช้ |
| `/context` | เลือกชุดข้อมูล (revenue, expense, etc.) |

## ถามคำถาม

พิมพ์คำถามภาษาไทยได้โดยตรง:

- "รายได้รวมปี 68"
- "Top 5 สินค้ารายได้สูงสุด"
- "ค่าใช้จ่ายกลุ่ม mobile เดือนมกราคม"
- "เปรียบเทียบรายได้ Q1 กับ Q2"

### ตัวอย่างการตอบกลับ

Bot จะตอบกลับด้วย:

1. **ข้อความ:** คำอธิบายผลลัพธ์เป็นภาษาไทย
2. **ตาราง:** ข้อมูลในรูปแบบตาราง (จัดรูปแบบให้อ่านง่าย)
3. **กราฟ (PNG):** กราฟแท่ง, เส้น, หรือวงกลม ตามความเหมาะสมของข้อมูล

## Admin Commands

Admin (ตรวจสอบจากอีเมลที่ลงทะเบียน) สามารถใช้คำสั่งจัดการระบบ:

- "เพิ่ม mapping datacom" — เรียก Admin Agent
- "ดู feedback ล่าสุด" — วิเคราะห์ feedback
- "refresh cache" — ล้าง cache

ผู้ใช้ทั่วไปจะไม่สามารถใช้คำสั่ง admin ได้ — ระบบจะตอบว่าไม่มีสิทธิ์

## Message Formatting

- ข้อความยาวจะถูกแบ่งอัตโนมัติ (Telegram limit: 4096 ตัวอักษร)
- Markdown escaping สำหรับ special characters
- ตารางจัดรูปแบบด้วย monospace font

## Chart Rendering

กราฟสร้างด้วย matplotlib และส่งเป็นรูป PNG:

| ประเภทกราฟ | เหมาะกับข้อมูล |
|------------|----------------|
| Bar chart | เปรียบเทียบค่าระหว่างหมวดหมู่ |
| Line chart | แสดงแนวโน้มตามเวลา |
| Pie chart | แสดงสัดส่วน |

รองรับ Thai font สำหรับ labels และ title

## Architecture

```
Telegram User
    |
    v
Telegram Webhook (POST /api/v1/telegram/webhook)
    |
    v
Dispatcher
    |-- /start, /help, /context -> Handlers (command)
    |-- Free text (user) -> QueryEngine -> Response + Chart
    |-- Free text (admin) -> AdminAgent -> Tool execution
    |
    v
Formatters -> Message splitting -> Telegram API
```

## Database Tables

`database/migrations/029_telegram_support.sql` สร้างตาราง:

| Table | คำอธิบาย |
|-------|----------|
| `telegram_users` | ผู้ใช้ Telegram ที่ลงทะเบียน |
| `telegram_otp` | OTP สำหรับยืนยันอีเมล |
| `telegram_chat_link` | เชื่อมต่อ chat_id กับ user account |

## Troubleshooting

| ปัญหา | วิธีแก้ |
|--------|---------|
| Bot ไม่ตอบ | ตรวจสอบ TELEGRAM_BOT_TOKEN ใน .env |
| ลงทะเบียนไม่ได้ | ตรวจสอบว่าอีเมลอยู่ใน domain ที่อนุญาต |
| ไม่ได้รับ OTP | ตรวจสอบ email service configuration |
| กราฟไม่แสดง | ตรวจสอบว่า matplotlib ติดตั้งแล้ว |
