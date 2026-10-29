"""Browser UI adapter for the mock HIS. No direct target-system writes."""

from __future__ import annotations

import os

from playwright.async_api import async_playwright

from .draft import FIELD_LABELS


class CuaError(RuntimeError):
    pass


async def fill_and_verify(url: str, draft: dict, trace_span, event) -> tuple[dict, bytes]:
    """Operate the target form, save a draft, reload it, and compare persisted values."""
    desired = {key: draft["fields"][key]["value"] for key in FIELD_LABELS}
    async with async_playwright() as playwright:
        executable = os.getenv("HANDOFF_CHROMIUM_EXECUTABLE")
        browser = await playwright.chromium.launch(headless=True, executable_path=executable)
        try:
            page = await browser.new_page(viewport={"width": 1360, "height": 1000}, device_scale_factor=1)
            with trace_span("cua.observe", {"target": "mock-his"}, kind="TOOL"):
                await page.goto(url, wait_until="networkidle", timeout=20000)
                observed_patient = await page.get_by_label("Patient ID", exact=True).input_value()
                if observed_patient != draft["patient_id"]:
                    raise CuaError("Target patient identity differs from the approved draft")
                event("target_observed", "Mock HIS opened and patient identity matched")

            for key, label in FIELD_LABELS.items():
                if key == "patient_id":
                    continue
                with trace_span("cua.fill_field", {"field": key}, kind="TOOL"):
                    locator = page.get_by_label(label, exact=True)
                    if await locator.count() != 1:
                        raise CuaError(f"Expected one target field for {label}")
                    await locator.fill(desired[key])
                    if await locator.input_value() != desired[key]:
                        raise CuaError(f"Target rejected {label} before save")
                    event("field_filled", f"Filled {label}", {"field": key})

            with trace_span("cua.save_draft", {"target": "mock-his"}, kind="TOOL"):
                await page.get_by_role("button", name="Save draft").click()
                await page.get_by_text("Draft saved", exact=True).wait_for(timeout=10000)
                event("draft_saved", "Mock HIS confirmed draft save")

            with trace_span("cua.verify_persisted", {"target": "mock-his"}, kind="TOOL"):
                await page.reload(wait_until="networkidle")
                actual = {key: await page.get_by_label(label, exact=True).input_value()
                          for key, label in FIELD_LABELS.items()}
                mismatches = [key for key in FIELD_LABELS if actual[key] != desired[key]]
                screenshot = await page.screenshot(full_page=True)
                event("verification", "All fields persisted" if not mismatches else "Persisted fields did not match",
                      {"matched": len(FIELD_LABELS) - len(mismatches), "total": len(FIELD_LABELS), "mismatches": mismatches})
                return {"matched": len(FIELD_LABELS) - len(mismatches), "total": len(FIELD_LABELS),
                        "mismatches": mismatches, "verified": not mismatches}, screenshot
        finally:
            await browser.close()
