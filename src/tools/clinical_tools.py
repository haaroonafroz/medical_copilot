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

    # 1. Resolve drug names to RxCUIs
    for med in medications:
        try:
            resp = requests.get(
                "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                params={"name": med},
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()

            ids = data.get("idGroup", {}).get("rxnormId", [])
            if ids:
                rxcuis.append(ids[0])
            else:
                print(f"Could not resolve RxCUI for: {med}")

        except Exception as e:
            print(f"Error resolving {med}: {e}")

    if len(rxcuis) < 2:
        return (
            "Could not identify enough medications in RxNorm to check interactions. "
            "This may happen for brand names or uncommon drugs."
        )

    # 2. Check interactions
    try:
        url = "https://rxnav.nlm.nih.gov/REST/interaction/list.json"
        resp = requests.get(url, params={"rxcuis": "+".join(rxcuis)}, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        interactions = []

        for group in data.get("fullInteractionTypeGroup", []):
            for ftype in group.get("fullInteractionType", []):
                for pair in ftype.get("interactionPair", []):
                    desc = pair.get("description", "Interaction detected")
                    severity = pair.get("severity", "").lower()

                    if severity == "high":
                        interactions.append(f"HIGH SEVERITY: {desc}")

        if not interactions:
            return "No high-severity drug interactions found."

        return "\n".join(interactions)

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