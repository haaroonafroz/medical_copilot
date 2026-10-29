"""Offline, reproducible evaluation of source mapping and safety decisions."""

from __future__ import annotations

import json
import sys
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.handoff.draft import build_draft
from src.handoff.fixtures import make_patient
from src.observability import trace_session, trace_span


def evaluate() -> dict:
    cases = json.loads((ROOT / "tests/fixtures/handoff_cases.json").read_text())
    results = []
    with trace_session(f"eval-{uuid4().hex[:8]}"):
        with trace_span("handoff.evaluation", {"case_count": len(cases)}):
            for case in cases:
                with trace_span("handoff.eval_case", {"scenario": case["scenario"]}):
                    sample = make_patient(case["scenario"])
                    draft = build_draft(sample["resources"], sample["patient_id"])
                    missing = sorted(k for k, field in draft["fields"].items() if field["status"] == "missing")
                    conflicts = sorted(k for k, field in draft["fields"].items() if field["status"] == "conflict")
                    source_coverage = sum(bool(field["source"]) for k, field in draft["fields"].items() if k != "clinical_note")
                    populated_source_fields = sum(bool(field["value"]) for k, field in draft["fields"].items() if k != "clinical_note")
                    passed = (missing == sorted(case["expected_missing"]) and conflicts == sorted(case["expected_conflicts"])
                              and source_coverage == populated_source_fields)
                    results.append({"scenario": case["scenario"], "passed": passed, "missing": missing,
                                    "conflicts": conflicts, "source_coverage": source_coverage})
    return {"passed": sum(r["passed"] for r in results), "total": len(results), "results": results}


if __name__ == "__main__":
    report = evaluate()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] == report["total"] else 1)
