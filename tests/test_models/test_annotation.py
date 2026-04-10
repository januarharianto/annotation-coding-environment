from ace.db.connection import create_project
from ace.models.annotation import (
    add_annotation,
    compact_deleted,
    delete_annotation,
    get_annotations_for_source,
    list_annotations,
    undelete_annotation,
)
from ace.models.project import add_coder
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


def test_undelete_annotation(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    aid = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    delete_annotation(conn, aid)
    assert len(get_annotations_for_source(conn, source_id)) == 0
    undelete_annotation(conn, aid)
    rows = get_annotations_for_source(conn, source_id)
    assert len(rows) == 1
    assert rows[0]["id"] == aid


# --- get_annotations_for_code ---

from ace.models.annotation import get_annotations_for_code
from ace.models.project import list_coders


def test_get_annotations_for_code(tmp_path):
    """Returns annotations across sources for a given code."""
    db_path = tmp_path / "test.ace"
    conn = create_project(db_path, "test")
    coder_id = list_coders(conn)[0]["id"]

    s1 = add_source(conn, "Doc1", "First source text here.", "row")
    s2 = add_source(conn, "Doc2", "Second source text here.", "row")
    code_a = add_code(conn, "Theme A", "#BF6030")
    code_b = add_code(conn, "Theme B", "#30A64E")

    add_annotation(conn, s1, coder_id, code_a, 0, 5, "First")
    add_annotation(conn, s2, coder_id, code_a, 0, 6, "Second")
    add_annotation(conn, s1, coder_id, code_b, 6, 12, "source")

    rows = get_annotations_for_code(conn, code_a, coder_id)
    assert len(rows) == 2
    assert rows[0]["display_id"] == "Doc1"
    assert rows[1]["display_id"] == "Doc2"
    assert rows[0]["selected_text"] == "First"
    conn.close()


def test_get_annotations_for_code_excludes_deleted(tmp_path):
    """Soft-deleted annotations are excluded."""
    db_path = tmp_path / "test.ace"
    conn = create_project(db_path, "test")
    coder_id = list_coders(conn)[0]["id"]

    s1 = add_source(conn, "Doc1", "Text.", "row")
    code_a = add_code(conn, "Theme A", "#BF6030")
    ann_id = add_annotation(conn, s1, coder_id, code_a, 0, 4, "Text")
    delete_annotation(conn, ann_id)

    rows = get_annotations_for_code(conn, code_a, coder_id)
    assert len(rows) == 0
    conn.close()


def test_get_annotations_for_code_empty(tmp_path):
    """Returns empty list when code has no annotations."""
    db_path = tmp_path / "test.ace"
    conn = create_project(db_path, "test")
    coder_id = list_coders(conn)[0]["id"]
    code_a = add_code(conn, "Theme A", "#BF6030")

    rows = get_annotations_for_code(conn, code_a, coder_id)
    assert len(rows) == 0
    conn.close()
