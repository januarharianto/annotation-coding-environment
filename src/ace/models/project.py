"""CRUD operations for project table."""

import sqlite3
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
