"""Coder package export and import/merge service."""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from ace.db.connection import checkpoint_and_close, open_project
from ace.db.schema import ACE_APPLICATION_ID, create_schema
from ace.models.codebook import compute_codebook_hash


def _upsert_by_id(conn: sqlite3.Connection, table: str, row: sqlite3.Row) -> str:
    """UPSERT a row by its 'id' column. Returns 'insert', 'update', or 'skip'."""
    existing = conn.execute(
        f"SELECT id, updated_at FROM {table} WHERE id = ?", (row["id"],)
    ).fetchone()
    cols = row.keys()
    if existing is None:
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(row),
        )
        return "insert"
    if row["updated_at"] > existing["updated_at"]:
        update_cols = [c for c in cols if c not in ("id", "created_at")]
        sets = ", ".join(f"{c} = ?" for c in update_cols)
        conn.execute(
            f"UPDATE {table} SET {sets} WHERE id = ?",
            [row[c] for c in update_cols] + [row["id"]],
        )
        return "update"
    return "skip"


def _upsert_by_key(
    conn: sqlite3.Connection, table: str, row: sqlite3.Row,
    *, key_cols: tuple[str, ...], update_cols: tuple[str, ...],
) -> str:
    """UPSERT a row by composite key columns. Returns 'insert', 'update', or 'skip'."""
    where = " AND ".join(f"{c} = ?" for c in key_cols)
    key_vals = [row[c] for c in key_cols]
    existing = conn.execute(
        f"SELECT updated_at FROM {table} WHERE {where}", key_vals
    ).fetchone()
    if existing is None:
        cols = row.keys()
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(row),
        )
        return "insert"
    if row["updated_at"] > existing["updated_at"]:
        sets = ", ".join(f"{c} = ?" for c in update_cols)
        conn.execute(
            f"UPDATE {table} SET {sets} WHERE {where}",
            [row[c] for c in update_cols] + key_vals,
        )
        return "update"
    return "skip"


@dataclass
class ImportResult:
    annotations_imported: int = 0
    annotations_skipped: int = 0
    annotations_updated: int = 0
    notes_imported: int = 0
    warnings: list = field(default_factory=list)


