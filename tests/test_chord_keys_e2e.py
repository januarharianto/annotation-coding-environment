"""End-to-end tests for chord-key chord mode in bridge.js (Chromium)."""

import os
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

# Skip if no playwright
pytest.importorskip("playwright")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Start uvicorn on an ephemeral port; seed a project with 33+ codes; open it."""
    from ace.db.connection import create_project, open_project
    from ace.models.codebook import add_code
    from ace.models.source import add_source
    from ace.models.assignment import add_assignment
    from ace.models.project import list_coders

    tmp = tmp_path_factory.mktemp("chord_e2e")
    project_path = tmp / "chord.ace"
    create_project(str(project_path), "ChordTest")

    conn = open_project(str(project_path))
    try:
        sid = add_source(
            conn,
            "S01",
            "The lazy dog jumps over the fox.",
            "row",
        )
        coder = list_coders(conn)[0]["id"]
        add_assignment(conn, sid, coder)

        # 31 single-key codes
        for i in range(31):
            add_code(conn, f"Code {i:02d}", "#A91818")
        # 32nd: chord-only ("Privacy of data" → "pd")
        add_code(conn, "Privacy of data", "#557FE6")
        # Two more chord codes
        add_code(conn, "AI replacing humans", "#6DA918")
        add_code(conn, "Repetitive feedback", "#E67355")
    finally:
        conn.close()

    port = _free_port()
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "ace.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port)],
    )
    # Wait for server to come up
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    else:
        proc.terminate()
        pytest.fail(f"uvicorn did not start on port {port} within 5s")

    # Open the test project
    data = urllib.parse.urlencode({"path": str(project_path)}).encode()
    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/project/open", data=data)

    yield f"http://127.0.0.1:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _focus_first_sentence(page):
    """Click the first sentence span to put focus on the text panel."""
    page.click(".ace-sentence")
    page.wait_for_timeout(100)


def test_single_key_still_applies(server):
    """Regression: pressing 1 still applies the first code (no chord mode interference)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector(".ace-code-row")

        _focus_first_sentence(page)
        before = page.locator(".ace-code-chip").count()
        page.keyboard.press("1")
        page.wait_for_function(
            "() => document.querySelectorAll('.ace-code-chip').length > 0",
            timeout=2000,
        )
        after = page.locator(".ace-code-chip").count()

        assert after > before, "expected at least one code chip to be added"
        browser.close()


def test_chord_mode_apply_pd(server):
    """Press ; then p then d → applies 'Privacy of data'."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector(".ace-code-row[data-chord]")

        _focus_first_sentence(page)
        page.keyboard.press("Semicolon")
        # Body should reflect chord mode
        mode = page.evaluate("() => document.body.dataset.chordMode")
        assert mode == "awaiting"

        page.keyboard.press("p")
        page.keyboard.press("d")
        # Wait for the SPECIFIC chord we applied — earlier tests in the module
        # may have left an unrelated chip on the same source.
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('.ace-code-chip'))"
            "      .some(el => el.textContent.includes('Privacy'))",
            timeout=2000,
        )

        # Mode should have exited
        mode_after = page.evaluate("() => document.body.dataset.chordMode")
        assert mode_after in (None, "", "default")
        browser.close()


def test_chord_mode_escape_no_apply(server):
    """Press ; then Esc → no code applied, mode exits."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector(".ace-code-row")

        _focus_first_sentence(page)
        before = page.locator(".ace-code-chip").count()

        page.keyboard.press("Semicolon")
        assert page.evaluate("() => document.body.dataset.chordMode") == "awaiting"
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        mode_after = page.evaluate("() => document.body.dataset.chordMode")
        assert mode_after in (None, "", "default")
        after = page.locator(".ace-code-chip").count()
        assert before == after, "no chip should be added on Esc"
        browser.close()


def test_semicolon_in_search_input_is_literal(server):
    """Pressing ; while filter input focused does NOT enter chord mode."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")

        page.click("#code-search-input")
        page.keyboard.press("Semicolon")

        mode = page.evaluate("() => document.body.dataset.chordMode")
        assert mode in (None, "", "default"), \
            f"chord mode should not activate from inside input; got {mode}"

        # Search input should contain a semicolon character
        val = page.input_value("#code-search-input")
        assert ";" in val, f"expected ; in input; got {val!r}"
        browser.close()
