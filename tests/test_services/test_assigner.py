"""Tests for the random assignment service with ICR overlap."""

from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.project import add_coder
from ace.services.assigner import generate_assignments, AssignmentPreview


def _setup(tmp_db, n_sources=100):
    """Create project, n sources, 3 coders (Alice, Bob, Carol)."""
    conn = create_project(tmp_db, "Test Project")
    source_ids = []
    for i in range(1, n_sources + 1):
        sid = add_source(conn, f"S{i:03d}", f"Content {i}", "row")
        source_ids.append(sid)
    coder_ids = []
    for name in ("Alice", "Bob", "Carol"):
        cid = add_coder(conn, name)
        coder_ids.append(cid)
    return conn, source_ids, coder_ids


def test_preview_shows_correct_totals(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    preview = generate_assignments(conn, coder_ids, overlap_pct=20, seed=42, preview_only=True)
    assert isinstance(preview, AssignmentPreview)
    assert preview.total_sources == 100
    assert preview.overlap_sources == 20
    assert preview.unique_sources == 80


def test_preview_per_coder_workload(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    preview = generate_assignments(conn, coder_ids, overlap_pct=20, seed=42, preview_only=True)
    for cid in coder_ids:
        info = preview.per_coder[cid]
        assert info["total"] == info["unique"] + info["overlap"]
        assert info["total"] > 0


def test_overlap_sources_assigned_to_exactly_2_coders(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    generate_assignments(conn, coder_ids, overlap_pct=20, seed=42, preview_only=False)
    rows = conn.execute(
        "SELECT source_id, COUNT(*) AS cnt FROM assignment "
        "GROUP BY source_id HAVING COUNT(*) > 1"
    ).fetchall()
    assert len(rows) == 20
    for row in rows:
        assert row["cnt"] == 2


def test_no_source_unassigned(tmp_db):
    conn, source_ids, coder_ids = _setup(tmp_db, n_sources=100)
    generate_assignments(conn, coder_ids, overlap_pct=20, seed=42, preview_only=False)
    row = conn.execute("SELECT COUNT(DISTINCT source_id) AS cnt FROM assignment").fetchone()
    assert row["cnt"] == 100


def test_seed_produces_same_structure(tmp_db):
    # Run 1
    conn1, _, coder_ids1 = _setup(tmp_db, n_sources=100)
    p1 = generate_assignments(conn1, coder_ids1, overlap_pct=20, seed=99, preview_only=True)
    conn1.close()

    # Run 2 — need a fresh db file
    import os
    db2 = tmp_db.parent / "test2.ace"
    conn2, _, coder_ids2 = _setup(db2, n_sources=100)
    p2 = generate_assignments(conn2, coder_ids2, overlap_pct=20, seed=99, preview_only=True)
    conn2.close()

    # Same coder order → same per-coder totals
    for c1, c2 in zip(coder_ids1, coder_ids2):
        assert p1.per_coder[c1]["total"] == p2.per_coder[c2]["total"]
        assert p1.per_coder[c1]["unique"] == p2.per_coder[c2]["unique"]
        assert p1.per_coder[c1]["overlap"] == p2.per_coder[c2]["overlap"]
