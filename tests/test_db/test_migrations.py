"""Tests for schema migrations."""

import sqlite3

import pytest

from ace.db.connection import create_project, open_project
from ace.db.migrations import _migrate_v6_to_v7, check_and_migrate
from ace.db.schema import ACE_APPLICATION_ID, SCHEMA_VERSION


def test_v1_to_v2_migration_adds_group_name(tmp_path):
    """Opening a v1 database migrates the codebook through to current schema.

    v1→v2 originally added group_name; v6→v7 dropped it again in favour of
    parent_id. After the full chain, the v1 row should land at root with
    parent_id IS NULL and kind='code'.
    """
    db_path = tmp_path / "v1.ace"

    # Create a v1 database manually (without group_name column)
    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA application_id = {ACE_APPLICATION_ID}")
    conn.execute("PRAGMA user_version = 1")
    conn.execute("""
        CREATE TABLE project (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            instructions TEXT, file_role TEXT NOT NULL, codebook_hash TEXT,
            assignment_seed TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE codebook_code (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            colour TEXT NOT NULL, sort_order INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE coder (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE)
    """)
    conn.execute("INSERT INTO coder VALUES ('c1', 'default')")
    conn.execute(
        "INSERT INTO project VALUES ('p1', 'Test', NULL, NULL, 'manager', NULL, NULL, '2025-01-01', '2025-01-01')"
    )
    conn.execute(
        "INSERT INTO codebook_code VALUES ('cc1', 'Alpha', '#FF0000', 1, '2025-01-01')"
    )
    conn.commit()
    conn.close()

    # Open with open_project — should trigger full migration chain
    conn = open_project(db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 2

    # group_name was added at v2 then dropped at v7; the row now lives at root.
    row = conn.execute(
        "SELECT kind, parent_id FROM codebook_code WHERE name = 'Alpha'"
    ).fetchone()
    assert row["kind"] == "code"
    assert row["parent_id"] is None
    conn.close()


def test_fresh_db_has_kind_and_parent_id_columns(tmp_path):
    """A newly created project has the v7 codebook columns (kind, parent_id)."""
    db_path = tmp_path / "fresh.ace"
    conn = create_project(db_path, "Test")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(codebook_code)")}
    assert "kind" in cols
    assert "parent_id" in cols
    assert "group_name" not in cols
    conn.close()


def test_v2_to_v3_migration_adds_deleted_at_to_codebook(tmp_path):
    """Opening a v2 database migrates the codebook through the full chain.

    v2→v3 originally added deleted_at; the v6→v7 step rewrites the unique-name
    index to (name, kind) NOCASE. After the full chain, the partial-unique-on-
    deleted_at behaviour still holds for active rows of the same kind.
    """
    db_path = tmp_path / "v2.ace"

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA application_id = {ACE_APPLICATION_ID}")
    conn.execute("PRAGMA user_version = 2")
    conn.execute("""
        CREATE TABLE project (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            instructions TEXT, file_role TEXT NOT NULL, codebook_hash TEXT,
            assignment_seed TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE codebook_code (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            colour TEXT NOT NULL, sort_order INTEGER NOT NULL,
            group_name TEXT, created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE coder (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE)
    """)
    conn.execute("INSERT INTO coder VALUES ('c1', 'default')")
    conn.execute(
        "INSERT INTO project VALUES ('p1', 'Test', NULL, NULL, 'manager', NULL, NULL, '2025-01-01', '2025-01-01')"
    )
    conn.execute(
        "INSERT INTO codebook_code VALUES ('cc1', 'Alpha', '#FF0000', 1, NULL, '2025-01-01')"
    )
    conn.commit()
    conn.close()

    conn = open_project(db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 3

    # deleted_at column exists, NULL for migrated rows
    row = conn.execute("SELECT deleted_at FROM codebook_code WHERE name = 'Alpha'").fetchone()
    assert row["deleted_at"] is None

    # Partial unique index allows reusing a soft-deleted name
    conn.execute(
        "UPDATE codebook_code SET deleted_at = '2025-01-02' WHERE id = 'cc1'"
    )
    conn.execute(
        "INSERT INTO codebook_code (id, name, colour, sort_order, kind, created_at, deleted_at)"
        " VALUES ('cc2', 'Alpha', '#00FF00', 2, 'code', '2025-01-02', NULL)"
    )
    conn.commit()
    # Two rows with name 'Alpha' but only one active — succeeds
    active = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE name = 'Alpha' AND deleted_at IS NULL"
    ).fetchone()[0]
    assert active == 1
    conn.close()


def test_v2_to_v3_partial_index_blocks_two_active_with_same_name(tmp_path):
    """After migration, two active codes cannot share a name."""
    db_path = tmp_path / "v2.ace"

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA application_id = {ACE_APPLICATION_ID}")
    conn.execute("PRAGMA user_version = 2")
    conn.execute("""
        CREATE TABLE codebook_code (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            colour TEXT NOT NULL, sort_order INTEGER NOT NULL,
            group_name TEXT, created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE TABLE coder (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
    conn.execute(
        "INSERT INTO codebook_code VALUES ('cc1', 'Alpha', '#FF0000', 1, NULL, '2025-01-01')"
    )
    conn.commit()
    conn.close()

    conn = open_project(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO codebook_code (id, name, colour, sort_order, kind, created_at, deleted_at)"
            " VALUES ('cc2', 'Alpha', '#00FF00', 2, 'code', '2025-01-02', NULL)"
        )
    conn.close()


def test_v3_to_v4_migration_replaces_status_with_flagged(tmp_path):
    """Opening a v3 database migrates it to v4: status column dropped, flagged column added.

    Only rows with status='flagged' become flagged=1; all others become flagged=0.
    """
    db_path = tmp_path / "v3.ace"

    conn = sqlite3.connect(str(db_path))
    conn.execute(f"PRAGMA application_id = {ACE_APPLICATION_ID}")
    conn.execute("PRAGMA user_version = 3")
    # v3 schema (codebook has deleted_at, assignment still has status)
    conn.executescript("""
        CREATE TABLE source (id TEXT PRIMARY KEY, display_id TEXT NOT NULL, source_type TEXT NOT NULL, source_column TEXT, filename TEXT, metadata_json TEXT, sort_order INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE coder (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE assignment (
            id          TEXT PRIMARY KEY,
            source_id   TEXT NOT NULL REFERENCES source(id),
            coder_id    TEXT NOT NULL REFERENCES coder(id),
            status      TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'in_progress', 'complete', 'flagged')),
            assigned_at TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            UNIQUE(source_id, coder_id)
        );
    """)
    conn.execute("INSERT INTO coder VALUES ('c1', 'alice')")
    for i, status in enumerate(['pending', 'in_progress', 'complete', 'flagged']):
        conn.execute(
            "INSERT INTO source VALUES (?, ?, 'file', NULL, ?, NULL, ?, '2025-01-01')",
            (f"s{i}", f"src{i}", f"src{i}.txt", i)
        )
        conn.execute(
            "INSERT INTO assignment VALUES (?, ?, 'c1', ?, '2025-01-01', '2025-01-01')",
            (f"a{i}", f"s{i}", status)
        )
    conn.commit()
    conn.close()

    conn = open_project(db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 4

    # status column gone; flagged column exists
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(assignment)")}
    assert "status" not in cols
    assert "flagged" in cols

    rows = conn.execute(
        "SELECT a.id, a.flagged FROM assignment a JOIN source s ON a.source_id = s.id ORDER BY s.sort_order"
    ).fetchall()
    assert [r["flagged"] for r in rows] == [0, 0, 0, 1]
    conn.close()


# ---------------------------------------------------------------------------
# v6 → v7 migration
# ---------------------------------------------------------------------------


def _build_v6_codebook(tmp_path):
    """Build a v6-schema DB with codes in a couple of named groups."""
    db = tmp_path / "v6.ace"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE codebook_code (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            colour      TEXT NOT NULL,
            sort_order  INTEGER NOT NULL,
            group_name  TEXT,
            chord       TEXT,
            created_at  TEXT NOT NULL,
            deleted_at  TEXT
        );
        INSERT INTO codebook_code VALUES
          ('c1', 'Identity',    '#D55E00', 1, 'Themes',  NULL, '2026-01-01', NULL),
          ('c2', 'Belonging',   '#56B4E9', 2, 'Themes',  NULL, '2026-01-01', NULL),
          ('c3', 'Negotiation', '#CC79A7', 3, 'Process', NULL, '2026-01-01', NULL),
          ('c4', 'Trust',       '#0072B2', 4, NULL,      NULL, '2026-01-01', NULL),
          ('c5', 'Stigma',      '#E69F00', 5, NULL,      'qa', '2026-01-01', NULL);
        CREATE UNIQUE INDEX idx_codebook_code_name_active
            ON codebook_code(name) WHERE deleted_at IS NULL;
        CREATE UNIQUE INDEX idx_codebook_chord
            ON codebook_code(chord) WHERE chord IS NOT NULL AND deleted_at IS NULL;
        PRAGMA user_version = 6;
    """)
    conn.commit()
    return conn


def test_v7_migration_adds_kind_and_parent_id_columns(tmp_path):
    conn = _build_v6_codebook(tmp_path)
    _migrate_v6_to_v7(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(codebook_code)").fetchall()}
    assert "kind" in cols
    assert "parent_id" in cols
    assert "group_name" not in cols


def test_v7_migration_creates_folder_for_each_distinct_group(tmp_path):
    conn = _build_v6_codebook(tmp_path)
    _migrate_v6_to_v7(conn)
    folders = conn.execute(
        "SELECT name FROM codebook_code WHERE kind = 'folder' ORDER BY name"
    ).fetchall()
    assert [r[0] for r in folders] == ["Process", "Themes"]


def test_v7_migration_links_codes_to_folders_via_parent_id(tmp_path):
    conn = _build_v6_codebook(tmp_path)
    _migrate_v6_to_v7(conn)
    themes_id = conn.execute(
        "SELECT id FROM codebook_code WHERE kind='folder' AND name='Themes'"
    ).fetchone()[0]
    children = conn.execute(
        "SELECT name FROM codebook_code WHERE parent_id=? ORDER BY name", (themes_id,)
    ).fetchall()
    assert [r[0] for r in children] == ["Belonging", "Identity"]


def test_v7_migration_keeps_ungrouped_codes_at_root(tmp_path):
    conn = _build_v6_codebook(tmp_path)
    _migrate_v6_to_v7(conn)
    root_codes = conn.execute(
        "SELECT name FROM codebook_code "
        "WHERE kind='code' AND parent_id IS NULL ORDER BY name"
    ).fetchall()
    assert [r[0] for r in root_codes] == ["Stigma", "Trust"]


def test_v7_migration_folders_have_no_colour_no_chord(tmp_path):
    conn = _build_v6_codebook(tmp_path)
    _migrate_v6_to_v7(conn)
    rows = conn.execute(
        "SELECT colour, chord FROM codebook_code WHERE kind='folder'"
    ).fetchall()
    for colour, chord in rows:
        assert colour == ""
        assert chord is None


def test_v7_migration_idempotent(tmp_path):
    conn = _build_v6_codebook(tmp_path)
    _migrate_v6_to_v7(conn)
    folder_count_first = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE kind='folder'"
    ).fetchone()[0]
    _migrate_v6_to_v7(conn)  # second call must be a no-op
    folder_count_second = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE kind='folder'"
    ).fetchone()[0]
    assert folder_count_first == folder_count_second


