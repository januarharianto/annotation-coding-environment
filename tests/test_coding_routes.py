"""Tests for the coding page route."""

import json
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


def test_sidebar_has_brand_and_nav_has_source(client_with_sources):
    """Sidebar shows ACE brand, nav shows flag button."""
    client, _ = client_with_sources
    resp = client.get("/code")
    assert resp.status_code == 200
    html = resp.text
    assert "ace-sidebar-brand" in html
    assert "ACE" in html
    assert 'aria-label="Toggle flag (Shift+F)"' in html


def test_sidebar_has_aria_tree_roles(client_with_sources, tmp_path):
    """Sidebar renders with ARIA treeview roles.

    `role="group"` only wraps folder children in the new tree shape, so
    seed one folder + child code to verify the wrapper still renders.
    """
    client, _ = client_with_sources
    # Seed a folder + nested code via the app's open project to exercise
    # the tree renderer's `role="group"` branch.
    from ace.db.connection import open_project
    from ace.models.codebook import add_code, add_folder

    project_path = client.app.state.project_path
    conn = open_project(project_path)
    folder_id = add_folder(conn, "Folder One")
    add_code(conn, "Nested code", "#1976d2", parent_id=folder_id)
    conn.close()

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
        "/api/undo",
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
    client.post("/api/undo", data={"current_index": 0})

    # Redo
    resp = client.post("/api/redo", data={"current_index": 0})
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
# Global /api/undo + /api/redo (Task 5)
# ---------------------------------------------------------------------------


def test_undo_endpoint_pops_undo_stack(client_with_codes):
    """POST /api/undo runs the inverse mutation and returns 200 with OOB swap."""
    client, _coder_id, code_id, _, _db_path = client_with_codes
    # Apply a code to source 0 — record_add fires automatically inside the route
    resp = client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })
    assert resp.status_code == 200

    # Now undo
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    # Status bar OOB present
    assert 'id="ace-statusbar-event"' in resp.text
    assert "Undone:" in resp.text


def test_undo_endpoint_empty_stack_returns_status(client_with_codes):
    """POST /api/undo on empty stack returns 'Nothing to undo' AND signals the
    client not to perform a primary swap. Without HX-Reswap=none, HTMX would
    receive an OOB-only response and replace #text-panel with empty content.
    """
    client, _coder_id, _code_id, _, _db_path = client_with_codes
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Nothing to undo" in resp.text
    assert resp.headers.get("HX-Reswap") == "none"

    resp = client.post("/api/redo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Nothing to redo" in resp.text
    assert resp.headers.get("HX-Reswap") == "none"


def test_old_code_undo_endpoint_removed(client_with_codes):
    """POST /api/code/undo no longer exists."""
    client, _coder_id, _code_id, _, _db_path = client_with_codes
    resp = client.post("/api/code/undo", data={"current_index": 0})
    assert resp.status_code == 404


def test_undo_annotation_delete_includes_flash_script(client_with_codes):
    """Undoing an annotation_delete returns a flash OOB script targeting #ace-undo-flash.

    Locks the wire so future changes to the flash plumbing don't silently regress.
    HTMX 2.x silently drops OOB swaps whose target is missing, so this also
    indirectly guards the placeholder in coding.html.
    """
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes

    # Apply a code, then look up its annotation id
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    ann_id = conn.execute(
        "SELECT id FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()["id"]
    conn.close()

    # Delete the annotation (records annotation_delete on the undo stack)
    client.post("/api/code/delete-annotation", data={
        "annotation_id": ann_id, "current_index": 0,
    })

    # Undo the delete — response should include the flash OOB script
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert 'id="ace-undo-flash"' in resp.text
    assert 'hx-swap-oob="outerHTML"' in resp.text
    assert "_flashAnnotation" in resp.text
    assert ann_id in resp.text


def test_undo_cross_source_includes_navigate_trigger(client_with_codes):
    """Undo of an annotation made on a different source emits HX-Trigger: ace-navigate."""
    import json as _json

    client, _coder_id, code_id, _, _db_path = client_with_codes

    # Apply on source 0
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })

    # Undo from source 1 (different) — fixture has 2 sources, so index 1 is the
    # "other" source the user has navigated to.
    resp = client.post("/api/undo", data={"current_index": 1})
    assert resp.status_code == 200
    trigger = resp.headers.get("HX-Trigger", "")
    assert "ace-navigate" in trigger
    data = _json.loads(trigger)
    assert data["ace-navigate"]["index"] == 0


