"""P1 review fix: /admin must be registered at the PTB Application level.

python-telegram-bot isn't installed in CI, so telegram.ext is faked just enough
for _build_application to run — what we assert is the registration wiring.
"""

import sys
import types
from unittest.mock import MagicMock, patch


def _fake_telegram_ext():
    """Fake telegram.ext capturing CommandHandler registrations."""
    ext = types.ModuleType("telegram.ext")
    registered = []

    class CommandHandler:
        def __init__(self, command, callback):
            self.command = command
            self.callback = callback
            registered.append(("command", command, callback))

    class MessageHandler:
        def __init__(self, filters, callback):
            registered.append(("message", None, callback))

    class CallbackQueryHandler:
        def __init__(self, callback):
            registered.append(("callback", None, callback))

    app = MagicMock()
    app.bot_data = {}
    builder = MagicMock()
    builder.token.return_value = builder
    builder.build.return_value = app

    class Application:
        @staticmethod
        def builder():
            return builder

    filters_mod = MagicMock()
    ext.Application = Application
    ext.CommandHandler = CommandHandler
    ext.MessageHandler = MessageHandler
    ext.CallbackQueryHandler = CallbackQueryHandler
    ext.filters = filters_mod

    telegram_mod = types.ModuleType("telegram")
    telegram_mod.ext = ext
    return telegram_mod, ext, registered


def test_admin_command_registered_on_application():
    telegram_mod, ext, registered = _fake_telegram_ext()
    with patch.dict(sys.modules, {"telegram": telegram_mod, "telegram.ext": ext}):
        from app.telegram.bot import NTAIBot
        bot = NTAIBot(token="t")
        bot._build_application()

    commands = [cmd for kind, cmd, _ in registered if kind == "command"]
    assert "admin" in commands, f"/admin not registered — got {commands}"
    assert set(commands) >= {"start", "help", "context", "admin"}

    # /admin routes through handle_admin → dispatcher (same wiring as other commands)
    # (compare by qualified name — patch.dict restore re-imports the module object)
    admin_cb = next(cb for kind, cmd, cb in registered if cmd == "admin")
    assert admin_cb.__module__ == "app.telegram.handlers"
    assert admin_cb.__name__ == "handle_admin"
