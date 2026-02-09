-- ============================================================
-- Migration: Add Pivot Table Metadata
-- Purpose: Configure pivot table behavior per column
-- Version: 1.0
-- Date: 2025-02-09
-- ============================================================

-- Add new columns to schema_metadata for pivot table behavior
ALTER TABLE schema_metadata ADD COLUMN pivot_behavior TEXT DEFAULT 'auto';
ALTER TABLE schema_metadata ADD COLUMN display_priority INTEGER DEFAULT 50;
ALTER TABLE schema_metadata ADD COLUMN is_identifier INTEGER DEFAULT 0;

-- Update existing metadata with pivot behavior

-- Time columns should be columns in pivot
UPDATE schema_metadata
SET pivot_behavior = 'column',
    display_priority = 10
WHERE column_name IN ('YEAR', 'MONTH', 'DATE', 'QUARTER', 'WEEK');

-- Identifier columns should NEVER be pivot columns (always rows)
UPDATE schema_metadata
SET pivot_behavior = 'row',
    is_identifier = 1,
    display_priority = 5
WHERE column_name LIKE '%CODE%'
   OR column_name LIKE '%_ID'
   OR column_name LIKE 'GL_%'
   OR column_name LIKE '%ABBR%'
   OR column_name = 'COST_CENTER'
   OR format_hint = 'Code'
   OR format_hint = 'Abbr';

-- Name columns should be rows
UPDATE schema_metadata
SET pivot_behavior = 'row',
    display_priority = 20
WHERE column_name LIKE '%NAME%'
   AND pivot_behavior = 'auto';

-- Organization hierarchy columns should be rows
UPDATE schema_metadata
SET pivot_behavior = 'row',
    display_priority = 30
WHERE column_name IN ('DIVISION', 'GROUP', 'DEPARTMENT', 'SECTION', 'BUSINESS_GROUP')
   AND pivot_behavior = 'auto';

-- Value columns should never be used for grouping
UPDATE schema_metadata
SET pivot_behavior = 'exclude',
    display_priority = 100
WHERE is_summable = 1;

-- Note: SQLite doesn't support COMMENT ON COLUMN
-- Column descriptions:
-- pivot_behavior: 'row' (always row), 'column' (prefer column), 'auto' (let system decide), 'exclude' (never use for pivot)
-- is_identifier: Boolean flag - 1 if this column is an identifier (code, id, abbr), 0 otherwise
-- display_priority: Display priority - lower numbers appear first (Time=10, Identifiers=5, Names=20, Org=30, Values=100)

-- Create view for pivot metadata
CREATE VIEW IF NOT EXISTS v_pivot_metadata AS
SELECT
    table_name,
    column_name,
    display_name_th,
    display_name_en,
    pivot_behavior,
    is_identifier,
    is_summable,
    is_groupable,
    display_priority,
    format_hint
FROM schema_metadata
WHERE pivot_behavior != 'exclude'
ORDER BY table_name, display_priority, column_name;

-- Insert business rule for pivot table
INSERT INTO schema_business_rules (
    rule_code,
    rule_name,
    rule_description,
    applies_to,
    example_correct,
    severity
) VALUES (
    'PIVOT_IDENTIFIER_ROW',
    'Identifier Columns Must Be Rows',
    'Columns with CODE, ID, GL, ABBR should always be rows in pivot tables, never columns',
    'GL_CODE,COST_CENTER_CODE,*_ABBR,*_ID',
    'Rows: GL_CODE + GL_NAME, Columns: MONTH',
    'warning'
);
