-- ============================================================
-- NT AI Assistant - Admin Configuration & Schema Contexts
-- Purpose: Admin settings and multi-context support
-- Version: 1.0
-- Date: 2025-02-09
-- ============================================================

-- ============================================================
-- Table: admin_config
-- Purpose: Store runtime configuration (AI providers, models, features)
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT NOT NULL UNIQUE,
    config_value TEXT,
    config_type TEXT NOT NULL,  -- 'ai_provider', 'model', 'api_key', 'feature_flag', 'database'
    category TEXT,              -- 'ai', 'database', 'security', 'features'
    display_name TEXT,          -- For UI display
    description TEXT,           -- Help text for admin UI
    is_active INTEGER DEFAULT 1,
    is_sensitive INTEGER DEFAULT 0,  -- Mask value in UI if 1
    validation_regex TEXT,      -- Optional validation pattern
    default_value TEXT,         -- Default value if config is deleted
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,            -- User email who made the change
    metadata TEXT               -- JSON field for extra data
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_admin_config_type ON admin_config(config_type, is_active);
CREATE INDEX IF NOT EXISTS idx_admin_config_category ON admin_config(category, is_active);

-- ============================================================
-- Table: schema_contexts
-- Purpose: Multi-context/database support for dynamic data sources
-- ============================================================
CREATE TABLE IF NOT EXISTS schema_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,              -- Context identifier (e.g., 'revenue', 'expense')
    display_name TEXT NOT NULL,             -- Display name in UI
    description TEXT,                       -- Context description
    main_view TEXT NOT NULL,                -- Main view/table name
    keywords TEXT,                          -- Comma-separated keywords for auto-detection
    priority INTEGER DEFAULT 0,             -- Higher = preferred in auto-detection
    database_url TEXT,                      -- Optional: Different database connection
    default_instruction TEXT,               -- Custom AI instruction for this context
    sample_queries TEXT,                    -- JSON array of example queries
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    metadata TEXT                           -- JSON field for extra settings
);

-- Index for context routing
CREATE INDEX IF NOT EXISTS idx_schema_contexts_active ON schema_contexts(is_active, priority DESC);

-- ============================================================
-- Insert Default AI Provider Configuration
-- ============================================================

-- AI Provider Settings (Matcha as default)
INSERT INTO admin_config (config_key, config_value, config_type, category, display_name, description, is_active, is_sensitive)
VALUES
    ('default_ai_provider', 'matcha', 'ai_provider', 'ai', 'Default AI Provider', 'Which AI provider to use by default (claude, gemini, matcha)', 1, 0),
    ('claude_enabled', 'true', 'ai_provider', 'ai', 'Enable Claude', 'Allow users to select Claude (Anthropic)', 1, 0),
    ('gemini_enabled', 'true', 'ai_provider', 'ai', 'Enable Gemini', 'Allow users to select Google Gemini', 1, 0),
    ('matcha_enabled', 'true', 'ai_provider', 'ai', 'Enable Matcha', 'Allow users to select Matcha (OpenAI-compatible)', 1, 0);

-- AI Model Configuration
INSERT INTO admin_config (config_key, config_value, config_type, category, display_name, description, is_active, is_sensitive)
VALUES
    ('claude_model', 'claude-sonnet-4-5-20250929', 'model', 'ai', 'Claude Model', 'Claude model to use', 1, 0),
    ('gemini_model', 'gemini-3-flash-preview', 'model', 'ai', 'Gemini Model', 'Gemini model to use', 1, 0),
    ('matcha_model', 'gpt-4.1', 'model', 'ai', 'Matcha Model', 'Matcha model to use', 1, 0);

-- API Keys (masked in UI)
INSERT INTO admin_config (config_key, config_value, config_type, category, display_name, description, is_active, is_sensitive)
VALUES
    ('anthropic_api_key', NULL, 'api_key', 'ai', 'Anthropic API Key', 'API key for Claude', 1, 1),
    ('google_ai_api_key', NULL, 'api_key', 'ai', 'Google AI API Key', 'API key for Gemini', 1, 1),
    ('matcha_api_key', NULL, 'api_key', 'ai', 'Matcha API Key', 'API key for Matcha gateway', 1, 1),
    ('matcha_api_url', 'https://aigateway.ntictsolution.com/v1/chat/completions', 'api_key', 'ai', 'Matcha API URL', 'Matcha gateway endpoint', 1, 0);

-- Feature Flags
INSERT INTO admin_config (config_key, config_value, config_type, category, display_name, description, is_active, is_sensitive)
VALUES
    ('rag_enabled', 'false', 'feature_flag', 'features', 'Enable RAG', 'Enable Retrieval-Augmented Generation', 1, 0),
    ('auto_context_detection', 'true', 'feature_flag', 'features', 'Auto Context Detection', 'Automatically detect context from question keywords', 1, 0),
    ('debug_mode', 'false', 'feature_flag', 'features', 'Debug Mode', 'Show debug information in responses', 1, 0),
    ('log_queries', 'true', 'feature_flag', 'features', 'Log SQL Queries', 'Save all generated SQL queries to database', 1, 0),
    ('collect_feedback', 'true', 'feature_flag', 'features', 'Collect User Feedback', 'Enable user feedback collection', 1, 0);

