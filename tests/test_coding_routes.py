"""Tests for the coding page route."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.fixture()
def client_with_sources(tmp_path):
    """Create a project with 3 sources, 2 codes, and a coder."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    # create_project auto-creates a "default" coder
    coders = list_coders(conn)
    coder_id = coders[0]["id"]

    # Add sources
    add_source(conn, "S001", "First document content for coding.", "row")
    add_source(conn, "S002", "Second document with different text.", "row")
    add_source(conn, "S003", "Third document for testing purposes.", "row")

    # Add codes
    add_code(conn, "Theme A", "#BF6030")
    add_code(conn, "Theme B", "#30A64E")

    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        yield client, coder_id


@pytest.fixture()
def client_with_codes(tmp_path):
    """Like client_with_sources but also returns code IDs and db_path."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    coders = list_coders(conn)
    coder_id = coders[0]["id"]

    add_source(conn, "S001", "First document content for coding.", "row")
    add_source(conn, "S002", "Second document with different text.", "row")

    code_a = add_code(conn, "Theme A", "#BF6030")
    code_b = add_code(conn, "Theme B", "#30A64E")

    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        # Visit the coding page once to auto-create assignments
        client.get("/code")
        yield client, coder_id, code_a, code_b, str(db_path)


def test_coding_page_renders(client_with_sources):
    """GET /code renders the coding page with swap zones."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "coding-workspace" in resp.text
    assert "code-sidebar" in resp.text
    assert "text-panel" in resp.text
    assert "ace-legend" in resp.text
    # Source notes UI (Task R1 — drawer pattern)
    assert 'id="note-pill"' in resp.text
    assert 'id="note-drawer"' in resp.text
    assert 'id="note-textarea"' in resp.text
    assert 'role="complementary"' in resp.text


def test_coding_page_redirects_without_project():
    """GET /code without project redirects to /."""
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/code", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"


def test_coding_page_redirects_without_coder(tmp_path):
    """GET /code without coder_id redirects to /."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        # coder_id not set
        resp = client.get("/code", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"


def test_coding_page_redirects_without_sources(tmp_path):
    """GET /code with no sources redirects to /import."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    coders = list_coders(conn)
    coder_id = coders[0]["id"]
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        resp = client.get("/code", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/import"


def test_coding_page_shows_source_content(client_with_sources):
    """First source text is visible in the text panel."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "First document content for coding." in resp.text


def test_coding_page_shows_codes(client_with_sources):
    """Codes appear in the sidebar."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "Theme A" in resp.text
    assert "Theme B" in resp.text


def test_coding_page_shows_project_name(client_with_sources):
    """Project name appears in the header."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "Test Project" in resp.text


def test_coding_page_index_param(client_with_sources):
    """Navigating to index=1 shows second source."""
    client, _ = client_with_sources
    resp = client.get("/code?index=1")
    assert resp.status_code == 200
    assert "Second document with different text." in resp.text


def test_coding_page_auto_creates_assignments(client_with_sources):
    """Assignments are auto-created for the coder."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    # Grid tile container + JSON payload should exist
    assert 'id="ace-grid-tiles"' in resp.text
    assert 'id="ace-sources-data"' in resp.text


def test_coding_page_includes_idiomorph(client_with_sources):
    """The coding page includes the idiomorph extension script."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    assert "idiomorph-ext.min.js" in resp.text


def test_sidebar_has_brand_and_nav_has_source(client_with_sources):
    """Sidebar shows ACE brand, nav shows flag button."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    assert "ace-sidebar-brand" in html
    assert "ACE" in html
    assert 'aria-label="Toggle flag (Shift+F)"' in html


def test_sidebar_has_aria_tree_roles(client_with_sources):
    """Sidebar renders with ARIA treeview roles."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    assert 'role="tree"' in html
    assert 'aria-label="Code list"' in html
    assert 'role="treeitem"' in html
    assert 'role="group"' in html


# ---------------------------------------------------------------------------
# Annotation CRUD routes
# ---------------------------------------------------------------------------


def test_annotate(client_with_codes):
    """POST /api/code/apply creates annotation and returns updated HTML."""
    client, coder_id, code_a, _, db_path = client_with_codes
    resp = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert resp.status_code == 200
    assert "text-panel" in resp.text
    # The annotation text should appear in the response
    assert "First" in resp.text

    # Verify annotation exists in the DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["selected_text"] == "First"


def test_delete_annotation(client_with_codes):
    """POST /api/code/delete-annotation soft-deletes an annotation."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # First create an annotation
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )

    # Get the annotation ID
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ann = conn.execute(
        "SELECT id FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()
    ann_id = ann["id"]
    conn.close()

    # Delete it
    resp = client.post(
        "/api/code/delete-annotation",
        data={"annotation_id": ann_id, "current_index": 0},
    )
    assert resp.status_code == 200
    assert "text-panel" in resp.text

    # Verify soft-deleted in DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    active = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    deleted = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NOT NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 0
    assert len(deleted) == 1


def test_undo_after_annotate(client_with_codes):
    """Undo reverses the last annotation."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # Create annotation
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )

    # Undo
    resp = client.post(
        "/api/code/undo",
        data={"current_index": 0},
    )
    assert resp.status_code == 200

    # Verify annotation is now soft-deleted
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    active = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 0


def test_redo_after_undo(client_with_codes):
    """Redo restores the undone annotation."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # Create annotation
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )

    # Undo
    client.post("/api/code/undo", data={"current_index": 0})

    # Redo
    resp = client.post("/api/code/redo", data={"current_index": 0})
    assert resp.status_code == 200

    # Verify annotation is active again
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    active = conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 1
    assert active[0]["selected_text"] == "First"


