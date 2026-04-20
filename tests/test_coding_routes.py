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
    # Grid cells should exist (one per assignment/source)
    assert "ace-grid-cell" in resp.text


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
    assert 'aria-label="Toggle flag"' in html


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


def test_excerpts_endpoint(client_with_codes):
    """GET /api/code/{id}/excerpts returns coded text list."""
    client, coder_id, code_a, code_b, db_path = client_with_codes
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    from ace.models.source import list_sources
    from ace.models.annotation import add_annotation
    sources = list_sources(conn)
    add_annotation(conn, sources[0]["id"], coder_id, code_a, 0, 5, "First")
    add_annotation(conn, sources[1]["id"], coder_id, code_a, 0, 6, "Second")
    conn.close()

    resp = client.get(f"/api/code/{code_a}/excerpts")
    assert resp.status_code == 200
    assert "text-panel" in resp.text
    assert "Theme A" in resp.text
    assert "First" in resp.text
    assert "Second" in resp.text
    assert "ace-excerpt-card" in resp.text
    assert "data-source-index" in resp.text


def test_excerpts_endpoint_empty(client_with_codes):
    """GET /api/code/{id}/excerpts with no annotations shows empty state."""
    client, coder_id, code_a, code_b, db_path = client_with_codes

    resp = client.get(f"/api/code/{code_a}/excerpts")
    assert resp.status_code == 200
    assert "No text has been coded" in resp.text


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


def test_density_class():
    """density_class maps annotation counts to density levels."""
    from ace.routes.pages import density_class

    assert density_class(0) == ""
    assert density_class(1) == "ace-grid-cell--ann-1"
    assert density_class(2) == "ace-grid-cell--ann-1"
    assert density_class(3) == "ace-grid-cell--ann-3"
    assert density_class(5) == "ace-grid-cell--ann-3"
    assert density_class(6) == "ace-grid-cell--ann-6"
    assert density_class(42) == "ace-grid-cell--ann-6"


def test_coding_context_grid_cells(client_with_codes):
    """grid_cells has correct shape AND class composition."""
    import sqlite3
    from ace.routes.pages import _coding_context

    client, coder_id, _, _, db_path = client_with_codes
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        ctx = _coding_context(conn, coder_id, 0)
    finally:
        conn.close()

    assert "grid_cells" in ctx
    cells = ctx["grid_cells"]
    assert isinstance(cells, list)
    assert len(cells) >= 1

    first = cells[0]
    for key in ("index", "source_id", "class_str", "title", "is_active", "tabindex"):
        assert key in first, f"grid_cells[0] missing key {key!r}"

    # Active cell at index 0
    assert first["is_active"] is True
    assert first["tabindex"] == "0"
    assert "ace-grid-cell" in first["class_str"]
    assert "ace-grid-cell--active" in first["class_str"]
    # No annotations yet → no density class
    for density in ("--ann-1", "--ann-3", "--ann-6"):
        assert density not in first["class_str"]
    # Zero annotations uses plural grammar: "0 annotations"
    assert first["title"].endswith("0 annotations")

    if len(cells) >= 2:
        second = cells[1]
        assert second["is_active"] is False
        assert second["tabindex"] == "-1"
        assert "ace-grid-cell--active" not in second["class_str"]


def test_sidebar_grid_replaces_popover(client_with_codes):
    """Coding page renders the integrated sidebar grid, not the overlay."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    resp = client.get("/code")
    body = resp.text

    # New markers present
    assert 'id="ace-sidebar-grid"' in body
    assert 'role="grid"' in body
    assert 'role="gridcell"' in body
    assert 'aria-current="location"' in body
    assert '<button type="button"' in body

    # Legacy markers gone
    for gone in (
        "source-grid-overlay",
        "ace-grid-overlay",
        "ace-grid-popover",
        "aceToggleGrid",
        "ace-grid-cell--ann-2",
        "ace-grid-cell--ann-5",
        "ace-grid-cell--ann-8",
        "ace-grid-cell--ann-10",
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


def test_grid_tabindex_and_live_region(client_with_codes):
    """Active cell has tabindex=0, others -1, and live region is polite."""
    import re
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    body = client.get("/code").text

    # Live region wired up with the correct aria-live value
    assert 'id="ace-grid-live"' in body
    assert 'aria-live="polite"' in body

    # Find the first ace-grid-cell button; it should be active and have tabindex=0
    m = re.search(
        r'<button[^>]*class="[^"]*ace-grid-cell[^"]*ace-grid-cell--active[^"]*"[^>]*>',
        body,
    )
    assert m, "no active grid cell button found"
    assert 'tabindex="0"' in m.group(0)

    # At least one other cell has tabindex=-1
    assert 'tabindex="-1"' in body


def test_annotate_refreshes_grid(client_with_codes):
    """POST /api/code/apply returns a sidebar OOB so the grid cell re-tints."""
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
    # After applying one code, the current source has 1 annotation → ann-1
    assert "ace-grid-cell--ann-1" in resp.text


def test_delete_refreshes_grid(client_with_codes):
    """Deleting an annotation returns a sidebar OOB so the grid cell re-tints."""
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

    # Pull the new annotation id from the OOB ann-data blob
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
    assert resp.status_code == 200, f"delete returned {resp.status_code}: {resp.text[:200]}"
    assert 'id="code-sidebar"' in resp.text
    # After deleting the only annotation, the density class should be gone
    assert "ace-grid-cell--ann-1" not in resp.text