def export_coder_package(
    conn: sqlite3.Connection, coder_id: str, output_dir: str | Path
) -> Path:
    """Export a coder package (.ace file) containing only this coder's assigned work.

    Steps:
    1. Get project and coder info
    2. Compute and store codebook_hash in main project
    3. Create new SQLite file at output_dir/project-name_coder-name.ace
    4. Run create_schema on new DB
    5. Copy project row with file_role='coder' and codebook_hash
    6. Copy only this coder's assigned sources + source_content
    7. Copy full codebook
    8. Copy this coder only
    9. Copy this coder's assignments only
    10. Annotation and source_note tables left empty
    11. checkpoint_and_close the new DB
    12. Return the path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Get project and coder info
    project = conn.execute("SELECT * FROM project").fetchone()
    coder = conn.execute("SELECT * FROM coder WHERE id = ?", (coder_id,)).fetchone()
    if coder is None:
        raise ValueError(f"Coder not found: {coder_id}")

    # 2. Compute and store codebook_hash
    cb_hash = compute_codebook_hash(conn)
    conn.execute("UPDATE project SET codebook_hash = ?", (cb_hash,))
    conn.commit()

    # 3. Create new SQLite file
    safe_project = project["name"].replace(" ", "-").lower()
    safe_coder = coder["name"].replace(" ", "-").lower()
    pkg_path = output_dir / f"{safe_project}_{safe_coder}.ace"

    pkg_conn = sqlite3.connect(str(pkg_path))
    pkg_conn.row_factory = sqlite3.Row
    pkg_conn.execute("PRAGMA journal_mode = WAL")

    # 4. Run create_schema
    create_schema(pkg_conn)

    # 5. Copy project row with file_role='coder'
    pkg_conn.execute(
        "INSERT INTO project (id, name, description, instructions, file_role, codebook_hash, assignment_seed, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'coder', ?, ?, ?, ?)",
        (
            project["id"],
            project["name"],
            project["description"],
            project["instructions"],
            cb_hash,
            project["assignment_seed"],
            project["created_at"],
            project["updated_at"],
        ),
    )

    # 6. Copy only this coder's assigned sources + source_content
    assigned_sources = conn.execute(
        "SELECT s.* FROM source s "
        "JOIN assignment a ON a.source_id = s.id "
        "WHERE a.coder_id = ? ORDER BY s.sort_order",
        (coder_id,),
    ).fetchall()

    for src in assigned_sources:
        pkg_conn.execute(
            "INSERT INTO source (id, display_id, source_type, source_column, filename, metadata_json, sort_order, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(src),
        )
        sc = conn.execute(
            "SELECT * FROM source_content WHERE source_id = ?", (src["id"],)
        ).fetchone()
        if sc is not None:
            pkg_conn.execute(
                "INSERT INTO source_content (source_id, content_text, content_hash) VALUES (?, ?, ?)",
                tuple(sc),
            )

    # 7. Copy full codebook
    codes = conn.execute(
        "SELECT * FROM codebook_code ORDER BY sort_order"
    ).fetchall()
    for code in codes:
        pkg_conn.execute(
            "INSERT INTO codebook_code (id, name, colour, sort_order, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (code["id"], code["name"], code["colour"], code["sort_order"], code["created_at"]),
        )

    # 8. Copy this coder only
    pkg_conn.execute(
        "INSERT INTO coder (id, name) VALUES (?, ?)",
        (coder["id"], coder["name"]),
    )

    # 9. Copy this coder's assignments only
    assignments = conn.execute(
        "SELECT * FROM assignment WHERE coder_id = ?", (coder_id,)
    ).fetchall()
    for asn in assignments:
        pkg_conn.execute(
            "INSERT INTO assignment (id, source_id, coder_id, status, assigned_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            tuple(asn),
        )

    # 10. Annotation and source_note tables left empty
    # 11. checkpoint_and_close
    pkg_conn.commit()
    checkpoint_and_close(pkg_conn)

    # 12. Return the path
    return pkg_path


def import_coder_package(
    conn: sqlite3.Connection, pkg_path: str | Path
) -> ImportResult:
    """Import annotations and notes from a coder package back into the main project.

    Steps:
    1. Open .ace file read-only
    2. Validate application_id, project.id match, file_role='coder'
    3. Validate content_hash for each source
    4. Check codebook drift
    5. UPSERT annotations by UUID
    6. Import source_notes (UPSERT by source_id + coder_id)
    7. Update assignment statuses
    8. All in a single transaction (rollback on error)
    9. Return ImportResult
    """
    pkg_path = Path(pkg_path)
    result = ImportResult()

    # 1. Open package read-only
    pkg_conn = sqlite3.connect(f"file:{pkg_path}?mode=ro", uri=True)
    pkg_conn.row_factory = sqlite3.Row

    try:
        # 2. Validate application_id, project.id, file_role
        app_id = pkg_conn.execute("PRAGMA application_id").fetchone()[0]
        if app_id != ACE_APPLICATION_ID:
            raise ValueError(
                f"Not a valid ACE package file (application_id={app_id:#x})"
            )

        pkg_project = pkg_conn.execute("SELECT * FROM project").fetchone()
        main_project = conn.execute("SELECT * FROM project").fetchone()

        if pkg_project["id"] != main_project["id"]:
            raise ValueError(
                f"Package project ID {pkg_project['id']} does not match "
                f"main project ID {main_project['id']}"
            )

        if pkg_project["file_role"] != "coder":
            raise ValueError(
                f"Package file_role is '{pkg_project['file_role']}', expected 'coder'"
            )

        # 3. Validate content_hash for each source
        pkg_sources = pkg_conn.execute(
            "SELECT sc.source_id, sc.content_hash FROM source_content sc"
        ).fetchall()
        for ps in pkg_sources:
            main_hash = conn.execute(
                "SELECT content_hash FROM source_content WHERE source_id = ?",
                (ps["source_id"],),
            ).fetchone()
            if main_hash is None:
                result.warnings.append(
                    f"Source {ps['source_id']} not found in main project"
                )
                continue
            if main_hash["content_hash"] != ps["content_hash"]:
                result.warnings.append(
                    f"Content hash mismatch for source {ps['source_id']}"
                )

        # 4. Check codebook drift — if codes were deleted in main, re-insert from coder file
        pkg_codes = pkg_conn.execute("SELECT * FROM codebook_code").fetchall()
        for pc in pkg_codes:
            existing = conn.execute(
                "SELECT id FROM codebook_code WHERE id = ?", (pc["id"],)
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO codebook_code (id, name, colour, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pc["id"], pc["name"], pc["colour"], pc["sort_order"], pc["created_at"]),
                )
                result.warnings.append(
                    f"Re-inserted deleted code: {pc['name']}"
                )

        # 5. UPSERT annotations by UUID
        pkg_annotations = pkg_conn.execute(
            "SELECT * FROM annotation WHERE deleted_at IS NULL"
        ).fetchall()
        for pa in pkg_annotations:
            action = _upsert_by_id(conn, "annotation", pa)
            if action == "insert":
                result.annotations_imported += 1
            elif action == "update":
                result.annotations_updated += 1
            else:
                result.annotations_skipped += 1

        # 6. Import source_notes (UPSERT by source_id + coder_id)
        pkg_notes = pkg_conn.execute("SELECT * FROM source_note").fetchall()
        for pn in pkg_notes:
            action = _upsert_by_key(
                conn, "source_note", pn,
                key_cols=("source_id", "coder_id"),
                update_cols=("note_text", "updated_at"),
            )
            if action in ("insert", "update"):
                result.notes_imported += 1

        # 7. Update assignment statuses from package
        pkg_assignments = pkg_conn.execute("SELECT * FROM assignment").fetchall()
        for pa in pkg_assignments:
            conn.execute(
                "UPDATE assignment SET status = ?, updated_at = ? "
                "WHERE source_id = ? AND coder_id = ?",
                (pa["status"], pa["updated_at"], pa["source_id"], pa["coder_id"]),
            )

        # 8. Commit the transaction
        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        pkg_conn.close()

    return result
