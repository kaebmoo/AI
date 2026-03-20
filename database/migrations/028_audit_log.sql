-- Migration 028: Config audit log for tracking all config changes
-- Supports manual, admin_agent, auto_analyzer, and onboarding sources

CREATE TABLE IF NOT EXISTS config_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL CHECK(action IN ('create', 'update', 'delete', 'toggle', 'auto_apply')),
    table_name TEXT NOT NULL,
    record_id INTEGER,
    old_value TEXT,                          -- JSON of old values
    new_value TEXT,                          -- JSON of new values
    source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual', 'admin_agent', 'auto_analyzer', 'onboarding', 'api')),
    confidence REAL,                         -- For auto_analyzer suggested fixes
    source_query_ids TEXT,                   -- JSON array of chat_ids that triggered this change
    created_by INTEGER,                      -- User ID who made the change
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_log_table ON config_audit_log(table_name);
CREATE INDEX IF NOT EXISTS ix_audit_log_source ON config_audit_log(source);
CREATE INDEX IF NOT EXISTS ix_audit_log_created ON config_audit_log(created_at);

-- Suggested fixes table for auto-analyzer
CREATE TABLE IF NOT EXISTS suggested_fixes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fix_type TEXT NOT NULL,                  -- add_mapping, add_rule, add_example, update_instruction
    params TEXT NOT NULL,                    -- JSON: tool parameters
    confidence REAL NOT NULL DEFAULT 0.0,
    reason TEXT,                             -- Why this fix was suggested
    source_query_ids TEXT,                   -- JSON array of chat_ids
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'auto_applied')),
    reviewed_by INTEGER,
    reviewed_at TIMESTAMP,
    applied_audit_id INTEGER,               -- FK to config_audit_log.id after application
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_suggested_fixes_status ON suggested_fixes(status);
