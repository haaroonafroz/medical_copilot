# Synthetic discharge handoff lab

This standalone workflow sits beside the LangGraph medical copilot. It reads synthetic FHIR R4 records, prepares an evidence-linked discharge sheet, requires clinician review, and transfers approved values into a local mock hospital system. The main UI now uses a **model-directed browser operator** powered by `gpt-6-luna`. The earlier scripted Playwright adapter remains available through **Run scripted baseline** on the standard layout and `POST /api/handoff/{run_id}/execute` for comparison.

## Run

Use Python 3.12, Docker, and a configured `OPENAI_API_KEY` in the project `.env` file or process environment. The operator sends only the invented demo records and screenshots to the model API. It makes paid API requests; keep real patient information out of this lab.

```bash
python -m venv .venv-handoff
source .venv-handoff/bin/activate
pip install -r requirements-handoff.txt
python -m playwright install chromium
docker compose up -d hapi-fhir phoenix
python scripts/seed_handoff.py
HANDOFF_FHIR_SOURCE=live uvicorn src.handoff.app:app --host 127.0.0.1 --port 8768
```

Open `http://127.0.0.1:8768` and Phoenix at `http://127.0.0.1:6006`. To avoid Docker FHIR, start with `HANDOFF_FHIR_SOURCE=fixture`. The model path still needs Playwright Chromium and an API key. If Chromium is installed elsewhere, set `HANDOFF_CHROMIUM_EXECUTABLE`.

## Demo walkthrough

1. Select **Complete discharge record** and a mock HIS challenge. Prepare the handoff. Inspect source chips, enter a clinician-authored synthetic note, save edits, and approve.
2. Click **Run AI Operator**. Its own Chromium browser opens the mock HIS. The page shows the latest browser screenshot, the chosen model actions, and a saved-form preview. The operator receives the exact approved values, a compact visible DOM summary, and a fresh screenshot. It chooses DOM refs or screenshot coordinates and drives Playwright mouse and keyboard actions. The target is accessed only through the rendered browser UI.
3. Try **Tabbed form** to see the model navigate a changed layout. Try **Ambiguous destination** to see the model request human guidance between Route A and Route B. Answer “Use Route B for the discharge plan.” Try **Visual label challenge** to see a field that has a visible caption but no accessible DOM label; the model must use screenshot coordinates to focus it. The app rejects any text outside the approved packet and blocks Save draft until every field matches.
4. If the model calls `request_human`, the run pauses with its browser still open. Read the reason and screenshot, enter guidance, and click **Resume operator**, or cancel. A patient identity mismatch stops the run automatically. Final clinical sign-off remains manual and is not available to the operator.
5. After Save draft, the app reloads the target page and compares all 11 persisted values to the clinician-approved packet. A green verified result requires 11/11 matches. A mismatch or error is recorded as a failed run; a bounded second save attempt is available when the model can recover.
6. Open Phoenix's `medical-copilot` project, then **Sessions** and find the run ID displayed in the demo. Expand `handoff.model_cua_run` to see `cua.model_decision` LLM spans, the chosen tools and short reasons, action spans, and verification. Those LLM spans contain the synthetic model prompt and tool call output plus token counts. The older generic HTTP root spans in Phoenix may still show blank Turns input/output; inspect child spans in Traces.

The three source cases are complete, missing follow-up, and conflicting medication. The last two block approval until a clinician resolves them. The **Transient save error** target rejects the first save and allows the second, so the operator can demonstrate UI error recovery. The target challenge is a separate choice, so you can combine a source case with any UI layout.

## Architecture and limits

`src/handoff/draft.py` maps FHIR resources to 11 fields and source references. `src/handoff/model_cua.py` owns the bounded GPT-6 Luna Responses API loop and browser driver. `src/handoff/app.py` owns the approval gate, model task, human pause/resume API, and mock HIS. `src/handoff/store.py` holds short-lived run state, events, and browser frames in process memory. Phoenix groups traces using the run ID.

The model context starts with the approved field packet and source references, then adds the current compact DOM, screenshot, and each tool result through the Responses conversation ID. Its Chromium browser stays alive across model turns and human pauses. The run store retains only this run's draft, events, frames, and outcome; there is no cross-patient or long-term agent memory.

The model receives only an approved value packet and current UI observation. It cannot write directly to the mock HIS backing store, change patient ID, type unapproved clinical text, or perform final sign-off. Browser operations are restricted to localhost and a maximum number of model turns. The mock HIS and its persistence are local training code, not a real KIS, Citrix, or Windows environment. The browser tool uses Playwright mouse and keyboard within Chromium; a VM/desktop driver would be needed for native hospital applications. This lab is synthetic and must not be used with patient data.

## Checks

```bash
pytest tests/test_handoff.py -q
HANDOFF_E2E_URL=http://127.0.0.1:8768 pytest tests/test_handoff_browser.py -q
HANDOFF_E2E_URL=http://127.0.0.1:8768 HANDOFF_AI_E2E=1 pytest tests/test_handoff_browser.py -q -k model_operator
python scripts/evaluate_handoff.py
```

The default browser test covers the scripted baseline. The optional paid GPT-6 Luna browser test covers screenshot-coordinate entry as well as a model-selected human pause, resume, and verified save because model decisions and API availability can vary. Successful model runs should show an LLM span, at least one browser action, and 11/11 post-save matches.
