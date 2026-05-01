"""Tests for folder CRUD and move ops on the codebook."""
import pytest

from ace.db.connection import create_project, open_project
from ace.models.codebook import (
    add_code,
    add_folder,
    delete_code,
    list_codes_with_tree,
    move_code_to_parent,
    restore_code,
)
from ace.models.codebook_invariants import InvariantError


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.ace"
    create_project(str(db), "Test")
    return open_project(str(db))


def test_add_folder_at_root(conn):
    fid = add_folder(conn, "Themes")
    row = conn.execute(
        "SELECT name, kind, colour, chord, parent_id "
        "FROM codebook_code WHERE id = ?",
        (fid,),
    ).fetchone()
    assert row["name"] == "Themes"
    assert row["kind"] == "folder"
    assert row["colour"] == ""
    assert row["chord"] is None
    assert row["parent_id"] is None


def test_move_code_to_folder(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00")
    move_code_to_parent(conn, cid, fid)
    parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert parent == fid


def test_move_code_to_root(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    move_code_to_parent(conn, cid, None)
    parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert parent is None


def test_move_code_under_code_rejected(conn):
    cid_a = add_code(conn, "A", "#D55E00")
    cid_b = add_code(conn, "B", "#56B4E9")
    with pytest.raises(InvariantError, match="parent must be a folder"):
        move_code_to_parent(conn, cid_b, cid_a)


def test_move_folder_under_folder_rejected(conn):
    fid_a = add_folder(conn, "Outer")
    fid_b = add_folder(conn, "Inner")
    with pytest.raises(InvariantError, match="folders cannot be nested"):
        move_code_to_parent(conn, fid_b, fid_a)


def test_list_codes_with_tree_returns_dfs_order(conn):
    fid = add_folder(conn, "Themes")
    add_code(conn, "Identity", "#D55E00", parent_id=fid)
    add_code(conn, "Belonging", "#56B4E9", parent_id=fid)
    add_code(conn, "Trust", "#0072B2")

    tree = list_codes_with_tree(conn)
    # Expect: [folder Themes, code Identity, code Belonging, code Trust]
    assert [r["kind"] for r in tree] == ["folder", "code", "code", "code"]
    assert [r["name"] for r in tree] == ["Themes", "Identity", "Belonging", "Trust"]
    # The folder row carries `child_ids` and `child_count`
    folder_row = tree[0]
    assert folder_row["child_count"] == 2


def test_delete_folder_lifts_children_to_root(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    affected_annotations, affected_children = delete_code(conn, fid)
    assert affected_annotations == []
    assert affected_children == [cid]
    # Folder soft-deleted
    deleted_at = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id = ?", (fid,)
    ).fetchone()[0]
    assert deleted_at is not None
    # Child lifted to root
    child_parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert child_parent is None


def test_restore_folder_relinks_children(conn):
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Identity", "#D55E00", parent_id=fid)
    _, children_lifted = delete_code(conn, fid)
    restore_code(conn, fid, annotation_ids=[], children_lifted_ids=children_lifted)
    # Folder restored
    deleted_at = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id = ?", (fid,)
    ).fetchone()[0]
    assert deleted_at is None
    # Children re-linked
    child_parent = conn.execute(
        "SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)
    ).fetchone()[0]
    assert child_parent == fid
