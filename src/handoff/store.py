"""Short-lived in-memory sessions for the local interview demo."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


class SessionStore:
    def __init__(self):
        self._runs: dict[str, dict] = {}
        self._lock = RLock()

    def create(self, draft: dict, run_id: str | None = None, layout: str = "standard") -> dict:
        run_id = run_id or uuid4().hex
        with self._lock:
            if run_id in self._runs:
                raise ValueError("Handoff run ID already exists")
            self._runs[run_id] = {"id": run_id, "draft": deepcopy(draft), "events": [], "target": {},
                                  "result": None, "screenshot": None, "frame": None, "layout": layout,
                                  "cua_status": "idle", "cua_pause": None, "cua_mode": None,
                                  "save_failures_remaining": 1 if layout == "flaky_save" else 0}
            self.event(run_id, "draft_created", "Discharge sheet prepared from FHIR resources")
            return deepcopy(self._public(self._runs[run_id]))

    def _public(self, run: dict) -> dict:
        return {key: deepcopy(value) for key, value in run.items() if key not in {"screenshot", "frame", "save_failures_remaining"}}

    def get(self, run_id: str) -> dict:
        with self._lock:
            return deepcopy(self._public(self._runs[run_id]))

    def update_draft(self, run_id: str, draft: dict) -> dict:
        with self._lock:
            self._runs[run_id]["draft"] = deepcopy(draft)
            self.event(run_id, "draft_revised", "Clinician revised the discharge sheet")
            return self.get(run_id)

    def approve(self, run_id: str) -> dict:
        with self._lock:
            self._runs[run_id]["draft"]["approved"] = True
            self.event(run_id, "approved", "Clinician approved the discharge sheet")
            return self.get(run_id)

    def event(self, run_id: str, kind: str, message: str, details: dict | None = None) -> None:
        with self._lock:
            self._runs[run_id]["events"].append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                    "kind": kind, "message": message, "details": details or {}})

    def start_cua(self, run_id: str) -> dict:
        with self._lock:
            self._runs[run_id]["cua_status"] = "running"
            self._runs[run_id]["cua_mode"] = "model"
            self._runs[run_id]["cua_pause"] = None
            self._runs[run_id]["result"] = None
            self.event(run_id, "cua_started", "GPT-6 Luna started observing the mock HIS")
            return self.get(run_id)

    def start_scripted(self, run_id: str) -> None:
        with self._lock:
            self._runs[run_id]["cua_status"] = "running"
            self._runs[run_id]["cua_mode"] = "scripted"
            self._runs[run_id]["result"] = None

    def pause_cua(self, run_id: str, reason: str) -> None:
        with self._lock:
            self._runs[run_id]["cua_status"] = "paused"
            self._runs[run_id]["cua_pause"] = reason
            self.event(run_id, "human_review_requested", reason)

    def resume_cua(self, run_id: str, guidance: str) -> None:
        with self._lock:
            self._runs[run_id]["cua_status"] = "running"
            self._runs[run_id]["cua_pause"] = None
            self.event(run_id, "human_review_resumed", "Human supplied guidance", {"guidance": guidance})

    def set_frame(self, run_id: str, frame: bytes) -> None:
        with self._lock:
            self._runs[run_id]["frame"] = frame

    def frame(self, run_id: str) -> bytes | None:
        with self._lock:
            return self._runs[run_id]["frame"]

    def fail_save_once(self, run_id: str) -> bool:
        with self._lock:
            remaining = self._runs[run_id]["save_failures_remaining"]
            if remaining:
                self._runs[run_id]["save_failures_remaining"] = remaining - 1
            return bool(remaining)

    def save_target(self, run_id: str, values: dict) -> None:
        with self._lock:
            self._runs[run_id]["target"] = deepcopy(values)

    def finish(self, run_id: str, result: dict, screenshot: bytes | None = None) -> dict:
        with self._lock:
            self._runs[run_id]["result"] = deepcopy(result)
            self._runs[run_id]["cua_status"] = "verified" if result.get("verified") else "failed"
            self._runs[run_id]["cua_pause"] = None
            self._runs[run_id]["screenshot"] = screenshot
            self._runs[run_id]["draft"]["verified"] = bool(result.get("verified"))
            return self.get(run_id)

    def screenshot(self, run_id: str) -> bytes | None:
        with self._lock:
            return self._runs[run_id]["screenshot"]
