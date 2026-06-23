import os
import sys

# Add project root to python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synq.agents.base import get_agent_llm
from synq.agents.compliance_agent import ComplianceAgent

print("Running test_llm_connection...")
print("Environment variables:")
print("SYNQ_LLM_PROVIDER:", os.environ.get("SYNQ_LLM_PROVIDER"))
print("SYNQ_LLM_BACKEND_URL:", os.environ.get("SYNQ_LLM_BACKEND_URL"))
print("SYNQ_QUICK_THINK_LLM:", os.environ.get("SYNQ_QUICK_THINK_LLM"))
print("SYNQ_DEEP_THINK_LLM:", os.environ.get("SYNQ_DEEP_THINK_LLM"))

try:
    llm = get_agent_llm(deep_think=True)
    print("LLM client instance:", llm)
    if llm is None:
        print("LLM is None! (Probably key check failed or factory returned None)")
    else:
        print("Invoking LLM...")
        res = llm.invoke("Hello, say hello back in 5 words or less.")
        print("LLM response:", res)
except Exception as e:
    print("Error during get_agent_llm or invoke:", e)
    import traceback
    traceback.print_exc()

# Now test ComplianceAgent specifically
try:
    print("\nTesting ComplianceAgent.review_campaign...")
    review = ComplianceAgent.review_campaign(
        campaign_name="Nightlife Beer Bonanza",
        merchant_category="Dining",
        marketing_copy="Get unlimited cashback on beers and cocktails!",
        legal_disclosure="Spend anything."
    )
    print("Review result compliant:", review.is_compliant)
    print("Review flagged reasons:", review.flagged_reasons)
    print("Suggested copy edits:", review.suggested_copy_edits)
except Exception as e:
    print("Error running ComplianceAgent:")
    import traceback
    traceback.print_exc()

# Now test CampaignAgent specifically
try:
    print("\nTesting CampaignAgent.generate_proposal...")
    proposal = CampaignAgent.generate_proposal(
        merchant_name="Starbucks",
        category="Coffee",
        business_goal="Acquire new morning weekend coffee customers"
    )
    print("Proposal name:", proposal.campaign_name)
    print("Proposal marketing copy:", proposal.marketing_copy)
    print("Proposal reasoning:", proposal.reasoning)
except Exception as e:
    print("Error running CampaignAgent:")
    import traceback
    traceback.print_exc()

