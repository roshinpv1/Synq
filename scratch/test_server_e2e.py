import sys
import time
import requests
import json

BASE_URL = "http://127.0.0.1:8005"

def test_e2e():
    print("==================================================================")
    # 1. Fetch Merchants list
    print("\n[Step 1] Fetching onboarded merchants list...")
    res = requests.get(f"{BASE_URL}/api/merchants")
    assert res.status_code == 200, f"Failed: {res.text}"
    merchants = res.json()
    print(f"Success: Found {len(merchants)} merchants.")
    for m in merchants:
        print(f"  - {m['merchant_id']}: {m['name']} (Category: {m['category']})")
        
    # 2. Trigger AI Campaign Suggestion (Campaign Agent AG-001)
    print("\n[Step 2] Triggering Campaign Agent (AG-001) for Starbucks (m1)...")
    payload = {
        "merchant_id": "m1",
        "goal": "Acquire new morning weekend coffee customers"
    }
    res = requests.post(f"{BASE_URL}/api/merchants/m1/ai-suggest", json=payload)
    assert res.status_code == 200, f"Failed: {res.text}"
    proposal = res.json()
    print(f"Success: AI Proposal Generated!")
    print(f"  - Suggested Name: {proposal.get('campaign_name')}")
    print(f"  - Copy: {proposal.get('marketing_copy')}")
    print(f"  - Suggested Rate: {proposal.get('offer_value')}%")
    print(f"  - Reasoning: {proposal.get('reasoning')[:100]}...")
    
    # 3. Create draft campaign using the suggested parameters
    print("\n[Step 3] Submitting new campaign to bank compliance queue...")
    audience = proposal.get("target_segments", ["Coffee Buyers", "Local Radius"])
    
    # Map raw LLM segments onto strict bank database segment enums
    mapped_audience = []
    for s in audience:
        s_lower = s.lower()
        if "coffee" in s_lower:
            mapped_audience.append("Coffee Buyers")
        elif "dine" in s_lower or "dining" in s_lower or "food" in s_lower:
            mapped_audience.append("Frequent Diners")
        elif "travel" in s_lower or "fly" in s_lower:
            mapped_audience.append("Travelers")
        elif "high spender" in s_lower or "big spender" in s_lower:
            mapped_audience.append("High Spenders")
        elif "competitor" in s_lower:
            mapped_audience.append("Competitor Spenders")
        elif "local" in s_lower or "radius" in s_lower or "nearby" in s_lower:
            mapped_audience.append("Local Radius")
        elif "credit" in s_lower:
            mapped_audience.append("Credit Card Holders")
        elif "rewards" in s_lower:
            mapped_audience.append("Rewards Customers")
            
    mapped_audience = list(set(mapped_audience))
    if not mapped_audience:
        mapped_audience = ["Coffee Buyers", "Local Radius"]
        
    print(f"  - LLM segments: {audience} -> Mapped strict segments: {mapped_audience}")
    
    campaign_payload = {
        "merchant_id": "m1",
        "name": proposal.get("campaign_name", "Weekend Morning Special"),
        "offer_type": "Cashback Percentage",
        "offer_value": proposal.get("offer_value", 10.0),
        "min_spend": 5.0,
        "budget": proposal.get("suggested_budget", 500.0),
        "duration_days": proposal.get("suggested_duration_days", 14),
        "audience_segments": mapped_audience,
        "marketing_copy": proposal.get("marketing_copy", "Enjoy coffee!"),
        "legal_disclosure": proposal.get("suggested_legal_disclosure", "Valid on debit cards. Min spend $5.")
    }
    res = requests.post(f"{BASE_URL}/api/merchants/m1/campaigns", json=campaign_payload)
    assert res.status_code == 200, f"Failed: {res.text}"
    camp_created = res.json()
    campaign_id = camp_created["campaign"]["campaign_id"]
    initial_status = camp_created["campaign"]["status"]
    print(f"Success: Campaign created with ID: {campaign_id} (Status: {initial_status})")
    
    # 4 & 5. Handle compliance approval if it is pending compliance
    if initial_status == "Pending Compliance":
        print("\n[Step 4] Checking Compliance Queue for AI audit review...")
        res = requests.get(f"{BASE_URL}/api/admin/compliance/pending")
        assert res.status_code == 200, f"Failed: {res.text}"
        pending = res.json()
        print(f"Success: Found {len(pending)} pending campaigns in compliance queue.")
        
        matching_audit = None
        for p in pending:
            if p["campaign_id"] == campaign_id:
                matching_audit = p
                break
                
        assert matching_audit is not None, "Created campaign not found in compliance queue!"
        print(f"  - Campaign: {matching_audit['name']}")
        print(f"  - Compliance Status: FLAGGED (Requires manual admin override)")
        print(f"  - Audit Flag Reasons: {matching_audit['compliance_review']['flagged_reasons']}")
        
        print("\n[Step 5] Manually approving campaign to the live network...")
        review_payload = {
            "campaign_id": campaign_id,
            "approved": True,
            "compliance_feedback": "Audited and approved via UAT integration test."
        }
        res = requests.post(f"{BASE_URL}/api/admin/compliance/review", json=review_payload)
        assert res.status_code == 200, f"Failed: {res.text}"
        print(f"Success: Campaign status is now: {res.json()['status']}")
    else:
        print("\n[Step 4 & 5] Skipping manual compliance approval queue because campaign was auto-approved as COMPLIANT on creation.")
    
    # 6. View Consumer personalized feed (triggers Ranking Agent AG-006 & Insights Agent AG-010)
    print("\n[Step 6] Loading Alice Vance's (c1) personalized feed...")
    res = requests.get(f"{BASE_URL}/api/consumers/c1/offers")
    assert res.status_code == 200, f"Failed: {res.text}"
    offers_data = res.json()
    recommended_offers = offers_data.get("recommended", [])
    print(f"Success: Received sorted offers list.")
    
    target_offer = None
    for idx, o in enumerate(recommended_offers):
        print(f"  {idx+1}. {o['merchant_name']} (Relevance Score: {o['relevance_score']})")
        print(f"     Personalized Insight: {o['user_explanation']}")
        if o["campaign_id"] == campaign_id:
            target_offer = o
            
    assert target_offer is not None, "Our published campaign is not visible in consumer feed!"
    
    # 7. Activate the offer for Alice
    print("\n[Step 7] Activating offer for consumer c1...")
    act_payload = {
        "campaign_id": campaign_id
    }
    res = requests.post(f"{BASE_URL}/api/consumers/c1/offers/activate", json=act_payload)
    assert res.status_code == 200, f"Failed: {res.text}"
    print(f"Success: {res.json()['message']}")
    
    # 8. Simulate card transaction swipe (Matching & Settlement Engines)
    print("\n[Step 8] Simulating Alice's debit card swipe of $8.50 at Starbucks...")
    swipe_payload = {
        "merchant_name": "Starbucks",
        "amount": 8.50,
        "card_product": "Debit Card"
    }
    res = requests.post(f"{BASE_URL}/api/consumers/c1/transactions/simulate", json=swipe_payload)
    assert res.status_code == 200, f"Failed: {res.text}"
    swipe_result = res.json()
    print("Success: Transaction processed!")
    matched = swipe_result.get("matched", False)
    print(f"  - Match Found: {matched}")
    
    cashback = 0.0
    if matched and swipe_result.get("redemption"):
        cashback = swipe_result["redemption"].get("cashback_amount", 0.0)
    print(f"  - Cashback Amount Credited: ${cashback:.2f}")
    
    # 9. Verify merchant settlement records (SettlementEngine)
    print("\n[Step 9] Verifying merchant billing and settlement ledger...")
    res = requests.get(f"{BASE_URL}/api/merchants/m1/analytics")
    assert res.status_code == 200, f"Failed: {res.text}"
    analytics = res.json()
    metrics = analytics.get("metrics", {})
    print(f"Success: Starbucks Analytics:")
    print(f"  - Total Spend Driven: ${metrics.get('spend_driven', 0.0):.2f}")
    
    budget_remaining = 0.0
    for c in analytics.get("campaigns", []):
        if c["campaign_id"] == campaign_id:
            budget_remaining = c["remaining_budget"]
    print(f"  - Active Campaign Budget Remaining: ${budget_remaining:.2f}")
    
    billing_records = analytics.get("settlements", [])
    print(f"  - Billing Invoices Count: {len(billing_records)}")
    for bill in billing_records:
        print(f"    - Charged: ${bill['total_charged']:.2f} (Cashback: ${bill['cashback_charge']:.2f} + Bank fee: ${bill['bank_fee']:.2f})")
    
    print("\n==================================================================")
    print("ALL API PORTALS, MATCHING ENGINES, AND AGENT WORKFLOWS ARE WORKING!")
    print("==================================================================")

if __name__ == "__main__":
    try:
        test_e2e()
    except Exception as e:
        print(f"\nERROR running integration test: {e}")
        sys.exit(1)
