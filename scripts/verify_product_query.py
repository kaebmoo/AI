import requests
import time
import json
from runtime_config import get_api_base_url, get_business_db_path

BASE_URL = get_api_base_url()
DB_PATH = get_business_db_path()
EMAIL = f"test_prod_{int(time.time())}@ntplc.co.th"

def verify_product_query():
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
    
    # 2. Ask for product breakdown
    question = "ขอรายได้แยกตามชื่อผลิตภัณฑ์ (PRODUCT_NAME) 5 อันดับแรก"
    print(f"\n2. Asking: '{question}'")
    
    resp = requests.post(f"{BASE_URL}/chat/", headers=headers, json={"question": question})
    data = resp.json()
    
    answer = data.get("answer", "")
    sql = data.get("sql_query", "")
    
    print(f"Answer: {answer}")
    print(f"SQL: {sql}")
    
    if "PRODUCT_NAME" in sql.upper():
        print("\nSUCCESS: AI used PRODUCT_NAME column.")
    else:
        print("\nFAILURE: AI did not use PRODUCT_NAME. Check if column exists.")

if __name__ == "__main__":
    verify_product_query()