-- Database Settings
INSERT INTO admin_config (config_key, config_value, config_type, category, display_name, description, is_active, is_sensitive)
VALUES
    ('query_timeout_seconds', '30', 'database', 'database', 'Query Timeout', 'Max seconds for SQL query execution', 1, 0),
    ('max_result_rows', '10000', 'database', 'database', 'Max Result Rows', 'Maximum rows to return from queries', 1, 0);

-- ============================================================
-- Insert Default Schema Contexts
-- ============================================================
INSERT INTO schema_contexts (
    name,
    display_name,
    description,
    main_view,
    keywords,
    priority,
    default_instruction,
    sample_queries,
    is_active
)
VALUES
    -- Revenue Context
    (
        'revenue',
        'รายได้ (Revenue)',
        'ข้อมูลรายได้รวมของ NT แยกตามหน่วยงาน, ผลิตภัณฑ์, และบัญชี',
        'revenue',
        'รายได้,revenue,ขาย,sales,income,เงิน',
        10,
        'คุณเป็น AI ที่เชี่ยวชาญด้านการวิเคราะห์รายได้ของ NT โดยข้อมูลใน revenue มีหน่วยเป็นบาท และ YEAR อยู่ในรูปแบบ ค.ศ. ถ้าผู้ใช้ถามเป็นปี พ.ศ. ให้แปลงเป็น ค.ศ. (ลบ 543)',
        '["รายได้รวมเดือนมกราคม 2568", "รายได้แยกตามกลุ่มธุรกิจ", "Top 10 สายงานที่มีรายได้สูงสุด"]',
        1
    ),

    -- Expense Context
    (
        'expense',
        'ค่าใช้จ่าย (Expense)',
        'ข้อมูลค่าใช้จ่ายของ NT',
        'expense',
        'ค่าใช้จ่าย,expense,cost,ต้นทุน,จ่าย',
        9,
        'คุณเป็น AI ที่เชี่ยวชาญด้านการวิเคราะห์ค่าใช้จ่ายของ NT',
        '["ค่าใช้จ่ายรวมปี 2568", "ค่าใช้จ่ายแยกตามประเภท"]',
        1
    );

-- ============================================================
-- Views for Admin UI
-- ============================================================

-- Active AI Providers
CREATE VIEW IF NOT EXISTS v_active_ai_providers AS
SELECT
    config_key,
    config_value as provider_name,
    CASE config_key
        WHEN 'claude_enabled' THEN 'claude'
        WHEN 'gemini_enabled' THEN 'gemini'
        WHEN 'matcha_enabled' THEN 'matcha'
    END as provider_id,
    is_active
FROM admin_config
WHERE config_type = 'ai_provider'
  AND config_key LIKE '%_enabled'
  AND config_value = 'true'
  AND is_active = 1;

-- Active Contexts for Context Selector
CREATE VIEW IF NOT EXISTS v_active_contexts AS
SELECT
    id,
    name,
    display_name,
    description,
    main_view,
    keywords,
    priority,
    sample_queries
FROM schema_contexts
WHERE is_active = 1
ORDER BY priority DESC, name;

-- AI Configuration Summary
CREATE VIEW IF NOT EXISTS v_ai_config AS
SELECT
    (SELECT config_value FROM admin_config WHERE config_key = 'default_ai_provider' AND is_active = 1) as default_provider,
    (SELECT config_value FROM admin_config WHERE config_key = 'claude_model' AND is_active = 1) as claude_model,
    (SELECT config_value FROM admin_config WHERE config_key = 'gemini_model' AND is_active = 1) as gemini_model,
    (SELECT config_value FROM admin_config WHERE config_key = 'matcha_model' AND is_active = 1) as matcha_model,
    (SELECT config_value FROM admin_config WHERE config_key = 'claude_enabled' AND is_active = 1) as claude_enabled,
    (SELECT config_value FROM admin_config WHERE config_key = 'gemini_enabled' AND is_active = 1) as gemini_enabled,
    (SELECT config_value FROM admin_config WHERE config_key = 'matcha_enabled' AND is_active = 1) as matcha_enabled;

-- ============================================================
-- Trigger: Update timestamp on admin_config changes
-- ============================================================
CREATE TRIGGER IF NOT EXISTS update_admin_config_timestamp
AFTER UPDATE ON admin_config
FOR EACH ROW
BEGIN
    UPDATE admin_config
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- ============================================================
-- Trigger: Update timestamp on schema_contexts changes
-- ============================================================
CREATE TRIGGER IF NOT EXISTS update_schema_contexts_timestamp
AFTER UPDATE ON schema_contexts
FOR EACH ROW
BEGIN
    UPDATE schema_contexts
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- ============================================================
-- End of Migration
-- ============================================================
