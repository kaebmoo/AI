import requests
import sys
import time
import json

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
EMAIL = f"test_mt_{int(time.time())}@ntplc.co.th"
PASSWORD = "password"

def test_multiturn_chat():
    username = f"User {int(time.time())}"
    
    # 1. Register & Login
    print(f"1. Registering/Login as {EMAIL}...")
    
    # Login (Request OTP)
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "platform": "web"})
    print(f"Login Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Login Response: {resp.text}")
        return

    # In DEV: Since email is async/mock, we update the DB directly with a known OTP hash
    import sqlite3
    import hashlib
    
    # Wait for async task to (hopefully) create the record
    time.sleep(2) 
    
    conn = sqlite3.connect("nt_revenue.sqlite")
    cursor = conn.cursor()
    otp_hash = hashlib.sha256("111111".encode()).hexdigest()
    
    # Update the latest OTP request for this email
    cursor.execute(
        "UPDATE otp_requests SET otp_code = ? WHERE email = ? AND verified_at IS NULL", 
        (otp_hash, EMAIL)
    )
    conn.commit()
    conn.close()
    print("Injected known OTP hash for testing.")
    
    # Verify OTP (Implicit Register)
    # Mock OTP is usually 111111 or similar in dev
    verify_resp = requests.post(f"{BASE_URL}/auth/verify", json={
        "email": EMAIL,
        "otp": "111111", # Mock OTP
        "platform": "web"
    })
    
    if verify_resp.status_code != 200:
        print(f"Login/Verify failed: {verify_resp.text}")
        return
        
    token = verify_resp.json()["access_token"]

    headers = {"X-Session-Token": token}
    print("Logged in.")

    # 2. First Question (Start Conversation)
    print("\n2. Sending First Question...")
    q1 = "รายได้รวมเดือนมกราคม 2568 รายได้ของ กลุ่มบริการ Satellite NT และ กลุ่มบริการ Satellite ไทยคม?"
    resp1 = requests.post(
        f"{BASE_URL}/chat/", 
        headers=headers,
        json={"question": q1}
    )
    if resp1.status_code != 200:
        print(f"Error Q1: {resp1.text}")
        return
        
    data1 = resp1.json()
    conversation_id = data1.get("conversation_id")
    print(f"Response 1: {data1.get('answer')}")
    print(f"Conversation ID: {conversation_id}")
    
    if not conversation_id:
        print("FAIL: No conversation_id returned")
        return

    # 3. Second Question (Follow-up)
    print("\n3. Sending Follow-up Question (expecting context awareness)...")
    q2 = "แยกตาม BU ให้หน่อย"
    resp2 = requests.post(
        f"{BASE_URL}/chat/", 
        headers=headers,
        json={
            "question": q2,
            "conversation_id": conversation_id
        }
    )
    
    if resp2.status_code != 200:
        print(f"Error Q2: {resp2.text}")
        return
        
    data2 = resp2.json()
    print(f"Response 2: {data2.get('answer')}")
    print(f"SQL Used: {data2.get('sql_query')}")
    
    # Check if SQL indicates awareness of Month (Jan 2025) and uses English columns
    sql = data2.get('sql_query', '').lower()
    
    is_month_aware = 'jan' in sql or '01' in sql or '2025' in sql or '2568' in sql
    is_english_col = 'business_unit' in sql and 'กลุ่มธุรกิจ' not in sql
    
    if is_month_aware:
        print("SUCCESS: SQL contains date context from previous turn.")
    else:
        print("WARNING: SQL might not contain date context.")
        
    if is_english_col:
        print("SUCCESS: SQL uses English columns (business_unit).")
    else:
        print("WARNING: SQL might still use Thai columns. Check output.")

    # 4. Third Question (Distinguish Product vs Org)
    print("\n4. Sending Question clarifying Product vs Org...")
    q3 = "แยกตามกลุ่มผลิตภัณฑ์ให้หน่อย (Product Group)"
    resp3 = requests.post(
        f"{BASE_URL}/chat/", 
        headers=headers,
        json={
            "question": q3,
            "conversation_id": conversation_id
        }
    )
    
    if resp3.status_code != 200:
        print(f"Error Q3: {resp3.text}")
        return
        
    data3 = resp3.json()
    print(f"Response 3: {data3.get('answer')}")
    print(f"SQL Used: {data3.get('sql_query')}")
    
    sql3 = data3.get('sql_query', '').lower()
    if 'business_group' in sql3:
        print("SUCCESS: AI correctly mapped 'กลุ่มผลิตภัณฑ์' to 'BUSINESS_GROUP'.")
    elif 'product_group' in sql3:
        print("WARNING: AI still used 'product_group' (old schema).")
    else:
        print("WARNING: SQL check output manually.")

if __name__ == "__main__":
    test_multiturn_chat()
