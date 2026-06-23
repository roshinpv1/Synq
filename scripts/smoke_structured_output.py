"""End-to-end smoke test for Synq structured-output agents against a real LLM provider.

Usage:
    OPENAI_API_KEY=... python scripts/smoke_structured_output.py openai
    GOOGLE_API_KEY=... python scripts/smoke_structured_output.py google
"""

from __future__ import annotations
import argparse
import os
import sys

from synq.agents import CampaignAgent, ComplianceAgent, AffinityAgent, RankingAgent
from synq.models import Customer, Category, CardProduct, Campaign, CampaignStatus, OfferType

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=["openai", "google"])
    args = parser.parse_args()

    # Configure env to select the chosen provider
    os.environ["SYNQ_LLM_PROVIDER"] = args.provider
    print(f"Testing Synq Agents structured output using LLM provider: {args.provider}")

    # 1. Test Campaign Agent
    print("\n--- [1] Testing CampaignAgent (AG-001) ---")
    goal = "Attract coffee lovers with weekend specials"
    proposal = CampaignAgent.generate_proposal("Starbucks Coffee", "Coffee", goal)
    print(f"Campaign name: {proposal.campaign_name}")
    print(f"Offer value:   {proposal.offer_value}%")
    print(f"Copy:          {proposal.marketing_copy}")
    print(f"Reasoning:     {proposal.reasoning}")

    # 2. Test Compliance Agent
    print("\n--- [2] Testing ComplianceAgent (AG-008) ---")
    review = ComplianceAgent.review_campaign(
        campaign_name=proposal.campaign_name,
        merchant_category="Coffee",
        marketing_copy=proposal.marketing_copy,
        legal_disclosure=proposal.suggested_legal_disclosure
    )
    print(f"Is compliant:  {review.is_compliant}")
    print(f"Flagged:       {review.flagged_reasons}")

    # 3. Test Affinity Agent
    print("\n--- [3] Testing AffinityAgent (AG-003) ---")
    tx_logs = [
        {"merchant_name": "Starbucks Coffee", "category": Category.COFFEE, "amount": 7.50},
        {"merchant_name": "Starbucks Coffee", "category": Category.COFFEE, "amount": 6.20},
        {"merchant_name": "Whole Foods", "category": Category.RETAIL, "amount": 80.00}
    ]
    profile = AffinityAgent.calculate_affinities("cust_smoke", tx_logs)
    print(f"Dominant segment: {profile.dominant_segment}")
    for aff in profile.affinities:
        print(f"  Category {aff.category}: score {aff.score}")

    # 4. Test Ranking Agent
    print("\n--- [4] Testing RankingAgent (AG-006) ---")
    customer = Customer(
        customer_id="cust_smoke",
        name="Smoke Tester",
        email="smoke@test.com",
        products=[CardProduct.REWARDS_CREDIT],
        transactions=[],
        affinity_scores={Category.COFFEE: 9.0, Category.RETAIL: 5.0}
    )
    campaigns = [
        Campaign(
            campaign_id="c1", merchant_id="m1", merchant_name="Starbucks Coffee",
            name="Free Espresso", offer_type=OfferType.CASHBACK_PERCENT, offer_value=15.0,
            budget=100.0, remaining_budget=100.0, duration_days=7, status=CampaignStatus.ACTIVE,
            category=Category.COFFEE, marketing_copy="Get 15% off espresso morning brews."
        ),
        Campaign(
            campaign_id="c2", merchant_id="m2", merchant_name="Target Store",
            name="Grocery Boost", offer_type=OfferType.CASHBACK_FLAT, offer_value=5.0,
            budget=200.0, remaining_budget=200.0, duration_days=7, status=CampaignStatus.ACTIVE,
            category=Category.RETAIL, marketing_copy="Get $5 flat back on grocery spend."
        )
    ]
    ranked = RankingAgent.rank_offers(customer, campaigns)
    for idx, item in enumerate(ranked.ranked_offers):
        print(f"  {idx+1}. Offer {item.campaign_id}: score {item.score}")
        print(f"     Explanation: {item.user_explanation}")

    print("\nSmoke tests completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
