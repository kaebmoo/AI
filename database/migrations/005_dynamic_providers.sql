-- ============================================================
-- NT AI Assistant - Dynamic AI Providers & Models
-- Purpose: Enable admin to add/remove AI providers and models via Web UI
-- Version: 1.0
-- Date: 2025-02-09
-- ============================================================

-- ============================================================
-- Table: ai_providers
-- Stores AI provider information
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_providers (
    id TEXT PRIMARY KEY,                    -- e.g., 'claude', 'gemini', 'matcha', 'openai'
    name TEXT NOT NULL,                     -- Display name: 'Claude', 'Gemini'
    display_name TEXT,                      -- Full display: 'Claude (Anthropic)'
    icon TEXT DEFAULT 'bulb',               -- Icon name for UI (Ionicons)
    is_active BOOLEAN DEFAULT 1,            -- Admin can enable/disable
    is_default BOOLEAN DEFAULT 0,           -- Is this the default provider?
    api_key_env_var TEXT,                   -- Environment variable name: 'ANTHROPIC_API_KEY'
    api_url_env_var TEXT,                   -- For providers with custom URLs: 'MATCHA_API_URL'
    default_api_url TEXT,                   -- Default API URL if not in env
    description TEXT,                       -- Provider description
    priority INTEGER DEFAULT 0,             -- Display order (higher = first)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Table: ai_models
-- Stores available models for each provider
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,              -- Foreign key to ai_providers.id
    model_id TEXT NOT NULL,                 -- e.g., 'gpt-4o', 'claude-sonnet-4-5'
    display_name TEXT,                      -- Display name for UI
    is_active BOOLEAN DEFAULT 1,            -- Admin can enable/disable
    is_default BOOLEAN DEFAULT 0,           -- Is this the default model for this provider?
    context_window INTEGER,                 -- Max tokens (optional)
    supports_vision BOOLEAN DEFAULT 0,      -- Supports image input
    cost_per_1m_tokens REAL,                -- Cost tracking (optional)
    description TEXT,                       -- Model description
    priority INTEGER DEFAULT 0,             -- Display order
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES ai_providers(id) ON DELETE CASCADE,
    UNIQUE(provider_id, model_id)
);

-- ============================================================
-- Create Indices
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_ai_providers_active ON ai_providers(is_active);
CREATE INDEX IF NOT EXISTS idx_ai_providers_default ON ai_providers(is_default);
CREATE INDEX IF NOT EXISTS idx_ai_models_provider ON ai_models(provider_id);
CREATE INDEX IF NOT EXISTS idx_ai_models_active ON ai_models(is_active, provider_id);

-- ============================================================
-- Insert Default Providers (Hardcoded Fallback)
-- ============================================================
INSERT OR IGNORE INTO ai_providers (id, name, display_name, icon, is_active, is_default, api_key_env_var, priority, description)
VALUES
    ('claude', 'Claude', 'Claude (Anthropic)', 'bulb', 1, 0, 'ANTHROPIC_API_KEY', 20, 'Anthropic Claude models - Best for reasoning and analysis'),
    ('gemini', 'Gemini', 'Gemini (Google)', 'sparkles', 1, 0, 'GOOGLE_AI_API_KEY', 10, 'Google Gemini models - Fast and efficient'),
    ('matcha', 'Matcha', 'Matcha (NT Gateway)', 'leaf', 1, 1, 'MATCHA_AI_API_KEY', 30, 'OpenAI models via NT Gateway - Default provider');

-- ============================================================
-- Insert Default Models (Hardcoded Fallback)
-- ============================================================

-- Claude Models
INSERT OR IGNORE INTO ai_models (provider_id, model_id, display_name, is_active, is_default, context_window, supports_vision, priority, description)
VALUES
    ('claude', 'claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5 (Latest)', 1, 1, 200000, 1, 40, 'Latest Sonnet model - Balanced performance'),
    ('claude', 'claude-sonnet-4-20250514', 'Claude Sonnet 4', 1, 0, 200000, 1, 30, 'Sonnet 4 - High quality responses'),
    ('claude', 'claude-opus-4-20250514', 'Claude Opus 4', 1, 0, 200000, 1, 20, 'Most powerful Claude model'),
    ('claude', 'claude-haiku-3-5-20241022', 'Claude Haiku 3.5', 1, 0, 200000, 1, 10, 'Fastest Claude model');

