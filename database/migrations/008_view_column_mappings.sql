-- Migration 008: View Column Mappings
-- Maps view columns back to source table columns for metadata propagation.
-- Without this, views like v_expense_mart have 0 metadata rows → AI gets no Thai names/summable flags.

CREATE TABLE IF NOT EXISTS view_column_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    view_name TEXT NOT NULL,
    view_column TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_column TEXT NOT NULL,
    mapping_type TEXT DEFAULT 'alias',  -- alias | expression | passthrough
    expression_sql TEXT,                -- original SQL expression (for expression type)
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(view_name, view_column)
);

-- ============================================================
-- Seed: revenue_search (27 columns from revenue)
-- ============================================================
INSERT OR IGNORE INTO view_column_mappings (view_name, view_column, source_table, source_column, mapping_type) VALUES
('revenue_search', 'year',                    'revenue', 'YEAR',             'alias'),
('revenue_search', 'month',                   'revenue', 'MONTH',            'alias'),
('revenue_search', 'business_unit',           'revenue', 'กลุ่มธุรกิจ',    'alias'),
('revenue_search', 'account_category',        'revenue', 'หมวดบัญชี',      'alias'),
('revenue_search', 'revenue',                 'revenue', 'REVENUE_VALUE',    'alias'),
('revenue_search', 'BUSINESS_GROUP',          'revenue', 'BUSINESS_GROUP',   'passthrough'),
('revenue_search', 'SERVICE_GROUP',           'revenue', 'SERVICE_GROUP',    'passthrough'),
('revenue_search', 'PRODUCT_NAME',            'revenue', 'PRODUCT_NAME',     'passthrough'),
('revenue_search', 'PRODUCT_KEY',             'revenue', 'PRODUCT_KEY',      'passthrough'),
('revenue_search', 'SUB_PRODUCT_NAME',        'revenue', 'SUB_PRODUCT_NAME', 'passthrough'),
('revenue_search', 'PRODUCT',                 'revenue', 'PRODUCT',          'passthrough'),
('revenue_search', 'SUB_PRODUCT',             'revenue', 'SUB_PRODUCT',      'passthrough'),
('revenue_search', 'ITEM',                    'revenue', 'ITEM',             'passthrough'),
('revenue_search', 'SUB_ITEM',                'revenue', 'SUB_ITEM',         'passthrough'),
('revenue_search', 'GL_CODE',                 'revenue', 'GL_CODE',          'passthrough'),
('revenue_search', 'GL_NAME',                 'revenue', 'GL_NAME',          'passthrough'),
('revenue_search', 'GL_GROUP',                'revenue', 'GL_GROUP',         'passthrough'),
('revenue_search', 'TYPE',                    'revenue', 'TYPE',             'passthrough'),
('revenue_search', 'division',                'revenue', 'DIVISION',         'alias'),
('revenue_search', 'department',              'revenue', 'DEPARTMENT',       'alias'),
('revenue_search', 'organization_group',      'revenue', 'GROUP',            'alias'),
('revenue_search', 'section',                 'revenue', 'SECTION',          'alias'),
('revenue_search', 'cost_center',             'revenue', 'COST_CENTER',      'alias'),
('revenue_search', 'division_abbr',           'revenue', 'DIVISION_ABBR',    'alias'),
('revenue_search', 'department_abbr',         'revenue', 'DEPARTMENT_ABBR',  'alias'),
('revenue_search', 'organization_group_abbr', 'revenue', 'GROUP_ABBR',       'alias'),
('revenue_search', 'section_abbr',            'revenue', 'SECTION_ABBR',     'alias');

-- ============================================================
-- Seed: v_expense_mart (20 columns from expense)
-- ============================================================
INSERT OR IGNORE INTO view_column_mappings (view_name, view_column, source_table, source_column, mapping_type) VALUES
('v_expense_mart', 'year',                    'expense', 'YEAR',             'alias'),
('v_expense_mart', 'month',                   'expense', 'MONTH',            'alias'),
('v_expense_mart', 'date',                    'expense', 'DATE',             'alias'),
('v_expense_mart', 'cost_center',             'expense', 'COST_CENTER',      'alias'),
('v_expense_mart', 'gl_code',                 'expense', 'GL_CODE',          'alias'),
('v_expense_mart', 'account_name',            'expense', 'GL_NAME_NT1',      'alias'),
('v_expense_mart', 'account_group_name',      'expense', 'GROUP_NAME',       'alias'),
('v_expense_mart', 'account_group_code',      'expense', 'CODE_GROUP',       'alias'),
('v_expense_mart', 'business_group',          'expense', 'กลุ่มธุรกิจ',    'alias'),
('v_expense_mart', 'nt',                      'expense', 'NT',               'alias'),
('v_expense_mart', 'type',                    'expense', 'TYPE',             'alias'),
('v_expense_mart', 'expense',                 'expense', 'EXPENSE_VALUE',    'alias'),
('v_expense_mart', 'division',                'expense', 'DIVISION',         'alias'),
('v_expense_mart', 'department',              'expense', 'DEPARTMENT',       'alias'),
('v_expense_mart', 'section',                 'expense', 'SECTION',          'alias'),
('v_expense_mart', 'organization_group',      'expense', 'GROUP',            'alias'),
('v_expense_mart', 'division_abbr',           'expense', 'DIVISION_ABBR',    'alias'),
('v_expense_mart', 'department_abbr',         'expense', 'DEPARTMENT_ABBR',  'alias'),
('v_expense_mart', 'section_abbr',            'expense', 'SECTION_ABBR',     'alias'),
('v_expense_mart', 'organization_group_abbr', 'expense', 'GROUP_ABBR',       'alias');

