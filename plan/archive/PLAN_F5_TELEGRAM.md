# PLAN F5 — Telegram: Webhook Lifecycle + Admin Routing + Runtime Cleanup

> **ตรวจ source ซ้ำ 2026-09-21:** แผนนี้มี implementation แล้ว ไม่ต้อง execute ซ้ำ; สถานะรายข้อ หลักฐาน และ acceptance ที่ยังค้างดู [รายงาน F1–F8](../REVIEW_F1_F8_2026-09-21.md) ข้อความและ checklist ด้านล่างคงไว้เป็นแผนในอดีต

**Prerequisite:** PLAN_F2 เสร็จ
**ประมาณเวลา:** 1 วัน
**หมายเหตุ:** แผนนี้รวมทุกจุดที่แตะ `app/main.py` ส่วน Telegram — ห้ามทำขนานกับแผนอื่นที่แก้ main.py

## READ FIRST

- `app/main.py` (lifespan ทั้งก้อน)
- `app/telegram/bot.py`
- `app/telegram/dispatcher.py`
- `app/telegram/handlers.py` ← **ยังไม่เคย review** อ่านทั้งไฟล์ (ดูว่า handle_message/handle_callback ผูกกับ dispatcher ยังไง, rate_limiter ถูกใช้ตรงไหน)
- `app/config.py` (ตัวแปร TELEGRAM_*)
- เอกสาร python-telegram-bot เวอร์ชันที่ติดตั้ง (`pip show python-telegram-bot`) เรื่อง `Application.initialize/start/stop/shutdown`, `Application.running`, `bot.set_webhook`, `bot.delete_webhook`

---

## F5.1 — Webhook mode: initialize application จาก main lifespan (B5)

**ปัญหา:** `get_webhook_app()` พึ่ง `@webhook_app.on_event("startup")` เพื่อ `application.initialize()` แต่ Starlette/FastAPI **ไม่รัน lifespan/startup ของ sub-app ที่ถูก `mount()`** → webhook mode จะ process_update บน application ที่ไม่ initialize (PTB raise RuntimeError) — น่าจะไม่เคยถูกทดสอบจริง (QA ที่ผ่านมาเป็น polling)

**การแก้ (`app/main.py` lifespan):**

```python
if settings.TELEGRAM_BOT_MODE == "webhook":
    webhook_app = bot.get_webhook_app()
    app.mount("/telegram", webhook_app)
    await bot.application.initialize()
    await bot.application.start()
    if settings.TELEGRAM_WEBHOOK_URL:
        await bot.application.bot.set_webhook(
            url=settings.TELEGRAM_WEBHOOK_URL,
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET or None,
            drop_pending_updates=True,
        )
        logger.info(f"Telegram webhook registered: {settings.TELEGRAM_WEBHOOK_URL}")
    else:
        logger.warning("TELEGRAM_BOT_MODE=webhook แต่ TELEGRAM_WEBHOOK_URL ว่าง — ต้องเรียก setWebhook เอง")
```

และฝั่ง shutdown:

```python
if hasattr(app.state, "telegram_bot"):
    bot_app = app.state.telegram_bot.application
    try:
        if bot_app.running:            # public property — แทน _running
            await bot_app.stop()
        await bot_app.shutdown()
        if settings.TELEGRAM_BOT_MODE == "polling" and bot_app.updater and bot_app.updater.running:
            await bot_app.updater.stop()
    except Exception as e:
        logger.warning(f"Telegram bot shutdown error: {e}")
```

(ปรับลำดับ updater.stop → app.stop → app.shutdown ให้ตรง PTB docs เวอร์ชันที่ติดตั้ง — เช็คจริงก่อนเขียน)

ใน `bot.get_webhook_app()`: ลบ `on_event("startup"/"shutdown")` ออก (ไม่เคยทำงาน + deprecated) — ใส่ comment ว่า lifecycle จัดการโดย main lifespan; คง `/health` endpoint

## F5.2 — Polling mode: กัน conflict กับ webhook เก่า + เก็บ task reference

1. ใน `_start_telegram_polling` ก่อน `start_polling`: `await app_instance.bot.delete_webhook(drop_pending_updates=True)` — ถ้าเคยตั้ง webhook ค้างไว้ getUpdates จะ conflict
2. `asyncio.create_task(...)` ต้องเก็บ reference กัน GC:

```python
app.state.telegram_polling_task = asyncio.create_task(_start_telegram_polling(bot))
app.state.telegram_polling_task.add_done_callback(
    lambda t: logger.error(f"Telegram polling task ended: {t.exception()}") if t.exception() else None
)
```

