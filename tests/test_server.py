import pytest
from fastapi.testclient import TestClient
from synq.server import app, init_demo_data_db
from synq.db_models import Base
from synq.database import engine, get_db_session, init_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_demo_data():
    # Drop and recreate all tables to get a clean slate for each test
    Base.metadata.drop_all(bind=engine)
    init_db()
    with get_db_session() as session:
        init_demo_data_db(session)

def test_list_merchants():
    res = client.get("/api/merchants")
    assert res.status_code == 200
    merchants = res.json()
    assert len(merchants) >= 5
    merchant_ids = [m["merchant_id"] for m in merchants]
    assert "m1" in merchant_ids

def test_ai_suggest_campaign():
    payload = {
        "merchant_id": "m1",
        "goal": "Acquire new morning weekend coffee customers"
    }
    res = client.post("/api/merchants/m1/ai-suggest", json=payload)
    assert res.status_code == 200
    proposal = res.json()
    assert "campaign_name" in proposal
    assert "offer_value" in proposal
    assert "marketing_copy" in proposal

def test_create_campaign_and_review():
    # 1. Create a campaign
    campaign_payload = {
        "merchant_id": "m1",
        "name": "Weekend Brew Fest",
        "offer_type": "Cashback Percentage",
        "offer_value": 15.0,
        "min_spend": 5.0,
        "budget": 500.0,
        "duration_days": 14,
        "audience_segments": ["Coffee Buyers", "Local Radius"],
        "marketing_copy": "Enjoy 15% cashback on weekend mornings!",
        "legal_disclosure": "Valid on debit transactions. Min spend $5. Max cashback $3."
    }
    res = client.post("/api/merchants/m1/campaigns", json=campaign_payload)
    assert res.status_code == 200
    data = res.json()
    campaign = data["campaign"]
    campaign_id = campaign["campaign_id"]
    
    # Since copy is clean, it should be auto-approved (ACTIVE)
    assert campaign["status"] == "Active"

    # 2. Create a non-compliant campaign with restricted category word "beer"
    bad_payload = campaign_payload.copy()
    bad_payload["name"] = "Starbucks Beer Special"
    bad_payload["marketing_copy"] = "Get 15% cashback on beers!"
    
    res = client.post("/api/merchants/m1/campaigns", json=bad_payload)
    assert res.status_code == 200
    data = res.json()
    campaign = data["campaign"]
    assert campaign["status"] == "Pending Compliance Review"
    bad_campaign_id = campaign["campaign_id"]

    # 3. Check pending compliance list
    res = client.get("/api/admin/compliance/pending")
    assert res.status_code == 200
    pending = res.json()
    pending_ids = [p["campaign_id"] for p in pending]
    assert bad_campaign_id in pending_ids

    # 4. Review decision (Approve the bad campaign)
    review_payload = {
        "campaign_id": bad_campaign_id,
        "approved": True
    }
    res = client.post("/api/admin/compliance/review", json=review_payload)
    assert res.status_code == 200
    assert res.json()["campaign"]["status"] == "Active"

def test_get_customer_360():
    res = client.get("/api/consumers/c1")
    assert res.status_code == 200
    data = res.json()
    assert "customer" in data
    assert data["customer"]["customer_id"] == "c1"
    assert "affinity_profile" in data

def test_get_offers_feed_and_activate():
    # Alice feed
    res = client.get("/api/consumers/c1/offers")
    assert res.status_code == 200
    feed = res.json()
    assert "recommended" in feed
    assert len(feed["recommended"]) > 0
    
    # Try to activate an offer
    campaign_id = feed["recommended"][0]["campaign_id"]
    res = client.post("/api/consumers/c1/offers/activate", json={"campaign_id": campaign_id})
    assert res.status_code == 200
    assert "activated" in res.json()["message"]

