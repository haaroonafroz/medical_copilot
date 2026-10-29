"""Capture synthetic workflow screenshots for visual review.

Requires a running local handoff server and Playwright Chromium.
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    origin = os.getenv("HANDOFF_E2E_URL", "http://127.0.0.1:8768")
    output = Path(os.getenv("HANDOFF_SCREENSHOT_DIR", "/tmp"))
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=os.getenv("HANDOFF_CHROMIUM_EXECUTABLE"))
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1)
            page.goto(origin, wait_until="networkidle")
            page.get_by_role("button", name="Prepare handoff").click()
            page.locator("#sheet-fields").wait_for()
            page.screenshot(path=str(output / "handoff-review.png"), full_page=True)
            page.get_by_label("Clinician-approved note", exact=True).fill("Synthetic test: clinician reviewed the discharge documentation.")
            page.get_by_role("button", name="Save edits").click()
            page.get_by_role("button", name="Approve for handoff").click()
            page.get_by_role("button", name="Run UI handoff").click()
            page.get_by_text("All fields persisted and matched after reload.").wait_for(timeout=30000)
            page.screenshot(path=str(output / "handoff-verified.png"), full_page=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
