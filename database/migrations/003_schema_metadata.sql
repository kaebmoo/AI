-- ============================================================
-- NT AI Assistant - Schema Metadata Enhancement
-- Purpose: Enhanced metadata tables with semantic mapping support
-- Version: 2.0
-- Date: 2025-01-28
-- ============================================================
-- ============================================================
-- Drop existing tables if migrating
-- ============================================================
DROP TABLE IF EXISTS schema_semantic_mapping;
DROP TABLE IF EXISTS schema_metadata;
DROP TABLE IF EXISTS schema_business_rules;
DROP TABLE IF EXISTS schema_sample_values;
DROP VIEW IF EXISTS v_schema_for_ai;
DROP VIEW IF EXISTS v_business_rules_for_ai;
-- ============================================================
-- Table: schema_metadata
-- Stores column information for AI context
-- ============================================================
CREATE TABLE schema_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    display_name_th TEXT,
    -- ชื่อภาษาไทย
    display_name_en TEXT,
    -- English name
    description TEXT,
    -- คำอธิบาย
    data_type TEXT,
    -- INTEGER, TEXT, REAL
    format_hint TEXT,
    -- Format hint (e.g., 'YYYY-MM-DD', 'Code')
    example_value TEXT,
    -- ตัวอย่างค่า
    is_summable BOOLEAN DEFAULT 0,
    -- SUM() ได้หรือไม่
    is_groupable BOOLEAN DEFAULT 1,
    -- GROUP BY ได้หรือไม่
    hierarchy_level INTEGER,
    -- Level in org hierarchy (1=DIVISION, 2=GROUP, etc.)
    sample_values TEXT,
    -- ตัวอย่างค่า (JSON array)
    special_notes TEXT,
    -- หมายเหตุพิเศษ
    conversion_sql TEXT,
    -- SQL สำหรับแปลงค่า
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_name, column_name)
);
-- ============================================================
-- Table: schema_semantic_mapping
-- Maps abbreviations and business terms to SQL conditions
-- ============================================================
CREATE TABLE schema_semantic_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    -- คำค้น เช่น "อสังหาริมทรัพย์", "นป."
    keyword_type TEXT DEFAULT 'term',
    -- 'abbreviation', 'term', 'synonym'
    target_column TEXT NOT NULL,
    -- column ที่ต้องใช้
    target_condition TEXT NOT NULL,
    -- เงื่อนไข SQL เช่น "= 'กลุ่มบริการพัฒนาสินทรัพย์'"
    full_condition TEXT,
    -- Full SQL condition (optional, for complex cases)
    description TEXT,
    -- คำอธิบาย
    priority INTEGER DEFAULT 0,
    -- ลำดับความสำคัญ (higher = more priority)
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(keyword)
);
-- ============================================================
-- Table: schema_business_rules
-- SQL generation rules for AI
-- ============================================================
CREATE TABLE schema_business_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL UNIQUE,
    rule_name TEXT NOT NULL,
    rule_description TEXT NOT NULL,
    table_name TEXT,
    -- Applies to specific table, NULL = ALL
    applies_to TEXT,
    -- Comma-separated column names
    example_correct TEXT,
    example_wrong TEXT,
    severity TEXT DEFAULT 'warning',
    -- 'error', 'warning', 'info'
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
-- ============================================================
-- Create indices for performance
-- ============================================================
CREATE INDEX idx_schema_metadata_table ON schema_metadata(table_name);
CREATE INDEX idx_semantic_mapping_keyword ON schema_semantic_mapping(keyword);
CREATE INDEX idx_semantic_mapping_type ON schema_semantic_mapping(keyword_type);
CREATE INDEX idx_semantic_mapping_active ON schema_semantic_mapping(is_active);
CREATE INDEX idx_business_rules_active ON schema_business_rules(is_active);
-- ============================================================
-- Insert Metadata for: revenue_search (view)
-- ============================================================
-- Time Columns
INSERT INTO schema_metadata (
        table_name,
        column_name,
        data_type,
        display_name_th,
        display_name_en,
        description,
        format_hint,
        example_value,
        is_summable,
        is_groupable,
        special_notes,
        conversion_sql
    )
