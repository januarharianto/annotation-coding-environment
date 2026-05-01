import re
import sqlite3

import pytest

from ace.db.connection import create_project
from ace.models.annotation import add_annotation, delete_annotation
from ace.models.assignment import add_assignment
from ace.models.codebook import (
    add_code,
    add_folder,
    compute_codebook_hash,
    delete_code,
    export_codebook_to_csv,
    import_codebook_from_csv,
    import_selected_codes,
    list_codes,
    move_code_to_parent,
    preview_codebook_csv,
    restore_code,
    update_code,
)
from ace.models.project import add_coder
from ace.models.source import add_source

def _filter_codes(rows):
    """Return only kind='code' rows from a list_codes() result."""
    return [r for r in rows if r["kind"] == "code"]


def _resolve_group_name(conn, code_id):
    """Look up the parent folder's name for a code, or None if at root."""
    row = conn.execute(
        """
        SELECT f.name
        FROM codebook_code c
        LEFT JOIN codebook_code f
               ON f.id = c.parent_id AND f.kind = 'folder'
        WHERE c.id = ?
        """,
        (code_id,),
    ).fetchone()
    return row[0] if row and row[0] else None


def test_add_code(tmp_db):
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Theme A", "#FF0000")
    assert isinstance(cid, str)
    assert len(cid) == 32
    row = conn.execute("SELECT * FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["name"] == "Theme A"
    assert row["colour"] == "#FF0000"


def test_add_duplicate_name_raises(tmp_db):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Theme A", "#FF0000")
    with pytest.raises(sqlite3.IntegrityError):
        add_code(conn, "Theme A", "#00FF00")


def test_update_code(tmp_db):
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Theme A", "#FF0000")
    update_code(conn, cid, name="Theme B", colour="#00FF00")
    row = conn.execute("SELECT * FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["name"] == "Theme B"
    assert row["colour"] == "#00FF00"


def test_delete_code_soft_deletes_row(tmp_db):
    """delete_code is now a soft-delete: row remains, deleted_at is set."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Theme A", "#FF0000")
    annotations, children = delete_code(conn, cid)

    # Returns a tuple (no annotations and no children for a leaf code)
    assert annotations == []
    assert children == []

    # Row still exists, but deleted_at is populated
    row = conn.execute("SELECT * FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row is not None
    assert row["deleted_at"] is not None

    # list_codes filters out soft-deleted entries
    assert list_codes(conn) == []


def test_delete_code_soft_deletes_code_and_annotations(tmp_db):
    """delete_code soft-deletes code and all its active annotations, returning their IDs."""
    conn = create_project(tmp_db, "Test")
    coder_id = add_coder(conn, "alice")
    src1 = add_source(conn, "src1", "hello world", "file", filename="src1.txt")
    src2 = add_source(conn, "src2", "test data", "file", filename="src2.txt")
    add_assignment(conn, src1, coder_id)
    add_assignment(conn, src2, coder_id)

    code_id = add_code(conn, "Frustration", "#FF0000")
    a1 = add_annotation(conn, src1, coder_id, code_id, 0, 5, "hello")
    a2 = add_annotation(conn, src2, coder_id, code_id, 0, 4, "test")

    annotations, children = delete_code(conn, code_id)

    assert sorted(annotations) == sorted([a1, a2])
    assert children == []

    # Code is soft-deleted (row remains, deleted_at set)
    row = conn.execute(
        "SELECT deleted_at FROM codebook_code WHERE id = ?", (code_id,)
    ).fetchone()
    assert row is not None
    assert row["deleted_at"] is not None

    # Both annotations are soft-deleted
    for ann_id in (a1, a2):
        ann = conn.execute(
            "SELECT deleted_at FROM annotation WHERE id = ?", (ann_id,)
        ).fetchone()
        assert ann["deleted_at"] is not None

    # list_codes filters out soft-deleted
    assert list_codes(conn) == []


def test_delete_code_only_soft_deletes_active_annotations(tmp_db):
    """If an annotation is already soft-deleted, delete_code should NOT include it in returned IDs."""
    conn = create_project(tmp_db, "Test")
    coder_id = add_coder(conn, "alice")
    src1 = add_source(conn, "src1", "hello world", "file", filename="src1.txt")
    add_assignment(conn, src1, coder_id)

    code_id = add_code(conn, "Theme A", "#FF0000")
    a_active = add_annotation(conn, src1, coder_id, code_id, 0, 5, "hello")
    a_already_deleted = add_annotation(conn, src1, coder_id, code_id, 6, 11, "world")
    delete_annotation(conn, a_already_deleted)

    annotations, children = delete_code(conn, code_id)

    # Only the previously-active annotation is in the returned list
    assert annotations == [a_active]
    assert children == []


def test_restore_code_clears_deleted_at(tmp_db):
    """restore_code clears deleted_at on the code and the listed annotations atomically."""
    conn = create_project(tmp_db, "Test")
    coder_id = add_coder(conn, "alice")
    src1 = add_source(conn, "src1", "hello world", "file", filename="src1.txt")
    add_assignment(conn, src1, coder_id)

    code_id = add_code(conn, "Joy", "#00FF00")
    a1 = add_annotation(conn, src1, coder_id, code_id, 0, 5, "hello")
    annotations, _children = delete_code(conn, code_id)
    assert annotations == [a1]

    restore_code(conn, code_id, annotations)

    rows = list_codes(conn)
    assert len(rows) == 1
    assert rows[0]["id"] == code_id

    ann = conn.execute(
        "SELECT deleted_at FROM annotation WHERE id = ?", (a1,)
    ).fetchone()
    assert ann["deleted_at"] is None


def test_restore_code_with_no_annotations(tmp_db):
    """restore_code works when the affected list is empty (code with no annotations)."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Lonely", "#123456")
    annotations, _children = delete_code(conn, cid)
    assert annotations == []

    restore_code(conn, cid, annotations)
    codes = list_codes(conn)
    assert len(codes) == 1
    assert codes[0]["id"] == cid


def test_codebook_hash_deterministic(tmp_db):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Theme A", "#FF0000")
    add_code(conn, "Theme B", "#00FF00")
    h1 = compute_codebook_hash(conn)
    h2 = compute_codebook_hash(conn)
    assert h1 == h2
    assert len(h1) == 64


def test_import_codebook_from_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text(
        "name,colour\n"
        "Theme A,#FF0000\n"
        "Theme B,#00FF00\n"
    )
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = _filter_codes(list_codes(conn))
    assert len(codes) == 2
    assert codes[0]["name"] == "Theme A"
    assert codes[1]["name"] == "Theme B"


def test_import_csv_optional_colour(tmp_db, tmp_path):
    """Import CSV with no colour column — colours auto-assigned."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,description\nAlpha,First\nBeta,Second\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = _filter_codes(list_codes(conn))
    assert all(re.match(r"^#[0-9A-F]{6}$", c["colour"]) for c in codes)


def test_import_csv_skips_empty_names(tmp_db, tmp_path):
    """Rows with empty name are skipped."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\n,#00FF00\n  ,#0000FF\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 1


def test_import_csv_dedup_names(tmp_db, tmp_path):
    """Duplicate names in CSV: keep first, skip subsequent."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\nAlpha,#00FF00\nBeta,#0000FF\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = _filter_codes(list_codes(conn))
    assert codes[0]["name"] == "Alpha"  # first occurrence kept
    assert codes[1]["name"] == "Beta"


def test_import_csv_colour_column_ignored_auto_assigns(tmp_db, tmp_path):
    """Colour column in CSV is ignored — colours always auto-assigned from palette."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,red\nBeta,#00FF00\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = _filter_codes(list_codes(conn))
    assert re.match(r"^#[0-9A-F]{6}$", codes[0]["colour"])  # auto-assigned
    assert re.match(r"^#[0-9A-F]{6}$", codes[1]["colour"])  # also auto-assigned


def test_import_csv_atomic_rollback(tmp_db, tmp_path):
    """Import is atomic — raises ValueError if no name column."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("colour\n#FF0000\n#00FF00\n")
    with pytest.raises(ValueError, match="name"):
        import_codebook_from_csv(conn, csv_path)
    assert list_codes(conn) == []


def test_import_csv_utf8_bom(tmp_db, tmp_path):
    """Handle UTF-8 BOM from Excel exports."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_bytes(b"\xef\xbb\xbfname,colour\nAlpha,#FF0000\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 1
    codes = _filter_codes(list_codes(conn))
    assert codes[0]["name"] == "Alpha"


def test_preview_marks_existing_codes(tmp_db, tmp_path):
    """Preview marks codes that already exist in the project."""
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")

    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name\nAlpha\nBeta\n")

    preview = preview_codebook_csv(conn, csv_path)
    assert len(preview) == 2
    assert preview[0]["name"] == "Alpha"
    assert preview[0]["exists"] is True
    assert preview[1]["name"] == "Beta"
    assert preview[1]["exists"] is False


def test_preview_empty_csv(tmp_db, tmp_path):
    """Preview of CSV with only header returns empty list."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\n")

    preview = preview_codebook_csv(conn, csv_path)
    assert preview == []


def test_preview_no_existing_codes(tmp_db, tmp_path):
    """Preview with no codes in DB marks all as not existing."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour\nAlpha,#FF0000\nBeta,#00FF00\n")

    preview = preview_codebook_csv(conn, csv_path)
    assert all(not p["exists"] for p in preview)


