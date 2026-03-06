"""In-memory undo/redo manager for annotation operations.

Stacks are per-source and lost on navigation or app restart.
"""

from collections import defaultdict


class UndoManager:
    def __init__(self):
        self._undo: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._redo: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def record_add(self, source_id: str, annotation_id: str) -> None:
        self._undo[source_id].append(("add", annotation_id))
        self._redo[source_id].clear()

    def record_delete(self, source_id: str, annotation_id: str) -> None:
        self._undo[source_id].append(("delete", annotation_id))
        self._redo[source_id].clear()

    def can_undo(self) -> bool:
        return any(bool(stack) for stack in self._undo.values())

    def can_redo(self) -> bool:
        return any(bool(stack) for stack in self._redo.values())

    def undo(self, source_id: str) -> dict | None:
        stack = self._undo.get(source_id)
        if not stack:
            return None
        action, ann_id = stack.pop()
        self._redo[source_id].append((action, ann_id))
        return {"type": f"undo_{action}", "annotation_id": ann_id}

    def redo(self, source_id: str) -> dict | None:
        stack = self._redo.get(source_id)
        if not stack:
            return None
        action, ann_id = stack.pop()
        self._undo[source_id].append((action, ann_id))
        return {"type": f"redo_{action}", "annotation_id": ann_id}

    def clear(self, source_id: str) -> None:
        self._undo.pop(source_id, None)
        self._redo.pop(source_id, None)
