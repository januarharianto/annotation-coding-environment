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
  AND cc.deleted_at IS NULL
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


def merge_adjacent_annotations(annotations: list[dict]) -> list[dict]:
    """Merge adjacent same-code annotations into single entries.

    Annotations are considered adjacent if their offset ranges are within
    5 characters of each other (to account for whitespace/newlines between
    sentence boundaries). Must share the same code_id to be merged.

    Input annotations must be sorted by start_offset.
    Returns new list (does not mutate input).
    """
    if not annotations:
        return []

    result: list[dict] = []
    current = dict(annotations[0])

    for ann in annotations[1:]:
        gap = ann["start_offset"] - current["end_offset"]
        if ann["code_id"] == current["code_id"] and 0 <= gap <= 5:
            current["end_offset"] = ann["end_offset"]
            current["selected_text"] = current["selected_text"] + " " + ann["selected_text"]
        else:
            result.append(current)
            current = dict(ann)

    result.append(current)
    return result


def export_annotations_csv(
    conn: sqlite3.Connection,
    output_path: str | Path,
    merge_adjacent: bool = True,
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

    # Convert rows to dicts for processing
    dicts: list[dict] = []
    for row in rows:
        out: dict[str, object] = {col: row[col] for col in _FIXED_COLUMNS}
        raw = row["metadata_json"]
        if raw:
            meta = json.loads(raw)
            for key in meta_keys:
                out[key] = meta.get(key, "")
        dicts.append(out)

    if merge_adjacent:
        # Group by (source_id, coder_name), merge each group, then reassemble
        from itertools import groupby

        merged: list[dict] = []
        for _key, group in groupby(dicts, key=lambda d: (d["source_id"], d["coder_name"])):
            group_list = list(group)
            # merge_adjacent_annotations expects code_id; use code_name as proxy since
            # rows are already resolved — remap to a temporary key
            for item in group_list:
                item["code_id"] = item["code_name"]
            merged_group = merge_adjacent_annotations(group_list)
            for item in merged_group:
                del item["code_id"]
            merged.extend(merged_group)
        dicts = merged

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for out in dicts:
            writer.writerow(out)

    return len(dicts)
