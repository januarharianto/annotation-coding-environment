import sqlite3

import pytest

from ace.db.connection import create_project
from ace.models.codebook import (
    add_code,
    compute_codebook_hash,
    delete_code,
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
