"""Seed reproducible, comprehensive synthetic discharge scenarios into HAPI FHIR.

Run from the repository root: python scripts/seed_handoff.py
No clinical data or external patient source is used.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.handoff.fixtures import SCENARIOS, make_patient


def seed(base_url: str, scenarios: list[str], seed_value: int = 7) -> dict:
    base_url = base_url.rstrip("/")
    result = {"patients": [], "resources_uploaded": 0, "errors": []}
    session = requests.Session()
    for scenario in scenarios:
        sample = make_patient(scenario, seed_value)
        for resource in sample["resources"]:
            url = f"{base_url}/{resource['resourceType']}/{resource['id']}"
            try:
                response = session.put(url, json=resource, headers={"Content-Type": "application/fhir+json"}, timeout=15)
                response.raise_for_status()
                result["resources_uploaded"] += 1
            except requests.RequestException as exc:
                result["errors"].append({"resource": f"{resource['resourceType']}/{resource['id']}", "error": str(exc)})
        result["patients"].append(sample["patient_id"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir"))
    parser.add_argument("--scenario", choices=SCENARIOS, action="append", help="Repeat to seed several; default is all")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    report = seed(args.base_url, args.scenario or list(SCENARIOS), args.seed)
    print(report)
    if report["errors"]:
        raise SystemExit(1)
