
import sqlite3

def insert_mobile_mapping():
    conn = sqlite3.connect('nt_fi_report.sqlite')
    cursor = conn.cursor()
    
    mappings = [
        ('mobile wholesale', 'SERVICE_GROUP', "= 'บริการโทรคมนาคมสื่อสารไร้สาย - กลุ่มค้าส่ง (Wholesale)'"),
        ('mobile retail', 'SERVICE_GROUP', "= 'บริการโทรคมนาคมสื่อสารไร้สาย - กลุ่มค้าปลีก (Retail)'")
    ]
    
    for kw, col, cond in mappings:
        # Check existing
        cursor.execute("SELECT id FROM schema_semantic_mapping WHERE keyword = ?", (kw,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE schema_semantic_mapping 
                SET target_column = ?, target_condition = ?
                WHERE keyword = ?
            """, (col, cond, kw))
            print(f"Updated mapping for '{kw}'")
        else:
            cursor.execute("""
                INSERT INTO schema_semantic_mapping (keyword, keyword_type, target_column, target_condition, description, is_active)
                VALUES (?, 'term', ?, ?, 'Mapped from Analysis', 1)
            """, (kw, col, cond))
            print(f"Inserted mapping for '{kw}'")
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    insert_mobile_mapping()