def test_code_rename_records_undo_entry(client_with_codes):
    """PUT /api/codes/{code_id} with new name records code_rename."""
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes
    resp = client.put(f"/api/codes/{code_id}", data={
        "name": "RenamedCode", "current_index": 0,
    })
    assert resp.status_code == 200

    # Sanity: rename did happen
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    row = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    conn.close()
    assert row["name"] == "RenamedCode"

    # Undo
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Undone:" in resp.text

    # Verify the rename was undone in the DB (status bar text mentions the
    # new name in the "back to" description, so an HTML-text assertion is
    # ambiguous — go to the source of truth).
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    row = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    conn.close()
    assert row["name"] == "Theme A"


def test_undo_cross_source_falls_back_when_source_unassigned(client_with_codes):
    """Undo where the action's source has been removed from the assignment list
    stays on the current source and notes 'no longer assigned' in the status."""
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes

    # Apply on source 0 (records add against source 0's id)
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })

    # Programmatically delete source 0's assignment row to simulate the source
    # being removed from the coder's assignment list after the action was recorded.
    # (Sources are 1-indexed by sort_order; the first source is the one with the
    # smallest sort_order.)
    conn = _sqlite3.connect(db_path)
    conn.execute(
        "DELETE FROM assignment WHERE source_id = ("
        "SELECT id FROM source ORDER BY sort_order LIMIT 1"
        ")"
    )
    conn.commit()
    conn.close()

    # Undo. Only one assignment remains (S002 at index 0); the action's source
    # (S001) is no longer in the list, so the route should fall back to the
    # current source and append "(source no longer assigned)" to the status.
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "no longer assigned" in resp.text
    # No navigate trigger, since the source's index can't be located.
    assert "ace-navigate" not in resp.headers.get("HX-Trigger", "")


def test_undo_code_rename_no_navigate_trigger(client_with_codes):
    """Undoing a codebook-only op (rename) must not emit ace-navigate."""
    client, _coder_id, code_id, _, _db_path = client_with_codes

    resp = client.put(f"/api/codes/{code_id}", data={
        "name": "RenamedCode", "current_index": 0,
    })
    assert resp.status_code == 200

    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "ace-navigate" not in resp.headers.get("HX-Trigger", "")


