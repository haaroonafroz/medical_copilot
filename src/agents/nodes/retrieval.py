from agents.state import AgentState
from tools.vector_store import VectorStore

def retrieval_node(state: AgentState):
    """
    Queries Qdrant for medical guidelines based on the patient's condition.
    """
    patient_data = state.get("patient_data", "")
    
    # 1. Generate a search query from patient data (simplification)
    # Ideally, use an LLM to formulate a query based on the 'Problem List'
    query = "hypertension treatment guidelines" 
    if "Hypertension" in patient_data or "Blood pressure" in patient_data:
        query = "Hypertension management guidelines adult"
    
    print(f"--- Retrieving Guidelines for query: '{query}' ---")
    
    try:
        vector_store = VectorStore()
        results = vector_store.search(query)
    except Exception as e:
        print(f"Vector Store Error: {e}")
        results = []

    return {
        "retrieved_docs": results,
        "messages": [{"role": "system", "content": f"Retrieved {len(results)} guidelines."}]
    }

