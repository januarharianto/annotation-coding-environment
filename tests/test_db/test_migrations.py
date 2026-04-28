"""Tests for schema migrations."""

import sqlite3

import pytest

from ace.db.connection import create_project, open_project
from ace.db.schema import ACE_APPLICATION_ID


def test_v1_to_v2_migration_adds_group_name(tmp_path):
    """Opening a v1 database migrates it to v2 with group_name column."""
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

    # Open with open_project — should trigger migration
    conn = open_project(db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 2

    # group_name column should exist and be NULL for existing codes
    row = conn.execute("SELECT group_name FROM codebook_code WHERE name = 'Alpha'").fetchone()
    assert row["group_name"] is None
    conn.close()


def test_fresh_db_has_group_name_column(tmp_path):
    """A newly created project has the group_name column."""
    db_path = tmp_path / "fresh.ace"
    conn = create_project(db_path, "Test")
    # Should not raise — column exists
    conn.execute("SELECT group_name FROM codebook_code").fetchall()
    conn.close()


def test_v2_to_v3_migration_adds_deleted_at_to_codebook(tmp_path):
    """Opening a v2 database migrates it to v3 with deleted_at column on codebook_code."""
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
        "INSERT INTO codebook_code VALUES ('cc2', 'Alpha', '#00FF00', 2, NULL, '2025-01-02', NULL)"
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
            "INSERT INTO codebook_code VALUES ('cc2', 'Alpha', '#00FF00', 2, NULL, '2025-01-02', NULL)"
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