def test_export_codebook_to_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")
    add_code(conn, "Beta", "#00FF00")
    out = tmp_path / "out.csv"
    count = export_codebook_to_csv(conn, out)
    assert count == 2
    content = out.read_text()
    assert "name,group" in content
    assert "Alpha," in content
    assert "Beta," in content


def test_import_selected_codes(tmp_db):
    """Import a list of codes into an empty project."""
    conn = create_project(tmp_db, "Test")
    codes_to_import = [
        {"name": "Alpha", "colour": "#FF0000"},
        {"name": "Beta", "colour": "#00FF00"},
    ]
    inserted = import_selected_codes(conn, codes_to_import)
    assert len(inserted) == 2
    assert all(isinstance(cid, str) for cid in inserted)
    codes = _filter_codes(list_codes(conn))
    assert len(codes) == 2
    assert codes[0]["name"] == "Alpha"
    assert codes[1]["name"] == "Beta"
    # Inserted IDs match what's now in the DB
    assert {c["id"] for c in codes} == set(inserted)


def test_import_selected_appends_sort_order(tmp_db):
    """Imported codes get sort_order after existing max."""
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Existing", "#999999")  # sort_order = 1

    codes_to_import = [{"name": "New", "colour": "#FF0000"}]
    import_selected_codes(conn, codes_to_import)

    codes = _filter_codes(list_codes(conn))
    assert len(codes) == 2
    assert codes[0]["name"] == "Existing"
    assert codes[0]["sort_order"] == 1
    assert codes[1]["name"] == "New"
    assert codes[1]["sort_order"] == 2


