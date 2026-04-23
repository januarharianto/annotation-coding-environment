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
