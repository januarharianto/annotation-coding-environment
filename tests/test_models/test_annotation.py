from ace.db.connection import create_project
from ace.models.annotation import (
    add_annotation,
    compact_deleted,
    delete_annotation,
    get_annotations_for_source,
    list_annotations,
)
from ace.models.coder import add_coder
from ace.models.codebook import add_code
from ace.models.source import add_source


def _setup(conn):
    """Create parent rows needed for annotations."""
    source_id = add_source(conn, "S001", "Some text content here", "file")
    coder_id = add_coder(conn, "Alice")
    code_id = add_code(conn, "Theme A", "#FF0000")
    return source_id, coder_id, code_id


def test_add_annotation(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    aid = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    assert isinstance(aid, str)
    assert len(aid) == 32
    row = conn.execute("SELECT * FROM annotation WHERE id = ?", (aid,)).fetchone()
    assert row["start_offset"] == 0
    assert row["end_offset"] == 4
    assert row["selected_text"] == "Some"


def test_list_annotations_excludes_deleted(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    aid1 = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    aid2 = add_annotation(conn, source_id, coder_id, code_id, 5, 9, "text")
    delete_annotation(conn, aid1)
    rows = list_annotations(conn)
    assert len(rows) == 1
    assert rows[0]["id"] == aid2


def test_delete_annotation_is_soft_delete(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    aid = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    delete_annotation(conn, aid)
    row = conn.execute("SELECT * FROM annotation WHERE id = ?", (aid,)).fetchone()
    assert row is not None
    assert row["deleted_at"] is not None


def test_compact_deleted_removes_rows(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    aid1 = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    aid2 = add_annotation(conn, source_id, coder_id, code_id, 5, 9, "text")
    delete_annotation(conn, aid1)
    count = compact_deleted(conn)
    assert count == 1
    row = conn.execute("SELECT * FROM annotation WHERE id = ?", (aid1,)).fetchone()
    assert row is None
    row2 = conn.execute("SELECT * FROM annotation WHERE id = ?", (aid2,)).fetchone()
    assert row2 is not None


def test_get_annotations_for_source(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    add_annotation(conn, source_id, coder_id, code_id, 5, 9, "text")
    add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    rows = get_annotations_for_source(conn, source_id)
    assert len(rows) == 2
    assert rows[0]["start_offset"] < rows[1]["start_offset"]


def test_get_annotations_for_source_filters_by_coder(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    coder2_id = add_coder(conn, "Bob")
    add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    add_annotation(conn, source_id, coder2_id, code_id, 5, 9, "text")
    rows = get_annotations_for_source(conn, source_id, coder_id=coder_id)
    assert len(rows) == 1
    assert rows[0]["coder_id"] == coder_id
