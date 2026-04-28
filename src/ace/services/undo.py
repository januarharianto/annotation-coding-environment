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
    "code_change_group",
    "code_reorder",
    "group_rename",
    "flag_toggle",
    "codebook_import",
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

    def record_code_delete(self, code_id: str, affected_annotation_ids: list[str]) -> None:
        self._push(UndoEntry(
            op="code_delete",
            payload={
                "code_id": code_id,
                "affected_annotation_ids": list(affected_annotation_ids),
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

    def record_code_change_group(
        self, code_id: str, prev_group: str | None, new_group: str | None
    ) -> None:
        self._push(UndoEntry(
            op="code_change_group",
            payload={"code_id": code_id, "prev_group": prev_group, "new_group": new_group},
        ))

    def record_code_reorder(
        self, prev: list[tuple[str, int]], new: list[tuple[str, int]]
    ) -> None:
        self._push(UndoEntry(
            op="code_reorder",
            payload={"prev": list(prev), "new": list(new)},
        ))

    def record_group_rename(self, old_name: str | None, new_name: str | None) -> None:
        self._push(UndoEntry(
            op="group_rename",
            payload={"old_name": old_name, "new_name": new_name},
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
    restore_code(conn, entry.payload["code_id"], affected)
    code_name = _code_name(conn, entry.payload["code_id"])
    suffix = f" ({len(affected)} annotations restored)" if affected else ""
    flash_id = affected[0] if affected else None
    return f"deleted '{code_name}'{suffix}", flash_id


def _redo_code_delete(conn, entry):
    from ace.models.codebook import delete_code
    code_name = _code_name(conn, entry.payload["code_id"])
    # Linear-undo invariant: delete_code's return matches the recorded
    # affected_annotation_ids, so we don't need it.
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


def _undo_code_change_group(conn, entry):
    _set_code_field(conn, entry.payload["code_id"], "group_name", entry.payload["prev_group"])
    name = _code_name(conn, entry.payload["code_id"])
    return f"moved '{name}' to group '{entry.payload['prev_group'] or 'none'}'", None


def _redo_code_change_group(conn, entry):
    _set_code_field(conn, entry.payload["code_id"], "group_name", entry.payload["new_group"])
    name = _code_name(conn, entry.payload["code_id"])
    return f"moved '{name}' to group '{entry.payload['new_group'] or 'none'}'", None


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


def _undo_group_rename(conn, entry):
    from ace.models.codebook import rename_group
    rename_group(conn, entry.payload["new_name"] or "", entry.payload["old_name"] or "")
    return f"renamed group '{entry.payload['new_name']}' back to '{entry.payload['old_name']}'", None


def _redo_group_rename(conn, entry):
    from ace.models.codebook import rename_group
    rename_group(conn, entry.payload["old_name"] or "", entry.payload["new_name"] or "")
    return f"renamed group '{entry.payload['old_name']}' to '{entry.payload['new_name']}'", None


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


# Single registry of (undo, redo) handler pairs, keyed by op type. Adding a
# new op is one entry here plus one record_* method on UndoManager.
_HANDLERS: dict[OpType, tuple[Handler, Handler]] = {
    "annotation_add":       (_undo_annotation_add,        _redo_annotation_add),
    "annotation_delete":    (_undo_annotation_delete,     _redo_annotation_delete),
    "annotation_merge_add": (_undo_annotation_merge_add,  _redo_annotation_merge_add),
    "code_add":             (_undo_code_add,              _redo_code_add),
    "code_delete":          (_undo_code_delete,           _redo_code_delete),
    "code_rename":          (_undo_code_rename,           _redo_code_rename),
    "code_recolour":        (_undo_code_recolour,         _redo_code_recolour),
    "code_change_group":    (_undo_code_change_group,     _redo_code_change_group),
    "code_reorder":         (_undo_code_reorder,          _redo_code_reorder),
    "group_rename":         (_undo_group_rename,          _redo_group_rename),
    "flag_toggle":          (_undo_flag_toggle,           _redo_flag_toggle),
    "codebook_import":      (_undo_codebook_import,       _redo_codebook_import),
}
