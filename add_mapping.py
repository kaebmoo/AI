
import sqlite3

def insert_mapping():
    conn = sqlite3.connect('nt_fi_report.sqlite')
    cursor = conn.cursor()
    
    # Check if already exists
    cursor.execute("SELECT id FROM schema_semantic_mapping WHERE keyword = 'Fixed Line'")
    existing = cursor.fetchone()
    
    if existing:
        print("Mapping for 'Fixed Line' already exists.")
        # Update it to be sure
        cursor.execute("""
            UPDATE schema_semantic_mapping 
            SET target_column = 'SERVICE_GROUP',
                target_condition = "= 'บริการโทรศัพท์ประจำที่ (Fixed Line)'"
            WHERE keyword = 'Fixed Line'
        """)
        print("Updated existing mapping.")
    else:
        cursor.execute("""
            INSERT INTO schema_semantic_mapping (keyword, keyword_type, target_column, target_condition, description, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('Fixed Line', 'term', 'SERVICE_GROUP', "= 'บริการโทรศัพท์ประจำที่ (Fixed Line)'", "Mapping from User Feedback", 1))
        print("Inserted new mapping.")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    insert_mapping()
