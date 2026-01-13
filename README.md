# Medical Co-Pilot: Agentic RAG for Clinical Decision Support

**An autonomous AI agent designed to assist healthcare providers by synthesizing patient-specific data with the latest medical research.**

---

##  1. The Real-World Problem: Clinical Burnout & Diagnostic Errors

In modern healthcare, doctors are overwhelmed by data. They must synthesize:
1.  **Electronic Health Records (EHR):** Scattered labs, notes, and medication lists.
2.  **Medical Literature:** Constantly changing clinical guidelines (e.g., Hypertension management).

This cognitive load leads to burnout and errors. The **Medical Co-Pilot** is not just a chatbot; it is an **Agentic System** that acts as a second pair of eyes. It uses an **Agentic RAG architecture** designed for accurate tool calling and strictly guideline-based advisory for cross-examining patients and flagging abnormalities. It doesn't just "chat"—it **thinks**, retrieves evidence, verifies patient history, and proposes a treatment plan for human review.

---

##  2. AI Architecture: Reasoning-First Design

This project moves beyond simple RAG (Retrieval-Augmented Generation) to **Agentic RAG**. It uses a graph-based orchestration engine to model the clinical decision-making process.

### The Agentic Flow (State Machine)
The agent is built on **LangGraph**, operating as a state machine with distinct cognitive steps (nodes):

1.  **Triage Node:**
    *   **Goal:** Understands the user's intent and extracts the unique Patient ID using structured output (Pydantic).
    *   *AI Logic:* "Is the user asking for a review? Which patient is this about?"

2.  **Patient Data Node (FHIR Tooling):**
    *   **Goal:** Connects to the **FHIR Server** (HAPI FHIR) via **LangChain Tools**.
    *   *AI Logic:* "I need the latest labs (BP, Lipid Panel), active conditions, and current medications for Patient X."
    *   *Tech:* Uses standardized tool calling to fetch real-time structured clinical data.

3.  **Knowledge Retrieval Node (Semantic Memory):**
    *   **Goal:** Searches the **Vector Database (Qdrant)** for relevant medical guidelines.
    *   *AI Logic:* "The patient has Hypertension. I need the 2025 JNC 8 or ACC/AHA guidelines for Stage 1 Hypertension treatment."
    *   *Tech:* Uses OpenAI Embeddings and Hybrid Search with metadata filtering.

4.  **Grader Node (Self-Correction Loop):**
    *   **Goal:** Evaluates if the retrieved documents actually answer the user's query.
    *   *AI Logic:* "Do these chunks talk about side effects? No? Refine search query and try again (up to 3 times)."

5.  **Reasoning Node (The "Brain"):**
    *   **Goal:** Synthesizes the *Patient Data* + *Medical Evidence* to form a recommendation.
    *   Can proactively use **Clinical Tools** before answering:
        *   **Risk Calculator:** Computes ASCVD 10-year risk for Statin/BP therapy decisions.
        *   **Interaction Checker:** Checks NIH RxNorm for dangerous drug-drug interactions.
    *   *AI Logic:* "Patient is on Lisinopril but BP is still 150/95. Guidelines suggest adding a Thiazide. Checking interaction between Lisinopril and Hydrochlorothiazide... Safe. Recommending addition."

6.  **Tool Executor Node (ReAct Loop):**
    *   **Goal:** Executes the deterministic tools requested by the Reasoning Node and loops the result back for final synthesis.

---

##  3. Technical Stack

*   **Orchestration:** `LangGraph` (Cyclic, stateful workflows).
*   **LLM:** `OpenAI GPT-4o-mini` (Clinical reasoning).
*   **Data Standard:** `HL7 FHIR` (via `fhir.resources` & HAPI FHIR Server).
*   **Vector Database:** `Qdrant` (Knowledge retrieval).
*   **Tooling:** `Langchain` tools with `@tool` decorator.
*   **Validation:** `Pydantic V2` (Strict schema validation).
*   **Infrastructure:** `Docker` (Containerized FHIR & Vector DB).
*   **Frontend:** `Streamlit` (Interactive Dashboard).

---

##  4. Getting Started

Follow these instructions to spin up the local environment.

### Prerequisites
*   **Docker Desktop** (running)
*   **Python 3.10+**

### Installation

1.  **Clone & Setup Environment**
    ```bash
    git clone <repo_url>
    cd medical_copilot
    python -m venv .venv
    source .venv/bin/activate  # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

2.  **Configure Environment Variables**
    *   Copy the example file:
        ```bash
        cp env.example .env
        ```
    *   Edit `.env` and add your `OPENAI_API_KEY`.
    *   *Note:* Ensure `FHIR_BASE_URL=http://localhost:8080/fhir` (HTTP, not HTTPS).

3.  **Start Infrastructure (Docker)**
    This spins up the HAPI FHIR Server (Patient Data) and Qdrant (Vector DB).
    ```bash
    docker-compose up -d
    ```
    *Wait ~30 seconds for the containers to initialize.*

### Data Seeding (The "Brain" Transplant)

Before the agent can reason, it needs knowledge and patients.

1.  **Ingest Medical Guidelines (Knowledge)**
    Loads a sample "Hypertension Management 2025" guideline into Qdrant.
    ```bash
    python scripts/ingest_docs.py
    ```

2.  **Seed Synthetic Patient (Context)**
    Loads a bulk dataset of 100+ synthetic patients (Synthea) into the local FHIR server.
    ```bash
    python scripts/seed_fhir.py
    ```

---

##  5. Usage

Interact with the agent via the UI.

1.  **Run the Streamlit App:**
    ```bash
    streamlit run src/app.py
    ```

2.  **Test Case:**
    *   Select a patient from the sidebar dropdown (auto-loaded from FHIR server).
    *   Click **"Load Patient Context"**.
    *   Watch the "Thinking" expander to see the agent Triage -> Fetch -> Retrieve -> Grade -> Reason.

3.  **Expected Output:**
    *   **Triage:** Identifies the ID.
    *   **Fetch:** Retrieves FHIR bundle.
    *   **Retrieve:** Finds relevant guidelines.
    *   **Tool Use:** Might calculate cardiovascular risk or check drug interactions.
    *   **Reason:** Outputs a structured Assessment & Plan.

---

##  6. Future Roadmap

*   **Observability:** Integrate **Arize Phoenix** to trace the "thought process" of the agent visually.
*   **Deterministic Safety:** Implement a `CDSRulesEngine` to hard-validate recommendations against contraindications (e.g., Allergy checks).
