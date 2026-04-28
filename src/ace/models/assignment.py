"""CRUD operations for assignment table."""

import sqlite3
import uuid
from datetime import datetime, timezone


def add_assignment(conn: sqlite3.Connection, source_id: str, coder_id: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    assignment_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO assignment (id, source_id, coder_id, flagged, assigned_at, updated_at) "
        "VALUES (?, ?, ?, 0, ?, ?)",
        (assignment_id, source_id, coder_id, now, now),
    )
    conn.commit()
    return assignment_id


def set_flagged(
    conn: sqlite3.Connection, source_id: str, coder_id: str, flagged: bool
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE assignment SET flagged = ?, updated_at = ? "
        "WHERE source_id = ? AND coder_id = ?",
        (1 if flagged else 0, now, source_id, coder_id),
    )
    conn.commit()


def get_assignments_for_coder(
    conn: sqlite3.Connection, coder_id: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT a.*, s.display_id FROM assignment a "
        "JOIN source s ON a.source_id = s.id "
        "WHERE a.coder_id = ? ORDER BY s.sort_order",
        (coder_id,),
    ).fetchall()
