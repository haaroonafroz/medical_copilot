from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from agents.state import AgentState
from config import settings
from tools.patient_records_tool import fetch_patient_record
from tools.clinical_tools import check_drug_interactions, calculate_cardiovascular_risk, summarize_patient_history

# Initialize LLM with Tools
tools = [check_drug_interactions, calculate_cardiovascular_risk, summarize_patient_history, fetch_patient_record]
llm = ChatOpenAI(model="gpt-4o", api_key=settings.OPENAI_API_KEY, temperature=0.1).bind_tools(tools)

def reasoning_node(state: AgentState):
    """
    Decides on the next step: either call a Clinical Tool or provide the final recommendation.
    """
    patient_data = state.get("patient_data")
    docs = state.get("retrieved_docs")
    messages = state["messages"]
    
    # Format docs for context
    context_str = "\n\n".join([f"Source: {d['source']}\n{d['content']}" for d in docs])
    
    # System Prompt with Instructions
    system_prompt = f"""
    You are an expert Clinical Decision Support Agent.
    
    === PATIENT DATA ===
    {patient_data}
    
    === CLINICAL GUIDELINES ===
    {context_str}
    
    === TASK ===
    1. Analyze the patient's condition.
    2. USE TOOLS if necessary:
       - If managing Hypertension/Lipids, calculate ASCVD Risk.
       - If proposing new medications, check for Drug Interactions.
       - If summarizing patient history, use the summarize_patient_history tool.
       - If fetching patient record, use the fetch_patient_record tool.
    3. If you have enough information, provide the final Assessment and Plan.
    
    RESPONSE FORMAT:
    - If using a tool: Just call the tool.
    - If finishing: Provide **Assessment**, **Plan**, and **Evidence**.
    """
    
    # Only add system prompt if it's not already in the history (to avoid duplication in loops)
    # A simple heuristic: check if the first message is a SystemMessage with "PATIENT DATA"
    # Or simpler: just invoke with context each time, but OpenAI handles history well.
    # For LangGraph, we usually append the system prompt to the list for the current invoke
    
    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    
    # Return the response (which might be a tool_call)
    return {
        "messages": [response]
    }