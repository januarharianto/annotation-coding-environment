"""CRUD operations for codebook_code table."""

import colorsys
import csv
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ace.services.chord_assignment import assign_chord

# Single-key shortcut slots: 10 digits (1-9, 0) + a-p minus n (15) +
# r-y minus v and x (6) = 31. Reserved keys: q, x, z, n, v.
# Codes at position >= 31 (0-indexed by sort_order rank) get a 2-letter chord shortcut.
SINGLE_KEY_LIMIT = 31

_INSERT_CODE_SQL = (
    "INSERT INTO codebook_code "
    "(id, name, colour, sort_order, group_name, chord, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


# ---------------------------------------------------------------------------
# Colour palette — golden-angle hue spacing with alternating lightness bands
# ---------------------------------------------------------------------------

def _generate_palette(n: int) -> list[tuple[str, str]]:
    golden_ratio = 0.618033988749895
    colours = []
    for i in range(n):
        hue = (i * golden_ratio) % 1.0
        lightness = 0.38 if i % 2 == 0 else 0.62
        saturation = 0.75
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        hex_val = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"
        colours.append((hex_val, f"Colour {i + 1}"))
    return colours


COLOUR_PALETTE = _generate_palette(36)


def next_colour(existing_count: int) -> str:
    """Return the next colour from the palette, cycling if needed."""
    return COLOUR_PALETTE[existing_count % len(COLOUR_PALETTE)][0]

_UNSET = object()


def _taken_chords(conn: sqlite3.Connection) -> set[str]:
    """Return the set of chord values currently in use (non-NULL only, undeleted)."""
    return {
        r[0] for r in conn.execute(
            "SELECT chord FROM codebook_code "
            "WHERE chord IS NOT NULL AND deleted_at IS NULL"
        )
    }


def add_code(
    conn: sqlite3.Connection,
    name: str,
    colour: str,
    group_name: str | None = None,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    code_id = uuid.uuid4().hex

    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code WHERE deleted_at IS NULL"
    ).fetchone()[0]
    sort_order = max_order + 1

    # Position of the new code = current count (0-indexed). If position >= SINGLE_KEY_LIMIT,
    # the keyboard's single-key slots are exhausted and the code needs a chord shortcut.
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM codebook_code WHERE deleted_at IS NULL"
    ).fetchone()[0]
    chord = None
    if existing_count >= SINGLE_KEY_LIMIT:
        chord = assign_chord(name, _taken_chords(conn))

    conn.execute(
        _INSERT_CODE_SQL,
        (code_id, name, colour, sort_order, group_name, chord, now),
    )
    conn.commit()
    return code_id


def list_codes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM codebook_code WHERE deleted_at IS NULL ORDER BY sort_order"
    ).fetchall()


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


def set_chord(conn: sqlite3.Connection, code_id: str, chord: str | None) -> None:
    """Set or clear the chord for a code. Raises IntegrityError on conflict."""
    conn.execute(
        "UPDATE codebook_code SET chord = ? WHERE id = ?",
        (chord, code_id),
    )
    conn.commit()


def backfill_chords(conn: sqlite3.Connection) -> int:
    """Assign chords to any code at position >= SINGLE_KEY_LIMIT with chord IS NULL.

    Position is 0-indexed rank ordered by sort_order, so this is robust to
    0-indexed, 1-indexed, or sparse sort_order values. Idempotent: codes that
    already have a chord are untouched. Returns the number of chords assigned.

    NOTE: does NOT commit. Caller is responsible for committing — this is the
    only write function in this module with that contract, intentionally so
    that bulk-import callers can keep inserts + backfill in one transaction.
    """
    rows = conn.execute(
        """
        WITH ranked AS (
          SELECT id, name, chord,
                 ROW_NUMBER() OVER (ORDER BY sort_order) - 1 AS pos
          FROM codebook_code
          WHERE deleted_at IS NULL
        )
        SELECT id, name FROM ranked
        WHERE pos >= ? AND chord IS NULL
        ORDER BY pos
        """,
        (SINGLE_KEY_LIMIT,),
    ).fetchall()

    if not rows:
        return 0

    taken = _taken_chords(conn)
    assigned = 0
    for row in rows:
        chord = assign_chord(row["name"], taken)
        conn.execute(
            "UPDATE codebook_code SET chord = ? WHERE id = ?",
            (chord, row["id"]),
        )
        taken.add(chord)
        assigned += 1
    return assigned


