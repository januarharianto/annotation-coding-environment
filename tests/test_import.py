"""Tests for the import page and API routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project


@pytest.fixture()
def client_with_project(tmp_path):
    """Create a .ace project, set app state, return (client, tmp_path)."""
    app = create_app()
    db_path = tmp_path / "test.ace"
    conn = create_project(str(db_path), "Test Project")
    conn.close()

    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.project_path = str(db_path)
        yield client, tmp_path


def test_import_page_renders(client_with_project):
    """GET /import shows import page."""
    client, _ = client_with_project
    resp = client.get("/import")
    assert resp.status_code == 200
    assert "Import Data" in resp.text
    assert "Test Project" in resp.text


def test_upload_csv_shows_preview(client_with_project):
    """Upload CSV returns preview table with column selection."""
    client, tmp_path = client_with_project

    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "participant_id,reflection,age\n"
        "P001,I enjoyed the group work.,22\n"
        "P002,The lectures were fast.,25\n"
    )

    with open(csv_path, "rb") as f:
        resp = client.post(
            "/api/import/upload",
            files={"file": ("sample.csv", f, "text/csv")},
        )

    assert resp.status_code == 200
    assert "ace-table" in resp.text
    assert "P001" in resp.text
    assert "participant_id" in resp.text
    # Should have column selection controls
    assert 'name="id_column"' in resp.text
    assert 'name="text_columns"' in resp.text
    assert "Import" in resp.text


def test_import_commit(client_with_project):
    """Import with selected columns creates sources."""
    client, tmp_path = client_with_project

    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text,group\nA1,hello,ctrl\nA2,world,exp\n")

    # Upload first to set the temp path
    with open(csv_path, "rb") as f:
        client.post(
            "/api/import/upload",
            files={"file": ("data.csv", f, "text/csv")},
        )

    # Commit the import
    resp = client.post(
        "/api/import/commit",
        data={"id_column": "id", "text_columns": ["text"]},
    )

    assert resp.status_code == 200
    assert "2 sources" in resp.text
    assert "Start coding" in resp.text


def test_import_folder(client_with_project):
    """Import .txt folder creates sources."""
    client, tmp_path = client_with_project

    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document")
    (folder / "two.txt").write_text("Second document")

    resp = client.post(
        "/api/import/folder",
        data={"path": str(folder)},
    )

    assert resp.status_code == 200
    assert "2 text files" in resp.text
    assert "Start coding" in resp.text
