"""Guard functions for codebook tree shape.

Called from model-layer write paths to fail fast with clear messages.
The schema also enforces (kind IN ('code','folder')) via CHECK; these
guards add the relational rules the schema can't express.
"""

import sqlite3


class InvariantError(ValueError):
    """Raised when a write would violate a codebook tree invariant."""


def assert_parent_is_folder_or_root(
    conn: sqlite3.Connection, parent_id: str | None
) -> None:
    """Allow None (root) or a row with kind='folder'. Reject anything else."""
    if parent_id is None:
        return
    row = conn.execute(
        "SELECT kind FROM codebook_code WHERE id = ? AND deleted_at IS NULL",
        (parent_id,),
    ).fetchone()
    if row is None:
        raise InvariantError(f"parent_id {parent_id!r} does not exist")
    if row[0] != "folder":
        raise InvariantError("parent must be a folder")


def assert_folder_stays_at_root(
    conn: sqlite3.Connection, code_id: str, new_parent_id: str | None
) -> None:
    """A folder's parent_id is always NULL (depth-1 cap)."""
    row = conn.execute(
        "SELECT kind FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    if row and row[0] == "folder" and new_parent_id is not None:
        raise InvariantError("folders cannot be nested")
