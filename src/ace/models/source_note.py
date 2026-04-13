"""CRUD operations for the source_note table.

One note per (source, coder), enforced by a UNIQUE constraint in schema.py.
Empty/whitespace-only text is treated as "no note" and deletes any existing row.
"""

import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_note(
    conn: sqlite3.Connection,
    source_id: str,
    coder_id: str,
    note_text: str,
) -> None:
    """Insert or update the note for (source_id, coder_id).

    Atomic via INSERT ... ON CONFLICT DO UPDATE. If note_text is empty
    after trimming, deletes any existing row instead.
    """
    if not note_text.strip():
        delete_note(conn, source_id, coder_id)
        return

    now = _now()
    conn.execute(
        """
        INSERT INTO source_note (id, source_id, coder_id, note_text, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id, coder_id) DO UPDATE SET
            note_text = excluded.note_text,
            updated_at = excluded.updated_at
        """,
        (uuid.uuid4().hex, source_id, coder_id, note_text, now, now),
    )
    conn.commit()


def get_note(
    conn: sqlite3.Connection,
    source_id: str,
    coder_id: str,
) -> str | None:
    """Return the note text or None."""
    row = conn.execute(
        "SELECT note_text FROM source_note WHERE source_id = ? AND coder_id = ?",
        (source_id, coder_id),
    ).fetchone()
    return row["note_text"] if row else None


def delete_note(
    conn: sqlite3.Connection,
    source_id: str,
    coder_id: str,
) -> None:
    """Remove the note row if present. Idempotent."""
    conn.execute(
        "DELETE FROM source_note WHERE source_id = ? AND coder_id = ?",
        (source_id, coder_id),
    )
    conn.commit()


def source_ids_with_notes(
    conn: sqlite3.Connection,
    coder_id: str,
) -> set[str]:
    """Return the set of source IDs that have a note for this coder."""
    rows = conn.execute(
        "SELECT source_id FROM source_note WHERE coder_id = ?",
        (coder_id,),
    ).fetchall()
    return {row["source_id"] for row in rows}


def list_notes_for_export(
    conn: sqlite3.Connection,
    coder_id: str,
) -> list[sqlite3.Row]:
    """Return notes joined with source + coder, ordered by source sort_order."""
    return conn.execute(
        """
        SELECT
            s.display_id,
            s.filename,
            c.name      AS coder_name,
            n.note_text,
            n.created_at,
            n.updated_at
        FROM source_note n
        JOIN source s ON s.id = n.source_id
        JOIN coder  c ON c.id = n.coder_id
        WHERE n.coder_id = ?
        ORDER BY s.sort_order
        """,
        (coder_id,),
    ).fetchall()
