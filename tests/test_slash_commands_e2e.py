"""End-to-end tests for slash commands and Cmd+Enter creation in the search input."""

import socket
import subprocess
import time
import urllib.parse
import urllib.request

import pytest

pytest.importorskip("playwright")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Start uvicorn on an ephemeral port; seed a project; open it."""
    from ace.db.connection import create_project, open_project
    from ace.models.codebook import add_code
    from ace.models.source import add_source
    from ace.models.assignment import add_assignment
    from ace.models.project import list_coders

    tmp = tmp_path_factory.mktemp("slash_e2e")
    project_path = tmp / "slash.ace"
    create_project(str(project_path), "SlashTest")

    conn = open_project(str(project_path))
    try:
        sid = add_source(conn, "S01", "The lazy dog jumps.", "row")
        coder = list_coders(conn)[0]["id"]
        add_assignment(conn, sid, coder)
        add_code(conn, "alpha", "#ff0000")
        add_code(conn, "beta", "#00ff00")
        add_code(conn, "gamma", "#0000ff")
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


def test_cmd_enter_creates_code_with_matches_visible(server):
    """Cmd+Enter creates a code even when filter has matches.

    The filter text 'alph' fuzzy-matches the seeded 'alpha' code (so matches
    are visible in the tree); Cmd+Enter creates a NEW code named 'alph'
    instead of applying the existing match.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        page.fill("#code-search-input", "alph")  # matches 'alpha' but not equal
        # Verify a match exists
        page.wait_for_selector(".ace-code-row[data-code-id]:not([style*='display: none'])")
        # Cmd+Enter (Meta on macOS, Control on Linux/Windows — Playwright handles "Meta")
        page.press("#code-search-input", "Meta+Enter")
        # New code "alph" should be created (even though 'alpha' was a match)
        # Wait for input to clear
        page.wait_for_function("document.getElementById('code-search-input').value === ''")
        # Wait for the OOB sidebar swap to settle
        page.wait_for_timeout(500)
        names = page.locator(".ace-code-name").all_text_contents()
        # Both the original 'alpha' and the newly-created 'alph' should exist
        assert "alph" in names, f"Expected 'alph' in rows, got: {names}"
        assert "alpha" in names, f"Expected 'alpha' still present, got: {names}"
        browser.close()


def test_zero_match_enter_creates_code(server):
    """Plain Enter in zero-match state creates the code via the inline create row."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        page.fill("#code-search-input", "themes")
        # Wait for the zero-match create row to appear
        page.wait_for_selector(".ace-create-row")
        page.press("#code-search-input", "Enter")
        # Input clears, new "themes" code appears
        page.wait_for_function("document.getElementById('code-search-input').value === ''")
        page.wait_for_timeout(500)
        names = page.locator(".ace-code-name").all_text_contents()
        assert "themes" in names, f"Expected 'themes' in rows, got: {names}"
        browser.close()


def test_slash_shows_command_palette(server):
    """Typing / shows command suggestions in the tree."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        page.fill("#code-search-input", "/")
        page.wait_for_selector(".ace-slash-mode")
        items = page.locator(".ace-slash-item").all_text_contents()
        assert any("/code" in i for i in items), f"Items: {items}"
        assert any("/folder" in i for i in items), f"Items: {items}"
        browser.close()


def test_slash_folder_creates_folder(server):
    """`/folder Themes` + Enter creates a folder."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        page.fill("#code-search-input", "/folder Themes")
        page.wait_for_selector(".ace-slash-item[data-selected='true']")
        page.press("#code-search-input", "Enter")
        page.wait_for_selector(".ace-code-folder-row .ace-folder-label")
        page.wait_for_timeout(500)
        labels = page.locator(".ace-folder-label").all_text_contents()
        assert "Themes" in labels, f"Labels: {labels}"
        browser.close()


def test_slash_case_insensitive(server):
    """Slash command name matches case-insensitively."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        page.fill("#code-search-input", "/Code mixedcase")
        page.wait_for_selector(".ace-slash-item[data-selected='true']")
        page.press("#code-search-input", "Enter")
        page.wait_for_function("document.getElementById('code-search-input').value === ''")
        page.wait_for_timeout(500)
        names = page.locator(".ace-code-name").all_text_contents()
        assert "mixedcase" in names, f"Names: {names}"
        browser.close()


