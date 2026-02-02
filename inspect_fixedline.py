
import sqlite3
import pandas as pd

def find_value(db_path, table, value):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get columns
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [info[1] for info in cursor.fetchall()]
    
    found = []
    
    for col in columns:
        try:
            query = f"SELECT count(*) FROM {table} WHERE \"{col}\" LIKE '%{value}%'"
            cursor.execute(query)
            count = cursor.fetchone()[0]
            if count > 0:
                # Get sample
                cursor.execute(f"SELECT DISTINCT \"{col}\" FROM {table} WHERE \"{col}\" LIKE '%{value}%' LIMIT 3")
                samples = [r[0] for r in cursor.fetchall()]
                found.append((col, count, samples))
        except Exception as e:
            pass # Skip non-text columns
            
    conn.close()
    return found

results = find_value("nt_fi_report.sqlite", "revenue_search", "Fixed Line")
for col, count, samples in results:
    print(f"Column: {col}, Count: {count}, Samples: {samples}")

results = find_value("nt_fi_report.sqlite", "revenue_search", "Fixedline")
for col, count, samples in results:
    print(f"Column: {col}, Count: {count}, Samples: {samples}")
