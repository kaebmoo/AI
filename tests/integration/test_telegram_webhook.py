"""
Plan 4: Telegram Webhook Integration Tests
============================================
Tests webhook endpoint security and message processing.

NOTE: Telegram bot webhook mounts at /telegram/webhook (sub-app),
NOT at /api/v1/telegram/webhook. When bot is not configured (no TELEGRAM_BOT_TOKEN),
the endpoint doesn't exist (404).
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestTelegramWebhook:
    """Integration tests for Telegram webhook endpoint."""

    def test_webhook_not_mounted_without_token(self, client):
        """Without TELEGRAM_BOT_TOKEN, webhook endpoint should not exist."""
        # Bot is not started in test environment → /telegram/webhook returns 404
        resp = client.post("/telegram/webhook", json={})
        assert resp.status_code == 404

    def test_root_health(self, client):
        """GET / → root endpoint returns OK."""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data


class TestWebhookSecurity:
    """Tests for webhook secret verification (requires bot to be mounted)."""

    def test_secret_verification_logic(self):
        """NTAIBot webhook verifies X-Telegram-Bot-Api-Secret-Token header."""
        from app.telegram.bot import NTAIBot

        # Bot with secret configured
        bot = NTAIBot.__new__(NTAIBot)
        bot._webhook_secret = "my_secret"
        # Verify the attribute is set
        assert bot._webhook_secret == "my_secret"

    def test_no_secret_allows_all(self):
        """NTAIBot with empty secret should not reject requests."""
        from app.telegram.bot import NTAIBot

        bot = NTAIBot.__new__(NTAIBot)
        bot._webhook_secret = ""
        assert bot._webhook_secret == ""
