#!/usr/bin/env python3
"""
NT AI Assistant - Populate Schema Metadata
================================================
Script to populate initial schema metadata, semantic mappings, and business rules.

Usage:
    python scripts/populate_schema_metadata.py [--db-path PATH] [--reset]

Options:
    --db-path PATH    Path to SQLite database (default: nt_revenue.sqlite)
    --reset           Drop and recreate tables before populating
"""

import sqlite3
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection, reset: bool = False):
    """Create metadata tables"""
    cursor = conn.cursor()

    if reset:
        print("Dropping existing tables...")
        cursor.execute("DROP TABLE IF EXISTS schema_semantic_mapping")
        cursor.execute("DROP TABLE IF EXISTS schema_metadata")
        cursor.execute("DROP TABLE IF EXISTS schema_business_rules")
        cursor.execute("DROP VIEW IF EXISTS v_schema_for_ai")
        cursor.execute("DROP VIEW IF EXISTS v_business_rules_for_ai")
        cursor.execute("DROP VIEW IF EXISTS v_semantic_mappings_for_ai")

    # Create schema_metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            display_name_th TEXT,
            display_name_en TEXT,
            description TEXT,
            data_type TEXT,
            format_hint TEXT,
            example_value TEXT,
            is_summable BOOLEAN DEFAULT 0,
            is_groupable BOOLEAN DEFAULT 1,
            hierarchy_level INTEGER,
            sample_values TEXT,
            special_notes TEXT,
            conversion_sql TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(table_name, column_name)
        )
    """)

    # Create schema_semantic_mapping table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_semantic_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            keyword_type TEXT DEFAULT 'term',
            target_column TEXT NOT NULL,
            target_condition TEXT NOT NULL,
            full_condition TEXT,
            description TEXT,
            priority INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create schema_business_rules table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_business_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_code TEXT NOT NULL UNIQUE,
            rule_name TEXT NOT NULL,
            rule_description TEXT NOT NULL,
            table_name TEXT,
            applies_to TEXT,
            example_correct TEXT,
            example_wrong TEXT,
            severity TEXT DEFAULT 'warning',
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_schema_metadata_table ON schema_metadata(table_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_semantic_mapping_keyword ON schema_semantic_mapping(keyword)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_semantic_mapping_type ON schema_semantic_mapping(keyword_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_semantic_mapping_active ON schema_semantic_mapping(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_business_rules_active ON schema_business_rules(is_active)")

    conn.commit()
    print("Tables created successfully.")


def populate_schema_metadata(conn: sqlite3.Connection):
    """Populate schema metadata for revenue_search view"""
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DELETE FROM schema_metadata")

    metadata = [
        # Time Columns
        ('revenue_search', 'year', 'ปี', 'Year', 'ปี ค.ศ.', 'INTEGER', 'YYYY', '2025', 0, 1, None, None, 'ปี พ.ศ. = year + 543', None),
        ('revenue_search', 'month', 'เดือน', 'Month', 'เดือน (1-12)', 'INTEGER', 'M', '1', 0, 1, None, None, 'เป็น Integer', None),

        # Organization Columns
        ('revenue_search', 'division', 'สายงาน', 'Division', 'ชื่อสายงาน', 'TEXT', 'Text', 'สายงานบริหารองค์กร', 0, 1, 1, None, None, None),
        ('revenue_search', 'organization_group', 'กลุ่ม', 'Organization Group', 'ชื่อกลุ่มในองค์กร', 'TEXT', 'Text', 'กลุ่มเลขานุการและบริหารงานกลาง', 0, 1, 2, None, None, None),
        ('revenue_search', 'department', 'ฝ่าย', 'Department', 'ชื่อฝ่าย', 'TEXT', 'Text', 'ฝ่ายเลขานุการผู้บริหาร', 0, 1, 3, None, None, None),
        ('revenue_search', 'section', 'ส่วน', 'Section', 'ชื่อส่วน', 'TEXT', 'Text', 'ส่วนการประชุมผู้บริหาร', 0, 1, 4, None, None, None),
        ('revenue_search', 'cost_center', 'ศูนย์ต้นทุน', 'Cost Center', 'รหัสศูนย์ต้นทุน', 'TEXT', 'Code', '1C00104', 0, 1, 5, None, None, None),
        ('revenue_search', 'business_unit', 'หน่วยธุรกิจ', 'Business Unit', 'โครงสร้างหน่วยงาน/BU - ไม่ใช่กลุ่มผลิตภัณฑ์', 'TEXT', 'Text', 'กลุ่มขายและตลาด', 0, 1, None, None, 'นี่คือโครงสร้างองค์กร ไม่ใช่กลุ่มผลิตภัณฑ์', None),

        # Abbreviation Columns
        ('revenue_search', 'division_abbr', 'ย่อสายงาน', 'Division Abbr', 'ชื่อย่อสายงาน', 'TEXT', 'Abbr', 'บ.', 0, 1, None, None, 'ใช้สำหรับค้นหาด้วยชื่อย่อ', None),
        ('revenue_search', 'organization_group_abbr', 'ย่อกลุ่ม', 'Org Group Abbr', 'ชื่อย่อกลุ่ม', 'TEXT', 'Abbr', 'ขบ.', 0, 1, None, None, 'ใช้สำหรับค้นหาด้วยชื่อย่อ', None),
        ('revenue_search', 'department_abbr', 'ย่อฝ่าย', 'Dept Abbr', 'ชื่อย่อฝ่าย', 'TEXT', 'Abbr', 'บชง.', 0, 1, None, None, 'ใช้สำหรับค้นหาด้วยชื่อย่อ', None),
        ('revenue_search', 'section_abbr', 'ย่อส่วน', 'Section Abbr', 'ชื่อย่อส่วน', 'TEXT', 'Abbr', 'ปลขบ.', 0, 1, None, None, 'ใช้สำหรับค้นหาด้วยชื่อย่อ', None),

        # Product Columns
        ('revenue_search', 'PRODUCT_KEY', 'รหัสผลิตภัณฑ์', 'Product Key', 'รหัสผลิตภัณฑ์', 'TEXT', 'Code', '192020001', 0, 1, None, None, None, None),
        ('revenue_search', 'PRODUCT_NAME', 'ชื่อผลิตภัณฑ์', 'Product Name', 'ชื่อผลิตภัณฑ์', 'TEXT', 'Text', 'รายได้อื่น', 0, 1, None, None, None, None),
        ('revenue_search', 'SUB_PRODUCT_NAME', 'ชื่อผลิตภัณฑ์ย่อย', 'Sub Product Name', 'ชื่อผลิตภัณฑ์ย่อย', 'TEXT', 'Text', 'รายได้อื่น', 0, 1, None, None, None, None),
        ('revenue_search', 'PRODUCT', 'ผลิตภัณฑ์', 'Product', 'รหัส+ชื่อผลิตภัณฑ์', 'TEXT', 'Display', '192020001 รายได้อื่น', 0, 1, None, None, None, None),

        # Business Group Columns
        ('revenue_search', 'BUSINESS_GROUP', 'กลุ่มผลิตภัณฑ์', 'Business Group', 'กลุ่มผลิตภัณฑ์ เช่น Mobile, Fixed Line', 'TEXT', 'Text', 'Mobile', 0, 1, None, None, 'นี่คือกลุ่มผลิตภัณฑ์ ไม่ใช่หน่วยงาน', None),
        ('revenue_search', 'SERVICE_GROUP', 'กลุ่มบริการ', 'Service Group', 'กลุ่มบริการ', 'TEXT', 'Text', 'รายได้อื่น', 0, 1, None, None, None, None),

        # Accounting Columns
        ('revenue_search', 'GL_CODE', 'รหัสบัญชี', 'GL Code', 'รหัสบัญชี GL', 'TEXT', 'Code', '49901101', 0, 1, None, None, None, None),
        ('revenue_search', 'GL_NAME', 'ชื่อบัญชี', 'GL Name', 'ชื่อบัญชี GL', 'TEXT', 'Text', 'ดอกเบี้ยเงินให้กู้ยืม', 0, 1, None, None, None, None),
        ('revenue_search', 'account_category', 'หมวดบัญชี', 'Account Category', 'หมวดบัญชี', 'TEXT', 'Display', 'R10 ผลตอบแทนทางการเงิน', 0, 1, None, None, None, None),

        # Value Columns
        ('revenue_search', 'revenue', 'รายได้', 'Revenue', 'มูลค่ารายได้', 'REAL', 'Number', '162.24', 1, 0, None, None, 'หน่วยเป็นบาท - ใช้ SUM(revenue)', None),
    ]

    cursor.executemany("""
        INSERT INTO schema_metadata
        (table_name, column_name, display_name_th, display_name_en, description,
         data_type, format_hint, example_value, is_summable, is_groupable,
         hierarchy_level, sample_values, special_notes, conversion_sql)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, metadata)

    conn.commit()
    print(f"Inserted {len(metadata)} schema metadata records.")


