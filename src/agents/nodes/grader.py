# src/agents/nodes/grader.py
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
# from langchain_core.pydantic_v1 import BaseModel, Field
from src.agents.state import AgentState
from src.config import settings

# Structured Output for Grading
class Grade(BaseModel):
    # score: int = Field(description="The score of the relevance of the retrieved documents to the user's query on a scale of 0 to 100.")
    is_relevant: bool = Field(description="True if the retrieved documents contain information relevant to the user's query.")
    feedback: str = Field(description="If irrelevant, explain what is missing to guide the next search.")

llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0)
grader_llm = llm.with_structured_output(Grade)

def grader_node(state: AgentState):
    """
    Evaluates if the retrieved documents are relevant to the user's intent.
    """
    user_intent = state.get("triage_intent", "")
    docs = state.get("retrieved_docs", [])
    
    # If no docs, obviously irrelevant
    if not docs:
        return {
            "grading_status": "irrelevant",
            "messages": [SystemMessage(content="Grader: No documents found.")]
        }

    # Format context
    context = "\n\n".join([d.get("content", "")[:500] for d in docs])
    
    prompt = f"""
    You are a Medical Research Evaluator.
    
    USER INTENT: "{user_intent}"
    
    RETRIEVED KNOWLEDGE:
    {context}
    
    TASK:
    Determine if the retrieved knowledge is sufficient to answer the user's intent.
    Example: If the docs talk about "Hypertension treatment" and the user asked about "Side effects", and side effects are mentioned, it is RELEVANT.
    If the docs are completely unrelated (e.g. Diabetes docs for a COPD question), it is IRRELEVANT.
    Return the relevance status and feedback in the following JSON format:
    {{
        "is_relevant": <is_relevant>,
        "feedback": <feedback if irrelevant>
    }}
    """
    
    try:
        grade = grader_llm.invoke([SystemMessage(content=prompt)])
        status = "relevant" if grade.is_relevant else "irrelevant"
        feedback = grade.feedback
    except Exception as e:
        print(f"Grader Error: {e}")
        status = "relevant" # Fallback to avoid infinite loops on error
        feedback = "Error in grading."

    print(f"--- Grading: {status.upper()} ({feedback}) ---")

    return {
        "grading_status": status,
        "messages": [SystemMessage(content=f"Grader: Documents are {status}. Feedback: {feedback}")]
    }