def rename_group(
    conn: sqlite3.Connection,
    old_name: str,
    new_name: str,
) -> int:
    """Rename a group by updating group_name on all codes in that group.

    Returns the number of codes affected.
    """
    new_val = new_name.strip() if new_name.strip() else None
    old_val = old_name if old_name else None
    cur = conn.execute(
        "UPDATE codebook_code SET group_name = ? WHERE group_name IS ?",
        (new_val, old_val),
    )
    conn.commit()
    return cur.rowcount


def reorder_codes(conn: sqlite3.Connection, code_ids: list[str]) -> None:
    for i, code_id in enumerate(code_ids):
        conn.execute(
            "UPDATE codebook_code SET sort_order = ? WHERE id = ?",
            (i, code_id),
        )
    conn.commit()


def delete_code(conn: sqlite3.Connection, code_id: str) -> list[str]:
    """Soft-delete a code and its referencing annotations.

    Returns the list of annotation IDs that were just soft-deleted (only
    those that were active before the call). The caller passes this list
    to restore_code() to undo the cascade.
    """
    now = datetime.now(timezone.utc).isoformat()

    affected = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM annotation WHERE code_id = ? AND deleted_at IS NULL",
            (code_id,),
        ).fetchall()
    ]

    try:
        conn.execute(
            "UPDATE annotation SET deleted_at = ? WHERE code_id = ? AND deleted_at IS NULL",
            (now, code_id),
        )
        conn.execute(
            "UPDATE codebook_code SET deleted_at = ? WHERE id = ?",
            (now, code_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return affected


def restore_code(
    conn: sqlite3.Connection,
    code_id: str,
    annotation_ids: list[str],
) -> None:
    """Inverse of delete_code: clear deleted_at on the code and each annotation. Atomic."""
    try:
        conn.execute(
            "UPDATE codebook_code SET deleted_at = NULL WHERE id = ?",
            (code_id,),
        )
        for ann_id in annotation_ids:
            conn.execute(
                "UPDATE annotation SET deleted_at = NULL WHERE id = ?",
                (ann_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def compute_codebook_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT id, name, colour, group_name FROM codebook_code WHERE deleted_at IS NULL ORDER BY id"
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
        r["name"]
        for r in conn.execute(
            "SELECT name FROM codebook_code WHERE deleted_at IS NULL"
        ).fetchall()
    }
    return [
        {**r, "exists": r["name"] in existing}
        for r in rows
    ]


def import_selected_codes(conn: sqlite3.Connection, codes: list[dict]) -> list[str]:
    """Import a pre-filtered list of codes into the codebook.

    Each dict must have 'name' and 'colour' keys.
    Skips codes whose name already exists (safety net).
    All inserts in a single transaction with rollback on failure.
    Returns the list of inserted code IDs (in the order they were inserted).
    """
    if not codes:
        return []

    existing = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM codebook_code WHERE deleted_at IS NULL"
        ).fetchall()
    }
    to_insert = [c for c in codes if c["name"] not in existing]
    if not to_insert:
        return []

    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM codebook_code WHERE deleted_at IS NULL"
    ).fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()

    inserted_ids: list[str] = []
    try:
        for i, code in enumerate(to_insert):
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, chord, created_at) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (code_id, code["name"], code["colour"], max_order + i + 1,
                 code.get("group_name"), now),
            )
            inserted_ids.append(code_id)
        backfill_chords(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return inserted_ids


def import_codebook_from_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    rows_to_insert = _parse_codebook_csv(path)

    now = datetime.now(timezone.utc).isoformat()
    try:
        for i, row in enumerate(rows_to_insert):
            code_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO codebook_code (id, name, colour, sort_order, group_name, chord, created_at) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (code_id, row["name"], row["colour"], i + 1, row.get("group_name"), now),
            )
        backfill_chords(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows_to_insert)


def export_codebook_to_csv(conn: sqlite3.Connection, path: str | Path) -> int:
    path = Path(path)
    codes = conn.execute(
        "SELECT name, group_name FROM codebook_code WHERE deleted_at IS NULL ORDER BY sort_order"
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
