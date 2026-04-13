"""Tests for the source notes CSV exporter."""

import csv

from ace.db.connection import create_project
from ace.models.project import list_coders
from ace.models.source import add_source
from ace.models.source_note import upsert_note
from ace.services.notes_exporter import export_notes_csv


def test_export_notes_writes_header_and_rows(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    coder_id = list_coders(conn)[0]["id"]
    s1 = add_source(conn, "S001", "Text one.", "row")
    s2 = add_source(conn, "S002", "Text two.", "file", filename="doc.txt")
    upsert_note(conn, s1, coder_id, "First note")
    upsert_note(conn, s2, coder_id, "Second note")

    out = tmp_path / "notes.csv"
    count = export_notes_csv(conn, coder_id, out)
    assert count == 2

    with open(out) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == [
        "source_display_id",
        "source_filename",
        "coder_name",
        "note_text",
        "created_at",
        "updated_at",
    ]
    assert rows[0]["source_display_id"] == "S001"
    assert rows[0]["source_filename"] == ""  # NULL filename → empty string
    assert rows[0]["note_text"] == "First note"
    assert rows[1]["source_display_id"] == "S002"
    assert rows[1]["source_filename"] == "doc.txt"
    assert rows[1]["note_text"] == "Second note"


def test_export_notes_header_only_when_empty(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    coder_id = list_coders(conn)[0]["id"]
    add_source(conn, "S001", "Text.", "row")

    out = tmp_path / "empty.csv"
    count = export_notes_csv(conn, coder_id, out)
    assert count == 0

    with open(out) as f:
        lines = f.readlines()
    assert len(lines) == 1  # header only
    assert "source_display_id" in lines[0]


def test_export_notes_filters_by_coder(tmp_db, tmp_path):
    from ace.models.project import add_coder

    conn = create_project(tmp_db, "Test")
    me = list_coders(conn)[0]["id"]
    other = add_coder(conn, "Other")
    s1 = add_source(conn, "S001", "Text.", "row")
    upsert_note(conn, s1, me, "Mine")
    upsert_note(conn, s1, other, "Theirs")

    out = tmp_path / "mine.csv"
    count = export_notes_csv(conn, me, out)
    assert count == 1
    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["note_text"] == "Mine"
