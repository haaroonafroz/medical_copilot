# Project Requirements Document: **Medical Co-Pilot**

**Subtitle:** *An Agentic RAG System for Clinical Decision Support using LangGraph, MCP, and Qdrant.*

---

## 1. Project Overview & Mission

The **Clinical Co-Pilot** is an autonomous AI agent designed to assist healthcare providers by synthesizing patient-specific data with the latest medical research. Its mission is to reduce clinical burnout and minimize diagnostic errors by providing "evidence-based reasoning" at the point of care.

Unlike a standard chatbot, this agent uses **Agentic RAG**, meaning it can decide whether it needs more information, verify its own findings, and pause for human validation before finalizing a recommendation.

---

## 2. Core Objectives

* **Contextual Synthesis:** Seamlessly merge "static" medical guidelines (Qdrant) with "dynamic" patient records (FHIR via MCP).
* **Reasoning-First Architecture:** Move beyond simple search to "Thinking" via LangGraph cycles (Reflect → Grade → Refine).
* **Trust & Transparency:** Provide full traceability of every decision via Arize Phoenix and cited medical literature.

---

## 3. Data Strategy

To maintain a professional standard without using sensitive data, this project utilizes **Synthetic Clinical Data**.

| Data Category | Source | Description |
| --- | --- | --- |
| **Electronic Health Records (EHR)** | [Synthea](https://synthetichealth.github.io/synthea/) | Realistic, synthetic JSON patient files (History, Meds, Labs). |
| **Medical Knowledge Base** | [PubMed](https://pubmed.ncbi.nlm.nih.gov/) / [Merck Manuals](https://www.merckmanuals.com/) | Academic abstracts and clinical treatment protocols for vectorization. |
| **Standardized Format** | **HL7 FHIR** | All patient data is structured using the global FHIR standard to ensure interoperability. |

---

## 4. Technical Stack & Libraries

This stack is curated to represent the "2025 Market Leader" profile.

* **Orchestration:** `LangGraph` (for stateful, cyclic multi-step workflows).
* **LLM (The Brain):** `OpenAI GPT-4o` (for complex medical reasoning).
* **Vector Database:** `Qdrant Client` (utilizing **Hybrid Search** and **Payload Filtering**).
* **Tooling Standard:** `Model Context Protocol (MCP)` (used to build the FHIR Data Server).
* **Observability & Eval:** `Arize Phoenix` (Tracing) + `RAGAS` (Context Precision/Recall metrics).
* **Validation:** `Pydantic v2` (strict data modeling for clinical safety).

---

## 5. System Architecture & Agentic Flow

The agent operates as a **State Machine** with the following nodes:

1. **Triage Node:** Analyzes the user query and the Patient ID.
2. **Patient Data Node (MCP):** Fetches the latest lab results/medications from the FHIR server.
3. **Knowledge Retrieval Node (Qdrant):** Performs a semantic search for treatment guidelines related to the patient's symptoms.
4. **Critique Node:** A separate LLM prompt that checks: *"Does the guideline conflict with the patient's existing medications or allergies?"*
5. **Human-in-the-Loop (HITL) Node:** The agent pauses. It presents its "Draft Recommendation" to the doctor for approval.

---

## 6. Competitive Advantages (The "Job-Winners")

### 🛡️ A. Compliance & Security Note (HIPAA-Ready)

> **Note:** While this project uses synthetic data, the architecture is **"HIPAA-Compliant by Design."**
> * **Data Minimization:** The agent only retrieves fields necessary for the current reasoning task.
> * **Audit Trails:** Every span and trace is logged in Arize Phoenix, providing a permanent record of how the AI reached its conclusion—essential for medical legalities.
> * **De-identification:** The MCP layer can be configured to strip PII (Personally Identifiable Information) before sending data to the OpenAI API.
> 
> 

### 👤 B. The "Human-in-the-Loop" (HITL) Element

This is your most important feature. In healthcare, an agent must **never** act autonomously without a license.

* **Implementation:** You will use LangGraph’s `breakpoint` feature.
* **Workflow:** The agent calculates a "Confidence Score." If the score is below 90% or the recommendation involves a medication change, the agent enters a `__wait__` state.
* **UI:** The dashboard (Streamlit/Next.js) will display an **"Approve / Edit / Reject"** interface, allowing the doctor to overwrite the AI’s logic.

---

## 7. Success Metrics (Evaluation)

To prove to recruiters that the agent works, you will report the following via **Arize Phoenix**:

* **Faithfulness:** 0.0 to 1.0 (Ensuring the agent doesn't hallucinate medical advice).
* **Context Relevancy:** (Ensuring Qdrant is retrieving the *correct* medical papers).
* **Tool Call Accuracy:** (Ensuring the agent calls the MCP server correctly every time).

---

## 8. Example repository structure
```
    medical_copilot(cwd)/
    ├── data/
    │   ├── raw_guidelines/       # PDF/Markdown medical docs
    │   └── synthetic_patients/   # JSON FHIR bundles from Synthea
    ├── src/
    │   ├── agents/
    │   │   ├── state.py          # TypedDict defining the AgentState
    │   │   ├── graph.py          # LangGraph workflow definition
    │   │   └── nodes/            # Logic for specific steps (e.g., triage, retrieval)
    │   ├── tools/
    │   │   ├── mcp_server.py     # MCP server connecting to FHIR
    │   │   └── vector_store.py   # Qdrant retrieval logic
    │   └── main.py               # Entry point (Streamlit or CLI)
    ├── scripts/
    │   ├── ingest_docs.py        # Script to embed guidelines into Qdrant
    │   └── seed_fhir.py          # Script to upload Synthea data to HAPI FHIR
    ├── docker-compose.yml        # To spin up Qdrant and HAPI FHIR locally
    ├── .env.example              # API keys and DB URLs
    └── requirements.txt
```