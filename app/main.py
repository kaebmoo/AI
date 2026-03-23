import logging

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)
from app.core.middleware import RequestIDMiddleware
from app.core.rate_limiter import limiter, RateLimitExceeded, _rate_limit_exceeded_handler
from app.services.mcp_client import MCPClientService

# Setup logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to MCP Servers
    mcp_client = MCPClientService()
    async with mcp_client.connected():
        app.state.mcp_client = mcp_client

        # Startup: Background scheduler (auto-analyzer, config GC)
        try:
            from app.services.scheduler import BackgroundScheduler
            from app.db.session import ConfigSessionLocal, SessionLocal
            scheduler = BackgroundScheduler(db_factory=SessionLocal, config_db_factory=ConfigSessionLocal)
            scheduler.start()
            app.state.scheduler = scheduler
        except Exception as e:
            logger.warning(f"Background scheduler init failed: {e}")

        # Startup: Telegram bot (if configured)
        if settings.TELEGRAM_BOT_TOKEN:
            try:
                from app.telegram.bot import NTAIBot
                bot = NTAIBot(
                    token=settings.TELEGRAM_BOT_TOKEN,
                    db_url=settings.DATABASE_URL,
                    webhook_secret=settings.TELEGRAM_WEBHOOK_SECRET,
                    mcp_client=mcp_client,
                )
                app.state.telegram_bot = bot

                if settings.TELEGRAM_BOT_MODE == "webhook":
                    webhook_app = bot.get_webhook_app()
                    app.mount("/telegram", webhook_app)
                    logger.info("Telegram bot mounted as webhook at /telegram/webhook")
                else:
                    import asyncio
                    asyncio.create_task(_start_telegram_polling(bot))
                    logger.info("Telegram bot starting in polling mode")
            except ImportError:
                logger.warning("python-telegram-bot not installed — Telegram bot disabled")
            except Exception as e:
                logger.warning(f"Telegram bot init failed: {e}")

        yield

        # Shutdown: stop scheduler
        if hasattr(app.state, 'scheduler'):
            try:
                await app.state.scheduler.stop()
            except Exception as e:
                logger.warning(f"Scheduler shutdown error: {e}")

        # Shutdown: stop Telegram polling
        if hasattr(app.state, 'telegram_bot'):
            try:
                bot_app = app.state.telegram_bot.application
                if bot_app._running:
                    await bot_app.updater.stop()
                    await bot_app.stop()
                    await bot_app.shutdown()
            except Exception as e:
                logger.warning(f"Telegram bot shutdown error: {e}")


async def _start_telegram_polling(bot):
    """Start Telegram polling in background (non-blocking)."""
    import asyncio
    try:
        await asyncio.sleep(2)  # Wait for app to finish startup
        app_instance = bot.application
        await app_instance.initialize()
        await app_instance.start()
        await app_instance.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling started")
    except Exception as e:
        logger.error(f"Telegram polling failed: {e}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# Initialize Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Set all CORS enabled origins
# Configure CORS_ORIGINS in .env as comma-separated list of allowed origins
cors_origins = settings.get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=settings.get_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)

@app.get("/")
def root():
    return {"message": "Welcome to NT AI Assistant API", "version": "1.0.0"}

# Note: Routers will be included here as they are implemented
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.admin import router as admin_router
from app.api.v1.users import router as users_router
from app.api.v1.schema_analyzer import router as analyzer_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.admin_agent import router as admin_agent_router
from app.api.v1.query import router as query_router

app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(chat_router, prefix=f"{settings.API_V1_STR}/chat", tags=["chat"])
app.include_router(feedback_router, prefix=f"{settings.API_V1_STR}/feedback", tags=["feedback"])
app.include_router(admin_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(users_router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(analyzer_router, prefix=f"{settings.API_V1_STR}/admin/analyzer", tags=["analyzer"])
app.include_router(conversations_router, prefix=f"{settings.API_V1_STR}/conversations", tags=["conversations"])
app.include_router(admin_agent_router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin-agent"])
app.include_router(query_router, prefix=f"{settings.API_V1_STR}/query", tags=["query"])
