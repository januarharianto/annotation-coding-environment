"""Project-scoped global undo/redo manager.

Stacks live in app.state.undo_managers[project_path] (one per open project).
In-memory only; lost on app exit.

Each entry is a typed UndoEntry. Each op has a (undo_handler, redo_handler)
pair registered in `_HANDLERS`. Handlers take the full UndoEntry (so the
flag-toggle handler can read `entry.source_id` without it being duplicated
into the payload) and return `(description, flash_annotation_id | None)`.

Descriptions are computed at undo/redo time so they reflect current entity
names — if a code was renamed since the op was recorded, the description
uses the current name.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal

logger = logging.getLogger(__name__)


OpType = Literal[
    "annotation_add",
    "annotation_delete",
    "annotation_merge_add",
    "code_add",
    "code_delete",
    "code_rename",
    "code_recolour",
    "code_chord",
    "code_reorder",
    "flag_toggle",
    "codebook_import",
    # NEW for v7 folder model:
    "code_create_folder",
    "code_move_parent",
    "code_indent_promote_to_folder",
    "code_delete_folder_cascade",
]


@dataclass
class UndoEntry:
    op: OpType
    source_id: str | None = None
    payload: dict = field(default_factory=dict)


HandlerResult = tuple[str, str | None]
Handler = Callable[["object", UndoEntry], HandlerResult]


class UndoManager:
    def __init__(self) -> None:
        self.undo_stack: list[UndoEntry] = []
        self.redo_stack: list[UndoEntry] = []

    def _push(self, entry: UndoEntry) -> None:
        self.undo_stack.append(entry)
        self.redo_stack.clear()

    def record_add(self, source_id: str, annotation_id: str) -> None:
        self._push(UndoEntry(
            op="annotation_add",
            source_id=source_id,
            payload={"annotation_id": annotation_id},
        ))

    def record_delete(self, source_id: str, annotation_id: str) -> None:
        self._push(UndoEntry(
            op="annotation_delete",
            source_id=source_id,
            payload={"annotation_id": annotation_id},
        ))

    def record_merge_add(
        self, source_id: str, new_annotation_id: str, replaced_ids: list[str]
    ) -> None:
        self._push(UndoEntry(
            op="annotation_merge_add",
            source_id=source_id,
            payload={
                "annotation_id": new_annotation_id,
                "replaced_ids": list(replaced_ids),
            },
        ))

    def record_code_add(self, code_id: str) -> None:
        self._push(UndoEntry(op="code_add", payload={"code_id": code_id}))

    def record_code_delete(
        self,
        code_id: str,
        affected_annotation_ids: list[str],
        prev_parent_id: str | None = None,
        prev_sort_order: int = 0,
        children_lifted_ids: list[str] | None = None,
    ) -> None:
        self._push(UndoEntry(
            op="code_delete",
            payload={
                "code_id": code_id,
                "affected_annotation_ids": list(affected_annotation_ids),
                "prev_parent_id": prev_parent_id,
                "prev_sort_order": prev_sort_order,
                "children_lifted_ids": list(children_lifted_ids or []),
            },
        ))

    def record_code_rename(self, code_id: str, prev_name: str, new_name: str) -> None:
        self._push(UndoEntry(
            op="code_rename",
            payload={"code_id": code_id, "prev_name": prev_name, "new_name": new_name},
        ))

    def record_code_recolour(self, code_id: str, prev_colour: str, new_colour: str) -> None:
        self._push(UndoEntry(
            op="code_recolour",
            payload={"code_id": code_id, "prev_colour": prev_colour, "new_colour": new_colour},
        ))

    def record_code_chord(
        self, code_id: str, prev_chord: str | None, new_chord: str | None
    ) -> None:
        # `prev_chord` may be None (the code had no chord override before) —
        # the undo handler restores it via set_chord which accepts NULL.
        self._push(UndoEntry(
            op="code_chord",
            payload={"code_id": code_id, "prev_chord": prev_chord, "new_chord": new_chord},
        ))

    def record_code_reorder(
        self, prev: list[tuple[str, int]], new: list[tuple[str, int]]
    ) -> None:
        self._push(UndoEntry(
            op="code_reorder",
            payload={"prev": list(prev), "new": list(new)},
        ))

    def record_flag_toggle(self, source_id: str, coder_id: str, prev_flagged: bool) -> None:
        # coder_id is captured so the inverse hits the same coder's row even
        # in a project with multiple coders assigned to the same source.
        self._push(UndoEntry(
            op="flag_toggle",
            source_id=source_id,
            payload={"coder_id": coder_id, "prev_flagged": bool(prev_flagged)},
        ))

    def record_codebook_import(self, imported_code_ids: list[str]) -> None:
        self._push(UndoEntry(
            op="codebook_import",
            payload={"imported_code_ids": list(imported_code_ids)},
        ))

    def record_create_folder(self, folder_id: str) -> None:
        self._push(UndoEntry(
            op="code_create_folder",
            payload={"folder_id": folder_id},
        ))

    def record_move_parent(
        self,
        code_id: str,
        prev_parent_id: str | None,
        new_parent_id: str | None,
        prev_source_ordering: list[tuple[str, int]],
        prev_dest_ordering: list[tuple[str, int]],
    ) -> None:
        """Record a parent change.

        Both source-scope and dest-scope orderings are snapshotted in full
        so undo can restore sibling sort_orders that move_code_to_parent
        renumbered when it placed the moved code at MAX(sort_order)+1.

        `prev_source_ordering` / `prev_dest_ordering` — list of (id, sort_order)
        pairs captured BEFORE the move.
        """
        self._push(UndoEntry(
            op="code_move_parent",
            payload={
                "code_id": code_id,
                "prev_parent_id": prev_parent_id,
                "new_parent_id": new_parent_id,
                "prev_source_ordering": list(prev_source_ordering),
                "prev_dest_ordering": list(prev_dest_ordering),
            },
        ))

    def record_indent_promote_to_folder(
        self,
        folder_id: str,
        code_ids: list[str],
        prev_sort_orders: list[int],
    ) -> None:
        self._push(UndoEntry(
            op="code_indent_promote_to_folder",
            payload={
                "folder_id": folder_id,
                "code_ids": list(code_ids),
                "prev_sort_orders": list(prev_sort_orders),
            },
        ))

    def record_delete_folder_cascade(
        self,
        folder_id: str,
        child_ids: list[str],
        annotation_ids: list[str],
    ) -> None:
        self._push(UndoEntry(
            op="code_delete_folder_cascade",
            payload={
                "folder_id": folder_id,
                "child_ids": list(child_ids),
                "annotation_ids": list(annotation_ids),
            },
        ))

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def _replay(self, conn, entry: UndoEntry, direction: int) -> dict:
        try:
            handler = _HANDLERS[entry.op][direction]
            description, flash_id = handler(conn, entry)
        except Exception:
            # Re-push so the user can retry after fixing whatever went wrong.
            (self.undo_stack if direction == 0 else self.redo_stack).append(entry)
            logger.exception("%s handler for %s failed",
                             "undo" if direction == 0 else "redo", entry.op)
            raise
        prefix = "Undone" if direction == 0 else "Redone"
        return {
            "description": f"{prefix}: {description}",
            "source_id": entry.source_id,
            "flash_annotation_id": flash_id,
        }

    def undo(self, conn) -> dict | None:
        if not self.undo_stack:
            return None
        entry = self.undo_stack.pop()
        result = self._replay(conn, entry, direction=0)
        self.redo_stack.append(entry)
        return result

    def redo(self, conn) -> dict | None:
        if not self.redo_stack:
            return None
        entry = self.redo_stack.pop()
        result = self._replay(conn, entry, direction=1)
        self.undo_stack.append(entry)
        return result


# ---------------------------------------------------------------------------
# Description helpers (run at replay time, reflect current entity names)
# ---------------------------------------------------------------------------


def _code_name(conn, code_id: str) -> str:
    row = conn.execute(
        "SELECT name FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    return row["name"] if row else "(deleted code)"


def _source_display_id(conn, source_id: str) -> str:
    row = conn.execute(
        "SELECT display_id FROM source WHERE id = ?", (source_id,)
    ).fetchone()
    return row["display_id"] if row else "(unknown source)"


def _annotation_code_and_source(conn, annotation_id: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT code_id, source_id FROM annotation WHERE id = ?",
        (annotation_id,),
    ).fetchone()
    if not row:
        return "(unknown code)", "(unknown source)"
    return _code_name(conn, row["code_id"]), _source_display_id(conn, row["source_id"])


# ---------------------------------------------------------------------------
# Op handlers — each returns (description, flash_annotation_id_or_None).
# Flash_id is set only when the op restored an annotation (so the client
# can briefly highlight it after the swap settles).
# ---------------------------------------------------------------------------


def _undo_annotation_add(conn, entry):
    from ace.models.annotation import delete_annotation
    code_name, src = _annotation_code_and_source(conn, entry.payload["annotation_id"])
    delete_annotation(conn, entry.payload["annotation_id"])
    return f"applied '{code_name}' on {src}", None


def _redo_annotation_add(conn, entry):
    from ace.models.annotation import undelete_annotation
    undelete_annotation(conn, entry.payload["annotation_id"])
    code_name, src = _annotation_code_and_source(conn, entry.payload["annotation_id"])
    return f"applied '{code_name}' on {src}", entry.payload["annotation_id"]


def _undo_annotation_delete(conn, entry):
    from ace.models.annotation import undelete_annotation
    undelete_annotation(conn, entry.payload["annotation_id"])
    code_name, src = _annotation_code_and_source(conn, entry.payload["annotation_id"])
    return f"removed '{code_name}' from {src}", entry.payload["annotation_id"]


def _redo_annotation_delete(conn, entry):
    from ace.models.annotation import delete_annotation
    code_name, src = _annotation_code_and_source(conn, entry.payload["annotation_id"])
    delete_annotation(conn, entry.payload["annotation_id"])
    return f"removed '{code_name}' from {src}", None


def _undo_annotation_merge_add(conn, entry):
    from ace.models.annotation import reverse_merge_add
    code_name, src = _annotation_code_and_source(conn, entry.payload["annotation_id"])
    reverse_merge_add(conn, entry.payload["annotation_id"], entry.payload["replaced_ids"])
    return f"merged annotations on {src} (code '{code_name}')", None


def _redo_annotation_merge_add(conn, entry):
    from ace.models.annotation import replay_merge_add
    replay_merge_add(conn, entry.payload["annotation_id"], entry.payload["replaced_ids"])
    code_name, src = _annotation_code_and_source(conn, entry.payload["annotation_id"])
    return f"merged annotations on {src} (code '{code_name}')", entry.payload["annotation_id"]


def _undo_code_add(conn, entry):
    from ace.models.codebook import delete_code
    code_name = _code_name(conn, entry.payload["code_id"])
    # Linear-undo invariant: any annotations made with this code are later
    # entries on the stack and have already been undone, so the cascade is
    # a no-op.
    delete_code(conn, entry.payload["code_id"])
    return f"added code '{code_name}'", None


def _redo_code_add(conn, entry):
    from ace.models.codebook import restore_code
    restore_code(conn, entry.payload["code_id"], [])
    code_name = _code_name(conn, entry.payload["code_id"])
    return f"added code '{code_name}'", None


def _undo_code_delete(conn, entry):
    from ace.models.codebook import restore_code
    affected = entry.payload["affected_annotation_ids"]
    children_lifted = entry.payload.get("children_lifted_ids", [])
    restore_code(conn, entry.payload["code_id"], affected, children_lifted)
    # Restore the row's prior parent and sort_order so undo puts the code
    # back where it was, not at root / end-of-list.
    prev_parent = entry.payload.get("prev_parent_id")
    prev_sort_order = entry.payload.get("prev_sort_order", 0)
    try:
        conn.execute(
            "UPDATE codebook_code SET parent_id = ?, sort_order = ? WHERE id = ?",
            (prev_parent, prev_sort_order, entry.payload["code_id"]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    code_name = _code_name(conn, entry.payload["code_id"])
    suffix = f" ({len(affected)} annotations restored)" if affected else ""
    flash_id = affected[0] if affected else None
    return f"deleted '{code_name}'{suffix}", flash_id


def _redo_code_delete(conn, entry):
    from ace.models.codebook import delete_code
    code_name = _code_name(conn, entry.payload["code_id"])
    # delete_code now returns (annotation_ids, children_lifted_ids); we
    # discard both because the recorded payload matches the linear-undo
    # state at the time the entry was first pushed.
    delete_code(conn, entry.payload["code_id"])
    return f"deleted '{code_name}'", None


def _set_code_field(conn, code_id: str, column: str, value) -> None:
    # column is always a hard-coded literal from the call site below — not
    # user input — so f-string interpolation is safe here.
    conn.execute(f"UPDATE codebook_code SET {column} = ? WHERE id = ?", (value, code_id))
    conn.commit()


def _undo_code_rename(conn, entry):
    _set_code_field(conn, entry.payload["code_id"], "name", entry.payload["prev_name"])
    return f"renamed '{entry.payload['new_name']}' back to '{entry.payload['prev_name']}'", None


def _redo_code_rename(conn, entry):
    _set_code_field(conn, entry.payload["code_id"], "name", entry.payload["new_name"])
    return f"renamed '{entry.payload['prev_name']}' to '{entry.payload['new_name']}'", None


def _undo_code_recolour(conn, entry):
    _set_code_field(conn, entry.payload["code_id"], "colour", entry.payload["prev_colour"])
    return f"code '{_code_name(conn, entry.payload['code_id'])}' colour reverted", None


def _redo_code_recolour(conn, entry):
    _set_code_field(conn, entry.payload["code_id"], "colour", entry.payload["new_colour"])
    return f"code '{_code_name(conn, entry.payload['code_id'])}' recoloured", None


def _undo_code_chord(conn, entry):
    # set_chord accepts NULL — used to restore the prior unset state.
    from ace.models.codebook import set_chord
    set_chord(conn, entry.payload["code_id"], entry.payload["prev_chord"])
    return f"chord on '{_code_name(conn, entry.payload['code_id'])}' reverted", None


def _redo_code_chord(conn, entry):
    from ace.models.codebook import set_chord
    set_chord(conn, entry.payload["code_id"], entry.payload["new_chord"])
    return f"chord on '{_code_name(conn, entry.payload['code_id'])}' reapplied", None


def _apply_reorder(conn, ordering: list[tuple[str, int]]) -> None:
    try:
        for code_id, sort_order in ordering:
            conn.execute(
                "UPDATE codebook_code SET sort_order = ? WHERE id = ?",
                (sort_order, code_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _undo_code_reorder(conn, entry):
    _apply_reorder(conn, entry.payload["prev"])
    return "code order", None


def _redo_code_reorder(conn, entry):
    _apply_reorder(conn, entry.payload["new"])
    return "code order", None


def _set_flag(conn, source_id: str, coder_id: str, flagged: bool) -> str:
    from ace.models.assignment import set_flagged
    set_flagged(conn, source_id, coder_id, flagged)
    return _source_display_id(conn, source_id)


def _undo_flag_toggle(conn, entry):
    src = _set_flag(
        conn, entry.source_id, entry.payload["coder_id"], entry.payload["prev_flagged"]
    )
    return f"flag on {src}", None


def _redo_flag_toggle(conn, entry):
    src = _set_flag(
        conn, entry.source_id, entry.payload["coder_id"], not entry.payload["prev_flagged"]
    )
    return f"flag on {src}", None


def _undo_codebook_import(conn, entry):
    from ace.models.codebook import delete_code
    ids = entry.payload["imported_code_ids"]
    for cid in ids:
        # delete_code returns (annotation_ids, children_lifted_ids); we
        # discard both since linear-undo guarantees there are no annotations
        # on a freshly-imported (and not-yet-used) code.
        delete_code(conn, cid)
    n = len(ids)
    return f"imported {n} code{'s' if n != 1 else ''}", None


def _redo_codebook_import(conn, entry):
    from ace.models.codebook import restore_code
    ids = entry.payload["imported_code_ids"]
    for cid in ids:
        restore_code(conn, cid, [])
    n = len(ids)
    return f"imported {n} code{'s' if n != 1 else ''}", None


# ---------------------------------------------------------------------------
# Folder-tree op handlers (v7).
# ---------------------------------------------------------------------------


def _undo_create_folder(conn, entry):
    fid = entry.payload["folder_id"]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE codebook_code SET deleted_at = ? WHERE id = ?", (now, fid))
    conn.commit()
    name = conn.execute("SELECT name FROM codebook_code WHERE id = ?", (fid,)).fetchone()
    return (f"Removed folder {name[0]!r}" if name else "Removed folder", None)


def _redo_create_folder(conn, entry):
    fid = entry.payload["folder_id"]
    conn.execute("UPDATE codebook_code SET deleted_at = NULL WHERE id = ?", (fid,))
    conn.commit()
    name = conn.execute("SELECT name FROM codebook_code WHERE id = ?", (fid,)).fetchone()
    return (f"Restored folder {name[0]!r}" if name else "Restored folder", None)


def _undo_move_parent(conn, entry):
    """Restore parent_id AND every sibling's sort_order in both scopes.

    Wrapped in try/rollback per audit finding — multi-statement undos must
    not leave the DB in a half-applied state if any step fails.
    """
    p = entry.payload
    try:
        # Restore moved code's parent_id (sort_order is restored via the
        # source-ordering update below).
        conn.execute(
            "UPDATE codebook_code SET parent_id = ? WHERE id = ?",
            (p["prev_parent_id"], p["code_id"]),
        )
        # Restore source-scope ordering (siblings move_code_to_parent renumbered)
        for cid, sort_order in p["prev_source_ordering"]:
            conn.execute(
                "UPDATE codebook_code SET sort_order = ? WHERE id = ?",
                (sort_order, cid),
            )
        # Restore destination-scope ordering (siblings shifted by the inserted code)
        for cid, sort_order in p["prev_dest_ordering"]:
            conn.execute(
                "UPDATE codebook_code SET sort_order = ? WHERE id = ?",
                (sort_order, cid),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ("Moved code back", None)


def _redo_move_parent(conn, entry):
    from ace.models.codebook import move_code_to_parent
    p = entry.payload
    move_code_to_parent(conn, p["code_id"], p["new_parent_id"])
    return ("Moved code", None)


def _undo_indent_promote_to_folder(conn, entry):
    """Soft-delete the auto-created folder and lift both codes back to root
    with their original sort_orders. Wrapped in try/rollback."""
    p = entry.payload
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "UPDATE codebook_code SET deleted_at = ? WHERE id = ?",
            (now, p["folder_id"]),
        )
        for cid, prev_sort in zip(p["code_ids"], p["prev_sort_orders"]):
            conn.execute(
                "UPDATE codebook_code SET parent_id = NULL, sort_order = ? WHERE id = ?",
                (prev_sort, cid),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ("Removed new folder", None)


def _redo_indent_promote_to_folder(conn, entry):
    """Re-create the folder grouping in a single transaction.

    Uses `_move_code_to_parent_no_commit` so all writes commit atomically;
    if any step raises mid-loop we roll back cleanly rather than leaving a
    partial regrouping behind.
    """
    from ace.models.codebook import _move_code_to_parent_no_commit
    p = entry.payload
    try:
        conn.execute(
            "UPDATE codebook_code SET deleted_at = NULL WHERE id = ?",
            (p["folder_id"],),
        )
        for cid in p["code_ids"]:
            _move_code_to_parent_no_commit(conn, cid, p["folder_id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ("Re-grouped", None)


def _undo_delete_folder_cascade(conn, entry):
    """Restore the folder and re-link children. restore_code handles
    its own try/rollback internally."""
    from ace.models.codebook import restore_code
    p = entry.payload
    restore_code(
        conn,
        code_id=p["folder_id"],
        annotation_ids=p["annotation_ids"],
        children_lifted_ids=p["child_ids"],
    )
    return ("Restored folder", None)


def _redo_delete_folder_cascade(conn, entry):
    from ace.models.codebook import delete_code
    p = entry.payload
    delete_code(conn, p["folder_id"])
    return ("Deleted folder", None)


# Single registry of (undo, redo) handler pairs, keyed by op type. Adding a
# new op is one entry here plus one record_* method on UndoManager.
_HANDLERS: dict[OpType, tuple[Handler, Handler]] = {
    "annotation_add":                (_undo_annotation_add,              _redo_annotation_add),
    "annotation_delete":             (_undo_annotation_delete,           _redo_annotation_delete),
    "annotation_merge_add":          (_undo_annotation_merge_add,        _redo_annotation_merge_add),
    "code_add":                      (_undo_code_add,                    _redo_code_add),
    "code_delete":                   (_undo_code_delete,                 _redo_code_delete),
    "code_rename":                   (_undo_code_rename,                 _redo_code_rename),
    "code_recolour":                 (_undo_code_recolour,               _redo_code_recolour),
    "code_chord":                    (_undo_code_chord,                  _redo_code_chord),
    "code_reorder":                  (_undo_code_reorder,                _redo_code_reorder),
    "flag_toggle":                   (_undo_flag_toggle,                 _redo_flag_toggle),
    "codebook_import":               (_undo_codebook_import,             _redo_codebook_import),
    "code_create_folder":            (_undo_create_folder,               _redo_create_folder),
    "code_move_parent":              (_undo_move_parent,                 _redo_move_parent),
    "code_indent_promote_to_folder": (_undo_indent_promote_to_folder,    _redo_indent_promote_to_folder),
    "code_delete_folder_cascade":    (_undo_delete_folder_cascade,       _redo_delete_folder_cascade),
}