## F5.3 — Admin routing: เลิก hijack ด้วย regex, ใช้ `/admin` explicit (B6)

**ปัญหา:** `_ADMIN_PATTERNS = (เพิ่ม|ลบ|แก้ไข|...)` เป็น substring — admin ถาม "รายได้**เพิ่ม**ขึ้นเท่าไร" หรือ "เดือนไหนติด**ลบ**" ถูกส่งเข้า AdminAgent แทน QueryEngine (คำเหล่านี้เป็น morpheme ปกติของภาษาไทย)

**การแก้ (`dispatcher.py`):**
1. ลบ block `if _auth.is_admin(...) and _ADMIN_PATTERNS.search(text)` ออกจาก `dispatch` (ลบ `_ADMIN_PATTERNS` ด้วย)
2. เพิ่ม command `/admin` ใน `_handle_command`:

```python
elif cmd == "/admin":
    await self._cmd_admin(args, update, context, db)
```

`_cmd_admin`: ตรวจ `_auth.is_admin(chat_id, db)` → ไม่ใช่: ตอบ "คำสั่งนี้สำหรับผู้ดูแลระบบ" / ใช่: args ว่าง → อธิบายวิธีใช้พร้อมตัวอย่าง, args มี → ส่งเข้า `_handle_admin_query(args, ...)` เดิม
3. เช็ค `handlers.py` (อ่านแล้วตาม READ FIRST): ถ้า command ถูก register ที่ระดับ PTB `CommandHandler` ใน `bot.py` ต้องเพิ่ม `CommandHandler("admin", ...)` ให้ครบวงจร — เลือกทางที่สอดคล้องกับโครงที่มีอยู่จริง (dispatcher-routed หรือ handler-routed) อย่าทำสองทาง
4. อัปเดต `/help` เพิ่มบรรทัด `/admin <คำสั่ง>` (แสดงเฉพาะข้อความกลาง ไม่ต้องซ่อนจาก non-admin — กด แล้วโดนปฏิเสธเองได้)

## F5.4 — Chart type guess: เคารพ viz_config ก่อน (เก็บเล็ก)

`_guess_chart_type` มีอยู่แล้ว — ตรวจว่า `qr.explanation` แบบ dict ที่มี `visualization` ถูกส่งถึงฟังก์ชันนี้จริงหรือไม่ (ปัจจุบันอ่านจาก `qr.visualization` attribute ซึ่งอาจไม่มี) — อ่านโครง `QueryResult` แล้วแก้ให้ดึงจาก explanation dict เมื่อเป็น dict; ถ้าโครงถูกอยู่แล้วให้ข้ามข้อนี้พร้อมจดยืนยันใน commit message

---

## การทดสอบ

Unit:
- `tests/unit/test_telegram_admin_command.py`: `/admin เพิ่ม mapping ...` โดย admin → AdminAgent ถูกเรียก (mock); โดย non-admin → ข้อความปฏิเสธ; ข้อความ free-text "รายได้เพิ่มขึ้นเท่าไร" โดย admin → QueryEngine ถูกเรียก (ไม่ใช่ AdminAgent)
- webhook secret ผิด → 403 (มีอยู่แล้ว? เช็คก่อน ถ้าไม่มีเพิ่ม)

Manual (บังคับ — webhook mode ไม่เคยถูกพิสูจน์):
1. Polling: รันปกติ ส่งข้อความ → ตอบ, ปิด server → shutdown log สะอาดไม่มี exception
2. Webhook: ใช้ ngrok/cloudflared ชั่วคราว ตั้ง `TELEGRAM_BOT_MODE=webhook`, `TELEGRAM_WEBHOOK_URL=https://<tunnel>/telegram/webhook`, secret → ส่งข้อความจริงจาก Telegram → ได้คำตอบ; ตรวจ `getWebhookInfo` ว่า url/secret ตั้งสำเร็จ
3. สลับกลับ polling → delete_webhook ทำงาน (ไม่เจอ 409 Conflict)

## Acceptance Criteria

- [ ] pytest ผ่าน + tests ใหม่ผ่าน
- [ ] Manual webhook end-to-end ผ่าน (แนบ log ใน PR/commit message)
- [ ] ไม่มีการอ้าง `_running` (private) เหลือใน repo
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md` (Telegram: webhook verified) และ `.env.example` ถ้ามี key ใหม่/คำอธิบายเพิ่ม
