import sqlite3

def migrate():
    conn = sqlite3.connect("nt_fi_report.sqlite")
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN hashed_password VARCHAR")
        print("Added hashed_password column")
    except sqlite3.OperationalError as e:
        print(f"hashed_password column might already exist: {e}")
        
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN force_password_change BOOLEAN DEFAULT 0")
        print("Added force_password_change column")
    except sqlite3.OperationalError as e:
        print(f"force_password_change column might already exist: {e}")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
