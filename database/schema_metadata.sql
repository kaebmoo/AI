-- ============================================================
-- NT Revenue Assistant - Schema Metadata
-- Purpose: Store metadata for AI to understand data structure
-- Version: 1.0
-- Date: 2025-01-26
-- ============================================================

-- Drop existing tables
DROP TABLE IF EXISTS schema_metadata;
DROP TABLE IF EXISTS schema_business_rules;
DROP TABLE IF EXISTS schema_sample_values;
DROP VIEW IF EXISTS v_schema_for_ai;

-- ============================================================
-- Table: schema_metadata
-- ============================================================
CREATE TABLE schema_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    data_type TEXT,
    display_name_th TEXT,
    display_name_en TEXT,
    description TEXT,
    format_hint TEXT,
    example_value TEXT,
    is_summable INTEGER DEFAULT 1,
    is_groupable INTEGER DEFAULT 1,
    hierarchy_level INTEGER,
    special_notes TEXT,
    conversion_sql TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_name, column_name)
);

-- ============================================================
-- Table: schema_business_rules
-- ============================================================
CREATE TABLE schema_business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL UNIQUE,
    rule_name TEXT NOT NULL,
    rule_description TEXT NOT NULL,
    applies_to TEXT,
    example_correct TEXT,
    example_wrong TEXT,
    severity TEXT DEFAULT 'warning',
    is_active INTEGER DEFAULT 1
);

-- ============================================================
-- Table: schema_sample_values
-- ============================================================
CREATE TABLE schema_sample_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    sample_value TEXT NOT NULL,
    value_description TEXT,
    display_order INTEGER DEFAULT 0
);

-- ============================================================
-- Insert Metadata for: revenue
-- ============================================================

-- Time Columns
INSERT INTO schema_metadata (table_name, column_name, data_type, display_name_th, display_name_en, description, format_hint, example_value, is_summable, is_groupable, special_notes, conversion_sql) VALUES
('revenue', 'YEAR', 'INTEGER', 'ปี', 'Year', 'ปี ค.ศ.', 'YYYY', '2025', 0, 1, 'ปี พ.ศ. = YEAR + 543', NULL),
('revenue', 'MONTH', 'INTEGER', 'เดือน', 'Month', 'เดือน (1-12)', 'M', '1', 0, 1, NULL, NULL),
('revenue', 'DATE', 'INTEGER', 'วันที่', 'Date', 'Unix Timestamp (milliseconds)', 'Unix ms', '1735689600000', 0, 1, '⚠️ ต้องแปลงก่อนใช้', 'date(DATE / 1000, ''unixepoch'')');

