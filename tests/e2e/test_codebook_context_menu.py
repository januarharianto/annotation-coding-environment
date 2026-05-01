"""Context-menu tests for the codebook sidebar.

The single contextmenu dispatcher in bridge.js (around L2236) routes
right-clicks on code rows / folder rows / empty tree to three different
item lists. These tests confirm:

  * Right-click on a code row opens the menu with the expected items.
  * Outside-click and Esc both dismiss the menu.

Submenu navigation (Move to folder ▸ …) is not exercised — keyboard
gestures already cover the underlying move actions, and submenu opening
is sensitive to mouse-hover timing across engines.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


_EXPECTED_CODE_ITEMS = ["Cut", "Paste here", "Rename", "Delete"]


@pytest.mark.parametrize("browser_name", browser_params())
def test_right_click_on_code_row_opens_menu_with_expected_items(
    ace_server, browser_name
):
    """Right-click on a code row → .ace-context-menu appears containing
    Cut, Paste here, Rename, and Delete entries."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            row = page.query_selector(".ace-code-row")
            assert row is not None
            row.click(button="right")

            page.wait_for_selector(".ace-context-menu", timeout=2000)
            labels = page.evaluate(
                "() => Array.from(document.querySelectorAll("
                "  '.ace-context-menu .ace-context-menu-item'"
                ")).map(el => el.textContent.trim())"
            )
            for expected in _EXPECTED_CODE_ITEMS:
                assert any(expected in label for label in labels), (
                    f"expected '{expected}' in context menu, got {labels!r}"
                )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_outside_click_dismisses_context_menu(ace_server, browser_name):
    """Clicking anywhere outside the menu closes it."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            row = page.query_selector(".ace-code-row")
            assert row is not None
            row.click(button="right")
            page.wait_for_selector(".ace-context-menu", timeout=2000)
            # _renderContextMenu registers its outside-click + Esc listeners
            # via setTimeout(..., 0) — give the JS event loop a tick to flush
            # before we try to trigger them. Otherwise the Esc/click that
            # follows beats the listener registration and the menu sticks.
            page.wait_for_timeout(50)

            # Click somewhere clearly outside the menu — the text panel
            # is the safest target since it's not a sidebar interactive.
            page.click("#text-panel")
            page.wait_for_selector(".ace-context-menu", state="detached", timeout=2000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_escape_dismisses_context_menu(ace_server, browser_name):
    """Esc dismisses the context menu (handler bound at capture phase)."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            row = page.query_selector(".ace-code-row")
            assert row is not None
            row.click(button="right")
            page.wait_for_selector(".ace-context-menu", timeout=2000)
            # See the outside-click test above for why we wait. The Esc
            # handler is added via setTimeout(..., 0) inside
            # _renderContextMenu — without this the keypress beats the
            # listener registration.
            page.wait_for_timeout(50)

            page.keyboard.press("Escape")
            page.wait_for_selector(".ace-context-menu", state="detached", timeout=2000)
        finally:
            browser.close()