def test_slash_empty_arg_does_not_commit(server):
    """Slash command with empty argument does not commit on Enter."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        page.fill("#code-search-input", "/code   ")  # whitespace only
        page.wait_for_selector(".ace-slash-mode")
        # Suggestion description should hint
        descs = page.locator(".ace-slash-item .desc").all_text_contents()
        assert any("Type a name" in d for d in descs), f"Descs: {descs}"
        # Input value persists; Enter does NOT clear
        before = page.input_value("#code-search-input")
        page.press("#code-search-input", "Enter")
        after = page.input_value("#code-search-input")
        assert after == before, f"Input changed: before={before!r} after={after!r}"
        browser.close()


def test_esc_exits_slash_mode(server):
    """Esc exits slash mode and clears input."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        page.fill("#code-search-input", "/code Foo")
        page.wait_for_selector(".ace-slash-mode")
        page.press("#code-search-input", "Escape")
        # Slash mode UI gone, input cleared, tree visible
        page.wait_for_function("document.getElementById('code-search-input').value === ''")
        assert page.locator(".ace-slash-mode").count() == 0
        browser.close()


def test_zero_match_shows_single_create_row(server):
    """Zero-match filter renders exactly one create affordance, not two."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        # Unique-enough string that no prior test has created.
        page.fill("#code-search-input", "zzz_no_match_xyz")
        page.wait_for_selector(".ace-create-row")
        # Only one create affordance — the legacy .ace-create-prompt should be gone
        assert page.locator(".ace-create-row").count() == 1
        assert page.locator(".ace-create-prompt").count() == 0
        browser.close()


def test_filter_then_slash_then_empty_restores_tree(server):
    """Active filter + entering slash mode + clearing input restores rows to original positions."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        # Type a filter that matches one code
        page.fill("#code-search-input", "alpha")
        # Wait for filter to apply (matched row stays visible)
        page.wait_for_function(
            "document.querySelectorAll('.ace-code-row:not([style*=\"display: none\"])').length === 1"
        )
        # Now enter slash mode by replacing input value with "/"
        page.fill("#code-search-input", "/")
        page.wait_for_selector(".ace-slash-mode")
        # Now backspace to empty — slash mode exits, tree should restore cleanly
        page.fill("#code-search-input", "")
        page.wait_for_function(
            "!document.querySelector('.ace-slash-mode')"
        )
        # All three seeded codes should be visible (no stuck filter state)
        names = page.locator(".ace-code-name").all_text_contents()
        for expected in ["alpha", "beta", "gamma"]:
            assert expected in names, f"missing {expected} after slash mode exit"
        browser.close()


def test_slash_folder_duplicate_does_not_wipe_text_panel(server):
    """Creating a folder twice with the same name leaves the coding view intact."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{server}/code")
        page.wait_for_selector("#code-search-input")
        # First /folder Themes — should succeed
        page.fill("#code-search-input", "/folder Themes")
        page.wait_for_selector(".ace-slash-item[data-selected='true']")
        page.press("#code-search-input", "Enter")
        page.wait_for_function(
            "Array.from(document.querySelectorAll('.ace-folder-label')).some(l => l.textContent === 'Themes')"
        )
        # Second /folder Themes — should NOT wipe the text panel
        page.fill("#code-search-input", "/folder Themes")
        page.wait_for_selector(".ace-slash-item[data-selected='true']")
        page.press("#code-search-input", "Enter")
        # Text panel must still contain the source-rendering surface
        # (`#text-panel` exists and still has its sentence content).
        page.wait_for_timeout(500)  # let any failure manifest
        assert page.locator("#text-panel").count() == 1
        assert page.locator(".ace-sentence").count() > 0, (
            "text panel was wiped — duplicate /folder ate the coding view"
        )
        browser.close()
