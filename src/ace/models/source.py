"""CRUD operations for source and source_content tables."""

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone


def add_source(
    conn: sqlite3.Connection,
    display_id: str,
    content_text: str,
    source_type: str,
    filename: str | None = None,
    source_column: str | None = None,
    metadata: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    source_id = uuid.uuid4().hex
    content_hash = hashlib.sha256(content_text.encode()).hexdigest()
    metadata_json = json.dumps(metadata) if metadata is not None else None

    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM source").fetchone()[0]
    sort_order = max_order + 1

    conn.execute(
        "INSERT INTO source (id, display_id, source_type, source_column, filename, metadata_json, sort_order, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, display_id, source_type, source_column, filename, metadata_json, sort_order, now),
    )
    conn.execute(
        "INSERT INTO source_content (source_id, content_text, content_hash) VALUES (?, ?, ?)",
        (source_id, content_text, content_hash),
    )
    conn.commit()
    return source_id


def get_source(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM source WHERE id = ?", (source_id,)).fetchone()


def get_source_content(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM source_content WHERE source_id = ?", (source_id,)).fetchone()


def list_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM source ORDER BY sort_order").fetchall()
