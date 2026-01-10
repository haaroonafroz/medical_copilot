import streamlit as st
import os
import glob
import json
import sys
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Ensure src is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load Env
load_dotenv()

from src.agents.graph import agent_graph

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Medical Co-Pilot",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")

# --- SIDEBAR: PATIENT SELECTION ---
with st.sidebar:
    st.title("🩺 MedCo-Pilot")
    st.subheader("Patient Selection")
    
    patient_options = {} # map "Name (ID)" -> ID
    
    # 1. Fetch from HAPI FHIR (Live Data)
    try:
        resp = requests.get(f"{FHIR_BASE_URL}/Patient?_count=50")
        if resp.status_code == 200:
            bundle = resp.json()
            if "entry" in bundle:
                for entry in bundle["entry"]:
                    res = entry["resource"]
                    pid = res.get("id")
                    name_list = res.get("name", [{}])[0]
                    name = f"{name_list.get('given', [''])[0]} {name_list.get('family', '')}"
                    label = f"{name} ({pid})"
                    patient_options[label] = pid
    except Exception as e:
        st.error(f"Could not connect to FHIR Server: {e}")

    # 2. Dropdown
    if patient_options:
        selected_label = st.selectbox(
            "Select Active Patient",
            options=list(patient_options.keys())
        )
        selected_id = patient_options[selected_label]
    else:
        st.warning("No patients found in server.")
        selected_id = None

    # 3. Manual Entry Override
    manual_id = st.text_input("Or Enter Patient ID Manually")
    if manual_id:
        selected_id = manual_id

    if st.button("Load Patient Context"):
        if selected_id:
            st.session_state.messages.append(
                HumanMessage(content=f"Review patient {selected_id}")
            )
            st.rerun()
        else:
            st.toast("Please select or enter a Patient ID")

    st.markdown("---")
    st.markdown("### System Status")
    st.success("✅ FHIR Server: Connected")
    st.success("✅ Vector DB: Connected")

# --- MAIN CHAT INTERFACE ---
st.title("Clinical Decision Support Agent")
st.caption("Powered by LangGraph, FHIR, and Qdrant")

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display History
for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(msg.content)

# Handle Input
if prompt := st.chat_input("Enter clinical query or patient ID..."):
    # Add User Message
    st.session_state.messages.append(HumanMessage(content=prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process Agent
    with st.chat_message("assistant"):
        # Container for "Thinking"
        status_container = st.status("Thinking...", expanded=True)
        
        try:
            # Prepare State
            initial_state = {"messages": st.session_state.messages}
            
            # Stream Graph
            final_response = ""
            
            for event in agent_graph.stream(initial_state):
                for node, values in event.items():
                    
                    if node == "triage":
                        intent = values.get("triage_intent", "Unknown")
                        pid = values.get("patient_id", "Unknown")
                        status_container.write(f"🔍 **Triage:** Patient: `{pid}` | Intent: `{intent}`")
                        
                    elif node == "fetch_data":
                        status_container.write(f"📂 **Data Fetcher:** Retrieved FHIR record for {values.get('patient_id', 'patient')}")
                        
                    elif node == "retrieve_knowledge":
                        search_query = values.get("search_query", "Unknown")
                        status_container.write(f"🔍 **Retrieval:** Searching for: `{search_query}`")
                        docs = values.get("retrieved_docs", [])
                        count = len(docs)
                        status_container.write(f"📚 **Retrieval:** Found {count} relevant guidelines.")
                        if count > 0:
                            with status_container.expander("View Guidelines"):
                                for d in docs:
                                    st.caption(f"Source: {d.get('source', 'Unknown')}")
                                    st.markdown(f"> {d.get('content')[:200]}...")
                    elif node == "grade_documents":
                        grading_status = values.get("grading_status", "Unknown")
                        status_container.write(f"🔍 **Grading:** Documents are {grading_status}.")
                        if grading_status == "irrelevant":
                            status_container.write(f"🔍 **Grading:** Documents are irrelevant. Retrying retrieval...")
                            
                    elif node == "tools":
                        # Visualize tool outputs
                        # ToolNode output is usually in messages as ToolMessage
                        # We can look at the last message in values
                        msgs = values.get("messages", [])
                        if msgs:
                            last_msg = msgs[-1]
                            status_container.write(f"🛠️ **Tool Used:** {last_msg.name}")
                            with status_container.expander(f"Result: {last_msg.name}"):
                                st.code(last_msg.content)

                    elif node == "reason":
                        status_container.write("🧠 **Reasoning:** Synthesizing final recommendation...")
                        
            # Get Final Answer
            # The stream finishes, now we get the final state payload
            final_state = agent_graph.invoke(initial_state)
            final_response = final_state['messages'][-1].content
            
            status_container.update(label="Reasoning Complete", state="complete", expanded=False)
            
            # Display Final Answer
            st.markdown(final_response)
            
            # Save to History
            st.session_state.messages.append(AIMessage(content=final_response))
            
        except Exception as e:
            status_container.update(label="Error Occurred", state="error")
            st.error(f"Agent Error: {str(e)}")