-- Organization Columns
INSERT INTO schema_metadata (table_name, column_name, data_type, display_name_th, display_name_en, description, format_hint, example_value, is_summable, is_groupable, hierarchy_level) VALUES
('revenue', 'DIVISION', 'TEXT', 'สายงาน', 'Division', 'ชื่อสายงาน', 'Text', 'สายงานบริหารองค์กร', 0, 1, 1),
('revenue', 'GROUP', 'TEXT', 'กลุ่ม', 'Group', 'ชื่อกลุ่ม', 'Text', 'กลุ่มเลขานุการและบริหารงานกลาง', 0, 1, 2),
('revenue', 'DEPARTMENT', 'TEXT', 'ฝ่าย', 'Department', 'ชื่อฝ่าย', 'Text', 'ฝ่ายเลขานุการผู้บริหาร', 0, 1, 3),
('revenue', 'SECTION', 'TEXT', 'ส่วน', 'Section', 'ชื่อส่วน', 'Text', 'ส่วนการประชุมผู้บริหาร', 0, 1, 4),
('revenue', 'COST_CENTER', 'TEXT', 'ศูนย์ต้นทุน', 'Cost Center', 'รหัสศูนย์ต้นทุน', 'Code', '1C00104', 0, 1, 5),
('revenue', 'COST_CENTER_DEPARTMENT', 'TEXT', 'รหัสฝ่าย', 'Cost Center Dept', 'รหัสศูนย์ต้นทุนระดับฝ่าย', 'Code', '1C00100', 0, 1, NULL),
('revenue', 'DIVISION_ABBR', 'TEXT', 'ย่อสายงาน', 'Division Abbr', 'ชื่อย่อสายงาน', 'Abbr', 'บ.', 0, 1, NULL),
('revenue', 'GROUP_ABBR', 'TEXT', 'ย่อกลุ่ม', 'Group Abbr', 'ชื่อย่อกลุ่ม', 'Abbr', 'ขบ.', 0, 1, NULL),
('revenue', 'DEPARTMENT_ABBR', 'TEXT', 'ย่อฝ่าย', 'Dept Abbr', 'ชื่อย่อฝ่าย', 'Abbr', 'ลขบ.', 0, 1, NULL),
('revenue', 'SECTION_ABBR', 'TEXT', 'ย่อส่วน', 'Section Abbr', 'ชื่อย่อส่วน', 'Abbr', 'ปลขบ.', 0, 1, NULL),
('revenue', 'กลุ่มธุรกิจ', 'TEXT', 'กลุ่มธุรกิจหลัก', 'Business Group', 'กลุ่มธุรกิจหลัก', 'Text', 'กลุ่มสนับสนุน', 0, 1, 0);

-- Product Columns
INSERT INTO schema_metadata (table_name, column_name, data_type, display_name_th, display_name_en, description, format_hint, example_value, is_summable, is_groupable) VALUES
('revenue', 'PRODUCT_KEY', 'TEXT', 'รหัสผลิตภัณฑ์', 'Product Key', 'รหัสผลิตภัณฑ์', 'Code', '192020001', 0, 1),
('revenue', 'SUB_PRODUCT_KEY', 'TEXT', 'รหัสผลิตภัณฑ์ย่อย', 'Sub Product Key', 'รหัสผลิตภัณฑ์ย่อย', 'Code', '1', 0, 1),
('revenue', 'PRODUCT_NAME', 'TEXT', 'ชื่อผลิตภัณฑ์', 'Product Name', 'ชื่อผลิตภัณฑ์', 'Text', 'รายได้อื่น', 0, 1),
('revenue', 'SUB_PRODUCT_NAME', 'TEXT', 'ชื่อผลิตภัณฑ์ย่อย', 'Sub Product Name', 'ชื่อผลิตภัณฑ์ย่อย', 'Text', 'รายได้อื่น', 0, 1),
('revenue', 'PRODUCT', 'TEXT', 'ผลิตภัณฑ์', 'Product', 'รหัส+ชื่อผลิตภัณฑ์', 'Display', '192020001 รายได้อื่น', 0, 1),
('revenue', 'SUB_PRODUCT', 'TEXT', 'ผลิตภัณฑ์ย่อย', 'Sub Product', 'รหัส+ชื่อผลิตภัณฑ์ย่อย', 'Display', '1 รายได้อื่น', 0, 1);