# ---------------------------------------------------------------------------
# Navigation + flag routes
# ---------------------------------------------------------------------------


def test_navigate_next(client_with_sources):
    """POST /api/code/navigate moves to target source and returns all zones."""
    client, _ = client_with_sources
    # Visit /code first so assignments are auto-created
    client.get("/code")
    resp = client.post(
        "/api/code/navigate",
        data={"current_index": "0", "target_index": "1"},
    )
    assert resp.status_code == 200
    # Should contain the second source's content
    assert "Second document with different text." in resp.text
    # Should contain all OOB swap zones
    assert 'id="ace-sidebar-grid"' in resp.text
    assert 'id="code-sidebar"' in resp.text
    # Should have HX-Trigger header with ace-navigate event
    assert "HX-Trigger" in resp.headers
    assert "ace-navigate" in resp.headers["HX-Trigger"]


def test_navigate_auto_completes_in_progress(client_with_codes):
    """Navigate away from an in_progress source auto-completes it."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # Create an annotation on source 0 to make it in_progress
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )

    # Verify source 0 is now in_progress
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM assignment WHERE coder_id = ? ORDER BY rowid LIMIT 1",
        (coder_id,),
    ).fetchone()
    assert row["status"] == "in_progress"
    conn.close()

    # Navigate from 0 to 1
    client.post(
        "/api/code/navigate",
        data={"current_index": "0", "target_index": "1"},
    )

    # Source 0 should now be complete
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT status FROM assignment WHERE coder_id = ? "
        "ORDER BY rowid",
        (coder_id,),
    ).fetchall()
    conn.close()
    assert rows[0]["status"] == "complete"
    # Source 1 should be in_progress (auto-started)
    assert rows[1]["status"] == "in_progress"


def test_flag_source(client_with_sources):
    """POST /api/code/flag toggles the flagged status."""
    client, _ = client_with_sources
    # Visit /code first so assignments are auto-created
    client.get("/code")

    # Flag source 0
    resp = client.post(
        "/api/code/flag",
        data={"source_index": "0"},
    )
    assert resp.status_code == 200
    assert "flagged" in resp.text.lower()

    # Flag again to unflag
    resp = client.post(
        "/api/code/flag",
        data={"source_index": "0"},
    )
    assert resp.status_code == 200


def test_flag_source_toggle_roundtrip(client_with_codes):
    """Flagging twice returns to in_progress."""
    client, coder_id, _, _, db_path = client_with_codes

    # Flag
    client.post("/api/code/flag", data={"source_index": "0"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM assignment WHERE coder_id = ? ORDER BY rowid LIMIT 1",
        (coder_id,),
    ).fetchone()
    assert row["status"] == "flagged"
    conn.close()

    # Unflag
    client.post("/api/code/flag", data={"source_index": "0"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM assignment WHERE coder_id = ? ORDER BY rowid LIMIT 1",
        (coder_id,),
    ).fetchone()
    assert row["status"] == "in_progress"
    conn.close()


def test_coding_context_includes_note_state(client_with_codes):
    """_coding_context exposes note text, has_note flag, and notes presence set."""
    import sqlite3
    from ace.models.assignment import get_assignments_for_coder
    from ace.models.source_note import upsert_note
    from ace.routes.pages import _coding_context

    client, coder_id, code_a, code_b, db_path = client_with_codes

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        assignments = get_assignments_for_coder(conn, coder_id)
        s1 = assignments[0]["source_id"]
        s2 = assignments[1]["source_id"]

        # No notes initially
        ctx0 = _coding_context(conn, coder_id, 0)
        assert ctx0["current_note_text"] == ""
        assert ctx0["has_note"] is False
        assert ctx0["source_ids_with_notes"] == set()

        # Add a note on source 1, view source 1
        upsert_note(conn, s1, coder_id, "Hello note")
        ctx1 = _coding_context(conn, coder_id, 0)
        assert ctx1["current_note_text"] == "Hello note"
        assert ctx1["has_note"] is True
        assert ctx1["source_ids_with_notes"] == {s1}

        # View source 2 — different has_note state, same presence set
        ctx2 = _coding_context(conn, coder_id, 1)
        assert ctx2["current_note_text"] == ""
        assert ctx2["has_note"] is False
        assert ctx2["source_ids_with_notes"] == {s1}

        # Add a second note
        upsert_note(conn, s2, coder_id, "Another")
        ctx3 = _coding_context(conn, coder_id, 1)
        assert ctx3["has_note"] is True
        assert ctx3["source_ids_with_notes"] == {s1, s2}
    finally:
        conn.close()


def test_invalid_code_name_returns_status_oob_swap(client_with_codes):
    """Code validation error returns an OOB swap into the status bar, not #toast."""
    client, _coder, _a, _b, _path = client_with_codes
    # Whitespace-only name passes Form(...) presence check but fails .strip() guard
    resp = client.post("/api/codes", data={"name": "   "})
    assert resp.status_code == 200
    assert "ace-statusbar-event" in resp.text
    # Errors must also reach screen readers via the assertive live region.
    assert "ace-live-region-assertive" in resp.text
    assert 'id="toast"' not in resp.text


