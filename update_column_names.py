
import sqlite3

def update_metadata():
    conn = sqlite3.connect('nt_fi_report.sqlite')
    cursor = conn.cursor()
    
    # Check if BUSINESS_GROUP metadata exists
    cursor.execute("SELECT id, display_name_th FROM schema_metadata WHERE column_name = 'BUSINESS_GROUP'")
    row = cursor.fetchone()
    
    updates = [
        ('BUSINESS_GROUP', 'กลุ่มธุรกิจ', 'Business Group'),
        ('SERVICE_GROUP', 'กลุ่มบริการ', 'Service Group'),
        ('PRODUCT_NAME', 'บริการ', 'Product / Service Name')
    ]
    
    for col, th_name, en_name in updates:
        # Try update
        cursor.execute("""
            UPDATE schema_metadata 
            SET display_name_th = ?, display_name_en = ?
            WHERE table_name = 'revenue_search' AND column_name = ?
        """, (th_name, en_name, col))
        
        if cursor.rowcount == 0:
            # Need insert? Or check if record exists at all?
            # Normally schema_metadata is populated, but if missing we might need to insert.
            # Assuming populated, but let's check.
            print(f"Warning: No metadata found for {col}, skipping update.")
        else:
            print(f"Updated metadata for {col} -> {th_name}")
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    update_metadata()
