-- Migration 009: Master Hierarchy
-- Auto-extractable from data, overridable by admin/master data files
--
-- This replaces hardcoded COLUMN_HIERARCHIES in ai_service.py

CREATE TABLE IF NOT EXISTS master_hierarchy (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    context_name        TEXT NOT NULL,
    level               INTEGER NOT NULL,
    level_label_th      TEXT NOT NULL,
    level_label_en      TEXT NOT NULL,
    level_columns       TEXT NOT NULL,          -- JSON array: ["BUSINESS_GROUP", "BUSINESS"]
    detection_keywords  TEXT NOT NULL,           -- JSON array: ["กลุ่มธุรกิจ", "business"]
    is_active           BOOLEAN DEFAULT 1,
    source              TEXT DEFAULT 'auto',     -- 'auto' (extracted from data) or 'manual' (admin/file)
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(context_name, level)
);

-- Hierarchy values: the actual parent-child relationships
-- Auto-extracted from DISTINCT combinations in the data
CREATE TABLE IF NOT EXISTS master_hierarchy_values (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    context_name    TEXT NOT NULL,
    level           INTEGER NOT NULL,
    value           TEXT NOT NULL,
    parent_value    TEXT,                        -- NULL for top level (level 0)
    aliases         TEXT,                        -- JSON array of alternative names/keywords
    source          TEXT DEFAULT 'auto',
    is_active       BOOLEAN DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(context_name, level, value)
);

CREATE INDEX IF NOT EXISTS idx_mhv_context_level ON master_hierarchy_values(context_name, level);
CREATE INDEX IF NOT EXISTS idx_mhv_value ON master_hierarchy_values(value);
CREATE INDEX IF NOT EXISTS idx_mhv_parent ON master_hierarchy_values(parent_value);