def test_undo_code_delete_restores_across_sources(client_with_codes):
    """Deleting a code with annotations on multiple sources soft-deletes them
    all; undo restores every annotation to active state."""
    import sqlite3 as _sqlite3

    client, _coder_id, code_id, _, db_path = client_with_codes

    # Apply the code on source 0 and source 1 (fixture has 2 sources).
    client.post("/api/code/apply", data={
        "current_index": 0, "code_id": code_id,
        "start_offset": 0, "end_offset": 5, "selected_text": "First",
    })
    client.post("/api/code/apply", data={
        "current_index": 1, "code_id": code_id,
        "start_offset": 0, "end_offset": 6, "selected_text": "Second",
    })

    # Sanity: 2 active annotations before delete.
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    active = conn.execute(
        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()[0]
    conn.close()
    assert active == 2

    # Delete the code — should cascade soft-delete both annotations.
    resp = client.delete(
        f"/api/codes/{code_id}", params={"current_index": 0}
    )
    assert resp.status_code == 200

    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    active = conn.execute(
        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()[0]
    conn.close()
    assert active == 0

    # Undo — both annotations restored to active state.
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200

    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    active = conn.execute(
        "SELECT id FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()
    conn.close()
    assert len(active) == 2


def test_reorder_codes_noop_does_not_record_undo_entry(client_with_codes):
    """A POST /api/codes/reorder that doesn't change ordering must NOT
    record an undo entry. The client uses this endpoint to re-render the
    sidebar after side-channel mutations; without this guard, one user
    drag takes two undo presses to reverse.
    """
    client, coder_id, code_a, code_b, db_path = client_with_codes

    # First, do a real reorder (swap the two codes) — should record one entry.
    resp = client.post(
        "/api/codes/reorder",
        data={"code_ids": json.dumps([code_b, code_a]), "current_index": 0},
    )
    assert resp.status_code == 200

    # Now a no-op reorder (same order) — should NOT record another entry.
    resp = client.post(
        "/api/codes/reorder",
        data={"code_ids": json.dumps([code_b, code_a]), "current_index": 0},
    )
    assert resp.status_code == 200

    # And the empty-list "refresh" pattern from _refreshSidebar — also no-op.
    resp = client.post(
        "/api/codes/reorder",
        data={"code_ids": "[]", "current_index": 0},
    )
    assert resp.status_code == 200

    # One undo should fully reverse the swap. After it, second undo says nothing.
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Undone:" in resp.text

    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "Nothing to undo" in resp.text


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


def test_navigate_does_not_change_flag_state(client_with_codes):
    """Navigation no longer auto-changes any assignment state."""
    client, coder_id, code_a, _, db_path = client_with_codes

    # Create an annotation on source 0
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

    # All assignments should remain unflagged
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows_before = conn.execute(
        "SELECT flagged FROM assignment WHERE coder_id = ? ORDER BY rowid",
        (coder_id,),
    ).fetchall()
    conn.close()
    assert all(r["flagged"] == 0 for r in rows_before)

    # Navigate from 0 to 1
    client.post(
        "/api/code/navigate",
        data={"current_index": "0", "target_index": "1"},
    )

    # Flag state unchanged
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows_after = conn.execute(
        "SELECT flagged FROM assignment WHERE coder_id = ? ORDER BY rowid",
        (coder_id,),
    ).fetchall()
    conn.close()
    assert all(r["flagged"] == 0 for r in rows_after)


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
    """Flagging twice returns to unflagged."""
    client, coder_id, _, _, db_path = client_with_codes

    # Flag
    client.post("/api/code/flag", data={"source_index": "0"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT flagged FROM assignment WHERE coder_id = ? ORDER BY rowid LIMIT 1",
        (coder_id,),
    ).fetchone()
    assert row["flagged"] == 1
    conn.close()

    # Unflag
    client.post("/api/code/flag", data={"source_index": "0"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT flagged FROM assignment WHERE coder_id = ? ORDER BY rowid LIMIT 1",
        (coder_id,),
    ).fetchone()
    assert row["flagged"] == 0
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
    """Undo action announces to the polite live region (and the status bar 'ok' channel)."""
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
    resp = client.post("/api/undo", data={"current_index": 0})
    assert resp.status_code == 200
    assert "X-ACE-Toast" not in resp.headers
    assert 'id="ace-live-region"' in resp.text
    # The new global undo emits a "Undone: ..." description that includes
    # the code name and source display id.
    assert "Undone:" in resp.text
    assert "Theme A" in resp.text


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
    # and the button sits inside an <h2> (W3C accordion pattern) with
    # aria-labelledby on the section pointing at the visible heading.
    assert '<span id="ace-sidebar-grid-heading" class="ace-panel-heading">Source map</span>' in body
    # The button is wrapped in an h2 via the shared .ace-panel-heading-wrap utility
    assert '<h2 class="ace-panel-heading-wrap">' in body
    # Section landmark references the visible heading, not a redundant aria-label
    assert 'aria-labelledby="ace-sidebar-grid-heading"' in body
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
    r = client.post("/api/undo", data={"current_index": 0})
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

    client.post("/api/undo", data={"current_index": 0})
    assert _active_annotation_ranges(db_path, 0) == [(0, 10)]

    client.post("/api/redo", data={"current_index": 0})
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


def test_coding_page_has_page_title(client_with_codes):
    """/code renders a centred H1 'Coding' above the nav cluster."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    assert r.status_code == 200
    body = r.text
    # H1 with the shared page-title class
    assert '<h1 class="ace-page-title' in body
    assert '>Coding</h1>' in body
    # H1 appears before the nav cluster in document order
    h1_pos = body.index('>Coding</h1>')
    nav_pos = body.index('ace-nav-cluster')
    assert h1_pos < nav_pos


def test_applied_codes_caption_hidden_when_empty(client_with_codes):
    """Applied-codes bar does not render when no codes have been applied to the source."""
    client, coder_id, _, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    r = client.get("/code?index=0")
    body = r.text
    # No chips applied → whole bar (including caption) absent
    assert 'class="ace-code-bar"' not in body
    assert 'Applied codes' not in body


def test_applied_codes_caption_when_present(client_with_codes):
    """Applied-codes bar carries a leading 'Applied codes' caption when ≥1 chip is rendered."""
    client, coder_id, code_a, _, _ = client_with_codes
    client.cookies.set("coder_id", coder_id)
    # Apply one code to source 0
    apply_resp = client.post(
        "/api/code/apply",
        data={
            "code_id": code_a,
            "current_index": 0,
            "start_offset": 0,
            "end_offset": 5,
            "selected_text": "First",
        },
    )
    assert apply_resp.status_code == 200
    r = client.get("/code?index=0")
    body = r.text
    assert 'class="ace-code-bar"' in body
    assert '<span class="ace-code-bar-label">Applied codes</span>' in body
    # Label appears before the first chip
    label_pos = body.index('Applied codes</span>')
    chip_pos = body.index('class="ace-code-chip"')
    assert label_pos < chip_pos


# ---------------------------------------------------------------------------
# PATCH /api/codes/{id}/chord — Task 7
# ---------------------------------------------------------------------------


def test_patch_code_chord_success(tmp_path):
    """PATCH /api/codes/{id}/chord with valid chord updates DB."""
    from ace.db.connection import open_project
    from ace.models.codebook import list_codes

    project_path = tmp_path / "patch_chord.ace"
    conn = create_project(str(project_path), "Test")

    # Seed 32 codes so the 32nd has a chord
    try:
        for i in range(32):
            add_code(conn, f"Code {i:02d}", "#A91818")
        codes = list_codes(conn)
        last_id = codes[31]["id"]  # 32nd code (0-indexed), has a chord
    finally:
        conn.close()

    app = create_app()
    with TestClient(app) as c:
        c.post("/api/project/open", data={"path": str(project_path)})
        response = c.patch(f"/api/codes/{last_id}/chord", data={"chord": "xy"})
        assert response.status_code == 200

    # Verify in DB
    conn = open_project(str(project_path))
    try:
        row = conn.execute(
            "SELECT chord FROM codebook_code WHERE id = ?", (last_id,)
        ).fetchone()
        assert row["chord"] == "xy"
    finally:
        conn.close()


def test_patch_code_chord_conflict_returns_409(tmp_path):
    """PATCH with chord already in use returns 409."""
    from ace.db.connection import open_project
    from ace.models.codebook import list_codes

    project_path = tmp_path / "patch_conflict.ace"
    conn = create_project(str(project_path), "Test")

    # Seed 33 codes so two codes have chords
    try:
        for i in range(33):
            add_code(conn, f"Code {i:02d}", "#A91818")
        codes = list_codes(conn)
        id_a = codes[31]["id"]  # 32nd
        id_b = codes[32]["id"]  # 33rd
    finally:
        conn.close()

    app = create_app()
    with TestClient(app) as c:
        c.post("/api/project/open", data={"path": str(project_path)})
        # First: set ab on code A
        r1 = c.patch(f"/api/codes/{id_a}/chord", data={"chord": "ab"})
        assert r1.status_code == 200
        # Then: try ab on code B — must fail
        r2 = c.patch(f"/api/codes/{id_b}/chord", data={"chord": "ab"})
        assert r2.status_code == 409


def test_patch_code_chord_invalid_format_returns_400(tmp_path):
    """PATCH with non-2-lowercase-letter chord returns 400."""
    from ace.db.connection import open_project
    from ace.models.codebook import list_codes

    project_path = tmp_path / "patch_invalid.ace"
    conn = create_project(str(project_path), "Test")

    try:
        for i in range(32):
            add_code(conn, f"Code {i:02d}", "#A91818")
        codes = list_codes(conn)
        last_id = codes[31]["id"]
    finally:
        conn.close()

    app = create_app()
    with TestClient(app) as c:
        c.post("/api/project/open", data={"path": str(project_path)})
        for bad in ["a", "abc", "AB", "1a", "a1", ""]:
            r = c.patch(f"/api/codes/{last_id}/chord", data={"chord": bad})
            assert r.status_code in (400, 422), (
                f"expected 400/422 for chord={bad!r}, got {r.status_code}"
            )


def test_patch_code_chord_unknown_id_returns_404(tmp_path):
    """PATCH with non-existent code_id returns 404."""
    project_path = tmp_path / "patch_404.ace"
    conn = create_project(str(project_path), "Test")
    conn.close()

    app = create_app()
    with TestClient(app) as c:
        c.post("/api/project/open", data={"path": str(project_path)})
        r = c.patch("/api/codes/nonexistent-uuid/chord", data={"chord": "ab"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Folder + parent + cut-paste routes (Task 5)
# ---------------------------------------------------------------------------


def _latest_id_by_name(db_path: str, name: str, kind: str) -> str:
    """Return the id of the most-recently-created row matching name+kind."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id FROM codebook_code "
        "WHERE name = ? AND kind = ? AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT 1",
        (name, kind),
    ).fetchone()
    conn.close()
    assert row is not None, f"no {kind} named {name!r} found in {db_path}"
    return row["id"]


def _extract_folder_id(_html: str, name: str, db_path: str) -> str:
    """Resolve a folder's id via the database (HTML markup is Task 6)."""
    return _latest_id_by_name(db_path, name, "folder")


def _create_folder(client, name: str, db_path: str) -> str:
    """POST /api/codes/folder and return the new folder id."""
    r = client.post(
        "/api/codes/folder",
        data={"name": name, "current_index": 0},
    )
    assert r.status_code == 200, r.text
    return _latest_id_by_name(db_path, name, "folder")


def _add_test_code(
    client, name: str, db_path: str, parent_id: str | None = None,
) -> str:
    """POST /api/codes and return the new code id."""
    data = {"name": name, "current_index": 0}
    if parent_id is not None:
        data["parent_id"] = parent_id
    r = client.post("/api/codes", data=data)
    assert r.status_code == 200, r.text
    return _latest_id_by_name(db_path, name, "code")


def test_create_folder_route(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    r = client.post(
        "/api/codes/folder",
        data={"name": "Themes", "current_index": 0},
    )
    assert r.status_code == 200
    # Folder row exists in the DB with kind='folder'
    fid = _latest_id_by_name(db_path, "Themes", "folder")
    assert fid


def test_set_parent_to_folder(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    code_id = _add_test_code(client, "Identity", db_path)

    r = client.put(
        f"/api/codes/{code_id}/parent",
        data={"parent_id": folder_id, "current_index": 0},
    )
    assert r.status_code == 200

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,),
    ).fetchone()
    conn.close()
    assert row["parent_id"] == folder_id


def test_set_parent_to_root(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    code_id = _add_test_code(client, "Identity", db_path, parent_id=folder_id)

    r = client.put(
        f"/api/codes/{code_id}/parent",
        data={"parent_id": "", "current_index": 0},
    )
    assert r.status_code == 200

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,),
    ).fetchone()
    conn.close()
    assert row["parent_id"] is None


def test_set_parent_to_code_rejected(client_with_codes):
    client, _coder_id, code_a, code_b, _db_path = client_with_codes
    # Both code_a and code_b are kind='code'. Moving b under a must fail.
    r = client.put(
        f"/api/codes/{code_b}/parent",
        data={"parent_id": code_a, "current_index": 0},
    )
    assert r.status_code == 400


def test_cut_paste_moves_code(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    code_id = _add_test_code(client, "Identity", db_path)

    r = client.post(
        "/api/codes/cut-paste",
        data={"code_id": code_id, "target_id": folder_id, "current_index": 0},
    )
    assert r.status_code == 200

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,),
    ).fetchone()
    conn.close()
    assert row["parent_id"] == folder_id


def test_rename_group_route_removed(client_with_codes):
    client, *_ = client_with_codes
    r = client.put(
        "/api/codes/rename-group",
        data={"old_name": "x", "new_name": "y"},
    )
    assert r.status_code == 404


def test_indent_promote_creates_folder_and_moves_both_codes(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    a = _add_test_code(client, "Alpha", db_path)
    b = _add_test_code(client, "Beta", db_path)
    r = client.post(
        f"/api/codes/{b}/indent-promote",
        data={
            "above_code_id": a,
            "folder_name": "Wrapped",
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    # Folder exists; both codes parented to it.
    fid = _latest_id_by_name(db_path, "Wrapped", "folder")
    assert fid
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, parent_id FROM codebook_code WHERE id IN (?, ?)",
        (a, b),
    ).fetchall()
    conn.close()
    parents = {r["id"]: r["parent_id"] for r in rows}
    assert parents[a] == fid
    assert parents[b] == fid


def test_indent_promote_rolls_back_on_name_collision(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    # Pre-create the folder name we'll collide with.
    existing = _create_folder(client, "Taken", db_path)
    a = _add_test_code(client, "Alpha", db_path)
    b = _add_test_code(client, "Beta", db_path)

    r = client.post(
        f"/api/codes/{b}/indent-promote",
        data={
            "above_code_id": a,
            "folder_name": "Taken",
            "current_index": 0,
        },
    )
    # Returns OOB status fragment (200) carrying the error message; transaction rolled back.
    assert r.status_code == 200
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, parent_id FROM codebook_code WHERE id IN (?, ?)",
        (a, b),
    ).fetchall()
    # Confirm only one folder named 'Taken' (the pre-existing one).
    folder_count = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE name = 'Taken' AND kind = 'folder' AND deleted_at IS NULL"
    ).fetchone()[0]
    conn.close()
    assert folder_count == 1
    parents = {r["id"]: r["parent_id"] for r in rows}
    # Both codes still at root — no half-built folder, no orphan move.
    assert parents[a] is None
    assert parents[b] is None
    assert existing  # silence unused-var lint


def test_indent_promote_invalid_above_code_id_returns_400(client_with_codes):
    client, _coder_id, _a, _b, db_path = client_with_codes
    b = _add_test_code(client, "Beta", db_path)
    r = client.post(
        f"/api/codes/{b}/indent-promote",
        data={
            "above_code_id": "does-not-exist",
            "folder_name": "Wrapped",
            "current_index": 0,
        },
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Reorder-in-scope route (Task 11) — same-scope drag persists sort_order
# without recording an undo entry, and returns the unified text-panel + OOB
# sidebar shape so count chips stay consistent across the swap.
# ---------------------------------------------------------------------------


def _sort_orders_at_root(db_path: str) -> dict[str, int]:
    """Return {code_id: sort_order} for every active code at root scope."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, sort_order FROM codebook_code "
        "WHERE deleted_at IS NULL AND parent_id IS NULL AND kind = 'code'"
    ).fetchall()
    conn.close()
    return {r["id"]: r["sort_order"] for r in rows}


def _sort_orders_in_folder(db_path: str, folder_id: str) -> dict[str, int]:
    """Return {code_id: sort_order} for every active code parented to folder."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, sort_order FROM codebook_code "
        "WHERE deleted_at IS NULL AND parent_id = ? AND kind = 'code'",
        (folder_id,),
    ).fetchall()
    conn.close()
    return {r["id"]: r["sort_order"] for r in rows}


def test_reorder_in_scope_updates_sort_order_within_root(client_with_codes):
    """POST /api/codes/reorder-in-scope rewrites sort_order for the listed
    ids in the order they're passed (root scope = empty parent_id)."""
    client, _coder_id, a, b, db_path = client_with_codes
    cc = _add_test_code(client, "Charlie", db_path)

    # Reorder root: Charlie, Alpha (a), Bravo (b)
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([cc, a, b]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    orders = _sort_orders_at_root(db_path)
    assert orders[cc] == 0
    assert orders[a] == 1
    assert orders[b] == 2


def test_reorder_in_scope_returns_text_panel_and_sidebar(client_with_codes):
    """The route returns the unified `_render_full_coding_oob` shape so the
    count chips on the text panel + sidebar stay in sync."""
    client, _coder_id, a, b, _db_path = client_with_codes
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([b, a]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200
    # text-panel primary swap + sidebar OOB
    assert 'id="text-panel"' in r.text
    assert 'id="code-sidebar"' in r.text
    assert 'hx-swap-oob' in r.text


def test_reorder_in_scope_within_folder(client_with_codes):
    """Reorder works within a folder scope — only rows under that parent
    get their sort_order updated."""
    client, _coder_id, _a, _b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    x = _add_test_code(client, "FX", db_path, parent_id=folder_id)
    y = _add_test_code(client, "FY", db_path, parent_id=folder_id)
    z = _add_test_code(client, "FZ", db_path, parent_id=folder_id)

    # Reorder folder: FZ, FX, FY
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([z, x, y]),
            "parent_id": folder_id,
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    orders = _sort_orders_in_folder(db_path, folder_id)
    assert orders[z] == 0
    assert orders[x] == 1
    assert orders[y] == 2


def test_reorder_in_scope_ignores_codes_outside_scope(client_with_codes):
    """If the client sends ids that live in a different scope, the UPDATE
    is filtered to the requested parent — out-of-scope rows are untouched.

    This is defensive: a stale client (e.g. mid-drag DOM) can't accidentally
    move a code from one folder into another via the reorder endpoint.
    """
    client, _coder_id, root_a, root_b, db_path = client_with_codes
    folder_id = _create_folder(client, "Themes", db_path)
    inside = _add_test_code(client, "Inside", db_path, parent_id=folder_id)

    before_root = _sort_orders_at_root(db_path)
    before_folder = _sort_orders_in_folder(db_path, folder_id)

    # Pretend client (incorrectly) lists a root code in the folder scope.
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([inside, root_a]),
            "parent_id": folder_id,
            "current_index": 0,
        },
    )
    assert r.status_code == 200, r.text

    after_root = _sort_orders_at_root(db_path)
    after_folder = _sort_orders_in_folder(db_path, folder_id)

    # root_a's sort_order must NOT have changed (it's still in root scope).
    assert after_root[root_a] == before_root[root_a]
    assert after_root[root_b] == before_root[root_b]
    # The in-scope row was renumbered to position 0.
    assert after_folder[inside] == 0
    # No spurious row got reparented.
    assert set(after_folder.keys()) == set(before_folder.keys())


def test_reorder_in_scope_does_not_record_undo(client_with_codes):
    """Drag-reorder is not stack-able by existing convention — an undo
    immediately after a reorder-in-scope must NOT undo it."""
    client, _coder_id, a, b, _db_path = client_with_codes

    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([b, a]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200

    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200
    # Empty stack message — confirms reorder-in-scope didn't push an entry.
    assert "Nothing to undo" in r.text


def test_reorder_in_scope_invalid_json_returns_oob_status(client_with_codes):
    """Malformed code_ids must not 500 — return an OOB status fragment."""
    client, *_ = client_with_codes
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": "not-json",
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200
    assert "Invalid code_ids format" in r.text


# ---------------------------------------------------------------------------
# PR review fixes — F2 / F4 / F5 / F7
# ---------------------------------------------------------------------------


def test_create_code_palette_unaffected_by_folder_count(client_with_codes):
    """F2 — `create_code` palette index counts only code rows, not folders.

    Two scenarios with the same code-count must yield the same colour even
    when the second one has extra folders sitting between them.
    """
    from ace.db.connection import open_project
    from ace.models.codebook import COLOUR_PALETTE

    client, _coder, _a, _b, db_path = client_with_codes

    # Baseline: two codes already exist (Theme A, Theme B). Next palette
    # slot for a freshly-created code should be index 2.
    expected_colour = COLOUR_PALETTE[2][0]

    r = client.post("/api/codes", data={"name": "Charlie", "current_index": 0})
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        row = conn.execute(
            "SELECT colour FROM codebook_code WHERE name = ?", ("Charlie",)
        ).fetchone()
    finally:
        conn.close()
    assert row["colour"].upper() == expected_colour.upper()

    # Create a folder, then a fourth code. With folders included in the
    # palette index (the bug), the colour would shift by one. The fix
    # filters `kind = 'code'`, so the next colour stays at palette[3].
    r = client.post("/api/codes/folder", data={"name": "Themes", "current_index": 0})
    assert r.status_code == 200

    expected_after_folder = COLOUR_PALETTE[3][0]
    r = client.post("/api/codes", data={"name": "Delta", "current_index": 0})
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        row = conn.execute(
            "SELECT colour FROM codebook_code WHERE name = ?", ("Delta",)
        ).fetchone()
    finally:
        conn.close()
    assert row["colour"].upper() == expected_after_folder.upper()


def test_delete_code_404_on_unknown_id(client_with_codes):
    """F4 — DELETE /api/codes/{id} returns 404 for a missing id, no undo entry."""
    client, *_ = client_with_codes
    r = client.delete("/api/codes/this-id-does-not-exist", params={"current_index": 0})
    assert r.status_code == 404

    # The 404 should NOT have pushed an undo entry.
    r = client.post("/api/undo", data={"current_index": 0})
    assert r.status_code == 200
    assert "Nothing to undo" in r.text


def test_cut_paste_to_root_with_empty_target(client_with_codes):
    """F5 — POST /api/codes/cut-paste accepts target_id="" as 'paste to root'."""
    from ace.db.connection import open_project
    from ace.models.codebook import add_folder, move_code_to_parent

    client, _coder, code_a, _b, db_path = client_with_codes

    # Move Theme A into a folder so we have something to "cut back to root".
    conn = open_project(db_path)
    try:
        fid = add_folder(conn, "Themes")
        move_code_to_parent(conn, code_a, fid)
    finally:
        conn.close()

    r = client.post(
        "/api/codes/cut-paste",
        data={"code_id": code_a, "target_id": "", "current_index": 0},
    )
    assert r.status_code == 200, r.text

    conn = open_project(db_path)
    try:
        parent = conn.execute(
            "SELECT parent_id FROM codebook_code WHERE id = ?", (code_a,)
        ).fetchone()["parent_id"]
    finally:
        conn.close()
    assert parent is None, "code should be back at root scope"


def test_cut_paste_404_on_unknown_target(client_with_codes):
    """F5 sibling — non-empty target_id that doesn't exist still 404s."""
    client, _coder, code_a, _b, _db = client_with_codes
    r = client.post(
        "/api/codes/cut-paste",
        data={"code_id": code_a, "target_id": "no-such-id", "current_index": 0},
    )
    assert r.status_code == 404


def test_reorder_in_scope_skips_folder_rows(client_with_codes):
    """F3 — UPDATE in /api/codes/reorder-in-scope is restricted to kind='code'.

    Sending a folder id alongside legitimate code ids must NOT rewrite the
    folder's sort_order (defence in depth against a stale client).
    """
    from ace.db.connection import open_project
    from ace.models.codebook import add_folder

    client, _coder, code_a, code_b, db_path = client_with_codes

    conn = open_project(db_path)
    try:
        fid = add_folder(conn, "Themes")
        before = conn.execute(
            "SELECT sort_order FROM codebook_code WHERE id = ?", (fid,)
        ).fetchone()["sort_order"]
    finally:
        conn.close()

    # Send the folder id at index 0 — if the route honoured it, the folder
    # would inherit sort_order=0.
    r = client.post(
        "/api/codes/reorder-in-scope",
        data={
            "code_ids": json.dumps([fid, code_a, code_b]),
            "parent_id": "",
            "current_index": 0,
        },
    )
    assert r.status_code == 200

    conn = open_project(db_path)
    try:
        after = conn.execute(
            "SELECT sort_order FROM codebook_code WHERE id = ?", (fid,)
        ).fetchone()["sort_order"]
    finally:
        conn.close()
    assert after == before, "folder sort_order must not be touched by reorder-in-scope"


def test_reorder_tree_persists_folder_order(client_with_codes):
    """F7 — POST /api/codes/reorder-tree rewrites sort_order across kinds."""
    from ace.db.connection import open_project
    from ace.models.codebook import add_folder

    client, _coder, code_a, code_b, db_path = client_with_codes

    conn = open_project(db_path)
    try:
        f1 = add_folder(conn, "Themes")
        f2 = add_folder(conn, "Methods")
    finally:
        conn.close()

    # Place Methods (f2) BEFORE Themes (f1), then the two root codes.
    new_order = [f2, f1, code_a, code_b]
    r = client.post(
        "/api/codes/reorder-tree",
        data={"tree_ids": json.dumps(new_order), "current_index": 0},
    )
    assert r.status_code == 200, r.text

    conn = open_project(db_path)
    try:
        rows = conn.execute(
            "SELECT id, sort_order FROM codebook_code "
            "WHERE deleted_at IS NULL ORDER BY sort_order"
        ).fetchall()
    finally:
        conn.close()
    ordered_ids = [r["id"] for r in rows]
    assert ordered_ids == new_order


def test_reorder_tree_rejects_malformed_payload(client_with_codes):
    """F7 sibling — bad shape returns OOB status, not a 500."""
    client, *_ = client_with_codes
    r = client.post(
        "/api/codes/reorder-tree",
        data={"tree_ids": "not-json", "current_index": 0},
    )
    assert r.status_code == 200
    assert "Invalid tree_ids format" in r.text

    r = client.post(
        "/api/codes/reorder-tree",
        data={"tree_ids": json.dumps([1, 2, 3]), "current_index": 0},
    )
    assert r.status_code == 200
    assert "Invalid tree_ids format" in r.text