-- Business Columns
INSERT INTO schema_metadata (table_name, column_name, data_type, display_name_th, display_name_en, description, format_hint, example_value, is_summable, is_groupable) VALUES
('revenue', 'ITEM', 'TEXT', 'หมวดธุรกิจ', 'Item', 'รหัสหมวดธุรกิจ', 'Code', '8', 0, 1),
('revenue', 'SUB_ITEM', 'TEXT', 'หมวดธุรกิจย่อย', 'Sub Item', 'รหัสหมวดธุรกิจย่อย', 'Code', '8.2', 0, 1),
('revenue', 'BUSINESS_GROUP', 'TEXT', 'กลุ่มธุรกิจ', 'Business Group', 'ชื่อกลุ่มธุรกิจ', 'Text', 'รายได้อื่น', 0, 1),
('revenue', 'BUSINESS', 'TEXT', 'ธุรกิจ', 'Business', 'รหัส+ชื่อธุรกิจ', 'Display', '8 รายได้อื่น', 0, 1),
('revenue', 'SERVICE', 'TEXT', 'บริการ', 'Service', 'รหัส+ชื่อบริการ', 'Display', '8.2 รายได้อื่น', 0, 1),
('revenue', 'SERVICE_GROUP', 'TEXT', 'กลุ่มบริการ', 'Service Group', 'กลุ่มบริการ', 'Text', 'รายได้อื่น', 0, 1),
('revenue', 'REVENUE_GROUP_TYPE', 'TEXT', 'ประเภทกลุ่มรายได้', 'Revenue Group Type', 'ประเภทกลุ่มรายได้', 'Text', 'รายได้อื่น', 0, 1);

-- Accounting Columns
INSERT INTO schema_metadata (table_name, column_name, data_type, display_name_th, display_name_en, description, format_hint, example_value, is_summable, is_groupable) VALUES
('revenue', 'REPORT_CODE', 'TEXT', 'รหัสรายงาน', 'Report Code', 'รหัสรายงาน', 'Code', 'R10', 0, 1),
('revenue', 'GL_CODE', 'TEXT', 'รหัสบัญชี', 'GL Code', 'รหัสบัญชี GL', 'Code', '49901101', 0, 1),
('revenue', 'GL_NAME', 'TEXT', 'ชื่อบัญชี', 'GL Name', 'ชื่อบัญชี GL', 'Text', 'ดอกเบี้ยเงินให้กู้ยืม-กองทุนสวัสดิการ', 0, 1),
('revenue', 'GL_GROUP', 'TEXT', 'กลุ่มบัญชี', 'GL Group', 'กลุ่มบัญชี GL', 'Text', 'ผลตอบแทนทางการเงินและรายได้อื่น', 0, 1),
('revenue', 'หมวดบัญชี', 'TEXT', 'หมวดบัญชี', 'Account Category', 'รหัส+ชื่อหมวดบัญชี', 'Display', 'R10 ผลตอบแทนทางการเงินและรายได้อื่น', 0, 1),
('revenue', 'NT', 'TEXT', 'บริษัท', 'Company', 'ชื่อบริษัท', 'Text', 'NT', 0, 1),
('revenue', 'TYPE', 'TEXT', 'ประเภท', 'Type', 'ประเภทรายการ', 'Text', 'รายได้', 0, 1);

-- Value Columns
INSERT INTO schema_metadata (table_name, column_name, data_type, display_name_th, display_name_en, description, format_hint, example_value, is_summable, is_groupable, special_notes) VALUES
('revenue', 'REVENUE_VALUE', 'REAL', 'มูลค่ารายได้', 'Revenue Value', 'มูลค่ารายได้', 'Number', '162.24', 1, 0, 'หน่วยเป็นบาท'),
('revenue', 'AMOUNT', 'REAL', 'จำนวนเงิน', 'Amount', 'จำนวนเงิน', 'Number', '162.24', 1, 0, 'หน่วยเป็นบาท ปกติเท่ากับ REVENUE_VALUE');

-- ============================================================
-- Insert Business Rules
-- ============================================================

INSERT INTO schema_business_rules (rule_code, rule_name, rule_description, applies_to, example_correct, example_wrong, severity) VALUES
('DATE_CONVERT', 'แปลง DATE ก่อนใช้', 'DATE เก็บเป็น Unix Timestamp (ms) ต้องแปลงก่อนแสดงผล', 'DATE', 
'SELECT date(DATE / 1000, ''unixepoch'') FROM revenue',
'SELECT DATE FROM revenue -- จะได้ตัวเลข',
'warning'),

