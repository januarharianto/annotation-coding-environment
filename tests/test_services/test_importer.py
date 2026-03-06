import json

from ace.db.connection import create_project
from ace.models.source import list_sources, get_source_content
from ace.services.importer import import_csv, import_text_files


def test_import_csv_creates_sources(tmp_db, sample_csv):
    conn = create_project(tmp_db, "test")
    count = import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    assert count == 3
    sources = list_sources(conn)
    assert len(sources) == 3
    assert sources[0]["display_id"] == "P001"
    assert sources[0]["source_type"] == "row"
    conn.close()


def test_import_csv_stores_metadata(tmp_db, sample_csv):
    conn = create_project(tmp_db, "test")
    import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    sources = list_sources(conn)
    meta = json.loads(sources[0]["metadata_json"])
    assert meta["age"] == 22
    conn.close()


def test_import_csv_content_hash(tmp_db, sample_csv):
    conn = create_project(tmp_db, "test")
    import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    sources = list_sources(conn)
    content_row = get_source_content(conn, sources[0]["id"])
    content_hash = content_row["content_hash"]
    assert len(content_hash) == 64
    assert all(c in "0123456789abcdef" for c in content_hash)
    conn.close()


def test_import_csv_multi_column(tmp_path, tmp_db):
    csv_path = tmp_path / "multi.csv"
    csv_path.write_text(
        "id,question1,question2,group\n"
        "S1,Answer A,Answer X,control\n"
        "S2,Answer B,Answer Y,treatment\n"
    )
    conn = create_project(tmp_db, "test")
    count = import_csv(conn, csv_path, id_column="id", text_columns=["question1", "question2"])
    assert count == 4
    sources = list_sources(conn)
    assert len(sources) == 4
    # Check display_id format for multi-column
    display_ids = [s["display_id"] for s in sources]
    assert "S1_question1" in display_ids
    assert "S1_question2" in display_ids
    # Check source_column is set
    for s in sources:
        assert s["source_column"] in ("question1", "question2")
    conn.close()


def test_import_text_files(tmp_path, tmp_db):
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "file1.txt").write_text("Hello world")
    (folder / "file2.txt").write_text("Goodbye world")
    conn = create_project(tmp_db, "test")
    count = import_text_files(conn, folder)
    assert count == 2
    sources = list_sources(conn)
    assert len(sources) == 2
    display_ids = sorted(s["display_id"] for s in sources)
    assert display_ids == ["file1", "file2"]
    assert all(s["source_type"] == "file" for s in sources)
    conn.close()
