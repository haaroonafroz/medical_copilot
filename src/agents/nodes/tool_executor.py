from langgraph.prebuilt import ToolNode
from tools.clinical_tools import check_drug_interactions, calculate_cardiovascular_risk, summarize_patient_history
from tools.patient_records_tool import fetch_patient_record

# We wrap our tools in a list
tools = [check_drug_interactions, calculate_cardiovascular_risk, summarize_patient_history, fetch_patient_record]

# LangGraph provides a prebuilt ToolNode that handles the heavy lifting
# (Executing the function, handling errors, formatting output as ToolMessage)
tool_node = ToolNode(tools)