('THAI_YEAR', 'แปลงปี พ.ศ.', 'เมื่อแสดงปีเป็นภาษาไทย ให้บวก 543', 'YEAR',
'SELECT YEAR + 543 as year_th FROM revenue',
'SELECT YEAR as year_th FROM revenue -- ได้ปี ค.ศ.',
'info'),

('REVENUE_UNIT', 'หน่วยรายได้เป็นบาท', 'REVENUE_VALUE และ AMOUNT มีหน่วยเป็นบาท ไม่ใช่ล้านบาท', 'REVENUE_VALUE,AMOUNT',
'SELECT SUM(REVENUE_VALUE) as revenue_baht FROM revenue',
'SELECT SUM(REVENUE_VALUE) as revenue_million FROM revenue -- ผิดหน่วย',
'warning'),

('THAI_COLUMN', 'Column ภาษาไทยต้อง quote', 'Column ที่มีชื่อภาษาไทยต้องใช้ double quotes', 'กลุ่มธุรกิจ,หมวดบัญชี',
'SELECT "กลุ่มธุรกิจ" FROM revenue',
'SELECT กลุ่มธุรกิจ FROM revenue -- syntax error',
'error'),

('USE_YEAR_MONTH', 'ใช้ YEAR, MONTH แทน DATE', 'แนะนำให้ใช้ YEAR และ MONTH โดยตรงแทนการแปลง DATE', 'DATE,YEAR,MONTH',
'SELECT * FROM revenue WHERE YEAR = 2025 AND MONTH = 1',
'SELECT * FROM revenue WHERE date(DATE/1000,''unixepoch'') = ''2025-01-01'' -- ซับซ้อนเกินไป',
'info'),

('ORG_HIERARCHY', 'โครงสร้างหน่วยงาน', 'DIVISION > GROUP > DEPARTMENT > SECTION > COST_CENTER', 'DIVISION,GROUP,DEPARTMENT,SECTION,COST_CENTER',
'SELECT DIVISION, "GROUP", DEPARTMENT, SUM(REVENUE_VALUE) FROM revenue GROUP BY DIVISION, "GROUP", DEPARTMENT',
NULL,
'info');

-- ============================================================
-- Insert Sample Values
-- ============================================================

INSERT INTO schema_sample_values (table_name, column_name, sample_value, value_description, display_order) VALUES
('revenue', 'กลุ่มธุรกิจ', 'กลุ่มสนับสนุน', 'Support Group', 1),
('revenue', 'REPORT_CODE', 'R10', 'ผลตอบแทนทางการเงินและรายได้อื่น', 1),
('revenue', 'TYPE', 'รายได้', 'Revenue', 1),
('revenue', 'NT', 'NT', 'National Telecom', 1);

-- ============================================================
-- Create View for AI
-- ============================================================

CREATE VIEW v_schema_for_ai AS
SELECT 
    table_name,
    column_name,
    display_name_th,
    display_name_en,
    data_type,
    format_hint,
    example_value,
    CASE WHEN is_summable = 1 THEN 'Yes' ELSE 'No' END as can_sum,
    CASE WHEN is_groupable = 1 THEN 'Yes' ELSE 'No' END as can_group_by,
    hierarchy_level,
    special_notes,
    conversion_sql
FROM schema_metadata
ORDER BY table_name, 
    CASE 
        WHEN column_name IN ('YEAR', 'MONTH', 'DATE') THEN 1
        WHEN column_name IN ('REVENUE_VALUE', 'AMOUNT') THEN 2
        ELSE 3
    END,
    column_name;

-- ============================================================
-- View for Business Rules
-- ============================================================

CREATE VIEW v_business_rules_for_ai AS
SELECT 
    rule_code,
    rule_name,
    rule_description,
    severity,
    example_correct as correct_sql,
    example_wrong as wrong_sql
FROM schema_business_rules
WHERE is_active = 1
ORDER BY 
    CASE severity 
        WHEN 'error' THEN 1 
        WHEN 'warning' THEN 2 
        ELSE 3 
    END;
