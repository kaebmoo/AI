import requests
import time
import json

BASE_URL = "http://localhost:8000/api/v1"
EMAIL = f"test_abbr_{int(time.time())}@ntplc.co.th"

def verify_abbreviations():
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
    conn = sqlite3.connect("nt_fi_report.sqlite")
    cursor = conn.cursor()
    otp_hash = hashlib.sha256("111111".encode()).hexdigest()
    cursor.execute("UPDATE otp_requests SET otp_code = ? WHERE email = ? AND verified_at IS NULL", (otp_hash, EMAIL))
    conn.commit()
    conn.close()
    
    verify_resp = requests.post(f"{BASE_URL}/auth/verify", json={"email": EMAIL, "otp": "111111", "platform": "web"})
    token = verify_resp.json().get("access_token")
    headers = {"X-Session-Token": token}
    
    # 2. Test "นป." (Should match Northern Group)
    question1 = "ขอรายได้รวมของหน่วยงาน นป."
    print(f"\n2. Asking: '{question1}'")
    resp1 = requests.post(f"{BASE_URL}/chat/", headers=headers, json={"question": question1})
    data1 = resp1.json()
    sql1 = data1.get("sql_query", "")
    print(f"SQL1: {sql1}")
    
    if "กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ" in sql1 or "นป." in sql1:
        print("SUCCESS: 'นป.' mapped correctly.")
    else:
        print("FAILURE: 'นป.' filtering incorrect.")
        
    # 3. Test "บชง." (Should match Accounting Dept)
    question2 = "ขอรายได้รวมของ บชง."
    print(f"\n3. Asking: '{question2}'")
    resp2 = requests.post(f"{BASE_URL}/chat/", headers=headers, json={"question": question2})
    data2 = resp2.json()
    sql2 = data2.get("sql_query", "")
    print(f"SQL2: {sql2}")
    
    if "ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ" in sql2:
        print("SUCCESS: 'บชง.' mapped correctly.")
    else:
        print("FAILURE: 'บชง.' filtering incorrect.")

if __name__ == "__main__":
    verify_abbreviations()
