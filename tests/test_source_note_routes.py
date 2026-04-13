"""Tests for the source note API routes."""

import csv
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import add_source


@pytest.fixture()
def client_with_sources(tmp_path):
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    coder_id = list_coders(conn)[0]["id"]
    s1 = add_source(conn, "S001", "First source content.", "row")
    s2 = add_source(conn, "S002", "Second source content.", "row")
    add_code(conn, "Theme A", "#BF6030")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        # Visit the coding page once to auto-create assignments
        client.get("/code")
        yield client, coder_id, s1, s2, str(db_path)


def test_get_note_returns_empty_when_none(client_with_sources):
    client, _, s1, _, _ = client_with_sources
    resp = client.get(f"/api/source-note/{s1}")
    assert resp.status_code == 200
    assert resp.json() == {"note_text": ""}


def test_put_note_creates_and_get_returns_it(client_with_sources):
    client, _, s1, _, _ = client_with_sources
    put = client.put(f"/api/source-note/{s1}", data={"note_text": "Hello"})
    assert put.status_code == 200
    assert "X-ACE-Toast" not in put.headers  # Decision 14: no toast on autosave
    # Response body is the OOB refresh payload — confirm the pill state shipped
    assert "ace-note-pill--has-note" in put.text

    got = client.get(f"/api/source-note/{s1}")
    assert got.json() == {"note_text": "Hello"}


def test_put_note_updates_existing(client_with_sources):
    client, _, s1, _, _ = client_with_sources
    client.put(f"/api/source-note/{s1}", data={"note_text": "v1"})
    client.put(f"/api/source-note/{s1}", data={"note_text": "v2"})
    got = client.get(f"/api/source-note/{s1}")
    assert got.json() == {"note_text": "v2"}


def test_put_note_empty_deletes(client_with_sources):
    client, _, s1, _, _ = client_with_sources
    client.put(f"/api/source-note/{s1}", data={"note_text": "Some text"})
    client.put(f"/api/source-note/{s1}", data={"note_text": "  "})
    got = client.get(f"/api/source-note/{s1}")
    assert got.json() == {"note_text": ""}


def test_put_note_promotes_pending_to_in_progress(client_with_sources):
    """Decision 15: writing the first non-empty note promotes pending → in_progress."""
    import sqlite3
    client, coder_id, s1, _, db_path = client_with_sources

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM assignment WHERE source_id=? AND coder_id=?",
        (s1, coder_id),
    ).fetchone()
    assert row["status"] == "pending"
    conn.close()

    client.put(f"/api/source-note/{s1}", data={"note_text": "First note"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM assignment WHERE source_id=? AND coder_id=?",
        (s1, coder_id),
    ).fetchone()
    assert row["status"] == "in_progress"
    conn.close()


def test_put_note_does_not_demote_complete(client_with_sources):
    """Status promotion is one-way — does not affect complete or flagged."""
    import sqlite3
    client, coder_id, s1, _, db_path = client_with_sources

    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE assignment SET status='complete' WHERE source_id=? AND coder_id=?",
        (s1, coder_id),
    )
    conn.commit()
    conn.close()

    client.put(f"/api/source-note/{s1}", data={"note_text": "Note"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM assignment WHERE source_id=? AND coder_id=?",
        (s1, coder_id),
    ).fetchone()
    assert row["status"] == "complete"
    conn.close()


def test_put_without_coder_id_returns_400(tmp_path):
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    s1 = add_source(conn, "S001", "Text.", "row")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        # Deliberately NOT setting app.state.coder_id
        resp = client.put(f"/api/source-note/{s1}", data={"note_text": "Hi"})
        assert resp.status_code == 400


def test_export_notes_returns_csv(client_with_sources):
    client, _, s1, s2, _ = client_with_sources
    client.put(f"/api/source-note/{s1}", data={"note_text": "First"})
    client.put(f"/api/source-note/{s2}", data={"note_text": "Second"})

    resp = client.get("/api/export/notes")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")

    reader = csv.DictReader(StringIO(resp.text))
    rows = list(reader)
    assert reader.fieldnames == [
        "source_display_id",
        "source_filename",
        "coder_name",
        "note_text",
        "created_at",
        "updated_at",
    ]
    assert len(rows) == 2
    assert {r["note_text"] for r in rows} == {"First", "Second"}


def test_export_notes_header_only_when_empty(client_with_sources):
    client, _, _, _, _ = client_with_sources
    resp = client.get("/api/export/notes")
    assert resp.status_code == 200
    lines = resp.text.strip().split("\n")
    assert len(lines) == 1
    assert "source_display_id" in lines[0]


def test_export_notes_handles_unicode_project_name(tmp_path):
    """Project names with non-ASCII characters (em-dash etc.) must not crash
    the Content-Disposition header — HTTP headers are latin-1 only."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Project — with em-dash")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S001", "Text.", "row")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        client.get("/code")
        resp = client.get("/api/export/notes")
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "—" not in cd


def test_export_notes_sanitises_header_injection_chars(tmp_path):
    """Filename sanitisation must strip quotes, semicolons, CR/LF, and
    backslashes — any of these can break or inject the Content-Disposition
    header."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), 'Bad"name;with\r\nheader\\chars')
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S001", "Text.", "row")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        client.get("/code")
        resp = client.get("/api/export/notes")
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        for bad in ['"', ";", "\r", "\n", "\\"]:
            # Only the filename= value should be free of these — there's one
            # semicolon in the header itself separating `attachment` from
            # `filename=...`, so slice the filename portion out.
            fname_idx = cd.find('filename="')
            assert fname_idx >= 0
            filename_val = cd[fname_idx + len('filename="'):-1]
            assert bad not in filename_val, f"found {bad!r} in filename: {filename_val!r}"


def test_export_notes_round_trip_with_unicode_content(tmp_path):
    """Notes containing non-ASCII characters must survive the CSV round
    trip on any platform — write and read must both use UTF-8 explicitly."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test")
    coder_id = list_coders(conn)[0]["id"]
    s1 = add_source(conn, "S001", "Text.", "row")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        app.state.coder_id = coder_id
        client.get("/code")
        client.put(f"/api/source-note/{s1}", data={
            "note_text": "Participant said café — très bon · 漢字 · émoji 😀",
        })
        resp = client.get("/api/export/notes")
        assert resp.status_code == 200
        assert "café" in resp.text
        assert "très bon" in resp.text
        assert "漢字" in resp.text
        assert "😀" in resp.text
