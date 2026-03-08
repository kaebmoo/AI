-- Migration 024: Add config_schema column to ai_providers
-- Stores JSON schema of provider-specific config fields
-- Enables Admin UI to render provider settings dynamically

-- Add config_schema column (JSON text describing extra config fields per provider)
ALTER TABLE ai_providers ADD COLUMN config_schema TEXT;

-- Seed config_schema for existing providers
UPDATE ai_providers SET config_schema = '{"extended_thinking": {"type": "boolean", "default": false, "label": "Extended Thinking"}, "thinking_budget_tokens": {"type": "integer", "default": 8000, "label": "Thinking Budget Tokens"}}' WHERE id = 'claude';

UPDATE ai_providers SET config_schema = '{"api_url": {"type": "string", "env_var": "MATCHA_API_URL", "label": "API URL"}, "ssl_verify": {"type": "boolean", "default": true, "label": "SSL Verify"}, "timeout": {"type": "number", "default": 60, "label": "Timeout (sec)"}}' WHERE id = 'matcha';

-- Gemini has no extra config fields (api_key + model is enough)
UPDATE ai_providers SET config_schema = NULL WHERE id = 'gemini';
