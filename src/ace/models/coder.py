"""CRUD operations for coder table."""

import sqlite3
import uuid


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