VALUES (
        'revenue_search',
        'year',
        'INTEGER',
        'ปี',
        'Year',
        'ปี ค.ศ.',
        'YYYY',
        '2025',
        0,
        1,
        'ปี พ.ศ. = year + 543',
        NULL
    ),
    (
        'revenue_search',
        'month',
        'INTEGER',
        'เดือน',
        'Month',
        'เดือน (1-12)',
        'M',
        '1',
        0,
        1,
        'เป็น Integer',
        NULL
    );
-- Organization Columns
INSERT INTO schema_metadata (
        table_name,
        column_name,
        data_type,
        display_name_th,
        display_name_en,
        description,
        format_hint,
        example_value,
        is_summable,
        is_groupable,
        hierarchy_level
    )
VALUES (
        'revenue_search',
        'division',
        'TEXT',
        'สายงาน',
        'Division',
        'ชื่อสายงาน',
        'Text',
        'สายงานบริหารองค์กร',
        0,
        1,
        1
    ),
    (
        'revenue_search',
        'organization_group',
        'TEXT',
        'กลุ่ม',
        'Organization Group',
        'ชื่อกลุ่มในองค์กร',
        'Text',
        'กลุ่มเลขานุการและบริหารงานกลาง',
        0,
        1,
        2
    ),
    (
        'revenue_search',
        'department',
        'TEXT',
        'ฝ่าย',
        'Department',
        'ชื่อฝ่าย',
        'Text',
        'ฝ่ายเลขานุการผู้บริหาร',
        0,
        1,
        3
    ),
    (
        'revenue_search',
        'section',
        'TEXT',
        'ส่วน',
        'Section',
        'ชื่อส่วน',
        'Text',
        'ส่วนการประชุมผู้บริหาร',
        0,
        1,
        4
    ),
    (
        'revenue_search',
        'cost_center',
        'TEXT',
        'ศูนย์ต้นทุน',
        'Cost Center',
        'รหัสศูนย์ต้นทุน',
        'Code',
        '1C00104',
        0,
        1,
        5
    ),
    (
        'revenue_search',
        'business_unit',
        'TEXT',
        'หน่วยธุรกิจ',
        'Business Unit',
        'โครงสร้างหน่วยงาน/BU - ไม่ใช่กลุ่มผลิตภัณฑ์',
        'Text',
        'กลุ่มขายและตลาด',
        0,
        1,
        NULL
    );
-- Abbreviation Columns
INSERT INTO schema_metadata (
        table_name,
        column_name,
        data_type,
        display_name_th,
        display_name_en,
        description,
        format_hint,
        example_value,
        is_summable,
        is_groupable,
        special_notes
    )
VALUES (
        'revenue_search',
        'division_abbr',
        'TEXT',
        'ย่อสายงาน',
        'Division Abbr',
        'ชื่อย่อสายงาน',
        'Abbr',
        'บ.',
        0,
        1,
        'ใช้สำหรับค้นหาด้วยชื่อย่อ'
    ),
    (
        'revenue_search',
        'organization_group_abbr',
        'TEXT',
        'ย่อกลุ่ม',
        'Org Group Abbr',
        'ชื่อย่อกลุ่ม',
        'Abbr',
        'ขบ.',
        0,
        1,
        'ใช้สำหรับค้นหาด้วยชื่อย่อ'
    ),
    (
        'revenue_search',
        'department_abbr',
        'TEXT',
        'ย่อฝ่าย',
        'Dept Abbr',
        'ชื่อย่อฝ่าย',
        'Abbr',
        'ลขบ.',
        0,
        1,
        'ใช้สำหรับค้นหาด้วยชื่อย่อ'
    ),
    (
        'revenue_search',
        'section_abbr',
        'TEXT',
        'ย่อส่วน',
        'Section Abbr',
        'ชื่อย่อส่วน',
        'Abbr',
        'ปลขบ.',
        0,
        1,
        'ใช้สำหรับค้นหาด้วยชื่อย่อ'
    );
