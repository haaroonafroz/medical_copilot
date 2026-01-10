from langgraph.prebuilt import ToolNode
from tools.clinical_tools import check_drug_interactions, calculate_cardiovascular_risk, summarize_patient_history
from tools.patient_records_tool import fetch_patient_record

tools = [check_drug_interactions, calculate_cardiovascular_risk, summarize_patient_history, fetch_patient_record]

tool_node = ToolNode(tools)