from synq.models import Customer, Category, CardProduct, Campaign, CampaignStatus, OfferType
from synq.agents import CampaignAgent, ComplianceAgent, AffinityAgent, RankingAgent

def main():
    print("==========================================================")
    print("Synq Agents Simulation Demo (Terminal Console)")
    print("==========================================================")
    
    # 1. Run Merchant Campaign Builder Agent (AG-001)
    print("\n[1] Running Merchant Campaign Agent (AG-001) for Starbucks...")
    goal = "Acquire new morning coffee customers"
    proposal = CampaignAgent.generate_proposal("Starbucks", "Coffee", goal)
    print(f"Proposed Campaign Name: {proposal.campaign_name}")
    print(f"Proposed Copy: {proposal.marketing_copy}")
    print(f"Reasoning: {proposal.reasoning}")

    # 2. Run Compliance Audit Agent (AG-008)
    print("\n[2] Running Compliance Agent (AG-008) to audit draft proposal...")
    review = ComplianceAgent.review_campaign(
        campaign_name=proposal.campaign_name,
        merchant_category="Coffee",
        marketing_copy=proposal.marketing_copy,
        legal_disclosure=proposal.suggested_legal_disclosure
    )
    print(f"Compliance Status: {'COMPLIANT' if review.is_compliant else 'FLAGGED'}")
    if not review.is_compliant:
        print(f"Reasons: {review.flagged_reasons}")

    # 3. Setup Mock Customer & Run Affinity Agent (AG-003)
    tx_data = [
        {"merchant_name": "Starbucks", "category": "Coffee", "amount": 6.50},
        {"merchant_name": "Starbucks", "category": "Coffee", "amount": 5.80},
        {"merchant_name": "Olive Garden", "category": "Dining", "amount": 55.00}
    ]
    print("\n[3] Running Customer Affinity Agent (AG-003) on transaction logs...")
    profile = AffinityAgent.calculate_affinities("c1", tx_data)
    print(f"Dominant segment: {profile.dominant_segment}")
    for aff in profile.affinities:
        if aff.score > 1.0:
            print(f"- {aff.category}: Score {aff.score} ({aff.reasoning[:60]}...)")

    # 4. Setup mock campaign inventory & Run Offer Ranking Agent (AG-006)
    customer = Customer(
        customer_id="c1",
        name="Alice Vance",
        email="alice@synq.com",
        products=[CardProduct.REWARDS_CREDIT],
        transactions=[],
        affinity_scores={Category.COFFEE: 8.5, Category.DINING: 4.0}
    )
    camps = [
        Campaign(
            campaign_id="camp_starbucks", merchant_id="m1", merchant_name="Starbucks",
            name="Starbucks Morning Brew", offer_type=OfferType.CASHBACK_PERCENT, offer_value=15.0,
            budget=500.0, remaining_budget=500.0, duration_days=30, status=CampaignStatus.ACTIVE,
            category=Category.COFFEE, marketing_copy="15% cash back at Starbucks."
        ),
        Campaign(
            campaign_id="camp_olive_garden", merchant_id="m2", merchant_name="Olive Garden",
            name="Olive Garden Family Dining", offer_type=OfferType.CASHBACK_PERCENT, offer_value=10.0,
            budget=1000.0, remaining_budget=1000.0, duration_days=30, status=CampaignStatus.ACTIVE,
            category=Category.DINING, marketing_copy="10% cash back at Olive Garden."
        )
    ]
    print("\n[4] Running Offer Ranking Agent (AG-006) for alice...")
    ranked = RankingAgent.rank_offers(customer, camps)
    for index, item in enumerate(ranked.ranked_offers):
        print(f"{index+1}. Campaign {item.campaign_id}: score {item.score}")
        print(f"   Explanation (AG-010): {item.user_explanation}")

if __name__ == "__main__":
    main()
