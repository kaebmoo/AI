-- Migration 025: Admin Agent conversation storage
-- Stores conversation history for the Admin Agent tool-calling dispatcher

CREATE TABLE IF NOT EXISTS admin_agent_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS admin_agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT DEFAULT '',
    tool_name TEXT,
    tool_args TEXT,
    tool_result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES admin_agent_conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_admin_agent_messages_conversation
    ON admin_agent_messages(conversation_id);

CREATE INDEX IF NOT EXISTS ix_admin_agent_conversations_user
    ON admin_agent_conversations(user_id);
