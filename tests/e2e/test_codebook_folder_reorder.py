"""F7 — folder reorder via ⌥⇧↑/↓ must persist across OOB sidebar swaps.

Regression: the original ⌥⇧↑ keybinding called `_persistCodeOrder`, which
collected only `[data-code-id]` rows. Folder reorders moved the DOM
locally but never wrote `sort_order`, so the next OOB swap (apply a
code, undo, etc.) snapped the folder back to its prior position.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


def _focus_folder_row(page, folder_label):
    """Click a folder row identified by its label text, then verify focus.

    Direct focus via JS is more robust than .click() — the latter can be
    intercepted by HTMX afterSettle handlers that fire after a recent
    sidebar swap and steal focus back to the text panel.
    """
    page.evaluate(
        "(label) => {"
        "  const row = Array.from(document.querySelectorAll('.ace-code-folder-row'))"
        "    .find(r => r.querySelector('.ace-folder-label')?.textContent.trim() === label);"
        "  if (!row) throw new Error('folder row not found: ' + label);"
        "  document.querySelectorAll('#code-tree [role=\"treeitem\"][tabindex=\"0\"]')"
        "    .forEach(el => el.setAttribute('tabindex', '-1'));"
        "  row.setAttribute('tabindex', '0');"
        "  row.focus();"
        "}",
        folder_label,
    )
    page.wait_for_function(
        "(label) => document.activeElement?.classList.contains('ace-code-folder-row') && "
        "document.activeElement?.querySelector('.ace-folder-label')?.textContent.trim() === label",
        arg=folder_label,
        timeout=2000,
    )


@pytest.mark.parametrize("browser_name", browser_params())
def test_folder_reorder_survives_oob_sidebar_swap(ace_server, browser_name):
    """⌥⇧↑ on a folder row must persist after an action that re-renders the sidebar.

    Setup: create two folders ("Alpha-folder" then "Bravo-folder") via the
    filter so they sit adjacent at the top of the tree. Focus Bravo-folder,
    press ⌥⇧↑ to move it above Alpha-folder. Apply a code by clicking it
    in the sidebar — this triggers a full sidebar re-render via OOB swap.
    The post-swap DOM must still show Bravo-folder above Alpha-folder.
    """
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            # --- Create Alpha-folder via filter + Shift+Enter.
            page.fill("#code-search-input", "Alpha-folder")
            page.keyboard.press("Shift+Enter")
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('.ace-folder-label'))"
                "      .some(el => el.textContent.trim() === 'Alpha-folder')",
                timeout=3000,
            )
            page.keyboard.press("Escape")  # exit any inline-rename state

            # --- Create Bravo-folder.
            page.fill("#code-search-input", "Bravo-folder")
            page.keyboard.press("Shift+Enter")
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('.ace-folder-label'))"
                "      .some(el => el.textContent.trim() === 'Bravo-folder')",
                timeout=3000,
            )
            page.keyboard.press("Escape")
            # Let any in-flight afterSettle finish before we touch focus.
            page.wait_for_timeout(150)

            # Sanity: order in DOM is Alpha-folder, then Bravo-folder.
            initial = page.evaluate(
                "() => Array.from(document.querySelectorAll('.ace-folder-label'))"
                "      .map(el => el.textContent.trim())"
            )
            assert initial.index("Alpha-folder") < initial.index("Bravo-folder"), (
                f"expected Alpha-folder before Bravo-folder, got {initial!r}"
            )

            # --- Focus Bravo-folder row and reorder up.
            _focus_folder_row(page, "Bravo-folder")
            page.keyboard.press("Alt+Shift+ArrowUp")

            # Wait for the reorder to settle in DOM.
            page.wait_for_function(
                "() => { "
                "const labels = Array.from(document.querySelectorAll('.ace-folder-label'))"
                "  .map(el => el.textContent.trim());"
                "return labels.indexOf('Bravo-folder') < labels.indexOf('Alpha-folder');"
                "}",
                timeout=3000,
            )

            # --- Trigger a full sidebar re-render via OOB swap.
            # The /api/codes/reorder endpoint with an empty list is a no-op
            # write that still returns a fresh sidebar (used by the client's
            # `_refreshSidebar` helper). If the folder reorder didn't make it
            # to the database, this swap will resurrect the prior order.
            page.evaluate(
                "() => htmx.ajax('POST', '/api/codes/reorder', {"
                "  target: '#code-sidebar',"
                "  swap: 'outerHTML',"
                "  values: { code_ids: '[]', current_index: window.__aceCurrentIndex || 0 },"
                "})"
            )
            # Wait for HTMX to settle the response.
            page.wait_for_function(
                "() => !document.body.classList.contains('htmx-request') && "
                "!document.querySelector('.htmx-request')",
                timeout=3000,
            )
            page.wait_for_timeout(150)

            # --- Post-swap assertion: Bravo-folder must STILL be above Alpha-folder.
            final = page.evaluate(
                "() => Array.from(document.querySelectorAll('.ace-folder-label'))"
                "      .map(el => el.textContent.trim())"
            )
            assert final.index("Bravo-folder") < final.index("Alpha-folder"), (
                f"folder reorder did NOT survive OOB sidebar swap: order is {final!r}. "
                "Expected Bravo-folder before Alpha-folder."
            )
        finally:
            browser.close()
