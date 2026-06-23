import json
from typing import Dict, Any
from synq.agents.base import get_agent_llm, extract_json_block, convert_keys_to_snake_case, get_schema_prompt
from synq.agents.schemas import CampaignProposal

class CampaignAgent:
    """AG-001 Merchant Campaign Agent
    
    Generates promotional campaign proposals based on merchant category and business goals.
    """
    
    @staticmethod
    def generate_proposal(merchant_name: str, category: str, business_goal: str, historical_performance: str = "") -> CampaignProposal:
        llm = get_agent_llm(deep_think=True)
        
        prompt = (
            f"You are the Synq Merchant Campaign Agent (AG-001).\n"
            f"Analyze the merchant profile and generate a campaign proposal:\n"
            f"Merchant Name: {merchant_name}\n"
            f"Category: {category}\n"
            f"Business Goal: {business_goal}\n"
            f"Historical Performance notes: {historical_performance}\n\n"
            f"Suggest a suitable campaign structure including campaign name, budget, suggested duration (days), "
            f"cashback offer value (percentage, e.g. 10.0 for 10% cash back), target audience segments, "
            f"high-conversion marketing copy, and standard legal disclosure.\n"
            f"Your output must follow the CampaignProposal schema structure."
        )
        
        if llm:
            try:
                # Use structured output bindings if supported
                if hasattr(llm, "with_structured_output"):
                    try:
                        structured_llm = llm.with_structured_output(CampaignProposal)
                        return structured_llm.invoke(prompt)
                    except Exception:
                        pass # Fallback to manual text completion below
                
                # Manual JSON parsing fallback (essential for local models/LM Studio)
                json_prompt = prompt + get_schema_prompt(CampaignProposal)
                response = llm.invoke(json_prompt)
                content = response.content if hasattr(response, "content") else str(response)
                
                clean_content = extract_json_block(content)
                data = json.loads(clean_content)
                data = convert_keys_to_snake_case(data)
                return CampaignProposal(**data)
            except Exception as e:
                import sys, traceback
                print(f"[DEBUG CampaignAgent Exception] {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                
        # --- OFFLINE SIMULATOR FALLBACK ---
        # Generate high-fidelity category-based suggestions
        category_lower = category.lower()
        
        if "coffee" in category_lower:
            name = "Morning Brew Boost"
            value = 15.0
            budget = 500.0
            duration = 14
            segments = ["Coffee Buyers", "Local Radius"]
            copy = f"Start your morning right at {merchant_name}! Get 15% cashback on your favorite coffee and breakfast items when you pay with your linked card."
            disclosure = "Valid on debit card transactions. Minimum spend $5. Max cashback $3 per transaction."
            reason = "Coffee shops thrive on high frequency. A 15% offer attracts repeat morning visits to increase weekly transaction counts."
        elif "din" in category_lower or "food" in category_lower or "rest" in category_lower:
            name = "Weekend Feast Rewards"
            value = 10.0
            budget = 1200.0
            duration = 30
            segments = ["Frequent Diners", "High Spenders"]
            copy = f"Dine and save at {merchant_name}! Enjoy a delicious meal and get 10% cashback credited instantly to your bank account."
            disclosure = "Valid on credit card transactions. Minimum spend $25. Max cashback $10 per bill."
            reason = "Restaurants benefit from higher ticket sizes. The $25 minimum spend encourages ordering appetizers/desserts."
        elif "retail" in category_lower or "shop" in category_lower:
            name = "Seasonal Style Cash Back"
            value = 8.0
            budget = 2000.0
            duration = 21
            segments = ["High Spenders", "Competitor Spenders"]
            copy = f"Upgrade your wardrobe at {merchant_name}! Get 8% cashback on all apparel and accessories this weekend."
            disclosure = "Valid on linked card purchases. Minimum spend $50. Max cashback $20."
            reason = "Retail campaigns with moderate rates (8%) and higher budget scales target competitive fashion spenders."
        elif "fit" in category_lower or "gym" in category_lower:
            name = "Active Lifestyle Rewards"
            value = 12.0
            budget = 800.0
            duration = 30
            segments = ["Rewards Customers", "Local Radius"]
            copy = f"Invest in your health at {merchant_name}! Get 12% cashback on memberships, class packs, and merchandise."
            disclosure = "Valid on credit card transactions. Minimum spend $30. Max cashback $15."
            reason = "Fitness centers benefit from subscription/package sales. A 12% offer increases card links for recurring membership billing."
        else:
            name = "Synq Welcome Special"
            value = 10.0
            budget = 1000.0
            duration = 30
            segments = ["Local Radius", "Rewards Customers"]
            copy = f"Welcome to {merchant_name}! Activate this card-linked offer to get 10% cashback on your next purchase."
            disclosure = "Valid on all linked bank card transactions. Max cashback $10."
            reason = "Generic 10% introductory cashback to establish merchant network engagement."
            
        if "repeat" in business_goal.lower():
            name = "Loyalty Loop Cashback"
            reason += " Modified to optimize for repeat business by offering slightly higher rewards with a lower minimum spend."
        elif "acquire" in business_goal.lower():
            name = "New Customer Welcome"
            segments.append("Competitor Spenders")
            reason += " Adjusted to target competitor spenders to drive new foot traffic."
            
        return CampaignProposal(
            campaign_name=name,
            suggested_budget=budget,
            suggested_duration_days=duration,
            offer_value=value,
            target_segments=segments,
            marketing_copy=copy,
            suggested_legal_disclosure=disclosure,
            reasoning=f"[OFFLINE SIMULATION] {reason}"
        )
