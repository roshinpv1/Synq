import json
from typing import Dict, Any, List
from synq.agents.base import get_agent_llm, extract_json_block, convert_keys_to_snake_case, get_schema_prompt
from synq.agents.schemas import ComplianceReview

class ComplianceAgent:
    """AG-008 Compliance Agent
    
    Verifies that merchant campaigns follow standard banking regulations:
    - Flags restricted business categories (alcohol, gambling, cannabis, high-risk loans).
    - Checks for aggressive or deceptive marketing copy.
    - Ensures standard legal disclosures are provided.
    """
    
    RESTRICTED_WORDS = {
        "gambling": ["casino", "gambling", "poker", "betting", "blackjack", "slots", "lottery"],
        "alcohol": ["alcohol", "beer", "wine", "whiskey", "bar", "brewery", "liquor", "cocktails"],
        "restricted_substances": ["cannabis", "marijuana", "weed", "vape", "tobacco", "cigarettes"],
        "deceptive_claims": ["guaranteed win", "free cash", "no risk", "earn millions", "risk-free double"]
    }

    @classmethod
    def review_campaign(
        cls, 
        campaign_name: str, 
        merchant_category: str, 
        marketing_copy: str, 
        legal_disclosure: str
    ) -> ComplianceReview:
        llm = get_agent_llm(deep_think=True)
        
        prompt = (
            f"You are the Synq Compliance Agent (AG-008).\n"
            f"Review this merchant campaign for banking marketing compliance:\n"
            f"Campaign Name: {campaign_name}\n"
            f"Merchant Category: {merchant_category}\n"
            f"Marketing Copy: {marketing_copy}\n"
            f"Legal Disclosure: {legal_disclosure}\n\n"
            f"Check if it targets any restricted banking industries (e.g. alcohol, gambling, adult content, drug/cannabis products, financial speculation).\n"
            f"Check if the marketing copy uses misleading words or promises. Ensure disclosure contains clear minimum spend and max cashback limits.\n"
            f"Your output must follow the ComplianceReview schema."
        )
        
        if llm:
            try:
                if hasattr(llm, "with_structured_output"):
                    try:
                        structured_llm = llm.with_structured_output(ComplianceReview)
                        return structured_llm.invoke(prompt)
                    except Exception:
                        pass # Fallback to manual text completion below
                
                # Manual JSON parsing fallback
                json_prompt = prompt + get_schema_prompt(ComplianceReview)
                response = llm.invoke(json_prompt)
                content = response.content if hasattr(response, "content") else str(response)
                
                clean_content = extract_json_block(content)
                data = json.loads(clean_content)
                data = convert_keys_to_snake_case(data)
                return ComplianceReview(**data)
            except Exception:
                pass
                
        # --- OFFLINE SIMULATOR FALLBACK ---
        is_compliant = True
        flagged_reasons = []
        restricted_found = []
        disclosures_required = []
        suggested_copy = marketing_copy

        content_to_check = (campaign_name + " " + merchant_category + " " + marketing_copy).lower()
        
        # 1. Restricted Industry Check
        for category, words in cls.RESTRICTED_WORDS.items():
            for word in words:
                if word in content_to_check:
                    is_compliant = False
                    if word not in flagged_reasons:
                        flagged_reasons.append(f"Contains restricted term: '{word}' (Industry: {category.upper()})")
                        if category not in restricted_found:
                            restricted_found.append(category)

        # Special check for alcohol/breweries since community banks do allow dining but flag direct alcohol-only promotions
        if "brewery" in content_to_check or "bar" in content_to_check:
            is_compliant = False
            flagged_reasons.append("Card-linked rewards cannot directly promote alcohol or bar-only spend under community bank guidelines.")
            suggested_copy = marketing_copy.replace("beer", "food").replace("drinks", "dining").replace("cocktails", "appetizers")

        # 2. Deceptive Marketing Copy Check
        for claim in cls.RESTRICTED_WORDS["deceptive_claims"]:
            if claim in content_to_check:
                is_compliant = False
                flagged_reasons.append(f"Deceptive marketing claim detected: '{claim}'. Banking rewards cannot imply guaranteed financial returns.")
                suggested_copy = suggested_copy.replace(claim, "rewards cashback")

        # 3. Disclosure Check
        disc_lower = legal_disclosure.lower()
        if "min" not in disc_lower and "spend" not in disc_lower:
            disclosures_required.append("Must state minimum transaction threshold or write 'No minimum spend required'.")
        if "max" not in disc_lower and "cap" not in disc_lower and "limit" not in disc_lower:
            disclosures_required.append("Must clarify maximum cashback cap per transaction.")

        if disclosures_required:
            is_compliant = False
            flagged_reasons.append(f"Missing mandatory regulatory disclosures: {', '.join(disclosures_required)}")

        return ComplianceReview(
            is_compliant=is_compliant,
            flagged_reasons=flagged_reasons,
            restricted_categories_found=restricted_found,
            disclosures_required=disclosures_required,
            suggested_copy_edits=suggested_copy if not is_compliant else ""
        )
