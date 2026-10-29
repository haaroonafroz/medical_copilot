"""Safety and integration tests for the detached handoff workflow."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import HTTPException

from src.handoff.app import CreateRequest, ReviseRequest, SaveRequest, approve_handoff, create_handoff, his_form, revise_handoff, save_his_draft
from src.handoff.draft import build_draft, revise, unresolved
from src.handoff.fhir import FhirClient, FhirError
from src.handoff.fixtures import make_patient


@pytest.mark.parametrize("scenario,blocked", [
    ("complete", {"clinical_note"}),
    ("missing_followup", {"clinical_note", "follow_up"}),
    ("conflicting_medication", {"clinical_note", "medications"}),
])
def test_scenarios_block_until_clinician_resolves_missing_or_conflicting_fields(scenario, blocked):
    sample = make_patient(scenario)
    draft = build_draft(sample["resources"], sample["patient_id"])
    assert set(unresolved(draft)) == blocked
    assert draft["fields"]["patient_name"]["source"] == [f"Patient/{sample['patient_id']}"]


def test_patient_identity_cannot_be_switched_or_contaminated():
    sample = make_patient()
    draft = build_draft(sample["resources"], sample["patient_id"])
    with pytest.raises(ValueError, match="identity"):
        revise(draft, {"patient_id": "another-patient"})
    wrong = deepcopy(sample["resources"])
    wrong[1]["subject"]["reference"] = "Patient/someone-else"
    with pytest.raises(ValueError, match="different patient"):
        build_draft(wrong, sample["patient_id"])


def test_review_and_approval_gate_the_target_save():
    patient_id = make_patient()["patient_id"]
    created = create_handoff(CreateRequest(patient_id=patient_id))
    run_id = created["id"]
    values = {key: entry["value"] for key, entry in created["draft"]["fields"].items()}
    with pytest.raises(HTTPException) as blocked:
        approve_handoff(run_id)
    assert blocked.value.status_code == 409
    with pytest.raises(HTTPException) as blocked:
        save_his_draft(run_id, SaveRequest(values=values))
    assert blocked.value.status_code == 409
    revise_handoff(run_id, ReviseRequest(changes={"clinical_note": "Clinician reviewed and approved the discharge note."}))
    assert approve_handoff(run_id)["draft"]["approved"]
    values["clinical_note"] = "Clinician reviewed and approved the discharge note."
    with pytest.raises(HTTPException) as wrong:
        save_his_draft(run_id, SaveRequest(values={**values, "patient_id": "wrong"}))
    assert wrong.value.status_code == 422
    assert save_his_draft(run_id, SaveRequest(values=values))["saved"]
    page = his_form(run_id).body.decode()
    assert "Clinician reviewed and approved" in page
    assert "Final sign-off remains outside this demo workflow" in page


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
    def get(self, url, params=None, timeout=None):
        return FakeResponse(self.pages[url])


def test_fhir_search_follows_pages_and_rejects_foreign_links():
    base = "http://localhost:8080/fhir"
    first = f"{base}/Condition"
    next_page = f"{base}/Condition?_page=2"
    pages = {
        first: {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Condition", "id": "one"}}],
                "link": [{"relation": "next", "url": next_page}]},
        next_page: {"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Condition", "id": "two"}}]},
    }
    client = FhirClient(base, FakeSession(pages))
    assert [r["id"] for r in client._search("Condition", "subject", "demo")] == ["one", "two"]
    pages[first]["link"][0]["url"] = "https://unrelated.example/steal"
    with pytest.raises(FhirError, match="changed origin"):
        client._search("Condition", "subject", "demo")


def test_live_fhir_source_rejects_non_demo_or_replaced_patient(monkeypatch):
    from src.handoff import app as handoff_app

    monkeypatch.setattr(handoff_app, "FHIR_SOURCE", "live")
    with pytest.raises(HTTPException) as rejected:
        handoff_app._resources("real-patient-123")
    assert rejected.value.status_code == 404

    sample = make_patient()
    altered = deepcopy(sample["resources"])
    altered[0]["name"][0]["family"] = "Different"
    monkeypatch.setattr(FhirClient, "patient", lambda self, patient_id: altered)
    with pytest.raises(FhirError, match="synthetic case"):
        handoff_app._resources(sample["patient_id"])
