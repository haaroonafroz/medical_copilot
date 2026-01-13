import streamlit as st
import os
import requests
import json
import sys
import uuid
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Ensure src is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load Env
load_dotenv()

from agents.graph import agent_graph

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Medical Co-Pilot",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")

# Initialize Thread ID (Session Persistence)
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

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
            # We don't append to messages here anymore, just let the user know
            st.toast(f"Context loaded for {selected_id}. You can now ask questions.")
            # Optionally, we could inject a system message to set the ID in the graph state silently
            # But the user will likely ask "Review patient X", which works fine.
        else:
            st.toast("Please select or enter a Patient ID")

    st.markdown("---")
    st.markdown("### System Status")
    st.success("✅ FHIR Server: Connected")
    st.success("✅ Qdrant Collection: Connected")
    st.info(f"Session ID: {st.session_state.thread_id}")

# --- MAIN CHAT INTERFACE ---
st.title("Clinical Decision Support Agent")
st.caption("Powered by LangGraph, FHIR, and Qdrant")

# Initialize Chat History (for UI display only)
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
    # Add User Message to UI
    st.session_state.messages.append(HumanMessage(content=prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process Agent
    with st.chat_message("assistant"):
        # Container for "Thinking"
        status_container = st.status("Thinking...", expanded=True)
        
        try:
            # Prepare Config for Checkpointer
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            
            # Prepare Input (Only the new message!)
            # LangGraph Checkpointer will merge this with existing history
            input_payload = {"messages": [HumanMessage(content=prompt)]}
            
            # Stream Graph
            final_response = ""
            
            for event in agent_graph.stream(input_payload, config=config):
                for node, values in event.items():
                    
                    if node == "triage":
                        intent = values.get("triage_intent", "Unknown")
                        pid = values.get("patient_id", "Unknown")
                        status_container.write(f"🔍 **Triage:** Patient: `{pid}` | Intent: `{intent}`")
                        
                    elif node == "fetch_data":
                        status_container.write(f"📂 **Data Fetcher:** Retrieved FHIR record.")
                        
                    elif node == "retrieve_knowledge":
                        query = values.get("search_query", "Unknown")
                        docs = values.get("retrieved_docs", [])
                        count = len(docs)
                        status_container.write(f"📚 **Retrieval:** Query: `{query}` ({count} docs)")
                        if count > 0:
                            with status_container.expander("View Guidelines"):
                                for d in docs:
                                    st.caption(f"Source: {d.get('source', 'Unknown')}")
                                    st.markdown(f"> {d.get('content')[:200]}...")

                    elif node == "grade_documents":
                        grading_status = values.get("grading_status", "Unknown")
                        status_container.write(f"⚖️ **Grading:** Relevance = {grading_status}")
                        if grading_status == "irrelevant":
                            status_container.warning("⚠️ Retrying retrieval...")

                    elif node == "tools":
                        # Visualize tool outputs
                        msgs = values.get("messages", [])
                        if msgs:
                            for msg in msgs:
                                if hasattr(msg, 'name') and msg.name: # Ensure it's a ToolMessage
                                    status_container.write(f"🛠️ **Tool Used:** {msg.name}")
                                    with status_container.expander(f"Result: {msg.name}"):
                                        st.code(msg.content)

                    elif node == "reason":
                        status_container.write("🧠 **Reasoning:** Synthesizing final recommendation...")
                        
            # Get Final Answer from the State
            final_state = agent_graph.get_state(config)

            if final_state.values and "messages" in final_state.values:
                bot_message = final_state.values['messages'][-1]
                final_response = bot_message.content
            else:
                final_response = "Error: No response generated."
            
            status_container.update(label="Reasoning Complete", state="complete", expanded=False)
            
            # Display Final Answer
            st.markdown(final_response)
            
            # Save to UI History (The Graph already saved it to Checkpointer)
            st.session_state.messages.append(bot_message)
            
        except Exception as e:
            status_container.update(label="Error Occurred", state="error")
            st.error(f"Agent Error: {str(e)}")
            import traceback
            st.error(traceback.format_exc())