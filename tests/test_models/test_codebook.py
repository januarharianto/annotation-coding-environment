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
    import_selected_codes,
    list_codes,
    preview_codebook_csv,
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
        "name,colour\n"
        "Theme A,#FF0000\n"
        "Theme B,#00FF00\n"
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


def test_preview_marks_existing_codes(tmp_db, tmp_path):
    """Preview marks codes that already exist in the project."""
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")

    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\nBeta,#00FF00\n")

    preview = preview_codebook_csv(conn, csv_path)
    assert len(preview) == 2
    assert preview[0] == {"name": "Alpha", "colour": "#FF0000", "exists": True}
    assert preview[1] == {"name": "Beta", "colour": "#00FF00", "exists": False}


def test_preview_empty_csv(tmp_db, tmp_path):
    """Preview of CSV with only header returns empty list."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\n")

    preview = preview_codebook_csv(conn, csv_path)
    assert preview == []


def test_preview_no_existing_codes(tmp_db, tmp_path):
    """Preview with no codes in DB marks all as not existing."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\nBeta,#00FF00\n")

    preview = preview_codebook_csv(conn, csv_path)
    assert all(not p["exists"] for p in preview)


def test_export_codebook_to_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")
    add_code(conn, "Beta", "#00FF00")
    out = tmp_path / "out.csv"
    count = export_codebook_to_csv(conn, out)
    assert count == 2
    content = out.read_text()
    assert "name,colour" in content
    assert "Alpha,#FF0000" in content
    assert "Beta,#00FF00" in content


def test_import_selected_codes(tmp_db):
    """Import a list of codes into an empty project."""
    conn = create_project(tmp_db, "Test")
    codes_to_import = [
        {"name": "Alpha", "colour": "#FF0000"},
        {"name": "Beta", "colour": "#00FF00"},
    ]
    count = import_selected_codes(conn, codes_to_import)
    assert count == 2
    codes = list_codes(conn)
    assert len(codes) == 2
    assert codes[0]["name"] == "Alpha"
    assert codes[1]["name"] == "Beta"


def test_import_selected_appends_sort_order(tmp_db):
    """Imported codes get sort_order after existing max."""
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Existing", "#999999")  # sort_order = 1

    codes_to_import = [{"name": "New", "colour": "#FF0000"}]
    import_selected_codes(conn, codes_to_import)

    codes = list_codes(conn)
    assert len(codes) == 2
    assert codes[0]["name"] == "Existing"
    assert codes[0]["sort_order"] == 1
    assert codes[1]["name"] == "New"
    assert codes[1]["sort_order"] == 2


def test_import_selected_skips_existing(tmp_db):
    """Codes whose name already exists in DB are skipped (safety net)."""
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")

    codes_to_import = [
        {"name": "Alpha", "colour": "#00FF00"},  # exists — skip
        {"name": "Beta", "colour": "#0000FF"},    # new — insert
    ]
    count = import_selected_codes(conn, codes_to_import)
    assert count == 1
    codes = list_codes(conn)
    assert len(codes) == 2
    assert codes[0]["colour"] == "#FF0000"  # original colour kept


def test_import_selected_empty_list(tmp_db):
    """Empty list returns 0, no DB changes."""
    conn = create_project(tmp_db, "Test")
    count = import_selected_codes(conn, [])
    assert count == 0
    assert list_codes(conn) == []