def test_import_selected_skips_existing(tmp_db):
    """Codes whose name already exists in DB are skipped (safety net)."""
    conn = create_project(tmp_db, "Test")
    add_code(conn, "Alpha", "#FF0000")

    codes_to_import = [
        {"name": "Alpha", "colour": "#00FF00"},  # exists — skip
        {"name": "Beta", "colour": "#0000FF"},    # new — insert
    ]
    inserted = import_selected_codes(conn, codes_to_import)
    assert len(inserted) == 1
    codes = _filter_codes(list_codes(conn))
    assert len(codes) == 2
    assert codes[0]["colour"] == "#FF0000"  # original colour kept


def test_import_selected_empty_list(tmp_db):
    """Empty list returns [], no DB changes."""
    conn = create_project(tmp_db, "Test")
    inserted = import_selected_codes(conn, [])
    assert inserted == []
    assert list_codes(conn) == []


def test_add_code_with_parent(tmp_db):
    """add_code accepts optional parent_id pointing to a folder."""
    conn = create_project(tmp_db, "Test")
    fid = add_folder(conn, "Emotions")
    cid = add_code(conn, "Happy", "#FF0000", parent_id=fid)
    row = conn.execute("SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["parent_id"] == fid


def test_add_code_without_parent(tmp_db):
    """add_code without parent_id stores NULL."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000")
    row = conn.execute("SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["parent_id"] is None


def test_move_code_to_parent_sets_folder(tmp_db):
    """move_code_to_parent attaches a code under a folder."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000")
    fid = add_folder(conn, "Emotions")
    move_code_to_parent(conn, cid, fid)
    row = conn.execute("SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["parent_id"] == fid


def test_move_code_to_parent_clears_to_root(tmp_db):
    """move_code_to_parent(None) lifts a code back to root."""
    conn = create_project(tmp_db, "Test")
    fid = add_folder(conn, "Emotions")
    cid = add_code(conn, "Happy", "#FF0000", parent_id=fid)
    move_code_to_parent(conn, cid, None)
    row = conn.execute("SELECT parent_id FROM codebook_code WHERE id = ?", (cid,)).fetchone()
    assert row["parent_id"] is None


def test_codebook_hash_includes_parent(tmp_db):
    """Hash changes when a code's parent_id changes."""
    conn = create_project(tmp_db, "Test")
    cid = add_code(conn, "Happy", "#FF0000")
    fid = add_folder(conn, "Emotions")
    h1 = compute_codebook_hash(conn)
    move_code_to_parent(conn, cid, fid)
    h2 = compute_codebook_hash(conn)
    assert h1 != h2


def test_codebook_hash_excludes_sort_order(tmp_db):
    """Reorders should NOT change the hash (per amendments §3.5.7)."""
    from ace.models.codebook import reorder_codes
    conn = create_project(tmp_db, "Test")
    a = add_code(conn, "Alpha", "#FF0000")
    b = add_code(conn, "Beta", "#00FF00")
    h1 = compute_codebook_hash(conn)
    # Swap order — should not affect hash.
    reorder_codes(conn, [b, a])
    h2 = compute_codebook_hash(conn)
    assert h1 == h2


def test_parse_csv_with_group_column(tmp_db, tmp_path):
    """CSV with name + group columns creates parent folders and links codes."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nSad,Emotions\nIdentity,Themes\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 3
    codes = _filter_codes(list_codes(conn))
    by_name = {c["name"]: c for c in codes}
    assert _resolve_group_name(conn, by_name["Happy"]["id"]) == "Emotions"
    assert _resolve_group_name(conn, by_name["Sad"]["id"]) == "Emotions"
    assert _resolve_group_name(conn, by_name["Identity"]["id"]) == "Themes"


def test_parse_csv_strips_group_whitespace(tmp_db, tmp_path):
    """Group names have whitespace stripped, casing preserved."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,  Emotions  \nSad,ICR Codes\n")
    import_codebook_from_csv(conn, csv_path)
    codes = _filter_codes(list_codes(conn))
    by_name = {c["name"]: c for c in codes}
    assert _resolve_group_name(conn, by_name["Happy"]["id"]) == "Emotions"
    assert _resolve_group_name(conn, by_name["Sad"]["id"]) == "ICR Codes"


