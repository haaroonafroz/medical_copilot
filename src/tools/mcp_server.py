import requests
from typing import Dict, Any, List
from langchain_core.tools import tool
from config import settings

class MCPServer:
    """
    A simplified representation of an MCP Server that exposes FHIR data as tools.
    In a full MCP implementation, this would run as a separate process or service.
    Here we embed it directly for the Agent to use.
    """
    
    def __init__(self):
        self.base_url = settings.FHIR_BASE_URL

    def get_patient_demographics(self, patient_id: str) -> str:
        """Fetches basic patient details."""
        try:
            url = f"{self.base_url}/Patient/{patient_id}"
            resp = requests.get(url)
            if resp.status_code != 200:
                return f"Error: Patient {patient_id} not found."
            
            data = resp.json()
            name_entry = data.get("name", [{}])[0]
            name = f"{name_entry.get('given', [''])[0]} {name_entry.get('family', '')}"
            return f"Patient Name: {name}\nGender: {data.get('gender')}\nDOB: {data.get('birthDate')}"
        except Exception as e:
            return f"Connection failed: {e}"

    def get_patient_labs(self, patient_id: str) -> str:
        """Fetches recent observations (labs/vitals) for the patient."""
        try:
            url = f"{self.base_url}/Observation?subject=Patient/{patient_id}&_sort=-date&_count=5"
            resp = requests.get(url)
            if resp.status_code != 200:
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
        """Fetches active medications."""
        try:
            # Check MedicationStatement and MedicationRequest
            url = f"{self.base_url}/MedicationStatement?subject=Patient/{patient_id}&status=active"
            resp = requests.get(url)
            
            meds = []
            if resp.status_code == 200:
                bundle = resp.json()
                if "entry" in bundle:
                    for entry in bundle["entry"]:
                        res = entry["resource"]
                        med_name = res.get("medicationCodeableConcept", {}).get("coding", [{}])[0].get("display", "Unknown Med")
                        meds.append(f"- {med_name}")
            
            if not meds:
                return "No active medications found on file."
            
            return "Current Medications:\n" + "\n".join(meds)
        except Exception as e:
            return f"Error fetching meds: {e}"

# Instantiate global MCP server
mcp_server = MCPServer()

# Define LangChain Tools
@tool
def fetch_patient_record(patient_id: str) -> str:
    """
    Retrieves the full clinical context for a patient ID.
    Includes Demographics, Recent Labs, and Active Medications.
    Use this tool to gather information before reasoning.
    """
    demographics = mcp_server.get_patient_demographics(patient_id)
    labs = mcp_server.get_patient_labs(patient_id)
    meds = mcp_server.get_patient_medications(patient_id)
    
    return f"""
    === PATIENT RECORD: {patient_id} ===
    
    [DEMOGRAPHICS]
    {demographics}
    
    [RECENT LABS & VITALS]
    {labs}
    
    [CURRENT MEDICATIONS]
    {meds}
    ====================================
    """

