"""Undo handlers for the new codebook folder operations."""
import pytest

from ace.db.connection import open_project, create_project
from ace.models.codebook import (
    add_code, add_folder, move_code_to_parent, delete_code, list_codes, set_chord,
)
from ace.services.undo import UndoManager


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.ace"
    create_project(str(db), "Test")
    return open_project(str(db))


def test_undo_create_folder_soft_deletes_it(conn):
    mgr = UndoManager()
    fid = add_folder(conn, "Themes")
    mgr.record_create_folder(fid)

    assert mgr.undo(conn) is not None
    deleted_at = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id = ?", (fid,)
    ).fetchone()[0]
    assert deleted_at is not None


def _snapshot_scope(conn, parent_id):
    """List of (id, sort_order) for everything in a scope. Helper for undo tests."""
    rows = conn.execute(
        "SELECT id, sort_order FROM codebook_code "
        "WHERE deleted_at IS NULL "
        "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?)",
        (parent_id, parent_id),
    ).fetchall()
    return [(r["id"], r["sort_order"]) for r in rows]


def test_undo_move_parent_restores_sibling_orderings(conn):
    """After move-and-undo, both source and dest scopes are sort-order-byte-identical
    to the pre-move snapshot."""
    mgr = UndoManager()
    fid = add_folder(conn, "Themes")
    cid_a = add_code(conn, "Identity", "#D55E00")
    cid_b = add_code(conn, "Belonging", "#56B4E9")  # also at root
    cid_in = add_code(conn, "Existing", "#009E73", parent_id=fid)

    pre_source = _snapshot_scope(conn, None)
    pre_dest = _snapshot_scope(conn, fid)
    move_code_to_parent(conn, cid_a, fid)
    mgr.record_move_parent(
        cid_a,
        prev_parent_id=None,
        new_parent_id=fid,
        prev_source_ordering=pre_source,
        prev_dest_ordering=pre_dest,
    )

    assert mgr.undo(conn) is not None
    post_source = _snapshot_scope(conn, None)
    post_dest = _snapshot_scope(conn, fid)
    assert sorted(post_source) == sorted(pre_source)
    assert sorted(post_dest) == sorted(pre_dest)


def test_undo_indent_promote_to_folder_removes_folder_and_lifts_codes(conn):
    mgr = UndoManager()
    cid_a = add_code(conn, "Identity", "#D55E00")
    cid_b = add_code(conn, "Belonging", "#56B4E9")
    sort_a = conn.execute("SELECT sort_order FROM codebook_code WHERE id=?", (cid_a,)).fetchone()[0]
    sort_b = conn.execute("SELECT sort_order FROM codebook_code WHERE id=?", (cid_b,)).fetchone()[0]

    fid = add_folder(conn, "New folder")
    move_code_to_parent(conn, cid_a, fid)
    move_code_to_parent(conn, cid_b, fid)
    mgr.record_indent_promote_to_folder(
        folder_id=fid, code_ids=[cid_a, cid_b],
        prev_sort_orders=[sort_a, sort_b],
    )

    assert mgr.undo(conn) is not None
    folder_deleted = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id=?", (fid,)
    ).fetchone()[0]
    assert folder_deleted is not None
    for cid, prev_sort in [(cid_a, sort_a), (cid_b, sort_b)]:
        row = conn.execute(
            "SELECT parent_id, sort_order FROM codebook_code WHERE id=?", (cid,)
        ).fetchone()
        assert row["parent_id"] is None
        assert row["sort_order"] == prev_sort


def test_undo_code_chord_round_trip(conn):
    """Setting a chord then undoing restores the prior NULL; redoing
    re-applies. Covers the new code_chord op type end-to-end."""
    mgr = UndoManager()
    cid = add_code(conn, "Identity", "#D55E00")
    prior = conn.execute(
        "SELECT chord FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()["chord"]

    set_chord(conn, cid, "qz")
    mgr.record_code_chord(cid, prior, "qz")

    assert mgr.undo(conn) is not None
    after_undo = conn.execute(
        "SELECT chord FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()["chord"]
    assert after_undo == prior

    assert mgr.redo(conn) is not None
    after_redo = conn.execute(
        "SELECT chord FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()["chord"]
    assert after_redo == "qz"


def test_undo_delete_folder_cascade_relinks_children(conn):
    mgr = UndoManager()
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    affected_anns, affected_children = delete_code(conn, fid)
    mgr.record_delete_folder_cascade(
        folder_id=fid,
        child_ids=affected_children,
        annotation_ids=affected_anns,
    )

    assert mgr.undo(conn) is not None
    row = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id=?", (fid,)
    ).fetchone()
    assert row[0] is None
    child_parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id=?", (cid,)
    ).fetchone()[0]
    assert child_parent == fid
