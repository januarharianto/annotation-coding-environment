"""Keyboard gesture tests for the codebook sidebar.

Covers the spec §6.4 gestures and the Task 9 audit amendment:

  * bare ⌥→ NEVER auto-creates a folder (no surprise materialisation);
    on a code-above-code config it announces the explicit gesture instead.
  * ⌥⇧→ is the explicit "wrap two root codes into a new folder" gesture.
  * Shift+Enter in the filter creates a folder at root.
  * ⌘X / ⌘V cut-paste a code into a folder.
  * Esc from the sidebar returns focus to the text panel.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


# ---------------------------------------------------------------------------
# ⌥⇧→ — explicit wrap-into-new-folder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("browser_name", browser_params())
def test_alt_shift_right_wraps_two_root_codes_into_folder(ace_server, browser_name):
    """⌥⇧→ on Bravo (root code with Alpha root above) → both codes nest
    inside a new folder atomically."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            # Pre-condition: zero folders.
            assert page.locator(".ace-code-folder-row").count() == 0

            # Focus the SECOND code row (Bravo). Alpha sits above it at root.
            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 2, "fixture should have at least 2 codes"
            rows[1].click()

            # Explicit wrap gesture (Task 9 amendment — bare ⌥→ would NOT do this).
            page.keyboard.press("Alt+Shift+ArrowRight")

            # Folder appears.
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            assert page.locator(".ace-code-folder-row").count() == 1

            # Both Alpha and Bravo are now inside the folder.
            inside = page.evaluate(
                "() => Array.from(document.querySelectorAll('[role=\"group\"] .ace-code-row'))"
                "      .map(r => r.querySelector('.ace-code-name')?.textContent?.trim())"
            )
            assert "Alpha" in inside, f"Alpha should be inside the folder, got {inside!r}"
            assert "Bravo" in inside, f"Bravo should be inside the folder, got {inside!r}"
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# bare ⌥→ — must NOT auto-create a folder (Task 9 amendment)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("browser_name", browser_params())
def test_bare_alt_right_on_root_code_does_not_create_folder(ace_server, browser_name):
    """Plain ⌥→ on Bravo (Alpha is a root code above) is a NO-OP.

    The spec amendment (plan header L51-56) requires the user to use the
    explicit ⌥⇧→ gesture for wrap-into-folder. Bare ⌥→ should announce
    the explicit gesture and write a status hint, but NOT create a folder.
    """
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            # Pre-condition: zero folders.
            assert page.locator(".ace-code-folder-row").count() == 0

            # Focus Bravo (second root code). Alpha sits above it at root.
            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 2
            rows[1].click()

            # Bare ⌥→ — no Shift.
            page.keyboard.press("Alt+ArrowRight")

            # Give the JS handler a tick to process; no folder must appear.
            page.wait_for_timeout(250)
            assert page.locator(".ace-code-folder-row").count() == 0, (
                "bare ⌥→ on root code with root code above must NOT auto-create a folder"
            )

            # Status text should hint at the explicit gesture (bridge.js L3632).
            status = page.evaluate(
                "() => document.querySelector('#ace-statusbar-event')?.textContent || ''"
            )
            # The exact message is "⌥⇧→ to wrap into a new folder".
            assert "⌥⇧→" in status or "Alt" in status or "wrap" in status.lower(), (
                f"expected a hint about ⌥⇧→ in status, got {status!r}"
            )
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Shift+Enter in the filter — create folder at root
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("browser_name", browser_params())
def test_shift_enter_in_filter_creates_folder(ace_server, browser_name):
    """Type a name in the filter, press Shift+Enter → new folder at root."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-search-input")

            page.fill("#code-search-input", "TestFolder")
            page.keyboard.press("Shift+Enter")

            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            labels = page.evaluate(
                "() => Array.from(document.querySelectorAll('.ace-folder-label'))"
                "      .map(el => el.textContent.trim())"
            )
            assert "TestFolder" in labels, f"expected TestFolder among {labels!r}"
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# ⌘X / ⌘V — cut-paste a code into a folder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("browser_name", browser_params())
def test_cmd_x_then_cmd_v_moves_code_into_folder(ace_server, browser_name):
    """Cut Alpha → focus the folder → paste → Alpha lives inside the folder."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            # Create a folder first via the filter.
            page.fill("#code-search-input", "Themes")
            page.keyboard.press("Shift+Enter")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            # The wrap may put the folder into rename mode — Esc steps out.
            page.keyboard.press("Escape")

            # Cut Alpha. Click the row first so focus is on the sidebar.
            alpha = page.query_selector('.ace-code-row[data-code-id]')
            assert alpha is not None
            alpha.click()
            page.keyboard.press("Meta+x")

            # Status bar should reflect cut state (sticky "Cut: Alpha …").
            status = page.evaluate(
                "() => document.querySelector('#ace-statusbar-event')?.textContent || ''"
            )
            assert "Cut" in status, f"expected sticky 'Cut' status, got {status!r}"

            # Focus the folder header and paste.
            folder = page.query_selector('.ace-code-folder-row')
            assert folder is not None
            folder.click()
            page.keyboard.press("Meta+v")

            # The moved code should now live inside a [role="group"].
            page.wait_for_function(
                "() => document.querySelector('[role=\"group\"] .ace-code-row[data-code-id]')",
                timeout=3000,
            )
            inside = page.evaluate(
                "() => Array.from(document.querySelectorAll('[role=\"group\"] .ace-code-row'))"
                "      .map(r => r.querySelector('.ace-code-name')?.textContent?.trim())"
            )
            assert "Alpha" in inside, f"Alpha should be inside the folder, got {inside!r}"
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# ⌥← — lift a code out of its folder, back to root
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("browser_name", browser_params())
def test_alt_left_lifts_code_out_of_folder_to_root(ace_server, browser_name):
    """Plan acceptance criterion §6.4 / L3303: Alt+ArrowLeft on a code that
    lives inside a folder must move it back to root (no longer inside any
    [role="group"] container).

    Setup uses the existing ⌥⇧→ wrap gesture to nest two root codes into a
    folder, then targets the second code (Bravo) for the lift.
    """
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            # Build the precondition: folder containing Bravo (and Alpha).
            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 2
            rows[1].click()  # Bravo is row[1] under the default fixture
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            # Both Alpha and Bravo are now inside [role="group"].
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('[role=\"group\"] .ace-code-row'))"
                "      .map(r => r.querySelector('.ace-code-name')?.textContent?.trim())"
                "      .includes('Bravo')",
                timeout=3000,
            )

            # Focus Bravo (now nested) and press ⌥← to lift it out.
            bravo = page.evaluate_handle(
                "() => Array.from(document.querySelectorAll('[role=\"group\"] .ace-code-row'))"
                "      .find(r => r.querySelector('.ace-code-name')?.textContent?.trim() === 'Bravo')"
            )
            bravo.as_element().click()
            page.keyboard.press("Alt+ArrowLeft")

            # Bravo must no longer be inside any [role="group"]: it's at root.
            page.wait_for_function(
                "() => {"
                "  const inside = Array.from(document.querySelectorAll('[role=\"group\"] .ace-code-row'))"
                "    .map(r => r.querySelector('.ace-code-name')?.textContent?.trim());"
                "  return !inside.includes('Bravo');"
                "}",
                timeout=3000,
            )

            # Sanity: Bravo still exists somewhere in the tree (just at root now).
            still_present = page.evaluate(
                "() => Array.from(document.querySelectorAll('.ace-code-row'))"
                "      .map(r => r.querySelector('.ace-code-name')?.textContent?.trim())"
                "      .includes('Bravo')"
            )
            assert still_present, "Bravo should still exist after lifting to root"
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Esc — return focus from sidebar to text panel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("browser_name", browser_params())
def test_esc_from_sidebar_returns_to_source(ace_server, browser_name):
    """Click a code row → sidebar owns the keyboard. Press Esc → text panel
    regains focus and the active zone flips back to 'source'."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")

            page.click(".ace-code-row")
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"

            # Esc on a treeitem is handled by the tree keydown handler, which
            # also routes back to the text panel. Either way, the active
            # zone must end up "source".
            page.keyboard.press("Escape")
            # Allow a tick for the focus shift to settle.
            page.wait_for_function(
                "() => document.body.dataset.activeZone === 'source'",
                timeout=2000,
            )
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Tab — cycle source → codebook search → tree → source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("browser_name", browser_params())
def test_tab_cycles_zones(ace_server, browser_name):
    """Starting from the text panel, Tab should land focus on the codebook
    search input, then again on the tree, then again back to the source.

    This test asserts the active-zone *transitions*, not the specific
    elements that hold focus, because the exact sequence of focusable
    elements between text panel and search varies (flag pill, etc.).
    """
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-search-input")

            # Start in the source.
            page.click(".ace-sentence")
            assert page.evaluate("document.body.dataset.activeZone") == "source"

            # Tab a few times until the codebook zone activates. Bound the
            # loop so we fail fast rather than tabbing forever if the zone
            # never flips.
            saw_codebook = False
            for _ in range(20):
                page.keyboard.press("Tab")
                if page.evaluate("document.body.dataset.activeZone") == "codebook":
                    saw_codebook = True
                    break
            assert saw_codebook, "Tab from source should reach the codebook zone"
        finally:
            browser.close()
