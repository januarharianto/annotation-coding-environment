"""Tests for agreement page and API routes."""

import json
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


@pytest.fixture()
def client_with_agreement_files(tmp_path):
    """Client fixture with two pre-created .ace files ready for paths-based compute."""
    path_a = _make_ace_file(
        tmp_path / "alice.ace",
        "Project A",
        "Alice",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),
            (1, 0, 0, 8, "Dogs are"),
        ],
    )
    path_b = _make_ace_file(
        tmp_path / "bob.ace",
        "Project B",
        "Bob",
        sources=[("S1", "The cat sat on the mat"), ("S2", "Dogs are great pets")],
        codes=[("Positive", "#00AA00"), ("Negative", "#AA0000")],
        annotations=[
            (0, 0, 0, 7, "The cat"),
            (1, 1, 0, 8, "Dogs are"),
        ],
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, [str(path_a), str(path_b)]


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


# ── Compute ───────────────────────────────────────────────────────────


def test_compute(client, ace_file_a, ace_file_b):
    """Compute with paths param returns metrics results."""
    paths = json.dumps([str(ace_file_a), str(ace_file_b)])
    resp = client.post("/api/agreement/compute", data={"paths": paths})
    assert resp.status_code == 200
    assert "Krippendorff" in resp.text
    assert "Positive" in resp.text
    assert "Negative" in resp.text
    assert "Overall (pooled)" in resp.text


def test_compute_returns_new_results_html(client_with_agreement_files):
    """Compute returns new minimalist results: title bar, context, table, references."""
    client, paths = client_with_agreement_files
    resp = client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    assert resp.status_code == 200
    html = resp.text
    assert "ace-agreement-title-bar" in html
    assert "Summary CSV" in html
    assert "Raw data CSV" in html
    assert "ace-agreement-context" in html
    assert "Overall (pooled)" in html
    assert "ace-agreement-table" in html
    assert "ace-agreement-refs" in html
    assert "Krippendorff" in html


def test_compute_insufficient_files(client, ace_file_a):
    """Computing with < 2 paths returns error HTML."""
    paths = json.dumps([str(ace_file_a)])
    resp = client.post("/api/agreement/compute", data={"paths": paths})
    assert resp.status_code == 400
    assert "at least" in resp.text.lower()


def test_compute_missing_paths(client):
    """Computing with no paths param returns 422."""
    resp = client.post("/api/agreement/compute")
    assert resp.status_code == 422


# ── Export ────────────────────────────────────────────────────────────


def test_export_csv(client, ace_file_a, ace_file_b):
    """Export returns CSV with per-code metrics after compute."""
    paths = json.dumps([str(ace_file_a), str(ace_file_b)])
    client.post("/api/agreement/compute", data={"paths": paths})

    resp = client.get("/api/agreement/export/results")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/csv")
    assert "Positive" in resp.text
    assert "Negative" in resp.text
    assert "percent_agreement" in resp.text


def test_export_summary_csv_has_metadata_and_overall(client_with_agreement_files):
    """Summary CSV includes metadata header, n_sources column, and Overall row."""
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    resp = client.get("/api/agreement/export/results")
    assert resp.status_code == 200
    text = resp.text
    assert text.startswith("#")
    assert "n_sources" in text
    assert "Overall" in text


def test_export_raw_data_csv(client_with_agreement_files):
    """Raw data CSV has correct columns and content-type."""
    client, paths = client_with_agreement_files
    client.post("/api/agreement/compute", data={"paths": json.dumps(paths)})
    resp = client.get("/api/agreement/export/raw")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.text
    assert "source_id" in text
    assert "start_offset" in text
    assert "end_offset" in text
    assert "coder_id" in text
    assert "code_name" in text
