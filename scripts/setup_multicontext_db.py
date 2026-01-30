import sqlite3
import sys

DB_PATH = 'nt_fi_report.sqlite'

def setup_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print(f"--- Connecting to {DB_PATH} ---")

        # 1. Create schema_contexts table
        print("Creating table: schema_contexts...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,           -- 'revenue', 'expense', 'performance'
            display_name TEXT,                   -- 'รายได้', 'ค่าใช้จ่าย'
            description TEXT,
            main_view TEXT,                      -- 'revenue_search', 'v_expense_mart'
            is_active BOOLEAN DEFAULT 1,
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Create schema_context_tables table (for additional tables if needed)
        print("Creating table: schema_context_tables...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_context_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context_id INTEGER,
            table_name TEXT,
            role TEXT DEFAULT 'main',            -- 'main', 'dimension', 'reference'
            FOREIGN KEY (context_id) REFERENCES schema_contexts(id)
        );
        """)

        # 3. Create v_expense_mart View
        print("Creating view: v_expense_mart...")
        cursor.execute("DROP VIEW IF EXISTS v_expense_mart")
        cursor.execute("""
        CREATE VIEW v_expense_mart AS
        SELECT 
            YEAR as year,
            MONTH as month,
            "DATE" as date,
            COST_CENTER as cost_center,
            GL_CODE as gl_code,
            GL_NAME_NT1 as account_name,
            GROUP_NAME as account_group_name,
            CODE_GROUP as account_group_code,
            "กลุ่มธุรกิจ" as business_group,
            "NT" as nt,
            TYPE as type,
            EXPENSE_VALUE as expense,
            
            -- Organization Hierarchy
            DIVISION as division,
            DEPARTMENT as department,
            SECTION as section,
            "GROUP" as organization_group,
            
            -- Abbreviations
            DIVISION_ABBR as division_abbr,
            DEPARTMENT_ABBR as department_abbr,
            SECTION_ABBR as section_abbr,
            GROUP_ABBR as organization_group_abbr
            
        FROM expense;
        """)

        # 4. Register Contexts
        print("Registering contexts...")
        
        # Revenue Context
        cursor.execute("""
        INSERT OR IGNORE INTO schema_contexts (name, display_name, description, main_view, priority)
        VALUES ('revenue', 'รายได้', 'ข้อมูลรายได้แยกตามผลิตภัณฑ์และหน่วยงาน', 'revenue_search', 10)
        """)
        
        # Expense Context
        cursor.execute("""
        INSERT OR IGNORE INTO schema_contexts (name, display_name, description, main_view, priority)
        VALUES ('expense', 'ค่าใช้จ่าย', 'ข้อมูลค่าใช้จ่ายแยกตามหมวดบัญชีและหน่วยงาน', 'v_expense_mart', 9)
        """)

        conn.commit()
        print("✅ Database setup completed successfully.")

        # Verify
        cursor.execute("SELECT name, main_view FROM schema_contexts")
        contexts = cursor.fetchall()
        print("\nRegistered Contexts:")
        for ctx in contexts:
            print(f"- {ctx[0]}: {ctx[1]}")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    setup_db()
