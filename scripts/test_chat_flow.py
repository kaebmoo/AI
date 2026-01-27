import requests
import sys
import time

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
email = f"test_chat_{int(time.time())}@example.com"

def test_chat_flow():
    # 1. Login
    print(f"1. Testing Login with {email}...")
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json={"email": email})
        if response.status_code != 200:
            print(f"Login failed: {response.text}")
            return
            
        print("   OTP requested.")
        
        # In a real test, we'd fetch the OTP. For now, assuming you have a way to get it or mocking verify.
        # But wait! We can't automatically get the OTP in this script without peeking at the DB or logs.
        # So we will ask the user for it if interactive, or skip if not.
        
        otp = input("Enter OTP sent to email (check logs): ")
        
        # 2. Verify
        print(f"2. Verifying OTP: {otp}...")
        verify_response = requests.post(f"{BASE_URL}/auth/verify", json={
            "email": EMAIL,
            "otp": otp,
            "platform": "web"
        })
        
        if verify_response.status_code != 200:
            print(f"Verification failed: {verify_response.text}")
            return
            
        token = verify_response.json()["access_token"]
        print(f"   Authenticated! Token: {token[:10]}...")
        
        # 3. Chat
        print("3. Sending Chat Question...")
        headers = {"X-Session-Token": token}
        question = "What is the revenue for Bangkok?"
        
        chat_response = requests.post(
            f"{BASE_URL}/chat/",
            json={"question": question},
            headers=headers
        )
        
        if chat_response.status_code == 200:
            data = chat_response.json()
            print(f"   Success!")
            print(f"   Question: {data['question']}")
            print(f"   SQL: {data['sql_query']}")
            print(f"   Answer: {data['answer']}")
        else:
            print(f"Chat failed: {chat_response.text}")

    except Exception as e:
        print(f"Test failed: {str(e)}")

if __name__ == "__main__":
    test_chat_flow()