-- Product Columns
INSERT INTO schema_metadata (
        table_name,
        column_name,
        data_type,
        display_name_th,
        display_name_en,
        description,
        format_hint,
        example_value,
        is_summable,
        is_groupable
    )
VALUES (
        'revenue_search',
        'PRODUCT_KEY',
        'TEXT',
        'รหัสผลิตภัณฑ์',
        'Product Key',
        'รหัสผลิตภัณฑ์',
        'Code',
        '192020001',
        0,
        1
    ),
    (
        'revenue_search',
        'PRODUCT_NAME',
        'TEXT',
        'ชื่อผลิตภัณฑ์',
        'Product Name',
        'ชื่อผลิตภัณฑ์',
        'Text',
        'รายได้อื่น',
        0,
        1
    ),
    (
        'revenue_search',
        'SUB_PRODUCT_NAME',
        'TEXT',
        'ชื่อผลิตภัณฑ์ย่อย',
        'Sub Product Name',
        'ชื่อผลิตภัณฑ์ย่อย',
        'Text',
        'รายได้อื่น',
        0,
        1
    ),
    (
        'revenue_search',
        'PRODUCT',
        'TEXT',
        'ผลิตภัณฑ์',
        'Product',
        'รหัส+ชื่อผลิตภัณฑ์',
        'Display',
        '192020001 รายได้อื่น',
        0,
        1
    );
-- Business Group Columns (Product categorization - NOT organization!)
INSERT INTO schema_metadata (
        table_name,
        column_name,
        data_type,
        display_name_th,
        display_name_en,
        description,
        format_hint,
        example_value,
        is_summable,
        is_groupable,
        special_notes
    )
VALUES (
        'revenue_search',
        'BUSINESS_GROUP',
        'TEXT',
        'กลุ่มผลิตภัณฑ์',
        'Business Group',
        'กลุ่มผลิตภัณฑ์ เช่น Mobile, Fixed Line',
        'Text',
        'Mobile',
        0,
        1,
        'นี่คือกลุ่มผลิตภัณฑ์ ไม่ใช่หน่วยงาน'
    ),
    (
        'revenue_search',
        'SERVICE_GROUP',
        'TEXT',
        'กลุ่มบริการ',
        'Service Group',
        'กลุ่มบริการ',
        'Text',
        'รายได้อื่น',
        0,
        1,
        NULL
    );
-- Accounting Columns
INSERT INTO schema_metadata (
        table_name,
        column_name,
        data_type,
        display_name_th,
        display_name_en,
        description,
        format_hint,
        example_value,
        is_summable,
        is_groupable
    )
VALUES (
        'revenue_search',
        'GL_CODE',
        'TEXT',
        'รหัสบัญชี',
        'GL Code',
        'รหัสบัญชี GL',
        'Code',
        '49901101',
        0,
        1
    ),
    (
        'revenue_search',
        'GL_NAME',
        'TEXT',
        'ชื่อบัญชี',
        'GL Name',
        'ชื่อบัญชี GL',
        'Text',
        'ดอกเบี้ยเงินให้กู้ยืม',
        0,
        1
    ),
    (
        'revenue_search',
        'account_category',
        'TEXT',
        'หมวดบัญชี',
        'Account Category',
        'หมวดบัญชี',
        'Display',
        'R10 ผลตอบแทนทางการเงิน',
        0,
        1
    );
