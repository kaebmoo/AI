-- Migration 029: Add telegram_chat_id to user_sessions for Telegram bot auth
-- Also add telegram_chat_id to users table for direct user lookup

ALTER TABLE users ADD COLUMN telegram_chat_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_users_telegram_chat_id ON users(telegram_chat_id);
