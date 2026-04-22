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
    sql = "SELECT * FROM annotation WHERE source_id = ? AND deleted_at IS NULL"
    params: tuple = (source_id,)
    if coder_id is not None:
        sql += " AND coder_id = ?"
        params += (coder_id,)
    sql += " ORDER BY start_offset"
    return conn.execute(sql, params).fetchall()


def get_annotations_for_code(
    conn: sqlite3.Connection,
    code_id: str,
    coder_id: str | None = None,
) -> list[sqlite3.Row]:
    """Return all non-deleted annotations for a code across all sources.

    Results include source.display_id and are ordered by
    source.sort_order then annotation.start_offset.
    """
    sql = (
        "SELECT a.*, s.display_id, s.sort_order "
        "FROM annotation a JOIN source s ON a.source_id = s.id "
        "WHERE a.code_id = ? AND a.deleted_at IS NULL"
    )
    params: tuple = (code_id,)
    if coder_id is not None:
        sql += " AND a.coder_id = ?"
        params += (coder_id,)
    sql += " ORDER BY s.sort_order, a.start_offset"
    return conn.execute(sql, params).fetchall()


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


def get_annotation_counts_by_source(conn: sqlite3.Connection, coder_id: str | None = None) -> dict[str, int]:
    """Return {source_id: count} of non-deleted annotations."""
    if coder_id is not None:
        rows = conn.execute(
            "SELECT source_id, COUNT(*) AS cnt FROM annotation "
            "WHERE deleted_at IS NULL AND coder_id = ? GROUP BY source_id",
            (coder_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT source_id, COUNT(*) AS cnt FROM annotation "
            "WHERE deleted_at IS NULL GROUP BY source_id",
        ).fetchall()
    return {r["source_id"]: r["cnt"] for r in rows}


def expand_annotation(
    conn: sqlite3.Connection,
    annotation_id: str,
    new_start: int,
    new_end: int,
    new_text: str,
) -> None:
    """Expand an annotation's offset range (for merging adjacent sentences)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE annotation SET start_offset = ?, end_offset = ?, selected_text = ?, updated_at = ? WHERE id = ?",
        (new_start, new_end, new_text, now, annotation_id),
    )
    conn.commit()


def compact_deleted(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM annotation WHERE deleted_at IS NOT NULL")
    conn.commit()
    return cursor.rowcount


def add_annotation_merging(
    conn: sqlite3.Connection,
    source_id: str,
    coder_id: str,
    code_id: str,
    start_offset: int,
    end_offset: int,
    selected_text: str,
) -> tuple[str, list[str]]:
    """Create an annotation, merging any existing same-code annotations that
    overlap or touch the new range.

    Returns (new_annotation_id, replaced_ids). replaced_ids is the list of
    soft-deleted annotation ids merged into the new one; empty if no merge.

    Overlap-or-touch: existing.end_offset >= new.start_offset AND
    existing.start_offset <= new.end_offset. Only same code_id + coder_id +
    not-soft-deleted annotations are merged.

    For merges, selected_text is re-sliced from source.content_text for the
    full union range. Caller does not need to pass the union text.

    Atomic: all soft-deletes + insert run in one transaction; rollback on error.
    """
    overlapping = conn.execute(
        "SELECT id, start_offset, end_offset FROM annotation "
        "WHERE source_id = ? AND coder_id = ? AND code_id = ? "
        "AND deleted_at IS NULL "
        "AND end_offset >= ? AND start_offset <= ?",
        (source_id, coder_id, code_id, start_offset, end_offset),
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    new_id = uuid.uuid4().hex

    if not overlapping:
        conn.execute(
            "INSERT INTO annotation "
            "(id, source_id, coder_id, code_id, start_offset, end_offset, "
            "selected_text, memo, w3c_selector_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
            (new_id, source_id, coder_id, code_id, start_offset, end_offset,
             selected_text, now, now),
        )
        conn.commit()
        return new_id, []

    union_start = min(start_offset, *(r["start_offset"] for r in overlapping))
    union_end = max(end_offset, *(r["end_offset"] for r in overlapping))

    source_row = conn.execute(
        "SELECT content_text FROM source_content WHERE source_id = ?", (source_id,)
    ).fetchone()
    if source_row is None:
        raise ValueError(f"source {source_id} not found")
    merged_text = source_row["content_text"][union_start:union_end]

    replaced_ids = [r["id"] for r in overlapping]
    try:
        for rid in replaced_ids:
            conn.execute(
                "UPDATE annotation SET deleted_at = ? WHERE id = ?",
                (now, rid),
            )
        conn.execute(
            "INSERT INTO annotation "
            "(id, source_id, coder_id, code_id, start_offset, end_offset, "
            "selected_text, memo, w3c_selector_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
            (new_id, source_id, coder_id, code_id, union_start, union_end,
             merged_text, now, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return new_id, replaced_ids


def reverse_merge_add(
    conn: sqlite3.Connection,
    merged_id: str,
    replaced_ids: list[str],
) -> None:
    """Atomically reverse a merge-add: soft-delete the merged row and
    undelete each replaced original, in a single transaction.

    Used by the /api/code/undo route. The per-call delete_annotation /
    undelete_annotation helpers each commit independently, which would
    leave the DB in a partially-undone state if an error occurred
    mid-sequence. This function commits once.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "UPDATE annotation SET deleted_at = ? WHERE id = ?",
            (now, merged_id),
        )
        for rid in replaced_ids:
            conn.execute(
                "UPDATE annotation SET deleted_at = NULL WHERE id = ?",
                (rid,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def replay_merge_add(
    conn: sqlite3.Connection,
    merged_id: str,
    replaced_ids: list[str],
) -> None:
    """Atomically replay a previously-undone merge-add: undelete the merged
    row and soft-delete each original again, in a single transaction.

    Used by the /api/code/redo route. See reverse_merge_add for the
    atomicity rationale.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "UPDATE annotation SET deleted_at = NULL WHERE id = ?",
            (merged_id,),
        )
        for rid in replaced_ids:
            conn.execute(
                "UPDATE annotation SET deleted_at = ? WHERE id = ?",
                (now, rid),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
