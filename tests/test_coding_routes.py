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
    assert "hint-bar" in resp.text
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
    assert "X-ACE-Toast" in resp.headers

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
    assert "X-ACE-Toast" in resp.headers

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
    assert "source-grid-overlay" in resp.text
    assert "code-sidebar" in resp.text
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
    assert resp.headers.get("X-ACE-Toast") == "Source flagged"

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
