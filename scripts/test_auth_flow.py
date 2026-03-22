import requests
import time

from runtime_config import get_api_base_url

# Configuration
BASE_URL = get_api_base_url()
EMAIL = f"test_{int(time.time())}@example.com"

def test_login():
    print(f"Testing Login with {EMAIL}...")
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json={"email": EMAIL})
        if response.status_code == 200:
            print("Login successful (OTP requested).")
            return True
        else:
            print(f"Login failed: {response.text}")
            return False
    except Exception as e:
        print(f"Connection failed: {str(e)}")
        return False

def test_verify_simulation():
    print("To test verification, you need the real OTP sent to email (or checking logs if mocked).")
    print("This script cannot automatically verify without the OTP.")
    # In a real integration test, we might check the database for the OTP or use a fixed seed in test env.

if __name__ == "__main__":
    if test_login():
        test_verify_simulation()
