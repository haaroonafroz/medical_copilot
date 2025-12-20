import operator
from typing import Annotated, List, Dict, Optional, TypedDict, Union
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    The state of the agent as it moves through the graph.
    """
    # Chat history
    messages: Annotated[List[BaseMessage], operator.add]
    
    # Context variables
    patient_id: Optional[str]
    patient_data: Optional[str]  # Raw text from FHIR
    retrieved_docs: Optional[List[Dict]] # Results from Qdrant
    
    # Reasoning outputs
    initial_assessment: Optional[str]
    treatment_plan: Optional[str]
    critique: Optional[str]
    
    # Control flow
    confidence_score: float
    needs_revision: bool
