"""
NT AI Assistant -- Telegram Handlers
======================================
Top-level handler functions registered with the python-telegram-bot Application.
Each handler creates its own DB session and delegates to TelegramDispatcher.

These are thin wrappers that handle:
1. DB session lifecycle (create / close per request)
2. Rate limiting
3. Delegation to TelegramDispatcher for business logic
"""

import logging

logger = logging.getLogger(__name__)


def _get_db_session(context):
    """Create a new SQLAlchemy session using the db_url stored in bot_data.

    Falls back to the default SessionLocal if no custom db_url was provided.
    """
    db_url = context.bot_data.get("db_url")
    if db_url:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
        engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
        Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return Session()
    else:
        from app.db.session import SessionLocal

        return SessionLocal()


def _check_rate_limit(update, context) -> bool:
    """Check rate limit for the chat_id. Returns True if blocked."""
    limiter = context.bot_data.get("rate_limiter")
    if limiter and not limiter.is_allowed(update.effective_chat.id):
        return True
    return False


# ---------------------------------------------------------------------------
# Lazy dispatcher singleton
# ---------------------------------------------------------------------------
_dispatcher = None


def _get_dispatcher():
    global _dispatcher
    if _dispatcher is None:
        from app.telegram.dispatcher import TelegramDispatcher

        _dispatcher = TelegramDispatcher()
    return _dispatcher


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def handle_start(update, context) -> None:
    """/start command -- registration or welcome."""
    if _check_rate_limit(update, context):
        await update.message.reply_text("คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
        return

    db = _get_db_session(context)
    try:
        await _get_dispatcher().dispatch(update, context, db)
    finally:
        db.close()


async def handle_help(update, context) -> None:
    """/help command -- show available commands."""
    if _check_rate_limit(update, context):
        await update.message.reply_text("คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
        return

    db = _get_db_session(context)
    try:
        await _get_dispatcher().dispatch(update, context, db)
    finally:
        db.close()


async def handle_context(update, context) -> None:
    """/context command -- select data context."""
    if _check_rate_limit(update, context):
        await update.message.reply_text("คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
        return

    db = _get_db_session(context)
    try:
        await _get_dispatcher().dispatch(update, context, db)
    finally:
        db.close()


async def handle_admin(update, context) -> None:
    """/admin command -- explicit admin operations (F5.3)."""
    if _check_rate_limit(update, context):
        await update.message.reply_text("คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
        return

    db = _get_db_session(context)
    try:
        await _get_dispatcher().dispatch(update, context, db)
    finally:
        db.close()


async def handle_message(update, context) -> None:
    """Free-text message -- query or OTP verification."""
    if _check_rate_limit(update, context):
        await update.message.reply_text("คุณส่งข้อความเร็วเกินไป กรุณารอสักครู่")
        return

    db = _get_db_session(context)
    try:
        await _get_dispatcher().dispatch(update, context, db)
    finally:
        db.close()


async def handle_callback(update, context) -> None:
    """Inline keyboard button callback (e.g. context selection)."""
    query = update.callback_query
    if not query:
        return

    await query.answer()

    data = query.data or ""

    # Context selection: "ctx:<context_name>"
    if data.startswith("ctx:"):
        context_name = data[4:]
        context.user_data["context"] = context_name
        await query.edit_message_text(
            f"เปลี่ยนชุดข้อมูลเป็น: {context_name}\n"
            "สามารถพิมพ์คำถามได้เลย"
        )
        logger.info(
            f"Context switched to '{context_name}' for chat_id={update.effective_chat.id}"
        )
        return

    # Unknown callback
    await query.edit_message_text("คำสั่งไม่รู้จัก กรุณาลองใหม่")
