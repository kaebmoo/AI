-- ============================================================
-- Migration 005: Add context_name to schema_semantic_mapping
-- ============================================================
-- Purpose: Allow semantic mappings to be scoped to a specific context.
--   NULL  = global (applies to ALL contexts, backward-compatible)
--   value = scoped to that context only (e.g., 'transfer price')
-- ============================================================

ALTER TABLE schema_semantic_mapping
    ADD COLUMN context_name TEXT DEFAULT NULL;

-- Index for fast filtering by context
CREATE INDEX IF NOT EXISTS idx_semantic_mapping_context
    ON schema_semantic_mapping(context_name);

-- ============================================================
-- Backfill: assign context_name for transfer-price-specific mappings
-- (those referencing owner_department / user_department)
-- ============================================================
UPDATE schema_semantic_mapping
SET context_name = 'transfer price'
WHERE target_column IN ('owner_department', 'user_department',
                        'owner_division',   'user_division')
   OR (full_condition IS NOT NULL AND (
       full_condition LIKE '%owner_department%'
    OR full_condition LIKE '%user_department%'
    OR full_condition LIKE '%owner_division%'
    OR full_condition LIKE '%user_division%'
   ));

-- ============================================================
-- Update view to expose context_name to AI prompt builder
-- ============================================================
DROP VIEW IF EXISTS v_semantic_mappings_for_ai;
CREATE VIEW v_semantic_mappings_for_ai AS
SELECT
    keyword,
    keyword_type,
    target_column,
    target_condition,
    full_condition,
    description,
    priority,
    context_name
FROM schema_semantic_mapping
WHERE is_active = 1
ORDER BY priority DESC, keyword;