def test_parse_csv_empty_group_is_null(tmp_db, tmp_path):
    """Empty group value in CSV leaves the code at root (no parent folder)."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nUngrouped,\n")
    import_codebook_from_csv(conn, csv_path)
    codes = _filter_codes(list_codes(conn))
    by_name = {c["name"]: c for c in codes}
    assert _resolve_group_name(conn, by_name["Happy"]["id"]) == "Emotions"
    assert _resolve_group_name(conn, by_name["Ungrouped"]["id"]) is None
    assert by_name["Ungrouped"]["parent_id"] is None


def test_parse_csv_colour_column_ignored(tmp_db, tmp_path):
    """Old CSV with colour column — colour ignored, auto-assigned, group used."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,colour,group\nHappy,#FF0000,Emotions\n")
    import_codebook_from_csv(conn, csv_path)
    codes = _filter_codes(list_codes(conn))
    assert _resolve_group_name(conn, codes[0]["id"]) == "Emotions"


def test_parse_csv_duplicate_names_different_groups(tmp_db, tmp_path):
    """Same code name in different groups — first kept, second skipped."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nHappy,Wellbeing\nSad,Emotions\n")
    count = import_codebook_from_csv(conn, csv_path)
    assert count == 2
    codes = _filter_codes(list_codes(conn))
    assert len(codes) == 2
    by_name = {c["name"]: c for c in codes}
    assert "Happy" in by_name
    assert _resolve_group_name(conn, by_name["Happy"]["id"]) == "Emotions"


def test_parse_csv_reuses_existing_folder(tmp_db, tmp_path):
    """If a folder by the same name already exists, the import reuses it."""
    conn = create_project(tmp_db, "Test")
    fid = add_folder(conn, "Emotions")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nSad,Emotions\n")
    import_codebook_from_csv(conn, csv_path)
    folders = conn.execute(
        "SELECT id, name FROM codebook_code "
        "WHERE kind='folder' AND deleted_at IS NULL"
    ).fetchall()
    assert len(folders) == 1
    assert folders[0]["id"] == fid


def test_preview_includes_group_name(tmp_db, tmp_path):
    """preview_codebook_csv includes group_name in output."""
    conn = create_project(tmp_db, "Test")
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("name,group\nHappy,Emotions\nSad,Emotions\n")
    preview = preview_codebook_csv(conn, csv_path)
    assert preview[0]["group_name"] == "Emotions"
    assert preview[1]["group_name"] == "Emotions"


def test_import_selected_with_group(tmp_db):
    """import_selected_codes converts group_name into a parent folder."""
    conn = create_project(tmp_db, "Test")
    codes = [
        {"name": "Happy", "colour": "#FF0000", "group_name": "Emotions"},
        {"name": "Identity", "colour": "#00FF00", "group_name": "Themes"},
    ]
    inserted = import_selected_codes(conn, codes)
    assert _resolve_group_name(conn, inserted[0]) == "Emotions"
    assert _resolve_group_name(conn, inserted[1]) == "Themes"


def test_export_csv_includes_group(tmp_db, tmp_path):
    """export_codebook_to_csv writes name,group columns (no colour)."""
    conn = create_project(tmp_db, "Test")
    fid = add_folder(conn, "Emotions")
    add_code(conn, "Happy", "#FF0000", parent_id=fid)
    add_code(conn, "Ungrouped", "#00FF00")
    out = tmp_path / "out.csv"
    export_codebook_to_csv(conn, out)
    content = out.read_text()
    assert "name,group" in content
    assert "Happy,Emotions" in content
    assert "Ungrouped," in content
    assert "colour" not in content


def test_round_trip_export_then_import_is_idempotent(tmp_path):
    """Round-trip test: export → wipe → import preserves the tree shape."""
    db = tmp_path / "rt.ace"
    conn = create_project(db, "Test")
    fid = add_folder(conn, "Themes")
    add_code(conn, "Identity", "#D55E00", parent_id=fid)
    add_code(conn, "Trust", "#0072B2")  # root

    csv_path = tmp_path / "exported.csv"
    export_codebook_to_csv(conn, csv_path)

    # Wipe the codebook. parent_id has ON DELETE SET NULL so the bulk DELETE
    # is fine; nothing else references codebook_code in this test.
    conn.execute("DELETE FROM codebook_code")
    conn.commit()

    import_codebook_from_csv(conn, csv_path)

    folders = conn.execute(
        "SELECT name FROM codebook_code "
        "WHERE kind='folder' AND deleted_at IS NULL"
    ).fetchall()
    assert [r["name"] for r in folders] == ["Themes"]

    codes = _filter_codes(list_codes(conn))
    by_name = {c["name"]: c for c in codes}
    assert set(by_name) == {"Identity", "Trust"}
    assert _resolve_group_name(conn, by_name["Identity"]["id"]) == "Themes"
    assert _resolve_group_name(conn, by_name["Trust"]["id"]) is None
    conn.close()
