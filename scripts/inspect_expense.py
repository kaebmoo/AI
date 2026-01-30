
import sqlite3
import sys

# Use the new database name
DB_PATH = 'nt_fi_report.sqlite'

def inspect_expense_table():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print(f"--- Connecting to {DB_PATH} ---")

        # 1. Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='expense'")
        if not cursor.fetchone():
            print("❌ Table 'expense' not found within standard tables.")
            # Check for views or other names
            cursor.execute("SELECT name, type FROM sqlite_master WHERE name LIKE '%expense%'")
            matches = cursor.fetchall()
            if matches:
                 print(f"Found similar tables/views: {[dict(m) for m in matches]}")
            return

        print("✅ Table 'expense' found.")

        # 2. Get Schema Info
        cursor.execute("PRAGMA table_info(expense)")
        columns = [dict(row) for row in cursor.fetchall()]
        print("\n--- Schema Info ---")
        for col in columns:
            print(f"- {col['name']} ({col['type']})")

        # 3. Get Sample Data
        cursor.execute("SELECT * FROM expense LIMIT 3")
        rows = [dict(row) for row in cursor.fetchall()]
        print(f"\n--- Sample Data (3 rows) ---")
        if not rows:
            print("Table is empty.")
        else:
            for row in rows:
                print(row)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    inspect_expense_table()
