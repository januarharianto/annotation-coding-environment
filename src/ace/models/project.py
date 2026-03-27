"""CRUD operations for project table."""

import sqlite3
import uuid
from datetime import datetime, timezone


def get_project(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM project").fetchone()


def update_instructions(conn: sqlite3.Connection, instructions: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE project SET instructions = ?, updated_at = ?",
        (instructions, now),
    )
    conn.commit()


# ── Coder helpers ──────────────────────────────────────────────


def add_coder(conn: sqlite3.Connection, name: str) -> str:
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, name))
    conn.commit()
    return coder_id


def update_coder(conn: sqlite3.Connection, coder_id: str, name: str) -> None:
    conn.execute("UPDATE coder SET name = ? WHERE id = ?", (name, coder_id))
    conn.commit()


def list_coders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM coder").fetchall()
