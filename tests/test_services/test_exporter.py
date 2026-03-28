"""Tests for annotation export with merge logic."""

import csv
import uuid

from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.annotation import add_annotation
from ace.services.exporter import export_annotations_csv, merge_adjacent_annotations


def test_export_annotations_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "export-test")

    # 1 source with metadata
    source_id = add_source(
        conn,
        display_id="P001",
        content_text="The quick brown fox jumps over the lazy dog.",
        source_type="row",
        metadata={"age": 22},
    )

    # 1 code
    code_id = add_code(conn, name="Theme-A", colour="#FF0000")

    # 1 coder (manual insert)
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, "Alice"))
    conn.commit()

    # 1 annotation
    add_annotation(
        conn,
        source_id=source_id,
        coder_id=coder_id,
        code_id=code_id,
        start_offset=0,
        end_offset=9,
        selected_text="The quick",
        memo="interesting phrase",
    )

    output_csv = tmp_path / "export.csv"
    row_count = export_annotations_csv(conn, output_csv)
    assert row_count == 1

    with open(output_csv, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row["source_id"] == source_id
    assert row["display_id"] == "P001"
    assert row["coder_name"] == "Alice"
    assert row["code_name"] == "Theme-A"
    assert row["selected_text"] == "The quick"
    assert row["start_offset"] == "0"
    assert row["end_offset"] == "9"
    assert row["memo"] == "interesting phrase"
    assert row["age"] == "22"

    conn.close()


def test_merge_no_annotations():
    assert merge_adjacent_annotations([]) == []


def test_merge_single_annotation_unchanged():
    anns = [{"code_id": "c1", "start_offset": 0, "end_offset": 10, "selected_text": "Hello."}]
    result = merge_adjacent_annotations(anns)
    assert len(result) == 1
    assert result[0]["start_offset"] == 0
    assert result[0]["end_offset"] == 10


def test_merge_adjacent_same_code():
    anns = [
        {"code_id": "c1", "start_offset": 0, "end_offset": 10, "selected_text": "First."},
        {"code_id": "c1", "start_offset": 11, "end_offset": 22, "selected_text": "Second."},
    ]
    result = merge_adjacent_annotations(anns)
    assert len(result) == 1
    assert result[0]["start_offset"] == 0
    assert result[0]["end_offset"] == 22
    assert result[0]["selected_text"] == "First. Second."


def test_merge_adjacent_different_code_not_merged():
    anns = [
        {"code_id": "c1", "start_offset": 0, "end_offset": 10, "selected_text": "First."},
        {"code_id": "c2", "start_offset": 11, "end_offset": 22, "selected_text": "Second."},
    ]
    result = merge_adjacent_annotations(anns)
    assert len(result) == 2


def test_merge_non_adjacent_same_code_not_merged():
    anns = [
        {"code_id": "c1", "start_offset": 0, "end_offset": 10, "selected_text": "First."},
        {"code_id": "c1", "start_offset": 50, "end_offset": 60, "selected_text": "Third."},
    ]
    result = merge_adjacent_annotations(anns)
    assert len(result) == 2


def test_merge_three_adjacent():
    anns = [
        {"code_id": "c1", "start_offset": 0, "end_offset": 6, "selected_text": "One."},
        {"code_id": "c1", "start_offset": 7, "end_offset": 13, "selected_text": "Two."},
        {"code_id": "c1", "start_offset": 14, "end_offset": 22, "selected_text": "Three."},
    ]
    result = merge_adjacent_annotations(anns)
    assert len(result) == 1
    assert result[0]["start_offset"] == 0
    assert result[0]["end_offset"] == 22
    assert result[0]["selected_text"] == "One. Two. Three."
