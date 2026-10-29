"""Repeatable FHIR R4 examples for the handoff demo.

These invented people and records are deliberately small enough to inspect by eye.
The scenario argument creates meaningful missing/conflicting-data cases for evals.
"""

from __future__ import annotations

from datetime import date
from random import Random


SCENARIOS = ("complete", "missing_followup", "conflicting_medication")


def make_patient(scenario: str = "complete", seed: int = 7) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    rng = Random(seed)
    patient_id = f"demo-{scenario.replace("_", "-")}-{seed}"
    given, family = rng.choice((('Mira', 'Winter'), ('Jonas', 'Falk'), ('Lea', 'Berger')))
    resources = [
        {"resourceType": "Patient", "id": patient_id,
         "name": [{"given": [given], "family": family}], "birthDate": "1962-04-18",
         "gender": "female" if given in ("Mira", "Lea") else "male"},
        {"resourceType": "Encounter", "id": f"{patient_id}-encounter", "status": "finished",
         "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
         "subject": {"reference": f"Patient/{patient_id}"},
         "period": {"start": "2026-10-20T09:00:00+02:00", "end": "2026-10-27T14:00:00+01:00"},
         "hospitalization": {"dischargeDisposition": {"text": "Home with outpatient follow-up"}}},
        {"resourceType": "Condition", "id": f"{patient_id}-condition", "subject": {"reference": f"Patient/{patient_id}"},
         "clinicalStatus": {"coding": [{"code": "active"}]},
         "code": {"coding": [{"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"}]}},
        {"resourceType": "MedicationStatement", "id": f"{patient_id}-medication", "status": "active",
         "subject": {"reference": f"Patient/{patient_id}"},
         "medicationCodeableConcept": {"text": "Lisinopril 10 mg daily"}},
        {"resourceType": "AllergyIntolerance", "id": f"{patient_id}-allergy", "patient": {"reference": f"Patient/{patient_id}"},
         "code": {"text": "Penicillin"}, "reaction": [{"manifestation": [{"text": "Rash"}]}]},
        {"resourceType": "Observation", "id": f"{patient_id}-bp", "status": "final",
         "subject": {"reference": f"Patient/{patient_id}"},
         "code": {"text": "Blood pressure"}, "effectiveDateTime": "2026-10-26T10:00:00+01:00",
         "component": [
             {"code": {"text": "Systolic"}, "valueQuantity": {"value": 132, "unit": "mmHg"}},
             {"code": {"text": "Diastolic"}, "valueQuantity": {"value": 82, "unit": "mmHg"}},
         ]},
        {"resourceType": "CarePlan", "id": f"{patient_id}-careplan", "status": "active", "intent": "plan",
         "subject": {"reference": f"Patient/{patient_id}"},
         "description": "Primary care follow-up within 7 days"},
    ]
    if scenario == "missing_followup":
        resources = [r for r in resources if r["resourceType"] != "CarePlan"]
    if scenario == "conflicting_medication":
        resources.append({"resourceType": "MedicationRequest", "id": f"{patient_id}-request", "status": "active", "intent": "order",
                          "subject": {"reference": f"Patient/{patient_id}"},
                          "medicationCodeableConcept": {"text": "Lisinopril 20 mg daily"}})
    return {"patient_id": patient_id, "scenario": scenario, "seed": seed,
            "generated_on": date(2026, 10, 28).isoformat(), "resources": resources}
