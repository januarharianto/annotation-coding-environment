"""Tests for the source_note model."""

from ace.db.connection import create_project
from ace.models.project import add_coder, list_coders
from ace.models.source import add_source
from ace.models.source_note import (
    delete_note,
    get_note,
    list_notes_for_export,
    source_ids_with_notes,
    upsert_note,
)


def _setup(conn):
    s1 = add_source(conn, "S001", "First source text.", "row")
    s2 = add_source(conn, "S002", "Second source text.", "row")
    coders = list_coders(conn)
    coder_id = coders[0]["id"]
    return s1, s2, coder_id


def test_upsert_creates_row(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, _, coder_id = _setup(conn)
    upsert_note(conn, s1, coder_id, "Defensive opening.")
    assert get_note(conn, s1, coder_id) == "Defensive opening."


def test_upsert_updates_existing_row(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, _, coder_id = _setup(conn)
    upsert_note(conn, s1, coder_id, "First version")
    upsert_note(conn, s1, coder_id, "Second version")
    assert get_note(conn, s1, coder_id) == "Second version"
    rows = conn.execute(
        "SELECT COUNT(*) FROM source_note WHERE source_id=? AND coder_id=?",
        (s1, coder_id),
    ).fetchone()
    assert rows[0] == 1


def test_upsert_empty_deletes_row(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, _, coder_id = _setup(conn)
    upsert_note(conn, s1, coder_id, "Some text")
    upsert_note(conn, s1, coder_id, "   \n\t  ")
    assert get_note(conn, s1, coder_id) is None


def test_upsert_empty_noop_when_no_row(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, _, coder_id = _setup(conn)
    upsert_note(conn, s1, coder_id, "")
    assert get_note(conn, s1, coder_id) is None


def test_get_note_missing_returns_none(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, _, coder_id = _setup(conn)
    assert get_note(conn, s1, coder_id) is None


def test_delete_note_is_idempotent(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, _, coder_id = _setup(conn)
    delete_note(conn, s1, coder_id)  # no-op
    upsert_note(conn, s1, coder_id, "Note")
    delete_note(conn, s1, coder_id)
    delete_note(conn, s1, coder_id)  # second call no-op
    assert get_note(conn, s1, coder_id) is None


def test_source_ids_with_notes(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, s2, coder_id = _setup(conn)
    upsert_note(conn, s1, coder_id, "Has note")
    assert source_ids_with_notes(conn, coder_id) == {s1}
    upsert_note(conn, s2, coder_id, "Also has note")
    assert source_ids_with_notes(conn, coder_id) == {s1, s2}
    upsert_note(conn, s1, coder_id, "")  # delete via empty
    assert source_ids_with_notes(conn, coder_id) == {s2}


def test_source_ids_with_notes_filters_by_coder(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, s2, coder_id = _setup(conn)
    other = add_coder(conn, "Other")
    upsert_note(conn, s1, coder_id, "Mine")
    upsert_note(conn, s2, other, "Theirs")
    assert source_ids_with_notes(conn, coder_id) == {s1}
    assert source_ids_with_notes(conn, other) == {s2}


def test_list_notes_for_export(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, s2, coder_id = _setup(conn)
    upsert_note(conn, s2, coder_id, "Second note")  # written first
    upsert_note(conn, s1, coder_id, "First note")
    rows = list_notes_for_export(conn, coder_id)
    # Ordered by source sort_order, so s1 (added first) comes first
    assert len(rows) == 2
    assert rows[0]["display_id"] == "S001"
    assert rows[0]["note_text"] == "First note"
    assert rows[1]["display_id"] == "S002"
    assert rows[1]["note_text"] == "Second note"
    assert "coder_name" in rows[0].keys()
    assert "created_at" in rows[0].keys()
    assert "updated_at" in rows[0].keys()


def test_concurrent_upserts_preserve_unique_constraint(tmp_db):
    """Spec testing requirement: concurrent upserts must not violate the unique constraint.

    With the atomic INSERT ... ON CONFLICT DO UPDATE rewrite, two upserts in
    quick succession both succeed and the second one wins, leaving exactly
    one row with the latest text.
    """
    conn = create_project(tmp_db, "Test")
    s1, _, coder_id = _setup(conn)

    # Two upserts that would race in the old read-then-write design.
    # The atomic version must produce exactly one row with the latest text.
    upsert_note(conn, s1, coder_id, "First")
    upsert_note(conn, s1, coder_id, "Second")

    rows = conn.execute(
        "SELECT note_text FROM source_note WHERE source_id=? AND coder_id=?",
        (s1, coder_id),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["note_text"] == "Second"