-- ============================================================
-- Seed: v_transfer_price (18 columns from transfer_price)
-- ============================================================
INSERT OR IGNORE INTO view_column_mappings (view_name, view_column, source_table, source_column, mapping_type) VALUES
('v_transfer_price', 'year',                'transfer_price', 'YEAR',                      'alias'),
('v_transfer_price', 'month',               'transfer_price', 'MONTH',                     'alias'),
('v_transfer_price', 'tp_product_id',       'transfer_price', 'TRANSFER_PRICE_PRODUCT_ID', 'alias'),
('v_transfer_price', 'product_name',        'transfer_price', 'Product',                   'alias'),
('v_transfer_price', 'sub_product_name',    'transfer_price', 'Sub_Product',               'alias'),
('v_transfer_price', 'unit',                'transfer_price', 'Unit',                      'alias'),
('v_transfer_price', 'unit_price',          'transfer_price', 'Unit_Price',                'alias'),
('v_transfer_price', 'total_price_value',   'transfer_price', 'PRICE_VALUE',               'alias'),
('v_transfer_price', 'quantity',            'transfer_price', 'QUANTITY',                  'alias'),
('v_transfer_price', 'owner_cc_unit',       'transfer_price', 'UNIT_COST_CENTER_OWNER',    'alias'),
('v_transfer_price', 'owner_cost_center',   'transfer_price', 'COST_CENTER_Owner',         'alias'),
('v_transfer_price', 'owner_division',      'transfer_price', 'DIVISION_Owner',            'alias'),
('v_transfer_price', 'owner_department',    'transfer_price', 'DEPARTMENT_Owner',          'alias'),
('v_transfer_price', 'user_cc_unit',        'transfer_price', 'UNIT_COST_CENTER_USER',     'alias'),
('v_transfer_price', 'user_cost_center',    'transfer_price', 'COST_CENTER_User',          'alias'),
('v_transfer_price', 'user_division',       'transfer_price', 'DIVISION_User',             'alias'),
('v_transfer_price', 'user_department',     'transfer_price', 'DEPARTMENT_User',           'alias');

-- ============================================================
-- Seed: v_pl_costtype_nt_mth_clean (11 columns)
-- Source chain: TRN_PL_COSTTYPE_NT_MTH → v_pl_costtype_nt_mth → v_pl_costtype_nt_mth_clean
-- Some columns use CASE WHEN expressions (mapping_type='expression')
-- ============================================================
INSERT OR IGNORE INTO view_column_mappings (view_name, view_column, source_table, source_column, mapping_type, expression_sql) VALUES
('v_pl_costtype_nt_mth_clean', 'report_date',    'TRN_PL_COSTTYPE_NT_MTH', 'DATE',         'alias',      NULL),
('v_pl_costtype_nt_mth_clean', 'report_year',    'TRN_PL_COSTTYPE_NT_MTH', 'YEAR',         'alias',      NULL),
('v_pl_costtype_nt_mth_clean', 'report_month',   'TRN_PL_COSTTYPE_NT_MTH', 'MONTH',        'alias',      NULL),
('v_pl_costtype_nt_mth_clean', 'main_group',     'TRN_PL_COSTTYPE_NT_MTH', 'GROUP',        'alias',      NULL),
('v_pl_costtype_nt_mth_clean', 'sub_group',      'TRN_PL_COSTTYPE_NT_MTH', 'SUB_GROUP',    'expression', 'CASE WHEN ... cleaned sub_group'),
('v_pl_costtype_nt_mth_clean', 'business_unit',  'TRN_PL_COSTTYPE_NT_MTH', 'BU',           'expression', 'CASE WHEN ... normalized business_unit'),
('v_pl_costtype_nt_mth_clean', 'service_group',  'TRN_PL_COSTTYPE_NT_MTH', 'SERVICE_GROUP', 'expression', 'CASE WHEN ... normalized service_group'),
('v_pl_costtype_nt_mth_clean', 'product_id',     'TRN_PL_COSTTYPE_NT_MTH', 'PRODUCT_KEY',  'alias',      NULL),
('v_pl_costtype_nt_mth_clean', 'product_name',   'TRN_PL_COSTTYPE_NT_MTH', 'PRODUCT_NAME', 'expression', 'COALESCE(pm.standard_name, v.product_name)'),
('v_pl_costtype_nt_mth_clean', 'alliance_flag',  'TRN_PL_COSTTYPE_NT_MTH', 'ALLIE',        'expression', 'COALESCE(v.alliance_flag, ''N'')'),
('v_pl_costtype_nt_mth_clean', 'amount_value',   'TRN_PL_COSTTYPE_NT_MTH', 'VALUE',        'alias',      NULL);

