-- Migration 027: API Key authentication for external integrations (OpenMiniCrew, etc.)

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,          -- SHA-256 hash of the raw key
    key_prefix TEXT NOT NULL,               -- First 8 chars for display (e.g., "ntai_<prefix>")
    name TEXT NOT NULL DEFAULT '',          -- Human-readable name (e.g., "OpenMiniCrew Bot")
    user_id INTEGER NOT NULL,              -- Owner user ID
    scopes TEXT NOT NULL DEFAULT 'query',   -- Comma-separated: query, admin, full
    rate_limit_per_minute INTEGER DEFAULT 30,
    rate_limit_per_day INTEGER DEFAULT 1000,
    is_active INTEGER DEFAULT 1,
    expires_at TIMESTAMP,                   -- NULL = never expires
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_key_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id INTEGER NOT NULL,
    date TEXT NOT NULL,                     -- YYYY-MM-DD
    request_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE,
    UNIQUE(api_key_id, date)
);

CREATE INDEX IF NOT EXISTS ix_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS ix_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX IF NOT EXISTS ix_api_key_usage_date ON api_key_usage(api_key_id, date);
