"""Optional full browser test against a running local handoff server.

Start uvicorn on localhost:8768, then set HANDOFF_E2E_URL=http://127.0.0.1:8768.
"""

from __future__ import annotations

import os

import pytest
import requests


BASE = os.getenv("HANDOFF_E2E_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="Set HANDOFF_E2E_URL for the browser integration test")


def request(method: str, path: str, **kwargs):
    response = requests.request(method, f"{BASE}{path}", timeout=45, **kwargs)
    response.raise_for_status()
    return response


def test_approved_discharge_draft_is_saved_and_verified_through_the_ui():
    patients = request("GET", "/api/patients").json()
    patient_id = next(item["id"] for item in patients if item["id"].startswith("demo-complete-"))
    run = request("POST", "/api/handoff", json={"patient_id": patient_id}).json()
    run_id = run["id"]
    note = "Synthetic test: clinician reviewed the discharge documentation."
    request("POST", f"/api/handoff/{run_id}/revise", json={"changes": {"clinical_note": note}})
    request("POST", f"/api/handoff/{run_id}/approve")
    result = request("POST", f"/api/handoff/{run_id}/execute").json()
    assert result["result"] == {"matched": 11, "total": 11, "mismatches": [], "verified": True}
    assert result["target"]["clinical_note"] == note
    assert result["target"]["patient_id"] == patient_id
    assert request("GET", f"/api/handoff/{run_id}/screenshot").headers["content-type"] == "image/png"
    kinds = [event["kind"] for event in result["events"]]
    assert kinds.index("approved") < kinds.index("cua_started") < kinds.index("verification")


def test_review_screen_exposes_all_evidence_and_gates_target_form():
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, executable_path=os.getenv("HANDOFF_CHROMIUM_EXECUTABLE") or None
        )
        try:
            page = browser.new_page()
            page.goto(BASE, wait_until="networkidle")
            assert page.locator("#target-card").is_hidden()
            page.get_by_role("button", name="Prepare handoff").click()
            page.locator("#sheet-fields").wait_for()
            assert len(page.locator("#session-id").inner_text()) == 32
            assert page.locator("#trace-note").inner_text().find("Sessions tab") >= 0
            assert page.locator("#target-card").is_hidden()
            observation = page.locator("#resource-list button", has_text="Observation/").first
            assert observation.is_visible()
            observation.click()
            assert '"resourceType": "Observation"' in page.locator("#source-json").inner_text()
            page.get_by_label("Clinician-approved note", exact=True).fill("Clinician reviewed the synthetic record.")
            page.get_by_role("button", name="Save edits").click()
            page.get_by_role("button", name="Approve for handoff").click()
            page.locator("#target-card").wait_for(state="visible")
            target_note = page.frame_locator("#target-frame").get_by_label("Clinician-approved note")
            expect(target_note).to_have_value("")
            page.get_by_role("button", name="Run scripted baseline").click()
            expect(page.locator("#verification")).to_contain_text("Verified 11/11")
            expect(target_note).to_have_value("Clinician reviewed the synthetic record.")
            assert page.get_by_role("link", name="View CUA screenshot").is_visible()
        finally:
            browser.close()


@pytest.mark.skipif(not os.getenv("HANDOFF_AI_E2E"), reason="Set HANDOFF_AI_E2E=1 for the paid GPT-6 Luna browser test")
def test_model_operator_pauses_for_ambiguous_destination_then_resumes_and_verifies():
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, executable_path=os.getenv("HANDOFF_CHROMIUM_EXECUTABLE") or None
        )
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(BASE, wait_until="networkidle")
            page.locator("#layout-select").select_option("ambiguous")
            page.get_by_role("button", name="Prepare handoff").click()
            page.get_by_label("Clinician-approved note", exact=True).fill("Synthetic note reviewed for the human pause check.")
            page.get_by_role("button", name="Save edits").click()
            page.get_by_role("button", name="Approve for handoff").click()
            page.get_by_role("button", name="Run AI Operator").click()
            expect(page.locator("#human-review")).to_be_visible(timeout=120000)
            expect(page.locator("#pause-reason")).to_contain_text("Route")
            expect(page.locator("#operator-frame")).to_be_visible()
            page.locator("#human-guidance").fill("Use Route B for the discharge follow-up plan.")
            page.get_by_role("button", name="Resume operator").click()
            expect(page.locator("#verification")).to_contain_text("Verified 11/11", timeout=180000)
            run_id = page.locator("#session-id").inner_text()
            run = request("GET", f"/api/handoff/{run_id}").json()
            assert run["cua_status"] == "verified"
            actions = [e["details"]["tool"] for e in run["events"] if e["kind"] == "model_decision"]
            assert "request_human" in actions
            assert "enter_dom" in actions
            assert run["result"]["matched"] == 11
        finally:
            browser.close()


@pytest.mark.skipif(not os.getenv("HANDOFF_AI_E2E"), reason="Set HANDOFF_AI_E2E=1 for the paid GPT-6 Luna browser test")
def test_model_operator_uses_screenshot_coordinates_for_unlabeled_field():
    import time

    patient_id = next(item["id"] for item in request("GET", "/api/patients").json() if item["scenario"] == "complete")
    run = request("POST", "/api/handoff", json={"patient_id": patient_id, "layout": "visual"}).json()
    run_id = run["id"]
    request("POST", f"/api/handoff/{run_id}/revise", json={"changes": {"clinical_note": "Synthetic reviewed note for visual test."}})
    request("POST", f"/api/handoff/{run_id}/approve")
    request("POST", f"/api/handoff/{run_id}/execute-model")
    for _ in range(90):
        run = request("GET", f"/api/handoff/{run_id}").json()
        if run["cua_status"] in {"verified", "failed", "paused"}:
            break
        time.sleep(2)
    assert run["cua_status"] == "verified", run.get("result") or run.get("cua_pause")
    assert run["result"]["matched"] == 11
    actions = [event["details"]["tool"] for event in run["events"] if event["kind"] == "model_decision"]
    assert "click_xy" in actions
    assert "type_text" in actions