-- Gemini Models
INSERT OR IGNORE INTO ai_models (provider_id, model_id, display_name, is_active, is_default, context_window, supports_vision, priority, description)
VALUES
    ('gemini', 'gemini-3-flash-preview', 'Gemini 3 Flash (Preview)', 1, 1, 1000000, 1, 40, 'Latest Gemini model - Fast and capable'),
    ('gemini', 'gemini-2.0-flash-exp', 'Gemini 2.0 Flash (Experimental)', 1, 0, 1000000, 1, 30, 'Experimental fast model'),
    ('gemini', 'gemini-2.0-flash-thinking-exp-1219', 'Gemini 2.0 Flash Thinking', 1, 0, 32000, 1, 20, 'Optimized for reasoning'),
    ('gemini', 'gemini-1.5-pro', 'Gemini 1.5 Pro', 1, 0, 2000000, 1, 10, 'Large context window model');

-- Matcha (OpenAI via NT Gateway) Models
INSERT OR IGNORE INTO ai_models (provider_id, model_id, display_name, is_active, is_default, context_window, supports_vision, priority, description)
VALUES
    ('matcha', 'gpt-4.1', 'GPT-4.1 (NT Gateway)', 1, 1, 128000, 1, 40, 'Latest GPT-4 model via NT Gateway'),
    ('matcha', 'gpt-4o', 'GPT-4o', 1, 0, 128000, 1, 30, 'GPT-4 Optimized'),
    ('matcha', 'gpt-4-turbo', 'GPT-4 Turbo', 1, 0, 128000, 1, 20, 'Fast GPT-4 variant'),
    ('matcha', 'gpt-3.5-turbo', 'GPT-3.5 Turbo', 1, 0, 16000, 0, 10, 'Cost-effective option');

-- ============================================================
-- Update admin_config to link with ai_providers
-- ============================================================

-- Update matcha_api_url in admin_config if not exists
INSERT OR IGNORE INTO admin_config (config_key, config_value, config_type, category, display_name, description)
VALUES ('matcha_api_url', 'https://aigateway.ntictsolution.com/v1/chat/completions', 'api_key', 'ai', 'Matcha API URL', 'NT Gateway API endpoint for Matcha (OpenAI compatible)');

-- ============================================================
-- Create View: v_active_providers
-- Returns active providers with their default models
-- ============================================================
CREATE VIEW IF NOT EXISTS v_active_providers AS
SELECT
    p.id,
    p.name,
    p.display_name,
    p.icon,
    p.is_default,
    m.model_id as default_model,
    m.display_name as default_model_name,
    p.api_key_env_var,
    p.api_url_env_var,
    p.default_api_url
FROM ai_providers p
LEFT JOIN ai_models m ON p.id = m.provider_id AND m.is_default = 1
WHERE p.is_active = 1
ORDER BY p.priority DESC, p.name;

-- ============================================================
-- Create View: v_active_models
-- Returns active models grouped by provider
-- ============================================================
CREATE VIEW IF NOT EXISTS v_active_models AS
SELECT
    m.id,
    m.provider_id,
    p.name as provider_name,
    m.model_id,
    m.display_name,
    m.is_default,
    m.context_window,
    m.supports_vision,
    m.description
FROM ai_models m
JOIN ai_providers p ON m.provider_id = p.id
WHERE m.is_active = 1 AND p.is_active = 1
ORDER BY p.priority DESC, m.priority DESC, m.display_name;

-- ============================================================
-- Triggers for updated_at
-- ============================================================
CREATE TRIGGER IF NOT EXISTS update_ai_providers_timestamp
AFTER UPDATE ON ai_providers
BEGIN
    UPDATE ai_providers SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_ai_models_timestamp
AFTER UPDATE ON ai_models
BEGIN
    UPDATE ai_models SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- Constraint: Only one default provider
-- ============================================================
CREATE TRIGGER IF NOT EXISTS enforce_single_default_provider
BEFORE UPDATE ON ai_providers
WHEN NEW.is_default = 1 AND OLD.is_default = 0
BEGIN
    UPDATE ai_providers SET is_default = 0 WHERE is_default = 1 AND id != NEW.id;
END;

-- ============================================================
-- Constraint: Only one default model per provider
-- ============================================================
CREATE TRIGGER IF NOT EXISTS enforce_single_default_model_per_provider
BEFORE UPDATE ON ai_models
WHEN NEW.is_default = 1 AND OLD.is_default = 0
BEGIN
    UPDATE ai_models SET is_default = 0 WHERE provider_id = NEW.provider_id AND is_default = 1 AND id != NEW.id;
END;

-- ============================================================
-- Migration Complete
-- ============================================================
