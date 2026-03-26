"""CRUD operations for codebook_code table."""

import csv
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ace.services.palette import next_colour

_UNSET = object()


def add_code(
    conn: sqlite3.Connection,
    name: str,
    colour: str,
    group_name: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    code_id = uuid.uuid4().hex

    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code").fetchone()[0]
    sort_order = max_order + 1

    conn.execute(
        "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (code_id, name, colour, sort_order, group_name, now),
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
    group_name: object = _UNSET,
) -> None:
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if colour is not None:
        updates.append("colour = ?")
        params.append(colour)
    if group_name is not _UNSET:
        updates.append("group_name = ?")
        params.append(group_name if group_name != "" else None)
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
        "SELECT id, name, colour, group_name FROM codebook_code ORDER BY id"
    ).fetchall()
    combined = "".join(
        f"{r['id']}{r['name']}{r['colour']}{r['group_name'] or ''}"
        for r in rows
    )
    return hashlib.sha256(combined.encode()).hexdigest()


def _parse_codebook_csv(path: str | Path) -> list[dict]:
    """Parse a codebook CSV file into a list of {name, colour, group_name} dicts.

    Reads 'group' column if present (strips whitespace, preserves casing).
    Ignores 'colour' column — always auto-assigns from palette.
    Raises ValueError if 'name' column is missing.
    """
    path = Path(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "name" not in reader.fieldnames:
            raise ValueError("CSV must have a 'name' column")

        has_group = "group" in (reader.fieldnames or [])
        rows: list[dict] = []
        seen_names: set[str] = set()
        for row in reader:
            name = row.get("name", "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            colour = next_colour(len(rows))

            group_name = None
            if has_group:
                g = row.get("group", "").strip()
                if g:
                    group_name = g

            rows.append({"name": name, "colour": colour, "group_name": group_name})
    return rows


def preview_codebook_csv(conn: sqlite3.Connection, path: str | Path) -> list[dict]:
    """Parse a codebook CSV and mark which codes already exist in the project.

    Returns list of {"name", "colour", "group_name", "exists"} dicts.
    """
    rows = _parse_codebook_csv(path)
    existing = {
        r["name"] for r in conn.execute("SELECT name FROM codebook_code").fetchall()
    }
    return [
        {**r, "exists": r["name"] in existing}
        for r in rows
    ]


def import_selected_codes(conn: sqlite3.Connection, codes: list[dict]) -> int:
    """Import a pre-filtered list of codes into the codebook.

    Each dict must have 'name' and 'colour' keys.
    Skips codes whose name already exists (safety net).
    All inserts in a single transaction with rollback on failure.
    Returns count of codes actually inserted.
    """
    if not codes:
        return 0

    existing = {
        r["name"] for r in conn.execute("SELECT name FROM codebook_code").fetchall()
    }
    to_insert = [c for c in codes if c["name"] not in existing]
    if not to_insert:
        return 0

    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code"
    ).fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()

    try:
        for i, code in enumerate(to_insert):
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (uuid.uuid4().hex, code["name"], code["colour"], max_order + i + 1,
                 code.get("group_name"), now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(to_insert)


def import_codebook_from_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    rows_to_insert = _parse_codebook_csv(path)

    now = datetime.now(timezone.utc).isoformat()
    try:
        for i, row in enumerate(rows_to_insert):
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (code_id, row["name"], row["colour"], i + 1, row.get("group_name"), now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows_to_insert)


def export_codebook_to_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    codes = conn.execute(
        "SELECT name, group_name FROM codebook_code ORDER BY sort_order"
    ).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "group"])
        writer.writeheader()
        for code in codes:
            writer.writerow({
                "name": code["name"],
                "group": code["group_name"] or "",
            })
    return len(codes)
