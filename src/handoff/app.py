"""Local discharge handoff demo. Run with uvicorn src.handoff.app:app --port 8768."""

from __future__ import annotations

import asyncio
import html
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from src.observability import request_span, setup_observability, status as tracing_status, trace_session, trace_span

from .cua import CuaError, fill_and_verify
from .model_cua import MODEL as CUA_MODEL, run_model_cua
from .draft import FIELD_LABELS, build_draft, revise, unresolved
from .fhir import FhirClient, FhirError
from .fixtures import SCENARIOS, make_patient
from .store import SessionStore

STATIC = Path(__file__).parent / "static"
FHIR_SOURCE = os.getenv("HANDOFF_FHIR_SOURCE", "fixture")
FHIR_BASE_URL = os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")

app = FastAPI(title="Clinical Handoff Demo", docs_url="/api/docs", redoc_url=None)
sessions = SessionStore()
_operator_tasks: dict[str, asyncio.Task] = {}
_resume_events: dict[str, asyncio.Event] = {}
_resume_feedback: dict[str, str] = {}
setup_observability()


class CreateRequest(BaseModel):
    patient_id: str
    layout: Literal["standard", "tabs", "visual", "ambiguous", "flaky_save"] = "standard"


class ReviseRequest(BaseModel):
    changes: dict[str, str] = Field(default_factory=dict)


class SaveRequest(BaseModel):
    values: dict[str, str]


class ResumeRequest(BaseModel):
    guidance: str = Field(min_length=1, max_length=500)


def _span_summary(span, direction: str, summary: dict) -> None:
    """Expose decisions in Phoenix without patient identifiers or clinical values."""
    value = json.dumps(summary, sort_keys=True)
    for target in (span, request_span()):
        if target is not None:
            target.set_attribute(f"{direction}.value", value)
            target.set_attribute(f"{direction}.mime_type", "application/json")


