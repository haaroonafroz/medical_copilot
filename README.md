# Medical Co-Pilot: Agentic RAG for Clinical Decision Support

**An autonomous AI agent designed to assist healthcare providers by synthesizing patient-specific data with the latest medical research.**

---

##  1. The Real-World Problem: Clinical Burnout & Diagnostic Errors

In modern healthcare, doctors are overwhelmed by data. They must synthesize:
1.  **Electronic Health Records (EHR):** Scattered labs, notes, and medication lists.
2.  **Medical Literature:** Constantly changing clinical guidelines (e.g., Hypertension management).

This cognitive load leads to burnout and errors. The **Medical Co-Pilot** is not just a chatbot; it is an **Agentic System** that acts as a second pair of eyes. It doesn't just "chat"—it **thinks**, retrieves evidence, verifies patient history, and proposes a treatment plan for human review.

---

##  2. AI Architecture: Reasoning-First Design

This project moves beyond simple RAG (Retrieval-Augmented Generation) to **Agentic RAG**. It uses a graph-based orchestration engine to model the clinical decision-making process.

### The Agentic Flow (State Machine)
The agent is built on **LangGraph**, operating as a state machine with distinct cognitive steps:

1.  **Triage Node:**
    *   **Goal:** Understands the user's intent and extracts the unique Patient ID using structured output (Pydantic).
    *   *AI Logic:* "Is the user asking for a review? Which patient is this about?"

2.  **Patient Data Node (MCP Standard):**
    *   **Goal:** Connects to the **FHIR Server** (HAPI FHIR) via the **Model Context Protocol (MCP)**.
    *   *AI Logic:* "I need the latest labs (BP, Lipid Panel), active conditions, and current medications for Patient X."
    *   *Tech:* Uses standardized tool calling to fetch real-time structured clinical data.

3.  **Knowledge Retrieval Node (Semantic Memory):**
    *   **Goal:** Searches the **Vector Database (Qdrant)** for relevant medical guidelines.
    *   *AI Logic:* "The patient has Hypertension. I need the 2025 JNC 8 or ACC/AHA guidelines for Stage 1 Hypertension treatment."
    *   *Tech:* Uses OpenAI Embeddings and Hybrid Search.

4.  **Reasoning Node (The "Brain"):**
    *   **Goal:** Synthesizes the *Patient Data* + *Medical Evidence* to form a recommendation.
    *   *AI Logic:* "Patient is on Lisinopril but BP is still 150/95. Guidelines suggest adding a Thiazide diuretic for this demographic. I will recommend this change."

5.  **Critique & Human-in-the-Loop (Safety):**
    *   **Goal:** Ensures safety before output.
    *   *AI Logic:* "Wait, does this new drug interact with their current allergy list?" (Future Implementation)

---

##  3. Technical Stack

*   **Orchestration:** `LangGraph` (Cyclic, stateful workflows).
*   **LLM:** `OpenAI GPT-4o-mini` (Clinical reasoning).
*   **Data Standard:** `HL7 FHIR` (via `fhir.resources` & HAPI FHIR Server).
*   **Vector Database:** `Qdrant` (Knowledge retrieval).
*   **Tooling:** `MCP` (Model Context Protocol) for standardized data access.
*   **Validation:** `Pydantic V2` (Strict schema validation).
*   **Infrastructure:** `Docker` (Containerized FHIR & Vector DB).

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
    Creates "John Doe" (ID: `test-patient-001`) in the FHIR server with:
    *   Condition: Hypertension
    *   Observation: BP 150/95 mmHg (Uncontrolled)
    *   Medication: Lisinopril 10mg
    ```bash
    python scripts/seed_fhir.py
    ```

---

##  5. Usage

Interact with the agent via the CLI.

1.  **Run the Agent:**
    ```bash
    python src/main.py
    ```

2.  **Test Case:**
    Type the following prompt when asked:
    > **"Review patient test-patient-001"**

3.  **Expected Output:**
    *   **Triage:** Identifies `test-patient-001`.
    *   **Fetch:** Retrieves John Doe's High BP (150/95) and Lisinopril.
    *   **Retrieve:** Finds the guideline saying "BP > 140/90 requires escalation."
    *   **Reason:** Recommends adding a second agent (e.g., Hydrochlorothiazide) citing the specific guideline.

---

##  6. Future Roadmap

*   **Streamlit UI:** Replace CLI with a chat interface displaying retrieved citations side-by-side.
*   **Observability:** Integrate **Arize Phoenix** to trace the "thought process" of the agent visually.
*   **Allergy Check:** Implement the `CritiqueNode` to auto-reject prescriptions that conflict with patient allergies.