def populate_semantic_mappings(conn: sqlite3.Connection):
    """Populate semantic mappings for abbreviations and business terms"""
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DELETE FROM schema_semantic_mapping")

    mappings = [
        # Organization Abbreviations (priority 10 - highest)
        ('นป.', 'abbreviation', 'organization_group_abbr', "= 'นป.'", None, 'กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ', 10),
        ('บชง.', 'abbreviation', 'department_abbr', "= 'บชง.'", None, 'ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ', 10),
        ('สญ.', 'abbreviation', 'division_abbr', "= 'สญ.'", None, 'สายงานขายและบริการ', 10),
        ('นต.', 'abbreviation', 'organization_group_abbr', "= 'นต.'", None, 'กลุ่มขายและปฏิบัติการลูกค้า ภาคตะวันออกเฉียงเหนือ', 10),
        ('กส.', 'abbreviation', 'organization_group_abbr', "= 'กส.'", None, 'กลุ่มขายและปฏิบัติการลูกค้า ภาคกลาง', 10),
        ('ปต.', 'abbreviation', 'organization_group_abbr', "= 'ปต.'", None, 'กลุ่มขายและปฏิบัติการลูกค้า กรุงเทพและปริมณฑล', 10),
        ('ทส.', 'abbreviation', 'organization_group_abbr', "= 'ทส.'", None, 'กลุ่มขายและปฏิบัติการลูกค้า ภาคใต้', 10),
        ('บก.', 'abbreviation', 'division_abbr', "= 'บก.'", None, 'สายงานบริหารกลาง', 10),

        # Real Estate / Property (priority 5)
        ('อสังหาริมทรัพย์', 'term', 'SERVICE_GROUP', "= 'กลุ่มบริการพัฒนาสินทรัพย์'", None, 'รายได้จากอสังหาริมทรัพย์', 5),
        ('real estate', 'term', 'SERVICE_GROUP', "= 'กลุ่มบริการพัฒนาสินทรัพย์'", None, 'Revenue from real estate', 5),
        ('ทรัพย์สิน', 'term', 'SERVICE_GROUP', "= 'กลุ่มบริการพัฒนาสินทรัพย์'", None, 'รายได้จากทรัพย์สิน', 5),
        ('property', 'term', 'SERVICE_GROUP', "= 'กลุ่มบริการพัฒนาสินทรัพย์'", None, 'Property revenue', 5),

        # Mobile / Wireless
        ('มือถือ', 'term', 'BUSINESS_GROUP', "= 'Mobile'", None, 'รายได้ Mobile', 5),
        ('โทรศัพท์มือถือ', 'term', 'BUSINESS_GROUP', "= 'Mobile'", None, 'รายได้โทรศัพท์มือถือ', 5),
        ('mobile', 'term', 'BUSINESS_GROUP', "= 'Mobile'", None, 'Mobile revenue', 5),
        ('wireless', 'term', 'BUSINESS_GROUP', "= 'Mobile'", None, 'Wireless revenue', 5),
        ('ไร้สาย', 'term', 'BUSINESS_GROUP', "= 'Mobile'", None, 'รายได้ไร้สาย', 5),

        # Fixed Line
        ('โทรศัพท์บ้าน', 'term', 'BUSINESS_GROUP', "= 'Fixed Line'", None, 'รายได้ Fixed Line', 5),
        ('fixed line', 'term', 'BUSINESS_GROUP', "= 'Fixed Line'", None, 'Fixed line revenue', 5),
        ('โทรศัพท์พื้นฐาน', 'term', 'BUSINESS_GROUP', "= 'Fixed Line'", None, 'รายได้โทรศัพท์พื้นฐาน', 5),
        ('สายตรง', 'term', 'BUSINESS_GROUP', "= 'Fixed Line'", None, 'รายได้สายตรง', 5),

        # Internet / Broadband
        ('อินเทอร์เน็ต', 'term', 'BUSINESS_GROUP', "LIKE '%Internet%'", None, 'รายได้อินเทอร์เน็ต', 5),
        ('internet', 'term', 'BUSINESS_GROUP', "LIKE '%Internet%'", None, 'Internet revenue', 5),
        ('บรอดแบนด์', 'term', 'BUSINESS_GROUP', "LIKE '%Broadband%'", None, 'Broadband revenue', 5),
        ('broadband', 'term', 'BUSINESS_GROUP', "LIKE '%Broadband%'", None, 'Broadband revenue', 5),

        # Data Center / Cloud
        ('ดาต้าเซ็นเตอร์', 'term', 'SERVICE_GROUP', "LIKE '%Data Center%'", None, 'รายได้ Data Center', 5),
        ('data center', 'term', 'SERVICE_GROUP', "LIKE '%Data Center%'", None, 'Data Center revenue', 5),
        ('คลาวด์', 'term', 'SERVICE_GROUP', "LIKE '%Cloud%'", None, 'รายได้ Cloud', 5),
        ('cloud', 'term', 'SERVICE_GROUP', "LIKE '%Cloud%'", None, 'Cloud revenue', 5),

        # ICT Services
        ('ไอซีที', 'term', 'BUSINESS_GROUP', "LIKE '%ICT%'", None, 'รายได้ ICT', 5),
        ('ict', 'term', 'BUSINESS_GROUP', "LIKE '%ICT%'", None, 'ICT revenue', 5),

        # Leased Line
        ('วงจรเช่า', 'term', 'SERVICE_GROUP', "LIKE '%Leased%'", None, 'รายได้วงจรเช่า', 5),
        ('leased line', 'term', 'SERVICE_GROUP', "LIKE '%Leased%'", None, 'Leased line revenue', 5),
    ]

    cursor.executemany("""
        INSERT INTO schema_semantic_mapping
        (keyword, keyword_type, target_column, target_condition, full_condition, description, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, mappings)

    conn.commit()
    print(f"Inserted {len(mappings)} semantic mapping records.")


def populate_business_rules(conn: sqlite3.Connection):
    """Populate business rules for SQL generation"""
    cursor = conn.cursor()

    # Clear existing data
    cursor.execute("DELETE FROM schema_business_rules")

    rules = [
        ('USE_YEAR_MONTH', 'ใช้ year, month สำหรับ filter เวลา',
         'แนะนำให้ใช้ year และ month โดยตรงแทนการแปลง DATE', 'revenue_search', 'year,month',
         'SELECT * FROM revenue_search WHERE year = 2025 AND month = 1',
         'SELECT * FROM revenue_search WHERE strftime(...) = ...', 'info'),

        ('THAI_YEAR', 'แปลงปี พ.ศ.',
         'เมื่อแสดงปีเป็นภาษาไทย ให้บวก 543', 'revenue_search', 'year',
         'SELECT year + 543 as year_th FROM revenue_search',
         'SELECT year as year_th FROM revenue_search -- ได้ปี ค.ศ.', 'info'),

        ('REVENUE_UNIT', 'หน่วยรายได้เป็นบาท',
         'revenue มีหน่วยเป็นบาท ไม่ใช่ล้านบาท', 'revenue_search', 'revenue',
         'SELECT SUM(revenue) as revenue_baht FROM revenue_search',
         'SELECT SUM(revenue) as revenue_million FROM revenue_search -- ผิดหน่วย', 'warning'),

        ('SQLITE_CONCAT', 'ใช้ || แทน CONCAT ใน SQLite',
         'SQLite ไม่รองรับ CONCAT() ให้ใช้ || แทน', None, None,
         "SELECT year || '-' || month as period FROM revenue_search",
         "SELECT CONCAT(year, '-', month) as period FROM revenue_search -- syntax error", 'error'),

        ('SQLITE_NO_LPAD', 'ใช้ printf แทน LPAD ใน SQLite',
         'SQLite ไม่รองรับ LPAD() ให้ใช้ printf แทน', None, None,
         "SELECT printf('%02d', month) FROM revenue_search",
         "SELECT LPAD(month, 2, '0') FROM revenue_search -- syntax error", 'error'),

        ('UNION_NO_PARENS', 'ห้ามใส่วงเล็บครอบ SELECT ใน UNION',
         'SQLite ไม่รองรับ (SELECT ...) UNION ...', None, None,
         'SELECT * FROM a UNION ALL SELECT * FROM b',
         '(SELECT * FROM a) UNION ALL (SELECT * FROM b) -- syntax error', 'error'),

        ('BU_VS_PRODUCT', 'แยกความแตกต่าง business_unit กับ BUSINESS_GROUP',
         'business_unit = หน่วยงาน/โครงสร้างองค์กร, BUSINESS_GROUP = กลุ่มผลิตภัณฑ์',
         'revenue_search', 'business_unit,BUSINESS_GROUP',
         'SELECT business_unit, SUM(revenue) FROM revenue_search GROUP BY business_unit -- หน่วยงาน',
         'SELECT BUSINESS_GROUP, SUM(revenue) FROM revenue_search GROUP BY BUSINESS_GROUP -- ถ้าต้องการแบ่งตามหน่วยงาน', 'warning'),

        ('CAST_FOR_COMPARE', 'Cast เป็น INTEGER ก่อน MAX/MIN/ORDER BY',
         'year และ month อาจเป็น TEXT ต้อง CAST ก่อนเปรียบเทียบ', 'revenue_search', 'year,month',
         'SELECT MAX(CAST(month AS INTEGER)) FROM revenue_search',
         'SELECT MAX(month) FROM revenue_search -- "9" > "10" ใน text sort', 'warning'),

        ('ABBR_COLUMNS', 'ใช้ column คำย่อสำหรับค้นหาคำย่อ',
         'เมื่อค้นหาด้วยคำย่อ เช่น นป., บชง. ให้ใช้ _abbr columns',
         'revenue_search', 'division_abbr,organization_group_abbr,department_abbr,section_abbr',
         "SELECT * FROM revenue_search WHERE department_abbr = 'บชง.'",
         "SELECT * FROM revenue_search WHERE department LIKE '%บชง%' -- ไม่แม่นยำ", 'info'),

        ('SINGLE_QUERY', 'สร้าง SQL เพียง query เดียว',
         'ห้ามสร้างหลาย query คั่นด้วย semicolon ถ้าต้องการหลายผลลัพธ์ ให้ใช้ UNION ALL',
         None, None,
         'SELECT ... UNION ALL SELECT ...',
         'SELECT ...; SELECT ... -- ไม่รองรับหลาย query', 'error'),

        ('UNION_SUBQUERY', 'ใช้ subquery เมื่อ UNION กับ ORDER BY/LIMIT',
         'ถ้าต้องการ Top N และ Bottom N ต้องใช้ subquery ครอบแต่ละส่วน เพราะ SQLite ไม่รองรับ ORDER BY/LIMIT ก่อน UNION',
         None, None,
         """SELECT 'Top 5' as category, * FROM (
    SELECT business_unit, SUM(revenue) as total FROM revenue_search GROUP BY business_unit ORDER BY total DESC LIMIT 5
)
UNION ALL
SELECT 'Bottom 5' as category, * FROM (
    SELECT business_unit, SUM(revenue) as total FROM revenue_search GROUP BY business_unit ORDER BY total ASC LIMIT 5
)""",
         """SELECT business_unit, SUM(revenue) as total FROM revenue_search GROUP BY business_unit ORDER BY total DESC LIMIT 5
UNION ALL
SELECT business_unit, SUM(revenue) as total FROM revenue_search GROUP BY business_unit ORDER BY total ASC LIMIT 5
-- ผิด! ORDER BY ต้องอยู่ใน subquery""", 'error'),

        ('USE_REVENUE_SEARCH', 'ใช้ revenue_search ไม่ใช่ revenue',
         'ต้อง query จาก view revenue_search เท่านั้น ไม่ใช่ table revenue',
         'revenue_search', None,
         'SELECT * FROM revenue_search WHERE ...',
         'SELECT * FROM revenue WHERE ... -- ผิด table', 'error'),
    ]

    cursor.executemany("""
        INSERT INTO schema_business_rules
        (rule_code, rule_name, rule_description, table_name, applies_to,
         example_correct, example_wrong, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rules)

    conn.commit()
    print(f"Inserted {len(rules)} business rule records.")


def create_views(conn: sqlite3.Connection):
    """Create views for AI prompt building"""
    cursor = conn.cursor()

    # Drop existing views
    cursor.execute("DROP VIEW IF EXISTS v_schema_for_ai")
    cursor.execute("DROP VIEW IF EXISTS v_business_rules_for_ai")
    cursor.execute("DROP VIEW IF EXISTS v_semantic_mappings_for_ai")

    # Create schema view
    cursor.execute("""
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
                WHEN column_name IN ('year', 'month', 'YEAR', 'MONTH') THEN 1
                WHEN column_name IN ('revenue', 'REVENUE_VALUE', 'AMOUNT') THEN 2
                ELSE 3
            END,
            column_name
    """)

    # Create business rules view
    cursor.execute("""
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
            END
    """)

    # Create semantic mappings view
    cursor.execute("""
        CREATE VIEW v_semantic_mappings_for_ai AS
        SELECT
            keyword,
            keyword_type,
            target_column,
            target_condition,
            description
        FROM schema_semantic_mapping
        WHERE is_active = 1
        ORDER BY priority DESC, keyword
    """)

    conn.commit()
    print("Views created successfully.")


def main():
    parser = argparse.ArgumentParser(description='Populate schema metadata tables')
    parser.add_argument('--db-path', type=str, default='nt_revenue.sqlite',
                        help='Path to SQLite database')
    parser.add_argument('--reset', action='store_true',
                        help='Drop and recreate tables before populating')

    args = parser.parse_args()

    # Check if database exists
    if not os.path.exists(args.db_path):
        print(f"Warning: Database {args.db_path} does not exist. Creating new database.")

    print(f"Connecting to database: {args.db_path}")
    conn = get_connection(args.db_path)

    try:
        print("\n=== Creating tables ===")
        create_tables(conn, reset=args.reset)

        print("\n=== Populating schema metadata ===")
        populate_schema_metadata(conn)

        print("\n=== Populating semantic mappings ===")
        populate_semantic_mappings(conn)

        print("\n=== Populating business rules ===")
        populate_business_rules(conn)

        print("\n=== Creating views ===")
        create_views(conn)

        print("\n=== Done! ===")

        # Show counts
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM schema_metadata")
        print(f"Total schema metadata records: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM schema_semantic_mapping")
        print(f"Total semantic mapping records: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM schema_business_rules")
        print(f"Total business rules records: {cursor.fetchone()[0]}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
