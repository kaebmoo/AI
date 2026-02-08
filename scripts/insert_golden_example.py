import sqlite3
import datetime

DB_PATH = "nt_fi_report.sqlite"

def insert_golden_example():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    question = "ขอรายได้รายกลุ่มบริการ แบบรายเดือน"
    sql = """SELECT 
  year, 
  CAST(month AS INTEGER) AS month, 
  SERVICE_GROUP, 
  SUM(revenue) AS revenue_baht
FROM revenue_search
WHERE BUSINESS_GROUP != 'รายได้อื่น'
GROUP BY year, CAST(month AS INTEGER), SERVICE_GROUP
ORDER BY year, CAST(month AS INTEGER), SERVICE_GROUP"""
    category = "Monthly Trends"
    
    # Check if exists
    cursor.execute("SELECT id FROM golden_examples WHERE question_pattern = ?", (question,))
    existing = cursor.fetchone()
    
    if existing:
        print(f"Example already exists with ID: {existing[0]}")
        # Update it just in case logic changed
        cursor.execute("""
            UPDATE golden_examples 
            SET expected_sql = ?, category = ?, is_active = 1 
            WHERE id = ?
        """, (sql, category, existing[0]))
        print("Updated existing example.")
    else:
        cursor.execute("""
            INSERT INTO golden_examples (question_pattern, expected_sql, category, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
        """, (question, sql, category, datetime.datetime.now()))
        print("Inserted new golden example.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    insert_golden_example()
