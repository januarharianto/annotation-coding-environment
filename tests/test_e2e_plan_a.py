"""End-to-end test: create project, import CSV, verify sources."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_full_flow_create_and_import(client, tmp_path):
    """Create a project, upload CSV, commit import, verify sources in DB."""
    project_path = str(tmp_path / "e2e.ace")

    # 1. Create project
    resp = client.post("/api/project/create", data={"name": "E2E Test", "path": project_path})
    assert resp.status_code == 200
    redirect = resp.headers.get("hx-redirect", resp.headers.get("HX-Redirect", ""))
    assert "/import" in redirect
    assert Path(project_path).exists()

    # 2. Upload CSV
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("id,text,extra\nA,First document,meta1\nB,Second document,meta2\nC,Third document,meta3\n")
    with open(csv_path, "rb") as f:
        resp = client.post("/api/import/upload", files={"file": ("data.csv", f, "text/csv")})
    assert resp.status_code == 200
    assert "id" in resp.text
    assert "text" in resp.text

    # 3. Commit import
    resp = client.post("/api/import/commit", data={"id_column": "id", "text_columns": "text"})
    assert resp.status_code == 200
    assert "3" in resp.text  # 3 sources imported

    # 4. Verify sources in database
    conn = sqlite3.connect(project_path)
    conn.row_factory = sqlite3.Row
    sources = conn.execute("SELECT * FROM source ORDER BY sort_order").fetchall()
    conn.close()

    assert len(sources) == 3
    assert sources[0]["display_id"] == "A"
    assert sources[1]["display_id"] == "B"
    assert sources[2]["display_id"] == "C"


def test_open_existing_project(client, tmp_path):
    """Open an existing project and verify redirect."""
    from ace.db.connection import create_project

    project_path = tmp_path / "existing.ace"
    conn = create_project(str(project_path), "Existing Project")
    conn.close()

    resp = client.post("/api/project/open", data={"path": str(project_path)})
    assert resp.status_code == 200
    redirect = resp.headers.get("hx-redirect", resp.headers.get("HX-Redirect", ""))
    # No sources → redirect to /import
    assert "/import" in redirect


def test_landing_page_loads(client):
    """Landing page returns 200 with ACE content."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "ACE" in resp.text