def test_undo_does_not_set_x_ace_toast_and_announces_via_live_region(client_with_codes):
    """Undo action is silent in the status bar but announces to the polite live region."""
    client, _coder_id, code_a, _code_b, _db_path = client_with_codes
    # Create an annotation we can undo
    client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    resp = client.post("/api/code/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "X-ACE-Toast" not in resp.headers
    assert 'id="ace-live-region"' in resp.text
    assert "Annotation removed" in resp.text


def test_flag_does_not_set_x_ace_toast_and_announces_via_live_region(client_with_codes):
    """Flag action is silent in the status bar but announces to the polite live region."""
    client, _coder_id, _code_a, _code_b, _db_path = client_with_codes
    resp = client.post("/api/code/flag", data={"source_index": "0"})
    assert resp.status_code == 200
    assert "X-ACE-Toast" not in resp.headers
    assert 'id="ace-live-region"' in resp.text
    assert "Source flagged" in resp.text


# ---------------------------------------------------------------------------
# Grid cell pre-computation
# ---------------------------------------------------------------------------


def test_coding_context_emits_sources_json(client_with_codes):
    """sources_json is a flat per-source array suitable for client rendering."""
    import sqlite3
    from ace.routes.pages import _coding_context

    client, coder_id, code_a, _, db_path = client_with_codes
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ctx = _coding_context(conn, coder_id, 0)
    finally:
        conn.close()

    assert "sources_json" in ctx
    data = ctx["sources_json"]
    assert isinstance(data, list)
    assert len(data) == ctx["total_sources"]

    first = data[0]
    for key in ("index", "source_id", "display_id", "count", "flagged", "note"):
        assert key in first, f"sources_json[0] missing key {key!r}"
    assert first["index"] == 0
    assert isinstance(first["count"], int)
    assert isinstance(first["flagged"], bool)
    assert isinstance(first["note"], bool)
    # No annotations yet → count is 0, flags all false
    assert first["count"] == 0
    assert first["flagged"] is False
    assert first["note"] is False


def test_sidebar_grid_replaces_popover(client_with_codes):
    """Coding page renders the sparkline + tile grid, not the legacy overlay."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    resp = client.get("/code")
    body = resp.text

    # New markers present
    assert 'id="ace-sidebar-grid"' in body
    assert 'id="ace-grid-spark"' in body
    assert 'id="ace-grid-tiles"' in body
    assert 'id="ace-grid-inspector"' in body
    assert 'id="ace-sources-data"' in body

    # Legacy markers gone
    for gone in (
        "source-grid-overlay",
        "ace-grid-overlay",
        "ace-grid-popover",
        "aceToggleGrid",
        "ace-grid-cell--ann-1",
        "ace-grid-cell--ann-3",
        "ace-grid-cell--ann-6",
        "ace-grid-cell--complete",
    ):
        assert gone not in body, f"legacy marker {gone!r} still in response"


def test_grid_separator_aria(client_with_codes):
    """Resize separator has the full ARIA contract required by WAI-ARIA."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    body = client.get("/code").text

    assert 'class="ace-sidebar-vsplit"' in body
    required = [
        'role="separator"',
        'aria-orientation="horizontal"',
        'aria-controls="ace-sidebar-grid"',
        'aria-valuemin=',
        'aria-valuemax=',
        'aria-valuenow=',
        'aria-valuetext=',
        'tabindex="0"',
    ]
    for attr in required:
        assert attr in body, f"separator missing {attr!r}"


def test_counter_chip_is_static(client_with_codes):
    """Counter span stays visible but has no onclick or ⚇ glyph."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    body = client.get("/code").text

    # Static text still present in flag row
    assert 'class="ace-nav-counter"' in body
    # Clickable affordance gone
    assert "aceToggleGrid" not in body
    assert "\u2687" not in body


def test_grid_scaffold_and_live_region(client_with_codes):
    """Tile grid container + live region scaffold present on the coding page."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    body = client.get("/code").text

    # Live region wired up with the correct aria-live value
    assert 'id="ace-grid-live"' in body
    assert 'aria-live="polite"' in body

    # Tile grid host exists (tiles are rendered client-side)
    assert 'id="ace-grid-tiles"' in body
    assert 'role="grid"' in body

    # Sources payload present
    assert 'id="ace-sources-data"' in body


def test_annotate_refreshes_grid(client_with_codes):
    """POST /api/code/apply returns OOB sources blob with incremented count."""
    import json
    import re
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)

    resp = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert resp.status_code == 200
    assert 'id="code-sidebar"' in resp.text
    assert 'id="ace-sources-data"' in resp.text

    # Parse the OOB blob and confirm the first source now has count == 1.
    # The OOB payload is JSON with < > & escaped as \u003c \u003e \u0026 (Task 4 fix);
    # those are valid inside JSON strings so json.loads accepts it as-is.
    m = re.search(
        r'id="ace-sources-data"[^>]*hx-swap-oob[^>]*>([^<]*)</script>',
        resp.text,
    )
    assert m, "ace-sources-data OOB fragment not found in response"
    payload = json.loads(m.group(1))
    assert payload[0]["count"] == 1


