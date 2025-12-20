from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from agents.state import AgentState
from config import settings

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0)

def triage_node(state: AgentState):
    """
    Analyzes the latest user message to extract the Patient ID 
    and understand the clinical intent.
    """
    last_message = state['messages'][-1]
    
    # Simple extraction logic (in production, use structured output/function calling)
    prompt = f"""
    You are a Clinical Triage Bot. 
    Analyze the following user query: "{last_message.content}"
    
    1. Extract the Patient ID if present.
    2. Summarize the clinical question.
    
    Return the result in this format:
    PATIENT_ID: <id>
    INTENT: <summary>
    """
    
    response = llm.invoke([SystemMessage(content=prompt)])
    content = response.content
    
    patient_id = None
    if "PATIENT_ID:" in content:
        try:
            patient_id = content.split("PATIENT_ID:")[1].split("\n")[0].strip()
        except:
            pass

    # If we found a patient ID, store it in state
    return {
        "patient_id": patient_id if patient_id else state.get('patient_id'),
        "messages": [response] # Append the triage thought process
    }

