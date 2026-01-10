from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from typing import Optional
from agents.state import AgentState
from config import settings

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0)

class TriageOutput(BaseModel):
    patient_id: Optional[str] = Field(description="The alphanumeric Patient ID extracted from the user query (e.g., 'test-patient-001').")
    intent: str = Field(description="A concise summary of the clinical question or request.")
    missing_info: bool = Field(description="True if the user query is too vague and requires clarification.")


def triage_node(state: AgentState):
    """
    Analyzes the latest user message to extract the Patient ID 
    and understand the clinical intent using structured output.
    """
    last_message = state['messages'][-1]
    
   # Context about available tools to help the agent understand what's possible
    tools_context = """
    You are a Clinical Triage Bot for a Medical Co-Pilot system.
    
    Your Capabilities:
    1. Retrieve comprehensive Patient Records (Demographics, Labs, Meds, Conditions, Allergies) via FHIR.
    2. Search Clinical Guidelines (Vector DB) for evidence-based treatment protocols.
    3. Use tools for comprehensive assessment and treatment planning (e.g., ASCVD risk calculator, drug interaction checker, history summarizer).
    
    Your Job:
    - Analyze the user's query.
    - Extract the specific Patient ID if provided.
    - Summarize the user's clinical intent (e.g., "Review hypertension therapy", "Check for drug interactions").
    - If no Patient ID is found but the query implies a specific patient, mark 'missing_info' as True.
    """
   
   # Bind the structured output model to the LLM
    structured_llm = llm.with_structured_output(TriageOutput)
    
    try:
        # Invoke with system instructions + user query
        result = structured_llm.invoke([
            SystemMessage(content=tools_context),
            last_message
        ])
        
        patient_id = result.patient_id
        intent = result.intent
        
        # Log the triage result for debugging
        print(f"--- Triage Complete: ID={patient_id}, Intent={intent} ---")
        
        # Create a message to store the intent in history
        triage_msg = SystemMessage(content=f"Triage Analysis: Intent='{intent}'. Patient ID='{patient_id}'")

    except Exception as e:
        # Fallback if structured output fails
        print(f"Triage Error: {e}")
        patient_id = None
        triage_msg = SystemMessage(content="Error during triage analysis.")

    # Return updates to the state
    return {
        "patient_id": patient_id if patient_id else state.get('patient_id'),
        "triage_intent": intent,
        "messages": [triage_msg] 
    }