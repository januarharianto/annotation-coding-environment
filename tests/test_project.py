"""Tests for project create/open API routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def tmp_project(tmp_path):
    """Create a valid .ace project file, close the connection, return the path."""
    db_path = tmp_path / "existing.ace"
    conn = create_project(str(db_path), "Existing")
    conn.close()
    return db_path


# ── Create ──────────────────────────────────────────────────────────────


def test_create_project(client, tmp_path):
    """POST /api/project/create creates .ace file and redirects."""
    path = str(tmp_path / "new.ace")
    resp = client.post("/api/project/create", data={"name": "Test", "path": path})
    assert Path(path).exists()
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


def test_create_project_overwrite_dialog(client, tmp_project):
    """Existing file shows overwrite dialog."""
    resp = client.post(
        "/api/project/create", data={"name": "Test", "path": str(tmp_project)}
    )
    assert "overwrite" in resp.text.lower() or "already exists" in resp.text.lower()


def test_create_project_overwrite_confirmed(client, tmp_project):
    """Overwrite=true deletes existing file and creates fresh project."""
    resp = client.post(
        "/api/project/create",
        data={"name": "Test", "path": str(tmp_project), "overwrite": "true"},
    )
    assert tmp_project.exists()
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


# ── Open ────────────────────────────────────────────────────────────────


def test_open_project(client, tmp_project):
    """POST /api/project/open sets state and redirects."""
    resp = client.post("/api/project/open", data={"path": str(tmp_project)})
    assert "hx-redirect" in resp.headers or "HX-Redirect" in resp.headers


def test_open_project_redirects_to_import(client, tmp_project):
    """Project with no sources redirects to /import."""
    resp = client.post("/api/project/open", data={"path": str(tmp_project)})
    redirect = resp.headers.get("HX-Redirect") or resp.headers.get("hx-redirect")
    assert redirect == "/import"


def test_open_invalid_file(client, tmp_path):
    """Non-.ace file returns error toast, not 500."""
    bad = tmp_path / "bad.ace"
    bad.write_text("not a database")
    resp = client.post("/api/project/open", data={"path": str(bad)})
    assert resp.status_code == 200  # toast error, not 500


def test_open_missing_file(client, tmp_path):
    """Missing file returns error toast."""
    resp = client.post(
        "/api/project/open", data={"path": str(tmp_path / "gone.ace")}
    )
    assert resp.status_code == 200
    assert "not found" in resp.text.lower() or "toast" in resp.text.lower()
