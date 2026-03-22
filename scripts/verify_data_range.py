import requests
import time
import json
from runtime_config import get_api_base_url, get_business_db_path

BASE_URL = get_api_base_url()
DB_PATH = get_business_db_path()
EMAIL = f"test_data_{int(time.time())}@ntplc.co.th"

def verify_data_range():
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    otp_hash = hashlib.sha256("111111".encode()).hexdigest()
    cursor.execute("UPDATE otp_requests SET otp_code = ? WHERE email = ? AND verified_at IS NULL", (otp_hash, EMAIL))
    conn.commit()
    conn.close()
    
    verify_resp = requests.post(f"{BASE_URL}/auth/verify", json={"email": EMAIL, "otp": "111111", "platform": "web"})
    token = verify_resp.json().get("access_token")
    headers = {"X-Session-Token": token}
    
    # 2. Ask for latest data
    question = "ข้อมูลรายได้ล่าสุดคือเดือนปีอะไร?"
    print(f"\n2. Asking: '{question}'")
    
    resp = requests.post(f"{BASE_URL}/chat/", headers=headers, json={"question": question})
    data = resp.json()
    
    answer = data.get("answer", "")
    sql = data.get("sql_query", "")
    
    print(f"Answer: {answer}")
    print(f"SQL: {sql}")
    
    if "12" in answer or "ธันวาคม" in answer:
        print("\nSUCCESS: AI identified December/Month 12.")
    else:
        print("\nFAILURE: AI did not identify December.")

    if "CAST" in sql.upper():
        print("SUCCESS: SQL uses CAST.")
    else:
        print("WARNING: SQL does not use CAST.")

if __name__ == "__main__":
    verify_data_range()
