"""Tests for the global undo/redo manager."""

import pytest
import sqlite3

from ace.db.connection import create_project
from ace.models.annotation import (
    add_annotation,
    add_annotation_merging,
    get_annotations_for_source,
)
from ace.models.codebook import add_code, list_codes, delete_code
from ace.models.assignment import add_assignment, get_assignments_for_coder, set_flagged
from ace.models.source import add_source
from ace.services.undo import UndoManager


@pytest.fixture
def project(tmp_path):
    """A tmp project with a coder, two sources, and one code."""
    db_path = tmp_path / "test.ace"
    conn = create_project(db_path, "Test")
    conn.row_factory = sqlite3.Row

    # Create coder
    conn.execute("INSERT INTO coder (id, name) VALUES ('c1', 'alice')")

    # Two sources — actual add_source signature is
    # (conn, display_id, content_text, source_type, filename=None, ...)
    src1 = add_source(conn, "src1.txt", "Hello world", "file", filename="src1.txt")
    src2 = add_source(conn, "src2.txt", "Goodbye world", "file", filename="src2.txt")

    # Assignments
    add_assignment(conn, src1, "c1")
    add_assignment(conn, src2, "c1")

    # Code
    code_id = add_code(conn, "Frustration", "#FF0000")

    conn.commit()
    yield {"conn": conn, "src1": src1, "src2": src2, "coder_id": "c1", "code_id": code_id}
    conn.close()


def test_initial_state():
    mgr = UndoManager()
    assert not mgr.can_undo()
    assert not mgr.can_redo()


def test_annotation_add_round_trip(project):
    mgr = UndoManager()
    conn = project["conn"]

    ann_id = add_annotation(conn, project["src1"], project["coder_id"], project["code_id"], 0, 5, "Hello")
    mgr.record_add(project["src1"], ann_id)

    # Undo: annotation soft-deleted
    result = mgr.undo(conn)
    assert result["description"].startswith("Undone:")
    assert result["source_id"] == project["src1"]
    rows = conn.execute(
        "SELECT deleted_at FROM annotation WHERE id = ?", (ann_id,)
    ).fetchone()
    assert rows["deleted_at"] is not None

    # Redo: annotation restored
    result = mgr.redo(conn)
    assert result["description"].startswith("Redone:")
    rows = conn.execute(
        "SELECT deleted_at FROM annotation WHERE id = ?", (ann_id,)
    ).fetchone()
    assert rows["deleted_at"] is None


def test_annotation_merge_add_round_trip(project):
    """Merging two existing annotations into one new one round-trips through undo/redo."""
    mgr = UndoManager()
    conn = project["conn"]
    src1 = project["src1"]
    coder_id = project["coder_id"]
    code_id = project["code_id"]

    # Two annotations whose spans fall inside the new merge range.
    a1 = add_annotation(conn, src1, coder_id, code_id, 0, 5, "Hello")
    a2 = add_annotation(conn, src1, coder_id, code_id, 6, 11, "world")

    # Merge: new range 0..11 overlaps both originals.
    merged_id, replaced_ids = add_annotation_merging(
        conn, src1, coder_id, code_id, 0, 11, "Hello world"
    )
    assert set(replaced_ids) == {a1, a2}
    mgr.record_merge_add(src1, merged_id, replaced_ids)

    # Undo: merged is soft-deleted, originals restored.
    result = mgr.undo(conn)
    assert result["description"].startswith("Undone:")
    assert result["source_id"] == src1
    merged_row = conn.execute(
        "SELECT deleted_at FROM annotation WHERE id = ?", (merged_id,)
    ).fetchone()
    assert merged_row["deleted_at"] is not None
    for ann_id in [a1, a2]:
        row = conn.execute(
            "SELECT deleted_at FROM annotation WHERE id = ?", (ann_id,)
        ).fetchone()
        assert row["deleted_at"] is None

    # Redo: merged is restored, originals soft-deleted again.
    result = mgr.redo(conn)
    assert result["description"].startswith("Redone:")
    merged_row = conn.execute(
        "SELECT deleted_at FROM annotation WHERE id = ?", (merged_id,)
    ).fetchone()
    assert merged_row["deleted_at"] is None
    for ann_id in [a1, a2]:
        row = conn.execute(
            "SELECT deleted_at FROM annotation WHERE id = ?", (ann_id,)
        ).fetchone()
        assert row["deleted_at"] is not None