def test_simulate_transaction_and_analytics():
    # 1. Simulate a transaction for Alice (c1) at Starbucks
    # Starbucks has active campaign 'camp_starbucks' which is activated by c1 in demo setup
    payload = {
        "merchant_name": "Starbucks Store #493",
        "amount": 10.0
    }
    res = client.post("/api/consumers/c1/transactions/simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["matched"] is True
    assert data["redemption"]["cashback_amount"] == 1.50 # 15% of $10.0
    
    # 2. Check analytics for Starbucks (m1)
    res = client.get("/api/merchants/m1/analytics")
    assert res.status_code == 200
    analytics = res.json()
    assert analytics["metrics"]["redemptions"] >= 1
    assert len(analytics["settlements"]) >= 1

def test_authentication(monkeypatch):
    # 1. Verify we can log in and retrieve a JWT token
    login_payload = {
        "username": "admin",
        "password": "admin123"
    }
    res = client.post("/api/auth/login", json=login_payload)
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data
    token = token_data["access_token"]

    # 2. Mock SYNQ_ENFORCE_AUTH to True to test securing endpoints
    monkeypatch.setattr("synq.server.SYNQ_ENFORCE_AUTH", True)

    # 3. Request a gated endpoint without headers -> Should return 401
    res_unauth = client.get("/api/admin/compliance/pending")
    assert res_unauth.status_code == 401

    # 4. Request with invalid header scheme -> Should return 401
    res_bad_scheme = client.get("/api/admin/compliance/pending", headers={"Authorization": f"Basic {token}"})
    assert res_bad_scheme.status_code == 401

    # 5. Request with valid bearer token -> Should succeed
    res_auth = client.get("/api/admin/compliance/pending", headers={"Authorization": f"Bearer {token}"})
    assert res_auth.status_code == 200

    # 6. Request a customer-specific gated endpoint with merchant role -> Should return 403
    merchant_login_payload = {
        "username": "merchant_m1",
        "password": "merchant123"
    }
    res_merch = client.post("/api/auth/login", json=merchant_login_payload)
    merch_token = res_merch.json()["access_token"]
    
    res_gated = client.get("/api/consumers/c1/offers", headers={"Authorization": f"Bearer {merch_token}"})
    assert res_gated.status_code == 403

def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

def test_registration():
    # 1. Register a new consumer user
    reg_payload = {
        "username": "test_consumer",
        "password": "testpassword123",
        "role": "consumer"
    }
    res = client.post("/api/auth/register", json=reg_payload)
    assert res.status_code == 200
    user_data = res.json()
    assert user_data["username"] == "test_consumer"
    assert user_data["role"] == "consumer"
    assert user_data["customer_id"] is not None

    # 2. Registering same username again should fail
    res_dup = client.post("/api/auth/register", json=reg_payload)
    assert res_dup.status_code == 400
    assert "already registered" in res_dup.json()["detail"]

    # 3. Log in with newly registered user
    login_payload = {
        "username": reg_payload["username"],
        "password": reg_payload["password"]
    }
    res_login = client.post("/api/auth/login", json=login_payload)
    assert res_login.status_code == 200
    login_data = res_login.json()
    assert "access_token" in login_data
    assert login_data["role"] == "consumer"

def test_validation_errors_and_exception_handler():
    # 1. Test validation error: negative transaction amount
    payload = {
        "merchant_name": "Starbucks Store",
        "amount": -10.0 # Negative is invalid
    }
    res = client.post("/api/consumers/c1/transactions/simulate", json=payload)
    assert res.status_code == 400
    res_json = res.json()
    assert "detail" in res_json
    assert "trace_id" in res_json

    # 2. Test invalid coordinate bounds during onboarding
    onboard_payload = {
        "name": "Invalid Location Store",
        "category": "Dining",
        "address": "123 Main St",
        "latitude": 95.0, # Latitude must be <= 90
        "longitude": 10.0
    }
    res_onboard = client.post("/api/onboard/merchant", json=onboard_payload)
    assert res_onboard.status_code == 400
    res_onboard_json = res_onboard.json()
    assert "detail" in res_onboard_json
    assert "trace_id" in res_onboard_json


def test_ai_suggest_campaign_for_newly_onboarded_merchant(monkeypatch):
    # 1. Mock SYNQ_ENFORCE_AUTH to False
    monkeypatch.setattr("synq.server.SYNQ_ENFORCE_AUTH", False)

    # 2. Onboard merchant
    onboard_payload = {
        "name": "Brews & Co Test Store",
        "category": "Coffee",
        "address": "999 Coffee Lane",
        "latitude": 37.7749,
        "longitude": -122.4194
    }
    res_onboard = client.post("/api/onboard/merchant", json=onboard_payload)
    assert res_onboard.status_code == 200
    new_merchant_id = res_onboard.json()["merchant"]["merchant_id"]

    # 3. Call ai-suggest
    suggest_payload = {
        "merchant_id": new_merchant_id,
        "goal": "Acquire weekend breakfast coffee users"
    }
    res_suggest = client.post(f"/api/merchants/{new_merchant_id}/ai-suggest", json=suggest_payload)
    assert res_suggest.status_code == 200


def test_customer_private_demographics_and_location():
    # 1. Fetch customer c1 details
    res_c1 = client.get("/api/consumers/c1")
    assert res_c1.status_code == 200
    c1_data = res_c1.json()
    assert c1_data["customer"]["age"] == 28
    assert c1_data["customer"]["gender"] == "Female"
    assert c1_data["customer"]["income_bracket"] == "Medium"
    assert c1_data["customer"]["home_latitude"] == 37.7895
    assert c1_data["customer"]["home_longitude"] == -122.4014

    # 2. Fetch customer c2 details and check offline demographic boosts
    res_c2 = client.get("/api/consumers/c2")
    assert res_c2.status_code == 200
    c2_data = res_c2.json()
    assert c2_data["customer"]["age"] == 45
    assert c2_data["customer"]["income_bracket"] == "High"

    # Verify that the affinity calculation includes demographic reasoning
    affinity_profile = c2_data["affinity_profile"]
    assert "affinities" in affinity_profile
    
    # Dining or Travel category should have high income tier adjustment applied
    dining_affinity = next((a for a in affinity_profile["affinities"] if a["category"] == "Dining"), None)
    assert dining_affinity is not None
    assert "High income tier adjustment" in dining_affinity["reasoning"]


def test_dynamic_device_location_offers_feed():
    # Fetch c1 offers feed passing active device location parameters close to Starbucks
    res = client.get("/api/consumers/c1/offers?latitude=37.7890&longitude=-122.4010")
    assert res.status_code == 200
    data = res.json()
    assert "recommended" in data
    assert "nearby" in data
    assert "trending" in data
    
    # Ensure nearby offers list is computed
    assert len(data["nearby"]) > 0


def test_bypass_auth_context_cross_merchant(monkeypatch):
    # 1. Force SYNQ_ENFORCE_AUTH to False
    monkeypatch.setattr("synq.server.SYNQ_ENFORCE_AUTH", False)

    # 2. Mock a token representing merchant 'm1'
    # In bypass mode, passing any authorization that translates to merchant role
    # should NOT restrict suggestions for merchant 'm2'
    from synq.auth import create_access_token
    token = create_access_token(data={"sub": "merchant_m1", "role": "merchant", "merchant_id": "m1"})
    headers = {"Authorization": f"Bearer {token}"}

    suggest_payload = {
        "merchant_id": "m2",
        "goal": "Promote weekend dinner values"
    }

    # Should succeed with 200 instead of 403 Forbidden
    res = client.post("/api/merchants/m2/ai-suggest", json=suggest_payload, headers=headers)
    assert res.status_code == 200
    assert "campaign_name" in res.json()





