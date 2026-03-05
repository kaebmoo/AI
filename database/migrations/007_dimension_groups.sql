-- ============================================================
-- Migration: Add Dimension Groups
-- Purpose: Group related columns into dimension families so AI
--          never splits columns from the same entity across
--          row/column axes in crosstab/pivot charts.
-- Version: 1.0
-- Date: 2025-03-05
-- ============================================================

-- Add dimension_group column to schema_metadata
ALTER TABLE schema_metadata ADD COLUMN dimension_group TEXT DEFAULT NULL;

-- ============================================================
-- Populate dimension groups for known column families
-- ============================================================

-- Organization hierarchy families
UPDATE schema_metadata SET dimension_group = 'org_division'
WHERE column_name IN ('DIVISION', 'DIVISION_ABBR');

UPDATE schema_metadata SET dimension_group = 'org_group'
WHERE column_name IN ('GROUP', 'GROUP_ABBR');

UPDATE schema_metadata SET dimension_group = 'org_department'
WHERE column_name IN ('DEPARTMENT', 'DEPARTMENT_ABBR');

UPDATE schema_metadata SET dimension_group = 'org_section'
WHERE column_name IN ('SECTION', 'SECTION_ABBR');

UPDATE schema_metadata SET dimension_group = 'org_cost_center'
WHERE column_name IN ('COST_CENTER', 'COST_CENTER_DEPARTMENT');

-- Accounting families
UPDATE schema_metadata SET dimension_group = 'acct_gl'
WHERE column_name IN ('GL_CODE', 'GL_NAME', 'GL_GROUP');

UPDATE schema_metadata SET dimension_group = 'acct_report'
WHERE column_name IN ('REPORT_CODE')
   OR column_name = 'หมวดบัญชี';

-- Product families
UPDATE schema_metadata SET dimension_group = 'prod_product'
WHERE column_name IN ('PRODUCT_KEY', 'PRODUCT_NAME', 'PRODUCT');

UPDATE schema_metadata SET dimension_group = 'prod_sub_product'
WHERE column_name IN ('SUB_PRODUCT_KEY', 'SUB_PRODUCT_NAME', 'SUB_PRODUCT');

-- Business/service families
UPDATE schema_metadata SET dimension_group = 'biz_item'
WHERE column_name IN ('ITEM', 'BUSINESS', 'BUSINESS_GROUP');

UPDATE schema_metadata SET dimension_group = 'biz_service'
WHERE column_name IN ('SUB_ITEM', 'SERVICE', 'SERVICE_GROUP');

-- Time family
UPDATE schema_metadata SET dimension_group = 'time'
WHERE column_name IN ('YEAR', 'MONTH', 'DATE');

-- Business group (Thai column)
UPDATE schema_metadata SET dimension_group = 'biz_item'
WHERE column_name = 'กลุ่มธุรกิจ'
  AND dimension_group IS NULL;

-- ============================================================
-- Update v_pivot_metadata view to include dimension_group
-- ============================================================
DROP VIEW IF EXISTS v_pivot_metadata;

CREATE VIEW v_pivot_metadata AS
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
    format_hint,
    dimension_group
FROM schema_metadata
WHERE pivot_behavior != 'exclude'
ORDER BY table_name, display_priority, column_name;

-- ============================================================
-- Business rule: Dimension Family Rule
-- ============================================================
INSERT OR IGNORE INTO schema_business_rules (
    rule_code,
    rule_name,
    rule_description,
    applies_to,
    example_correct,
    example_wrong,
    severity
) VALUES (
    'DIMENSION_FAMILY',
    'Same-Family Columns Must Share Axis',
    'Columns belonging to the same dimension family (e.g. SECTION and SECTION_ABBR) must be on the same axis in crosstab/pivot charts. Never split code/abbr/name of the same entity across row and column axes.',
    '*',
    'Rows: SECTION, SECTION_ABBR — Columns: MONTH',
    'Rows: SECTION_ABBR — Columns: SECTION (same family split across axes)',
    'error'
);
