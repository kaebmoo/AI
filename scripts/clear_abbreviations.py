import sqlite3

def clear_abbreviations():
    conn = sqlite3.connect("nt_revenue.sqlite")
    cursor = conn.cursor()
    
    # Delete the hardcoded rules to test general logic
    cursor.execute("DELETE FROM schema_business_rules WHERE rule_name = 'Common Abbreviations'")
    
    conn.commit()
    print("Deleted hardcoded abbreviation rules.")
    conn.close()

if __name__ == "__main__":
    clear_abbreviations()
