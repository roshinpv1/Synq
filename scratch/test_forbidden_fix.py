import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_ai_suggest_for_new_merchant():
    print("Starting AI Suggest 403 Forbidden validation test...")

    # 1. Login as admin to get token
    payload = {
        "username": "admin",
        "password": "admin123"
    }
    print(f"Logging in as admin to {BASE_URL}...")
    res = requests.post(f"{BASE_URL}/api/auth/login", json=payload)
    if res.status_code != 200:
        print(f"Login failed: {res.text}")
        sys.exit(1)
        
    login_data = res.json()
    token = login_data["access_token"]
    print(f"Login succeeded! Token retrieved.")

    # 2. Onboard a new merchant
    headers = {"Authorization": f"Bearer {token}"}
    onboard_payload = {
        "name": "Brews & Co Test Store",
        "category": "Coffee",
        "address": "999 Coffee Lane",
        "latitude": 37.7749,
        "longitude": -122.4194
    }
    print("Onboarding new merchant 'Brews & Co Test Store'...")
    res_onboard = requests.post(f"{BASE_URL}/api/onboard/merchant", json=onboard_payload, headers=headers)
    if res_onboard.status_code != 200:
        print(f"Onboarding failed: {res_onboard.text}")
        sys.exit(1)
        
    onboard_data = res_onboard.json()
    new_merchant_id = onboard_data["merchant"]["merchant_id"]
    print(f"New merchant onboarded successfully with ID: {new_merchant_id}")

    # 3. Request AI campaign suggestions for the new merchant
    suggest_payload = {
        "merchant_id": new_merchant_id,
        "goal": "Acquire weekend breakfast coffee users"
    }
    print(f"Requesting AI campaign suggestions for {new_merchant_id}...")
    res_suggest = requests.post(f"{BASE_URL}/api/merchants/{new_merchant_id}/ai-suggest", json=suggest_payload, headers=headers)
    
    print(f"Response Status Code: {res_suggest.status_code}")
    print(f"Response Body: {res_suggest.text[:300]}")
    
    assert res_suggest.status_code == 200, f"Expected 200 OK, got {res_suggest.status_code}"
    print("SUCCESS: 403 Forbidden is resolved! The AI campaign generation endpoint is fully functional.")

if __name__ == "__main__":
    test_ai_suggest_for_new_merchant()
