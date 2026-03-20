"""
Plan 4: Telegram Dispatcher Tests
===================================
Tests routing logic for commands, queries, and admin operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.telegram.dispatcher import TelegramDispatcher


def _make_update(chat_id=12345, text="test"):
    """Create a mock Telegram update object."""
    update = MagicMock()
    update.message.chat_id = chat_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.reply_photo = AsyncMock()
    update.message.chat.send_action = AsyncMock()
    return update


def _make_context(user_data=None):
    """Create a mock Telegram context."""
    ctx = MagicMock()
    ctx.user_data = user_data or {}
    return ctx


class TestDispatchHelpCommand:
    """Test /help command dispatch."""

    async def test_help_returns_commands(self, db_session):
        """Sending /help → shows command list (no LLM call)."""
        dispatcher = TelegramDispatcher()
        update = _make_update(text="/help")
        context = _make_context()

        await dispatcher.dispatch(update, context, db_session)

        update.message.reply_text.assert_called_once()
        help_text = update.message.reply_text.call_args[0][0]
        assert "/start" in help_text
        assert "/help" in help_text


class TestDispatchContextCommand:
    """Test /context command dispatch."""

    async def test_context_command(self, db_session):
        """Sending /context → shows available contexts."""
        dispatcher = TelegramDispatcher()
        update = _make_update(text="/context")
        context = _make_context()

        with patch("app.telegram.dispatcher.TelegramDispatcher._cmd_context", new_callable=AsyncMock) as mock_ctx:
            await dispatcher.dispatch(update, context, db_session)
            mock_ctx.assert_called_once()


class TestDispatchFreeTextQuery:
    """Test free-text query routing."""

    async def test_unregistered_user_rejected(self, db_session):
        """Free text from unregistered user → asks to register."""
        dispatcher = TelegramDispatcher()
        update = _make_update(chat_id=99999, text="รายได้รวมปี 68")
        context = _make_context()

        with patch.object(dispatcher, "_handle_query", new_callable=AsyncMock):
            with patch("app.telegram.dispatcher._auth") as mock_auth:
                mock_auth.get_user_by_chat_id.return_value = None
                mock_auth.is_admin.return_value = False

                await dispatcher.dispatch(update, context, db_session)

                update.message.reply_text.assert_called()
                msg = update.message.reply_text.call_args[0][0]
                assert "ลงทะเบียน" in msg

    async def test_registered_user_query(self, db_session):
        """Free text from registered user → QueryEngine called."""
        dispatcher = TelegramDispatcher()
        update = _make_update(chat_id=12345, text="รายได้รวมปี 68")
        context = _make_context()

        mock_user = MagicMock()
        mock_user.id = 1

        with patch("app.telegram.dispatcher._auth") as mock_auth:
            mock_auth.get_user_by_chat_id.return_value = mock_user
            mock_auth.is_admin.return_value = False

            with patch.object(dispatcher, "_handle_query", new_callable=AsyncMock) as mock_query:
                await dispatcher.dispatch(update, context, db_session)
                mock_query.assert_called_once()


class TestDispatchAdminCommand:
    """Test admin query routing."""

    async def test_admin_mapping_request(self, db_session):
        """Admin sending 'เพิ่ม mapping' → AdminAgent called."""
        dispatcher = TelegramDispatcher()
        update = _make_update(chat_id=11111, text="เพิ่ม mapping datacom ไป service_group")
        context = _make_context()

        mock_user = MagicMock()
        mock_user.id = 1

        with patch("app.telegram.dispatcher._auth") as mock_auth:
            mock_auth.get_user_by_chat_id.return_value = mock_user
            mock_auth.is_admin.return_value = True

            with patch.object(dispatcher, "_handle_admin_query", new_callable=AsyncMock) as mock_admin:
                await dispatcher.dispatch(update, context, db_session)
                mock_admin.assert_called_once()

    async def test_non_admin_blocked_from_admin_commands(self, db_session):
        """Non-admin sending 'เพิ่ม mapping' → normal query, not admin."""
        dispatcher = TelegramDispatcher()
        update = _make_update(chat_id=22222, text="เพิ่ม mapping datacom")
        context = _make_context()

        mock_user = MagicMock()
        mock_user.id = 2

        with patch("app.telegram.dispatcher._auth") as mock_auth:
            mock_auth.get_user_by_chat_id.return_value = mock_user
            mock_auth.is_admin.return_value = False

            with patch.object(dispatcher, "_handle_query", new_callable=AsyncMock) as mock_query:
                with patch.object(dispatcher, "_handle_admin_query", new_callable=AsyncMock) as mock_admin:
                    await dispatcher.dispatch(update, context, db_session)
                    mock_query.assert_called_once()
                    mock_admin.assert_not_called()


class TestDispatchEmptyMessage:
    """Test edge cases."""

    async def test_empty_text_ignored(self, db_session):
        """Empty text message → no action."""
        dispatcher = TelegramDispatcher()
        update = _make_update(text="")
        context = _make_context()

        await dispatcher.dispatch(update, context, db_session)
        update.message.reply_text.assert_not_called()

    async def test_no_message_ignored(self, db_session):
        """Update without message → no action."""
        dispatcher = TelegramDispatcher()
        update = MagicMock()
        update.message = None
        context = _make_context()

        await dispatcher.dispatch(update, context, db_session)
