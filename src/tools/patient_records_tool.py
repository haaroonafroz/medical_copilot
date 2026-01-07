import requests
from typing import Dict, Any, List
from langchain_core.tools import tool
from config import settings

class FETCH_PATIENT_RECORDS:
    """
    Contains the functions to fetch patient record from the FHIR server.
    """
    
    def __init__(self):
        self.base_url = settings.FHIR_BASE_URL

    def get_patient_demographics(self, patient_id: str) -> str:
        """Fetches basic patient details."""
        # print("Tool called: get_patient_demographics")
        try:
            url = f"{self.base_url}/Patient/{patient_id}"
            # print(f"[MCP] Fetching: {url}") # Debugging
            resp = requests.get(url)
            if resp.status_code != 200:
                print(f"[Sub-tool: get_patient_demographics] Error {resp.status_code}: {resp.text}")
                return f"Error: Patient {patient_id} not found."
            
            data = resp.json()
            name_entry = data.get("name", [{}])[0]
            name = f"{name_entry.get('given', [''])[0]} {name_entry.get('family', '')}"
            return f"Patient Name: {name}\nGender: {data.get('gender')}\nDOB: {data.get('birthDate')}"
        except Exception as e:
            return f"Connection failed: {e}"

    def get_patient_labs(self, patient_id: str) -> str:
        """Fetches recent observations (labs/vitals) for the patient."""
        # print("Tool called: get_patient_labs")
        try:
            url = f"{self.base_url}/Observation?subject=Patient/{patient_id}"
            # print(f"[MCP] Fetching: {url}") # Debugging
            resp = requests.get(url)
            if resp.status_code != 200:
                print(f"[Sub-tool: get_patient_labs] Error {resp.status_code}: {resp.text}")
                return "No lab results found."
            
            bundle = resp.json()
            if "entry" not in bundle:
                return "No recent lab results."
            
            results = []
            for entry in bundle["entry"]:
                res = entry["resource"]
                code_text = res.get("code", {}).get("coding", [{}])[0].get("display", "Unknown Test")
                
                # Handle valueQuantity
                if "valueQuantity" in res:
                    val = f"{res['valueQuantity']['value']} {res['valueQuantity']['unit']}"
                # Handle component (BP often splits sys/dia)
                elif "component" in res:
                    components = []
                    for comp in res["component"]:
                        c_name = comp.get("code", {}).get("coding", [{}])[0].get("display", "")
                        c_val = f"{comp.get('valueQuantity', {}).get('value')} {comp.get('valueQuantity', {}).get('unit')}"
                        components.append(f"{c_name}: {c_val}")
                    val = ", ".join(components)
                else:
                    val = "Check Report"
                
                date = res.get("effectiveDateTime", "Unknown Date")
                results.append(f"- {date}: {code_text} = {val}")
                
            return "\n".join(results)
        except Exception as e:
            return f"Error fetching labs: {e}"

    def get_patient_medications(self, patient_id: str) -> str:
        """
        Fetches active medications from both MedicationStatement (reported) 
        and MedicationRequest (prescribed).
        """
        # print("Tool called: get_patient_medications")
        meds = []
        # 1. Search across two different FHIR resources to be thorough
        resources = ["MedicationStatement", "MedicationRequest"]
        
        for res_type in resources:
            try:
                # We filter by 'active' status to avoid showing old prescriptions
                url = f"{self.base_url}/{res_type}?subject=Patient/{patient_id}&status=active"
                # print(f"[MCP] Fetching: {url}") # Debugging
                resp = requests.get(url)
                
                if resp.status_code != 200:
                    print(f"[Sub-tool: get_patient_medications] Error {resp.status_code}: {resp.text}")
                    continue
                
                bundle = resp.json()
                if "entry" not in bundle:
                    print(f"[Sub-tool: get_patient_medications] No entries found in bundle")
                    continue

                for entry in bundle["entry"]:
                    res = entry["resource"]
                    name = "Unknown Medication"
                    
                    # Logic to handle both R4 and R5 naming conventions
                    # R4: medicationCodeableConcept | R5: medication.concept
                    med_concept = res.get("medicationCodeableConcept") or \
                                res.get("medication", {}).get("concept")
                    
                    if med_concept:
                        name = med_concept.get("coding", [{}])[0].get("display", "Unknown")
                    elif "medicationReference" in res:
                        name = res["medicationReference"].get("display", "Referenced Medication")
                    
                    meds.append(f"[{res_type}] {name}")
                    
            except Exception as e:
                print(f"[Sub-tool: get_patient_medications] Error fetching {res_type}: {e}")

        if not meds:
            return "No active medications found on file."
        
        return "Current Medications:\n" + "\n".join(list(set(meds))) # Set to remove duplicates

    def get_patient_conditions(self, patient_id: str) -> str:
        """Fetches active conditions/diagnoses."""
        # print("Tool called: get_patient_conditions")
        try:
            url = f"{self.base_url}/Condition?subject=Patient/{patient_id}"
            # print(f"[MCP] Fetching: {url}")
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                print(f"[Sub-tool: get_patient_conditions] Error {resp.status_code}: {resp.text}")
                return "No conditions found."
            
            bundle = resp.json()
            if "entry" not in bundle:
                print(f"[Sub-tool: get_patient_conditions] No entries found in bundle")
                return "No active conditions."
                
            conditions = []
            for entry in bundle["entry"]:
                res = entry["resource"]
                # Extract condition name
                code_text = res.get("code", {}).get("coding", [{}])[0].get("display", "Unknown Condition")
                status = res.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "unknown")
                conditions.append(f"- {code_text} ({status})")
                
            return "\n".join(conditions)
        except Exception as e:
            print(f"[Sub-tool: get_patient_conditions] Conditions failed: {e}")
            return f"Error fetching conditions: {e}"

    def get_patient_allergies(self, patient_id: str) -> str:
        """Fetches patient allergies/intolerances."""
        # print("Tool called: get_patient_allergies")
        try:
            url = f"{self.base_url}/AllergyIntolerance?patient=Patient/{patient_id}"
            # print(f"[MCP] Fetching: {url}")
            resp = requests.get(url, timeout=5)
            
            if resp.status_code != 200:
                return "No allergies on file."
            
            bundle = resp.json()
            if "entry" not in bundle:
                return "No known allergies."
                
            allergies = []
            for entry in bundle["entry"]:
                res = entry["resource"]
                substance = res.get("code", {}).get("coding", [{}])[0].get("display", "Unknown Substance")
                reaction = "Unknown reaction"
                # Try to find reaction manifestation
                if "reaction" in res and len(res["reaction"]) > 0:
                    manifest = res["reaction"][0].get("manifestation", [{}])[0].get("coding", [{}])[0].get("display")
                    if manifest: reaction = manifest
                
                allergies.append(f"- {substance}: {reaction}")
                
            return "\n".join(allergies)
        except Exception as e:
            print(f"[Sub-tool: get_patient_allergies] Allergies failed: {e}")
            return f"Error fetching allergies: {e}"

# Instantiate global MCP server
patient_records = FETCH_PATIENT_RECORDS()

# Define LangChain Tools
@tool
def fetch_patient_record(patient_id: str) -> str:
    """
    Retrieves the full clinical context for a patient ID.
    Includes Demographics, Recent Labs, Active Medications, Conditions, Allergies.
    Use this tool to gather information before reasoning.
    """
    print("Tool called: fetch_patient_record")
    demographics = patient_records.get_patient_demographics(patient_id)
    labs = patient_records.get_patient_labs(patient_id)
    meds = patient_records.get_patient_medications(patient_id)
    conditions = patient_records.get_patient_conditions(patient_id)
    allergies = patient_records.get_patient_allergies(patient_id)
    print("Tool called: fetch_patient_record - completed")
    return f"""
    === PATIENT RECORD: {patient_id} ===
   
    [DEMOGRAPHICS]
    {demographics}
    
    [RECENT LABS & VITALS]
    {labs}
    
    [CURRENT MEDICATIONS]
    {meds}

    [CONDITIONS]
    {conditions}

    [ALLERGIES]
    {allergies}

    ====================================
    """