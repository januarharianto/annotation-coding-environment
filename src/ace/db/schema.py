"""SQLite schema definition for ACE project files."""

import sqlite3

ACE_APPLICATION_ID = 0x41434500  # "ACE\0"
SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS project (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    instructions TEXT,
    file_role   TEXT NOT NULL CHECK (file_role IN ('manager', 'coder')),
    codebook_hash TEXT,
    assignment_seed TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source (
    id            TEXT PRIMARY KEY,
    display_id    TEXT NOT NULL,
    source_type   TEXT NOT NULL CHECK (source_type IN ('file', 'row')),
    source_column TEXT,
    filename      TEXT,
    metadata_json TEXT,
    sort_order    INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_content (
    source_id    TEXT PRIMARY KEY REFERENCES source(id),
    content_text TEXT,
    content_hash TEXT
);

CREATE TABLE IF NOT EXISTS codebook_code (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    colour      TEXT,
    sort_order  INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coder (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS assignment (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL REFERENCES source(id),
    coder_id    TEXT NOT NULL REFERENCES coder(id),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'in_progress', 'complete', 'flagged')),
    assigned_at TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(source_id, coder_id)
);

CREATE TABLE IF NOT EXISTS annotation (
    id                TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL REFERENCES source(id),
    coder_id          TEXT NOT NULL REFERENCES coder(id),
    code_id           TEXT NOT NULL REFERENCES codebook_code(id),
    start_offset      INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset        INTEGER NOT NULL CHECK (end_offset > start_offset),
    selected_text     TEXT,
    memo              TEXT,
    w3c_selector_json TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    deleted_at        TEXT
);

CREATE TABLE IF NOT EXISTS source_note (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES source(id),
    coder_id   TEXT NOT NULL REFERENCES coder(id),
    note_text  TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, coder_id)
);

CREATE INDEX IF NOT EXISTS idx_annotation_source_coder
    ON annotation(source_id, coder_id) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_annotation_code
    ON annotation(code_id);

CREATE INDEX IF NOT EXISTS idx_assignment_coder
    ON assignment(coder_id);

CREATE INDEX IF NOT EXISTS idx_assignment_source
    ON assignment(source_id);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the full ACE schema on the given connection."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_SQL)
    conn.execute(f"PRAGMA application_id = {ACE_APPLICATION_ID}")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
