"""Deterministic field mapping from FHIR resources to a reviewable discharge sheet."""

from __future__ import annotations

from datetime import datetime
from typing import Any


FIELD_LABELS = {
    "patient_id": "Patient ID",
    "patient_name": "Patient name",
    "birth_date": "Date of birth",
    "admitted": "Admission date",
    "discharged": "Discharge date",
    "disposition": "Discharge disposition",
    "diagnoses": "Diagnoses",
    "medications": "Current medications",
    "allergies": "Allergies",
    "follow_up": "Follow-up plan",
    "clinical_note": "Clinician-approved note",
}

REQUIRED = set(FIELD_LABELS)


def _text(concept: dict | None) -> str:
    concept = concept or {}
    return str(concept.get("text") or next((c.get("display") for c in concept.get("coding", []) if c.get("display")), "") or "")


def _day(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def _field(value: str, source: list[str], status: str = "ready", reason: str = "") -> dict:
    return {"value": value, "source": source, "status": status, "reason": reason}


def build_draft(resources: list[dict], patient_id: str) -> dict[str, Any]:
    patient = next((r for r in resources if r.get("resourceType") == "Patient" and r.get("id") == patient_id), None)
    if patient is None:
        raise ValueError("Patient resource is missing or does not match the selected patient")
    for resource in resources:
        if resource is patient:
            continue
        reference = (resource.get("subject") or resource.get("patient") or {}).get("reference")
        if reference != f"Patient/{patient_id}":
            raise ValueError(f"Resource {resource.get('id')} belongs to a different patient")

    by_type: dict[str, list[dict]] = {}
    for resource in resources:
        by_type.setdefault(resource.get("resourceType", ""), []).append(resource)

    def refs(items: list[dict]) -> list[str]:
        return [f"{r['resourceType']}/{r['id']}" for r in items if r.get("id")]

    fields: dict[str, dict] = {}
    fields["patient_id"] = _field(patient_id, refs([patient]))
    name = (patient.get("name") or [{}])[0]
    full_name = " ".join([*(name.get("given") or []), name.get("family") or ""]).strip()
    fields["patient_name"] = _field(full_name, refs([patient]), "ready" if full_name else "missing")
    birth_date = patient.get("birthDate") or ""
    fields["birth_date"] = _field(birth_date, refs([patient]), "ready" if birth_date else "missing")

    encounters = sorted(by_type.get("Encounter", []), key=lambda r: (r.get("period") or {}).get("end") or "", reverse=True)
    encounter = encounters[0] if encounters else None
    encounter_refs = refs([encounter]) if encounter else []
    period = (encounter or {}).get("period") or {}
    for key, raw in (("admitted", period.get("start")), ("discharged", period.get("end"))):
        value = _day(raw)
        fields[key] = _field(value, encounter_refs, "ready" if value else "missing")
    disposition = _text(((encounter or {}).get("hospitalization") or {}).get("dischargeDisposition"))
    fields["disposition"] = _field(disposition, encounter_refs, "ready" if disposition else "missing")

    conditions = [r for r in by_type.get("Condition", [])
                  if next((c.get("code") for c in (r.get("clinicalStatus") or {}).get("coding", [])), None) != "resolved"]
    diagnoses = sorted({_text(r.get("code")) for r in conditions} - {""})
    fields["diagnoses"] = _field("; ".join(diagnoses), refs(conditions), "ready" if diagnoses else "missing")

    medications = [r for kind in ("MedicationStatement", "MedicationRequest") for r in by_type.get(kind, []) if r.get("status") == "active"]
    med_names = sorted({_text(r.get("medicationCodeableConcept") or (r.get("medication") or {}).get("concept")) for r in medications} - {""})
    by_ingredient: dict[str, set[str]] = {}
    for med in med_names:
        by_ingredient.setdefault(med.split()[0].lower(), set()).add(med)
    medication_status = "conflict" if any(len(versions) > 1 for versions in by_ingredient.values()) else "ready" if med_names else "missing"
    fields["medications"] = _field("; ".join(med_names), refs(medications), medication_status,
                                    "Conflicting active medication entries require clinician resolution" if medication_status == "conflict" else "")

    allergies = by_type.get("AllergyIntolerance", [])
    allergy_names = sorted({_text(r.get("code")) for r in allergies} - {""})
    fields["allergies"] = _field("; ".join(allergy_names), refs(allergies), "ready" if allergy_names else "missing",
                                "No allergy resource is not proof of no known allergies" if not allergy_names else "")

    careplans = [r for r in by_type.get("CarePlan", []) if r.get("status") == "active"]
    follow_up = "; ".join(r.get("description", "") for r in careplans if r.get("description"))
    fields["follow_up"] = _field(follow_up, refs(careplans), "ready" if follow_up else "missing")
    fields["clinical_note"] = _field("", [], "missing", "Enter and approve a clinician-authored note")
    return {"patient_id": patient_id, "fields": fields, "approved": False,
            "verified": False, "source_resources": {f"{r['resourceType']}/{r['id']}": r for r in resources if r.get("id")}}


def unresolved(draft: dict) -> list[str]:
    return [name for name in FIELD_LABELS if draft["fields"][name]["status"] != "ready" or not draft["fields"][name]["value"].strip()]


def revise(draft: dict, changes: dict[str, str]) -> dict:
    for key, value in changes.items():
        if key not in FIELD_LABELS:
            raise ValueError(f"Unknown field: {key}")
        if key == "patient_id" and value != draft["patient_id"]:
            raise ValueError("Patient identity cannot be changed in a draft")
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        if len(value) > 4000:
            raise ValueError(f"{key} is too long")
        entry = draft["fields"][key]
        if value != entry["value"]:
            entry.update(value=value.strip(), status="ready" if value.strip() else "missing", reason="",
                         source=[*entry["source"], "Clinician review"])
    draft["approved"] = False
    draft["verified"] = False
    return draft
