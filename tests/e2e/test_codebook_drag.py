"""Drag-and-drop tests for the codebook sidebar.

WebKit's headless drag-and-drop pipeline does not emit the same dragenter
/ dragover sequence that Sortable.js relies on, so the WebKit case is
skipped — coverage on Chromium and Firefox is sufficient for the gesture.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


def _drag_param_names():
    """Drop WebKit from the parametrize set since headless drag is flaky.

    We still want a missing-engine to skip cleanly, so we re-walk
    browser_params() and rewrite WebKit's mark to a skip.
    """
    out = []
    for entry in browser_params():
        # entry is either a plain string ("chromium") or a pytest.param
        name = entry.values[0] if hasattr(entry, "values") else entry
        if name == "webkit":
            out.append(
                pytest.param(
                    "webkit",
                    marks=pytest.mark.skip(
                        reason="WebKit headless drag-and-drop is flaky with Sortable.js"
                    ),
                )
            )
        else:
            out.append(entry)
    return out


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_drag_code_into_folder(ace_server, browser_name):
    """Create a folder, then drag Alpha onto its header → Alpha lands inside."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")

            # Create a folder by wrapping Alpha + Bravo (⌥⇧→). This gives
            # us a folder with at least one code already in it — a non-empty
            # children container is a more reliable drag target than an
            # empty role="group", because Sortable measures the destination
            # by hit-testing existing siblings.
            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3, "fixture needs at least 3 codes (Alpha/Bravo/Charlie)"
            rows[1].click()  # Bravo
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            page.keyboard.press("Escape")
            # The wrap may have triggered inline rename — Esc twice to be safe.
            page.keyboard.press("Escape")

            # Now there's a folder containing Alpha + Bravo, and Charlie at
            # root. Drag Charlie INTO the folder by dropping onto an existing
            # code inside it (a known-good Sortable hit target).
            charlie_loc = page.locator(
                '#code-tree > .ace-code-row[data-code-id]'
            ).last  # last root-level code row (Charlie)
            target_loc = page.locator(
                '[role="group"] .ace-code-row[data-code-id]'
            ).first  # any existing child of the folder
            charlie_loc.wait_for(timeout=2000)
            target_loc.wait_for(timeout=2000)

            charlie_loc.drag_to(target_loc)

            # All three codes should now live inside the folder.
            page.wait_for_function(
                "() => document.querySelectorAll("
                "  '[role=\"group\"] .ace-code-row[data-code-id]'"
                ").length >= 3",
                timeout=4000,
            )
        finally:
            browser.close()
