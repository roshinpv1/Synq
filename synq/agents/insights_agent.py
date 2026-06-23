from synq.agents.base import get_agent_llm

class InsightsAgent:
    """AG-010 Customer Insights Agent
    
    Generates personalized, friendly explanation strings for the consumer.
    Helps them understand why they are seeing specific merchant offers.
    """
    
    @staticmethod
    def generate_explanation(
        customer_name: str, 
        merchant_name: str, 
        category: str, 
        affinity_score: float, 
        offer_details: str
    ) -> str:
        llm = get_agent_llm(deep_think=False)
        
        prompt = (
            f"You are the Synq Customer Insights Agent (AG-010).\n"
            f"Write a friendly, single-sentence explanation for a customer named '{customer_name}' "
            f"explaining why we recommended a card-linked offer at '{merchant_name}' "
            f"({offer_details} under the '{category}' category).\n"
            f"The customer has an affinity score of {affinity_score}/10 in this category.\n"
            f"Make it warm, conversational, and direct (e.g. 'Since you enjoy dining out...'). Do not use generic placeholders."
        )
        
        if llm:
            try:
                response = llm.invoke(prompt)
                explanation = response.content if hasattr(response, "content") else str(response)
                return explanation.strip().strip('"')
            except Exception:
                pass
                
        # --- OFFLINE SIMULATOR FALLBACK ---
        cat = category.lower()
        if affinity_score >= 7.0:
            if "coffee" in cat:
                return f"Since you frequently visit coffee shops, save on your next morning run at {merchant_name}!"
            elif "din" in cat:
                return f"As a food lover, enjoy extra cashback on your next meal at {merchant_name}!"
            elif "retail" in cat or "shop" in cat:
                return f"Because you shop often, grab this exclusive card-linked reward at {merchant_name}!"
            elif "fit" in cat:
                return f"Since wellness is part of your daily routine, earn cashback on your next visit to {merchant_name}!"
            elif "travel" in cat:
                return f"As a frequent traveler, save on your next booking or commute at {merchant_name}!"
            else:
                return f"Since you frequently spend on {category}, we unlocked this special reward at {merchant_name}!"
        elif affinity_score >= 4.0:
            return f"Based on your interest in local {category} spots, we think you'll love {merchant_name}!"
        else:
            return f"Check out this popular deal from {merchant_name} in the {category} category!"
