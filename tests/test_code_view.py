"""Tests for the /code/{id}/view page route."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.fixture()
def client_with_annotations(tmp_path):
    """Project with 2 sources, 1 code, and 3 annotations."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")

    coder_id = list_coders(conn)[0]["id"]
    s1 = add_source(conn, "S001", "a" * 100, "row")
    s2 = add_source(conn, "S002", "b" * 200, "row")
    code = add_code(conn, "Theme A", "#1565c0")

    add_annotation(conn, s1, coder_id, code, 0, 10, "aaaaaaaaaa")
    add_annotation(conn, s1, coder_id, code, 30, 40, "aaaaaaaaaa")
    add_annotation(conn, s2, coder_id, code, 50, 75, "b" * 25)
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        client.get("/code")  # auto-create assignments
        yield client, coder_id, code, str(db_path)


def test_view_happy_path(client_with_annotations):
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    assert "Theme A" in resp.text
    assert 'id="ace-codeview-data"' in resp.text


def test_view_data_blob_is_valid_json(client_with_annotations):
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    m = re.search(
        r'<script id="ace-codeview-data" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    assert m, "ace-codeview-data script not found"
    data = json.loads(m.group(1))
    assert data["code"]["name"] == "Theme A"
    assert data["stats"]["excerpts"] == 3
    assert data["stats"]["sources_with_hits"] == 2
    assert data["stats"]["total_sources"] == 2
    assert len(data["sources"]) == 2


def test_view_redirects_when_no_project(tmp_path):
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/code/any-id/view", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get("location") == "/"


def test_view_redirects_when_no_coder(tmp_path):
    app = create_app()
    db_path = tmp_path / "test.ace"
    create_project(str(db_path), "Test")
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        # No coder_id set
        resp = client.get("/code/any-id/view", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get("location") == "/"


def test_view_redirects_when_unknown_code(client_with_annotations):
    client, _, _, _ = client_with_annotations
    resp = client.get("/code/does-not-exist/view", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("location") == "/code"


def test_view_page_has_codebook_heading(client_with_annotations):
    """Coded-text-view shares the Codebook panel heading with /code.

    Guards against someone inlining the shared sidebar partial on only
    one of the two routes that render it.
    """
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    assert '<h2 class="ace-panel-heading">Codebook</h2>' in resp.text


def test_code_view_has_column_headings(client_with_annotations):
    """Coded-text view shows visible H2 headings on both columns,
    and each section uses aria-labelledby to point at its visible heading."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    body = resp.text

    # Visible column headings
    assert '<h2 id="cv-tracks-heading" class="ace-panel-heading">Source tracks</h2>' in body
    assert '<h2 id="cv-excerpts-heading" class="ace-panel-heading">Excerpts</h2>' in body

    # Sections point at the visible headings rather than carrying redundant aria-label
    assert 'class="cv-tracks-col" aria-labelledby="cv-tracks-heading"' in body
    assert 'class="cv-excerpts-col" aria-labelledby="cv-excerpts-heading"' in body

    # Document order: tracks heading inside tracks column; excerpts heading inside excerpts column
    tracks_col_pos = body.index('class="cv-tracks-col"')
    tracks_h2_pos = body.index('Source tracks</h2>')
    excerpts_col_pos = body.index('class="cv-excerpts-col"')
    excerpts_h2_pos = body.index('Excerpts</h2>')
    assert tracks_col_pos < tracks_h2_pos < excerpts_col_pos < excerpts_h2_pos


def test_cv_table_has_listbox_role(client_with_annotations):
    """Excerpts container is a listbox so roving tabindex + arrow keys
    announce correctly to AT."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    assert 'id="cv-table"' in resp.text
    assert 'role="listbox"' in resp.text
    # Confirm the role belongs to #cv-table, not just #cv-tracks
    # (search for role on the cv-table element specifically)
    m = re.search(r'<div[^>]*\bid="cv-table"[^>]*>', resp.text)
    assert m is not None, "cv-table div not found"
    assert 'role="listbox"' in m.group(0), \
        f"role=listbox not on cv-table div: {m.group(0)}"


def test_cv_tracks_has_listbox_role_regression(client_with_annotations):
    """Sources listbox — regression guard. Already present pre-change."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert 'id="cv-tracks"' in resp.text
    assert 'role="listbox"' in resp.text
    assert 'aria-multiselectable="true"' in resp.text


def test_codebook_search_has_slash_keyshortcut_regression(client_with_annotations):
    """Codebook search input advertises `/` hotkey — regression guard.
    Already present via _sidebar_codebook.html pre-change."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert 'id="code-search-input"' in resp.text
    assert 'aria-keyshortcuts="/"' in resp.text


def test_code_view_has_cheatsheet_dialog(client_with_annotations):
    """`?` cheat sheet dialog is rendered server-side for /view with shortcut content."""
    client, _, code_id, _ = client_with_annotations
    resp = client.get(f"/code/{code_id}/view")
    assert resp.status_code == 200
    # Extract the dialog block so the shortcut assertions don't get fooled by
    # matches elsewhere on the page (e.g. "Tab" appearing in unrelated copy).
    m = re.search(
        r'<dialog[^>]*id="cv-cheatsheet-dialog".*?</dialog>',
        resp.text,
        re.DOTALL,
    )
    assert m is not None, "cheatsheet dialog block not found"
    dialog = m.group(0)
    assert "Coded text shortcuts" in dialog
    # Every zone gets its own section — guard against an empty/truncated body.
    assert "Cycle Tracks" in dialog
    assert "Move cursor" in dialog
    assert "pin / unpin" in dialog.lower()
