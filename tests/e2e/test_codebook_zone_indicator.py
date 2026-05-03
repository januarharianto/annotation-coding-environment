"""Active-zone indicator tests — body[data-active-zone] toggles between
'source' and 'codebook' as focus moves between the text panel and the
sidebar, and the visual state of the focused row reflects this."""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


@pytest.mark.parametrize("browser_name", browser_params())
def test_active_zone_toggles_on_focus(ace_server, browser_name):
    """Default = source · click the search input → codebook · click the
    text panel → source again."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")

            # Default zone is set to "source" by the inline init script in
            # bridge.js (line ~64).
            assert page.evaluate("document.body.dataset.activeZone") == "source"

            # Focus the codebook search input — focusin → _setActiveZone("codebook").
            page.click("#code-search-input")
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"

            # Click back into the source body.
            page.click("#text-panel")
            assert page.evaluate("document.body.dataset.activeZone") == "source"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_focused_row_styles_change_with_zone(ace_server, browser_name):
    """The focused code row wears the inverted slate-on-white treatment
    only while the codebook zone is active. Switching focus to the source
    clears the background (transparent)."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-code-row")

            # Click a row → roving tabindex=0 lands on it AND sidebar gains focus.
            page.click(".ace-code-row")
            # Confirm the active zone flipped to codebook.
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"

            # Background fades in via a CSS transition — poll until it
            # resolves to the inverted slate value #1a1d27 (rgb(26, 29, 39)).
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector("
                "  '.ace-code-row[tabindex=\"0\"]'"
                ")).backgroundColor === 'rgb(26, 29, 39)'",
                timeout=2000,
            )

            # Click into the source body. The codebook row keeps its
            # tabindex="0" (roving focus persists) but loses the background tint.
            page.click("#text-panel")
            assert page.evaluate("document.body.dataset.activeZone") == "source"
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector("
                "  '.ace-code-row[tabindex=\"0\"]'"
                ")).backgroundColor === 'rgba(0, 0, 0, 0)'",
                timeout=2000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_focused_sentence_thickness_changes_with_zone(ace_server, browser_name):
    """Focused sentence shows 2px underline when source is active, 1.5px
    when codebook is active (the dimmed cue from coding.css L1499–1504)."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")

            # Click first sentence → source zone, sentence gets .ace-sentence--focused.
            page.click(".ace-sentence")
            assert page.evaluate("document.body.dataset.activeZone") == "source"
            page.wait_for_selector(".ace-sentence--focused")

            thickness_source = page.evaluate(
                "() => getComputedStyle("
                "document.querySelector('.ace-sentence--focused')"
                ").textDecorationThickness"
            )
            # Strong cue when source is active. The default rule is 2px.
            assert thickness_source.startswith("2"), (
                f"expected ~2px when source active, got {thickness_source!r}"
            )

            # Switch to codebook by clicking a code row.
            page.click(".ace-code-row")
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"
            thickness_codebook = page.evaluate(
                "() => getComputedStyle("
                "document.querySelector('.ace-sentence--focused')"
                ").textDecorationThickness"
            )
            # Dimmed cue: 1.5px (coding.css L1503).
            assert thickness_codebook.startswith("1.5"), (
                f"expected ~1.5px when codebook active, got {thickness_codebook!r}"
            )
        finally:
            browser.close()
