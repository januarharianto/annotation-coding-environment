"""Tests for agreement page and API routes."""

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.source import add_source


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _make_ace_file(path, project_name, coder_name, sources, codes, annotations):
    """Create a .ace file with sources, codes, and annotations.

    sources: list of (display_id, content_text)
    codes: list of (name, colour)
    annotations: list of (source_index, code_index, start, end, text)
    """
    conn = create_project(str(path), project_name)

    # Rename default coder
    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()

    coder_id = conn.execute("SELECT id FROM coder").fetchone()[0]

    source_ids = []
    for display_id, content_text in sources:
        sid = add_source(conn, display_id, content_text, "row")
        source_ids.append(sid)

    code_ids = []
    for name, colour in codes:
        cid = add_code(conn, name, colour)
        code_ids.append(cid)

    for src_idx, code_idx, start, end, text in annotations:
        add_annotation(
            conn,
            source_ids[src_idx],
            coder_id,
            code_ids[code_idx],
            start,
            end,
            text,
        )

    conn.close()
    return path


@pytest.fixture()
def ace_file_a(tmp_path):
    """First .ace file with coder Alice."""
    return _make_ace_file(
        tmp_path / "alice.ace",
        "Project A",
        "Alice",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),  # S1, Positive
            (1, 0, 0, 8, "Dogs are"),  # S2, Positive
        ],
    )


@pytest.fixture()
def ace_file_b(tmp_path):
    """Second .ace file with coder Bob, same sources."""
    return _make_ace_file(
        tmp_path / "bob.ace",
        "Project B",
        "Bob",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),  # S1, Positive (same as Alice)
            (1, 1, 0, 8, "Dogs are"),  # S2, Negative (different from Alice)
        ],
    )


# ── Page renders ──────────────────────────────────────────────────────


def test_agreement_page_renders(client):
    """GET /agreement returns the agreement template."""
    resp = client.get("/agreement")
    assert resp.status_code == 200
    assert "Inter-Coder Agreement" in resp.text
    assert "agreement-results" in resp.text


# ── Add file ──────────────────────────────────────────────────────────


def test_add_file(client, ace_file_a):
    """POST /api/agreement/add-file returns file info fragment."""
    resp = client.post(
        "/api/agreement/add-file",
        data={"path": str(ace_file_a)},
    )
    assert resp.status_code == 200
    assert "alice.ace" in resp.text
    assert "ace-agreement-file" in resp.text
    assert "2 sources" in resp.text
    assert "Alice" in resp.text


def test_add_file_invalid(client, tmp_path):
    """Adding a non-.ace file returns an error fragment."""
    bad = tmp_path / "bad.ace"
    bad.write_text("not a database")
    resp = client.post(
        "/api/agreement/add-file",
        data={"path": str(bad)},
    )
    assert resp.status_code == 200
    assert "error" in resp.text.lower() or "not a valid" in resp.text.lower()


# ── Compute ───────────────────────────────────────────────────────────


def test_compute(client, ace_file_a, ace_file_b):
    """Adding 2 files and computing returns metrics dashboard."""
    # Add both files
    client.post("/api/agreement/add-file", data={"path": str(ace_file_a)})
    client.post("/api/agreement/add-file", data={"path": str(ace_file_b)})

    # Compute
    resp = client.post("/api/agreement/compute")
    assert resp.status_code == 200
    assert "Krippendorff" in resp.text
    assert "% agree" in resp.text
    assert "Positive" in resp.text
    assert "Negative" in resp.text
    # Should have 2 coders, 2 sources, 2 codes
    assert ">2<" in resp.text  # coders or sources count


def test_compute_insufficient_files(client, ace_file_a):
    """Computing with < 2 files returns error toast."""
    client.post("/api/agreement/add-file", data={"path": str(ace_file_a)})
    resp = client.post("/api/agreement/compute")
    assert resp.status_code == 200
    assert "toast" in resp.text.lower() or "at least" in resp.text.lower()


# ── Export ────────────────────────────────────────────────────────────


def test_export_csv(client, ace_file_a, ace_file_b):
    """Export returns CSV with per-code metrics."""
    client.post("/api/agreement/add-file", data={"path": str(ace_file_a)})
    client.post("/api/agreement/add-file", data={"path": str(ace_file_b)})

    resp = client.get("/api/agreement/export/results")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/csv")
    assert "Positive" in resp.text
    assert "Negative" in resp.text
    assert "percent_agreement" in resp.text


# ── Reset ─────────────────────────────────────────────────────────────


def test_reset(client, ace_file_a, ace_file_b):
    """Reset clears the loader so compute fails afterward."""
    client.post("/api/agreement/add-file", data={"path": str(ace_file_a)})
    client.post("/api/agreement/add-file", data={"path": str(ace_file_b)})
    client.post("/api/agreement/reset")

    resp = client.post("/api/agreement/compute")
    assert "toast" in resp.text.lower() or "at least" in resp.text.lower()
