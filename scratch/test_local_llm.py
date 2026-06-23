import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from synq.default_config import DEFAULT_CONFIG
from synq.llm_clients.factory import create_llm_client

def test_connection():
    provider = "openai_compatible"
    model = "llama-3.2-3b-instruct"
    base_url = "http://localhost:1234/v1"
    
    client = create_llm_client(provider=provider, model=model, base_url=base_url)
    llm = client.get_llm()
    
    prompt = (
        "You are the Synq Merchant Campaign Agent (AG-001).\n"
        "Generate a campaign proposal for:\n"
        "Merchant Name: Starbucks\n"
        "Category: Coffee\n"
        "Business Goal: Acquire new coffee customers\n\n"
        "You must return ONLY a JSON object with these exact keys:\n"
        "- campaign_name (string)\n"
        "- suggested_budget (float/number)\n"
        "- suggested_duration_days (integer)\n"
        "- offer_value (float/number, e.g. 15.0)\n"
        "- target_segments (list of strings)\n"
        "- marketing_copy (string)\n"
        "- suggested_legal_disclosure (string)\n"
        "- reasoning (string)\n\n"
        "Do not write any introductory or concluding conversational text. Return the JSON wrapped in ```json ... ```"
    )
    
    print("Sending prompt to local LLM...")
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    print("\n--- RAW LLM RESPONSE ---")
    print(content)
    print("------------------------\n")
    
    # Try parsing
    try:
        clean_content = content
        if "```json" in content:
            clean_content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            clean_content = content.split("```")[1].split("```")[0].strip()
        
        data = json.loads(clean_content)
        print("Successfully parsed raw string as JSON!")
        print(f"Keys found: {list(data.keys())}")
        
        from synq.agents.schemas import CampaignProposal
        proposal = CampaignProposal(**data)
        print("Successfully validated JSON against CampaignProposal Pydantic model!")
        print(proposal)
    except Exception as e:
        print(f"Error parsing/validating: {e}")

if __name__ == "__main__":
    test_connection()
