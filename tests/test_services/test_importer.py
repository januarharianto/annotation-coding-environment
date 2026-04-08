import json

import openpyxl

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


def test_import_csv_two_rows(tmp_path):
    """Import a 2-row CSV and verify count and display_ids."""
    csv_path = tmp_path / "two.csv"
    csv_path.write_text("id,text\nA1,hello\nA2,world\n")
    db_path = tmp_path / "two.ace"
    conn = create_project(db_path, "test")
    count = import_csv(conn, csv_path, id_column="id", text_columns=["text"])
    assert count == 2
    sources = list_sources(conn)
    assert [s["display_id"] for s in sources] == ["A1", "A2"]
    conn.close()


def test_import_csv_multi_text_columns(tmp_path):
    """Multi-text-column import adds _col suffix to display_ids."""
    csv_path = tmp_path / "multi_text.csv"
    csv_path.write_text("id,q1,q2\nR1,ans1,ans2\nR2,ans3,ans4\n")
    db_path = tmp_path / "multi_text.ace"
    conn = create_project(db_path, "test")
    count = import_csv(conn, csv_path, id_column="id", text_columns=["q1", "q2"])
    assert count == 4
    sources = list_sources(conn)
    display_ids = [s["display_id"] for s in sources]
    assert "R1_q1" in display_ids
    assert "R1_q2" in display_ids
    assert "R2_q1" in display_ids
    assert "R2_q2" in display_ids
    conn.close()


def test_import_xlsx(tmp_path):
    """Create an .xlsx with openpyxl and verify import."""
    xlsx_path = tmp_path / "data.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "response", "score"])
    ws.append(["X1", "Good stuff", 85])
    ws.append(["X2", "Needs work", 62])
    wb.save(xlsx_path)
    wb.close()

    db_path = tmp_path / "xlsx.ace"
    conn = create_project(db_path, "test")
    count = import_csv(conn, xlsx_path, id_column="id", text_columns=["response"])
    assert count == 2
    sources = list_sources(conn)
    assert sources[0]["display_id"] == "X1"
    assert sources[1]["display_id"] == "X2"
    meta = json.loads(sources[0]["metadata_json"])
    assert meta["score"] == 85
    conn.close()


def test_import_text_files_two(tmp_path):
    """Create 2 .txt files in tmp_path and verify import."""
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "alpha.txt").write_text("Alpha content")
    (folder / "beta.txt").write_text("Beta content")

    db_path = tmp_path / "txt.ace"
    conn = create_project(db_path, "test")
    count = import_text_files(conn, folder)
    assert count == 2
    sources = list_sources(conn)
    display_ids = sorted(s["display_id"] for s in sources)
    assert display_ids == ["alpha", "beta"]
    content = get_source_content(conn, sources[0]["id"])
    assert content["content_text"] in ("Alpha content", "Beta content")
    conn.close()


def test_import_text_files_md(tmp_path):
    """Markdown files are imported alongside .txt files."""
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "notes.md").write_text("# Markdown content")
    (folder / "readme.txt").write_text("Plain text")
    (folder / "data.csv").write_text("id,text\n1,ignore")  # should be skipped

    db_path = tmp_path / "mixed.ace"
    conn = create_project(db_path, "test")
    count = import_text_files(conn, folder)
    assert count == 2
    sources = list_sources(conn)
    display_ids = sorted(s["display_id"] for s in sources)
    assert display_ids == ["notes", "readme"]
    assert all(s["source_type"] == "file" for s in sources)
    conn.close()


def test_import_csv_latin1(tmp_path):
    """Write bytes with a latin-1 char and verify decoding fallback."""
    csv_path = tmp_path / "latin1.csv"
    # \xe9 is 'e' with acute accent in latin-1, invalid in utf-8
    csv_path.write_bytes(b"id,text\nL1,caf\xe9\n")

    db_path = tmp_path / "latin1.ace"
    conn = create_project(db_path, "test")
    count = import_csv(conn, csv_path, id_column="id", text_columns=["text"])
    assert count == 1
    sources = list_sources(conn)
    assert sources[0]["display_id"] == "L1"
    content = get_source_content(conn, sources[0]["id"])
    assert content["content_text"] == "caf\u00e9"
    conn.close()
