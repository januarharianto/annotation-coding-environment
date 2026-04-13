"""Export source notes to CSV."""

import csv
import sqlite3
from pathlib import Path

from ace.models.source_note import list_notes_for_export

_FIELDNAMES = [
    "source_display_id",
    "source_filename",
    "coder_name",
    "note_text",
    "created_at",
    "updated_at",
]


def export_notes_csv(
    conn: sqlite3.Connection,
    coder_id: str,
    output_path: str | Path,
) -> int:
    """Write all source notes for a coder to a CSV file.

    Returns the number of rows written (excluding the header).
    """
    rows = list_notes_for_export(conn, coder_id)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "source_display_id": row["display_id"],
                "source_filename": row["filename"] or "",
                "coder_name": row["coder_name"],
                "note_text": row["note_text"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
    return len(rows)
