"""Phoenix/OpenTelemetry setup shared by the copilot and handoff demo.

Workflow spans contain short metadata. The handoff CUA records full model inputs and outputs in Phoenix only for the allowlisted synthetic demo patients.
LangChain model content capture remains opt-in for other workflows.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar

_provider = None
_error = None
_attempted = False
_session_id: ContextVar[str | None] = ContextVar("handoff_session_id", default=None)
_request_span: ContextVar[object | None] = ContextVar("handoff_request_span", default=None)


def setup_observability() -> bool:
    global _provider, _error, _attempted
    if _attempted:
        return _provider is not None
    _attempted = True
    try:
        from phoenix.otel import register
        from openinference.instrumentation import TraceConfig
        from openinference.instrumentation.langchain import LangChainInstrumentor

        endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:4317")
        _provider = register(project_name=os.getenv("PHOENIX_PROJECT_NAME", "medical-copilot"),
                             endpoint=endpoint, auto_instrument=False, batch=True)
        capture_content = os.getenv("PHOENIX_CAPTURE_CONTENT", "false").lower() == "true"
        LangChainInstrumentor().instrument(
            tracer_provider=_provider,
            config=TraceConfig(hide_inputs=not capture_content, hide_outputs=not capture_content,
                               hide_input_messages=not capture_content, hide_output_messages=not capture_content),
        )
        return True
    except Exception as exc:
        _provider = None
        _error = f"{type(exc).__name__}: {exc}"
        return False


def status() -> dict:
    setup_observability()
    return {"configured": _provider is not None, "error": _error,
            "collector": os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:4317"),
            "project": os.getenv("PHOENIX_PROJECT_NAME", "medical-copilot")}


@contextmanager
def trace_session(session_id: str):
    """Associate every trace in one handoff with its stable run ID."""
    if not session_id:
        raise ValueError("A Phoenix session ID must be non-empty")
    ready = setup_observability()
    request_span = None
    if ready:
        from opentelemetry import trace
        candidate = trace.get_current_span()
        if candidate.is_recording():
            request_span = candidate
            request_span.set_attribute("session.id", session_id)
            request_span.set_attribute("handoff.run_id", session_id)
            request_span.set_attribute("openinference.span.kind", "CHAIN")
    session_token = _session_id.set(session_id)
    request_token = _request_span.set(request_span)
    try:
        try:
            if ready:
                from openinference.instrumentation import using_session
                with using_session(session_id):
                    yield
            else:
                yield
        except BaseException as exc:
            if request_span is not None:
                from opentelemetry.trace import Status, StatusCode
                request_span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise
        else:
            if request_span is not None:
                from opentelemetry.trace import Status, StatusCode
                request_span.set_status(Status(StatusCode.OK))
    finally:
        _request_span.reset(request_token)
        _session_id.reset(session_token)


def request_span():
    """Return the active HTTP root span, when the app has one."""
    return _request_span.get()


@contextmanager
def trace_span(name: str, attributes: dict | None = None, *, kind: str = "CHAIN"):
    """Create a manual span with the active handoff session and semantic kind."""
    if not setup_observability():
        yield None
        return
    with _provider.get_tracer("medical-copilot.handoff").start_as_current_span(name) as span:
        span.set_attribute("openinference.span.kind", kind)
        if session_id := _session_id.get():
            span.set_attribute("session.id", session_id)
            span.set_attribute("handoff.run_id", session_id)
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        try:
            yield span
        except BaseException:
            raise
        else:
            from opentelemetry.trace import Status, StatusCode
            span.set_status(Status(StatusCode.OK))