def test_delete_refreshes_grid(client_with_codes):
    """Deleting an annotation returns OOB sources blob with decremented count."""
    import json
    import re
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)

    # Create an annotation, then delete it
    create = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert create.status_code == 200

    # Pull the new annotation id from the ann-data OOB blob (data-annotations attr)
    m = re.search(r'data-annotations="([^"]+)"', create.text)
    assert m, "ann-data payload missing from create response"
    payload = m.group(1).replace("&#34;", '"').replace("&quot;", '"')
    anns = json.loads(payload)
    assert anns, "ann-data was empty after apply"
    ann_id = anns[0]["id"]

    # Delete the annotation
    resp = client.post(
        "/api/code/delete-annotation",
        data={
            "annotation_id": ann_id,
            "current_index": 0,
        },
    )
    assert resp.status_code == 200, (
        f"delete returned {resp.status_code}: {resp.text[:200]}"
    )
    assert 'id="code-sidebar"' in resp.text
    assert 'id="ace-sources-data"' in resp.text

    # Parse the OOB sources blob — source 0's count should be back to 0
    m = re.search(
        r'id="ace-sources-data"[^>]*hx-swap-oob[^>]*>([^<]*)</script>',
        resp.text,
    )
    assert m, "ace-sources-data OOB fragment missing after delete"
    sources = json.loads(m.group(1))
    assert sources[0]["count"] == 0


