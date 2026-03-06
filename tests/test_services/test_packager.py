"""Tests for the coder package export and import/merge service."""

import sqlite3

from ace.db.connection import create_project, open_project, checkpoint_and_close
from ace.models.source import add_source
from ace.models.codebook import add_code, list_codes
from ace.models.coder import add_coder
from ace.models.annotation import add_annotation
from ace.services.assigner import generate_assignments
from ace.services.packager import export_coder_package, import_coder_package, ImportResult


def _setup_assigned_project(tmp_db):
    """Create project with 10 sources, 2 codes, 2 coders, 20% overlap assignments."""
    conn = create_project(tmp_db, "Test Project")
    for i in range(1, 11):
        add_source(conn, f"S{i:03d}", f"Content for source {i}", "row")
    code1 = add_code(conn, "Positive", "#00ff00")
    code2 = add_code(conn, "Negative", "#ff0000")
    alice = add_coder(conn, "Alice")
    bob = add_coder(conn, "Bob")
    generate_assignments(conn, [alice, bob], overlap_pct=20, seed=42)
    return conn, [alice, bob], [code1, code2]


def _code_and_return(pkg_path):
    """Open a coder package, add 1 annotation to the first source with the first code, commit, close."""
    pkg_conn = open_project(pkg_path)
    source = pkg_conn.execute("SELECT id FROM source ORDER BY sort_order LIMIT 1").fetchone()
    code = pkg_conn.execute("SELECT id FROM codebook_code ORDER BY sort_order LIMIT 1").fetchone()
    coder = pkg_conn.execute("SELECT id FROM coder LIMIT 1").fetchone()
    add_annotation(
        pkg_conn,
        source_id=source["id"],
        coder_id=coder["id"],
        code_id=code["id"],
        start_offset=0,
        end_offset=5,
        selected_text="Conte",
    )
    checkpoint_and_close(pkg_conn)


# --- Export tests ---


def test_export_creates_valid_ace_file(tmp_db, tmp_path):
    conn, coder_ids, _ = _setup_assigned_project(tmp_db)
    pkg_path = export_coder_package(conn, coder_ids[0], tmp_path)
    assert pkg_path.exists()
    assert pkg_path.suffix == ".ace"
    pkg_conn = open_project(pkg_path)
    role = pkg_conn.execute("SELECT file_role FROM project").fetchone()
    assert role["file_role"] == "coder"
    pkg_conn.close()
    conn.close()


def test_export_contains_only_assigned_sources(tmp_db, tmp_path):
    conn, coder_ids, _ = _setup_assigned_project(tmp_db)
    pkg_path = export_coder_package(conn, coder_ids[0], tmp_path)
    pkg_conn = open_project(pkg_path)
    n_sources = pkg_conn.execute("SELECT COUNT(*) AS cnt FROM source").fetchone()["cnt"]
    n_assignments = pkg_conn.execute("SELECT COUNT(*) AS cnt FROM assignment").fetchone()["cnt"]
    assert n_sources == n_assignments
    assert n_sources > 0
    pkg_conn.close()
    conn.close()


def test_export_contains_full_codebook(tmp_db, tmp_path):
    conn, coder_ids, _ = _setup_assigned_project(tmp_db)
    pkg_path = export_coder_package(conn, coder_ids[0], tmp_path)
    pkg_conn = open_project(pkg_path)
    n_codes = pkg_conn.execute("SELECT COUNT(*) AS cnt FROM codebook_code").fetchone()["cnt"]
    assert n_codes == 2
    pkg_conn.close()
    conn.close()


def test_export_stores_codebook_hash(tmp_db, tmp_path):
    conn, coder_ids, _ = _setup_assigned_project(tmp_db)
    export_coder_package(conn, coder_ids[0], tmp_path)
    row = conn.execute("SELECT codebook_hash FROM project").fetchone()
    assert row["codebook_hash"] is not None
    conn.close()


# --- Import tests ---


def test_import_merges_annotations(tmp_db, tmp_path):
    conn, coder_ids, _ = _setup_assigned_project(tmp_db)
    pkg_path = export_coder_package(conn, coder_ids[0], tmp_path)
    _code_and_return(pkg_path)
    result = import_coder_package(conn, pkg_path)
    assert isinstance(result, ImportResult)
    assert result.annotations_imported > 0
    conn.close()


def test_import_validates_project_id(tmp_db, tmp_path):
    conn, coder_ids, _ = _setup_assigned_project(tmp_db)
    # Create a different project and export from it
    other_db = tmp_path / "other.ace"
    other_conn = create_project(other_db, "Other Project")
    add_source(other_conn, "S001", "Content", "row")
    add_code(other_conn, "Code1", "#aabbcc")
    other_coder = add_coder(other_conn, "Carol")
    generate_assignments(other_conn, [other_coder], overlap_pct=0, seed=1)
    other_pkg = export_coder_package(other_conn, other_coder, tmp_path / "other_out")
    other_conn.close()
    import pytest
    with pytest.raises(ValueError, match="project"):
        import_coder_package(conn, other_pkg)
    conn.close()


def test_import_is_idempotent(tmp_db, tmp_path):
    conn, coder_ids, _ = _setup_assigned_project(tmp_db)
    pkg_path = export_coder_package(conn, coder_ids[0], tmp_path)
    _code_and_return(pkg_path)
    result1 = import_coder_package(conn, pkg_path)
    assert result1.annotations_imported > 0
    result2 = import_coder_package(conn, pkg_path)
    assert result2.annotations_imported == 0
    assert result2.annotations_skipped > 0
    conn.close()
