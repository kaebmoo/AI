import sqlite3

def fix_abbreviations():
    conn = sqlite3.connect("nt_revenue.sqlite")
    cursor = conn.cursor()
    
    # 1. Delete the bad row we just added (id 2)
    cursor.execute("DELETE FROM schema_business_rules WHERE rule_name = 'Common Abbreviations'")
    
    # 2. Insert correctly
    rule_desc = """คำย่อหน่วยงาน:
- **นป.** = `กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ` (ใช้ column `organization_group`)
- **บชง.** = `ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ` (ใช้ column `department`)"""
    
    cursor.execute("""
        INSERT INTO schema_business_rules 
        (rule_name, rule_description, severity, is_active, table_name) 
        VALUES (?, ?, 'info', 1, 'ALL')
    """, ("Common Abbreviations", rule_desc))
    
    conn.commit()
    print("Inserted rules successfully.")
    
    # Verify
    cursor.execute("SELECT rule_description FROM schema_business_rules WHERE rule_name = 'Common Abbreviations'")
    print(f"Stored value: {cursor.fetchone()[0]}")
    conn.close()

if __name__ == "__main__":
    fix_abbreviations()
