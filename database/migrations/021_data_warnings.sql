-- Migration 021: Create data_warnings table
-- Moves hardcoded warning definitions to database for admin management

CREATE TABLE IF NOT EXISTS data_warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    keywords TEXT NOT NULL,            -- JSON array of trigger keywords
    exclude_keywords TEXT,             -- JSON array of keywords that prevent trigger
    columns_to_check TEXT NOT NULL,    -- JSON array of column names to scan
    message TEXT NOT NULL,
    severity TEXT DEFAULT 'warning',   -- info, warning, important
    context_name TEXT,                 -- NULL = all contexts
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Seed with existing hardcoded warning
INSERT OR IGNORE INTO data_warnings (code, keywords, exclude_keywords, columns_to_check, message, severity, context_name, is_active)
VALUES (
    'OTHER_REVENUE_NOT_NET',
    '["รายได้อื่น"]',
    '["ผลตอบแทนทางการเงิน"]',
    '["BUSINESS_GROUP", "SERVICE_GROUP", "PRODUCT_NAME", "gl_group"]',
    'หมายเหตุ: ''รายได้อื่น'' เป็นรายได้ที่ยังไม่สุทธิ',
    'warning',
    NULL,
    1
);
