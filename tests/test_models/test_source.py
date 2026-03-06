import hashlib

from ace.db.connection import create_project
from ace.models.source import add_source, get_source, get_source_content, list_sources


def test_add_source(tmp_db):
    conn = create_project(tmp_db, "Test")
    sid = add_source(conn, "S001", "Hello world", "file", filename="hello.txt")
    assert isinstance(sid, str)
    assert len(sid) == 32  # uuid4().hex
    row = conn.execute("SELECT * FROM source WHERE id = ?", (sid,)).fetchone()
    assert row is not None
    assert row["display_id"] == "S001"


def test_get_source_returns_metadata_without_content(tmp_db):
    conn = create_project(tmp_db, "Test")
    sid = add_source(conn, "S001", "Hello world", "file")
    row = get_source(conn, sid)
    assert row["display_id"] == "S001"
    assert "content_text" not in row.keys()


def test_get_source_content(tmp_db):
    conn = create_project(tmp_db, "Test")
    sid = add_source(conn, "S001", "Hello world", "file")
    row = get_source_content(conn, sid)
    assert row["content_text"] == "Hello world"


def test_list_sources_returns_all_ordered(tmp_db):
    conn = create_project(tmp_db, "Test")
    add_source(conn, "S001", "First", "file")
    add_source(conn, "S002", "Second", "file")
    add_source(conn, "S003", "Third", "file")
    rows = list_sources(conn)
    assert len(rows) == 3
    assert [r["display_id"] for r in rows] == ["S001", "S002", "S003"]


def test_content_hash_is_sha256(tmp_db):
    conn = create_project(tmp_db, "Test")
    content = "Hello world"
    sid = add_source(conn, "S001", content, "file")
    row = get_source_content(conn, sid)
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert row["content_hash"] == expected
    assert len(row["content_hash"]) == 64