def test_v7_migration_handles_empty_codebook(tmp_path):
    db = tmp_path / "empty.ace"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE codebook_code (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, colour TEXT NOT NULL,
            sort_order INTEGER NOT NULL, group_name TEXT, chord TEXT,
            created_at TEXT NOT NULL, deleted_at TEXT
        );
        PRAGMA user_version = 6;
    """)
    conn.commit()
    _migrate_v6_to_v7(conn)
    assert conn.execute("SELECT COUNT(*) FROM codebook_code").fetchone()[0] == 0


def test_v7_migration_preserves_chord_column(tmp_path):
    conn = _build_v6_codebook(tmp_path)
    _migrate_v6_to_v7(conn)
    chord = conn.execute(
        "SELECT chord FROM codebook_code WHERE name='Stigma'"
    ).fetchone()[0]
    assert chord == "qa"


def test_v7_check_and_migrate_runs_through_full_chain(tmp_path):
    """End-to-end: a fresh v1-style DB migrates all the way to v7."""
    conn = sqlite3.connect(tmp_path / "fresh.ace")
    # Build minimal v1 codebook
    conn.executescript("""
        CREATE TABLE codebook_code (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, colour TEXT NOT NULL,
            sort_order INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        PRAGMA user_version = 1;
    """)
    conn.commit()
    final = check_and_migrate(conn)
    assert final == SCHEMA_VERSION
    assert final == 7


def test_v7_folder_and_code_share_name_namespace(tmp_path):
    """A folder and a code can have the same name (per spec §3.5.5)."""
    from ace.db.connection import create_project, open_project
    from ace.models.codebook import add_code, add_folder
    db = tmp_path / "ns.ace"
    create_project(str(db), "Test")
    conn = open_project(str(db))
    fid = add_folder(conn, "Themes")
    cid = add_code(conn, "Themes", "#D55E00")  # same name, different kind — must succeed
    assert fid != cid


def test_v7_case_insensitive_collision_within_kind(tmp_path):
    """Two folders with names differing only in case should collide."""
    import sqlite3
    from ace.db.connection import create_project, open_project
    from ace.models.codebook import add_folder
    db = tmp_path / "case.ace"
    create_project(str(db), "Test")
    conn = open_project(str(db))
    add_folder(conn, "Themes")
    with pytest.raises(sqlite3.IntegrityError):
        add_folder(conn, "themes")  # NOCASE collision — must raise


def test_v7_check_constraint_blocks_folder_with_chord(tmp_path):
    """The CHECK constraint catches a malformed folder write at the DB level."""
    import sqlite3
    from ace.db.connection import create_project, open_project
    db = tmp_path / "ck.ace"
    create_project(str(db), "Test")
    conn = open_project(str(db))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO codebook_code "
            "(id, name, colour, sort_order, kind, parent_id, chord, created_at) "
            "VALUES ('f1', 'Themes', '#FF0000', 1, 'folder', NULL, 'qa', '2026-01-01')"
        )


def test_v7_idempotent_after_partial_completion(tmp_path):
    """Half-completed migration: columns added but DROP COLUMN failed.
    Re-running must not duplicate folder rows."""
    conn = _build_v6_codebook(tmp_path)
    # Simulate Step A done, Step C started but failed before DROP COLUMN.
    _migrate_v6_to_v7(conn)
    # Pretend group_name still exists by re-adding it (tests the guard).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(codebook_code)").fetchall()}
    if "group_name" not in cols:
        conn.execute("ALTER TABLE codebook_code ADD COLUMN group_name TEXT")
        conn.execute(
            "UPDATE codebook_code SET group_name = ? "
            "WHERE name IN ('Identity', 'Belonging') AND kind = 'code'",
            ("Themes",),
        )
        conn.execute(
            "UPDATE codebook_code SET group_name = ? "
            "WHERE name = 'Negotiation' AND kind = 'code'",
            ("Process",),
        )
        conn.commit()
    folder_count_before = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE kind='folder'"
    ).fetchone()[0]
    _migrate_v6_to_v7(conn)
    folder_count_after = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE kind='folder'"
    ).fetchone()[0]
    assert folder_count_before == folder_count_after  # no duplicates