-- ============================================================
-- Bootstrap: TRN_PL_COSTTYPE_NT_MTH has no metadata but
-- v_pl_costtype_nt_mth (intermediate view) does.
-- Copy metadata to the raw table so propagation works.
-- ============================================================
INSERT OR IGNORE INTO schema_metadata (table_name, column_name, display_name_th, display_name_en, description, data_type, format_hint, example_value, is_summable, is_groupable, hierarchy_level, special_notes, conversion_sql, dimension_group)
SELECT
    'TRN_PL_COSTTYPE_NT_MTH',
    column_name,
    display_name_th,
    display_name_en,
    description,
    data_type,
    format_hint,
    example_value,
    is_summable,
    is_groupable,
    hierarchy_level,
    special_notes,
    conversion_sql,
    dimension_group
FROM schema_metadata
WHERE table_name = 'v_pl_costtype_nt_mth';

-- ============================================================
-- Propagate metadata from source tables to views
-- UPSERT: update if exists, insert if not
-- ============================================================

-- For alias/passthrough mappings: copy metadata from source → view
INSERT INTO schema_metadata (table_name, column_name, display_name_th, display_name_en, description, data_type, format_hint, example_value, is_summable, is_groupable, hierarchy_level, special_notes, conversion_sql, dimension_group)
SELECT
    vcm.view_name,
    vcm.view_column,
    sm.display_name_th,
    sm.display_name_en,
    sm.description,
    sm.data_type,
    sm.format_hint,
    sm.example_value,
    sm.is_summable,
    sm.is_groupable,
    sm.hierarchy_level,
    sm.special_notes,
    sm.conversion_sql,
    sm.dimension_group
FROM view_column_mappings vcm
JOIN schema_metadata sm
    ON sm.table_name = vcm.source_table
    AND sm.column_name = vcm.source_column
WHERE NOT EXISTS (
    SELECT 1 FROM schema_metadata existing
    WHERE existing.table_name = vcm.view_name
    AND existing.column_name = vcm.view_column
);

-- Update existing rows that have NULL display_name_th (e.g. revenue_search rows with empty metadata)
UPDATE schema_metadata
SET
    display_name_th = (
        SELECT sm.display_name_th
        FROM view_column_mappings vcm
        JOIN schema_metadata sm ON sm.table_name = vcm.source_table AND sm.column_name = vcm.source_column
        WHERE vcm.view_name = schema_metadata.table_name AND vcm.view_column = schema_metadata.column_name
    ),
    display_name_en = COALESCE(display_name_en, (
        SELECT sm.display_name_en
        FROM view_column_mappings vcm
        JOIN schema_metadata sm ON sm.table_name = vcm.source_table AND sm.column_name = vcm.source_column
        WHERE vcm.view_name = schema_metadata.table_name AND vcm.view_column = schema_metadata.column_name
    )),
    is_summable = COALESCE((
        SELECT sm.is_summable
        FROM view_column_mappings vcm
        JOIN schema_metadata sm ON sm.table_name = vcm.source_table AND sm.column_name = vcm.source_column
        WHERE vcm.view_name = schema_metadata.table_name AND vcm.view_column = schema_metadata.column_name
    ), is_summable),
    special_notes = COALESCE(special_notes, (
        SELECT sm.special_notes
        FROM view_column_mappings vcm
        JOIN schema_metadata sm ON sm.table_name = vcm.source_table AND sm.column_name = vcm.source_column
        WHERE vcm.view_name = schema_metadata.table_name AND vcm.view_column = schema_metadata.column_name
    )),
    updated_at = CURRENT_TIMESTAMP
WHERE display_name_th IS NULL
AND EXISTS (
    SELECT 1 FROM view_column_mappings vcm
    JOIN schema_metadata sm ON sm.table_name = vcm.source_table AND sm.column_name = vcm.source_column
    WHERE vcm.view_name = schema_metadata.table_name AND vcm.view_column = schema_metadata.column_name
);
