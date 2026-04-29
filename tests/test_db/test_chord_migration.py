"""Tests for v4 → v5 migration: add chord column to codebook_code."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from ace.db.connection import open_project, create_project


def test_new_project_has_chord_column():
    """New v5 .ace files have the chord column."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fresh.ace"
        create_project(str(path), "Test")
        conn = open_project(str(path))
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(codebook_code)")}
        conn.close()
        assert "chord" in cols


def test_v4_to_v5_migration_adds_column():
    """A v4 .ace file gains the chord column on open."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v4.ace"

        # Create a v4-shaped database manually
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA application_id = 0x41434500")
        conn.execute("PRAGMA user_version = 4")
        conn.execute("""
            CREATE TABLE codebook_code (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                colour TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                group_name TEXT,
                created_at TEXT NOT NULL,
                deleted_at TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Open: triggers migration to v6 (via v5 → v6 chain)
        conn = open_project(str(path))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(codebook_code)")}
        conn.close()
        assert version == 6
        assert "chord" in cols


def test_migration_is_idempotent():
    """Running migrations twice on a v5 file is a no-op."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fresh.ace"
        create_project(str(path), "Test")

        # First open → already at v5
        conn = open_project(str(path))
        v1 = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()

        # Second open → still v5, no errors
        conn = open_project(str(path))
        v2 = conn.execute("PRAGMA user_version").fetchone()[0]
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(codebook_code)")}
        conn.close()

        assert v1 == v2 == 6
        assert "chord" in cols


def test_v5_to_v6_tightens_index_for_soft_deletes():
    """v5→v6 migration recreates idx_codebook_chord to exclude deleted rows."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "v5.ace"

        # Build a v5-shaped DB by hand
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA application_id = 0x41434500")
        conn.execute("PRAGMA user_version = 5")
        conn.execute("""
            CREATE TABLE codebook_code (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                colour TEXT NOT NULL,
                sort_order INTEGER NOT NULL,
                group_name TEXT,
                chord TEXT,
                created_at TEXT NOT NULL,
                deleted_at TEXT
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX idx_codebook_chord
                ON codebook_code(chord) WHERE chord IS NOT NULL
        """)
        # Soft-deleted code with chord "ab"
        conn.execute(
            "INSERT INTO codebook_code (id, name, colour, sort_order, chord, created_at, deleted_at) "
            "VALUES ('a', 'A', '#A91818', 0, 'ab', datetime('now'), datetime('now'))"
        )
        conn.commit()
        conn.close()

        # Open: triggers v5→v6 migration. New code with chord "ab" should now be insertable.
        conn = open_project(str(path))
        try:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, chord, created_at) "
                "VALUES ('b', 'B', '#557FE6', 1, 'ab', datetime('now'))"
            )
            conn.commit()
        finally:
            conn.close()


def test_chord_unique_when_set():
    """Two codes can both have NULL chord, but not duplicate non-null values."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fresh.ace"
        create_project(str(path), "Test")

        conn = open_project(str(path))
        from ace.models.codebook import add_code
        id1 = add_code(conn, "Code A", "#A91818")
        id2 = add_code(conn, "Code B", "#557FE6")

        # Both NULL — fine
        conn.execute("UPDATE codebook_code SET chord = NULL WHERE id = ?", (id1,))
        conn.execute("UPDATE codebook_code SET chord = NULL WHERE id = ?", (id2,))
        conn.commit()

        # Set same chord on both — must fail
        conn.execute("UPDATE codebook_code SET chord = 'pd' WHERE id = ?", (id1,))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE codebook_code SET chord = 'pd' WHERE id = ?", (id2,))
            conn.commit()
        conn.close()
