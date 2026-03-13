import re
import sqlite3

import pytest

from ace.db.connection import create_project
from ace.models.codebook import (
    add_code,
    compute_codebook_hash,
    delete_code,
    export_codebook_to_csv,
    import_codebook_from_csv,
    list_codes,
    update_code,
)


def test_add_code(tmp_db):
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Theme A", "#FF0000")
    assert isinstance(cid, str)
    assert len(cid) == 32
    row = conn.execute("SELECT * FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["name"] == "Theme A"
    assert row["colour"] == "#FF0000"


def test_add_duplicate_name_raises(tmp_db):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Theme A", "#FF0000")
    with pytest.raises(sqlite3.IntegrityError):
        add_code(conn, "Theme A", "#00FF00")


def test_update_code(tmp_db):
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Theme A", "#FF0000")
    update_code(conn, cid, name="Theme B", colour="#00FF00")
    row = conn.execute("SELECT * FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["name"] == "Theme B"
    assert row["colour"] == "#00FF00"


def test_delete_code(tmp_db):
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Theme A", "#FF0000")
    delete_code(conn, cid)
    row = conn.execute("SELECT * FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row is None


def test_codebook_hash_deterministic(tmp_db):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Theme A", "#FF0000")
    add_code(conn, "Theme B", "#00FF00")
    h1 = compute_codebook_hash(conn)
    h2 = compute_codebook_hash(conn)
    assert h1 == h2
    assert len(h1) == 64


def test_import_codebook_from_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text(
        "name,colour,description\n"
        "Theme A,#FF0000,First theme\n"
        "Theme B,#00FF00,Second theme\n"
    )
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = list_codes(conn)
    assert len(codes) == 2
    assert codes[0]["name"] == "Theme A"
    assert codes[1]["name"] == "Theme B"


def test_import_csv_optional_colour(tmp_db, tmp_path):
    """Import CSV with no colour column — colours auto-assigned."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,description\nAlpha,First\nBeta,Second\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = list_codes(conn)
    assert all(re.match(r"^#[0-9A-F]{6}$", c["colour"]) for c in codes)


def test_import_csv_skips_empty_names(tmp_db, tmp_path):
    """Rows with empty name are skipped."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\n,#00FF00\n  ,#0000FF\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 1


def test_import_csv_dedup_names(tmp_db, tmp_path):
    """Duplicate names in CSV: keep first, skip subsequent."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\nAlpha,#00FF00\nBeta,#0000FF\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = list_codes(conn)
    assert codes[0]["colour"] == "#FF0000"  # first occurrence kept


def test_import_csv_invalid_colour_auto_assigns(tmp_db, tmp_path):
    """Invalid colour values get auto-assigned from palette."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,red\nBeta,#00FF00\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = list_codes(conn)
    assert re.match(r"^#[0-9A-F]{6}$", codes[0]["colour"])  # auto-assigned
    assert codes[1]["colour"] == "#00FF00"  # valid, kept


def test_import_csv_atomic_rollback(tmp_db, tmp_path):
    """Import is atomic — raises ValueError if no name column."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("colour\n#FF0000\n#00FF00\n")
    with pytest.raises(ValueError, match="name"):
        import_codebook_from_csv(conn, csv_path)
    assert list_codes(conn) == []


def test_import_csv_utf8_bom(tmp_db, tmp_path):
    """Handle UTF-8 BOM from Excel exports."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_bytes(b"\xef\xbb\xbfname,colour\nAlpha,#FF0000\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 1
    assert list_codes(conn)[0]["name"] == "Alpha"


def test_export_codebook_to_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000", "First")
    add_code(conn, "Beta", "#00FF00")
    out = tmp_path / "out.csv"
    count = export_codebook_to_csv(conn, out)
    assert count == 2
    content = out.read_text()
    assert "name,description,colour" in content
    assert "Alpha,First,#FF0000" in content
    assert "Beta,,#00FF00" in content