def test_coding_page_has_collapsible_grid_header(client_with_codes):
    """Source-grid header is a single button with chevron + 'Sources' label, no total count."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text

    # Collapsible button replaces the old header span pair
    assert 'id="ace-grid-collapse-btn"' in body
    assert 'aria-expanded="true"' in body
    assert 'class="ace-grid-header"' in body
    assert "ace-grid-chevron" in body
    # Title is now "Source map" using the shared panel-heading class,
    # and the button sits inside an <h2> (W3C accordion pattern).
    assert '<span class="ace-panel-heading">Source map</span>' in body
    # The button is wrapped in an h2 for document-outline semantics
    assert body.count("<h2") >= 1
    # Total count no longer in header (it still appears in range label, which is
    # client-rendered)
    assert 'class="ace-grid-meta"' not in body
    # Wrapper for collapse state exists
    assert 'id="ace-grid-content"' in body


def test_coding_page_has_inline_collapse_restore_script(client_with_codes):
    """Inline head script restores ace-grid-collapsed dataset before CSS loads."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text
    assert 'localStorage.getItem("ace-grid-collapsed")' in body
    assert "dataset.aceGridCollapsed" in body


def test_coding_page_text_header_has_three_rows(client_with_sources):
    """Text panel header is wrapped in .ace-text-header with nav, event row, flag row in that order."""
    client, _ = client_with_sources
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text

    # Wrapper present
    assert 'class="ace-text-header"' in body
    # Three child rows — ordering matters
    nav_idx = body.find('class="ace-text-nav"')
    event_idx = body.find('class="ace-text-event-row"')
    flag_idx = body.find('class="ace-flag-row"')
    assert nav_idx > 0 and event_idx > 0 and flag_idx > 0
    assert nav_idx < event_idx < flag_idx

    # Event pill element present, empty on initial render
    assert 'id="ace-text-event-pill"' in body
    assert 'class="ace-text-event-pill"' in body
    assert 'role="status"' in body
    assert 'aria-live="polite"' in body


def test_oob_status_emits_both_statusbar_and_pill_fragments():
    """_oob_status emits OOB fragments for both the statusbar and the text pill."""
    from ace.routes.api import _oob_status

    response = _oob_status("Validation failed", "err")
    body = response.body.decode("utf-8")

    # Statusbar fragment present
    assert 'id="ace-statusbar-event"' in body
    assert "ace-statusbar-event--err" in body
    # Text-panel pill fragment present
    assert 'id="ace-text-event-pill"' in body
    assert "ace-text-event-pill--err" in body
    # Both use OOB outerHTML swap
    assert body.count('hx-swap-oob="outerHTML"') >= 2
    # Message HTML-escaped and present in both fragments
    assert body.count("Validation failed") >= 2
    # ARIA live region fragment also present (assertive for err)
    assert 'id="ace-live-region-assertive"' in body


def test_coding_page_shows_project_name_in_sidebar_brand(client_with_sources):
    """Project name appears inside the sidebar brand section."""
    client, _ = client_with_sources
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text
    # Class is unique to this span
    assert 'class="ace-sidebar-brand-project"' in body
    # Fixture uses test.ace → stem is "test"
    assert ">test<" in body


def test_oob_status_ok_kind_uses_ok_class_suffix():
    """_oob_status with kind='ok' uses --ok class suffix on both fragments."""
    from ace.routes.api import _oob_status

    response = _oob_status("Saved", "ok")
    body = response.body.decode("utf-8")
    assert "ace-statusbar-event--ok" in body
    assert "ace-text-event-pill--ok" in body


