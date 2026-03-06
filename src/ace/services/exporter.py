"""Export annotations to CSV."""

import csv
import json
import sqlite3
from pathlib import Path

_EXPORT_QUERY = """
SELECT
    a.source_id,
    s.display_id,
    c.name  AS coder_name,
    cc.name AS code_name,
    a.selected_text,
    a.start_offset,
    a.end_offset,
    a.memo,
    s.metadata_json
FROM annotation a
JOIN source s        ON s.id  = a.source_id
JOIN coder c         ON c.id  = a.coder_id
JOIN codebook_code cc ON cc.id = a.code_id
WHERE a.deleted_at IS NULL
ORDER BY s.sort_order, a.start_offset
"""

_FIXED_COLUMNS = [
    "source_id",
    "display_id",
    "coder_name",
    "code_name",
    "selected_text",
    "start_offset",
    "end_offset",
    "memo",
]


def export_annotations_csv(
    conn: sqlite3.Connection,
    output_path: str | Path,
) -> int:
    """Export all non-deleted annotations to a CSV file.

    Returns the number of rows written (excluding the header).
    """
    rows = conn.execute(_EXPORT_QUERY).fetchall()

    # Discover all metadata keys across rows for flattening
    meta_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw = row["metadata_json"]
        if raw:
            for key in json.loads(raw):
                if key not in seen:
                    meta_keys.append(key)
                    seen.add(key)

    fieldnames = _FIXED_COLUMNS + meta_keys

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out: dict[str, object] = {col: row[col] for col in _FIXED_COLUMNS}
            raw = row["metadata_json"]
            if raw:
                meta = json.loads(raw)
                for key in meta_keys:
                    out[key] = meta.get(key, "")
            writer.writerow(out)

    return len(rows)
