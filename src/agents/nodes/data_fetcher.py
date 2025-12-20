from agents.state import AgentState
from tools.mcp_server import fetch_patient_record

def data_fetcher_node(state: AgentState):
    """
    Fetches patient data from the FHIR server using the MCP tool.
    """
    patient_id = state.get("patient_id")
    
    if not patient_id:
        return {
            "messages": [
                {"role": "assistant", "content": "I need a Patient ID to proceed. Please provide one."}
            ]
        }
        
    print(f"--- Fetching FHIR Data for {patient_id} ---")
    try:
        # Call the tool directly
        patient_data = fetch_patient_record.invoke(patient_id)
    except Exception as e:
        patient_data = f"Error fetching data: {e}"

    return {
        "patient_data": patient_data,
        "messages": [{"role": "tool", "content": f"Fetched data for {patient_id}"}]
    }

