
import sqlite3
import json

DB_PATH = 'nt_fi_report.sqlite'

def add_keywords():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Add column if not exists
        try:
            cursor.execute("ALTER TABLE schema_contexts ADD COLUMN keywords TEXT")
            print("Added 'keywords' column.")
        except sqlite3.OperationalError:
            print("'keywords' column may already exist.")
            
        # 2. Update Revenue Keywords
        revenue_keywords = json.dumps(["รายได้", "revenue", "sales", "ยอดขาย", "income", "profit", "กำไร"])
        cursor.execute("UPDATE schema_contexts SET keywords = ? WHERE name = 'revenue'", (revenue_keywords,))
        
        # 3. Update Expense Keywords
        expense_keywords = json.dumps(["ค่าใช้จ่าย", "expense", "cost", "ต้นทุน", "งบประมาณ", "spending", "pay", "จ่าย"])
        cursor.execute("UPDATE schema_contexts SET keywords = ? WHERE name = 'expense'", (expense_keywords,))
        
        conn.commit()
        print("✅ Context keywords updated.")
        
        # Verify
        cursor.execute("SELECT name, keywords FROM schema_contexts")
        for row in cursor.fetchall():
            print(f"- {row[0]}: {row[1]}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_keywords()
