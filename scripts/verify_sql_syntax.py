import requests
import time
import json

BASE_URL = "http://localhost:8000/api/v1"
EMAIL = f"test_sql_{int(time.time())}@ntplc.co.th"

def verify_sqlite_syntax():
    # 1. Register/Login
    print(f"1. Login as {EMAIL}...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "platform": "web"})
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        return

    # Injections
    import sqlite3
    import hashlib
    time.sleep(1)
    conn = sqlite3.connect("nt_revenue.sqlite")
    cursor = conn.cursor()
    otp_hash = hashlib.sha256("111111".encode()).hexdigest()
    cursor.execute("UPDATE otp_requests SET otp_code = ? WHERE email = ? AND verified_at IS NULL", (otp_hash, EMAIL))
    conn.commit()
    conn.close()
    
    verify_resp = requests.post(f"{BASE_URL}/auth/verify", json={"email": EMAIL, "otp": "111111", "platform": "web"})
    token = verify_resp.json().get("access_token")
    headers = {"X-Session-Token": token}
    
    # 2. Ask question requiring concatenation and padding
    # "YYYY-MM" format requires concat(year, '-', lpad(month)) if naively done, so this is a good test.
    question = "ขอรายได้รวมแยกตามเดือน รูปแบบ YYYY-MM (เช่น 2025-01)"
    print(f"\n2. Asking: '{question}'")
    
    resp = requests.post(f"{BASE_URL}/chat/", headers=headers, json={"question": question})
    data = resp.json()
    
    sql = data.get("sql_query", "")
    print(f"SQL: {sql}")
    
    if "CONCAT" in sql.upper() or "LPAD" in sql.upper():
        print("FAILURE: AI still uses CONCAT/LPAD")
    elif "||" in sql or "printf" in sql:
        print("SUCCESS: AI used SQLite compatible syntax")
    else:
        print("WARNING: AI might have used a different approach (check SQL)")

if __name__ == "__main__":
    verify_sqlite_syntax()