# ---------------------------------------------------------------------------
# Merge-on-apply integration tests
# ---------------------------------------------------------------------------


def _count_active_annotations(client, db_path: str, source_index: int) -> int:
    """Count non-deleted annotations on the source at source_index."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        source_row = conn.execute(
            "SELECT id FROM source ORDER BY sort_order LIMIT 1 OFFSET ?",
            (source_index,),
        ).fetchone()
        assert source_row is not None, f"no source at index {source_index}"
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM annotation "
            "WHERE source_id = ? AND deleted_at IS NULL",
            (source_row["id"],),
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def test_apply_same_code_overlap_merges(client_with_codes):
    """POST /api/code/apply twice with overlapping same-code ranges → 1 annotation."""
    client, _, code_a, _, db_path = client_with_codes

    r1 = client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 10, "selected_text": "First docu",
    })
    assert r1.status_code == 200

    r2 = client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 5, "end_offset": 15, "selected_text": "documen",
    })
    assert r2.status_code == 200

    assert _count_active_annotations(client, db_path, 0) == 1


def test_apply_different_code_overlap_creates_two(client_with_codes):
    """Overlap with DIFFERENT code → both annotations remain."""
    client, _, code_a, code_b, db_path = client_with_codes

    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 10, "selected_text": "First docu",
    })
    client.post("/api/code/apply", data={
        "code_id": code_b, "current_index": 0,
        "start_offset": 5, "end_offset": 15, "selected_text": "documen",
    })

    assert _count_active_annotations(client, db_path, 0) == 2


def test_apply_merge_then_undo_restores_originals(client_with_codes):
    """After a merge, undo: originals restored, merged one gone."""
    client, _, code_a, _, db_path = client_with_codes

    # Two non-overlapping annotations first
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 4, "selected_text": "Firs",
    })
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 10, "end_offset": 14, "selected_text": "cont",
    })
    assert _count_active_annotations(client, db_path, 0) == 2

    # Spanning apply merges both
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 2, "end_offset": 13, "selected_text": "rst documen",
    })
    assert _count_active_annotations(client, db_path, 0) == 1

    # Undo → originals restored
    r = client.post("/api/code/undo", data={"current_index": 0})
    assert r.status_code == 200
    assert _count_active_annotations(client, db_path, 0) == 2


def _active_annotation_ranges(db_path: str, source_index: int) -> list[tuple[int, int]]:
    """Return [(start_offset, end_offset), ...] for active annotations, ordered by start."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        source_row = conn.execute(
            "SELECT id FROM source ORDER BY sort_order LIMIT 1 OFFSET ?",
            (source_index,),
        ).fetchone()
        rows = conn.execute(
            "SELECT start_offset, end_offset FROM annotation "
            "WHERE source_id = ? AND deleted_at IS NULL "
            "ORDER BY start_offset",
            (source_row["id"],),
        ).fetchall()
        return [(r["start_offset"], r["end_offset"]) for r in rows]
    finally:
        conn.close()


def test_apply_merge_then_undo_then_redo(client_with_codes):
    """Undo + redo returns to merged state. Asserts specific ranges to prove
    the right annotation survives each transition (count alone would pass even
    if undo/redo were no-ops)."""
    client, _, code_a, _, db_path = client_with_codes

    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 0, "end_offset": 10, "selected_text": "First docu",
    })
    client.post("/api/code/apply", data={
        "code_id": code_a, "current_index": 0,
        "start_offset": 5, "end_offset": 15, "selected_text": "documen",
    })
    assert _active_annotation_ranges(db_path, 0) == [(0, 15)]

    client.post("/api/code/undo", data={"current_index": 0})
    assert _active_annotation_ranges(db_path, 0) == [(0, 10)]

    client.post("/api/code/redo", data={"current_index": 0})
    assert _active_annotation_ranges(db_path, 0) == [(0, 15)]


def test_coding_page_has_codebook_heading(client_with_codes):
    """Sidebar shows a visible 'Codebook' panel heading above the search input."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text
    assert '<h2 class="ace-panel-heading">Codebook</h2>' in body
    # Appears before the search input in document order
    heading_pos = body.index('ace-panel-heading">Codebook')
    search_pos = body.index('id="code-search-input"')
    assert heading_pos < search_pos
