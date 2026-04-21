"""Tests for the undo/redo manager."""

import pytest
from ace.services.undo import UndoManager


def test_initial_state():
    mgr = UndoManager()
    assert not mgr.can_undo()
    assert not mgr.can_redo()


def test_record_add_then_undo():
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    assert mgr.can_undo()
    action = mgr.undo("src1")
    assert action == {"type": "undo_add", "annotation_id": "ann1"}
    assert not mgr.can_undo()


def test_record_delete_then_undo():
    mgr = UndoManager()
    mgr.record_delete("src1", "ann2")
    action = mgr.undo("src1")
    assert action == {"type": "undo_delete", "annotation_id": "ann2"}


def test_undo_then_redo():
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    mgr.undo("src1")
    assert mgr.can_redo()
    action = mgr.redo("src1")
    assert action == {"type": "redo_add", "annotation_id": "ann1"}


def test_redo_delete():
    mgr = UndoManager()
    mgr.record_delete("src1", "ann2")
    mgr.undo("src1")
    action = mgr.redo("src1")
    assert action == {"type": "redo_delete", "annotation_id": "ann2"}


def test_new_action_clears_redo():
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    mgr.undo("src1")
    assert mgr.can_redo()
    mgr.record_add("src1", "ann2")
    assert not mgr.can_redo()


def test_separate_sources():
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    mgr.record_add("src2", "ann2")
    action = mgr.undo("src1")
    assert action["annotation_id"] == "ann1"
    action = mgr.undo("src2")
    assert action["annotation_id"] == "ann2"


def test_undo_wrong_source_returns_none():
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    assert mgr.undo("src_other") is None


def test_redo_wrong_source_returns_none():
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    mgr.undo("src1")
    assert mgr.redo("src_other") is None


def test_clear_source():
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    mgr.clear("src1")
    assert mgr.undo("src1") is None


def test_record_merge_add_then_undo():
    """Merge-add pushes one compound action; undo returns both new + replaced ids."""
    mgr = UndoManager()
    mgr.record_merge_add("src1", "new_ann", ["old1", "old2"])
    assert mgr.can_undo()
    action = mgr.undo("src1")
    assert action == {
        "type": "undo_merge_add",
        "annotation_id": "new_ann",
        "replaced_ids": ["old1", "old2"],
    }


def test_merge_add_undo_then_redo():
    """Redo of a merge-add returns the same structure with redo_ prefix."""
    mgr = UndoManager()
    mgr.record_merge_add("src1", "new_ann", ["old1", "old2"])
    mgr.undo("src1")
    action = mgr.redo("src1")
    assert action == {
        "type": "redo_merge_add",
        "annotation_id": "new_ann",
        "replaced_ids": ["old1", "old2"],
    }


def test_new_merge_add_clears_redo():
    """Recording a new merge-add clears redo stack like other actions."""
    mgr = UndoManager()
    mgr.record_add("src1", "ann1")
    mgr.undo("src1")
    assert mgr.can_redo()
    mgr.record_merge_add("src1", "new_ann", ["old1"])
    assert not mgr.can_redo()


def test_merge_add_with_single_replaced():
    """Single-replacement merge still uses the compound action type."""
    mgr = UndoManager()
    mgr.record_merge_add("src1", "new_ann", ["old1"])
    action = mgr.undo("src1")
    assert action["type"] == "undo_merge_add"
    assert action["replaced_ids"] == ["old1"]
