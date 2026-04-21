"""In-memory undo/redo manager for annotation operations.

Stacks are per-source and lost on navigation or app restart.

Stack entries are tuples:
    ("add", annotation_id, None)
    ("delete", annotation_id, None)
    ("merge_add", new_annotation_id, [replaced_ids])  # compound

Undo returns a dict with "type", "annotation_id", and — for merge_add —
"replaced_ids". The callers in routes/api.py dispatch on "type".
"""

from collections import defaultdict


class UndoManager:
    def __init__(self):
        self._undo: dict[str, list[tuple[str, str, list[str] | None]]] = defaultdict(list)
        self._redo: dict[str, list[tuple[str, str, list[str] | None]]] = defaultdict(list)

    def record_add(self, source_id: str, annotation_id: str) -> None:
        self._undo[source_id].append(("add", annotation_id, None))
        self._redo[source_id].clear()

    def record_delete(self, source_id: str, annotation_id: str) -> None:
        self._undo[source_id].append(("delete", annotation_id, None))
        self._redo[source_id].clear()

    def record_merge_add(
        self, source_id: str, new_annotation_id: str, replaced_ids: list[str]
    ) -> None:
        """Record a compound merge-add: one insert + N soft-deletes replayed together."""
        self._undo[source_id].append(("merge_add", new_annotation_id, list(replaced_ids)))
        self._redo[source_id].clear()

    def can_undo(self) -> bool:
        return any(bool(stack) for stack in self._undo.values())

    def can_redo(self) -> bool:
        return any(bool(stack) for stack in self._redo.values())

    def undo(self, source_id: str) -> dict | None:
        stack = self._undo.get(source_id)
        if not stack:
            return None
        action, ann_id, replaced = stack.pop()
        self._redo[source_id].append((action, ann_id, replaced))
        result = {"type": f"undo_{action}", "annotation_id": ann_id}
        if replaced is not None:
            result["replaced_ids"] = replaced
        return result

    def redo(self, source_id: str) -> dict | None:
        stack = self._redo.get(source_id)
        if not stack:
            return None
        action, ann_id, replaced = stack.pop()
        self._undo[source_id].append((action, ann_id, replaced))
        result = {"type": f"redo_{action}", "annotation_id": ann_id}
        if replaced is not None:
            result["replaced_ids"] = replaced
        return result

    def clear(self, source_id: str) -> None:
        self._undo.pop(source_id, None)
        self._redo.pop(source_id, None)