def _run(run_id: str) -> dict:
    try:
        return sessions.get(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Handoff run not found") from None


def _resources(patient_id: str) -> list[dict]:
    if FHIR_SOURCE == "fixture":
        for scenario in SCENARIOS:
            sample = make_patient(scenario)
            if sample["patient_id"] == patient_id:
                return sample["resources"]
        raise HTTPException(status_code=404, detail="Synthetic patient not found")
    if FHIR_SOURCE != "live":
        raise HTTPException(status_code=500, detail="HANDOFF_FHIR_SOURCE must be fixture or live")
    sample = next((make_patient(s) for s in SCENARIOS if make_patient(s)["patient_id"] == patient_id), None)
    if sample is None:
        raise HTTPException(status_code=404, detail="Only the generated demo patients are allowed")
    resources = FhirClient(FHIR_BASE_URL).patient(patient_id)
    expected = sample["resources"][0]
    actual = resources[0]
    if actual.get("name") != expected["name"] or actual.get("birthDate") != expected["birthDate"]:
        raise FhirError("FHIR patient no longer matches the generated synthetic case")
    return resources


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/static/{name}")
def static_file(name: str):
    if name not in {"app.css", "app.js"}:
        raise HTTPException(status_code=404)
    return FileResponse(STATIC / name)


@app.get("/api/health")
def health():
    fhir = {"mode": FHIR_SOURCE, "reachable": FHIR_SOURCE == "fixture"}
    if FHIR_SOURCE == "live":
        try:
            response = requests.get(f"{FHIR_BASE_URL.rstrip('/')}/metadata", timeout=3)
            fhir["reachable"] = response.ok and response.json().get("resourceType") == "CapabilityStatement"
        except (requests.RequestException, ValueError):
            fhir["reachable"] = False
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    return {"status": "ok", "fhir": fhir, "phoenix": tracing_status(),
            "cua": {"model": os.getenv("HANDOFF_CUA_MODEL", CUA_MODEL),
                    "configured": bool(os.getenv("OPENAI_API_KEY"))}}


@app.get("/api/patients")
def patients():
    if FHIR_SOURCE == "fixture":
        return [{"id": make_patient(s)["patient_id"], "scenario": s,
                 "name": " ".join([*make_patient(s)["resources"][0]["name"][0]["given"],
                                    make_patient(s)["resources"][0]["name"][0]["family"]])} for s in SCENARIOS]
    listed = []
    for scenario in SCENARIOS:
        patient_id = make_patient(scenario)["patient_id"]
        try:
            response = requests.get(f"{FHIR_BASE_URL.rstrip('/')}/Patient/{patient_id}", timeout=8)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            patient = response.json()
            if patient.get("resourceType") != "Patient" or patient.get("id") != patient_id:
                raise FhirError("FHIR patient identity did not match the expected synthetic case")
            name = (patient.get("name") or [{}])[0]
            listed.append({"id": patient_id, "scenario": scenario,
                           "name": " ".join([*(name.get("given") or []), name.get("family", "")]).strip()})
        except (requests.RequestException, ValueError, FhirError) as exc:
            raise HTTPException(status_code=503, detail=f"FHIR patient listing failed: {exc}") from exc
    return listed



@app.post("/api/handoff")
def create_handoff(body: CreateRequest):
    run_id = uuid4().hex
    with trace_session(run_id):
        with trace_span("handoff.prepare", {"source": FHIR_SOURCE}) as span:
            _span_summary(span, "input", {"workflow": "discharge_handoff", "source": FHIR_SOURCE})
            try:
                with trace_span("handoff.fetch_fhir", {"source": FHIR_SOURCE}, kind="TOOL"):
                    resources = _resources(body.patient_id)
                with trace_span("handoff.map_discharge_sheet", {"resource_count": len(resources)}):
                    draft = build_draft(resources, body.patient_id)
                    for field_name, field in draft["fields"].items():
                        with trace_span("handoff.map_field", {"field": field_name,
                                                               "status": field["status"],
                                                               "source_count": len(field["source"])}):
                            pass
            except (FhirError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            _span_summary(span, "output", {"resource_count": len(resources),
                                            "field_statuses": {key: field["status"] for key, field in draft["fields"].items()}})
            run = sessions.create(draft, run_id, body.layout)
            for field_name, field in draft["fields"].items():
                if field["status"] != "ready":
                    sessions.event(run_id, "field_needs_review", f"{FIELD_LABELS[field_name]} needs review",
                                   {"field": field_name, "status": field["status"], "sources": field["source"]})
            return sessions.get(run_id)


@app.get("/api/handoff/{run_id}")
def get_handoff(run_id: str):
    return _run(run_id)


@app.post("/api/handoff/{run_id}/revise")
def revise_handoff(run_id: str, body: ReviseRequest):
    run = _run(run_id)
    with trace_session(run_id):
        with trace_span("handoff.clinician_revision", {"field_count": len(body.changes),
                                                       "fields": sorted(body.changes)}) as span:
            _span_summary(span, "input", {"edited_fields": sorted(body.changes)})
            try:
                draft = revise(run["draft"], body.changes)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            _span_summary(span, "output", {"unresolved_fields": unresolved(draft)})
            return sessions.update_draft(run_id, draft)


@app.post("/api/handoff/{run_id}/approve")
def approve_handoff(run_id: str):
    run = _run(run_id)
    with trace_session(run_id):
        with trace_span("handoff.clinician_approval", {"field_count": len(FIELD_LABELS)}) as span:
            _span_summary(span, "input", {"action": "approve"})
            missing = unresolved(run["draft"])
            if missing:
                if span is not None:
                    span.set_attribute("review.unresolved_fields", missing)
                _span_summary(span, "output", {"approved": False, "unresolved_fields": missing})
                sessions.event(run_id, "approval_blocked", "Unresolved fields blocked approval",
                               {"fields": missing})
                raise HTTPException(status_code=409, detail={"message": "Resolve these fields before approval", "fields": missing})
            if span is not None:
                span.set_attribute("review.approved", True)
            _span_summary(span, "output", {"approved": True})
            return sessions.approve(run_id)


@app.post("/api/handoff/{run_id}/execute")
async def execute_handoff(run_id: str, request: Request):
    run = _run(run_id)
    with trace_session(run_id):
        with trace_span("handoff.cua_run", {"target": "mock-his", "field_count": len(FIELD_LABELS)}) as span:
            _span_summary(span, "input", {"target": "mock-his", "field_count": len(FIELD_LABELS)})
            if not run["draft"]["approved"] or unresolved(run["draft"]):
                sessions.event(run_id, "execution_blocked", "Clinician approval and complete fields are required")
                raise HTTPException(status_code=409, detail="Clinician approval and complete fields are required")
            target_url = str(request.url_for("his_form", run_id=run_id))
            if urlparse(target_url).hostname not in {"127.0.0.1", "localhost"}:
                raise HTTPException(status_code=400, detail="The demo target must run on localhost")
            sessions.start_scripted(run_id)
            sessions.event(run_id, "cua_started", "Scripted Playwright adapter began work in the mock HIS")
            try:
                result, screenshot = await fill_and_verify(
                    target_url, run["draft"], trace_span,
                    lambda kind, message, details=None: sessions.event(run_id, kind, message, details),
                )
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                _span_summary(span, "output", {"verified": False, "error_type": type(exc).__name__})
                sessions.event(run_id, "cua_failed", reason)
                sessions.finish(run_id, {"verified": False, "error": reason})
                raise HTTPException(status_code=502, detail=reason) from exc
            if span is not None:
                span.set_attribute("verification.matched", result["matched"])
                span.set_attribute("verification.total", result["total"])
                span.set_attribute("verification.verified", result["verified"])
            _span_summary(span, "output", {"verified": result["verified"],
                                           "matched": result["matched"], "total": result["total"],
                                           "mismatches": result["mismatches"]})
            return sessions.finish(run_id, result, screenshot)


async def _wait_for_human(run_id: str, reason: str) -> str:
    waiter = _resume_events[run_id]
    waiter.clear()
    sessions.pause_cua(run_id, reason)
    await waiter.wait()
    return _resume_feedback.pop(run_id)


async def _model_operator_task(run_id: str, target_url: str) -> None:
    try:
        with trace_session(run_id):
            with trace_span("handoff.model_cua_run", {"target": "mock-his", "llm.model_name": os.getenv("HANDOFF_CUA_MODEL", CUA_MODEL)}) as span:
                run = sessions.get(run_id)
                _span_summary(span, "input", {"target": "mock-his", "model": os.getenv("HANDOFF_CUA_MODEL", CUA_MODEL),
                                               "layout": run["layout"], "field_count": len(FIELD_LABELS)})
                result, screenshot = await run_model_cua(
                    target_url, run["draft"], trace_span,
                    lambda kind, message, details=None: sessions.event(run_id, kind, message, details),
                    lambda frame: sessions.set_frame(run_id, frame),
                    lambda reason: _wait_for_human(run_id, reason),
                )
                _span_summary(span, "output", result)
                sessions.finish(run_id, result, screenshot)
    except asyncio.CancelledError:
        sessions.event(run_id, "cua_cancelled", "Model-driven handoff cancelled")
        sessions.finish(run_id, {"verified": False, "error": "Cancelled by user"})
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        sessions.event(run_id, "cua_failed", reason)
        sessions.finish(run_id, {"verified": False, "error": reason})
    finally:
        _operator_tasks.pop(run_id, None)
        _resume_events.pop(run_id, None)
        _resume_feedback.pop(run_id, None)


@app.post("/api/handoff/{run_id}/execute-model")
async def execute_model_handoff(run_id: str, request: Request):
    run = _run(run_id)
    if not run["draft"]["approved"] or unresolved(run["draft"]):
        raise HTTPException(status_code=409, detail="Clinician approval and complete fields are required")
    if run_id in _operator_tasks:
        raise HTTPException(status_code=409, detail="Model operator is already running")
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
    target_url = str(request.url_for("his_form", run_id=run_id))
    if urlparse(target_url).hostname not in {"127.0.0.1", "localhost"}:
        raise HTTPException(status_code=400, detail="The demo target must run on localhost")
    _resume_events[run_id] = asyncio.Event()
    result = sessions.start_cua(run_id)
    _operator_tasks[run_id] = asyncio.create_task(_model_operator_task(run_id, target_url))
    return result


@app.post("/api/handoff/{run_id}/resume")
async def resume_model_handoff(run_id: str, body: ResumeRequest):
    run = _run(run_id)
    if run["cua_status"] != "paused" or run_id not in _resume_events:
        raise HTTPException(status_code=409, detail="No model operator is waiting for human guidance")
    _resume_feedback[run_id] = body.guidance.strip()
    sessions.resume_cua(run_id, body.guidance.strip())
    _resume_events[run_id].set()
    return sessions.get(run_id)


@app.post("/api/handoff/{run_id}/cancel")
async def cancel_model_handoff(run_id: str):
    _run(run_id)
    task = _operator_tasks.get(run_id)
    if task is None:
        raise HTTPException(status_code=409, detail="No model operator is running")
    task.cancel()
    return {"cancel_requested": True}


@app.get("/api/handoff/{run_id}/frame")
def operator_frame(run_id: str):
    _run(run_id)
    data = sessions.frame(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No operator frame yet")
    return Response(content=data, media_type="image/png")


@app.get("/api/handoff/{run_id}/screenshot")
def screenshot(run_id: str):
    _run(run_id)
    data = sessions.screenshot(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No screenshot yet")
    return Response(content=data, media_type="image/png")


@app.get("/his/{run_id}", name="his_form")
def his_form(run_id: str):
    run = _run(run_id)
    target = run["target"]
    layout = run["layout"]
    fields = {}
    for key, label in FIELD_LABELS.items():
        value = run["draft"]["patient_id"] if key == "patient_id" else target.get(key, "")
        escaped = html.escape(str(value), quote=True)
        visual_only = layout == "visual" and key == "follow_up"
        caption = (f'<div class="visual-caption">{html.escape(label)} <span>↘</span></div>' if visual_only
                   else f'<label for="{key}">{html.escape(label)}</label>')
        if key in {"diagnoses", "medications", "allergies", "follow_up", "clinical_note"}:
            control = f'<textarea id="{key}" name="{key}" rows="3">{escaped}</textarea>'
        else:
            control = f'<input id="{key}" name="{key}" value="{escaped}" {"readonly" if key == "patient_id" else ""}>'
        fields[key] = f'<div class="his-field {"visual-only" if visual_only else ""}">{caption}{control}</div>'
    if layout == "ambiguous":
        fields["follow_up"] = ('<div class="his-field"><label for="follow_up_alt">Follow-up plan · Route A</label>'
                               '<textarea id="follow_up_alt" name="follow_up_alt" rows="3"></textarea></div>'
                               + fields["follow_up"].replace('>Follow-up plan</label>', '>Follow-up plan · Route B</label>'))
    if layout == "tabs":
        first = ["patient_id", "patient_name", "birth_date", "admitted", "discharged", "disposition"]
        second = [key for key in FIELD_LABELS if key not in first]
        tabs = '<div class="his-tabs"><button type="button" class="selected" data-tab="stay">Patient &amp; stay</button><button type="button" data-tab="care">Care &amp; notes</button></div>'
        controls = (f'<div class="grid tab-panel" data-panel="stay">{"".join(fields[key] for key in first)}</div>'
                    f'<div class="grid tab-panel" data-panel="care" hidden>{"".join(fields[key] for key in second)}</div>')
    else:
        tabs = ""
        order = list(FIELD_LABELS)
        if layout == "visual":
            order = ["patient_id", "patient_name", "birth_date", "diagnoses", "follow_up", "admitted", "discharged", "disposition", "medications", "allergies", "clinical_note"]
        controls = '<div class="grid">' + "".join(fields[key] for key in order) + '</div>'
        if layout == "ambiguous":
            controls = '<p class="ambiguity">Two follow-up destinations are available. Ask hospital staff which route stores the discharge plan.</p>' + controls
    document = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Mock HIS • Discharge form</title><style>
    body{font:14px/1.5 system-ui,sans-serif;background:#f3f6f9;color:#183047;margin:0}header{background:#123b52;color:white;padding:16px 24px}
    header strong{font-size:18px}header span{float:right;opacity:.8}main{max-width:850px;margin:24px auto;background:white;border:1px solid #d9e2e8;border-radius:12px;padding:24px}
    h1{font-size:22px;margin:0 0 4px}.hint{color:#60798b;margin:0 0 20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .his-field{display:flex;flex-direction:column;gap:5px}.his-field:nth-last-child(-n+5){grid-column:1/-1}
    label,.visual-caption{font-weight:650}.visual-caption span{color:#0a7780}input,textarea{font:inherit;border:1px solid #bdcbd4;border-radius:7px;padding:9px;color:#183047;resize:vertical}
    input[readonly]{background:#edf3f6}button{background:#0a7780;color:white;border:0;border-radius:7px;padding:11px 18px;font-weight:700;cursor:pointer;margin-top:20px}
    .his-tabs{display:flex;gap:8px;margin-bottom:18px}.his-tabs button{margin:0;background:#e6f0f2;color:#235366}.his-tabs button.selected{background:#0a7780;color:white}
    .tab-panel[hidden]{display:none}.ambiguity{color:#855819;background:#fff3db;border:1px solid #efce92;padding:10px;border-radius:7px;font-weight:650}#save-status{margin-left:12px;color:#166c50;font-weight:700}.foot{border-top:1px solid #d9e2e8;margin-top:22px;padding-top:12px;color:#60798b}
    </style></head><body><header><strong>Mock HIS</strong><span>Local training environment</span></header><main>
    <h1>Discharge documentation</h1><p class="hint">Draft entry screen · synthetic patient only</p><form id="his-form">__TABS____FIELDS__
    <button type="submit">Save draft</button><span id="save-status" role="status"></span></form>
    <p class="foot">Final sign-off remains outside this demo workflow.</p></main>
    <script>document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('selected',b===button));document.querySelectorAll('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==button.dataset.tab)}));
    document.querySelector('#his-form').addEventListener('submit',async(e)=>{e.preventDefault();const values=Object.fromEntries([...new FormData(e.target).entries()].filter(([key])=>key!=='follow_up_alt'));
    const response=await fetch('/api/his/__RUN_ID__/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({values})});
    document.querySelector('#save-status').textContent=response.ok?'Draft saved':'Save failed';});</script></body></html>"""
    return HTMLResponse(document.replace("__TABS__", tabs).replace("__FIELDS__", controls).replace("__RUN_ID__", run_id))


@app.post("/api/his/{run_id}/save")
def save_his_draft(run_id: str, body: SaveRequest):
    run = _run(run_id)
    with trace_session(run_id):
        with trace_span("mock_his.save_draft", {"field_count": len(body.values)}, kind="TOOL") as span:
            _span_summary(span, "input", {"action": "save_draft", "field_count": len(body.values)})
            if not run["draft"]["approved"]:
                raise HTTPException(status_code=409, detail="Handoff is not approved")
            if set(body.values) != set(FIELD_LABELS) or body.values["patient_id"] != run["draft"]["patient_id"]:
                raise HTTPException(status_code=422, detail="Field set or patient identity mismatch")
            if any(len(value) > 4000 for value in body.values.values()):
                raise HTTPException(status_code=422, detail="Field value too long")
            if sessions.fail_save_once(run_id):
                sessions.event(run_id, "mock_save_rejected", "Mock HIS rejected the first save attempt")
                raise HTTPException(status_code=503, detail="Synthetic transient save failure")
            sessions.save_target(run_id, body.values)
            _span_summary(span, "output", {"saved": True})
            return {"saved": True}
