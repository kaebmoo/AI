import sqlite3
import os

DB_PATH = "nt_fi_report.sqlite"

def setup_database():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create schema_business_rules table
    print("Creating schema_business_rules table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schema_business_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT, -- specific table or 'ALL'
        rule_name TEXT NOT NULL,
        rule_description TEXT NOT NULL,
        sql_condition TEXT,
        is_active BOOLEAN DEFAULT 1,
        severity TEXT DEFAULT 'info',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Update revenue_search View
    # User requested: product_group -> BUSINESS_GROUP, service_group -> SERVICE_GROUP
    print("Updating revenue_search view...")
    cursor.execute("DROP VIEW IF EXISTS revenue_search")
    cursor.execute("""
    CREATE VIEW revenue_search AS 
    SELECT 
        YEAR as year, 
        MONTH as month, 
        "กลุ่มธุรกิจ" as business_unit, 
        "หมวดบัญชี" as account_category, 
        REVENUE_VALUE as revenue, 
        BUSINESS_GROUP as BUSINESS_GROUP, 
        SERVICE_GROUP as SERVICE_GROUP, 
        "DIVISION" as division, 
        "DEPARTMENT" as department, 
        "GROUP" as organization_group 
    FROM revenue
    """)
    
    # 3. Insert specific rule
    print("Inserting business rules...")
    
    # Check if rule exists first
    rule_name = "Exclude Irrelevant Other Revenue"
    cursor.execute("SELECT id FROM schema_business_rules WHERE rule_name = ?", (rule_name,))
    if not cursor.fetchone():
        rule_desc = "When querying revenue, ALWAYS exclude data where `BUSINESS_GROUP` is 'รายได้อื่น' AND `SERVICE_GROUP` is 'รายได้อื่น'. However, INCLUDE it if `SERVICE_GROUP` is 'ผลตอบแทนทางการเงิน'."
        
        cursor.execute("""
        INSERT INTO schema_business_rules (table_name, rule_name, rule_description, severity)
        VALUES (?, ?, ?, ?)
        """, ('revenue_search', rule_name, rule_desc, 'warning'))
        print(f"Added rule: {rule_name}")
    else:
        print(f"Rule already exists: {rule_name}")
        
    conn.commit()
    conn.close()
    print("Database setup complete.")

if __name__ == "__main__":
    setup_database()