-- Value Columns
INSERT INTO schema_metadata (
        table_name,
        column_name,
        data_type,
        display_name_th,
        display_name_en,
        description,
        format_hint,
        example_value,
        is_summable,
        is_groupable,
        special_notes
    )
VALUES (
        'revenue_search',
        'revenue',
        'REAL',
        'รายได้',
        'Revenue',
        'มูลค่ารายได้',
        'Number',
        '162.24',
        1,
        0,
        'หน่วยเป็นบาท - ใช้ SUM(revenue)'
    );
-- ============================================================
-- Insert Semantic Mappings - Abbreviations
-- ============================================================
-- Organization Abbreviations
INSERT INTO schema_semantic_mapping (
        keyword,
        keyword_type,
        target_column,
        target_condition,
        description,
        priority
    )
VALUES (
        'นป.',
        'abbreviation',
        'organization_group_abbr',
        "= 'นป.'",
        'กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ',
        10
    ),
    (
        'บชง.',
        'abbreviation',
        'department_abbr',
        "= 'บชง.'",
        'ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ',
        10
    ),
    (
        'สญ.',
        'abbreviation',
        'division_abbr',
        "= 'สญ.'",
        'สายงานขายและบริการ',
        10
    ),
    (
        'นต.',
        'abbreviation',
        'organization_group_abbr',
        "= 'นต.'",
        'กลุ่มขายและปฏิบัติการลูกค้า ภาคตะวันออกเฉียงเหนือ',
        10
    ),
    (
        'กส.',
        'abbreviation',
        'organization_group_abbr',
        "= 'กส.'",
        'กลุ่มขายและปฏิบัติการลูกค้า ภาคกลาง',
        10
    ),
    (
        'ปต.',
        'abbreviation',
        'organization_group_abbr',
        "= 'ปต.'",
        'กลุ่มขายและปฏิบัติการลูกค้า กรุงเทพและปริมณฑล',
        10
    );
-- ============================================================
-- Insert Semantic Mappings - Business Terms
-- ============================================================
-- Real Estate / Property
INSERT INTO schema_semantic_mapping (
        keyword,
        keyword_type,
        target_column,
        target_condition,
        description,
        priority
    )
VALUES (
        'อสังหาริมทรัพย์',
        'term',
        'SERVICE_GROUP',
        "= 'กลุ่มบริการพัฒนาสินทรัพย์'",
        'รายได้จากอสังหาริมทรัพย์',
        5
    ),
    (
        'real estate',
        'term',
        'SERVICE_GROUP',
        "= 'กลุ่มบริการพัฒนาสินทรัพย์'",
        'Revenue from real estate',
        5
    ),
    (
        'ทรัพย์สิน',
        'term',
        'SERVICE_GROUP',
        "= 'กลุ่มบริการพัฒนาสินทรัพย์'",
        'รายได้จากทรัพย์สิน',
        5
    ),
    (
        'property',
        'term',
        'SERVICE_GROUP',
        "= 'กลุ่มบริการพัฒนาสินทรัพย์'",
        'Property revenue',
        5
    );
-- Mobile / Wireless
INSERT INTO schema_semantic_mapping (
        keyword,
        keyword_type,
        target_column,
        target_condition,
        description,
        priority
    )
VALUES (
        'มือถือ',
        'term',
        'BUSINESS_GROUP',
        "= 'Mobile'",
        'รายได้ Mobile',
        5
    ),
    (
        'โทรศัพท์มือถือ',
        'term',
        'BUSINESS_GROUP',
        "= 'Mobile'",
        'รายได้โทรศัพท์มือถือ',
        5
    ),
    (
        'mobile',
        'term',
        'BUSINESS_GROUP',
        "= 'Mobile'",
        'Mobile revenue',
        5
    ),
    (
        'wireless',
        'term',
        'BUSINESS_GROUP',
        "= 'Mobile'",
        'Wireless revenue',
        5
    );
