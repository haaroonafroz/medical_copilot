from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from agents.state import AgentState
from config import settings

llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.1)

def reasoning_node(state: AgentState):
    """
    Synthesizes Patient Data + Guidelines to form a recommendation.
    """
    patient_data = state.get("patient_data")
    docs = state.get("retrieved_docs")
    
    # Format docs
    context_str = "\n\n".join([f"Source: {d['source']}\n{d['content']}" for d in docs])
    
    prompt = f"""
    You are an expert Clinical Decision Support Agent.
    
    Your Goal: Provide an evidence-based treatment recommendation.
    
    === PATIENT DATA ===
    {patient_data}
    
    === CLINICAL GUIDELINES ===
    {context_str}
    
    === INSTRUCTIONS ===
    1. Analyze the patient's current condition and medications.
    2. Check if the current treatment aligns with the guidelines.
    3. Recommend any changes (start, stop, or adjust medications).
    4. Cite the specific guideline that supports your decision.
    
    Response Format:
    - **Assessment**: ...
    - **Plan**: ...
    - **Evidence**: ...
    """
    
    response = llm.invoke([SystemMessage(content=prompt)])
    
    return {
        "treatment_plan": response.content,
        "messages": [response]
    }

