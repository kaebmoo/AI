-- Migration 022: Add tier column to ai_models
-- Allows providers to select models by tier (default/cheap) from DB instead of hardcoding

-- Add tier column (idempotent: ignore if already exists)
ALTER TABLE ai_models ADD COLUMN tier TEXT DEFAULT 'default';

-- Set cheap tier for cost-effective models
UPDATE ai_models SET tier = 'cheap' WHERE model_id = 'claude-haiku-3-5-20241022';
UPDATE ai_models SET tier = 'cheap' WHERE model_id = 'gemini-2.0-flash-exp';
UPDATE ai_models SET tier = 'cheap' WHERE model_id = 'gpt-3.5-turbo';