-- Fixed Line
INSERT INTO schema_semantic_mapping (
        keyword,
        keyword_type,
        target_column,
        target_condition,
        description,
        priority
    )
VALUES (
        'โทรศัพท์บ้าน',
        'term',
        'BUSINESS_GROUP',
        "= 'Fixed Line'",
        'รายได้ Fixed Line',
        5
    ),
    (
        'fixed line',
        'term',
        'BUSINESS_GROUP',
        "= 'Fixed Line'",
        'Fixed line revenue',
        5
    ),
    (
        'โทรศัพท์พื้นฐาน',
        'term',
        'BUSINESS_GROUP',
        "= 'Fixed Line'",
        'รายได้โทรศัพท์พื้นฐาน',
        5
    );
-- Internet / Broadband
INSERT INTO schema_semantic_mapping (
        keyword,
        keyword_type,
        target_column,
        target_condition,
        description,
        priority
    )
VALUES (
        'อินเทอร์เน็ต',
        'term',
        'BUSINESS_GROUP',
        "LIKE '%Internet%' OR BUSINESS_GROUP LIKE '%Broadband%'",
        'รายได้อินเทอร์เน็ต',
        5
    ),
    (
        'internet',
        'term',
        'BUSINESS_GROUP',
        "LIKE '%Internet%' OR BUSINESS_GROUP LIKE '%Broadband%'",
        'Internet revenue',
        5
    ),
    (
        'บรอดแบนด์',
        'term',
        'BUSINESS_GROUP',
        "LIKE '%Internet%' OR BUSINESS_GROUP LIKE '%Broadband%'",
        'Broadband revenue',
        5
    );
-- ============================================================
-- Insert Business Rules
-- ============================================================
INSERT INTO schema_business_rules (
        rule_code,
        rule_name,
        rule_description,
        table_name,
        applies_to,
        example_correct,
        example_wrong,
        severity
    )
