"""Tests for the assignment model."""

from ace.db.connection import create_project
from ace.models.assignment import (
    add_assignment,
    get_assignments_for_coder,
    set_flagged,
)
from ace.models.project import list_coders
from ace.models.source import add_source


def _setup(conn):
    s1 = add_source(conn, "S001", "First source text.", "row")
    coders = list_coders(conn)
    coder_id = coders[0]["id"]
    return s1, coder_id


def test_add_assignment_defaults_flagged_to_zero(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, coder_id = _setup(conn)
    add_assignment(conn, s1, coder_id)
    rows = get_assignments_for_coder(conn, coder_id)
    assert len(rows) == 1
    assert rows[0]["flagged"] == 0


def test_set_flagged_writes_flagged_and_updated_at(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, coder_id = _setup(conn)
    add_assignment(conn, s1, coder_id)

    initial = get_assignments_for_coder(conn, coder_id)[0]
    initial_updated_at = initial["updated_at"]

    set_flagged(conn, s1, coder_id, True)
    rows = get_assignments_for_coder(conn, coder_id)
    assert rows[0]["flagged"] == 1
    # updated_at should have been bumped
    assert rows[0]["updated_at"] >= initial_updated_at

    set_flagged(conn, s1, coder_id, False)
    rows = get_assignments_for_coder(conn, coder_id)
    assert rows[0]["flagged"] == 0


def test_set_flagged_only_affects_matching_row(tmp_db):
    conn = create_project(tmp_db, "Test")
    s1, coder_id = _setup(conn)
    s2 = add_source(conn, "S002", "Second source text.", "row")
    add_assignment(conn, s1, coder_id)
    add_assignment(conn, s2, coder_id)

    set_flagged(conn, s1, coder_id, True)
    rows = {r["source_id"]: r["flagged"] for r in get_assignments_for_coder(conn, coder_id)}
    assert rows[s1] == 1
    assert rows[s2] == 0
