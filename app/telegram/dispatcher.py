"""
NT AI Assistant -- Telegram Dispatcher
========================================
Routes incoming Telegram messages to the correct handler:
- Commands (/start, /help, /context, /admin) go to their respective handlers.
- All free-text goes to QueryEngine (admin work is explicit via /admin — B6:
  regex intent detection misfired on normal Thai like "รายได้เพิ่มขึ้น").
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.telegram.auth import TelegramAuth
from app.telegram.formatters import (
    format_error_message,
    format_table_data,
    split_long_message,
)
from app.telegram.chart_renderer import render_chart_to_png

logger = logging.getLogger(__name__)

_auth = TelegramAuth()


class TelegramDispatcher:
    """Routes Telegram updates to the appropriate processing logic."""

    # ── Main dispatch ─────────────────────────────────────────────────────

    async def dispatch(self, update: Any, context: Any, db: Session) -> None:
        """Route an incoming Telegram update.

        ``update`` and ``context`` are python-telegram-bot objects, imported
        lazily so tests can run without the library installed.

        Args:
            update: ``telegram.Update``
            context: ``telegram.ext.ContextTypes.DEFAULT_TYPE``
            db: SQLAlchemy session (created per-request by the caller).
        """
        # Ignore non-message updates handled elsewhere (callbacks, etc.)
        if not update.message:
            return

        message = update.message
        chat_id = message.chat_id
        text = (message.text or "").strip()

        if not text:
            return

        # ── Commands ──────────────────────────────────────────────────
        if text.startswith("/"):
            await self._handle_command(text, update, context, db)
            return

        # ── Authentication gate ───────────────────────────────────────
        user = _auth.get_user_by_chat_id(chat_id, db)

        # Check if user is in the middle of OTP verification
        pending_email = context.user_data.get("pending_email")
        if not user and pending_email:
            await self._handle_otp_verification(chat_id, text, update, context, db)
            return

        if not user:
            await message.reply_text(
                "กรุณาลงทะเบียนก่อนใช้งาน\n"
                "พิมพ์ /start แล้วทำตามขั้นตอน"
            )
            return

        # ── Normal query (admin work goes through /admin explicitly) ──
        await self._handle_query(text, user, update, context, db)

    # ── Command router ────────────────────────────────────────────────────

    async def _handle_command(
        self, text: str, update: Any, context: Any, db: Session
    ) -> None:
        cmd = text.split()[0].lower().replace("@", " ").split()[0]  # strip bot mention
        args = text[len(cmd):].strip()

        if cmd == "/start":
            await self._cmd_start(args, update, context, db)
        elif cmd == "/help":
            await self._cmd_help(update, context)
        elif cmd == "/context":
            await self._cmd_context(update, context, db)
        elif cmd == "/admin":
            await self._cmd_admin(args, update, context, db)
        else:
            await update.message.reply_text("คำสั่งไม่รู้จัก พิมพ์ /help เพื่อดูคำสั่งทั้งหมด")

    # ── /start ────────────────────────────────────────────────────────────

    async def _cmd_start(
        self, args: str, update: Any, context: Any, db: Session
    ) -> None:
        chat_id = update.message.chat_id
        user = _auth.get_user_by_chat_id(chat_id, db)

        if user:
            await update.message.reply_text(
                f"สวัสดี {user.display_name or user.email}!\n"
                "คุณลงทะเบียนแล้ว สามารถพิมพ์คำถามได้เลย\n"
                "พิมพ์ /help เพื่อดูคำสั่งทั้งหมด"
            )
            return

        # Start registration -- ask for email
        if args and "@" in args:
            # Email provided inline: /start user@nt.co.th
            email = args.strip()
            result = _auth.start_registration(chat_id, email, db)
            if result["success"]:
                context.user_data["pending_email"] = email
            await update.message.reply_text(result["message"])
        else:
            await update.message.reply_text(
                "สวัสดี! ยินดีต้อนรับสู่ NT AI Assistant\n\n"
                "กรุณาพิมพ์อีเมลองค์กรของคุณเพื่อลงทะเบียน\n"
                "ตัวอย่าง: /start yourname@nt.co.th"
            )

    # ── OTP verification ──────────────────────────────────────────────────

    async def _handle_otp_verification(
        self,
        chat_id: int,
        otp_text: str,
        update: Any,
        context: Any,
        db: Session,
    ) -> None:
        """Handle OTP input during registration flow."""
        otp = otp_text.strip()

        # Basic format check (digits only, expected length)
        if not otp.isdigit() or len(otp) < 4:
            await update.message.reply_text(
                "กรุณาพิมพ์รหัส OTP ที่ส่งไปทางอีเมล (ตัวเลขเท่านั้น)"
            )
            return

        result = _auth.verify_otp(chat_id, otp, db)
        if result["success"]:
            context.user_data.pop("pending_email", None)
            await update.message.reply_text(
                f"{result['message']}\n\n"
                "สามารถพิมพ์คำถามเกี่ยวกับข้อมูลได้เลย\n"
                "พิมพ์ /help เพื่อดูคำสั่งทั้งหมด"
            )
        else:
            await update.message.reply_text(result["message"])

    # ── /help ─────────────────────────────────────────────────────────────

    async def _cmd_help(self, update: Any, context: Any) -> None:
        help_text = (
            "NT AI Assistant - คำสั่งที่ใช้ได้\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "/start <email> - ลงทะเบียนด้วยอีเมลองค์กร\n"
            "/help - แสดงคำสั่งทั้งหมด\n"
            "/context - เลือกชุดข้อมูลที่ต้องการถาม\n"
            "/admin <คำสั่ง> - จัดการระบบ (สำหรับผู้ดูแลระบบ)\n"
            "\n"
            "วิธีใช้งาน:\n"
            "พิมพ์คำถามเป็นภาษาไทยได้เลย เช่น\n"
            '  "รายได้รวมเดือนมกราคม 2568"\n'
            '  "รายได้แยกตามสายงาน ปี 2568"\n'
            '  "Top 5 สินค้าที่มีรายได้สูงสุด"\n'
        )
        await update.message.reply_text(help_text)

    # ── /context ──────────────────────────────────────────────────────────

    async def _cmd_context(self, update: Any, context: Any, db: Session) -> None:
        """Show available data contexts as inline buttons."""
        try:
            from app.services.schema_service import SchemaService
            from app.db.session import business_engine, config_engine

            # ponytail: per-call SchemaService is fine here — /context is a rare
            # manual command, not the query hot path (F2.5 targets the retry loop)
            schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
            contexts = schema_service.get_all_contexts()
        except Exception as e:
            logger.error(f"Failed to load contexts: {e}")
            await update.message.reply_text("ไม่สามารถโหลดรายการชุดข้อมูลได้")
            return

        if not contexts:
            await update.message.reply_text("ไม่พบชุดข้อมูลในระบบ")
            return

        # Build inline keyboard lazily
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            # Fallback: text-based listing
            lines = ["เลือกชุดข้อมูล:"]
            for ctx in contexts:
                name = ctx.get("name", "?")
                desc = ctx.get("description", "")
                lines.append(f"  - {name}: {desc}")
            lines.append("\nพิมพ์ชื่อ context ที่ต้องการ")
            await update.message.reply_text("\n".join(lines))
            return

        buttons = []
        for ctx in contexts:
            name = ctx.get("name", "?")
            desc = ctx.get("description", name)
            buttons.append(
                [InlineKeyboardButton(f"{name} - {desc}", callback_data=f"ctx:{name}")]
            )

        current = context.user_data.get("context", "auto")
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            f"ชุดข้อมูลปัจจุบัน: {current}\nเลือกชุดข้อมูลที่ต้องการ:",
            reply_markup=reply_markup,
        )

    # ── Query execution ───────────────────────────────────────────────────

    async def _handle_query(
        self, text: str, user: Any, update: Any, context: Any, db: Session
    ) -> None:
        """Execute a data query via QueryEngine and send results."""
        chat_id = update.message.chat_id

        # Typing indicator
        await update.message.chat.send_action("typing")

        try:
            from app.services.query_engine import QueryEngine
            from app.services.mcp_client import MCPClientService

            selected_context = context.user_data.get("context")
            shared_mcp_client = context.bot_data.get("mcp_client")

            engine = None
            try:
                if shared_mcp_client:
                    engine = QueryEngine(mcp_client=shared_mcp_client, db_session=db)
                    result = await engine.query(
                        question=text,
                        context=selected_context,
                        history=context.user_data.get("history", []),
                        user_id=getattr(user, "id", None), channel="telegram",
                    )
                else:
                    mcp_client = MCPClientService()
                    async with mcp_client.connected():
                        engine = QueryEngine(mcp_client=mcp_client, db_session=db)
                        result = await engine.query(
                            question=text,
                            context=selected_context,
                            history=context.user_data.get("history", []),
                            user_id=getattr(user, "id", None), channel="telegram",
                        )
            finally:
                if engine is not None:
                    engine.close()  # release self-created config-DB session

            qr = result.query_result

            # Update conversation history (keep last 10 turns)
            history = context.user_data.get("history", [])
            history.append({"role": "user", "content": text})
            if qr.explanation:
                history.append({"role": "assistant", "content": qr.explanation})
            context.user_data["history"] = history[-20:]  # 10 turns = 20 messages

            # Send explanation
            if qr.explanation:
                for chunk in split_long_message(qr.explanation):
                    await update.message.reply_text(chunk)

            # Send data table if available
            if qr.data:
                table_text = format_table_data(qr.data)
                for chunk in split_long_message(table_text, max_length=4096):
                    await update.message.reply_text(chunk, parse_mode="HTML")

                # Try to render a chart
                if len(qr.data) >= 2:
                    chart_type = _guess_chart_type(qr)
                    try:
                        png_bytes = render_chart_to_png(
                            data=qr.data,
                            chart_type=chart_type,
                            title=text[:60],
                        )
                        if png_bytes:
                            import io
                            await update.message.reply_photo(
                                photo=io.BytesIO(png_bytes),
                                caption="กราฟจากข้อมูล",
                            )
                    except Exception as e:
                        logger.warning(f"Chart render failed: {e}")

            # Handle error case
            if qr.error and not qr.explanation:
                await update.message.reply_text(format_error_message(qr.error))

        except Exception as e:
            logger.error(f"Query execution error for chat_id={chat_id}: {e}", exc_info=True)
            await update.message.reply_text(format_error_message(str(e)))

    # ── Admin query ───────────────────────────────────────────────────────

    # ── /admin ────────────────────────────────────────────────────────────

    async def _cmd_admin(
        self, args: str, update: Any, context: Any, db: Session
    ) -> None:
        """Explicit admin entry point — /admin <คำสั่ง> routes to AdminAgent."""
        chat_id = update.message.chat_id
        if not _auth.is_admin(chat_id, db):
            await update.message.reply_text("คำสั่งนี้สำหรับผู้ดูแลระบบเท่านั้น")
            return

        if not args:
            await update.message.reply_text(
                "วิธีใช้: /admin <คำสั่ง>\n"
                "ตัวอย่าง:\n"
                '  /admin เพิ่ม mapping "มือถือ" → BUSINESS_GROUP = Mobile\n'
                "  /admin ดู rules ของ context revenue\n"
                "  /admin เพิ่ม golden example ..."
            )
            return

        user = _auth.get_user_by_chat_id(chat_id, db)
        await self._handle_admin_query(args, user, update, context, db)

    async def _handle_admin_query(
        self, text: str, user: Any, update: Any, context: Any, db: Session
    ) -> None:
        """Route admin commands to AdminAgent."""
        await update.message.chat.send_action("typing")

        try:
            from app.services.admin_agent import AdminAgent

            agent = AdminAgent(db=db)
            result = await agent.chat(
                message=text,
                user_id=user.id,
            )

            response = result.get("response", "ดำเนินการเรียบร้อย")
            for chunk in split_long_message(response):
                await update.message.reply_text(chunk)

        except Exception as e:
            logger.error(f"Admin agent error: {e}", exc_info=True)
            await update.message.reply_text(
                "เกิดข้อผิดพลาดในการดำเนินการ admin กรุณาลองใหม่"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _guess_chart_type(qr: Any) -> str:
    """Heuristic to pick a chart type from query result."""
    if not qr.data:
        return "bar"

    # If the AI recommended a chart type, respect it — QueryResult carries it
    # inside the explanation dict (there is no qr.visualization attribute)
    explanation = getattr(qr, "explanation", None)
    if isinstance(explanation, dict) and explanation.get("visualization"):
        viz = explanation["visualization"]
        if isinstance(viz, dict):
            return viz.get("type", "bar")
        return str(viz)

    cols = list(qr.data[0].keys()) if qr.data else []
    num_rows = len(qr.data)

    # Pie: small number of rows, likely category breakdown
    if 2 <= num_rows <= 8 and len(cols) == 2:
        return "pie"

    # Line: time-based or many rows
    time_cols = {"year", "month", "quarter", "date", "YEAR", "MONTH"}
    if any(c.lower() in {t.lower() for t in time_cols} for c in cols):
        return "line"

    return "bar"
