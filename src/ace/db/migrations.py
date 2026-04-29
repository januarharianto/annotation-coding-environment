"""Migration runner for ACE project files."""

import sqlite3
from typing import Callable

from ace.db.schema import SCHEMA_VERSION

def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add group_name column to codebook_code."""
    conn.execute("ALTER TABLE codebook_code ADD COLUMN group_name TEXT")


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add deleted_at to codebook_code; replace column-level UNIQUE(name) with partial unique index.

    Wrapped in PRAGMA foreign_keys = OFF because the annotation table has
    code_id REFERENCES codebook_code(id) — dropping codebook_code with FKs on
    would error or cascade.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript("""
            CREATE TABLE codebook_code_new (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                colour      TEXT NOT NULL,
                sort_order  INTEGER NOT NULL,
                group_name  TEXT,
                created_at  TEXT NOT NULL,
                deleted_at  TEXT
            );

            INSERT INTO codebook_code_new
                (id, name, colour, sort_order, group_name, created_at, deleted_at)
            SELECT id, name, colour, sort_order, group_name, created_at, NULL
            FROM codebook_code;

            DROP TABLE codebook_code;
            ALTER TABLE codebook_code_new RENAME TO codebook_code;

            CREATE UNIQUE INDEX idx_codebook_code_name_active
                ON codebook_code(name) WHERE deleted_at IS NULL;
        """)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after v2→v3 migration: {violations}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Replace assignment.status (4-state) with assignment.flagged (binary).

    Only status='flagged' rows become flagged=1; pending / in_progress / complete
    are intentionally collapsed to flagged=0 because the auto-progress feature
    is being removed.

    Defensive: skips if the assignment table doesn't exist (some test fixtures
    construct minimal v1/v2 schemas without it).
    """
    has_assignment = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assignment'"
    ).fetchone()
    if has_assignment is None:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript("""
            CREATE TABLE assignment_new (
                id          TEXT PRIMARY KEY,
                source_id   TEXT NOT NULL REFERENCES source(id),
                coder_id    TEXT NOT NULL REFERENCES coder(id),
                flagged     INTEGER NOT NULL DEFAULT 0 CHECK (flagged IN (0, 1)),
                assigned_at TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                UNIQUE(source_id, coder_id)
            );

            INSERT INTO assignment_new
                (id, source_id, coder_id, flagged, assigned_at, updated_at)
            SELECT id, source_id, coder_id,
                   CASE status WHEN 'flagged' THEN 1 ELSE 0 END,
                   assigned_at, updated_at
            FROM assignment;

            DROP TABLE assignment;
            ALTER TABLE assignment_new RENAME TO assignment;

            CREATE INDEX idx_assignment_coder ON assignment(coder_id);
            CREATE INDEX idx_assignment_source ON assignment(source_id);
        """)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after v3→v4 migration: {violations}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """Add `chord` column to codebook_code for chord-key shortcuts.

    The column is nullable: the first 31 codes (positions 0-30 by sort_order
    rank) use single-key shortcuts and have NULL chord. Codes at position 31+
    get a 2-letter chord assigned by `services.chord_assignment.assign_chord`.

    Defensive: skips if codebook_code doesn't exist (some test fixtures build
    minimal schemas without it).

    See spec: docs/superpowers/specs/2026-04-29-codebook-chord-keys-design.md
    """
    has_codebook = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='codebook_code'"
    ).fetchone()
    if has_codebook is None:
        return

    # Column-existence probe — SQLite has no `ADD COLUMN IF NOT EXISTS`, and a
    # second ALTER raises OperationalError("duplicate column name: chord").
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(codebook_code)").fetchall()}
    if "chord" not in existing_cols:
        conn.execute("ALTER TABLE codebook_code ADD COLUMN chord TEXT")

    # Unique partial index — multiple NULL allowed, but values must be unique
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_codebook_chord
            ON codebook_code(chord) WHERE chord IS NOT NULL
    """)


# Registry of migration functions keyed by target version.
# Each function takes a connection and migrates from version (key - 1) to key.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    2: _migrate_v1_to_v2,
    3: _migrate_v2_to_v3,
    4: _migrate_v3_to_v4,
    5: _migrate_v4_to_v5,
}


def check_and_migrate(conn: sqlite3.Connection) -> int:
    """Check user_version and apply sequential migrations if needed.

    Returns the current schema version after any migrations.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    while current < SCHEMA_VERSION:
        next_version = current + 1
        migrate_fn = MIGRATIONS.get(next_version)
        if migrate_fn is None:
            raise RuntimeError(
                f"No migration found for version {current} -> {next_version}"
            )
        migrate_fn(conn)
        conn.execute(f"PRAGMA user_version = {next_version}")
        conn.commit()
        current = next_version

    return current
