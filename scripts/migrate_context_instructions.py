
import sqlite3
import json

DB_PATH = "nt_fi_report.sqlite"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Starting migration...")
    
    # 1. Add columns if not exist
    try:
        cursor.execute("ALTER TABLE schema_contexts ADD COLUMN instruction_th TEXT")
        print("✅ Added 'instruction_th' column")
    except sqlite3.OperationalError:
        print("ℹ️ 'instruction_th' already exists")
        
    try:
        cursor.execute("ALTER TABLE schema_contexts ADD COLUMN instruction_en TEXT")
        print("✅ Added 'instruction_en' column")
    except sqlite3.OperationalError:
        print("ℹ️ 'instruction_en' already exists")
        
    # 2. Hardcoded Rules to Migrate
    revenue_th = """
   - **คำเตือน (Revenue Context):**
     - อย่ารวม 'รายได้อื่น' (Other Revenue) ในการคำนวณรายได้ทั้งหมด ยกเว้น user สั่ง
     - หน่วยรายได้เป็น **บาท**
    """.strip()
    
    expense_th = """
   - **คำเตือน (Expense Context):**
     - ค่าใช้จ่ายแยกตามหมวดบัญชี (Account Group)
     - `gl_code` คือรหัสบัญชี, `account_name` คือชื่อบัญชี
     - `amount` คือยอดค่าใช้จ่าย (เป็นตัวเลขติดลบ หรือบวกแล้วแต่การบันทึก ให้ระวังเรื่อง SUM)
     - ปกติถ้าเป็น Expense table ค่าอาจจะเป็น + หรือ - ให้เช็ค Data range ใน Schema
    """.strip()
    
    # 3. Update Data
    print("\nMigrating data...")
    
    # Revenue
    cursor.execute("UPDATE schema_contexts SET instruction_th = ? WHERE name = 'revenue'", (revenue_th,))
    if cursor.rowcount > 0:
        print("✅ Updated Revenue instructions (TH)")
    else:
        print("⚠️ Revenue context not found")
        
    # Expense
    cursor.execute("UPDATE schema_contexts SET instruction_th = ? WHERE name = 'expense'", (expense_th,))
    if cursor.rowcount > 0:
        print("✅ Updated Expense instructions (TH)")
    else:
        print("⚠️ Expense context not found")
        
    conn.commit()
    conn.close()
    print("\nMigration complete! 🎉")

if __name__ == "__main__":
    migrate()
