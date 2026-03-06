"""CRUD operations for annotation table."""

import sqlite3
import uuid
from datetime import datetime, timezone


def add_annotation(
    conn: sqlite3.Connection,
    source_id: str,
    coder_id: str,
    code_id: str,
    start_offset: int,
    end_offset: int,
    selected_text: str,
    memo: str | None = None,
    w3c_selector_json: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    annotation_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO annotation "
        "(id, source_id, coder_id, code_id, start_offset, end_offset, selected_text, memo, w3c_selector_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (annotation_id, source_id, coder_id, code_id, start_offset, end_offset, selected_text, memo, w3c_selector_json, now, now),
    )
    conn.commit()
    return annotation_id


def get_annotations_for_source(
    conn: sqlite3.Connection,
    source_id: str,
    coder_id: str | None = None,
) -> list[sqlite3.Row]:
    if coder_id is not None:
        return conn.execute(
            "SELECT * FROM annotation WHERE source_id = ? AND coder_id = ? AND deleted_at IS NULL ORDER BY start_offset",
            (source_id, coder_id),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM annotation WHERE source_id = ? AND deleted_at IS NULL ORDER BY start_offset",
        (source_id,),
    ).fetchall()


def list_annotations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM annotation WHERE deleted_at IS NULL"
    ).fetchall()


def delete_annotation(conn: sqlite3.Connection, annotation_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE annotation SET deleted_at = ? WHERE id = ?",
        (now, annotation_id),
    )
    conn.commit()


def undelete_annotation(conn: sqlite3.Connection, annotation_id: str) -> None:
    conn.execute(
        "UPDATE annotation SET deleted_at = NULL WHERE id = ?",
        (annotation_id,),
    )
    conn.commit()


def compact_deleted(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM annotation WHERE deleted_at IS NOT NULL")
    conn.commit()
    return cursor.rowcount
