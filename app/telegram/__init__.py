"""
NT AI Assistant -- Telegram Bot Interface
==========================================
Provides query and admin capabilities via Telegram.

Usage (polling / dev)::

    from app.telegram.bot import NTAIBot
    bot = NTAIBot(token="BOT_TOKEN")
    bot.start_polling()

Usage (webhook / prod)::

    from app.telegram.bot import NTAIBot
    bot = NTAIBot(token="BOT_TOKEN")
    webhook_app = bot.get_webhook_app()
    # main_app.mount("/telegram", webhook_app)
"""
