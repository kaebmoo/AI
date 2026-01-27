import requests
import sys
import time
import json
import sqlite3

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
EMAIL = f"test_rules_{int(time.time())}@ntplc.co.th"

def setup_user_and_token():
    # Login (Request OTP) - using ntplc.co.th to bypass domain check
    requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "platform": "web"})
    
    # In DEV: Inject known OTP hash
    time.sleep(1) 
    conn = sqlite3.connect("nt_revenue.sqlite")
    cursor = conn.cursor()
    import hashlib
    otp_hash = hashlib.sha256("111111".encode()).hexdigest()
    cursor.execute(
        "UPDATE otp_requests SET otp_code = ? WHERE email = ? AND verified_at IS NULL", 
        (otp_hash, EMAIL)
    )
    conn.commit()
    conn.close()
    
    # Verify
    verify_resp = requests.post(f"{BASE_URL}/auth/verify", json={
        "email": EMAIL,
        "otp": "111111", 
        "platform": "web"
    })
    
    if verify_resp.status_code != 200:
        print(f"Login failed: {verify_resp.text}")
        sys.exit(1)
        
    return verify_resp.json()["access_token"]

def test_filtering_rule():
    token = setup_user_and_token()
    headers = {"X-Session-Token": token}
    
    question = "ขอทราบรายได้รวมทั้งหมด แยกตาม product group"
    print(f"\nSending Question: '{question}'")
    
    resp = requests.post(
        f"{BASE_URL}/chat/", 
        headers=headers,
        json={"question": question}
    )
    
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
        return
        
    data = resp.json()
    sql = data.get('sql_query', '')
    print(f"\nSQL Generated:\n{sql}")
    print(f"\nExplanation:\n{data.get('answer')}")
    
    # Validation Logic
    # Rule: Exclude BUSINESS_GROUP='รายได้อื่น' AND SERVICE_GROUP='รายได้อื่น' UNLESS SERVICE_GROUP='ผลตอบแทนทางการเงิน'
    # Since 'รายได้อื่น' matches both, the logic usually simplifies to:
    # NOT (BUSINESS_GROUP = 'รายได้อื่น' AND SERVICE_GROUP = 'รายได้อื่น')
    # OR explicit logic.
    
    # Note: AI might implement this in various ways.
    # e.g. WHERE ... AND NOT (BUSINESS_GROUP = 'รายได้อื่น' AND SERVICE_GROUP = 'รายได้อื่น')
    # Or WHERE ... AND (BUSINESS_GROUP != 'รายได้อื่น' OR SERVICE_GROUP != 'รายได้อื่น') -- wait this is tricky
    
    # Let's check for keywords 'รายได้อื่น' and 'BUSINESS_GROUP' / 'SERVICE_GROUP' in WHERE clause
    sql_lower = sql.lower()
    
    has_rule_logic = False
    
    # Check for exclusion logic
    if "รายได้อื่น" in sql and ("business_group" in sql_lower or "service_group" in sql_lower):
        if "not" in sql_lower or "!=" in sql or "<>" in sql:
            has_rule_logic = True
            
    if has_rule_logic:
        print("\n✅ SUCCESS: SQL appears to contain the filtering rule logic.")
    else:
        print("\n⚠️ WARNING: SQL might be missing the filtering rule. Check manually.")
        
    # Check for Column Names
    if "BUSINESS_GROUP" in sql or "business_group" in sql_lower:
        print("✅ SUCCESS: Correctly used 'BUSINESS_GROUP'")
    else:
         print("❌ FAIL: Did not use 'BUSINESS_GROUP'")

if __name__ == "__main__":
    test_filtering_rule()
