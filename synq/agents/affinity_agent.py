import json
from typing import List, Dict, Any
from synq.agents.base import get_agent_llm, extract_json_block, convert_keys_to_snake_case, get_schema_prompt
from synq.agents.schemas import CustomerAffinityProfile, CategoryAffinity
from synq.models import Customer, Category

class AffinityAgent:
    """AG-003 Customer Affinity Agent
    
    Computes a customer's affinity scores across various spend categories
    based on their historical card transaction frequency and volume.
    """
    
    @classmethod
    def calculate_affinities(
        cls, 
        customer_id: str, 
        transactions_data: List[Dict[str, Any]], 
        demographics: Dict[str, Any] = None, 
        location: Dict[str, Any] = None
    ) -> CustomerAffinityProfile:
        llm = get_agent_llm(deep_think=False)
        
        # Serialize transactions for LLM context
        tx_summary = []
        for tx in transactions_data:
            tx_summary.append({
                "merchant": tx.get("merchant_name"),
                "category": tx.get("category"),
                "amount": tx.get("amount")
            })
            
        prompt = (
            f"You are the Synq Customer Affinity Agent (AG-003).\n"
            f"Analyze the following transactions for Customer ID {customer_id}:\n"
            f"{json.dumps(tx_summary, indent=2)}\n\n"
        )
        if demographics:
            prompt += f"Customer Demographics (strictly confidential, bank-only): {json.dumps(demographics)}\n"
        if location:
            prompt += f"Customer Home Location (strictly confidential, bank-only): {json.dumps(location)}\n"
            
        category_list = ", ".join([cat.value for cat in Category])
        prompt += (
            f"\nCalculate the customer's affinity score (0.0 to 10.0) for the categories: {category_list}.\n"
            f"Leverage both the transaction patterns and the demographic/location details to refine the scoring (e.g. higher travel affinity score for higher income brackets or users located near specific hubs, or dining habits mapped to demographic trends, while ensuring transaction history remains the primary source of truth).\n"
            f"Write a short, data-backed reasoning for each category.\n"
            f"Identify the single highest affinity category as the dominant_segment.\n"
            f"Your output must follow the CustomerAffinityProfile schema."
        )
        
        if llm:
            try:
                if hasattr(llm, "with_structured_output"):
                    try:
                        structured_llm = llm.with_structured_output(CustomerAffinityProfile)
                        return structured_llm.invoke(prompt)
                    except Exception:
                        pass # Fallback to manual text completion below
                
                # Manual JSON parsing fallback
                json_prompt = prompt + get_schema_prompt(CustomerAffinityProfile)
                response = llm.invoke(json_prompt)
                content = response.content if hasattr(response, "content") else str(response)
                
                clean_content = extract_json_block(content)
                data = json.loads(clean_content)
                data = convert_keys_to_snake_case(data)
                return CustomerAffinityProfile(**data)
            except Exception as e:
                import sys, traceback
                print(f"[DEBUG AffinityAgent Exception] {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                
        # --- OFFLINE SIMULATOR FALLBACK ---
        # Calculate mathematically from transaction records
        counts = {cat.value: 0 for cat in Category}
        totals = {cat.value: 0.0 for cat in Category}
        
        for tx in transactions_data:
            cat = tx.get("category")
            # Convert string to Category Enum value if needed
            cat_val = cat.value if isinstance(cat, Category) else str(cat)
            if cat_val in counts:
                counts[cat_val] += 1
                totals[cat_val] += float(tx.get("amount", 0))

        affinities = []
        highest_score = -1.0
        dominant_segment = "General Spender"

        for cat in Category:
            cat_val = cat.value
            cnt = counts[cat_val]
            tot = totals[cat_val]
            
            # Simple scoring algorithm:
            # - Frequency weight (up to 5 points, 1 point per transaction up to 5)
            # - Volume weight (up to 5 points, 1 point per $20 spent up to $100)
            freq_score = min(cnt * 1.0, 5.0)
            vol_score = min(tot / 20.0, 5.0)
            score = round(freq_score + vol_score, 1)
            
            # Apply demographic private adjustments:
            demographic_notes = []
            if demographics:
                # High income boost for Travel and Dining
                if demographics.get("income_bracket") == "High" and cat_val in ["Travel", "Dining"]:
                    score = min(score + 0.8, 10.0)
                    demographic_notes.append("High income tier adjustment")
                # Younger age group boost for Coffee and Fitness
                age_val = demographics.get("age")
                if age_val and age_val < 30 and cat_val in ["Coffee", "Fitness"]:
                    score = min(score + 0.6, 10.0)
                    demographic_notes.append("Younger age affinity boost")

            # Ensure a base baseline score of 1.0 for active customers
            if cnt > 0 and score < 1.0:
                score = 1.0
            elif cnt == 0:
                # Add base baseline plus demographic baseline adjustment
                if demographics and demographics.get("income_bracket") == "High" and cat_val in ["Travel", "Dining"]:
                    score = 1.8
                elif demographics and demographics.get("age") and demographics.get("age") < 30 and cat_val in ["Coffee", "Fitness"]:
                    score = 1.6
                else:
                    score = 1.0  # Base level

            # Write data-backed explanation
            notes_str = f" ({', '.join(demographic_notes)} applied)" if demographic_notes else ""
            if cnt > 0:
                reason = f"Customer made {cnt} purchase(s) in this category totaling ${tot:.2f}.{notes_str} "
                if score >= 7.0:
                    reason += "Indicates very strong spending loyalty."
                elif score >= 4.0:
                    reason += "Indicates moderate spending interest."
                else:
                    reason += "Indicates minor spending presence."
            else:
                if demographic_notes:
                    reason = f"No transactions recorded in this category. Baseline adjusted via demographics:{notes_str}."
                else:
                    reason = "No transactions recorded in this category. Baseline affinity assigned."

            affinities.append(CategoryAffinity(
                category=cat_val,
                score=score,
                reasoning=f"[OFFLINE ANALYSIS] {reason}"
            ))

            if score > highest_score:
                highest_score = score
                dominant_segment = f"{cat_val} Enthusiast"

        if highest_score <= 1.0:
            dominant_segment = "New Account"

        return CustomerAffinityProfile(
            customer_id=customer_id,
            affinities=affinities,
            dominant_segment=dominant_segment
        )
