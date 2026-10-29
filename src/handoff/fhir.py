"""FHIR access with explicit failures and search pagination."""

from __future__ import annotations

from urllib.parse import urlparse

import requests


class FhirError(RuntimeError):
    pass


RESOURCE_QUERIES = {
    "Encounter": "patient",
    "Condition": "subject",
    "MedicationStatement": "subject",
    "MedicationRequest": "subject",
    "AllergyIntolerance": "patient",
    "Observation": "subject",
    "CarePlan": "subject",
}


class FhirClient:
    def __init__(self, base_url: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.origin = urlparse(self.base_url)

    def _json(self, url: str, params: dict | None = None) -> dict:
        try:
            response = self.session.get(url, params=params, timeout=8)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise FhirError(f"FHIR request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise FhirError("FHIR returned a non-object response")
        return payload

    def _search(self, resource_type: str, param: str, patient_id: str) -> list[dict]:
        url = f"{self.base_url}/{resource_type}"
        params: dict | None = {param: f"Patient/{patient_id}", "_count": 50}
        seen = set()
        resources = []
        while url:
            if url in seen or len(seen) >= 20:
                raise FhirError(f"FHIR paging loop or excessive pages for {resource_type}")
            seen.add(url)
            bundle = self._json(url, params=params)
            params = None
            if bundle.get("resourceType") != "Bundle":
                raise FhirError(f"Expected FHIR Bundle for {resource_type}")
            resources.extend(entry["resource"] for entry in bundle.get("entry", []) if isinstance(entry.get("resource"), dict))
            next_url = next((link.get("url") for link in bundle.get("link", []) if link.get("relation") == "next"), None)
            if next_url:
                parsed = urlparse(next_url)
                if parsed.scheme != self.origin.scheme or parsed.netloc != self.origin.netloc:
                    raise FhirError("FHIR paging link changed origin")
            url = next_url
        return resources

    def patient(self, patient_id: str) -> list[dict]:
        if not patient_id or not all(c.isalnum() or c in "-_." for c in patient_id):
            raise FhirError("Invalid patient ID")
        patient = self._json(f"{self.base_url}/Patient/{patient_id}")
        if patient.get("resourceType") != "Patient" or patient.get("id") != patient_id:
            raise FhirError("FHIR patient identity did not match the request")
        result = [patient]
        for kind, param in RESOURCE_QUERIES.items():
            result.extend(self._search(kind, param, patient_id))
        return result
