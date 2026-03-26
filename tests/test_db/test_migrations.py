"""Tests for schema migrations."""

import sqlite3

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
    assert version == 2

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