def test_code_rename_round_trip(project):
    mgr = UndoManager()
    conn = project["conn"]

    conn.execute(
        "UPDATE codebook_code SET name = ? WHERE id = ?",
        ("Joy", project["code_id"]),
    )
    conn.commit()
    mgr.record_code_rename(project["code_id"], "Frustration", "Joy")

    mgr.undo(conn)
    name = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (project["code_id"],)
    ).fetchone()["name"]
    assert name == "Frustration"

    mgr.redo(conn)
    name = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (project["code_id"],)
    ).fetchone()["name"]
    assert name == "Joy"


def test_code_delete_cascade_round_trip(project):
    """Delete a code with annotations across two sources; undo restores both."""
    mgr = UndoManager()
    conn = project["conn"]

    a1 = add_annotation(conn, project["src1"], project["coder_id"], project["code_id"], 0, 5, "Hello")
    a2 = add_annotation(conn, project["src2"], project["coder_id"], project["code_id"], 0, 7, "Goodbye")

    affected = delete_code(conn, project["code_id"])
    mgr.record_code_delete(project["code_id"], affected)

    # Verify deletion
    assert list_codes(conn) == []

    # Undo: code and both annotations restored
    mgr.undo(conn)
    codes = list_codes(conn)
    assert len(codes) == 1
    assert codes[0]["id"] == project["code_id"]
    for ann_id in [a1, a2]:
        row = conn.execute(
            "SELECT deleted_at FROM annotation WHERE id = ?", (ann_id,)
        ).fetchone()
        assert row["deleted_at"] is None


def test_flag_toggle_round_trip(project):
    mgr = UndoManager()
    conn = project["conn"]

    set_flagged(conn, project["src1"], project["coder_id"], True)
    mgr.record_flag_toggle(project["src1"], project["coder_id"], prev_flagged=False)

    mgr.undo(conn)
    rows = get_assignments_for_coder(conn, project["coder_id"])
    src1_row = next(r for r in rows if r["source_id"] == project["src1"])
    assert src1_row["flagged"] == 0

    mgr.redo(conn)
    rows = get_assignments_for_coder(conn, project["coder_id"])
    src1_row = next(r for r in rows if r["source_id"] == project["src1"])
    assert src1_row["flagged"] == 1


def test_mixed_sequence(project):
    """annotation -> rename -> annotation -> undo*3 -> redo*3 returns to original."""
    mgr = UndoManager()
    conn = project["conn"]

    a1 = add_annotation(conn, project["src1"], project["coder_id"], project["code_id"], 0, 5, "Hello")
    mgr.record_add(project["src1"], a1)

    conn.execute("UPDATE codebook_code SET name = 'Joy' WHERE id = ?", (project["code_id"],))
    conn.commit()
    mgr.record_code_rename(project["code_id"], "Frustration", "Joy")

    a2 = add_annotation(conn, project["src1"], project["coder_id"], project["code_id"], 6, 11, "world")
    mgr.record_add(project["src1"], a2)

    # Undo three times
    mgr.undo(conn)  # remove a2
    mgr.undo(conn)  # rename Joy -> Frustration
    mgr.undo(conn)  # remove a1

    # State: no annotations, code named Frustration
    name = conn.execute("SELECT name FROM codebook_code WHERE id = ?", (project["code_id"],)).fetchone()["name"]
    assert name == "Frustration"
    active_anns = conn.execute(
        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()[0]
    assert active_anns == 0

    # Redo three times back to final
    mgr.redo(conn)
    mgr.redo(conn)
    mgr.redo(conn)
    name = conn.execute("SELECT name FROM codebook_code WHERE id = ?", (project["code_id"],)).fetchone()["name"]
    assert name == "Joy"
    active_anns = conn.execute(
        "SELECT COUNT(*) FROM annotation WHERE deleted_at IS NULL"
    ).fetchone()[0]
    assert active_anns == 2


def test_new_action_clears_redo(project):
    mgr = UndoManager()
    conn = project["conn"]

    a1 = add_annotation(conn, project["src1"], project["coder_id"], project["code_id"], 0, 5, "Hello")
    mgr.record_add(project["src1"], a1)
    mgr.undo(conn)
    assert mgr.can_redo()

    a2 = add_annotation(conn, project["src1"], project["coder_id"], project["code_id"], 6, 11, "world")
    mgr.record_add(project["src1"], a2)
    assert not mgr.can_redo()


def test_undo_empty_returns_none():
    mgr = UndoManager()
    assert mgr.undo(None) is None


def test_redo_empty_returns_none():
    mgr = UndoManager()
    assert mgr.redo(None) is None
