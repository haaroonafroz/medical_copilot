import requests
from typing import List, Dict
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from config import settings

# Initialize LLM for summarization
llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)

# --- Tool 1: Drug Interaction Checker (NIH API) ---
@tool
def check_drug_interactions(medications: List[str]) -> str:
    """
    Checks for high-severity drug-drug interactions using the NIH RxNorm API.
    Input: List of drug names (e.g., ['Lisinopril', 'Aspirin']).
    """
    print("Tool called: check_drug_interactions")

    if len(medications) < 2:
        return "No interaction check needed (less than 2 drugs)."

    rxcuis = []

    # 1. Resolve drug names to RxCUIs using the correct endpoint
    for med in medications:
        try:
            # Use the approximate match endpoint for better results
            resp = requests.get(
                "https://rxnav.nlm.nih.gov/REST/approximateTerm.json",
                params={"term": med, "maxEntries": 1},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Extract RxCUI from candidate list
            candidates = data.get("approximateGroup", {}).get("candidate")
            if candidates and len(candidates) > 0:
                rxcui = candidates[0].get("rxcui")
                if rxcui:
                    rxcuis.append(rxcui)
                    print(f"Resolved {med} to RxCUI: {rxcui}")
                else:
                    print(f"Could not resolve RxCUI for: {med}")
            else:
                print(f"No candidates found for: {med}")

        except requests.exceptions.RequestException as e:
            print(f"Network error resolving {med}: {e}")
        except Exception as e:
            print(f"Error resolving {med}: {e}")

    if len(rxcuis) < 2:
        return (
            "Could not identify enough medications in RxNorm to check interactions. "
            "This may happen for brand names or uncommon drugs. "
            f"Resolved {len(rxcuis)} out of {len(medications)} medications."
        )

    # 2. Check interactions between all pairs
    try:
        # Format: separate rxcui parameters (not joined with +)
        url = "https://rxnav.nlm.nih.gov/REST/interaction/list.json"
        params = {"rxcuis": " ".join(rxcuis)}  # Space-separated, not +
        
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        interactions = []
        
        # Navigate the response structure correctly
        full_interaction_groups = data.get("fullInteractionTypeGroup", [])
        
        if not full_interaction_groups:
            return "No drug interactions found in RxNorm database."
        
        for group in full_interaction_groups:
            for interaction_type in group.get("fullInteractionType", []):
                for pair in interaction_type.get("interactionPair", []):
                    desc = pair.get("description", "Interaction detected")
                    severity = pair.get("severity", "unknown").lower()
                    
                    # Get interacting drugs info
                    drug1 = pair.get("interactionConcept", [{}])[0].get("minConceptItem", {}).get("name", "Drug 1")
                    drug2 = pair.get("interactionConcept", [{}])[1].get("minConceptItem", {}).get("name", "Drug 2") if len(pair.get("interactionConcept", [])) > 1 else "Drug 2"
                    
                    # Filter by severity if needed
                    if severity in ["high", "contraindicated"]:
                        interactions.append(f"⚠️ {severity.upper()}: {drug1} + {drug2}\n   {desc}")
                    else:
                        # Still report other severities for transparency
                        interactions.append(f"• {severity.upper()}: {drug1} + {drug2}\n   {desc}")

        if not interactions:
            return "No significant drug interactions found."

        return "\n\n".join(interactions[:10])  # Limit to first 10 to avoid overflow

    except requests.exceptions.RequestException as e:
        return f"Network error while checking drug interactions: {e}"
    except KeyError as e:
        return f"Error parsing interaction data (API response structure may have changed): {e}"
    except Exception as e:
        return f"Error while checking drug interactions: {e}"

# --- Tool 2: Risk Calculator (Simplified ASCVD) ---
@tool
def calculate_cardiovascular_risk(age: int, systolic_bp: int, smoker: bool, diabetic: bool) -> str:
    """
    Calculates the 10-year ASCVD risk score (Simplified estimate).
    Useful for determining if Statin or Hypertension therapy is needed.
    """
    print("Tool called: calculate_cardiovascular_risk")
    # Simplified Logic (Real ASCVD is a complex regression equation)
    # Base risk starts low
    risk_score = 1.0
    
    # Age factor
    if age > 40: risk_score += (age - 40) * 0.2
    
    # BP factor
    if systolic_bp > 120: risk_score += (systolic_bp - 120) * 0.1
    
    # Comorbidities
    if smoker: risk_score *= 1.5
    if diabetic: risk_score *= 1.8
    
    # Cap at 100%
    risk_score = min(risk_score, 100.0)
    
    category = "Low Risk"
    if risk_score >= 7.5: category = "Elevated Risk (Consider Statin)"
    if risk_score >= 20.0: category = "High Risk"

    print(f"10-Year ASCVD Risk Estimate: {risk_score:.1f}% ({category})")
    return f"10-Year ASCVD Risk Estimate: {risk_score:.1f}% ({category})"

# --- Tool 3: History Summarizer ---
@tool
def summarize_patient_history(clinical_notes: List[str]) -> str:
    """
    Summarizes a list of clinical notes/encounters into a concise HPI (History of Present Illness).
    """
    print("Tool called: summarize_patient_history")
    if not clinical_notes:
        return "No notes available to summarize."
        
    combined_text = "\n---\n".join(clinical_notes[:5]) # Limit to last 5 notes
    
    prompt = f"""
    Summarize the following clinical history into a 3-bullet point 'History of Present Illness' (HPI).
    Focus on chronic conditions, recent hospitalizations, and major procedures.
    
    NOTES:
    {combined_text}
    """
    
    response = llm.invoke(prompt)
    return response.content