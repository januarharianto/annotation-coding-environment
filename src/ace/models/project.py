"""CRUD operations for project table."""

import sqlite3
import uuid


def get_project(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM project").fetchone()


# ── Coder helpers ──────────────────────────────────────────────


def add_coder(conn: sqlite3.Connection, name: str) -> str:
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, name))
    conn.commit()
    return coder_id


def list_coders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM coder").fetchall()
