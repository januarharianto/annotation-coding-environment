"""CRUD operations for codebook_code table."""

import csv
import hashlib
import re as _re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ace.services.palette import next_colour

_COLOUR_RE = _re.compile(r"^#[0-9A-Fa-f]{6}$")


def add_code(
    conn: sqlite3.Connection,
    name: str,
    colour: str,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    code_id = uuid.uuid4().hex

    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code").fetchone()[0]
    sort_order = max_order + 1

    conn.execute(
        "INSERT INTO codebook_code (id, name, colour, sort_order, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (code_id, name, colour, sort_order, now),
    )
    conn.commit()
    return code_id


def list_codes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM codebook_code ORDER BY sort_order").fetchall()


def update_code(
    conn: sqlite3.Connection,
    code_id: str,
    name: str | None = None,
    colour: str | None = None,
) -> None:
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if colour is not None:
        updates.append("colour = ?")
        params.append(colour)
    if not updates:
        return
    params.append(code_id)
    conn.execute(
        f"UPDATE codebook_code SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()


def reorder_codes(conn: sqlite3.Connection, code_ids: list[str]) -> None:
    for i, code_id in enumerate(code_ids):
        conn.execute(
            "UPDATE codebook_code SET sort_order = ? WHERE id = ?",
            (i, code_id),
        )
    conn.commit()


def delete_code(conn: sqlite3.Connection, code_id: str) -> None:
    conn.execute("DELETE FROM annotation WHERE code_id = ?", (code_id,))
    conn.execute("DELETE FROM codebook_code WHERE id = ?", (code_id,))
    conn.commit()


def compute_codebook_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, name, colour FROM codebook_code ORDER BY id"
    ).fetchall()
    combined = "".join(f"{r['id']}{r['name']}{r['colour']}" for r in rows)
    return hashlib.sha256(combined.encode()).hexdigest()


def import_codebook_from_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "name" not in reader.fieldnames:
            raise ValueError("CSV must have a 'name' column")

        rows_to_insert = []
        seen_names: set[str] = set()
        for row in reader:
            name = row.get("name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            colour = row.get("colour", "").strip()
            if not _COLOUR_RE.match(colour):
                colour = next_colour(len(rows_to_insert))

            rows_to_insert.append((name, colour))

    now = datetime.now(timezone.utc).isoformat()
    try:
        for i, (name, colour) in enumerate(rows_to_insert):
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (code_id, name, colour, i + 1, now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows_to_insert)


def export_codebook_to_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    codes = conn.execute(
        "SELECT name, colour FROM codebook_code ORDER BY sort_order"
    ).fetchall()
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "colour"])
        writer.writeheader()
        for code in codes:
            writer.writerow({
                "name": code["name"],
                "colour": code["colour"],
            })
    return len(codes)