VALUES (
        'USE_YEAR_MONTH',
        'ใช้ year, month สำหรับ filter เวลา',
        'แนะนำให้ใช้ year และ month โดยตรงแทนการแปลง DATE',
        'revenue_search',
        'year,month',
        'SELECT * FROM revenue_search WHERE year = 2025 AND month = 1',
        'SELECT * FROM revenue_search WHERE strftime(...) = ...',
        'info'
    ),
    (
        'THAI_YEAR',
        'แปลงปี พ.ศ.',
        'เมื่อแสดงปีเป็นภาษาไทย ให้บวก 543',
        'revenue_search',
        'year',
        'SELECT year + 543 as year_th FROM revenue_search',
        'SELECT year as year_th FROM revenue_search -- ได้ปี ค.ศ.',
        'info'
    ),
    (
        'REVENUE_UNIT',
        'หน่วยรายได้เป็นบาท',
        'revenue มีหน่วยเป็นบาท ไม่ใช่ล้านบาท',
        'revenue_search',
        'revenue',
        'SELECT SUM(revenue) as revenue_baht FROM revenue_search',
        'SELECT SUM(revenue) as revenue_million FROM revenue_search -- ผิดหน่วย',
        'warning'
    ),
    (
        'SQLITE_CONCAT',
        'ใช้ || แทน CONCAT ใน SQLite',
        'SQLite ไม่รองรับ CONCAT() ให้ใช้ || แทน',
        NULL,
        NULL,
        'SELECT year || ''-'' || month as period FROM revenue_search',
        'SELECT CONCAT(year, ''-'', month) as period FROM revenue_search -- syntax error',
        'error'
    ),
    (
        'SQLITE_NO_LPAD',
        'ใช้ printf แทน LPAD ใน SQLite',
        'SQLite ไม่รองรับ LPAD() ให้ใช้ printf แทน',
        NULL,
        NULL,
        'SELECT printf(''%02d'', month) FROM revenue_search',
        'SELECT LPAD(month, 2, ''0'') FROM revenue_search -- syntax error',
        'error'
    ),
    (
        'UNION_NO_PARENS',
        'ห้ามใส่วงเล็บครอบ SELECT ใน UNION',
        'SQLite ไม่รองรับ (SELECT ...) UNION ...',
        NULL,
        NULL,
        'SELECT * FROM a UNION ALL SELECT * FROM b',
        '(SELECT * FROM a) UNION ALL (SELECT * FROM b) -- syntax error',
        'error'
    ),
    (
        'BU_VS_PRODUCT',
        'แยกความแตกต่าง business_unit กับ BUSINESS_GROUP',
        'business_unit = หน่วยงาน/โครงสร้างองค์กร, BUSINESS_GROUP = กลุ่มผลิตภัณฑ์',
        'revenue_search',
        'business_unit,BUSINESS_GROUP',
        'SELECT business_unit, SUM(revenue) FROM revenue_search GROUP BY business_unit -- หน่วยงาน',
        'SELECT BUSINESS_GROUP, SUM(revenue) FROM revenue_search GROUP BY BUSINESS_GROUP -- ถ้าต้องการแบ่งตามหน่วยงาน',
        'warning'
    ),
    (
        'CAST_FOR_COMPARE',
        'Cast เป็น INTEGER ก่อน MAX/MIN/ORDER BY',
        'year และ month อาจเป็น TEXT ต้อง CAST ก่อนเปรียบเทียบ',
        'revenue_search',
        'year,month',
        'SELECT MAX(CAST(month AS INTEGER)) FROM revenue_search',
        'SELECT MAX(month) FROM revenue_search -- "9" > "10" ใน text sort',
        'warning'
    ),
    (
        'ABBR_COLUMNS',
        'ใช้ column คำย่อสำหรับค้นหาคำย่อ',
        'เมื่อค้นหาด้วยคำย่อ เช่น นป., บชง. ให้ใช้ _abbr columns',
        'revenue_search',
        'division_abbr,organization_group_abbr,department_abbr,section_abbr',
        'SELECT * FROM revenue_search WHERE department_abbr = ''บชง.''',
        'SELECT * FROM revenue_search WHERE department LIKE ''%บชง%'' -- ไม่แม่นยำ',
        'info'
    );
-- ============================================================
-- Create View for AI
-- ============================================================
CREATE VIEW v_schema_for_ai AS
SELECT table_name,
    column_name,
    display_name_th,
    display_name_en,
    data_type,
    format_hint,
    example_value,
    CASE
        WHEN is_summable = 1 THEN 'Yes'
        ELSE 'No'
    END as can_sum,
    CASE
        WHEN is_groupable = 1 THEN 'Yes'
        ELSE 'No'
    END as can_group_by,
    hierarchy_level,
    special_notes,
    conversion_sql
FROM schema_metadata
ORDER BY table_name,
    CASE
        WHEN column_name IN ('year', 'month', 'YEAR', 'MONTH') THEN 1
        WHEN column_name IN ('revenue', 'REVENUE_VALUE', 'AMOUNT') THEN 2
        ELSE 3
    END,
    column_name;
-- ============================================================
-- View for Business Rules
-- ============================================================
CREATE VIEW v_business_rules_for_ai AS
SELECT rule_code,
    rule_name,
    rule_description,
    severity,
    example_correct as correct_sql,
    example_wrong as wrong_sql
FROM schema_business_rules
WHERE is_active = 1
ORDER BY CASE
        severity
        WHEN 'error' THEN 1
        WHEN 'warning' THEN 2
        ELSE 3
    END;
-- ============================================================
-- View for Semantic Mappings (for AI prompt)
-- ============================================================
CREATE VIEW v_semantic_mappings_for_ai AS
SELECT keyword,
    keyword_type,
    target_column,
    target_condition,
    description
FROM schema_semantic_mapping
WHERE is_active = 1
ORDER BY priority DESC,
    keyword;