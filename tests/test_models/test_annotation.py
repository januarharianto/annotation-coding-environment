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


# ----------------------------------------------------------------------
# add_annotation_merging — overlap detection + union merge on apply
# ----------------------------------------------------------------------

from ace.models.annotation import add_annotation_merging


def test_merging_no_overlap_creates_new_annotation(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 0, 4, "Some",
    )
    assert isinstance(new_id, str)
    assert replaced == []
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 1
    assert rows[0]["start_offset"] == 0 and rows[0]["end_offset"] == 4


def test_merging_exact_duplicate_range(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    old_id = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 0, 4, "Some",
    )
    assert new_id != old_id
    assert replaced == [old_id]
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 1
    assert rows[0]["id"] == new_id
    assert rows[0]["start_offset"] == 0 and rows[0]["end_offset"] == 4


def test_merging_new_inside_existing(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    old_id = add_annotation(conn, source_id, coder_id, code_id, 0, 15, "Some text conte")

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 5, 9, "text",
    )
    assert replaced == [old_id]
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 1
    assert rows[0]["start_offset"] == 0 and rows[0]["end_offset"] == 15


def test_merging_existing_inside_new(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    old_id = add_annotation(conn, source_id, coder_id, code_id, 5, 9, "text")

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 0, 15, "Some text conte",
    )
    assert replaced == [old_id]
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 1
    assert rows[0]["start_offset"] == 0 and rows[0]["end_offset"] == 15


def test_merging_touching_boundary(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    old_id = add_annotation(conn, source_id, coder_id, code_id, 0, 10, "Some text ")

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 10, 20, "content he",
    )
    assert replaced == [old_id]
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 1
    assert rows[0]["start_offset"] == 0 and rows[0]["end_offset"] == 20


def test_merging_multiple_disjoint_annotations(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    old1 = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    old2 = add_annotation(conn, source_id, coder_id, code_id, 10, 17, "content")

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 2, 15, "me text conten",
    )
    assert set(replaced) == {old1, old2}
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 1
    assert rows[0]["start_offset"] == 0 and rows[0]["end_offset"] == 17


def test_merging_different_code_untouched(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    other_code_id = add_code(conn, "Theme B", "#00FF00")
    other_id = add_annotation(conn, source_id, coder_id, other_code_id, 0, 10, "Some text ")

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 5, 15, "text conten",
    )
    assert replaced == []
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 2
    code_ids = {r["code_id"] for r in rows}
    assert code_ids == {code_id, other_code_id}


def test_merging_different_coder_untouched(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    other_coder = add_coder(conn, "Bob")
    bobs_id = add_annotation(conn, source_id, other_coder, code_id, 0, 10, "Some text ")

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 5, 15, "text conten",
    )
    assert replaced == []
    bobs_row = conn.execute(
        "SELECT * FROM annotation WHERE id = ? AND deleted_at IS NULL", (bobs_id,)
    ).fetchone()
    assert bobs_row is not None


def test_merging_ignores_soft_deleted(tmp_db):
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    old_id = add_annotation(conn, source_id, coder_id, code_id, 0, 10, "Some text ")
    delete_annotation(conn, old_id)

    new_id, replaced = add_annotation_merging(
        conn, source_id, coder_id, code_id, 5, 15, "text conten",
    )
    assert replaced == []
    rows = get_annotations_for_source(conn, source_id, coder_id)
    assert len(rows) == 1
    assert rows[0]["start_offset"] == 5 and rows[0]["end_offset"] == 15


# ----------------------------------------------------------------------
# reverse_merge_add / replay_merge_add — atomic undo/redo of merge-add
# ----------------------------------------------------------------------

from ace.models.annotation import reverse_merge_add, replay_merge_add


def test_reverse_merge_add_restores_originals_and_deletes_merged(tmp_db):
    """Reversing a merge: merged row becomes soft-deleted, originals undeleted."""
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    # Simulate a merge-add having happened: two originals are soft-deleted,
    # one merged row is active
    old1 = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    old2 = add_annotation(conn, source_id, coder_id, code_id, 10, 14, "cont")
    delete_annotation(conn, old1)
    delete_annotation(conn, old2)
    merged = add_annotation(conn, source_id, coder_id, code_id, 0, 14, "Some text con")

    reverse_merge_add(conn, merged, [old1, old2])

    # Merged row gone, originals restored
    active = get_annotations_for_source(conn, source_id, coder_id)
    ids = {r["id"] for r in active}
    assert ids == {old1, old2}
    merged_row = conn.execute(
        "SELECT deleted_at FROM annotation WHERE id = ?", (merged,)
    ).fetchone()
    assert merged_row["deleted_at"] is not None


def test_replay_merge_add_re_merges(tmp_db):
    """Replaying a merge: merged row restored, originals re-deleted."""
    conn = create_project(tmp_db, "Test")
    source_id, coder_id, code_id = _setup(conn)
    # After an undo of merge-add: two originals active, merged row soft-deleted
    old1 = add_annotation(conn, source_id, coder_id, code_id, 0, 4, "Some")
    old2 = add_annotation(conn, source_id, coder_id, code_id, 10, 14, "cont")
    merged = add_annotation(conn, source_id, coder_id, code_id, 0, 14, "Some text con")
    delete_annotation(conn, merged)

    replay_merge_add(conn, merged, [old1, old2])

    active = get_annotations_for_source(conn, source_id, coder_id)
    ids = {r["id"] for r in active}
    assert ids == {merged}
    for orig in (old1, old2):
        row = conn.execute(
            "SELECT deleted_at FROM annotation WHERE id = ?", (orig,)
        ).fetchone()
        assert row["deleted_at"] is not None
