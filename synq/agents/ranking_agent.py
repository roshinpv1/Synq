import json
from typing import List, Dict, Any
from synq.agents.base import get_agent_llm, extract_json_block, convert_keys_to_snake_case, get_schema_prompt
from synq.agents.schemas import RankedOffers, RankedOfferItem
from synq.agents.insights_agent import InsightsAgent
from synq.models import Customer, Campaign

class RankingAgent:
    """AG-006 Offer Ranking Agent
    
    Evaluates campaign offers against a customer's affinity scores
    and preferences to sort them by relevancy.
    """
    
    @classmethod
    def rank_offers(
        cls, 
        customer: Customer, 
        campaigns: List[Campaign], 
        customer_lat: float = 37.7749, 
        customer_lon: float = -122.4194
    ) -> RankedOffers:
        llm = get_agent_llm(deep_think=False)
        
        # Serialize inputs for LLM
        campaigns_data = []
        for c in campaigns:
            campaigns_data.append({
                "campaign_id": c.campaign_id,
                "merchant": c.merchant_name,
                "category": c.category.value if hasattr(c.category, "value") else str(c.category),
                "offer_type": c.offer_type.value if hasattr(c.offer_type, "value") else str(c.offer_type),
                "offer_value": c.offer_value,
                "min_spend": c.min_spend,
                "copy": c.marketing_copy
            })

        affinities = {k.value if hasattr(k, "value") else str(k): v for k, v in customer.affinity_scores.items()}
        
        prompt = (
            f"You are the Synq Offer Ranking Agent (AG-006).\n"
            f"Rank the following campaigns for Customer ID {customer.customer_id}:\n"
            f"Customer Affinity Profile: {json.dumps(affinities, indent=2)}\n"
            f"Available Campaigns: {json.dumps(campaigns_data, indent=2)}\n\n"
            f"Sort these campaigns by relevance. Score each between 0.0 and 10.0.\n"
            f"For each ranked campaign, provide an internal reasoning and a customer-facing explanation (AG-010 style) explaining why they will like it (e.g. 'Since you love coffee...').\n"
            f"Your output must follow the RankedOffers schema."
        )
        
        if llm:
            try:
                if hasattr(llm, "with_structured_output"):
                    try:
                        structured_llm = llm.with_structured_output(RankedOffers)
                        return structured_llm.invoke(prompt)
                    except Exception:
                        pass # Fallback to manual text completion below
                
                # Manual JSON parsing fallback
                json_prompt = prompt + get_schema_prompt(RankedOffers)
                response = llm.invoke(json_prompt)
                content = response.content if hasattr(response, "content") else str(response)
                
                clean_content = extract_json_block(content)
                data = json.loads(clean_content)
                data = convert_keys_to_snake_case(data)
                return RankedOffers(**data)
            except Exception as e:
                import sys, traceback
                print(f"[DEBUG RankingAgent Exception] {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                
        # --- OFFLINE SIMULATOR FALLBACK ---
        ranked_items = []
        
        for c in campaigns:
            category_str = c.category.value if hasattr(c.category, "value") else str(c.category)
            # Find matching affinity
            affinity_score = 5.0  # Default
            for key, val in customer.affinity_scores.items():
                key_str = key.value if hasattr(key, "value") else str(key)
                if key_str.lower() == category_str.lower():
                    affinity_score = val
                    break

            # Calculate ranking score:
            # - Base is affinity score (0-10)
            # - Boost high value offers (+1 point for > 10% value)
            boost = 1.0 if c.offer_value >= 12.0 else 0.0
            
            # Distance simulation penalty
            # Simulate merchants have fixed locations. We compute distance to customer location.
            # (Just a mock distance boost: if within radius, add +0.5)
            dist_boost = 0.5 if c.campaign_id in ["c1", "c2"] else 0.0
            
            score = round(min(affinity_score + boost + dist_boost, 10.0), 1)
            
            # Generate reasoning
            internal_reason = (
                f"Affinity score for {category_str} is {affinity_score}. "
                f"Added offer value boost of {boost} and distance boost of {dist_boost}."
            )
            
            # Delegate customer explanation to InsightsAgent
            user_explanation = InsightsAgent.generate_explanation(
                customer_name=customer.name,
                merchant_name=c.merchant_name,
                category=category_str,
                affinity_score=affinity_score,
                offer_details=f"{c.offer_value}% cashback"
            )

            ranked_items.append(RankedOfferItem(
                campaign_id=c.campaign_id,
                score=score,
                reason_for_ranking=f"[OFFLINE RANKING] {internal_reason}",
                user_explanation=user_explanation
            ))

        # Sort descending by score
        ranked_items.sort(key=lambda x: x.score, reverse=True)

        return RankedOffers(
            customer_id=customer.customer_id,
            ranked_offers=ranked_items
        )
