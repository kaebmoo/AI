"""
NT AI Assistant -- Telegram Bot
================================
Main bot class that sets up the python-telegram-bot Application,
registers handlers, and provides both polling (dev) and webhook (prod) modes.
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from app.services.mcp_client import MCPClientService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter (simple in-memory, per chat_id)
# ---------------------------------------------------------------------------

_rate_window = 60  # seconds
_rate_limit = 30  # max messages per window


class _RateLimiter:
    """Sliding-window rate limiter keyed by chat_id."""

    def __init__(self, window: int = _rate_window, limit: int = _rate_limit):
        self.window = window
        self.limit = limit
        self._timestamps: dict[int, list[float]] = defaultdict(list)

    def is_allowed(self, chat_id: int) -> bool:
        """Return True if the chat_id is within the rate limit."""
        now = time.time()
        timestamps = self._timestamps[chat_id]
        # Prune old entries
        self._timestamps[chat_id] = [t for t in timestamps if now - t < self.window]
        if len(self._timestamps[chat_id]) >= self.limit:
            return False
        self._timestamps[chat_id].append(now)
        return True


_limiter = _RateLimiter()


# ---------------------------------------------------------------------------
# Bot class
# ---------------------------------------------------------------------------

class NTAIBot:
    """Telegram bot for NT AI Assistant.

    Provides two runtime modes:
    - ``start_polling()`` for local development (long-polling).
    - ``get_webhook_app()`` returns a FastAPI sub-app for production webhooks.

    Usage (polling)::

        bot = NTAIBot(token="BOT_TOKEN", db_url="sqlite:///./app.db")
        bot.start_polling()

    Usage (webhook)::

        bot = NTAIBot(token="BOT_TOKEN", db_url="sqlite:///./app.db")
        webhook_app = bot.get_webhook_app()
        # Mount: main_app.mount("/telegram", webhook_app)
    """

    def __init__(
        self,
        token: str,
        db_url: Optional[str] = None,
        webhook_secret: str = "",
        mcp_client: Optional[MCPClientService] = None,
    ):
        """
        Args:
            token: Telegram Bot API token.
            db_url: SQLAlchemy database URL.  Falls back to ``settings.DATABASE_URL``.
            webhook_secret: Secret token for webhook verification (X-Telegram-Bot-Api-Secret-Token).
        """
        self.token = token
        self.db_url = db_url
        self._webhook_secret = webhook_secret
        self._mcp_client = mcp_client
        self._application = None

    # ── Lazy application builder ──────────────────────────────────────────

    def _build_application(self):
        """Build the python-telegram-bot Application with all handlers."""
        from telegram.ext import (
            Application,
            CommandHandler,
            MessageHandler,
            CallbackQueryHandler,
            filters,
        )
        from app.telegram.handlers import (
            handle_start,
            handle_help,
            handle_context,
            handle_message,
            handle_callback,
        )

        builder = Application.builder().token(self.token)
        app = builder.build()

        # Store db_url in bot_data so handlers can create sessions
        app.bot_data["db_url"] = self.db_url
        app.bot_data["rate_limiter"] = _limiter
        app.bot_data["mcp_client"] = self._mcp_client

        # Register handlers (order matters -- commands first)
        app.add_handler(CommandHandler("start", handle_start))
        app.add_handler(CommandHandler("help", handle_help))
        app.add_handler(CommandHandler("context", handle_context))
        app.add_handler(CallbackQueryHandler(handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        self._application = app
        return app

    @property
    def application(self):
        if self._application is None:
            self._build_application()
        return self._application

    # ── Polling (dev) ─────────────────────────────────────────────────────

    def start_polling(self) -> None:
        """Start the bot in long-polling mode (blocking). For development."""
        logger.info("Starting Telegram bot in polling mode...")
        self.application.run_polling(drop_pending_updates=True)

    # ── Webhook (prod) ────────────────────────────────────────────────────

    def get_webhook_app(self):
        """Return a FastAPI sub-app that handles Telegram webhook POSTs.

        Mount this on your main FastAPI app::

            from app.telegram.bot import NTAIBot
            bot = NTAIBot(token=settings.TELEGRAM_BOT_TOKEN)
            app.mount("/telegram", bot.get_webhook_app())

        The webhook endpoint will be at ``POST /telegram/webhook``.
        """
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        webhook_app = FastAPI(title="NT AI Telegram Webhook")
        app = self.application

        @webhook_app.on_event("startup")
        async def on_startup():
            await app.initialize()

        @webhook_app.on_event("shutdown")
        async def on_shutdown():
            await app.shutdown()

        @webhook_app.post("/webhook")
        async def webhook_handler(request: Request):
            """Receive Telegram webhook updates with secret verification."""
            # Verify webhook secret (Telegram sends this header if configured)
            if self._webhook_secret:
                token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if token != self._webhook_secret:
                    return JSONResponse({"ok": False, "error": "Forbidden"}, status_code=403)

            try:
                from telegram import Update

                data = await request.json()
                update = Update.de_json(data, app.bot)
                await app.process_update(update)
                return JSONResponse({"ok": True})
            except Exception as e:
                logger.error(f"Webhook processing error: {e}", exc_info=True)
                return JSONResponse({"ok": False, "error": str(e)}, status_code=200)

        @webhook_app.get("/health")
        async def health():
            return {"status": "ok", "bot": "NTAIBot"}

        return webhook_app
