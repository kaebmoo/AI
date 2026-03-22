
import sqlite3

from runtime_config import get_business_db_path

DB_PATH = get_business_db_path()

def print_table(headers, rows):
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
    
    # Create format string
    fmt = " | ".join([f"{{:<{w}}}" for w in widths])
    separator = "-+-".join(["-" * w for w in widths])
    
    print(fmt.format(*headers))
    print(separator)
    for row in rows:
        print(fmt.format(*[str(val) for val in row]))

def analyze_table(conn, table_name, columns):
    print(f"\n--- Analyzing {table_name} ---")
    try:
        query = f"SELECT {', '.join(columns)} FROM {table_name}"
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            print("Table is empty.")
            return

        print(f"Total Rows: {len(rows)}")
        print_table(columns, rows)
        
        # Check for duplicate keywords
        if 'keyword' in columns:
            keywords = [row[0] for row in rows]
            duplicates = set([x for x in keywords if keywords.count(x) > 1])
            if duplicates:
                print(f"\nWarning: Duplicate keywords found: {', '.join(duplicates)}")

    except Exception as e:
        print(f"Error reading {table_name}: {e}")

def main():
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # 1. schema_metadata
        analyze_table(conn, 'schema_metadata', ['table_name', 'column_name', 'display_name_th', 'data_type', 'is_summable'])

        # 2. schema_business_rules
        analyze_table(conn, 'schema_business_rules', ['rule_code', 'rule_name', 'applies_to', 'severity'])

        # 3. schema_semantic_mapping
        analyze_table(conn, 'schema_semantic_mapping', ['keyword', 'keyword_type', 'target_column', 'target_condition'])

        # 4. golden_examples
        analyze_table(conn, 'golden_examples', ['question_pattern', 'category'])

    except Exception as e:
        print(f"Database connection error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
