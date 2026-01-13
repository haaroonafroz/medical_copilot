from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.nodes.triage import triage_node
from agents.nodes.data_fetcher import data_fetcher_node
from agents.nodes.retrieval import retrieval_node
from agents.nodes.reasoning import reasoning_node
from agents.nodes.tool_executor import tool_node
from agents.nodes.grader import grader_node
from langgraph.checkpoint.memory import MemorySaver

def build_graph():
    """
    Constructs the ReAct Agent Workflow.
    """
    workflow = StateGraph(AgentState)

    # 1. Add Nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("fetch_data", data_fetcher_node)
    workflow.add_node("retrieve_knowledge", retrieval_node)
    workflow.add_node("grade_documents", grader_node)
    workflow.add_node("reason", reasoning_node)
    workflow.add_node("tools", tool_node)

    # 2. Add Edges (Control Flow)
    workflow.set_entry_point("triage")

    # Conditional logic: If we have a patient ID, fetch data. Else, if we have data in state, skip fetch. Else, stop and ask.
    def check_patient_id(state: AgentState):
        patient_id = state.get("patient_id")
        patient_data = state.get("patient_data")
        
        if patient_data:
            print("--- Data already in state, skipping fetch ---")
            return "retrieve_knowledge" # Optimization: Skip fetch_data
            
        if patient_id:
            return "fetch_data"
            
        return END

    workflow.add_conditional_edges(
        "triage",
        check_patient_id,
        {
            "fetch_data": "fetch_data",
            "retrieve_knowledge": "retrieve_knowledge",
            END: END
        }
    )

    workflow.add_edge("fetch_data", "retrieve_knowledge")
    workflow.add_edge("retrieve_knowledge", "grade_documents")
    
    # Conditional logic: If documents are irrelevant, retry retrieval. Else, proceed to reasoning.
    def check_grade(state: AgentState):
        status = state.get("grading_status")
        retries = state.get("retrieval_retries", 0)
        
        if status == "irrelevant" and retries < 3:
            return "retrieve_knowledge" # Loop back
        return "reason" # Proceed

    # Conditional edges for grading and retrying retrieval if necessary.
    workflow.add_conditional_edges(
        "grade_documents",
        check_grade,
        {
            "retrieve_knowledge": "retrieve_knowledge",
            "reason": "reason"
        }
    )
    
    def check_tool_calls(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges(
        "reason",
        check_tool_calls,
        {
            "tools": "tools",
            END: END
        }
    )

    workflow.add_edge("tools", "reason")

    # Initialiaze checkpointer
    memory = MemorySaver()
    # 3. Compile
    return workflow.compile(checkpointer=memory)

# Global instance
agent_graph = build_graph()